package collector

import (
	"context"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"

	"nazoratchi/agent/internal/metric"
)

var backupNow = time.Date(2026, 10, 22, 12, 0, 0, 0, time.UTC)

// bk — soxta zaxira daraxti yordamchisi.
type bk struct {
	t    *testing.T
	root string
}

func newBK(t *testing.T) *bk { return &bk{t: t, root: t.TempDir()} }

func (b *bk) write(rel, body string, mtime time.Time) {
	b.t.Helper()
	p := filepath.Join(b.root, rel)
	if err := os.MkdirAll(filepath.Dir(p), 0o750); err != nil {
		b.t.Fatal(err)
	}
	if err := os.WriteFile(p, []byte(body), 0o600); err != nil {
		b.t.Fatal(err)
	}
	if !mtime.IsZero() {
		if err := os.Chtimes(p, mtime, mtime); err != nil {
			b.t.Fatal(err)
		}
	}
}

func (b *bk) collect(conf string) (map[string]metric.Sample, error) {
	b.t.Helper()
	s, err := NewBackup(b.root, conf).Collect(context.Background(), backupNow)
	return byName(s), err
}

const okState = `{"schema":1,"project":"Biz","status":"ok","started_at":"2026-10-22T03:15:01Z","finished_at":"2026-10-22T03:15:41Z",` +
	`"duration_s":40,"daily":{"status":"ok","file":"Biz-1.sql.gz","size_bytes":48273114,"error":null},"weekly_files":null}`

func want(t *testing.T, m map[string]metric.Sample, key string, v float64) {
	t.Helper()
	got, ok := m[key]
	if !ok {
		t.Errorf("%s yo'q; bor: %v", key, keys(m))
		return
	}
	if got.V != v {
		t.Errorf("%s = %v, kutilgan %v", key, got.V, v)
	}
}

func absent(t *testing.T, m map[string]metric.Sample, key string) {
	t.Helper()
	if _, ok := m[key]; ok {
		t.Errorf("%s bo'lmasligi kerak", key)
	}
}

func TestBackupOKProject(t *testing.T) {
	b := newBK(t)
	old := backupNow.Add(-48 * time.Hour)
	fresh := backupNow.Add(-9 * time.Hour)
	b.write("Biz/state.json", okState, fresh)
	b.write("Biz/daily/Biz-0.sql.gz", "aa", old)
	b.write("Biz/daily/Biz-1.sql.gz", "bbbb", fresh)
	b.write("Biz/daily/Biz-2.sql.gz.tmp", "yarim", backupNow) // hisobga olinmaydi
	b.write("Biz/daily/.hidden", "x", backupNow)
	b.write("Biz/weekly/Biz-20261018-031501.sql.gz", "w", backupNow.Add(-100*time.Hour))
	b.write("Biz/weekly/Biz-files-20261018-031501.tar.gz", "f", backupNow.Add(-90*time.Hour))
	b.write("Biz/weekly/Biz-files-20261011-031501.tar.gz", "f", backupNow.Add(-250*time.Hour))
	b.write("_run.json", `{"offsite":{"configured":true}}`, time.Time{})

	m, err := b.collect("")
	if err != nil {
		t.Fatal(err)
	}
	want(t, m, "backup_last_status{project=Biz}", 1)
	want(t, m, "backup_last_success_timestamp{project=Biz}", float64(time.Date(2026, 10, 22, 3, 15, 41, 0, time.UTC).Unix()))
	want(t, m, "backup_last_size_bytes{project=Biz}", 48273114)
	want(t, m, "backup_newest_file_age_seconds{kind=daily,project=Biz}", 9*3600)
	want(t, m, "backup_files_count{kind=daily,project=Biz}", 2)
	want(t, m, "backup_newest_file_age_seconds{kind=weekly,project=Biz}", 100*3600)
	want(t, m, "backup_files_count{kind=weekly,project=Biz}", 1)
	want(t, m, "backup_newest_file_age_seconds{kind=files,project=Biz}", 90*3600)
	want(t, m, "backup_files_count{kind=files,project=Biz}", 2)
	want(t, m, "backup_offsite_configured", 1)
}

