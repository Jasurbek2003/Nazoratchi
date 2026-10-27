package main

import (
	"bytes"
	"context"
	"errors"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"testing"

	"nazoratchi/agent/internal/sender"
)

type fakeRunner struct {
	calls []string
	fail  map[string]bool // "systemctl disable" kabi prefiks bo'yicha xato
}

func (f *fakeRunner) Run(_ context.Context, name string, args ...string) ([]byte, error) {
	line := strings.TrimSpace(name + " " + strings.Join(args, " "))
	f.calls = append(f.calls, line)
	for p := range f.fail {
		if strings.HasPrefix(line, p) {
			return []byte("xato chiqishi"), errors.New("exit 1")
		}
	}
	return nil, nil
}

type goodbyeReq struct{ auth, path string }

type fixture struct {
	root   string
	u      *uninstaller
	run    *fakeRunner
	out    *bytes.Buffer
	gotReq *goodbyeReq
}

func newFixture(t *testing.T, goodbyeStatus int) *fixture {
	t.Helper()
	root := t.TempDir()
	f := &fixture{root: root, run: &fakeRunner{fail: map[string]bool{}}, out: &bytes.Buffer{}, gotReq: &goodbyeReq{}}
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		f.gotReq.auth, f.gotReq.path = r.Header.Get("Authorization"), r.URL.Path
		w.WriteHeader(goodbyeStatus)
	}))
	t.Cleanup(srv.Close)

	write := func(p, data string) {
		full := filepath.Join(root, p)
		if err := os.MkdirAll(filepath.Dir(full), 0o755); err != nil {
			t.Fatal(err)
		}
		if err := os.WriteFile(full, []byte(data), 0o600); err != nil {
			t.Fatal(err)
		}
	}
	write("etc/nazoratchi/agent.yaml", "core:\n  url: "+srv.URL+"\n")
	write("etc/nazoratchi/token", "agt_sirli_token\n")
	write("var/lib/nazoratchi/queue/x", "q")
	write("etc/systemd/system/nazoratchi-agent.service", "[Unit]")
	write("usr/local/bin/nazoratchi-agent", "bin")

	f.u = &uninstaller{
		Root: root, Run: f.run, Out: f.out, Geteuid: func() int { return 0 },
		Exe: "/usr/local/bin/nazoratchi-agent", Version: "t", Goodbye: sender.Goodbye,
		ConfPath: "/etc/nazoratchi/agent.yaml",
	}
	return f
}

func (f *fixture) exists(p string) bool {
	_, err := os.Lstat(filepath.Join(f.root, p))
	return err == nil
}

func TestUninstallFullFlow(t *testing.T) {
	f := newFixture(t, 200)
	f.u.Purge = true
	if err := f.u.Do(context.Background(), true); err != nil {
		t.Fatal(err)
	}
	if f.gotReq.path != "/ingest/v1/goodbye" || f.gotReq.auth != "Bearer agt_sirli_token" {
		t.Fatalf("goodbye so'rovi noto'g'ri: %+v", f.gotReq)
	}
	for _, p := range []string{"etc/nazoratchi", "var/lib/nazoratchi", "etc/systemd/system/nazoratchi-agent.service", "usr/local/bin/nazoratchi-agent"} {
		if f.exists(p) {
			t.Errorf("%s o'chirilmagan", p)
		}
	}
	want := []string{"systemctl disable --now nazoratchi-agent", "systemctl daemon-reload", "userdel nazoratchi", "docker rm -f nazoratchi-docker-proxy"}
	if strings.Join(f.run.calls, "|") != strings.Join(want, "|") {
		t.Fatalf("buyruqlar tartibi: %v", f.run.calls)
	}
	if strings.Contains(f.out.String(), "agt_sirli_token") {
		t.Fatal("token chiqishda ko'rinib qoldi")
	}
}

func TestUninstallWithoutPurgeKeepsDockerProxy(t *testing.T) {
	f := newFixture(t, 200)
	if err := f.u.Do(context.Background(), true); err != nil {
		t.Fatal(err)
	}
	for _, c := range f.run.calls {
		if strings.HasPrefix(c, "docker") {
			t.Fatalf("--purge siz docker chaqirilmasligi kerak: %v", f.run.calls)
		}
	}
}

func TestUninstallNeedsYes(t *testing.T) {
	f := newFixture(t, 200)
	err := f.u.Do(context.Background(), false)
	var ee *exitError
	if !errors.As(err, &ee) || ee.Code != 2 {
		t.Fatalf("exit 2 kutilgan: %v", err)
	}
	if !strings.Contains(f.out.String(), "--yes") || !strings.Contains(f.out.String(), "/etc/nazoratchi") {
		t.Fatalf("ro'yxat va --yes eslatmasi yo'q: %s", f.out)
	}
	if len(f.run.calls) != 0 || f.gotReq.path != "" || !f.exists("etc/nazoratchi/token") || !f.exists("usr/local/bin/nazoratchi-agent") {
		t.Fatal("tasdiqsiz hech narsa o'zgarmasligi kerak")
	}
}

