package update

import (
	"errors"
	"fmt"
	"strconv"
	"strings"
)

// Version — `1.2.3` ko'rinishidagi reliz versiyasi. Pre-release (`-rc1`) va `dev` qabul qilinmaydi:
// yangilanish faqat to'liq relizlar orasida bo'ladi.
type Version [3]int

func ParseVersion(s string) (Version, error) {
	s = strings.TrimPrefix(strings.TrimSpace(s), "v")
	parts := strings.Split(s, ".")
	if s == "" || len(parts) > 3 {
		return Version{}, fmt.Errorf("versiya %q noto'g'ri", s)
	}
	var v Version
	for i, p := range parts {
		n, err := strconv.Atoi(p)
		if err != nil || n < 0 || n > 1_000_000 || strconv.Itoa(n) != p {
			return Version{}, fmt.Errorf("versiya %q noto'g'ri", s)
		}
		v[i] = n
	}
	return v, nil
}

func (v Version) String() string { return fmt.Sprintf("%d.%d.%d", v[0], v[1], v[2]) }

// Less v < o ekanini bildiradi.
func (v Version) Less(o Version) bool {
	for i := range v {
		if v[i] != o[i] {
			return v[i] < o[i]
		}
	}
	return false
}

var errDevBuild = errors.New("agent reliz versiyasi bilan yig'ilmagan (dev), yangilab bo'lmaydi")
