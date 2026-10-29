package collector

import (
	"context"
	"fmt"
	"net/url"
	"os"
	"path/filepath"
	"time"
)

// F2 qismi (TZ 7.4.4): resurs sarfi, log hajmi va `docker system df`. Hammasi faqat GET.

const (
	// dfEvery — `GET /system/df` og'ir (volume hajmlarini hisoblaydi): TZ bo'yicha 10 daqiqada bir.
	dfEvery = 10 * time.Minute
	// dfTimeout — df sekin javob bersa, 30 s lik asosiy yig'ishni to'xtatib qo'ymaslik uchun.
	dfTimeout = 20 * time.Second
	// hostMemTTL — `/info` dagi xost RAM hajmi kam o'zgaradi.
	hostMemTTL = time.Hour
	// unlimitedMem — cgroup v1 da limitsiz konteyner shu atrofdagi qiymat qaytaradi.
	unlimitedMem = uint64(1) << 60
)

type dockerStats struct {
	CPUStats struct {
		CPUUsage struct {
			TotalUsage  uint64   `json:"total_usage"`
			PercpuUsage []uint64 `json:"percpu_usage"`
		} `json:"cpu_usage"`
		SystemCPUUsage uint64 `json:"system_cpu_usage"`
		OnlineCPUs     uint32 `json:"online_cpus"`
	} `json:"cpu_stats"`
	MemoryStats struct {
		Usage uint64            `json:"usage"`
		Limit uint64            `json:"limit"`
		Stats map[string]uint64 `json:"stats"`
	} `json:"memory_stats"`
}

type cpuPrev struct{ total, system uint64 }

type dockerSystemDF struct {
	LayersSize int64 `json:"LayersSize"`
	Images     []struct {
		Size int64 `json:"Size"`
	} `json:"Images"`
	Containers []struct {
		SizeRw int64 `json:"SizeRw"`
	} `json:"Containers"`
	Volumes []struct {
		UsageData *struct {
			Size int64 `json:"Size"`
		} `json:"UsageData"`
	} `json:"Volumes"`
	BuildCache []struct {
		Size int64 `json:"Size"`
	} `json:"BuildCache"`
}

// resources: CPU %, xotira va limit. Docker `cpu_percent` ni ikki o'lchov farqidan hisoblaydi
// (`one-shot` so'rovda oldingi namuna bo'lmaydi, shuning uchun oldingisini o'zimiz eslab qolamiz).
func (d *Docker) resources(ctx context.Context, o *out, id string, labels []string, hostMem uint64) error {
	var st dockerStats
	if err := d.get(ctx, "/containers/"+url.PathEscape(id)+"/stats?stream=false&one-shot=true", &st); err != nil {
		return err
	}
	cur := cpuPrev{total: st.CPUStats.CPUUsage.TotalUsage, system: st.CPUStats.SystemCPUUsage}
	if p, ok := d.prevCPU[id]; ok && cur.total >= p.total && cur.system > p.system {
		cpus := float64(st.CPUStats.OnlineCPUs)
		if cpus == 0 {
			cpus = float64(len(st.CPUStats.CPUUsage.PercpuUsage))
		}
		if cpus == 0 {
			cpus = 1
		}
		// Bir yadro = 100% (TZ 7.4.4), shuning uchun yadrolar soniga ko'paytiriladi.
		pct := float64(cur.total-p.total) / float64(cur.system-p.system) * cpus * 100
		o.add("docker_container_cpu_percent", max(0, pct), labels...)
	}
	d.prevCPU[id] = cur

	used := st.MemoryStats.Usage
	// Sahifa keshi ("cache") hisobga olinmaydi, aks holda fayl o'qiydigan konteyner xotirani to'ldirgandek ko'rinadi.
	for _, k := range []string{"total_inactive_file", "inactive_file", "cache"} { // cgroup v1, v2, eski
		if c, ok := st.MemoryStats.Stats[k]; ok {
			used -= min(used, c)
			break
		}
	}
	o.add("docker_container_mem_bytes", float64(used), labels...)
	limit := st.MemoryStats.Limit
	if limit == 0 || limit >= unlimitedMem || (hostMem > 0 && limit >= hostMem) {
		// Limitsiz: Docker xost RAM ni limit sifatida ko'rsatadi. 0 = "cheksiz", foiz hisoblanmaydi.
		o.add("docker_container_mem_limit_bytes", 0, labels...)
		return nil
	}
	o.add("docker_container_mem_limit_bytes", float64(limit), labels...)
	o.add("docker_container_mem_percent", percent(100*float64(used)/float64(limit)), labels...)
	return nil
}

