package update

import (
	"context"
	"errors"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"
)

var t0 = time.Date(2026, 11, 1, 12, 0, 0, 0, time.UTC)

func TestMinisignBothAlgorithmsAndTamper(t *testing.T) {
	k := newKey(t)
	pub, err := ParsePublicKey(k.pub)
	if err != nil {
		t.Fatal(err)
	}
	msg := []byte("SHA256SUMS mazmuni\n")
	for _, alg := range []string{"Ed", "ED"} {
		if err := pub.Verify(msg, k.sign(alg, msg, "c")); err != nil {
			t.Errorf("%s: to'g'ri imzo rad etildi: %v", alg, err)
		}
		if pub.Verify([]byte("boshqa\n"), k.sign(alg, msg, "c")) == nil {
			t.Errorf("%s: o'zgargan xabar qabul qilindi", alg)
		}
	}

	other := newKey(t)
	if pub.Verify(msg, other.sign("ED", msg, "c")) == nil {
		t.Error("boshqa kalit imzosi qabul qilindi")
	}
	// kalit ID si mos, lekin imzo boshqa kalitdan (ID soxtalashtirilgan)
	forged := other
	forged.id = k.id
	if pub.Verify(msg, forged.sign("ED", msg, "c")) == nil {
		t.Error("ID soxtalashtirilgan imzo qabul qilindi")
	}
	// trusted comment o'zgartirilsa global imzo buziladi
	sig := strings.Replace(string(k.sign("ED", msg, "asl")), "trusted comment: asl", "trusted comment: soxta", 1)
	if pub.Verify(msg, []byte(sig)) == nil {
		t.Error("trusted comment o'zgartirilgan imzo qabul qilindi")
	}
	for _, bad := range []string{"", "untrusted comment: x\nAAAA\n", strings.Repeat("a", 5000)} {
		if pub.Verify(msg, []byte(bad)) == nil {
			t.Errorf("buzuq imzo fayli qabul qilindi: %.20q", bad)
		}
	}
}

func TestParsePublicKeyAcceptsFileAndRejectsGarbage(t *testing.T) {
	k := newKey(t)
	if _, err := ParsePublicKey("untrusted comment: minisign public key\n" + k.pub + "\n"); err != nil {
		t.Errorf(".pub fayl matni: %v", err)
	}
	for _, bad := range []string{"", "!!!", "QUJD", k.pub[:20]} {
		if _, err := ParsePublicKey(bad); err == nil {
			t.Errorf("yaroqsiz kalit qabul qilindi: %q", bad)
		}
	}
}

func TestVersionParsingAndOrder(t *testing.T) {
	for in, want := range map[string]string{"1.2.3": "1.2.3", "v2.0": "2.0.0", " 3 ": "3.0.0"} {
		v, err := ParseVersion(in)
		if err != nil || v.String() != want {
			t.Errorf("ParseVersion(%q) = %v, %v", in, v, err)
		}
	}
	for _, bad := range []string{"", "dev", "1.2.3-rc1", "1.2.3.4", "01.2.3", "-1.0.0", "1.x"} {
		if _, err := ParseVersion(bad); err == nil {
			t.Errorf("ParseVersion(%q) xato berishi kerak", bad)
		}
	}
	a, _ := ParseVersion("1.9.0")
	b, _ := ParseVersion("1.10.0")
	if !a.Less(b) || b.Less(a) || a.Less(a) {
		t.Error("1.9.0 < 1.10.0 (raqamli solishtirish)")
	}
}

func TestStageDownloadsVerifiesAndWritesMarkerLast(t *testing.T) {
	k, e := newKey(t), newEnv(t, "eski-binar")
	rel := makeRelease(k, "ED", "1.1.0", []byte("YANGI-BINAR"))
	srv, hits := serve(t, rel)
	v, err := e.updater(t, k, srv.URL, "1.0.0").Stage(context.Background(), Command{Version: "1.1.0", SHA256: sha([]byte("YANGI-BINAR"))})
	if err != nil || v.String() != "1.1.0" {
		t.Fatalf("Stage: %v %v", v, err)
	}
	if got := read(t, filepath.Join(e.stage, filePrefix+arch)); got != "YANGI-BINAR" {
		t.Errorf("binar: %q", got)
	}
	if !exists(filepath.Join(e.stage, fileStaged)) {
		t.Error("staged belgisi yozilishi kerak")
	}
	if len(*hits) != 4 {
		t.Errorf("faqat 4 ta qat'iy fayl so'ralishi kerak: %v", *hits)
	}
	for _, h := range *hits {
		if !strings.HasPrefix(h, "/agent/v1/") {
			t.Errorf("kutilmagan yo'l: %s", h)
		}
	}
}