func TestBackupFailFallsBackToNewestDaily(t *testing.T) {
	b := newBK(t)
	mt := backupNow.Add(-30 * time.Hour)
	b.write("Biz/state.json", `{"status":"fail","finished_at":"2026-10-22T03:00:00Z","daily":{"status":"fail","file":null,"size_bytes":0,"error":"pg_dump: parol=sir"}}`, time.Time{})
	b.write("Biz/daily/Biz-1.sql.gz", "123456", mt)
	m, err := b.collect("")
	if err != nil {
		t.Fatal(err)
	}
	want(t, m, "backup_last_status{project=Biz}", 0)
	want(t, m, "backup_last_success_timestamp{project=Biz}", float64(mt.Unix()))
	want(t, m, "backup_last_size_bytes{project=Biz}", 6) // state.json emas, fayl hajmi
	for _, s := range m {
		for _, v := range s.L {
			if strings.Contains(v, "pg_dump") || strings.Contains(v, "parol") {
				t.Fatalf("error matni belgiga tushdi: %v", s)
			}
		}
	}
}

func TestBackupFailWithoutDailyFiles(t *testing.T) {
	b := newBK(t)
	b.write("Biz/state.json", `{"status":"fail","daily":null}`, time.Time{})
	if err := os.MkdirAll(filepath.Join(b.root, "Biz", "daily"), 0o750); err != nil {
		t.Fatal(err)
	}
	m, err := b.collect("")
	if err != nil {
		t.Fatal(err)
	}
	want(t, m, "backup_last_status{project=Biz}", 0)
	absent(t, m, "backup_last_success_timestamp{project=Biz}")
	absent(t, m, "backup_last_size_bytes{project=Biz}")
	want(t, m, "backup_files_count{kind=daily,project=Biz}", 0) // papka bor, fayl yo'q
	absent(t, m, "backup_newest_file_age_seconds{kind=daily,project=Biz}")
	absent(t, m, "backup_files_count{kind=weekly,project=Biz}")
}

func TestBackupOKWithNullDailyUsesNewestFile(t *testing.T) {
	b := newBK(t)
	b.write("Biz/state.json", `{"status":"ok","finished_at":"2026-10-22T03:15:41Z","daily":null}`, time.Time{})
	b.write("Biz/daily/x.sql.gz", "abc", backupNow.Add(-time.Hour))
	m, _ := b.collect("")
	want(t, m, "backup_last_size_bytes{project=Biz}", 3)
	want(t, m, "backup_last_status{project=Biz}", 1)
}

func TestBackupBrokenStateIsErrorButRestContinues(t *testing.T) {
	b := newBK(t)
	b.write("NoState/daily/a.sql.gz", "aaa", backupNow.Add(-2*time.Hour))
	b.write("Broken/state.json", "{bu json emas", time.Time{})
	b.write("BadStatus/state.json", `{"status":"maybe"}`, time.Time{})
	b.write("Good/state.json", okState, time.Time{})
	m, err := b.collect("")
	if err == nil {
		t.Fatal("xato kutilgan")
	}
	for _, p := range []string{"Broken", "BadStatus"} {
		absent(t, m, "backup_last_status{project="+p+"}")
		if !strings.Contains(err.Error(), p) {
			t.Errorf("xatoda %s yo'q: %v", p, err)
		}
	}
	absent(t, m, "backup_last_status{project=NoState}")
	if strings.Contains(err.Error(), "NoState") {
		t.Error("state.json yo'qligi xato emas (appctl hali yozmagan)")
	}
	if strings.Contains(err.Error(), "bu json") {
		t.Error("xatoda fayl mazmuni bo'lmasligi kerak")
	}
	// state yo'q bo'lsa ham skaner natijalari va eng yangi kunlik fayl vaqti chiqadi
	want(t, m, "backup_last_success_timestamp{project=NoState}", float64(backupNow.Add(-2*time.Hour).Unix()))
	want(t, m, "backup_files_count{kind=daily,project=NoState}", 1)
	want(t, m, "backup_last_status{project=Good}", 1)
}

func TestBackupEmptyStateFile(t *testing.T) {
	b := newBK(t)
	b.write("Biz/state.json", "", time.Time{})
	m, err := b.collect("")
	if err == nil {
		t.Fatal("bo'sh state.json xato berishi kerak")
	}
	absent(t, m, "backup_last_status{project=Biz}")
}

func TestBackupOversizedStateRejected(t *testing.T) {
	b := newBK(t)
	b.write("Biz/state.json", `{"status":"ok","pad":"`+strings.Repeat("a", 1<<20)+`"}`, time.Time{})
	m, err := b.collect("")
	if err == nil || !strings.Contains(err.Error(), "1 MB") {
		t.Fatalf("katta fayl rad etilishi kerak: %v", err)
	}
	absent(t, m, "backup_last_status{project=Biz}")
}

