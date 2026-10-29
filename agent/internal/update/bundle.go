package update

import (
	"bytes"
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"strings"
)

// Reliz fayllari (core `/agent/v1/<nom>` dan; TZ 15.x). VERSION ham SHA256SUMS ichida, ya'ni imzolangan:
// shuning uchun core versiyani o'zboshimcha ko'rsata olmaydi va eski imzolangan binarni "yangi" deb
// o'tkaza olmaydi (rollback hujumi, 14.5.4).
const (
	fileSums    = "SHA256SUMS"
	fileSig     = "SHA256SUMS.minisig"
	fileVersion = "VERSION"
	filePrefix  = "nazoratchi-agent-"

	maxSmall  = 64 << 10 // SHA256SUMS, imzo, VERSION
	maxBinary = 64 << 20
)

// RejectError — xavfsizlik tekshiruvidan o'tmagan yangilanish (tarmoq xatosi emas). Hisoblanadi va qayd etiladi.
type RejectError struct{ Reason string }

func (e *RejectError) Error() string { return "yangilanish rad etildi: " + e.Reason }

func reject(format string, a ...any) error { return &RejectError{Reason: fmt.Sprintf(format, a...)} }

// bundle — bir reliz fayllari (xotirada: tekshirilgan baytlar yoziladi, qayta o'qilmaydi — TOCTOU yo'q).
type bundle struct{ sums, sig, version, binary []byte }

func parseSums(b []byte) map[string]string {
	m := map[string]string{}
	for _, line := range strings.Split(string(b), "\n") {
		f := strings.Fields(line)
		if len(f) != 2 || len(f[0]) != 64 {
			continue
		}
		name := strings.TrimPrefix(f[1], "*")
		if name == "" || strings.ContainsAny(name, "/\\") {
			continue
		}
		m[name] = strings.ToLower(f[0])
	}
	return m
}

func hexSum(b []byte) string {
	s := sha256.Sum256(b)
	return hex.EncodeToString(s[:])
}

// verifyBundle imzo, xesh va versiya (faqat oldinga) ni tekshiradi. Stage ham, Apply ham aynan shuni ishlatadi.
func verifyBundle(pub PublicKey, b bundle, arch string, current Version) (Version, error) {
	if err := pub.Verify(b.sums, b.sig); err != nil {
		return Version{}, reject("%v", err)
	}
	sums := parseSums(b.sums)
	if want, ok := sums[fileVersion]; !ok || want != hexSum(b.version) {
		return Version{}, reject("VERSION fayli imzolangan ro'yxatga mos emas")
	}
	v, err := ParseVersion(string(bytes.TrimSpace(b.version)))
	if err != nil {
		return Version{}, reject("%v", err)
	}
	name := filePrefix + arch
	if want, ok := sums[name]; !ok || want != hexSum(b.binary) {
		return Version{}, reject("%s SHA-256 imzolangan ro'yxatga mos emas", name)
	}
	if !current.Less(v) {
		return Version{}, reject("versiya %s hozirgi %s dan katta emas (orqaga qaytarishdan himoya)", v, current)
	}
	return v, nil
}

// readLimited fayl yo'lini kuzatmasdan (symlink rad etiladi) va hajm chegarasi bilan o'qiydi.
func readLimited(path string, max int64) ([]byte, error) {
	f, err := openNoFollow(path)
	if err != nil {
		return nil, err
	}
	defer f.Close()
	fi, err := f.Stat()
	if err != nil {
		return nil, err
	}
	if !fi.Mode().IsRegular() {
		return nil, errors.New("oddiy fayl emas")
	}
	data, err := io.ReadAll(io.LimitReader(f, max+1))
	if err != nil {
		return nil, err
	}
	if int64(len(data)) > max {
		return nil, fmt.Errorf("fayl %d baytdan katta", max)
	}
	return data, nil
}

// writeAtomic vaqtinchalik fayl + fsync + rename bilan yozadi.
func writeAtomic(path string, data []byte, mode os.FileMode) error {
	tmp, err := os.CreateTemp(filepath.Dir(path), ".tmp-*")
	if err != nil {
		return err
	}
	name := tmp.Name()
	ok := false
	defer func() {
		if !ok {
			_ = os.Remove(name)
		}
	}()
	if _, err := tmp.Write(data); err != nil {
		_ = tmp.Close()
		return err
	}
	if err := tmp.Chmod(mode); err != nil {
		_ = tmp.Close()
		return err
	}
	if err := tmp.Sync(); err != nil {
		_ = tmp.Close()
		return err
	}
	if err := tmp.Close(); err != nil {
		return err
	}
	if err := os.Rename(name, path); err != nil {
		return err
	}
	ok = true
	return nil
}
