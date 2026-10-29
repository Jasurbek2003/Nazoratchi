package collector

import (
	"context"
	"crypto/ecdsa"
	"crypto/elliptic"
	"crypto/rand"
	"crypto/x509"
	"crypto/x509/pkix"
	"encoding/pem"
	"math/big"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"
)

// writeCert o'z-o'zidan imzolangan sertifikat yozadi; withKey bo'lsa PEM oldiga maxfiy kalit ham qo'shadi
// (agent uni o'qimasligi va undan chalg'imasligini tekshirish uchun).
func writeCert(t *testing.T, path string, notAfter time.Time, withKey bool) {
	t.Helper()
	key, err := ecdsa.GenerateKey(elliptic.P256(), rand.Reader)
	if err != nil {
		t.Fatal(err)
	}
	tpl := &x509.Certificate{
		SerialNumber: big.NewInt(1), Subject: pkix.Name{CommonName: "test"},
		NotBefore: notAfter.Add(-90 * 24 * time.Hour), NotAfter: notAfter,
	}
	der, err := x509.CreateCertificate(rand.Reader, tpl, tpl, &key.PublicKey, key)
	if err != nil {
		t.Fatal(err)
	}
	var data []byte
	if withKey {
		kb, _ := x509.MarshalECPrivateKey(key)
		data = append(data, pem.EncodeToMemory(&pem.Block{Type: "EC PRIVATE KEY", Bytes: kb})...)
	}
	data = append(data, pem.EncodeToMemory(&pem.Block{Type: "CERTIFICATE", Bytes: der})...)
	if err := os.MkdirAll(filepath.Dir(path), 0o750); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(path, data, 0o600); err != nil {
		t.Fatal(err)
	}
}

func TestCertsReadsLetsEncryptLayout(t *testing.T) {
	live := t.TempDir()
	now := time.Unix(1_800_000_000, 0)
	writeCert(t, filepath.Join(live, "avlo.ai", "cert.pem"), now.Add(30*24*time.Hour), false)
	writeCert(t, filepath.Join(live, "nazar.avlo.ai", "cert.pem"), now.Add(-2*24*time.Hour), true) // muddati o'tgan
	got, err := NewCerts([]string{filepath.Join(live, "*", "cert.pem")}, "").Collect(context.Background(), now)
	if err != nil {
		t.Fatal(err)
	}
	m := byName(got)
	if v := m["cert_days_left{name=avlo.ai}"].V; !approx(v, 30) {
		t.Errorf("avlo.ai kunlari: %v", v)
	}
	if v := m["cert_days_left{name=nazar.avlo.ai}"].V; !approx(v, -2) {
		t.Errorf("muddati o'tgan sertifikat manfiy kun berishi kerak: %v", v)
	}
	if v := m["cert_not_after_timestamp{name=avlo.ai}"].V; int64(v) != now.Add(30*24*time.Hour).Unix() {
		t.Errorf("timestamp: %v", v)
	}
	for _, s := range got {
		if _, has := s.L["path"]; has {
			t.Fatalf("fayl yo'li belgi sifatida yuborilmasligi kerak: %+v", s)
		}
	}
}

func TestCertsPrefersDirectReadAndMergesHookFile(t *testing.T) {
	dir := t.TempDir()
	now := time.Unix(1_800_000_000, 0)
	direct := filepath.Join(dir, "a.example", "cert.pem")
	writeCert(t, direct, now.Add(10*24*time.Hour), false)
	hook := filepath.Join(dir, "certs.json")
	body := `{"certs":[
		{"name":"a.example","not_after":` + itoa64(now.Add(99*24*time.Hour).Unix()) + `},
		{"name":"b.example","not_after":` + itoa64(now.Add(20*24*time.Hour).Unix()) + `},
		{"name":"bad name!","not_after":1},
		{"name":"zero","not_after":0}]}`
	if err := os.WriteFile(hook, []byte(body), 0o600); err != nil {
		t.Fatal(err)
	}
	got, err := NewCerts([]string{direct}, hook).Collect(context.Background(), now)
	if err != nil {
		t.Fatal(err)
	}
	m := byName(got)
	if v := m["cert_days_left{name=a.example}"].V; !approx(v, 10) {
		t.Errorf("bevosita o'qilgan ustun bo'lishi kerak (10), %v", v)
	}
	if v := m["cert_days_left{name=b.example}"].V; !approx(v, 20) {
		t.Errorf("hook faylidan: %v", v)
	}
	if len(got) != 4 { // 2 sertifikat x 2 metrika; yaroqsiz nomlar tashlanadi
		t.Errorf("4 namuna kutilgan: %d", len(got))
	}
}

