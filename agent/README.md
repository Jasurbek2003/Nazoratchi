# nazoratchi-agent

Kuzatiladigan serverda ishlaydigan yagona statik Go binari (TZ 7). U kirish portini ochmaydi, serverda
buyruq bajarmaydi; faqat o'lchaydi va core'ga HTTPS orqali yuboradi.

## Holat (F1 / S6)

| Bor | Hali yo'q (keyingi sprintlar) |
|---|---|
| `system` (CPU, yuklama, xotira, swap, uptime; F2: jarayonlar, fd, swap faolligi, OOM), `disk` (hajm, faqat-o'qish; F2: inode), `diskio` (bayt/s, IOPS, band vaqti, kutish), `reboot` (reboot kerakmi, yangi kernel), `certs` (mahalliy sertifikat muddati: `cert.pem` yoki certbot deploy-hook `certs.json`), `net` (bayt/s), `docker` (holat, restartlar, uptime, health, OOM, "kutilgan"; F2: CPU/xotira, log hajmi, `system df`), `systemd` (unit active/failed, cron heartbeat), `backup` (`appctl` state.json + papka skaneri, offsite sozlanganmi) | `ssh`, `apt`; o'z-o'zini yangilash; systemd F2 metrikalari (restartlar, uptime); backup F2 (davomiylik, `du`, `gzip -t`, offsite holati) |
| Jadval (interval ±10% jitter, timeout), 15 s paket, diskdagi navbat (20 MB / 15 daq) | Core buyruqlari (`set_interval`, `reload_config`, `update`) bajarilmaydi, faqat logga yoziladi |
| Yuborish (gzip, backoff, `Retry-After`, 401 da 5 daq), `enroll`, `facts`, o'z metrikalari (`agent_*`) | `install.sh`, systemd unit, imzolangan reliz (S7) |

## Buyruqlar

```
nazoratchi-agent run [--config /etc/nazoratchi/agent.yaml]        # standart; SIGHUP = sozlamani qayta o'qish
nazoratchi-agent enroll --core https://... --token enr_...        # yoki NAZORATCHI_ENROLL_TOKEN
nazoratchi-agent check-config [--config ...]
nazoratchi-agent collect                                          # bir martalik yig'ish, JSON (diagnostika)
nazoratchi-agent beat <job> [--dir /var/lib/nazoratchi/heartbeats]   # cron skript oxirida (FR-SVC-004)
nazoratchi-agent version
```

`beat` `<dir>/<job>` faylini atomik yozadi (ichida ISO vaqt, rejim 0644); `systemd` kollektori fayl `mtime` ini
`cron_job_last_success_timestamp{job}` sifatida yuboradi. Misol: cron skript oxirida `nazoratchi-agent beat nightly-report`.
Job nomi: `[A-Za-z0-9_.@-]{1,80}`, nuqta bilan boshlanmaydi, `.tmp` bilan tugamaydi.

`enroll` bir martalik tokenni doimiy tokenga almashtiradi va uni `0600` rejimli faylga atomik yozadi.
Enroll tokenni buyruq satrida bermaslik uchun `NAZORATCHI_ENROLL_TOKEN` muhit o'zgaruvchisini ishlating
(buyruq satri `ps` da ko'rinadi). Namuna sozlama: [`agent.example.yaml`](agent.example.yaml).

## Ishlab chiqish

Go mahalliy o'rnatilmagan bo'lsa, Docker orqali (CI dagi bilan bir xil versiya):

```sh
docker run --rm -v "$PWD:/src" -v nzr-gomod:/go/pkg/mod -w /src/agent golang:1.27-bookworm \
  sh -c 'gofmt -l . && go vet ./... && go test -race -cover ./...'
```

Yig'ish: `CGO_ENABLED=0 GOOS=linux GOARCH=amd64|arm64 go build -trimpath -ldflags "-s -w -X main.version=X" ./cmd/nazoratchi-agent`.

## Tuzilma

```
cmd/nazoratchi-agent   buyruqlar, signallar
internal/agent         jadval, Batcher (seq, faktlar, 1000 qator chegarasi), Uploader (backoff), o'z metrikalari
internal/collector     system, disk, net, docker, systemd (Runner: soxta systemctl), backup (/proc ildizi parametr: testlarda soxta fayl daraxti)
internal/queue         diskdagi navbat (atomik yozish, hajm va yosh chegarasi)
internal/sender        HTTPS (TLS 1.2+, yo'naltirishsiz), gzip, enroll
internal/facts         hostname, OS, kernel (ishlayotgan va o'rnatilgan eng yangi), CPU, RAM
internal/config        agent.yaml (noma'lum kalit = xato), tekshiruv
```

## Ma'lum cheklovlar

- `413` (paket > 1 MB) da paket bo'laklanmaydi, tashlanadi. 15 soniyalik paket ~10 KB, shuning uchun amalda uchramaydi.
- Qayta urinishdagi `seq` o'zgarmaydi, lekin `sent_at` har yuborishda yangilanadi (TZ 7.5.2).
- `seq` boshlang'ich qiymati vaqtdan (ms) olinadi: soat orqaga surilsa va agent qayta ishga tushsa `seq` kamayishi mumkin.
