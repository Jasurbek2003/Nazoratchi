# 1. Kirish

## 1.1. Hujjatning maqsadi

Ushbu texnik topshiriq **Nazoratchi** nomli infratuzilma monitoringi platformasini yaratish uchun
barcha talablarni belgilaydi. Hujjat quyidagi savollarga aniq javob berishi kerak:

- Tizim nimani kuzatadi va nima uchun?
- Qaysi ma'lumot qanday yig'iladi, qayerda va qancha vaqt saqlanadi?
- Qachon va kimga ogohlantirish yuboriladi?
- Dasturchi qaysi texnologiya bilan, qaysi tartibda va qanday sifat mezoni bilan ishlaydi?
- Tizim tayyor ekani qanday tekshiriladi?

Hujjat bir vaqtning o'zida (a) dasturchi uchun ishlab chiqish qo'llanmasi, (b) buyurtmachi uchun
qabul qilish shartnomasi va (c) keyinchalik tizimni ekspluatatsiya qiladigan odam uchun
ma'lumotnoma bo'lib xizmat qiladi.

## 1.2. Loyihaning qisqacha tavsifi

**Nazoratchi** — buyurtmachining barcha serverlari, ularda ishlayotgan loyihalar, zaxira
nusxalar, sertifikatlar va domenlarning holatini bitta oynada ko'rsatuvchi hamda muammo
paydo bo'lishidan **oldin** yoki paydo bo'lgan zahoti Telegram orqali xabar beruvchi platforma.

Platforma uch qismdan iborat:

1. **Agent** — har bir serverga o'rnatiladi, CPU, RAM, disk (SSD), tarmoq, Docker konteynerlar,
   systemd servislar va zaxira papkalari haqida ma'lumot yig'adi.
2. **Markaziy server** — ma'lumotni qabul qiladi, saqlaydi, qoidalar bo'yicha tahlil qiladi,
   faol tekshiruvlarni (HTTP, TLS, DNS) o'zi bajaradi, alert yuboradi.
3. **Veb-panel** — barcha ma'lumotni ko'rsatadi (jonli grafiklar, loyihalar ro'yxati, zaxiralar
   holati, incidentlar tarixi).

## 1.3. Muammo bayoni va loyiha asosi

### 1.3.1. 2026-10 hodisasi (post-mortem qisqacha)

