//go:build linux

package collector

import "syscall"

func statfs(mountpoint string) (FsStat, error) {
	var st syscall.Statfs_t
	if err := syscall.Statfs(mountpoint, &st); err != nil {
		return FsStat{}, err
	}
	return FsStat{
		BlockSize: uint64(st.Bsize), //nolint:unconvert // turi arxitekturaga qarab farq qiladi
		Blocks:    st.Blocks,
		Bfree:     st.Bfree,
		Bavail:    st.Bavail,
		Files:     st.Files,
		Ffree:     st.Ffree,
	}, nil
}