func TestStageRejections(t *testing.T) {
	k, evil := newKey(t), newKey(t)
	cases := []struct {
		name    string
		release func() release
		current string
		cmd     Command
	}{
		{"begona kalit imzosi (T-U-SEC-11)", func() release { return makeRelease(evil, "ED", "1.1.0", []byte("X")) }, "1.0.0", Command{Version: "1.1.0"}},
		{"binar almashtirilgan", func() release {
			r := makeRelease(k, "ED", "1.1.0", []byte("ASL"))
			r.files[filePrefix+arch] = []byte("ZARARLI")
			return r
		}, "1.0.0", Command{Version: "1.1.0"}},
		{"SHA256SUMS almashtirilgan, imzo eskisi", func() release {
			r := makeRelease(k, "ED", "1.1.0", []byte("ASL"))
			r.files[fileSums] = []byte(sha([]byte("ZARARLI")) + "  " + filePrefix + arch + "\n")
			return r
		}, "1.0.0", Command{Version: "1.1.0"}},
		{"VERSION almashtirilgan (eski imzolangan binar yangi deb ko'rsatilmoqda)", func() release {
			r := makeRelease(k, "ED", "1.0.5", []byte("ESKI-IMZOLANGAN"))
			r.files[fileVersion] = []byte("9.9.9\n")
			return r
		}, "1.0.0", Command{Version: "9.9.9"}},
		{"orqaga qaytarish: imzolangan, lekin eski", func() release { return makeRelease(k, "ED", "0.9.0", []byte("ESKI")) }, "1.0.0", Command{Version: "0.9.0"}},
		{"bir xil versiya", func() release { return makeRelease(k, "ED", "1.0.0", []byte("BIR-XIL")) }, "1.0.0", Command{Version: "1.0.0"}},
		{"core boshqa versiya e'lon qildi", func() release { return makeRelease(k, "ED", "1.1.0", []byte("X")) }, "1.0.0", Command{Version: "1.5.0"}},
		{"core boshqa SHA-256 e'lon qildi", func() release { return makeRelease(k, "ED", "1.1.0", []byte("X")) }, "1.0.0", Command{Version: "1.1.0", SHA256: strings.Repeat("0", 64)}},
		{"yaroqsiz versiya", func() release { return makeRelease(k, "ED", "1.1.0", []byte("X")) }, "1.0.0", Command{Version: "yangi"}},
	}
	for _, c := range cases {
		t.Run(c.name, func(t *testing.T) {
			e := newEnv(t, "eski")
			srv, _ := serve(t, c.release())
			_, err := e.updater(t, k, srv.URL, c.current).Stage(context.Background(), c.cmd)
			var rej *RejectError
			if !errors.As(err, &rej) {
				t.Fatalf("RejectError kutilgan, olindi: %v", err)
			}
			if exists(filepath.Join(e.stage, fileStaged)) {
				t.Error("rad etilgan yangilanish staged belgisini qoldirmasligi kerak")
			}
		})
	}
}

func TestStageTransientErrorsAreNotRejections(t *testing.T) {
	k, e := newKey(t), newEnv(t, "eski")
	rel := makeRelease(k, "ED", "1.1.0", []byte("X"))
	delete(rel.files, fileSig) // core vaqtincha fayl bermayapti: 404
	srv, _ := serve(t, rel)
	_, err := e.updater(t, k, srv.URL, "1.0.0").Stage(context.Background(), Command{Version: "1.1.0"})
	var rej *RejectError
	if err == nil || errors.As(err, &rej) {
		t.Fatalf("tarmoq/404 xatosi rad etish emas: %v", err)
	}
}

