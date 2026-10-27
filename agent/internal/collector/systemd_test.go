package collector

import (
	"context"
	"errors"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"
)

type call struct {
	name string
	args []string
}

// fakeSystemctl: unit -> `systemctl show` chiqishi; yo'q unit uchun xato.
func fakeSystemctl(units map[string]string, calls *[]call) Runner {
	return func(_ context.Context, name string, args ...string) ([]byte, error) {
		*calls = append(*calls, call{name, args})
		if name != "systemctl" || len(args) != 3 || args[0] != "show" {
			return nil, errors.New("kutilmagan chaqiruv")
		}
		out, ok := units[args[1]]
		if !ok {
			return nil, errors.New("exit status 1")
		}
		return []byte(out), nil
	}
}

func keys[V any](m map[string]V) []string {
	var k []string
	for n := range m {
		k = append(k, n)
	}
	return k
}

func TestSystemdUnitStates(t *testing.T) {
	var calls []call
	run := fakeSystemctl(map[string]string{
		"nginx":       "ActiveState=active\nLoadState=loaded\nSubState=running\n",
		"cron":        "LoadState=loaded\nActiveState=failed\nSubState=failed\n",
		"ssh":         "ActiveState=inactive\nLoadState=loaded\nSubState=dead\n",
		"missing":     "ActiveState=inactive\nLoadState=not-found\nSubState=dead\n",
		"a@b.service": "ActiveState=active\nLoadState=loaded\nSubState=running\n",
	}, &calls)
	c, err := NewSystemd([]string{"nginx", "cron", "ssh", "missing", "a@b.service"}, "", run)
	if err != nil {
		t.Fatal(err)
	}
	s, err := c.Collect(context.Background(), time.Unix(1000, 0))
	if err != nil {
		t.Fatal(err)
	}
	m := byName(s)
	want := map[string]float64{
		"systemd_unit_active{unit=nginx}": 1, "systemd_unit_failed{unit=nginx}": 0,
		"systemd_unit_active{unit=cron}": 0, "systemd_unit_failed{unit=cron}": 1,
		"systemd_unit_active{unit=ssh}": 0, "systemd_unit_failed{unit=ssh}": 0,
		"systemd_unit_active{unit=missing}": 0, "systemd_unit_failed{unit=missing}": 0,
		"systemd_unit_active{unit=a@b.service}": 1,
	}
	for k, v := range want {
		got, ok := m[k]
		if !ok || got.V != v {
			t.Errorf("%s = %v (bor=%v), kutilgan %v; barcha: %v", k, got.V, ok, v, keys(m))
		}
	}
	for _, cl := range calls { // shell yo'q, argumentlar alohida
		if cl.name != "systemctl" || cl.args[0] != "show" || cl.args[2] != "--property=ActiveState,LoadState,SubState" {
			t.Errorf("noto'g'ri chaqiruv: %+v", cl)
		}
	}
}

func TestSystemdPartialErrorContinues(t *testing.T) {
	var calls []call
	run := fakeSystemctl(map[string]string{"nginx": "ActiveState=active\nLoadState=loaded\n"}, &calls)
	c, _ := NewSystemd([]string{"broken", "nginx"}, "", run)
	s, err := c.Collect(context.Background(), time.Now())
	if err == nil || !strings.Contains(err.Error(), "broken") {
		t.Fatalf("xato kutilgan: %v", err)
	}
	if byName(s)["systemd_unit_active{unit=nginx}"].V != 1 {
		t.Fatalf("qolgan unit davom etishi kerak: %v", s)
	}
	if _, ok := byName(s)["systemd_unit_active{unit=broken}"]; ok {
		t.Fatal("xatoli unit uchun namuna bo'lmasligi kerak")
	}
}

func TestSystemctlMissingIsError(t *testing.T) {
	c, _ := NewSystemd([]string{"nginx"}, "", func(context.Context, string, ...string) ([]byte, error) {
		return nil, errors.New(`exec: "systemctl": executable file not found in $PATH`)
	})
	if _, err := c.Collect(context.Background(), time.Now()); err == nil {
		t.Fatal("systemctl yo'q bo'lsa xato kutilgan")
	}
}

