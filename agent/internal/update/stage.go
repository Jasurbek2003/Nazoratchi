package update

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"os"
	"path/filepath"
	"strings"
	"sync/atomic"
	"time"
)

// Standart yo'llar (install.sh yaratadi).
const (
	DefaultStageDir = "/var/lib/nazoratchi/update" // agent yozadi (nazoratchi foydalanuvchisi)
	DefaultStateDir = "/var/lib/nazoratchi-update" // faqat root yozadi; agent o'qiy oladi
	fileStaged      = "staged"                     // oxirida yoziladigan belgi: to'plam to'liq
	fileConfirmed   = "confirmed"                  // yangi agent birinchi paketni yuborgach yozadi
	filePending     = "pending.json"               // root: almashtirildi, tasdiq kutilmoqda
	fileRolledBack  = "rolled_back.json"           // root: qaytarilgan versiya (qayta urinilmaydi)
	downloadTimeout = 5 * time.Minute
)

var stagedFiles = []string{fileStaged, fileSums, fileSig, fileVersion}

// Command — core'ning `update` buyrug'i (TZ 7.7.3). Hech biriga ishonilmaydi: faqat maslahat.
// Haqiqiy versiya va xesh imzolangan `SHA256SUMS` dan olinadi.
type Command struct {
	Version string
	SHA256  string
}

type Config struct {
	CoreURL  string
	PubKey   string // minisign ochiq kaliti (base64); bo'sh bo'lsa yangilanish o'chiq
	Arch     string // runtime.GOARCH
	Current  string // ishlayotgan versiya
	StageDir string
	StateDir string
	HTTP     *http.Client
}

// Updater Stage va Confirm ni bajaradi (agent jarayoni ichida, root emas).
type Updater struct {
	cfg   Config
	pub   PublicKey
	hasPK bool
	busy  atomic.Bool
}

func New(c Config) (*Updater, error) {
	if c.StageDir == "" {
		c.StageDir = DefaultStageDir
	}
	if c.StateDir == "" {
		c.StateDir = DefaultStateDir
	}
	u := &Updater{cfg: c}
	if strings.TrimSpace(c.PubKey) != "" {
		pk, err := ParsePublicKey(c.PubKey)
		if err != nil {
			return nil, err
		}
		u.pub, u.hasPK = pk, true
	}
	return u, nil
}

// Enabled: ochiq kalit bilan yig'ilgan reliz binari.
func (u *Updater) Enabled() bool { return u.hasPK }

var ErrBusy = errors.New("yangilanish allaqachon yuklanmoqda")

// Stage yangilanishni yuklaydi, tekshiradi va StageDir ga qo'yadi. Muvaffaqiyatda agent chiqishi kerak
// (systemd qayta ishga tushiradi, ExecStartPre root almashtiradi). Xavfsizlik rad etishi *RejectError.
func (u *Updater) Stage(ctx context.Context, cmd Command) (Version, error) {
	if !u.hasPK {
		return Version{}, reject("agent minisign ochiq kalitisiz yig'ilgan")
	}
	cur, err := ParseVersion(u.cfg.Current)
	if err != nil {
		return Version{}, errDevBuild
	}
	if !u.busy.CompareAndSwap(false, true) {
		return Version{}, ErrBusy
	}
	defer u.busy.Store(false)

	// Maslahat bo'yicha oldindan tekshiruv: keraksiz yuklashdan saqlaydi (haqiqiy tekshiruv imzo bilan).
	if want, err := ParseVersion(cmd.Version); err != nil {
		return Version{}, reject("core versiyasi: %v", err)
	} else if !cur.Less(want) {
		return Version{}, reject("versiya %s hozirgi %s dan katta emas", want, cur)
	} else if u.rolledBack(want) {
		return Version{}, reject("versiya %s avval qaytarilgan (yangi reliz kutiladi)", want)
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
		{filePrefix + u.cfg.Arch, maxBinary, &b.binary},
	} {
		data, err := u.download(ctx, f.name, f.max)
		if err != nil {
			return Version{}, fmt.Errorf("%s: %w", f.name, err)
		}
		*f.dst = data
	}
	v, err := verifyBundle(u.pub, b, u.cfg.Arch, cur)
	if err != nil {
		return Version{}, err
	}
	if want, _ := ParseVersion(cmd.Version); want != v {
		return Version{}, reject("core e'lon qilgan versiya %s imzolangan VERSION (%s) ga mos emas", want, v)
	}
	if h := strings.ToLower(strings.TrimSpace(cmd.SHA256)); h != "" && h != parseSums(b.sums)[filePrefix+u.cfg.Arch] {
		return Version{}, reject("core e'lon qilgan SHA-256 imzolangan ro'yxatga mos emas")
	}
	if err := u.writeStage(b, v); err != nil {
		return Version{}, fmt.Errorf("stage yozilmadi: %w", err)
	}
	return v, nil
}