func TestStageRefusesDevBuildAndMissingKey(t *testing.T) {
	k, e := newKey(t), newEnv(t, "eski")
	srv, _ := serve(t, makeRelease(k, "ED", "1.1.0", []byte("X")))
	if _, err := e.updater(t, k, srv.URL, "dev").Stage(context.Background(), Command{Version: "1.1.0"}); !errors.Is(err, errDevBuild) {
		t.Errorf("dev build yangilanmasligi kerak: %v", err)
	}
	u, err := New(Config{CoreURL: srv.URL, Arch: arch, Current: "1.0.0", StageDir: e.stage, StateDir: e.state})
	if err != nil || u.Enabled() {
		t.Fatalf("kalitsiz updater o'chiq bo'lishi kerak: %v", err)
	}
	var rej *RejectError
	if _, err := u.Stage(context.Background(), Command{Version: "1.1.0"}); !errors.As(err, &rej) {
		t.Errorf("kalitsiz Stage rad etishi kerak: %v", err)
	}
}

func TestStageOversizeBinaryRejected(t *testing.T) {
	k, e := newKey(t), newEnv(t, "eski")
	// maxBinary dan katta binarni test uchun kichraytirib bo'lmaydi; maxSmall chegarasi SHA256SUMS da tekshiriladi.
	rel := makeRelease(k, "ED", "1.1.0", []byte("X"))
	rel.files[fileSums] = append(rel.files[fileSums], []byte(strings.Repeat("a", maxSmall+10))...)
	srv, _ := serve(t, rel)
	_, err := e.updater(t, k, srv.URL, "1.0.0").Stage(context.Background(), Command{Version: "1.1.0"})
	var rej *RejectError
	if !errors.As(err, &rej) {
		t.Fatalf("katta fayl rad etilishi kerak: %v", err)
	}
}

func TestStageSkipsVersionRolledBackBefore(t *testing.T) {
	k, e := newKey(t), newEnv(t, "eski")
	if err := os.WriteFile(filepath.Join(e.state, fileRolledBack), []byte(`{"version":"1.1.0"}`), 0o644); err != nil {
		t.Fatal(err)
	}
	srv, hits := serve(t, makeRelease(k, "ED", "1.1.0", []byte("X")))
	var rej *RejectError
	if _, err := e.updater(t, k, srv.URL, "1.0.0").Stage(context.Background(), Command{Version: "1.1.0"}); !errors.As(err, &rej) {
		t.Fatalf("qaytarilgan versiya rad etilishi kerak: %v", err)
	}
	if len(*hits) != 0 {
		t.Error("qaytarilgan versiya uchun yuklash boshlanmasligi kerak")
	}
	// undan yangi versiya qabul qilinadi
	srv2, _ := serve(t, makeRelease(k, "ED", "1.2.0", []byte("Y")))
	if _, err := e.updater(t, k, srv2.URL, "1.0.0").Stage(context.Background(), Command{Version: "1.2.0"}); err != nil {
		t.Fatalf("yangiroq versiya qabul qilinishi kerak: %v", err)
	}
}

// ---- Apply (root) ----

func stageRelease(t *testing.T, k testKey, e env, alg, version, binary, current string) {
	t.Helper()
	srv, _ := serve(t, makeRelease(k, alg, version, []byte(binary)))
	if _, err := e.updater(t, k, srv.URL, current).Stage(context.Background(), Command{Version: version}); err != nil {
		t.Fatal(err)
	}
}

func TestApplySwapsKeepsOldAndRequiresConfirmation(t *testing.T) {
	k, e := newKey(t), newEnv(t, "ESKI-BINAR")
	stageRelease(t, k, e, "ED", "1.1.0", "YANGI-BINAR", "1.0.0")

	out, err := Apply(e.apply(k, "1.0.0", t0))
	if err != nil || out != OutcomeUpdated {
		t.Fatalf("Apply: %v %v", out, err)
	}
	if read(t, e.bin) != "YANGI-BINAR" || read(t, e.bin+".old") != "ESKI-BINAR" {
		t.Error("binar almashtirilib, eskisi .old ga saqlanishi kerak")
	}
	if fi, _ := os.Stat(e.bin); fi.Mode().Perm() != 0o755 {
		t.Errorf("ruxsat saqlanishi kerak: %v", fi.Mode().Perm())
	}
	if !exists(filepath.Join(e.state, filePending)) || exists(filepath.Join(e.stage, fileStaged)) {
		t.Error("pending yozilib, staged tozalanishi kerak")
	}

	// Yangi agent birinchi paketni yubordi -> tasdiq; keyingi ishga tushishda rollback yo'q
	up := e.updater(t, k, "http://x", "1.1.0")
	if err := up.Confirm(); err != nil {
		t.Fatal(err)
	}
	out, err = Apply(e.apply(k, "1.1.0", t0.Add(time.Minute)))
	if err != nil || out != OutcomeNone || read(t, e.bin) != "YANGI-BINAR" {
		t.Fatalf("tasdiqlangan yangilanish saqlanishi kerak: %v %v", out, err)
	}
	if exists(filepath.Join(e.state, filePending)) {
		t.Error("pending tasdiqdan keyin o'chirilishi kerak")
	}
}