func TestBackupProjectNamesAndNonProjects(t *testing.T) {
	b := newBK(t)
	b.write("_run.json", `{}`, time.Time{})
	b.write("_hidden/state.json", okState, time.Time{})
	b.write("bad name/state.json", okState, time.Time{})
	b.write("a.b/state.json", okState, time.Time{})
	b.write("file.txt", "x", time.Time{})
	b.write(strings.Repeat("a", 61)+"/state.json", okState, time.Time{})
	b.write("ok_1-A/state.json", okState, time.Time{})
	m, _ := b.collect("")
	var projects []string
	for _, s := range m {
		if p := s.L["project"]; p != "" && s.N == "backup_last_status" {
			projects = append(projects, p)
		}
	}
	if len(projects) != 1 || projects[0] != "ok_1-A" {
		t.Fatalf("faqat ok_1-A kutilgan: %v", projects)
	}
}

func TestBackupSymlinksNotFollowed(t *testing.T) {
	b := newBK(t)
	outside := t.TempDir()
	if err := os.WriteFile(filepath.Join(outside, "state.json"), []byte(okState), 0o600); err != nil {
		t.Fatal(err)
	}
	if err := os.Symlink(outside, filepath.Join(b.root, "Linked")); err != nil {
		t.Skip("simvolik havola yaratib bo'lmadi:", err)
	}
	// loyiha ichida: state.json, daily va fayllar havola
	b.write("Biz/real.gz", "r", backupNow)
	_ = os.Symlink(filepath.Join(outside, "state.json"), filepath.Join(b.root, "Biz", "state.json"))
	_ = os.Symlink(outside, filepath.Join(b.root, "Biz", "daily"))
	_ = os.MkdirAll(filepath.Join(b.root, "Biz", "weekly"), 0o750)
	_ = os.Symlink(filepath.Join(b.root, "Biz", "real.gz"), filepath.Join(b.root, "Biz", "weekly", "link.sql.gz"))

	m, err := b.collect("")
	if err == nil { // Biz/state.json havola -> xato
		t.Fatal("havola bo'lgan state.json rad etilishi kerak")
	}
	for k := range m {
		if strings.Contains(k, "Linked") {
			t.Errorf("havola bo'yicha loyiha kuzatilmasligi kerak: %s", k)
		}
	}
	absent(t, m, "backup_last_status{project=Biz}")
	absent(t, m, "backup_files_count{kind=daily,project=Biz}")
	absent(t, m, "backup_files_count{kind=weekly,project=Biz}")
}

func TestBackupRootMissingIsQuiet(t *testing.T) {
	s, err := NewBackup(filepath.Join(t.TempDir(), "yoq"), filepath.Join(t.TempDir(), "yoq.conf")).Collect(context.Background(), backupNow)
	if err != nil || len(s) != 0 {
		t.Fatalf("namuna ham xato ham bo'lmasligi kerak: %v %v", s, err)
	}
}

func TestBackupUnreadableDirIsErrorButRestContinues(t *testing.T) {
	if os.Geteuid() == 0 {
		t.Skip("root ruxsat tekshiruvini aylanib o'tadi")
	}
	b := newBK(t)
	b.write("Good/state.json", okState, time.Time{})
	b.write("Locked/daily/a.gz", "a", time.Time{})
	b.write("Locked/state.json", okState, time.Time{})
	locked := filepath.Join(b.root, "Locked", "daily")
	if err := os.Chmod(locked, 0o000); err != nil {
		t.Fatal(err)
	}
	defer os.Chmod(locked, 0o700)
	m, err := b.collect("")
	if err == nil || !strings.Contains(err.Error(), "Locked") {
		t.Fatalf("xato kutilgan: %v", err)
	}
	want(t, m, "backup_last_status{project=Good}", 1)
	want(t, m, "backup_last_status{project=Locked}", 1) // state.json baribir o'qildi
	absent(t, m, "backup_files_count{kind=daily,project=Locked}")
}

func TestBackupProjectLimit(t *testing.T) {
	b := newBK(t)
	for i := 0; i < maxBackupProjects+5; i++ {
		b.write("p"+strings.Repeat("0", 3-len(itoa(i)))+itoa(i)+"/state.json", okState, time.Time{})
	}
	m, err := b.collect("")
	if err == nil {
		t.Fatal("limitdan oshganda xato kutilgan")
	}
	n := 0
	for _, s := range m {
		if s.N == "backup_last_status" {
			n++
		}
	}
	if n != maxBackupProjects {
		t.Fatalf("%d loyiha kutilgan, %d", maxBackupProjects, n)
	}
}

