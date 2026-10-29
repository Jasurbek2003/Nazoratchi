package update

import (
	"crypto/ed25519"
	"crypto/rand"
	"crypto/sha256"
	"encoding/base64"
	"encoding/hex"
	"fmt"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"sync"
	"testing"
	"time"

	"golang.org/x/crypto/blake2b"
)

const arch = "amd64"

type testKey struct {
	priv ed25519.PrivateKey
	id   [8]byte
	pub  string // sozlamadagi base64 qator
}

func newKey(t *testing.T) testKey {
	t.Helper()
	pub, priv, err := ed25519.GenerateKey(rand.Reader)
	if err != nil {
		t.Fatal(err)
	}
	k := testKey{priv: priv}
	if _, err := rand.Read(k.id[:]); err != nil {
		t.Fatal(err)
	}
	raw := append(append([]byte("Ed"), k.id[:]...), pub...)
	k.pub = base64.StdEncoding.EncodeToString(raw)
	return k
}

// sign minisign formatidagi imzo yozadi ("Ed" yoki "ED" = BLAKE2b prehash).
func (k testKey) sign(alg string, msg []byte, comment string) []byte {
	data := msg
	if alg == "ED" {
		s := blake2b.Sum512(msg)
		data = s[:]
	}
	sig := ed25519.Sign(k.priv, data)
	raw := append(append([]byte(alg), k.id[:]...), sig...)
	global := ed25519.Sign(k.priv, append(append([]byte(nil), sig...), comment...))
	return []byte(fmt.Sprintf("untrusted comment: test\n%s\ntrusted comment: %s\n%s\n",
		base64.StdEncoding.EncodeToString(raw), comment, base64.StdEncoding.EncodeToString(global)))
}

func sha(b []byte) string { s := sha256.Sum256(b); return hex.EncodeToString(s[:]) }

// release — bitta reliz to'plami (core `/agent/v1/` ostida beradigan fayllar).
type release struct {
	files map[string][]byte
}

func makeRelease(k testKey, alg, version string, binary []byte) release {
	ver := []byte(version + "\n")
	sums := fmt.Sprintf("%s  %s\n%s  %s\n", sha(ver), fileVersion, sha(binary), filePrefix+arch)
	return release{files: map[string][]byte{
		fileVersion:       ver,
		filePrefix + arch: binary,
		fileSums:          []byte(sums),
		fileSig:           k.sign(alg, []byte(sums), "release "+version),
	}}
}

// serve release fayllarini beradi; hits so'ralgan yo'llarni sanaydi.
func serve(t *testing.T, r release) (*httptest.Server, *[]string) {
	t.Helper()
	var mu sync.Mutex
	var hits []string
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, req *http.Request) {
		mu.Lock()
		hits = append(hits, req.URL.Path)
		mu.Unlock()
		name := strings.TrimPrefix(req.URL.Path, "/agent/v1/")
		data, ok := r.files[name]
		if !ok {
			http.NotFound(w, req)
			return
		}
		_, _ = w.Write(data)
	}))
	t.Cleanup(srv.Close)
	return srv, &hits
}

type env struct {
	stage, state, bin string
}

func newEnv(t *testing.T, installed string) env {
	t.Helper()
	root := t.TempDir()
	e := env{stage: filepath.Join(root, "stage"), state: filepath.Join(root, "state"), bin: filepath.Join(root, "agent")}
	if err := os.WriteFile(e.bin, []byte(installed), 0o755); err != nil {
		t.Fatal(err)
	}
	if err := os.Mkdir(e.state, 0o755); err != nil {
		t.Fatal(err)
	}
	return e
}

func (e env) updater(t *testing.T, k testKey, url, current string) *Updater {
	t.Helper()
	u, err := New(Config{CoreURL: url, PubKey: k.pub, Arch: arch, Current: current, StageDir: e.stage, StateDir: e.state, HTTP: http.DefaultClient})
	if err != nil {
		t.Fatal(err)
	}
	return u
}

func (e env) apply(k testKey, current string, now time.Time) ApplyConfig {
	return ApplyConfig{
		Bin: e.bin, StageDir: e.stage, StateDir: e.state, PubKey: k.pub, Arch: arch, Current: current,
		Now: func() time.Time { return now },
	}
}

func read(t *testing.T, path string) string {
	t.Helper()
	b, err := os.ReadFile(path)
	if err != nil {
		t.Fatal(err)
	}
	return string(b)
}

func exists(path string) bool { _, err := os.Lstat(path); return err == nil }