func (u *Updater) download(ctx context.Context, name string, max int64) ([]byte, error) {
	// Manzil faqat sozlamadagi core'dan va qat'iy fayl nomidan quriladi: buyruqdagi `url` ishlatilmaydi.
	url := strings.TrimRight(u.cfg.CoreURL, "/") + "/agent/v1/" + name
	ctx, cancel := context.WithTimeout(ctx, downloadTimeout)
	defer cancel()
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, url, nil)
	if err != nil {
		return nil, err
	}
	hc := u.cfg.HTTP
	if hc == nil {
		hc = http.DefaultClient
	}
	resp, err := hc.Do(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		_, _ = io.Copy(io.Discard, io.LimitReader(resp.Body, 4096))
		return nil, fmt.Errorf("HTTP %d", resp.StatusCode)
	}
	data, err := io.ReadAll(io.LimitReader(resp.Body, max+1))
	if err != nil {
		return nil, err
	}
	if int64(len(data)) > max {
		return nil, reject("%s hajmi %d baytdan katta", name, max)
	}
	return data, nil
}

func (u *Updater) writeStage(b bundle, v Version) error {
	if err := os.MkdirAll(u.cfg.StageDir, 0o700); err != nil {
		return err
	}
	for _, n := range append([]string{filePrefix + u.cfg.Arch}, stagedFiles...) {
		_ = os.Remove(filepath.Join(u.cfg.StageDir, n))
	}
	w := func(name string, data []byte) error {
		return writeAtomic(filepath.Join(u.cfg.StageDir, name), data, 0o600)
	}
	if err := w(filePrefix+u.cfg.Arch, b.binary); err != nil {
		return err
	}
	for name, data := range map[string][]byte{fileSums: b.sums, fileSig: b.sig, fileVersion: b.version} {
		if err := w(name, data); err != nil {
			return err
		}
	}
	return w(fileStaged, []byte(v.String()+"\n")) // oxirida: Apply faqat to'liq to'plamni ko'radi
}

// Confirm yangi agent ishlayotganini (birinchi paket core'ga yetdi) belgilaydi. Root bu belgini keyingi
// ishga tushirishda o'qiydi va rollbackni bekor qiladi.
func (u *Updater) Confirm() error {
	if err := os.MkdirAll(u.cfg.StageDir, 0o700); err != nil {
		return err
	}
	cur := u.cfg.Current
	if v, err := ParseVersion(cur); err == nil {
		cur = v.String() // Apply `pending.to` bilan bir xil ko'rinishda solishtiradi
	}
	return writeAtomic(filepath.Join(u.cfg.StageDir, fileConfirmed), []byte(cur+"\n"), 0o600)
}

func (u *Updater) rolledBack(v Version) bool {
	data, err := readLimited(filepath.Join(u.cfg.StateDir, fileRolledBack), maxSmall)
	if err != nil {
		return false
	}
	var rb rolledBackFile
	if json.Unmarshal(data, &rb) != nil {
		return false
	}
	got, err := ParseVersion(rb.Version)
	return err == nil && !got.Less(v) // qaytarilgan versiya va undan eskilari qayta urinilmaydi
}
