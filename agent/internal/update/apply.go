package update

import (
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"time"
)

// PendingWindow — almashtirishdan keyin yangi agent shu vaqt ichida tasdiq bermasdan qayta ishga tushsa,
// u buzuq deb hisoblanadi va eskisi qaytariladi (TZ 7.7.3: "60 soniya" — qayta ishga tushish oralig'i bilan).
const PendingWindow = 10 * time.Minute

// Outcome — Apply natijasi.
type Outcome string

const (
	OutcomeNone       Outcome = "none"
	OutcomeUpdated    Outcome = "updated"
	OutcomeRolledBack Outcome = "rolled_back"
	OutcomeRejected   Outcome = "rejected"
)

type ApplyConfig struct {
	Bin      string // /usr/local/bin/nazoratchi-agent
	StageDir string
	StateDir string // root yozadi
	PubKey   string
	Arch     string
	Current  string // ishlayotgan (o'rnatilgan) binar versiyasi
	Now      func() time.Time
	Logf     func(format string, args ...any)
}

type pending struct {
	From      string    `json:"from"`
	To        string    `json:"to"`
	AppliedAt time.Time `json:"applied_at"`
}

type rolledBackFile struct {
	Version string    `json:"version"`
	At      time.Time `json:"at"`
	Reason  string    `json:"reason"`
}

func (c *ApplyConfig) now() time.Time {
	if c.Now != nil {
		return c.Now()
	}
	return time.Now()
}

func (c *ApplyConfig) logf(format string, a ...any) {
	if c.Logf != nil {
		c.Logf(format, a...)
	}
}

// Apply `ExecStartPre=+` sifatida root bilan ishlaydi. Agent yozadigan hamma narsa (StageDir) ishonchsiz:
// to'plam bu yerda imzo bilan qayta tekshiriladi. Xatolar loglanadi, lekin agentning ishga tushishini
// to'xtatmaslik uchun chaqiruvchi har doim 0 bilan chiqadi.
func Apply(c ApplyConfig) (Outcome, error) {
	if c.Bin == "" || c.StageDir == "" || c.StateDir == "" {
		return OutcomeNone, errors.New("bin, stage va state yo'llari majburiy")
	}
	if err := os.MkdirAll(c.StateDir, 0o755); err != nil {
		return OutcomeNone, err
	}
	if fi, err := os.Stat(c.StateDir); err != nil || fi.Mode().Perm()&0o022 != 0 {
		return OutcomeNone, fmt.Errorf("%s boshqalar yoza oladigan papka: xavfsiz emas", c.StateDir)
	}
	if fi, err := os.Lstat(c.StageDir); err != nil || !fi.IsDir() {
		// Papka yo'q yoki symlink: staged yangilanish yo'q. Kutilayotgan rollback baribir tekshiriladi.
		if out, done, err := c.handlePending(); done || err != nil {
			return out, err
		}
		return OutcomeNone, nil
	}
	if out, done, err := c.handlePending(); done || err != nil {
		return out, err
	}
	return c.applyStaged()
}

func (c *ApplyConfig) path(dir, name string) string { return filepath.Join(dir, name) }

func (c *ApplyConfig) handlePending() (Outcome, bool, error) {
	data, err := readLimited(c.path(c.StateDir, filePending), maxSmall)
	if errors.Is(err, os.ErrNotExist) {
		return OutcomeNone, false, nil
	}
	if err != nil {
		return OutcomeNone, false, err
	}
	var p pending
	if err := json.Unmarshal(data, &p); err != nil {
		_ = os.Remove(c.path(c.StateDir, filePending))
		return OutcomeNone, false, fmt.Errorf("pending.json buzuq: %w", err)
	}
	defer func() { _ = os.Remove(c.path(c.StateDir, filePending)) }()

	confirmed := false
	if b, err := readLimited(c.path(c.StageDir, fileConfirmed), 64); err == nil {
		confirmed = strings.TrimSpace(string(b)) == p.To
	}
	if confirmed {
		c.logf("yangilanish tasdiqlandi: %s -> %s", p.From, p.To)
		return OutcomeNone, false, nil
	}
	if c.now().Sub(p.AppliedAt) > PendingWindow {
		c.logf("yangilanish %s tasdiqsiz, lekin %s dan beri o'tdi: oddiy qayta ishga tushish deb hisoblandi", p.To, PendingWindow)
		return OutcomeNone, false, nil
	}

	old := c.Bin + ".old"
	if _, err := os.Lstat(old); err != nil {
		return OutcomeNone, true, fmt.Errorf("rollback uchun %s yo'q: %w", old, err)
	}
	if err := os.Rename(old, c.Bin); err != nil {
		return OutcomeNone, true, fmt.Errorf("rollback bajarilmadi: %w", err)
	}
	rb, _ := json.Marshal(rolledBackFile{Version: p.To, At: c.now().UTC(), Reason: "yangi agent tasdiqlanmadi"})
	_ = writeAtomic(c.path(c.StateDir, fileRolledBack), rb, 0o644)
	c.cleanStage()
	c.logf("ROLLBACK: %s tasdiqlanmadi, %s qaytarildi", p.To, p.From)
	return OutcomeRolledBack, true, nil
}