2026-10-18 kuni 15:25 da toza `poweroff` bilan to'xtagan "Avlo main server"
(`185.214.135.9`, Contabo vmi3628663) qayta ishga tushmadi: VNC'da faqat
`Booting from Hard Disk...` ko'rinib, foydalanuvchi darajasiga hech qachon yetib bormadi.
Bir necha kunlik diagnostika (VNC, Rescue System, `fsck`, GRUB sozlamalari, boshqa kernel
tanlash) natija bermadi. Barcha ma'lumot rescue tizimidan `rsync` orqali yangi serverga
(`164.68.105.194`) ko'chirildi va loyihalar bir-bir qayta ko'tarildi.
(2026-10-26 holati: eski server tozalanib, Nazoratchi core serveri sifatida qayta o'rnatilmoqda, QARORLAR.md.)

Hodisadan olingan saboqlar, ular shu loyiha talablarining asosi bo'ldi:

| № | Saboq | Qaysi talabga olib keldi |
|---|---|---|
| L-1 | Server ishdan chiqqanini foydalanuvchilar yoki egasi o'zi bilib qoldi, avtomatik xabar bo'lmadi | Heartbeat va "server o'chdi" alerti (FR-ALR-*) |
| L-2 | Zaxira nusxalar faqat shu serverning o'zida edi; serverga kirib bo'lmagach, ularga ham kirib bo'lmadi | Offsite zaxira monitoringi (FR-BKP-*) |
| L-3 | Server GCP'dan ko'chirilgan, GCP'ga xos kernel va agentlar qolgan edi; bu xavf oldindan ko'rinmagan | Inventar va "kutilayotgan kernel yangilanishi" tekshiruvi (FR-HST-*) |
| L-4 | Kernel yangilanishi/reboot dan oldin snapshot olinmagan | Reboot oldidan nazorat ro'yxati va "reboot kerak" belgisi |
| L-5 | Loyihalar qaysi serverda, qaysi portda, qaysi domen bilan ishlashi bitta joyda yozilmagan edi | Reyestr (registry) moduli (FR-REG-*) |
| L-6 | DNS yozuvlari turli provayderlarda (ahost.uz, Namecheap, Google Cloud DNS, Beget); qaysi domen qayerga qarashi noaniq | DNS monitoring (FR-DNS-*) |
| L-7 | Sertifikat muddati qo'lda kuzatilgan | TLS monitoring (FR-TLS-*) |
| L-8 | Disk va log hajmi nazoratsiz | Disk bashorati va Docker log hajmi tekshiruvi |

### 1.3.2. Hozirgi kuzatuv holati

Hozir (2026-10-22) monitoring **yo'q**: faqat `appctl status` buyrug'i qo'lda ishga
tushiriladi va diskning, xotiraning, konteynerlarning, sertifikat muddatlarining hamda oxirgi
zaxiralarning bir lahzalik holatini ko'rsatadi. Tarix saqlanmaydi, ogohlantirish yo'q.

### 1.3.3. Ishlatilmagan imkoniyatlar

- Zaxira kunlik 03:15 da avtomatik olinadi (`/etc/cron.d/appctl-backup`), lekin natijasi
  faqat `/var/log/appctl-backup.log` ga yoziladi. Hech kim uni o'qimaydi; muvaffaqiyatsiz
  zaxira bir hafta jim qolishi mumkin.
- Sertifikatlar `certbot` bilan yangilanadi, lekin yangilanish xatosi haqida xabar yo'q.
- Docker konteynerlar `restart: unless-stopped` bilan qayta ishga tushadi, lekin cheksiz
  qayta ishga tushish (crash loop) bildirilmaydi.

## 1.4. Loyiha maqsadlari

| ID | Maqsad | O'lchov |
|---|---|---|
| G-1 | Har bir server holatini (CPU, RAM, disk, tarmoq) real vaqtga yaqin ko'rish | Yangilanish kechikishi ≤ 30 soniya |
| G-2 | Server yoki servis ishdan chiqqanini tez bilish | MTTD ≤ 2 daqiqa (server), ≤ 90 soniya (HTTP servis) |
| G-3 | Disk to'lib qolishidan oldin ogohlantirish | Disk to'lishiga ≥ 7 kun qolganda xabar |
| G-4 | Zaxira nusxalar mavjudligi, yangiligi va to'liqligiga ishonch | Har loyiha uchun "oxirgi muvaffaqiyatli zaxira yoshi" ko'rinadi; > 26 soat bo'lsa alert |
| G-5 | Sertifikat va domen muddati o'tib ketmasligi | 21, 7, 3 kun oldin ogohlantirish |
| G-6 | Barcha loyiha/domen/port/baza ma'lumoti bitta reyestrda | Reyestr 100% inventarga mos |
| G-7 | Ogohlantirishlar "shovqin" bo'lmasligi | Soxta alert ulushi ≤ 5% (oyiga) |
| G-8 | Tizimning o'zi ishonchli bo'lishi | Nazoratchi'ning o'zi o'chsa, boshqa serverdagi (S-01) "watchdog" xabar beradi |
| G-9 | Kam resurs sarfi | Agent ≤ 1% CPU, ≤ 60 MB RAM; markaziy server 1 vCPU/2 GB da ishlaydi |
| G-10 | Sodda boshqaruv | Yangi serverni 5 daqiqada qo'shish (bitta buyruq) |

## 1.5. Loyiha doirasi

### 1.5.1. Doira ichida

1. Linux serverlarni (Ubuntu 22.04/24.04) agent orqali kuzatish.
2. Tizim metrikalari: CPU, yuklama (load), RAM, swap, disk (hajm, inode, I/O), tarmoq,
   jarayonlar soni, uptime, kernel versiyasi, kutilayotgan reboot.
3. Docker: konteynerlar holati, qayta ishga tushishlar, resurs sarfi, log hajmi,
   image/volume hajmi.
4. systemd: berilgan servislar holati (masalan, `avlo-contact`, `redis`, `nginx`).
5. Faol tekshiruvlar: HTTP(S), TCP port, DNS, TLS sertifikat muddati, domen (WHOIS) muddati.
6. Zaxira nusxalar: `/opt/applications/backups/<loyiha>/{daily,weekly}` ni kuzatish,
   offsite sinxronlashni tekshirish, tiklash testini (restore drill) rejalashtirish va qayd etish.
7. Reyestr: serverlar, loyihalar, domenlar, portlar, bazalar, egalar.
8. Alert tizimi: qoidalar, jim qilish (silence), texnik ish oynalari, eskalatsiya.
9. Kanallar: Telegram (asosiy), elektron pochta (ikkilamchi), webhook (kengaytma).
10. Veb-panel (uz/ru/en), mobil brauzerda qulay.
11. Rollar: egasi (owner), operator, kuzatuvchi (read-only).
12. Audit jurnali: kim nimani o'zgartirdi.
13. O'zini-o'zi kuzatish va alohida serverdagi watchdog (S-01).

### 1.5.2. Doira tashqarisida (bu versiyada)

| ID | Nima | Sababi |
|---|---|---|
| X-1 | Ilova ichidagi APM / distributed tracing (OpenTelemetry) | Alohida katta yo'nalish; F3 dan keyin |
| X-2 | Log yig'ish va qidirish (Loki/ELK analogi) | Faqat log hajmi nazorati kiradi, mazmuni emas |
| X-3 | Avtomatik tuzatish (auto-remediation), masalan, konteynerni o'zi qayta ishga tushirish | Xavfli; faqat F3 da, cheklangan "restart" amali |
| X-4 | Windows/macOS serverlar | Infratuzilmada yo'q |
| X-5 | Kubernetes | Infratuzilmada yo'q |
| X-6 | Ko'p ijarachili (multi-tenant) SaaS rejimi | Bitta egasi uchun |
| X-7 | Zaxiralarni o'zi olish | Zaxirani `appctl` oladi; Nazoratchi faqat kuzatadi (restore drill bundan mustasno, 10-bo'lim) |
| X-8 | Serverni boshqarish (SSH terminal, fayl menejer) | Xavfsizlik xavfi; kuzatuv ≠ boshqaruv |