func TestCertsUnreadableCoveredByHookIsNotAnError(t *testing.T) {
	dir := t.TempDir()
	now := time.Unix(1_800_000_000, 0)
	broken := filepath.Join(dir, "x.example", "cert.pem")
	if err := os.MkdirAll(filepath.Dir(broken), 0o750); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(broken, []byte("bu sertifikat emas"), 0o600); err != nil {
		t.Fatal(err)
	}

	// hook yo'q: o'qib bo'lmayotgani xato sifatida ko'rinishi kerak (panelda ko'rinadi)
	_, err := NewCerts([]string{broken}, filepath.Join(dir, "yoq.json")).Collect(context.Background(), now)
	if err == nil || !strings.Contains(err.Error(), "x.example") {
		t.Fatalf("o'qib bo'lmaydigan sertifikat xato berishi kerak: %v", err)
	}

	// hook shu nomni berdi: xato emas
	hook := filepath.Join(dir, "certs.json")
	if err := os.WriteFile(hook, []byte(`{"certs":[{"name":"x.example","not_after":`+itoa64(now.Add(time.Hour).Unix())+`}]}`), 0o600); err != nil {
		t.Fatal(err)
	}
	got, err := NewCerts([]string{broken}, hook).Collect(context.Background(), now)
	if err != nil || len(got) != 2 {
		t.Fatalf("hook qoplagan bo'lsa xato bo'lmasligi kerak: %v, %d namuna", err, len(got))
	}
}

func TestCertsNoCertbotIsQuiet(t *testing.T) {
	dir := t.TempDir()
	got, err := NewCerts([]string{filepath.Join(dir, "*", "cert.pem")}, filepath.Join(dir, "yoq.json")).Collect(context.Background(), time.Now())
	if err != nil || len(got) != 0 {
		t.Fatalf("certbot yo'q serverda xato ham, namuna ham bo'lmasligi kerak: %v %d", err, len(got))
	}
}

func TestCertsRejectsOversizedAndKeyOnlyFiles(t *testing.T) {
	dir := t.TempDir()
	huge := filepath.Join(dir, "big", "cert.pem")
	if err := os.MkdirAll(filepath.Dir(huge), 0o750); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(huge, make([]byte, maxCertFile+10), 0o600); err != nil {
		t.Fatal(err)
	}
	keyOnly := filepath.Join(dir, "k", "cert.pem")
	if err := os.MkdirAll(filepath.Dir(keyOnly), 0o750); err != nil {
		t.Fatal(err)
	}
	k, _ := ecdsa.GenerateKey(elliptic.P256(), rand.Reader)
	kb, _ := x509.MarshalECPrivateKey(k)
	if err := os.WriteFile(keyOnly, pem.EncodeToMemory(&pem.Block{Type: "EC PRIVATE KEY", Bytes: kb}), 0o600); err != nil {
		t.Fatal(err)
	}
	got, err := NewCerts([]string{huge, keyOnly}, "").Collect(context.Background(), time.Now())
	if err == nil || len(got) != 0 {
		t.Fatalf("katta yoki faqat-kalit fayl rad etilishi kerak: %v, %d", err, len(got))
	}
}

func TestCertName(t *testing.T) {
	for in, want := range map[string]string{
		"/etc/letsencrypt/live/avlo.ai/cert.pem":      "avlo.ai",
		"/etc/letsencrypt/live/avlo.ai/fullchain.pem": "avlo.ai",
		"/srv/tls/custom.crt":                         "custom",
		"/cert.pem":                                   "cert",
	} {
		if got := certName(in); got != want {
			t.Errorf("certName(%q) = %q, kutilgan %q", in, got, want)
		}
	}
}

func TestCertsDuplicateNamesDoNotOverwrite(t *testing.T) {
	dir := t.TempDir()
	now := time.Unix(1_800_000_000, 0)
	a, b := filepath.Join(dir, "a", "site.crt"), filepath.Join(dir, "b", "site.crt")
	writeCert(t, a, now.Add(24*time.Hour), false)
	writeCert(t, b, now.Add(48*time.Hour), false)
	got, err := NewCerts([]string{a, b}, "").Collect(context.Background(), now)
	if err != nil || len(got) != 4 {
		t.Fatalf("ikkala sertifikat ham ko'rinishi kerak: %v, %d", err, len(got))
	}
}

func itoa64(v int64) string { return big.NewInt(v).String() }
