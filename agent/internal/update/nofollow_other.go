//go:build !linux

package update

import (
	"errors"
	"os"
)

func openNoFollow(path string) (*os.File, error) {
	fi, err := os.Lstat(path)
	if err != nil {
		return nil, err
	}
	if fi.Mode()&os.ModeSymlink != 0 {
		return nil, errors.New("symlink rad etildi")
	}
	return os.Open(path)
}