## 1.6. Manfaatdor tomonlar

| Tomon | Qiziqishi |
|---|---|
| Egasi (Jasurbek) | Barcha loyiha ishlashini bilish, mijozlar oldida javobgarlik, pul yo'qotishdan saqlanish |
| Dasturchi/DevOps (egasi yoki yollangan) | Muammoni tez topish, aniq ko'rsatma, kam shovqin |
| Mijozlar (masalan, wmg.uz egasi, Nazar foydalanuvchilari) | Xizmat uzluksizligi; to'g'ridan-to'g'ri Nazoratchi'dan foydalanmaydi |
| Hamkor hosting provayderlari (Contabo va boshqalar) | Faqat tashqi omil: server holati ularga bog'liq |

## 1.7. Muvaffaqiyat mezonlari (KPI)

Tizim ishga tushirilgandan keyin 90 kun ichida quyidagilar bajarilishi kerak:

| KPI | Maqsad |
|---|---|
| Barcha serverlar va loyihalar reyestrda | 100% |
| Server o'chganda xabar kelish vaqti | ≤ 2 daqiqa |
| HTTP servis ishdan chiqqanda xabar kelish vaqti | ≤ 90 soniya |
| Muvaffaqiyatsiz zaxira aniqlanishi | Keyingi tekshiruvda (≤ 15 daqiqa); eng ko'pi bilan 26 soatda |
| Sertifikat muddati o'tib ketgan holatlar | 0 |
| Disk to'lib ketgan holatlar | 0 |
| Soxta alertlar | ≤ 5% |
| Haqiqiy incidentlarning aniqlanish ulushi | ≥ 95% (qo'lda baholash) |
| Nazoratchi'ning o'zi uptime'i | ≥ 99.5% |
| Restore drill | Har loyiha uchun kamida chorakda 1 marta muvaffaqiyatli |

## 1.8. Taxminlar va cheklovlar

### 1.8.1. Taxminlar

1. Barcha kuzatiladigan serverlar Linux (Ubuntu), `systemd` va Docker (ba'zilarida) bilan.
2. Markaziy server **kuzatiladigan serverlardan alohida** joyda turadi (kamida bitta server
   boshqasini kuzatishi uchun). Tavsiya: alohida arzon VPS (1 vCPU / 2 GB / 20 GB).
3. Agentlar markazga HTTPS orqali chiqish (outbound) ulanishi bilan ma'lumot yuboradi;
   kuzatiladigan serverda yangi kiruvchi (inbound) port ochish talab qilinmaydi.
4. Telegram bot tokeni mavjud va kanal (chat) ochilgan bo'ladi.
5. Egasi bitta shaxs yoki kichik jamoa; 10–30 server va 20–60 loyiha miqyosi.

### 1.8.2. Cheklovlar

| ID | Cheklov |
|---|---|
| C-1 | Byudjet cheklangan: ochiq manbali komponentlar ishlatiladi, pullik SaaS yo'q |
| C-2 | Asosiy texnologiyalar buyurtmachi tanish stekka mos: Python/Django, PostgreSQL, Docker Compose, nginx |
| C-3 | Markaziy server resursi kam (1–2 vCPU, 2–4 GB RAM) |
| C-4 | Maxfiy ma'lumot (parol, token) metrikalarga yoki loglarga tushmasligi kerak |
| C-5 | Barcha interfeys matnlari o'zbek tilida (lotin); qo'shimcha ru, en |
| C-6 | Agent o'rnatilishi mavjud ishlayotgan loyihalarni to'xtatmasligi kerak |

## 1.9. Mavjud yechimlar bilan taqqoslash va tanlov asosi

Bu bo'lim halollik uchun kiritilgan: tayyor yechimlar bor, ularning ba'zilari
ushbu TZ ning katta qismini allaqachon bajaradi. Qaror egasiga tegishli.

| Yechim | Kuchli tomoni | Zaif tomoni (bizning ehtiyoj uchun) |
|---|---|---|
| **Uptime Kuma** | HTTP/TCP/DNS/sertifikat tekshiruvi, chiroyli panel, Telegram — 10 daqiqada ishga tushadi | CPU/RAM/disk yo'q; zaxira fayllarini kuzatmaydi |
| **Netdata** | Server metrikalari va Docker, juda boy, tayyor alertlar | Zaxira, reyestr, o'zbekcha UI, bizning `appctl` bilan integratsiya yo'q; markaziy panel (Netdata Cloud) tashqi xizmat |
| **Prometheus + Grafana + Alertmanager** | Sanoat standarti, cheksiz moslashuvchan | Sozlash va ekspluatatsiya murakkab; zaxira/reyestr uchun baribir o'z kod kerak |
| **Beszel / Glances** | Yengil agent + panel | Funksiyalar cheklangan |
| **Zabbix** | To'liq korxona yechimi | Og'ir, ko'p resurs, o'rganish qiyin |
| **Healthchecks.io** (o'zi-hosting) | Cron/zaxira "tirikman" signallari uchun juda yaxshi | Faqat heartbeat |

**Tanlov asosi.** Nazoratchi yaratilishining sababi bitta: ehtiyojlarning aynan **birlashmasi** —
(server metrikasi) + (loyiha reyestri) + (appctl bilan zaxira nazorati va restore drill) +
(DNS/domen/sertifikat) + (o'zbekcha, sodda UI) — tayyor yechimda yo'q. Shu bilan birga:

> **Tavsiya (oraliq yechim).** Nazoratchi'ning birinchi ishlaydigan versiyasi (F1) bir dasturchi
> bilan taxminan 4–5 oy, ikki dasturchi bilan 2–2.5 oy talab qiladi (17.3.5). Shu vaqt
> davomida serverlar kuzatuvsiz qolmasligi uchun **Uptime Kuma** ni darhol o'rnatish tavsiya
> etiladi (1–2 soat ish). Nazoratchi F1 tugagach, Uptime Kuma o'chiriladi yoki ikkilamchi
> tekshiruv sifatida qoladi.

**Yaratish yoki tayyorini olish (Build vs Buy) bo'yicha xulosa:** Agar egasi faqat "server o'chdi / sayt
ishlamayapti" xabarini xohlasa — tayyor yechim yetarli. Agar zaxira va reyestr nazorati
ham muhim bo'lsa (hodisa saboqlari L-2, L-5), Nazoratchi asoslangan.

## 1.10. Talablar ustuvorligi

Talablar umumiy soni (4–5-bo'limlar): **243 ta** (178 funksional + 65 nofunksional). Taqsimot:

| Ustuvorlik | Funksional | Nofunksional | Jami | Izoh |
|---|---|---|---|---|
| M (Must) | 95 | 47 | 142 | F1 va F2 ning asosi |
| S (Should) | 59 | 15 | 74 | Asosan F2 |
| C (Could) | 24 | 3 | 27 | Asosan F3 |
| W (Won't) | 0 | 0 | 0 | Bu versiyada qilinmaydiganlar 1.5.2 da (X-1..X-8) alohida ro'yxatlangan |

Aniq ro'yxat va bosqichlar 4–5 hamda 17-bo'limlarda; bosqichlar bo'yicha taqsimot — 18.7.
