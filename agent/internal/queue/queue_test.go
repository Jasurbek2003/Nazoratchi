package queue

import (
	"bytes"
	"os"
	"path/filepath"
	"testing"
	"time"
)

func open(t *testing.T, maxBytes int64, maxAge time.Duration) *Queue {
	t.Helper()
	q, err := Open(filepath.Join(t.TempDir(), "q"), maxBytes, maxAge)
	if err != nil {
		t.Fatal(err)
	}
	return q
}

func TestFIFOOrderBySeq(t *testing.T) {
	q := open(t, 1<<20, time.Hour)
	for _, seq := range []uint64{30, 5, 100} { // 5 < 30 < 100: son bo'yicha, matn bo'yicha emas
		if _, err := q.Push(seq, []byte{byte(seq)}); err != nil {
			t.Fatal(err)
		}
	}
	var order []byte
	for {
		name, data, ok, err := q.Oldest()
		if err != nil {
			t.Fatal(err)
		}
		if !ok {
			break
		}
		order = append(order, data...)
		if err := q.Remove(name); err != nil {
			t.Fatal(err)
		}
	}
	if !bytes.Equal(order, []byte{5, 30, 100}) {
		t.Fatalf("tartib noto'g'ri: %v", order)
	}
}

func TestSizeLimitDropsOldestButKeepsNewest(t *testing.T) {
	q := open(t, 250, time.Hour)
	var dropped int
	for seq := uint64(1); seq <= 5; seq++ {
		d, err := q.Push(seq, bytes.Repeat([]byte{'x'}, 100))
		if err != nil {
			t.Fatal(err)
		}
		dropped += d
	}
	files, size := q.Stats()
	if files != 2 || size != 200 || dropped != 3 {
		t.Fatalf("files=%d size=%d dropped=%d", files, size, dropped)
	}
	name, _, _, _ := q.Oldest()
	if name != "00000000000000000004.json.gz" {
		t.Fatalf("eng eski 4-paket bo'lishi kerak: %s", name)
	}
}

func TestSingleOversizedBatchIsKept(t *testing.T) {
	q := open(t, 10, time.Hour)
	if _, err := q.Push(1, bytes.Repeat([]byte{'x'}, 100)); err != nil {
		t.Fatal(err)
	}
	if files, _ := q.Stats(); files != 1 {
		t.Fatal("yagona paket hajm sababli o'chmasligi kerak")
	}
}

func TestAgeLimit(t *testing.T) {
	q := open(t, 1<<20, 15*time.Minute)
	if _, err := q.Push(1, []byte("old")); err != nil {
		t.Fatal(err)
	}
	old := time.Now().Add(-20 * time.Minute)
	if err := os.Chtimes(filepath.Join(q.dir, "00000000000000000001.json.gz"), old, old); err != nil {
		t.Fatal(err)
	}
	if _, err := q.Push(2, []byte("new")); err != nil {
		t.Fatal(err)
	}
	name, _, ok, _ := q.Oldest()
	if !ok || name != "00000000000000000002.json.gz" {
		t.Fatalf("15 daqiqadan eskisi o'chishi kerak: %s", name)
	}
}

func TestOpenCleansTmpAndSurvivesRestart(t *testing.T) {
	dir := filepath.Join(t.TempDir(), "q")
	q, _ := Open(dir, 1<<20, time.Hour)
	_, _ = q.Push(1, []byte("a"))
	if err := os.WriteFile(filepath.Join(dir, "garbage.json.gz.tmp"), []byte("half"), 0o600); err != nil {
		t.Fatal(err)
	}
	q2, err := Open(dir, 1<<20, time.Hour) // qayta ishga tushish
	if err != nil {
		t.Fatal(err)
	}
	if files, _ := q2.Stats(); files != 1 {
		t.Fatalf("paket saqlanishi kerak, %d fayl", files)
	}
	if _, err := os.Stat(filepath.Join(dir, "garbage.json.gz.tmp")); !os.IsNotExist(err) {
		t.Fatal("yarim yozilgan fayl o'chirilishi kerak")
	}
}

func TestRemoveMissingIsNotAnError(t *testing.T) {
	q := open(t, 1<<20, time.Hour)
	if err := q.Remove("yoq.json.gz"); err != nil {
		t.Fatal(err)
	}
	if err := q.Remove("../../etc/passwd"); err != nil { // yo'l faqat nom sifatida olinadi
		t.Fatal(err)
	}
}

func TestEmptyQueue(t *testing.T) {
	q := open(t, 1<<20, time.Hour)
	if _, _, ok, err := q.Oldest(); ok || err != nil {
		t.Fatal("bo'sh navbat ok=false bo'lishi kerak")
	}
}