func TestApplyRollsBackUnconfirmedAndBlocksRetry(t *testing.T) {
	k, e := newKey(t), newEnv(t, "ESKI-BINAR")
	stageRelease(t, k, e, "Ed", "1.1.0", "BUZUQ-YANGI", "1.0.0")
	if out, err := Apply(e.apply(k, "1.0.0", t0)); err != nil || out != OutcomeUpdated {
		t.Fatalf("%v %v", out, err)
	}
	// Yangi agent tasdiqsiz qayta ishga tushdi (2 daqiqada): eskisi qaytariladi
	out, err := Apply(e.apply(k, "1.1.0", t0.Add(2*time.Minute)))
	if err != nil || out != OutcomeRolledBack {
		t.Fatalf("rollback kutilgan: %v %v", out, err)
	}
	if read(t, e.bin) != "ESKI-BINAR" {
		t.Error("eski binar qaytarilishi kerak")
	}
	if !strings.Contains(read(t, filepath.Join(e.state, fileRolledBack)), "1.1.0") {
		t.Error("qaytarilgan versiya qayd etilishi kerak")
	}
	// Core shu versiyani yana yuborsa — Stage ham, Apply ham rad etadi
	srv, hits := serve(t, makeRelease(k, "Ed", "1.1.0", []byte("BUZUQ-YANGI")))
	var rej *RejectError
	if _, err := e.updater(t, k, srv.URL, "1.0.0").Stage(context.Background(), Command{Version: "1.1.0"}); !errors.As(err, &rej) || len(*hits) != 0 {
		t.Errorf("qaytarilgan versiya qayta yuklanmasligi kerak: %v, %d so'rov", err, len(*hits))
	}
}

func TestApplyLateUnconfirmedRestartIsNotRollback(t *testing.T) {
	k, e := newKey(t), newEnv(t, "ESKI")
	stageRelease(t, k, e, "ED", "1.1.0", "YANGI", "1.0.0")
	if _, err := Apply(e.apply(k, "1.0.0", t0)); err != nil {
		t.Fatal(err)
	}
	// core soatlab ulanmadi, so'ng host reboot bo'ldi: oddiy qayta ishga tushish, rollback emas
	out, err := Apply(e.apply(k, "1.1.0", t0.Add(PendingWindow+time.Minute)))
	if err != nil || out != OutcomeNone || read(t, e.bin) != "YANGI" {
		t.Fatalf("kech qayta ishga tushish rollback bermasligi kerak: %v %v", out, err)
	}
}

func TestApplyRejectsTamperedStageByCompromisedAgent(t *testing.T) {
	k, e := newKey(t), newEnv(t, "ESKI")
	stageRelease(t, k, e, "ED", "1.1.0", "ASL", "1.0.0")
	// Agent jarayoni buzilgan: staged binarni ixtiyoriy narsaga almashtirdi (imzo va ro'yxat o'sha-o'sha)
	if err := os.WriteFile(filepath.Join(e.stage, filePrefix+arch), []byte("ROOT-SHELL"), 0o600); err != nil {
		t.Fatal(err)
	}
	out, err := Apply(e.apply(k, "1.0.0", t0))
	if out != OutcomeRejected || err == nil {
		t.Fatalf("buzilgan staged rad etilishi kerak: %v %v", out, err)
	}
	if read(t, e.bin) != "ESKI" {
		t.Fatal("o'rnatilgan binar o'zgarmasligi kerak")
	}
	if exists(filepath.Join(e.stage, fileStaged)) {
		t.Error("rad etilgan to'plam tozalanishi kerak")
	}
}

