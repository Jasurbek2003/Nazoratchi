// Package queue — yuborilmagan paketlar uchun diskdagi navbat (TZ 7.2): har paket alohida fayl
// (`<seq>.json.gz`), maksimum hajm va yosh; to'lsa eng eskilari o'chadi.
package queue

import (
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"sort"
	"strings"
	"sync"
	"time"
)

const suffix = ".json.gz"

type Queue struct {
	dir      string
	maxBytes int64
	maxAge   time.Duration
	now      func() time.Time
	mu       sync.Mutex
}

// Open papkani yaratadi (0750) va oldingi ishdan qolgan yarim yozilgan `.tmp` fayllarni o'chiradi.
func Open(dir string, maxBytes int64, maxAge time.Duration) (*Queue, error) {
	if err := os.MkdirAll(dir, 0o750); err != nil {
		return nil, fmt.Errorf("navbat papkasi: %w", err)
	}
	q := &Queue{dir: dir, maxBytes: maxBytes, maxAge: maxAge, now: time.Now}
	entries, err := os.ReadDir(dir)
	if err != nil {
		return nil, err
	}
	for _, e := range entries {
		if strings.HasSuffix(e.Name(), ".tmp") {
			_ = os.Remove(filepath.Join(dir, e.Name()))
		}
	}
	return q, nil
}

// Push paketni atomik yozadi (tmp -> rename), keyin chegaralarni qo'llaydi.
// Qaytadi: chegara sababli o'chirilgan eski fayllar soni.
func (q *Queue) Push(seq uint64, data []byte) (dropped int, err error) {
	q.mu.Lock()
	defer q.mu.Unlock()
	final := filepath.Join(q.dir, fmt.Sprintf("%020d%s", seq, suffix))
	tmp := final + ".tmp"
	if err := os.WriteFile(tmp, data, 0o640); err != nil {
		_ = os.Remove(tmp)
		return 0, fmt.Errorf("navbatga yozilmadi: %w", err)
	}
	if err := os.Rename(tmp, final); err != nil {
		_ = os.Remove(tmp)
		return 0, fmt.Errorf("navbatga yozilmadi: %w", err)
	}
	return q.trim(), nil
}

type entry struct {
	name string
	size int64
	mod  time.Time
}

// list nomi bo'yicha (ya'ni seq bo'yicha, vaqt tartibida) saralangan fayllar.
func (q *Queue) list() ([]entry, error) {
	dirEntries, err := os.ReadDir(q.dir)
	if err != nil {
		return nil, err
	}
	var out []entry
	for _, e := range dirEntries {
		if e.IsDir() || !strings.HasSuffix(e.Name(), suffix) {
			continue
		}
		info, err := e.Info()
		if err != nil {
			continue
		}
		out = append(out, entry{e.Name(), info.Size(), info.ModTime()})
	}
	sort.Slice(out, func(i, j int) bool { return out[i].name < out[j].name })
	return out, nil
}

// trim: avval yoshi oshganlarni, keyin hajm oshsa eng eskilarini o'chiradi. Oxirgi (eng yangi) fayl
// hajm sababli hech qachon o'chirilmaydi.
func (q *Queue) trim() int {
	files, err := q.list()
	if err != nil {
		return 0
	}
	dropped := 0
	cutoff := q.now().Add(-q.maxAge)
	var keep []entry
	for _, f := range files {
		if f.mod.Before(cutoff) {
			_ = os.Remove(filepath.Join(q.dir, f.name))
			dropped++
			continue
		}
		keep = append(keep, f)
	}
	var total int64
	for _, f := range keep {
		total += f.size
	}
	for len(keep) > 1 && total > q.maxBytes {
		_ = os.Remove(filepath.Join(q.dir, keep[0].name))
		total -= keep[0].size
		keep = keep[1:]
		dropped++
	}
	return dropped
}

// Oldest eng eski faylni qaytaradi; navbat bo'sh bo'lsa ok=false. Yoshi oshgan fayllar avval tozalanadi.
func (q *Queue) Oldest() (name string, data []byte, ok bool, err error) {
	q.mu.Lock()
	defer q.mu.Unlock()
	q.trim()
	files, err := q.list()
	if err != nil || len(files) == 0 {
		return "", nil, false, err
	}
	data, err = os.ReadFile(filepath.Join(q.dir, files[0].name))
	if err != nil {
		return "", nil, false, err
	}
	return files[0].name, data, true, nil
}

func (q *Queue) Remove(name string) error {
	q.mu.Lock()
	defer q.mu.Unlock()
	err := os.Remove(filepath.Join(q.dir, filepath.Base(name)))
	if errors.Is(err, os.ErrNotExist) {
		return nil
	}
	return err
}

// Stats navbatdagi fayllar soni va umumiy hajmi (`agent_queue_files`, `agent_queue_bytes`).
func (q *Queue) Stats() (files int, bytes int64) {
	q.mu.Lock()
	defer q.mu.Unlock()
	list, _ := q.list()
	for _, f := range list {
		bytes += f.size
	}
	return len(list), bytes
}
