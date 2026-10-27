package collector

import (
	"context"
	"encoding/json"
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
	// DefaultBackupRoot va DefaultAppctlConf — TZ 7.4.6.
	DefaultBackupRoot = "/opt/applications/backups"
	DefaultAppctlConf = "/opt/applications/appctl.conf"
	maxBackupProjects = 100
	maxStateBytes     = 1 << 20
)

var projectNameRe = regexp.MustCompile(`^[A-Za-z0-9_\-]{1,60}$`)

// Backup — zaxira holati (TZ 7.4.6, F1): `appctl` yozgan state.json + papka skaneri. Fayl hajmi `du` bilan
// hisoblanmaydi (faqat ReadDir + Info), shuning uchun katta papkalarda ham tez. state.json dagi `error`
// matni hech qaerga yuborilmaydi (kardinallik va maxfiylik).
type Backup struct {
	root       string
	appctlConf string
}

func NewBackup(root, appctlConf string) *Backup {
	if root == "" {
		root = DefaultBackupRoot
	}
	if appctlConf == "" {
		appctlConf = DefaultAppctlConf
	}
	return &Backup{root: root, appctlConf: appctlConf}
}

func (b *Backup) Name() string { return "backup" }

type backupFile struct {
	size  int64
	mtime time.Time
}

// backupState — state.json (TZ 10.3.1) ning bizga kerakli qismi.
type backupState struct {
	Status     string `json:"status"`
	FinishedAt string `json:"finished_at"`
	Daily      *struct {
		SizeBytes int64 `json:"size_bytes"`
	} `json:"daily"`
}

func (b *Backup) Collect(_ context.Context, now time.Time) ([]metric.Sample, error) {
	o := newOut(now)
	var errs []error
	entries, err := os.ReadDir(b.root)
	switch {
	case errors.Is(err, os.ErrNotExist):
		// zaxira ildizi yo'q (bu serverda zaxira yo'q): xato emas
	case err != nil:
		errs = append(errs, fmt.Errorf("zaxira papkasi o'qilmadi: %w", err))
	default:
		n := 0
		for _, e := range entries {
			name := e.Name()
			if !e.IsDir() || strings.HasPrefix(name, "_") || !projectNameRe.MatchString(name) {
				continue // oddiy fayl, simvolik havola (Type() lstat asosida) yoki loyiha emas
			}
			if n++; n > maxBackupProjects {
				errs = append(errs, fmt.Errorf("loyihalar %d dan ko'p, ortiqchasi o'tkazib yuborildi", maxBackupProjects))
				break
			}
			if err := b.project(o, now, name); err != nil {
				errs = append(errs, err)
			}
		}
	}
	if v, ok := b.offsiteConfigured(); ok {
		o.add("backup_offsite_configured", v)
	}
	return o.s, errors.Join(errs...)
}

// scanDir: oddiy, yashirin bo'lmagan va `.tmp` bilan tugamaydigan fayllar. ok=false — papka yo'q.
func scanDir(dir string) (files map[string]backupFile, ok bool, err error) {
	if fi, lerr := os.Lstat(dir); lerr == nil && !fi.IsDir() {
		return nil, false, nil // simvolik havola yoki fayl: kuzatilmaydi
	}
	entries, err := os.ReadDir(dir)
	if errors.Is(err, os.ErrNotExist) {
		return nil, false, nil
	}
	if err != nil {
		return nil, false, err
	}
	files = map[string]backupFile{}
	for _, e := range entries {
		name := e.Name()
		if !e.Type().IsRegular() || strings.HasPrefix(name, ".") || strings.HasSuffix(name, ".tmp") {
			continue
		}
		info, err := e.Info()
		if err != nil {
			continue // skanerlash paytida o'chirilgan
		}
		files[name] = backupFile{size: info.Size(), mtime: info.ModTime()}
	}
	return files, true, nil
}

func newest(files map[string]backupFile, match func(string) bool) (backupFile, int) {
	var best backupFile
	n := 0
	for name, f := range files {
		if !match(name) {
			continue
		}
		if n == 0 || f.mtime.After(best.mtime) {
			best = f
		}
		n++
	}
	return best, n
}

