package collector

import (
	"context"
	"crypto/x509"
	"encoding/json"
	"encoding/pem"
	"errors"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"regexp"
	"strings"
	"time"

	"nazoratchi/agent/internal/metric"
)

const (
	// DefaultCertGlob — Let's Encrypt (certbot) ning standart joyi.
	DefaultCertGlob = "/etc/letsencrypt/live/*/cert.pem"
	// DefaultCertsJSON — root'da ishlaydigan certbot deploy-hook yozadigan muddatlar fayli (TZ 7.7.2).
	DefaultCertsJSON = "/var/lib/nazoratchi/certs.json"

	maxCertFile    = 64 << 10 // ommaviy sertifikat zanjiri bundan kichik; kattasi — begona fayl
	maxCertEntries = 200
)

var certNameRe = regexp.MustCompile(`^[A-Za-z0-9._*-]{1,200}$`)

// certsFile — deploy-hook yozadigan fayl formati. Maxfiy ma'lumot yo'q: faqat nom va tugash vaqti.
type certsFile struct {
	Certs []struct {
		Name     string `json:"name"`
		NotAfter int64  `json:"not_after"`
	} `json:"certs"`
}

// Certs — mahalliy sertifikatlar muddati (TZ 7.4.7, FR-TLS-005): haqiqiy domen tekshiruvidan (prober)
// farqli, ishlatilmayotgan, lekin yangilanayotgan sertifikatlarni ham ko'rsatadi.
//
// Ikki manba: (1) glob bo'yicha `cert.pem` ni bevosita o'qish (agent o'qiy olsa); (2) `certs.json`
// (root'dagi certbot deploy-hook yozadi). `/etc/letsencrypt/live` odatda root uchun yopiq, shuning
// uchun (2) tavsiya etiladi. Agent `privkey*.pem` ga **hech qachon** tegmaydi: faqat `cert.pem`.
type Certs struct {
	globs    []string
	jsonPath string
}

func NewCerts(globs []string, jsonPath string) *Certs {
	if len(globs) == 0 {
		globs = []string{DefaultCertGlob}
	}
	return &Certs{globs: globs, jsonPath: jsonPath}
}

func (c *Certs) Name() string { return "certs" }

type certEntry struct {
	name     string
	notAfter time.Time
}

func (c *Certs) Collect(_ context.Context, now time.Time) ([]metric.Sample, error) {
	var entries []certEntry
	seen := map[string]bool{}
	add := func(name string, notAfter time.Time) {
		base := name
		for i := 2; seen[name]; i++ { // bir xil nomli ikki fayl bir-birini bosib ketmasin
			name = fmt.Sprintf("%s-%d", base, i)
		}
		seen[name] = true
		entries = append(entries, certEntry{name: name, notAfter: notAfter})
	}

	failed := map[string]error{} // nom -> o'qish xatosi (ko'pincha ruxsat yo'q)
	for _, g := range c.globs {
		matches, err := filepath.Glob(g)
		if err != nil {
			return nil, fmt.Errorf("glob %q: %w", g, err)
		}
		for _, path := range matches {
			name := certName(path)
			notAfter, err := readCertNotAfter(path)
			if err != nil {
				failed[name] = err
				continue
			}
			add(name, notAfter)
		}
	}

	var errs []error
	if c.jsonPath != "" {
		fromHook, err := readCertsJSON(c.jsonPath)
		if err != nil {
			errs = append(errs, err)
		}
		for _, e := range fromHook {
			if seen[e.name] {
				continue // bevosita o'qilgani ustun
			}
			delete(failed, e.name)
			add(e.name, e.notAfter)
		}
	}
	// Faqat hook ham yopa olmagan fayllar xato: shunda "agent o'qiy olmayapti" panelda ko'rinadi.
	for name, err := range failed {
		errs = append(errs, fmt.Errorf("sertifikat %q: %w", name, err))
	}

	o := newOut(now)
	for _, e := range entries {
		o.add("cert_not_after_timestamp", float64(e.notAfter.Unix()), "name", trunc(e.name))
		o.add("cert_days_left", e.notAfter.Sub(now).Hours()/24, "name", trunc(e.name))
	}
	return o.s, errors.Join(errs...)
}

// certName: `.../live/example.com/cert.pem` -> `example.com`; boshqa yo'llar uchun fayl nomi (kengaytmasiz).
func certName(path string) string {
	base := filepath.Base(path)
	if dir := filepath.Base(filepath.Dir(path)); dir != "." && dir != string(filepath.Separator) &&
		(base == "cert.pem" || base == "fullchain.pem") {
		return dir
	}
	return strings.TrimSuffix(base, filepath.Ext(base))
}

// readCertNotAfter PEM dagi birinchi CERTIFICATE ning tugash vaqtini qaytaradi (zanjirning yaprog'i).
func readCertNotAfter(path string) (time.Time, error) {
	f, err := os.Open(path)
	if err != nil {
		return time.Time{}, err
	}
	defer f.Close()
	data, err := io.ReadAll(io.LimitReader(f, maxCertFile+1))
	if err != nil {
		return time.Time{}, err
	}
	if len(data) > maxCertFile {
		return time.Time{}, errors.New("fayl juda katta, sertifikat emas")
	}
	for {
		var block *pem.Block
		block, data = pem.Decode(data)
		if block == nil {
			return time.Time{}, errors.New("PEM da CERTIFICATE topilmadi")
		}
		if block.Type != "CERTIFICATE" { // PRIVATE KEY bo'lsa ham mazmuni o'qilmaydi va tashlanadi
			continue
		}
		cert, err := x509.ParseCertificate(block.Bytes)
		if err != nil {
			return time.Time{}, fmt.Errorf("sertifikatni o'qib bo'lmadi: %w", err)
		}
		return cert.NotAfter, nil
	}
}

func readCertsJSON(path string) ([]certEntry, error) {
	f, err := os.Open(path)
	if errors.Is(err, os.ErrNotExist) {
		return nil, nil // hook hali ishlamagan: xato emas
	}
	if err != nil {
		return nil, fmt.Errorf("%s: %w", path, err)
	}
	defer f.Close()
	var cf certsFile
	if err := json.NewDecoder(io.LimitReader(f, 1<<20)).Decode(&cf); err != nil {
		return nil, fmt.Errorf("%s: %w", path, err)
	}
	var out []certEntry
	for _, e := range cf.Certs {
		if len(out) >= maxCertEntries {
			break
		}
		if !certNameRe.MatchString(e.Name) || e.NotAfter <= 0 {
			continue
		}
		out = append(out, certEntry{name: e.Name, notAfter: time.Unix(e.NotAfter, 0)})
	}
	return out, nil
}