// hostMemory `/info` dan xost RAM hajmi; limitsiz konteynerni aniqlash uchun. Topilmasa 0.
func (d *Docker) hostMemory(ctx context.Context, now time.Time) uint64 {
	if d.hostMem > 0 && now.Sub(d.hostMemAt) < hostMemTTL {
		return d.hostMem
	}
	var info struct {
		MemTotal uint64 `json:"MemTotal"`
	}
	if err := d.get(ctx, "/info", &info); err == nil && info.MemTotal > 0 {
		d.hostMem, d.hostMemAt = info.MemTotal, now
	}
	return d.hostMem
}

// logBytes konteyner log fayli va aylantirilgan nusxalari (`<id>-json.log*`) hajmi. Fayl mazmuni
// o'qilmaydi, faqat `stat`. Huquq yo'q yoki drayver `json-file` emas bo'lsa ok=false (xato emas, 7.8).
func logBytes(logPath string) (total int64, ok bool) {
	if logPath == "" {
		return 0, false
	}
	matches, err := filepath.Glob(logPath + "*")
	if err != nil {
		return 0, false
	}
	for _, m := range matches {
		if fi, err := os.Stat(m); err == nil && fi.Mode().IsRegular() {
			total += fi.Size()
			ok = true
		}
	}
	if !ok {
		// Papka o'qilmasa Glob jim bo'sh qaytaradi; bevosita stat huquq xatosini ham ko'rsatmaydi.
		if fi, err := os.Stat(logPath); err == nil && fi.Mode().IsRegular() {
			return fi.Size(), true
		}
	}
	return total, ok
}

// systemDF — `docker system df`: image, konteyner (yozuvchi qatlam), volume va build cache hajmlari.
func (d *Docker) systemDF(ctx context.Context, o *out, now time.Time) error {
	if !d.dfAt.IsZero() && now.Sub(d.dfAt) < dfEvery {
		return nil
	}
	d.dfAt = now // xato bo'lsa ham 10 daqiqa kutiladi: og'ir so'rovni har siklda takrorlamaslik uchun
	ctx, cancel := context.WithTimeout(ctx, dfTimeout)
	defer cancel()
	var df dockerSystemDF
	if err := d.get(ctx, "/system/df", &df); err != nil {
		return fmt.Errorf("system df: %w", err)
	}
	images := df.LayersSize // umumiy qatlamlar ikki marta sanalmaydi
	if images == 0 {
		for _, im := range df.Images {
			images += im.Size
		}
	}
	var containers, volumes, cache int64
	for _, c := range df.Containers {
		containers += max(0, c.SizeRw)
	}
	for _, v := range df.Volumes {
		if v.UsageData != nil && v.UsageData.Size > 0 { // -1: hajm hisoblanmagan
			volumes += v.UsageData.Size
		}
	}
	for _, b := range df.BuildCache {
		cache += max(0, b.Size)
	}
	o.add("docker_images_bytes", float64(max(0, images)))
	o.add("docker_containers_bytes", float64(containers))
	o.add("docker_volumes_bytes", float64(volumes))
	o.add("docker_build_cache_bytes", float64(cache))
	return nil
}
