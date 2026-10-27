package main

import (
	"bytes"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"
)

func TestWriteBeatCreatesDirAndFile(t *testing.T) {
	dir := filepath.Join(t.TempDir(), "a", "hb")
	now := time.Date(2026, 10, 27, 3, 15, 1, 0, time.UTC)
	if err := writeBeat(dir, "backup-all", now); err != nil {
		t.Fatal(err)
	}
	data, err := os.ReadFile(filepath.Join(dir, "backup-all"))
	if err != nil || strings.TrimSpace(string(data)) != "2026-10-27T03:15:01Z" {
		t.Fatalf("%q %v", data, err)
	}
	fi, _ := os.Stat(filepath.Join(dir, "backup-all"))
	if fi.Mode().Perm() != 0o644 {
		t.Fatalf("rejim 0644 kutilgan: %v", fi.Mode().Perm())
	}
	// qayta yozish; tmp fayl qolmaydi
	if err := writeBeat(dir, "backup-all", now.Add(time.Hour)); err != nil {
		t.Fatal(err)
	}
	entries, _ := os.ReadDir(dir)
	if len(entries) != 1 {
		t.Fatalf("faqat bitta fayl kutilgan: %v", entries)
	}
}

func TestWriteBeatRejectsBadJob(t *testing.T) {
	dir := t.TempDir()
	for _, j := range []string{"", "../x", "a/b", ".hidden", "x.tmp", "a b", strings.Repeat("a", 81)} {
		if err := writeBeat(dir, j, time.Now()); err == nil {
			t.Errorf("%q rad etilishi kerak", j)
		}
	}
	if entries, _ := os.ReadDir(dir); len(entries) != 0 {
		t.Fatalf("hech narsa yozilmasligi kerak: %v", entries)
	}
}

func TestCmdBeatArgs(t *testing.T) {
	dir := t.TempDir()
	var out bytes.Buffer
	for _, args := range [][]string{{"j1", "--dir", dir}, {"--dir", dir, "j2"}} {
		if err := cmdBeat(args, &out); err != nil {
			t.Fatalf("%v: %v", args, err)
		}
	}
	for _, j := range []string{"j1", "j2"} {
		if _, err := os.Stat(filepath.Join(dir, j)); err != nil {
			t.Error(err)
		}
	}
	if err := cmdBeat([]string{"--dir", dir}, &out); err == nil {
		t.Error("job nomisiz xato kerak")
	}
	if err := cmdBeat([]string{"a", "b", "--dir", dir}, &out); err == nil {
		t.Error("ortiqcha argument xato kerak")
	}
	if err := cmdBeat([]string{"../x", "--dir", dir}, &out); err == nil {
		t.Error("yaroqsiz job xato kerak")
	}
}
