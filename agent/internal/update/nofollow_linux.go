//go:build linux

package update

import (
	"os"
	"syscall"
)

// openNoFollow oxirgi yo'l bo'lagi symlink bo'lsa ochmaydi: agent yozadigan papkada root o'qiydigan
// faylni boshqa joyga yo'naltirib bo'lmasligi uchun.
func openNoFollow(path string) (*os.File, error) {
	return os.OpenFile(path, os.O_RDONLY|syscall.O_NOFOLLOW, 0)
}