func (c *ApplyConfig) cleanStage() {
	for _, n := range append([]string{filePrefix + c.Arch}, stagedFiles...) {
		_ = os.Remove(c.path(c.StageDir, n))
	}
}

func (c *ApplyConfig) applyStaged() (Outcome, error) {
	if _, err := readLimited(c.path(c.StageDir, fileStaged), 64); errors.Is(err, os.ErrNotExist) {
		return OutcomeNone, nil
	} else if err != nil {
		c.cleanStage()
		return OutcomeRejected, fmt.Errorf("staged belgisi o'qilmadi: %w", err)
	}
	defer c.cleanStage() // natija qanday bo'lmasin to'plam qayta ishlatilmaydi

	pub, err := ParsePublicKey(c.PubKey)
	if err != nil {
		return OutcomeRejected, fmt.Errorf("ochiq kalit: %w", err)
	}
	cur, err := ParseVersion(c.Current)
	if err != nil {
		return OutcomeRejected, errDevBuild
	}
	var b bundle
	for _, f := range []struct {
		name string
		max  int64
		dst  *[]byte
	}{
		{fileSums, maxSmall, &b.sums},
		{fileSig, maxSmall, &b.sig},
		{fileVersion, maxSmall, &b.version},
		{filePrefix + c.Arch, maxBinary, &b.binary},
	} {
		data, err := readLimited(c.path(c.StageDir, f.name), f.max)
		if err != nil {
			return OutcomeRejected, fmt.Errorf("%s: %w", f.name, err)
		}
		*f.dst = data
	}
	v, err := verifyBundle(pub, b, c.Arch, cur)
	if err != nil {
		return OutcomeRejected, err
	}
	if c.wasRolledBack(v) {
		return OutcomeRejected, reject("versiya %s avval qaytarilgan", v)
	}

	oldBytes, err := readLimited(c.Bin, maxBinary)
	if err != nil {
		return OutcomeNone, fmt.Errorf("joriy binar o'qilmadi: %w", err)
	}
	mode := os.FileMode(0o755)
	if fi, err := os.Stat(c.Bin); err == nil {
		mode = fi.Mode().Perm()
	}
	if err := writeAtomic(c.Bin+".old", oldBytes, mode); err != nil {
		return OutcomeNone, fmt.Errorf(".old yozilmadi: %w", err)
	}
	// Avval belgi, keyin almashtirish: orada uzilsa, keyingi ishga tushishda .old o'sha binarning nusxasi bo'ladi.
	pj, _ := json.Marshal(pending{From: cur.String(), To: v.String(), AppliedAt: c.now().UTC()})
	if err := writeAtomic(c.path(c.StateDir, filePending), pj, 0o644); err != nil {
		return OutcomeNone, fmt.Errorf("pending.json yozilmadi: %w", err)
	}
	if err := writeAtomic(c.Bin, b.binary, mode); err != nil {
		_ = os.Remove(c.path(c.StateDir, filePending))
		return OutcomeNone, fmt.Errorf("binar almashtirilmadi: %w", err)
	}
	_ = os.Remove(c.path(c.StateDir, fileRolledBack))
	_ = os.Remove(c.path(c.StageDir, fileConfirmed)) // eski agentning tasdig'i yangisiniki bilan adashmasin
	c.logf("yangilandi: %s -> %s", cur, v)
	return OutcomeUpdated, nil
}

func (c *ApplyConfig) wasRolledBack(v Version) bool {
	data, err := readLimited(c.path(c.StateDir, fileRolledBack), maxSmall)
	if err != nil {
		return false
	}
	var rb rolledBackFile
	if json.Unmarshal(data, &rb) != nil {
		return false
	}
	got, err := ParseVersion(rb.Version)
	return err == nil && !got.Less(v)
}