func TestUninstallRequiresRoot(t *testing.T) {
	f := newFixture(t, 200)
	f.u.Geteuid = func() int { return 1000 }
	if err := f.u.Do(context.Background(), true); err == nil || !strings.Contains(err.Error(), "root") {
		t.Fatalf("root xatosi kutilgan: %v", err)
	}
	if !f.exists("etc/nazoratchi/token") {
		t.Fatal("root bo'lmasa hech narsa o'chirilmasligi kerak")
	}
}

func TestUninstallContinuesAfterFailures(t *testing.T) {
	f := newFixture(t, 500) // goodbye 500 qaytaradi
	f.run.fail["systemctl disable"] = true
	f.run.fail["userdel"] = true
	if err := f.u.Do(context.Background(), true); err != nil {
		t.Fatal(err)
	}
	out := f.out.String()
	for _, w := range []string{"core'ga xabar berib bo'lmadi", "servisni to'xtatib bo'lmadi", "foydalanuvchisini o'chirib bo'lmadi"} {
		if !strings.Contains(out, w) {
			t.Errorf("ogohlantirish yo'q %q:\n%s", w, out)
		}
	}
	if f.exists("etc/nazoratchi") || f.exists("var/lib/nazoratchi") || f.exists("usr/local/bin/nazoratchi-agent") {
		t.Fatal("xatolardan keyin ham o'chirish davom etishi kerak")
	}
}

func TestUninstallMissingConfigSkipsGoodbye(t *testing.T) {
	f := newFixture(t, 200)
	_ = os.Remove(filepath.Join(f.root, "etc/nazoratchi/agent.yaml"))
	if err := f.u.Do(context.Background(), true); err != nil {
		t.Fatal(err)
	}
	if f.gotReq.path != "" || !strings.Contains(f.out.String(), "goodbye o'tkazib yuborildi") {
		t.Fatalf("goodbye o'tkazilishi kerak edi: %s", f.out)
	}
	if f.exists("etc/nazoratchi") {
		t.Fatal("katalog baribir o'chirilishi kerak")
	}
}

func TestUninstallBinaryOutsideBinDirKept(t *testing.T) {
	f := newFixture(t, 200)
	other := filepath.Join(f.root, "tmp", "nazoratchi-agent")
	if err := os.MkdirAll(filepath.Dir(other), 0o755); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(other, []byte("x"), 0o755); err != nil {
		t.Fatal(err)
	}
	f.u.Exe = "/tmp/nazoratchi-agent"
	if err := f.u.Do(context.Background(), true); err != nil {
		t.Fatal(err)
	}
	if !f.exists("tmp/nazoratchi-agent") || !f.exists("usr/local/bin/nazoratchi-agent") {
		t.Fatal("/usr/local/bin/ dan tashqaridagi binar o'chirilmasligi kerak")
	}
	if !strings.Contains(f.out.String(), "qo'lda o'chiring") {
		t.Fatalf("qo'lda o'chirish xabari yo'q: %s", f.out)
	}
}

func TestBinaryRemovable(t *testing.T) {
	cases := map[string]bool{
		"/usr/local/bin/nazoratchi-agent":        true,
		"/usr/local/bin/../../../etc/passwd":     false,
		"/usr/local/bin":                         false,
		"/usr/local/bin/":                        false,
		"/usr/bin/nazoratchi-agent":              false,
		"/usr/local/binx/nazoratchi-agent":       false,
		"/home/u/usr/local/bin/nazoratchi-agent": false,
		"":                                       false,
	}
	for in, want := range cases {
		if got := binaryRemovable(in); got != want {
			t.Errorf("binaryRemovable(%q)=%v, kutilgan %v", in, got, want)
		}
	}
}

func TestResolveStaysInsideRoot(t *testing.T) {
	root := t.TempDir()
	u := &uninstaller{Root: root}
	got, err := u.resolve("/etc/nazoratchi")
	if err != nil || got != filepath.Join(root, "etc", "nazoratchi") {
		t.Fatalf("%q %v", got, err)
	}
	for _, in := range []string{"/../../outside", "../../outside", "/etc/../../outside"} {
		got, err := u.resolve(in)
		if err == nil && !strings.HasPrefix(got, root) {
			t.Fatalf("%q ildizdan chiqib ketdi: %q", in, got)
		}
	}
}

func TestRemovePathRefusesRoot(t *testing.T) {
	f := newFixture(t, 200)
	f.u.removePath("/", true)
	if !f.exists("etc/nazoratchi") {
		t.Fatal("ildiz o'chirilmasligi kerak")
	}
	if !strings.Contains(f.out.String(), "xavfli yo'l") {
		t.Fatalf("ogohlantirish yo'q: %s", f.out)
	}
}