func itoa(i int) string {
	if i == 0 {
		return "0"
	}
	s := ""
	for ; i > 0; i /= 10 {
		s = string(rune('0'+i%10)) + s
	}
	return s
}

func TestBackupOffsiteSources(t *testing.T) {
	conf := func(body string) string {
		p := filepath.Join(t.TempDir(), "appctl.conf")
		if err := os.WriteFile(p, []byte(body), 0o600); err != nil {
			t.Fatal(err)
		}
		return p
	}
	t.Run("_run.json false conf'dan ustun", func(t *testing.T) {
		b := newBK(t)
		b.write("_run.json", `{"offsite":{"configured":false}}`, time.Time{})
		m, _ := b.collect(conf(`OFFSITE="user@host:/x"`))
		want(t, m, "backup_offsite_configured", 0)
	})
	t.Run("_run.json buzuq -> conf", func(t *testing.T) {
		b := newBK(t)
		b.write("_run.json", `{buzuq`, time.Time{})
		m, _ := b.collect(conf("OFFSITE=host:/x\n"))
		want(t, m, "backup_offsite_configured", 1)
	})
	t.Run("_run.json offsite yo'q -> conf", func(t *testing.T) {
		b := newBK(t)
		b.write("_run.json", `{"schema":1}`, time.Time{})
		m, _ := b.collect(conf(`OFFSITE=""`))
		want(t, m, "backup_offsite_configured", 0)
	})
	t.Run("ikkalasi ham yo'q -> metrika yo'q", func(t *testing.T) {
		b := newBK(t)
		m, _ := b.collect(filepath.Join(t.TempDir(), "yoq.conf"))
		absent(t, m, "backup_offsite_configured")
	})
}

func TestParseOffsite(t *testing.T) {
	cases := map[string]string{
		"OFFSITE=\"a@b:/x\"":               "a@b:/x",
		"OFFSITE='a@b:/x'":                 "a@b:/x",
		"OFFSITE=a@b:/x":                   "a@b:/x",
		"export OFFSITE=a@b":               "a@b",
		"OFFSITE=a@b # izoh":               "a@b",
		"# OFFSITE=a@b":                    "",
		"OFFSITE=":                         "",
		"OFFSITE=\"\"":                     "",
		"OFFSITE=''  # bo'sh":              "",
		"OFFSITE=#izoh":                    "",
		"  OFFSITE=\"  \"":                 "",
		"OFFSITE_X=1":                      "",
		"X=1\r\nOFFSITE=\"h:/p\"\r\nY=2\r": "h:/p",
		"OFFSITE=old\nOFFSITE=":            "", // oxirgisi ustun
		"OFFSITE=\"unterminated":           "unterminated",
		"":                                 "",
	}
	for in, want := range cases {
		if got := parseOffsite(in); got != want {
			t.Errorf("%q -> %q, kutilgan %q", in, got, want)
		}
	}
}

func TestBackupOffsiteConfNotSourced(t *testing.T) {
	// `$(...)` va boshqa shell konstruksiyalari bajarilmaydi, faqat matn sifatida o'qiladi
	marker := filepath.Join(t.TempDir(), "bajarildi")
	p := filepath.Join(t.TempDir(), "appctl.conf")
	if err := os.WriteFile(p, []byte("touch "+marker+"\nOFFSITE=\"$(touch "+marker+")\"\n"), 0o600); err != nil {
		t.Fatal(err)
	}
	b := newBK(t)
	m, _ := b.collect(p)
	want(t, m, "backup_offsite_configured", 1)
	if _, err := os.Stat(marker); err == nil {
		t.Fatal("conf bajarilgan!")
	}
}

func TestBackupMissingStateJSONIsNotAnError(t *testing.T) {
	b := newBK(t)
	b.write("Biz/daily/Biz-1.sql.gz", "123456", time.Now().Add(-time.Hour))
	m, err := b.collect("")
	if err != nil {
		t.Fatalf("state.json yo'q: xato bo'lmasligi kerak: %v", err)
	}
	absent(t, m, "backup_last_status{project=Biz}") // state.json yo'q: holat metrikasi chiqmaydi
	want(t, m, "backup_files_count{kind=daily,project=Biz}", 1)
}