func TestApplyRejectsAgentForgedSignatureAndDowngrade(t *testing.T) {
	k, evil, e := newKey(t), newKey(t), newEnv(t, "ESKI")
	// Agent o'z kaliti bilan to'liq "to'g'ri" to'plam yasadi
	forged := makeRelease(evil, "ED", "2.0.0", []byte("ZARARLI"))
	if err := os.MkdirAll(e.stage, 0o700); err != nil {
		t.Fatal(err)
	}
	for name, data := range forged.files {
		if err := os.WriteFile(filepath.Join(e.stage, name), data, 0o600); err != nil {
			t.Fatal(err)
		}
	}
	if err := os.WriteFile(filepath.Join(e.stage, fileStaged), []byte("2.0.0\n"), 0o600); err != nil {
		t.Fatal(err)
	}
	if out, err := Apply(e.apply(k, "1.0.0", t0)); out != OutcomeRejected || err == nil || read(t, e.bin) != "ESKI" {
		t.Fatalf("begona kalit rad etilishi kerak: %v %v", out, err)
	}

	// To'g'ri imzo, lekin eski versiya (rollback hujumi)
	old := makeRelease(k, "ED", "0.5.0", []byte("ESKI-LEKIN-IMZOLI"))
	for name, data := range old.files {
		if err := os.WriteFile(filepath.Join(e.stage, name), data, 0o600); err != nil {
			t.Fatal(err)
		}
	}
	if err := os.WriteFile(filepath.Join(e.stage, fileStaged), []byte("0.5.0\n"), 0o600); err != nil {
		t.Fatal(err)
	}
	if out, err := Apply(e.apply(k, "1.0.0", t0)); out != OutcomeRejected || err == nil || read(t, e.bin) != "ESKI" {
		t.Fatalf("eski versiya rad etilishi kerak: %v %v", out, err)
	}
}

func TestApplyDoesNotFollowSymlinksInStage(t *testing.T) {
	k, e := newKey(t), newEnv(t, "ESKI")
	stageRelease(t, k, e, "ED", "1.1.0", "ASL", "1.0.0")
	secret := filepath.Join(t.TempDir(), "sir")
	if err := os.WriteFile(secret, []byte("ASL"), 0o600); err != nil { // mazmuni to'g'ri binarga teng bo'lsa ham symlink rad etiladi
		t.Fatal(err)
	}
	bin := filepath.Join(e.stage, filePrefix+arch)
	_ = os.Remove(bin)
	if err := os.Symlink(secret, bin); err != nil {
		t.Skip("symlink yaratib bo'lmadi:", err)
	}
	if out, err := Apply(e.apply(k, "1.0.0", t0)); out != OutcomeRejected || err == nil || read(t, e.bin) != "ESKI" {
		t.Fatalf("symlink rad etilishi kerak: %v %v", out, err)
	}
}

func TestApplyRefusesWritableStateDirAndSymlinkedStageDir(t *testing.T) {
	k, e := newKey(t), newEnv(t, "ESKI")
	if err := os.Chmod(e.state, 0o777); err != nil {
		t.Fatal(err)
	}
	if _, err := Apply(e.apply(k, "1.0.0", t0)); err == nil {
		t.Error("hamma yoza oladigan holat papkasi rad etilishi kerak")
	}
	if err := os.Chmod(e.state, 0o755); err != nil {
		t.Fatal(err)
	}

	real := t.TempDir()
	if err := os.Symlink(real, e.stage); err != nil {
		t.Skip("symlink yaratib bo'lmadi:", err)
	}
	if err := os.WriteFile(filepath.Join(real, fileStaged), []byte("9.9.9\n"), 0o600); err != nil {
		t.Fatal(err)
	}
	if out, err := Apply(e.apply(k, "1.0.0", t0)); err != nil || out != OutcomeNone {
		t.Errorf("symlink bo'lgan stage papkasi e'tiborsiz qoldirilishi kerak: %v %v", out, err)
	}
	if !exists(filepath.Join(real, fileStaged)) {
		t.Error("symlink orqali boshqa papkaga tegilmasligi kerak")
	}
}

func TestApplyNothingStagedIsNoop(t *testing.T) {
	k, e := newKey(t), newEnv(t, "ESKI")
	if out, err := Apply(e.apply(k, "1.0.0", t0)); err != nil || out != OutcomeNone || read(t, e.bin) != "ESKI" {
		t.Fatalf("%v %v", out, err)
	}
	if err := os.MkdirAll(e.stage, 0o700); err != nil {
		t.Fatal(err)
	}
	if out, err := Apply(e.apply(k, "1.0.0", t0)); err != nil || out != OutcomeNone {
		t.Fatalf("bo'sh stage: %v %v", out, err)
	}
}