func (b *Backup) project(o *out, now time.Time, name string) error {
	dir := filepath.Join(b.root, name)
	var errs []error

	daily, dailyOK, err := scanDir(filepath.Join(dir, "daily"))
	if err != nil {
		errs = append(errs, fmt.Errorf("%s: daily papkasi o'qilmadi: %w", name, err))
	}
	weekly, _, err := scanDir(filepath.Join(dir, "weekly"))
	if err != nil {
		errs = append(errs, fmt.Errorf("%s: weekly papkasi o'qilmadi: %w", name, err))
	}
	isFiles := func(n string) bool { return strings.Contains(n, "-files-") }
	groups := []struct {
		kind  string
		files map[string]backupFile
		match func(string) bool
		show0 bool
	}{
		{"daily", daily, func(string) bool { return true }, dailyOK},
		{"weekly", weekly, func(n string) bool { return !isFiles(n) }, false},
		{"files", weekly, isFiles, false},
	}
	var newestDaily backupFile
	haveDaily := false
	for _, g := range groups {
		f, n := newest(g.files, g.match)
		if n > 0 {
			o.add("backup_newest_file_age_seconds", max(0, now.Sub(f.mtime).Seconds()), "project", name, "kind", g.kind)
		}
		if n > 0 || g.show0 {
			o.add("backup_files_count", float64(n), "project", name, "kind", g.kind)
		}
		if g.kind == "daily" && n > 0 {
			newestDaily, haveDaily = f, true
		}
	}

	st, stErr := readState(filepath.Join(dir, "state.json"))
	// state.json hali yo'q (appctl hali yozmagan): xato emas, faqat papka skaneri metrikalari chiqadi.
	if stErr != nil && !errors.Is(stErr, os.ErrNotExist) {
		errs = append(errs, fmt.Errorf("%s: %w", name, stErr))
	}
	ok := st != nil && st.Status == "ok"
	if st != nil {
		status := 0.0
		if ok {
			status = 1
		}
		o.add("backup_last_status", status, "project", name)
	}
	switch {
	case ok:
		if t, err := time.Parse(time.RFC3339, st.FinishedAt); err == nil {
			o.add("backup_last_success_timestamp", float64(t.Unix()), "project", name)
		} else if haveDaily {
			o.add("backup_last_success_timestamp", float64(newestDaily.mtime.Unix()), "project", name)
		}
	case haveDaily:
		o.add("backup_last_success_timestamp", float64(newestDaily.mtime.Unix()), "project", name)
	}
	switch {
	case ok && st.Daily != nil:
		o.add("backup_last_size_bytes", float64(max(0, st.Daily.SizeBytes)), "project", name)
	case haveDaily:
		o.add("backup_last_size_bytes", float64(newestDaily.size), "project", name)
	}
	return errors.Join(errs...)
}

// readFileLimited oddiy faylni o'qiydi (simvolik havola rad etiladi); 1 MB dan katta bo'lsa xato.
func readFileLimited(path string) ([]byte, error) {
	fi, err := os.Lstat(path)
	if err != nil {
		return nil, err
	}
	if !fi.Mode().IsRegular() {
		return nil, errors.New("oddiy fayl emas")
	}
	f, err := os.Open(path)
	if err != nil {
		return nil, err
	}
	defer f.Close()
	data, err := io.ReadAll(io.LimitReader(f, maxStateBytes+1))
	if err != nil {
		return nil, err
	}
	if len(data) > maxStateBytes {
		return nil, errors.New("fayl 1 MB dan katta")
	}
	return data, nil
}

// readState: yo'q yoki yaroqsiz bo'lsa nil va xato (xato matnida fayl mazmuni YO'Q).
func readState(path string) (*backupState, error) {
	data, err := readFileLimited(path)
	if err != nil {
		return nil, fmt.Errorf("state.json o'qilmadi: %w", err)
	}
	var st backupState
	if err := json.Unmarshal(data, &st); err != nil {
		return nil, errors.New("state.json yaroqsiz JSON")
	}
	if st.Status != "ok" && st.Status != "fail" {
		return nil, errors.New("state.json: status ok yoki fail emas")
	}
	return &st, nil
}

// offsiteConfigured: avval `_run.json`, keyin appctl.conf dagi `OFFSITE=`. ok=false — ikkalasi ham o'qilmadi.
func (b *Backup) offsiteConfigured() (float64, bool) {
	if data, err := readFileLimited(filepath.Join(b.root, "_run.json")); err == nil {
		var run struct {
			Offsite *struct {
				Configured *bool `json:"configured"`
			} `json:"offsite"`
		}
		if json.Unmarshal(data, &run) == nil && run.Offsite != nil && run.Offsite.Configured != nil {
			if *run.Offsite.Configured {
				return 1, true
			}
			return 0, true
		}
	}
	data, err := readFileLimited(b.appctlConf)
	if err != nil {
		return 0, false
	}
	if parseOffsite(string(data)) != "" {
		return 1, true
	}
	return 0, true
}

// parseOffsite OFFSITE qiymatini matn sifatida topadi (`source` qilinmaydi); oxirgi tayinlash ustun.
func parseOffsite(conf string) string {
	val := ""
	for _, line := range strings.Split(conf, "\n") {
		line = strings.TrimSpace(line)
		line = strings.TrimSpace(strings.TrimPrefix(line, "export "))
		rest, ok := strings.CutPrefix(line, "OFFSITE=")
		if !ok {
			continue
		}
		val = shellValue(rest)
	}
	return val
}

func shellValue(s string) string {
	if s == "" {
		return ""
	}
	if q := s[0]; q == '"' || q == '\'' {
		if end := strings.IndexByte(s[1:], q); end >= 0 {
			return strings.TrimSpace(s[1 : 1+end])
		}
		return strings.TrimSpace(s[1:])
	}
	if i := strings.IndexAny(s, " \t#;"); i >= 0 {
		s = s[:i]
	}
	return s
}
