# 4. Funksional talablar

Har talab jadvalda quyidagi ustunlar bilan beriladi: **ID**, **Talab**, **Ust.** (M/S/C/W),
**Faza** (F1/F2/F3), **Qabul mezoni** (talab bajarilganini qanday tekshirish).

Modullar: REG (reyestr), HST (host), AGT (agent), DKR (Docker), SVC (systemd va cron),
HTTP (faol tekshiruvlar), TLS (sertifikat), DNS (DNS va domen), BKP (zaxira),
ALR (alert), NTF (bildirishnoma), UI (interfeys), AUTH (autentifikatsiya), AUD (audit),
INT (integratsiya), SYS (tizimning o'zi).

## 4.1. REG — Reyestr moduli

Reyestr — barcha serverlar, loyihalar, domenlar va portlarning yagona manbai.
Nazoratchi'dagi boshqa barcha modullar reyestrga tayanadi.

| ID | Talab | Ust. | Faza | Qabul mezoni |
|---|---|---|---|---|
| FR-REG-001 | **Server obyekti.** Har serverda: nom, provayder, ommaviy IP (IPv4, ixtiyoriy IPv6), OS, rol, teglar, joylashuv, narx/oy (ixtiyoriy), izoh, holat (yangi/onlayn/aloqa yo'q/pauza/arxiv). Nom noyob bo'lishi kerak | M | F1 | Server yaratilganda barcha maydonlar saqlanadi; takroriy nom 409 xato qaytaradi |
| FR-REG-002 | **Loyiha obyekti.** Har loyihada: nom, qisqa tavsif, egasi/mijoz, tur (compose / systemd / static / boshqa), asosiy server, `appctl` papka nomi, teglar, holat (ishlayapti / ko'chirilmagan / arxiv) | M | F1 | Loyiha yaratiladi va serverga bog'lanadi; bir loyiha bir nechta serverda bo'lishi mumkin (staging/production) |
| FR-REG-003 | **Domen obyekti.** Har domenda: FQDN, loyiha, kutilgan IP lar ro'yxati, DNS provayder, registrar, domen egasi/nazoratchisi (biz/mijoz), WHOIS muddati, HTTP tekshiruv sozlamalari | M | F1 | Bitta loyihaga ko'p domen biriktiriladi; FQDN noyob |
| FR-REG-004 | **Birlashtirilgan ro'yxat.** Loyihalar sahifasi har loyiha uchun: domenlar, server, port(lar), joriy holat, oxirgi zaxira yoshi, eng yaqin sertifikat muddati ustunlarini ko'rsatadi; ustun bo'yicha saralash va qidiruv | M | F1 | 10 loyiha bilan ro'yxat < 1 soniyada yuklanadi; saralash ishlaydi |
| FR-REG-005 | **Loyiha qo'shish formasi.** UC-10 bo'yicha; domen kiritilganda avtomatik HTTP/TLS/DNS tekshiruvlari qo'shiladi (rozilik bilan) | M | F1 | Yangi loyiha qo'shilgach 1 daqiqada tekshiruvlar ishga tushadi |
| FR-REG-006 | **Tahrirlash va arxivlash.** Obyektlar o'chirilmaydi, arxivga o'tadi (tarix va incident bog'lanishlari saqlanadi). Arxivlangan obyekt alert yubormaydi | M | F1 | Arxivlangan loyiha ro'yxatda ko'rinmaydi (filtr bilan ko'rinadi); tarixi saqlanadi |
| FR-REG-007 | **"Ko'chirilmagan" holati.** Loyiha hali ishlamayotgan bo'lsa ham reyestrda saqlanadi; unga tekshiruv va alert qo'llanmaydi | S | F2 | `moved=false` loyiha 2.4-bo'lim ro'yxatiga mos holda ko'rinadi, alert yubormaydi |
| FR-REG-008 | **Teglar va guruhlash.** Teglar (masalan, `django`, `client:wmg`, `prod`) bo'yicha filtr va guruhlangan ko'rinish | S | F2 | Tegli filtr ro'yxatni to'g'ri toraytiradi |
| FR-REG-009 | **Import/eksport.** Butun reyestrni YAML/JSON ga eksport va import; formatning versiyasi bor. Maqsad: zaxira va git'da saqlash | S | F2 | Eksport → yangi bo'sh tizimga import → bir xil reyestr (testda diff yo'q) |
| FR-REG-010 | **Port to'qnashuvi nazorati.** Bir serverda bir xil port ikki loyihaga berilsa, saqlashda ogohlantirish; keyingi bo'sh port taklif qilinadi (REGISTRY.md dagi qoida) | S | F2 | Port 8020 ikkinchi marta kiritilsa xato; "keyingi bo'sh: 8021" ko'rinadi |
| FR-REG-011 | **Aloqa shaxslari.** Loyiha uchun mas'ul shaxs va mijoz kontakti (ism, Telegram) saqlanadi; alertda mas'ul ko'rsatiladi | C | F3 | Alert xabarida mas'ul ism chiqadi |
| FR-REG-012 | **Havolalar va eslatmalar.** Loyihada: repo URL, deploy yo'riqnomasi, runbook havolalari, markdown izoh | C | F3 | Loyiha sahifasida havolalar ishlaydi |

## 4.2. HST — Host (server) monitoringi

Agent tomonidan yig'iladigan ko'rsatkichlar (to'liq katalog — 7-bo'lim).

| ID | Talab | Ust. | Faza | Qabul mezoni |
|---|---|---|---|---|
| FR-HST-001 | **CPU.** Umumiy foiz (user, system, iowait, steal, idle bo'yicha ham), har yadro uchun; yig'ish intervali 15 soniya | M | F1 | `stress` ostida panel 30 soniyada o'sishni ko'rsatadi; `top` bilan ±3% farq |
| FR-HST-002 | **Yuklama (load average).** 1, 5, 15 daqiqalik; yadro soniga normallashtirilgan ko'rinish ham | M | F1 | `uptime` qiymatlariga mos |
| FR-HST-003 | **RAM.** Jami, band, bo'sh, mavjud (`MemAvailable`), cache/buffers; foiz va bayt | M | F1 | `free -b` bilan ±2% farq |
| FR-HST-004 | **Swap.** Jami va band; swap-in/out tezligi | S | F1 | `free` bilan mos |
| FR-HST-005 | **Disk hajmi va bashorat.** Har o'rnatilgan fayl tizimi (tmpfs, overlay va squashfs'siz) uchun jami/band/bo'sh; asosiy bo'limda chiziqli regressiya bilan "to'lishga qolgan kun" hisoblanadi | M | F1 | `df` bilan mos; sun'iy o'sish testida bashorat ±20% aniq |
| FR-HST-006 | **Disk I/O.** O'qish/yozish baytlari/s, IOPS, o'rtacha kutish vaqti (await), band foiz (util) har blok qurilma uchun | S | F2 | `fio` ostida o'sish ko'rinadi |
| FR-HST-007 | **Tarmoq.** Interfeys bo'yicha kiruvchi/chiquvchi bayt/s, paket/s, xato va tashlangan paketlar; `lo` va `docker*`/`veth*` ni yashirish mumkin | M | F1 | `iperf3`/`curl` yuklamasida o'sish ko'rinadi |
| FR-HST-008 | **Inode.** Fayl tizimi bo'yicha inode bandligi (kichik fayllar ko'p bo'lganda disk "bo'sh", lekin yozib bo'lmaydigan holat uchun) | S | F2 | `df -i` bilan mos |
| FR-HST-009 | **Kutilayotgan reboot va kernel.** `/var/run/reboot-required` mavjudligi; ishlayotgan va o'rnatilgan eng yangi kernel versiyasi; farq bo'lsa — "reboot kerak" belgisi va yoshi (necha kundan beri) | S | F2 | Kernel o'rnatilgan serverda belgisi paydo bo'ladi, reboot'dan keyin yo'qoladi |
| FR-HST-010 | **Uptime va boot vaqti.** Server ishga tushgan vaqt, uptime; kutilmagan reboot aniqlanadi (boot vaqti o'zgargan va ruxsat etilgan texnik ish yo'q) | M | F1 | Reboot'dan keyin 1 daqiqada "reboot aniqlandi" voqeasi yaratiladi |
| FR-HST-011 | **OS va jihoz haqida ma'lumot.** Hostname, OS nomi/versiyasi, kernel, arxitektura, CPU modeli/yadro soni, jami RAM, disk hajmi; o'zgarsa voqea yoziladi | M | F1 | Server qo'shilganda avtomatik to'ldiriladi |
| FR-HST-012 | **Jarayonlar.** Jami jarayonlar soni, zombi jarayonlar, ochiq fayl deskriptorlari (umumiy), threadlar soni | S | F2 | `ps` bilan mos |
| FR-HST-013 | **Vaqt sinxronligi.** Soat farqi (agent vaqti va markaziy vaqt); `chrony`/`timesyncd` holati. Katta farq (> 5 s) ma'lumot sifatiga ta'sir qiladi | S | F2 | Qo'lda soat siljitilsa, 1 daqiqada belgi chiqadi |
| FR-HST-014 | **SSH xavfsizlik ko'rsatkichi.** So'nggi soatdagi muvaffaqiyatsiz SSH kirishlar soni (`/var/log/auth.log` yoki `journalctl -u ssh`), noyob IP soni, `fail2ban` taqiqlagan IP soni (mavjud bo'lsa) | C | F3 | Sun'iy noto'g'ri parol bilan urinishdan keyin hisob oshadi |
| FR-HST-015 | **Paket yangilanishlari.** Kutilayotgan yangilanishlar soni va shundan xavfsizlik yangilanishlari soni (`apt`), kuniga 1 marta | C | F3 | `apt list --upgradable` bilan mos |
| FR-HST-016 | **Pauza.** Host "pauza" rejimiga o'tkazilsa, unga alert yuborilmaydi, lekin ma'lumot yig'ilaveradi; pauzani kim va qachon qo'yganini ko'rsatadi | M | F1 | Pauzadagi serverga alert kelmaydi; audit jurnalida yoziladi |
| FR-HST-017 | **Eng og'ir jarayonlar (top-N).** CPU va RAM bo'yicha 5 ta eng og'ir jarayon (nomi, PID, foiz); har 60 soniyada | C | F3 | `stress` ishga tushirilganda ro'yxatda ko'rinadi |

## 4.3. AGT — Agent moduli

| ID | Talab | Ust. | Faza | Qabul mezoni |
|---|---|---|---|---|
| FR-AGT-001 | **Bir buyruqli o'rnatish.** `curl ... \| sudo bash -s -- --token <T>` shaklidagi skript: arxitekturani aniqlaydi, agent faylini yuklaydi, SHA-256 imzosini tekshiradi, systemd unit yaratadi va ishga tushiradi. Skript idempotent: qayta ishga tushirsa buzmaydi | M | F1 | Toza Ubuntu 22.04 va 24.04 da 60 soniyada o'rnatiladi; qayta ishga tushirish xatosiz |
| FR-AGT-002 | **Token almashtirish.** Bir martalik "enroll" tokeni (1 soat amal qiladi) birinchi ulanishda doimiy agent tokeniga almashtiriladi; doimiy token faqat agent faylida (rejim 0600) saqlanadi | M | F1 | Eskirgan enroll tokeni rad etiladi; doimiy token oddiy foydalanuvchi o'qiy olmaydi |
| FR-AGT-003 | **Sozlama fayli.** `/etc/nazoratchi/agent.yaml` (core manzil, intervallar, yoqilgan kollektorlar, kuzatiladigan servislar/papkalar); o'zgarishi `SIGHUP` yoki servis qayta ishga tushirilganda qo'llanadi | M | F1 | Intervalni o'zgartirib qayta yuklagach yangi interval ishlaydi |
| FR-AGT-004 | **Yig'ish intervallari.** Standart: tizim metrikalari 15 s; Docker 30 s; disk/papka skaneri 5 daqiqa; sertifikat skaneri 6 soat. Minimal interval 5 s | M | F1 | Standart qiymatlar sozlamada ko'rinadi, o'zgartirilsa ishlaydi |
| FR-AGT-005 | **Yuborish.** Ma'lumot HTTPS POST bilan paketlab (JSON, gzip), har 15 soniyada; agent faqat chiquvchi ulanish ochadi | M | F1 | Serverda hech qanday yangi inbound port ochilmaydi (`ss -ltn` farqi yo'q) |
| FR-AGT-006 | **Heartbeat.** Har 15 soniyada kichik "tirikman" paketi (versiya, uptime, bufer holati); ma'lumot paketi bilan birlashtirilishi mumkin | M | F1 | 120 soniya kelmasa host "aloqa yo'q" bo'ladi |
| FR-AGT-007 | **Mahalliy bufer.** Aloqa uzilsa, ma'lumot diskdagi navbatda (maks. 20 MB yoki 15 daqiqa) saqlanadi, aloqa tiklangach vaqt tartibida yuboriladi; bufer to'lsa eng eski ma'lumot o'chiriladi | M | F1 | Tarmoq 5 daqiqaga uzilib tiklangach grafikda bo'shliq yo'q |
| FR-AGT-008 | **O'z-o'zini yangilash.** Core yangi versiya borligini bildiradi; agent faylni yuklaydi, imzoni tekshiradi, o'zini almashtiradi va qayta ishga tushadi; muvaffaqiyatsiz bo'lsa eski versiyaga qaytadi | S | F2 | Versiya yangilanishi paneldan boshqariladi; buzuq fayl bilan rollback ishlaydi |
| FR-AGT-009 | **Resurs cheklovi.** Agent o'rtacha ≤ 1% CPU va ≤ 60 MB RAM; systemd `MemoryMax=100M`, `CPUQuota=20%` | M | F1 | 24 soatlik o'lchovda chegaradan oshmaydi |
| FR-AGT-010 | **Minimal huquq.** Agent `root` bo'lmagan `nazoratchi` foydalanuvchisi bilan ishlaydi; Docker ma'lumoti uchun socket'ga to'g'ridan-to'g'ri emas, faqat o'qish huquqli proksi (`docker-socket-proxy`) orqali; tizim fayllarini o'qish uchun `adm`/`systemd-journal` guruhlari | M | F1 | `id nazoratchi` da `docker` guruhi yo'q; agent `docker run` qila olmaydi |
| FR-AGT-011 | **Versiya hisoboti.** Agent o'z versiyasi, build vaqti va OS/arxitekturasini bildiradi; panelda eskirgan agentlar belgilanadi | S | F2 | Eski versiyali agent "yangilash kerak" deb ko'rinadi |
| FR-AGT-012 | **Soat farqi aniqlash.** Core javobida o'z vaqtini qaytaradi; agent farq > 5 s bo'lsa shuni bildiradi | S | F2 | Soat 10 s ga siljitilsa belgi chiqadi |
| FR-AGT-013 | **Toza o'chirish.** `nazoratchi-agent uninstall` servis, fayl, foydalanuvchi va sozlamani o'chiradi va core'ga "xayrlashuv" yuboradi (host "arxiv" holatiga tushadi) | S | F2 | O'chirishdan keyin tizimda agent izi qolmaydi |
| FR-AGT-014 | **Kollektorlar tizimi.** Har metrika guruhi alohida kollektor (`system`, `disk`, `net`, `docker`, `systemd`, `backup`, `certs`, `ssh`); kollektor xatosi boshqalarga ta'sir qilmaydi, xato `agent_collector_errors` metrikasi sifatida yuboriladi | M | F1 | Docker to'xtatilsa ham tizim metrikalari uzluksiz yuboriladi |

## 4.4. DKR — Docker monitoringi

| ID | Talab | Ust. | Faza | Qabul mezoni |
|---|---|---|---|---|
| FR-DKR-001 | **Konteynerlar ro'yxati va holati.** Nom, image, holat (running/exited/restarting/paused), ishga tushgan vaqt, compose loyiha va servis nomi (labellardan) | M | F1 | `docker ps -a` bilan mos |
| FR-DKR-002 | **Health status.** Konteynerda `HEALTHCHECK` bo'lsa, `healthy/unhealthy/starting` holati; unhealthy → alert | S | F2 | Sun'iy buzilgan healthcheck 2 daqiqada alert beradi |
| FR-DKR-003 | **Konteyner resurs sarfi.** Har konteyner uchun CPU %, RAM (bayt va limitga nisbatan %), tarmoq, blok I/O | S | F2 | `docker stats` bilan ±5% |
| FR-DKR-004 | **Qayta ishga tushish va crash loop.** Restart soni; 10 daqiqada ≥ 3 marta qayta ishga tushsa — "crash loop" | M | F1 | Doim xato bilan chiqadigan konteynerda alert paydo bo'ladi |
| FR-DKR-005 | **Compose loyihaga bog'lash.** `com.docker.compose.project` labeli bo'yicha konteynerlar reyestrdagi loyihaga avtomatik biriktiriladi; biriktirilmaganlar "noma'lum konteynerlar" ro'yxatida | M | F1 | Nazar konteynerlari Nazar loyihasi kartasida ko'rinadi |
| FR-DKR-006 | **Log hajmi.** Har konteyner log fayli hajmi (`/var/lib/docker/containers/<id>/<id>-json.log*`); limitdan (standart 50 MB) oshgan konteyner belgilanadi. Bu `daemon.json` limiti qo'llanmagan eski konteynerlarni topadi | S | F2 | Limitsiz konteyner ro'yxatda "log limiti yo'q" deb chiqadi |
| FR-DKR-007 | **Docker disk sarfi.** Image, konteyner, volume, build cache hajmlari (`docker system df`) va "qaytarib olinadigan" hajm | S | F2 | `docker system df` bilan mos |
| FR-DKR-008 | **OOM-kill voqealari.** Konteyner xotira yetishmasligidan o'ldirilsa (`OOMKilled`) voqea yoziladi va alert | S | F2 | `stress` bilan limitdan oshirilganda voqea paydo bo'ladi |
| FR-DKR-009 | **`daemon.json` muvofiqligi.** Docker konfiguratsiyasi qoidalarga mosligi: log drayveri/limiti, `live-restore`. Mos kelmasa — ma'lumot belgisi | C | F3 | `daemon.json` yo'q serverda belgi chiqadi |
| FR-DKR-010 | **Image yoshi.** Konteyner image'ining yaratilgan sanasi; 180 kundan eski bo'lsa — ma'lumot (xavfsizlik yangilanishi uchun) | C | F3 | Eski image belgilanadi |

## 4.5. SVC — systemd va cron

| ID | Talab | Ust. | Faza | Qabul mezoni |
|---|---|---|---|---|
| FR-SVC-001 | **Kuzatiladigan servislar ro'yxati.** Agent sozlamasida yoki panelda belgilangan systemd unit lari (`avlo-contact`, `nginx`, `docker`, `cron`, `redis` va h.k.) | M | F1 | Ro'yxatga qo'shilgan unit holati 30 soniyada ko'rinadi |
| FR-SVC-002 | **Unit holati.** `active/inactive/failed/activating`; `failed` yoki kutilmagan `inactive` → alert | M | F1 | `systemctl stop avlo-contact` dan keyin 90 soniyada alert |
| FR-SVC-003 | **Qayta ishga tushish soni.** `NRestarts` va oxirgi qayta ishga tushish vaqti; tez-tez qayta ishga tushsa alert | S | F2 | Sun'iy crash bilan alert |
| FR-SVC-004 | **Cron va davriy vazifalar heartbeat'i.** Muhim cron ishlari (zaxira, certbot renew) oxirida core'ga "men bajarildim" signali yuboradi (`curl` yoki agent komandasi); signal belgilangan oraliqda kelmasa — alert | M | F1 | `appctl backup all` signal yubormasa, 26 soatdan keyin alert |
| FR-SVC-005 | **Muvaffaqiyatsiz unitlar soni.** `systemctl --failed` soni; > 0 bo'lsa ma'lumot sifatida panelda | S | F2 | Failed unit paydo bo'lsa son ko'rinadi |
| FR-SVC-006 | **nginx konfiguratsiyasi sog'lig'i.** Agent `nginx -t` natijasini (muvaffaqiyat/xato) kuniga bir marta va konfig o'zgarganda tekshiradi; xato bo'lsa alert (reload qilinsa buzilishi mumkin) | C | F3 | Sun'iy sintaksis xatosi alert beradi |

## 4.6. HTTP — Faol tekshiruvlar

Faol tekshiruvlarni markaziy server bajaradi (agent'dan mustaqil, tashqaridan).

| ID | Talab | Ust. | Faza | Qabul mezoni |
|---|---|---|---|---|
| FR-HTTP-001 | **HTTP(S) tekshiruv.** URL, metod (GET/HEAD), kutilgan status kodi (standart 200; oraliq `200-299`), timeout (standart 10 s) | M | F1 | Ishlamayotgan URL 90 soniyada "qizil" |
| FR-HTTP-002 | **Kalit so'z tekshiruvi.** Javob matnida belgilangan matn bo'lishi (yoki bo'lmasligi) kerak | S | F2 | Soxta "502 Bad Gateway" sahifasi (200 bilan) aniqlanadi |
| FR-HTTP-003 | **Maxsus sarlavhalar.** `Host`, `X-Forwarded-Proto`, `Authorization` kabi sarlavhalar (Django `ALLOWED_HOSTS`/`SECURE_SSL_REDIRECT` uchun kerak). Maxfiy qiymatlar shifrlab saqlanadi | M | F1 | Nazar `/healthz/` `Host: nazar.avlo.ai` bilan 200 beradi |
| FR-HTTP-004 | **Intervall, qayta urinish.** Standart interval 60 s; xato bo'lsa 15 s oraliq bilan 2 marta qayta tekshiriladi; faqat 3 ketma-ket xatodan keyin "tushdi" deb belgilanadi | M | F1 | Bitta tasodifiy xato alert bermaydi |
| FR-HTTP-005 | **Yo'naltirishlar.** `301/302` ni kuzatish (maks. 5) yoki bevosita javobni baholash (sozlanadi) | S | F2 | `www → asosiy` yo'naltirish to'g'ri baholanadi |
| FR-HTTP-006 | **Javob vaqti.** Umumiy vaqt, DNS, TCP ulanish, TLS qo'l siqish, birinchi bayt vaqti (TTFB) alohida o'lchanadi; chegaradan sekin bo'lsa ogohlantirish | S | F2 | `curl -w` bilan mos taqsimot |
| FR-HTTP-007 | **TCP tekshiruv.** Berilgan host:port ga ulanish (masalan, 22, 5432 — faqat ichki tarmoqdan emas, tashqi ochiq portlar uchun); kutilmagan ochiq port aniqlansa — xavfsizlik ogohlantirishi | S | F2 | Serverda 5432 tashqariga ochilsa alert |
| FR-HTTP-008 | **Ko'p lokatsiyali tekshiruv.** Ikkinchi tekshiruvchi tugun (boshqa serverdan) — "yolg'on tushdi"ni yo'qotish uchun: ikkala tugun ham xato bersa — tasdiq | C | F3 | Bitta tugun tarmoq muammosida alert chiqmaydi |
| FR-HTTP-009 | **Uptime hisobi.** Har tekshiruv uchun kun/hafta/oy/90 kun uptime %; rejalashtirilgan texnik ish vaqti alohida hisoblanadi | M | F2 | 24 soatlik uptime = (muvaffaqiyatli / jami) bilan mos |
| FR-HTTP-010 | **Tekshiruv tarixi.** Har tekshiruvning oxirgi 90 kunlik holati, javob vaqti grafigi, xato sabablari (timeout, DNS, TLS, 5xx) | S | F2 | Grafik va xato jadvali ochiladi |

## 4.7. TLS — Sertifikat monitoringi

| ID | Talab | Ust. | Faza | Qabul mezoni |
|---|---|---|---|---|
| FR-TLS-001 | **Muddatni o'qish.** Domenning 443 portiga TLS ulanib, sertifikat `notAfter`, chiqaruvchi, subject, SAN larni olish. SNI ishlatiladi | M | F1 | `openssl s_client` natijasi bilan bir xil sana |
| FR-TLS-002 | **Chegaralar.** Qolgan kun: ≤ 21 — ogohlantirish, ≤ 7 — yuqori, ≤ 3 — kritik, 0 — o'tib ketgan (kritik). Chegaralar sozlanadi | M | F1 | Test sertifikati bilan har chegarada alert |
| FR-TLS-003 | **Ko'p domen.** Har domenning ro'yxatdagi barcha nomlari (`www`, subdomenlar) alohida tekshiriladi | M | F1 | `www.` uchun alohida holat ko'rinadi |
| FR-TLS-004 | **Zanjir va nom mosligi.** Zanjir to'liqligi, ishonchli CA, hostname SAN ga mosligi; mos kelmasa — xato | S | F2 | Noto'g'ri nom sertifikati aniqlanadi |
| FR-TLS-005 | **Mahalliy skaner.** Agent `/etc/letsencrypt/live/*/cert.pem` va konfigda ko'rsatilgan yo'llardagi sertifikatlarni o'qib, muddatini yuboradi — shu bilan ishlatilmayotgan, lekin yangilanayotgan sertifikatlar ham ko'rinadi | S | F2 | `appctl status` bo'limi "Sertifikatlar" bilan mos |
| FR-TLS-006 | **Yangilanish natijasi.** `certbot renew` (yoki konteynerdagi yangilanish) oxirgi natijasi va vaqti; yangilanish 2 marta ketma-ket xato bersa — alert (muddat hali yaqin bo'lmasa ham) | S | F2 | Sun'iy buzilgan renew alert beradi |
| FR-TLS-007 | **Protokol versiyalari.** TLS 1.0/1.1 yoqilmaganligi, HTTP/2 mavjudligi | C | F3 | Eski protokol yoqilgan serverda belgi |
| FR-TLS-008 | **Kutilgan chiqaruvchi.** Domen uchun kutilgan CA (Let's Encrypt); boshqasi chiqsa — ma'lumot | C | F3 | CA o'zgarishi ko'rinadi |