func TestUnitNameValidation(t *testing.T) {
	good := []string{"nginx", "nginx.service", "getty@tty1.service", "dev-sda1.device", "a:b_c", strings.Repeat("a", 100)}
	bad := []string{"", "-x", "--property=Id", "a b", "a;b", "a/b", "a$b", "a\nb", strings.Repeat("a", 101), "näm"}
	for _, n := range good {
		if !ValidUnitName(n) {
			t.Errorf("%q yaroqli bo'lishi kerak", n)
		}
	}
	for _, n := range bad {
		if ValidUnitName(n) {
			t.Errorf("%q rad etilishi kerak", n)
		}
	}
	if _, err := NewSystemd([]string{"nginx", "--all"}, "", nil); err == nil {
		t.Fatal("yaroqsiz unit konstruktorda rad etilishi kerak")
	}
	// konstruktorsiz yaratilgan bo'lsa ham Collect rad etadi va runner chaqirilmaydi
	var calls []call
	c := &Systemd{units: []string{"-x"}, run: fakeSystemctl(nil, &calls)}
	if _, err := c.Collect(context.Background(), time.Now()); err == nil || len(calls) != 0 {
		t.Fatalf("rad etilishi kerak: %v, chaqiruvlar %v", err, calls)
	}
}

func TestHeartbeats(t *testing.T) {
	dir := t.TempDir()
	mt := time.Unix(1_700_000_000, 500_000_000)
	mk := func(name string) {
		p := filepath.Join(dir, name)
		if err := os.WriteFile(p, []byte("x"), 0o600); err != nil {
			t.Fatal(err)
		}
		if err := os.Chtimes(p, mt, mt); err != nil {
			t.Fatal(err)
		}
	}
	mk("backup-all")
	mk("job.v2@x")
	mk(".hidden")
	mk("half.tmp")
	mk("bad name")
	mk(strings.Repeat("a", 81))
	if err := os.Mkdir(filepath.Join(dir, "subdir"), 0o750); err != nil {
		t.Fatal(err)
	}
	if err := os.Symlink(filepath.Join(dir, "backup-all"), filepath.Join(dir, "link")); err != nil {
		t.Skip("simvolik havola yaratib bo'lmadi:", err)
	}
	c, _ := NewSystemd(nil, dir, nil)
	s, err := c.Collect(context.Background(), time.Now())
	if err != nil {
		t.Fatal(err)
	}
	m := byName(s)
	if len(m) != 2 {
		t.Fatalf("faqat 2 ta heartbeat kutilgan: %v", keys(m))
	}
	if v := m["cron_job_last_success_timestamp{job=backup-all}"].V; v != 1_700_000_000.5 {
		t.Fatalf("mtime noto'g'ri: %v", v)
	}
}

func TestHeartbeatsDirMissingIsNotError(t *testing.T) {
	c, _ := NewSystemd(nil, filepath.Join(t.TempDir(), "yoq"), nil)
	s, err := c.Collect(context.Background(), time.Now())
	if err != nil || len(s) != 0 {
		t.Fatalf("namuna ham, xato ham bo'lmasligi kerak: %v %v", s, err)
	}
}

func TestHeartbeatsDirUnreadableIsError(t *testing.T) {
	if os.Geteuid() == 0 {
		t.Skip("root ruxsat tekshiruvini aylanib o'tadi")
	}
	dir := filepath.Join(t.TempDir(), "hb")
	if err := os.Mkdir(dir, 0o000); err != nil {
		t.Fatal(err)
	}
	defer os.Chmod(dir, 0o700)
	c, _ := NewSystemd(nil, dir, nil)
	if _, err := c.Collect(context.Background(), time.Now()); err == nil {
		t.Fatal("ruxsat yo'q papka xato berishi kerak")
	}
}

func TestJobNameValidation(t *testing.T) {
	for _, n := range []string{"backup", "a.b", "x@y-z_1", strings.Repeat("a", 80)} {
		if !ValidJobName(n) {
			t.Errorf("%q yaroqli", n)
		}
	}
	for _, n := range []string{"", ".", "..", ".x", "a.tmp", "a/b", "../x", "a b", strings.Repeat("a", 81)} {
		if ValidJobName(n) {
			t.Errorf("%q rad etilishi kerak", n)
		}
	}
}
