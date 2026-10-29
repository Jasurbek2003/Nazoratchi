package agent

import (
	"bytes"
	"log/slog"
	"strings"
	"testing"
	"time"
)

func skewUploader(buf *bytes.Buffer, clock *time.Time) *Uploader {
	return &Uploader{
		log: slog.New(slog.NewTextHandler(buf, &slog.HandlerOptions{Level: slog.LevelInfo})),
		now: func() time.Time { return *clock },
	}
}

func TestClockSkewWarnsOnlyAboveLimitWithoutSpam(t *testing.T) {
	var buf bytes.Buffer
	clock := time.Date(2026, 11, 1, 12, 0, 0, 0, time.UTC)
	u := skewUploader(&buf, &clock)

	u.checkSkew(300 * time.Millisecond) // oddiy tarmoq kechikishi
	u.checkSkew(-4900 * time.Millisecond)
	if buf.Len() != 0 {
		t.Fatalf("chegara ichida log bo'lmasligi kerak: %s", buf.String())
	}

	u.checkSkew(10 * time.Second) // soat 10 s ga siljigan (FR-AGT-012 qabul mezoni)
	if !strings.Contains(buf.String(), "farq qiladi") || !strings.Contains(buf.String(), "skew_seconds=10") {
		t.Fatalf("ogohlantirish kutilgan: %s", buf.String())
	}

	buf.Reset()
	for i := 0; i < 20; i++ { // har 15 s da yangi paket: spam bo'lmasin
		clock = clock.Add(15 * time.Second)
		u.checkSkew(10 * time.Second)
	}
	if strings.Count(buf.String(), "farq qiladi") != 0 {
		t.Fatalf("5 daqiqada qayta ogohlantirmasligi kerak: %s", buf.String())
	}
	clock = clock.Add(skewWarnEvery)
	u.checkSkew(-11 * time.Second) // manfiy farq ham hisoblanadi
	if strings.Count(buf.String(), "farq qiladi") != 1 {
		t.Fatalf("10 daqiqadan keyin takror ogohlantirish kerak: %s", buf.String())
	}

	buf.Reset()
	u.checkSkew(100 * time.Millisecond)
	if !strings.Contains(buf.String(), "mos keldi") {
		t.Fatalf("tuzalganda xabar kerak: %s", buf.String())
	}
	buf.Reset()
	u.checkSkew(100 * time.Millisecond)
	if buf.Len() != 0 {
		t.Fatalf("tuzalgandan keyin takror xabar bo'lmasligi kerak: %s", buf.String())
	}
}
