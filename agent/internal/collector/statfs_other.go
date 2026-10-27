//go:build !linux

package collector

import "errors"

func statfs(string) (FsStat, error) { return FsStat{}, errors.New("statfs faqat Linux da") }
