# 13. Foydalanuvchi interfeysi

## 13.1. Dizayn tamoyillari

1. **5 soniya qoidasi.** Bosh sahifaga qarab, 5 soniyada "hammasi joyidami?" ga javob olinishi kerak.
   Birinchi ekran — raqamlar emas, **xulosa**: "Hammasi joyida" yoki "2 ta muammo".
2. **Muammo tepada.** Sog'lom narsalar jim; muammolar yuqorida, rangli, bosiladigan.
3. **Bir bosishda sababga.** Dashboard → incident → server/loyiha → grafik: har bosqich bir bosish.
4. **Rang yagona signal emas.** Har holat rang + belgi + matn (rang ko'rlik va qora-oq chop uchun).
5. **Zichlik.** DevOps foydalanuvchi uchun ma'lumot zich, lekin o'qiladigan: bir ekranda 10 ta
   serverni sparkline'lar bilan sig'dirish.
6. **Ishonch.** Ma'lumot yangiligini doimo ko'rsatish ("yangilandi: 3 soniya oldin"); ma'lumot
   kelmayotgan bo'lsa — "eskirgan", hech qachon eski raqamni "hozirgi" deb ko'rsatmaslik.
7. **Xavfsiz amallar.** Qaytarib bo'lmaydigan amallar (token bekor qilish, arxivlash) tasdiqlanadi
   va nima bo'lishi yozib ko'rsatiladi.
8. **Tezlik.** Skeleton yuklash, kesh, `stale-while-revalidate`; hech qachon bo'sh oq ekran.

## 13.2. Axborot arxitekturasi (sitemap)

```
/                       Bosh sahifa (Dashboard)
/servers                Serverlar ro'yxati
/servers/:id            Server sahifasi  (Umumiy | Resurslar | Konteynerlar | Servislar | Tarix)
/projects               Loyihalar ro'yxati
/projects/:id           Loyiha sahifasi  (Holat | Domenlar | Konteynerlar | Zaxira | Incidentlar | Sozlama)
/domains                Domenlar va sertifikatlar
/domains/:id            Domen sahifasi (DNS, TLS, HTTP tarixi)
/backups                Zaxiralar (umumiy jadval)
/backups/:project       Loyiha zaxira kartasi, restore drill
/incidents              Incidentlar (ochiq / yopilgan)
/incidents/:id          Incident tafsiloti
/alerts/rules           Alert qoidalari
/alerts/silences        Jim qilishlar va texnik ishlar (maintenance)
/reports                Hisobotlar
/settings               Sozlamalar (Kanallar | Foydalanuvchilar | Tokenlar | Saqlash | Tizim)
/audit                  Audit jurnali
/status/:slug           Ommaviy holat sahifasi (F3, avtorizatsiyasiz)
/login                  Kirish
```

**Asosiy navigatsiya** (chap panel desktopda, pastki panel mobilda): Bosh sahifa, Serverlar,
Loyihalar, Zaxiralar, Incidentlar (ochiq soni nishonchasi bilan), Yana (Domenlar, Qoidalar,
Hisobotlar, Sozlamalar). Yuqorida: global qidiruv (`/`), vaqt zonasi/til, foydalanuvchi menyusi,
"yangilandi: N soniya oldin" ko'rsatkichi.

## 13.3. Ekranlar ro'yxati

| ID | Ekran | Asosiy maqsad | Talablar |
|---|---|---|---|
| SCR-01 | Dashboard | Umumiy holat, muammolar, muddatlar | FR-UI-001, 002 |
| SCR-02 | Serverlar ro'yxati | Hamma serverni bir qarashda | FR-UI-004 |
| SCR-03 | Server sahifasi | Resurslar, konteynerlar, servislar, tarix | FR-UI-005 |
| SCR-04 | Loyihalar ro'yxati | Birlashtirilgan reyestr | FR-UI-003 |
| SCR-05 | Loyiha sahifasi | Loyiha holati va barcha tarkibiy qismlari | FR-UI-006 |
| SCR-06 | Zaxiralar | Hamma loyiha zaxirasi jadvali | FR-UI-008 |
| SCR-07 | Zaxira kartasi + drill | Bitta loyiha zaxirasi, drill kiritish | FR-BKP-003, 016 |
| SCR-08 | Domenlar va sertifikatlar | Muddatlar, DNS mosligi | FR-UI-009 |
| SCR-09 | Domen sahifasi (+ cut-over) | DNS resolverlar, tarixi, kesib o'tish yordamchisi | FR-DNS-002, 005, 009 |
| SCR-10 | Incidentlar ro'yxati | Ochiq va yopilgan incidentlar | FR-UI-010 |
| SCR-11 | Incident tafsiloti | Vaqt chizig'i, ta'sirlanganlar, izohlar | FR-UI-010, FR-ALR-016 |
| SCR-12 | Alert qoidalari | Ko'rish, tahrirlash, sinash | FR-ALR-007 |
| SCR-13 | Jim qilish va texnik ishlar | Silence, maintenance | FR-UI-011 |
| SCR-14 | Hisobotlar | Uptime, incident, zaxira statistikasi | FR-UI-012 |
| SCR-15 | Sozlamalar | Kanallar, foydalanuvchilar, tokenlar, saqlash | FR-UI-013 |
| SCR-16 | Audit jurnali | O'zgarishlar tarixi | FR-AUD-003 |
| SCR-17 | Server qo'shish | O'rnatish buyrug'i, birinchi aloqa kutish | UC-01 |
| SCR-18 | Loyiha qo'shish | Forma, avtomatik tekshiruvlar taklifi | UC-10 |
| SCR-19 | Kirish va 2FA | Autentifikatsiya | FR-AUTH-* |
| SCR-20 | Ommaviy holat sahifasi (F3) | Mijozlar uchun | FR-UI-019 |

## 13.4. Rang va holat qoidalari

### 13.4.1. Holatlar (yagona lug'at)

| Holat | Rang (semantik) | Belgi | Matn (uz) | Qachon |
|---|---|---|---|---|
| `ok` | Yashil | ● / ✓ | Joyida | Hammasi me'yorda |
| `warning` | Sariq | ▲ | Diqqat | Ogohlantirish ochiq |
| `high` | To'q sariq | ▲▲ | Muhim | `high` incident ochiq |
| `critical` | Qizil | ✖ / ! | Kritik | `critical` incident ochiq yoki xizmat to'xtagan |
| `unknown` | Kulrang | ? | Noma'lum | Ma'lumot kelmayapti |
| `paused` | Kulrang, shtrixli chegara | ⏸ | Pauza | Pauza/maintenance |
| `info` | Ko'k | i | Ma'lumot | Faqat ma'lumot |

### 13.4.2. Aggregatsiya

Obyektning umumiy holati = tarkibiy qismlar holatlarining **eng yomoni**
(`critical > high > warning > unknown > ok`). Istisno: `unknown` faqat qolganlar `ok` bo'lsa
ko'rinadi (aniq muammo noma'lumdan muhimroq). Pauza/maintenance — alohida "pauza" holati, lekin
ichidagi muammolar ko'rinadi.

### 13.4.3. Rang tokenlari

Ranglar CSS o'zgaruvchilari (`:root`) sifatida; yorug' va qorong'i mavzu uchun alohida
qiymatlar. Mavzu: tizim sozlamasi (`prefers-color-scheme`) + qo'lda almashtirish (`data-theme`).

```css
:root {
  --bg: #f7f8fa;      --surface: #ffffff;   --text: #1b1f24;   --muted: #5c6670;  --border: #dde1e6;
  --ok: #1f9d55;      --warning: #c28400;   --high: #d9622b;   --critical: #cf2e2e;
  --unknown: #7a828c; --info: #2b6fd6;
  --ok-bg: #e7f6ed;   --warning-bg: #fdf3d9; --high-bg: #fde9df; --critical-bg: #fbe5e5;
}
:root[data-theme="dark"] {
  --bg: #0f1216;      --surface: #171b21;   --text: #e6e9ed;   --muted: #98a2ad;  --border: #2a313a;
  --ok: #3ccf7a;      --warning: #f0b429;   --high: #ff8a50;   --critical: #ff5c5c;
  --unknown: #8b95a1; --info: #5c9dff;
  --ok-bg: #12301f;   --warning-bg: #3a2e0c; --high-bg: #3d2112; --critical-bg: #3d1616;
}
```

> Qiymatlar boshlang'ich; amalga oshirishda kontrast (matn ≥ 4.5:1, katta matn va grafik
> elementlari ≥ 3:1) avtomatik tekshiriladi (NFR-USA-003).

### 13.4.4. Grafik ranglari

- Bir grafikda ≤ 6 qator; ranglar rang ko'rlikka chidamli palitradan, qator nomi bilan legend.
- Chegara chiziqlari (warning/critical) — shtrixli, tegishli holat rangida, 40% shaffoflik.
- Ma'lumot yo'q oraliq (`null`) — ko'rinadigan bo'shliq (kulrang fon bilan "ma'lumot yo'q"),
  chiziq **tutashtirilmaydi**.

## 13.5. Maketlar (wireframe)

Quyidagi maketlar tuzilmani ko'rsatadi, vizual dizayn emas.

### 13.5.1. SCR-01 Dashboard (desktop)

```
┌─ Nazoratchi ─────────────[ Qidiruv: / ]───────── uz ▾  ☾  Jasur ▾ ─┐   yangilandi: 3 s oldin
│ ▣ Bosh   ▤ Serverlar   ▥ Loyihalar   ▦ Zaxiralar   ⚑ Incidentlar (2)   ⋯ Yana │
├──────────────────────────────────────────────────────────────────────────────────┤
│  ┌─────────────────────────────────────────────────────────────────────────────┐ │
│  │ ▲ Diqqat: 2 ta muammo ochiq                              [ Incidentlarga o'tish ] │
│  └─────────────────────────────────────────────────────────────────────────────┘ │
│                                                                                  │
│  ┌ Serverlar ───┐ ┌ Loyihalar ───┐ ┌ Zaxira ──────┐ ┌ Muddatlar ───────────────┐ │
│  │ 3 / 3 onlayn │ │ 9 sog'lom    │ │ 8 / 8 yangi  │ │ Sertifikat: 41 kun (eng  │ │
│  │ ● ● ▲        │ │ 0 muammo     │ │ Offsite: ✖   │ │ yaqin) · Domen: 118 kun  │ │
│  └──────────────┘ └──────────────┘ └──────────────┘ │ Drill: 6 muddati o'tgan  │ │
│                                                     └──────────────────────────┘ │
│  Ochiq incidentlar                                                               │
│  ┌──────────────────────────────────────────────────────────────────────────────┐ │
│  │ 🟡 Disk 7 kunda to'ladi · main-2 ( / )              40 daq oldin  [Qabul] [›] │ │
│  │ 🟡 Offsite zaxira sozlanmagan · main-2             3 kun oldin   [Qabul] [›] │ │
│  └──────────────────────────────────────────────────────────────────────────────┘ │
│  Serverlar                                                                       │
│  ┌──────────────────────────────────────────────────────────────────────────────┐ │
│  │ ● main-2   CPU 12% ▁▂▁▃▂  RAM 42% ▃▃▃▄▃  Disk 78% ▇▇▇▇█   uptime 4 k  v1.0.0 │ │
│  │ ● vmd208589 CPU  6% ▁▁▂▁▁  RAM 55% ▄▄▄▄▅  Disk 10% ▁▁▁▁▁   uptime 41 k        │ │
│  │ ● backup-1 CPU  1% ▁▁▁▁▁  RAM 18% ▂▂▂▂▂  Disk 31% ▃▃▃▃▃   uptime 12 k        │ │
│  └──────────────────────────────────────────────────────────────────────────────┘ │
│  Loyihalar                                                                       │
│  ┌ Nazar ● ┐ ┌ BiznesRadar ● ┐ ┌ avlo.ai ● ┐ ┌ lutfan_ai ▲ ┐ ┌ wmg ● ┐ ...        │
│  └─────────┘ └───────────────┘ └───────────┘ └─────────────┘ └───────┘             │
└──────────────────────────────────────────────────────────────────────────────────┘
```

Elementlar:
- **Banner** — butun sahifaning holati ("Hammasi joyida" yashil / "N ta muammo" ahamiyat rangida).
- **Xulosa kartochkalari** — serverlar, loyihalar, zaxira, muddatlar; har biri tegishli
  sahifaga havola.
- **Ochiq incidentlar** — eng og'ir tepada; tugmalar: Qabul, Ochish.
- **Serverlar jadvali** — qisqa grafiklar (sparkline, oxirgi 1 soat).
- **Loyiha kartochkalari** — holat rangi; muammo bo'lsa sababi bir qatorda.

### 13.5.2. SCR-03 Server sahifasi

```
┌ main-2 ● onlayn · 164.68.105.194 · Contabo · Ubuntu 24.04 · kernel 6.8.0-139 (yangi: -147 ▲ reboot kerak)
│ Uptime: 4 kun 3 soat · Agent v1.0.0 · oxirgi aloqa: 5 s oldin       [Pauza] [Texnik ish] [⋯]
├ Umumiy | Resurslar | Konteynerlar (14) | Servislar (5) | Fayl tizimi | Tarix ────────────────
│ Oraliq: [1s] [6s] [24s] [7k] [30k] [90k] [Maxsus]                    ☐ deploy belgilari
│
│ CPU (%)                                      │ RAM (%)
│ 100┤                                         │ 100┤
│  75┤                                         │  75┤
│  50┤        ╭╮                               │  50┤──────────────────────────
│  25┤  ──────╯╰────────────────  ─ ─ ─ 90 ─   │  25┤
│   0┴──────────────────────────────           │   0┴──────────────────────────
│     09:00      09:30      10:00              │     09:00      09:30      10:00
│
│ Disk /  78% (62.4 / 80 GB)  → 9.3 kunda to'ladi ▲       │ Tarmoq: ↓ 1.2 MB/s  ↑ 0.4 MB/s
│ ┌────────────────────────────────────────────┐          │
│ │ ███████████████████████████████░░░░░░░░░░░ │          │
│ └────────────────────────────────────────────┘          │
│
│ Ochiq incidentlar (1): 🟡 Disk 7 kunda to'ladi · 40 daq oldin
│ Ta'sirlangan loyihalar: Nazar, BiznesRadar, avlo.ai, lutfan_ai, wmg, ...
└──────────────────────────────────────────────────────────────────────────────────────────
```

Tablar:
- **Umumiy** — "hozirgi" ko'rsatkichlar, ochiq incidentlar, ta'sirlangan loyihalar, faktlar (OS, kernel, CPU, RAM).
- **Resurslar** — CPU (rejimlar bo'yicha), yuklama, RAM/swap, disk I/O, tarmoq grafiklari.
- **Konteynerlar** — jadval: nom, loyiha, holat, uptime, CPU, RAM, qayta ishga tushishlar, log hajmi; qatorni bosish → konteyner grafiklari.
- **Servislar** — systemd unitlar holati, qayta ishga tushishlar.
- **Fayl tizimi** — har mount: hajm, band, inode, bashorat.
- **Tarix** — host voqealari (reboot, kernel o'zgardi, agent yangilandi), incidentlar.

### 13.5.3. SCR-05 Loyiha sahifasi

```
┌ Nazar ● joyida · production · main-2 · Docker Compose                          [Sozlama] [⋯]
├ Holat | Domenlar | Konteynerlar | Zaxira | Incidentlar | Havolalar ───────────────────────
│ ┌ Domenlar ──────────────────────────────────────────────────────────────────────────┐
│ │ nazar.avlo.ai        ● 200  184 ms   TLS 41 k ●   DNS ● 164.68.105.194            │
│ │ app.beyondlinks.uz   ● 307  210 ms   TLS 63 k ●   DNS ● 164.68.105.194            │
│ └────────────────────────────────────────────────────────────────────────────────────┘
│ ┌ Konteynerlar (7) ──────────────────────────────────────────────────────────────────┐
│ │ ● db        postgres:16     ↑ 4 k   CPU 2%   RAM 310 MB                           │
│ │ ● redis     redis:7         ↑ 4 k   CPU 1%   RAM  22 MB                           │
│ │ ● web       nazar-web       ↑ 2 k   CPU 8%   RAM 420 MB   restart: 0              │
│ │ ● worker / worker-yandex / beat / frontend ...                                    │
│ └────────────────────────────────────────────────────────────────────────────────────┘
│ ┌ Zaxira ────────────────────────────────────────────────────────────────────────────┐
│ │ Oxirgi: 6 soat oldin · 48.3 MB · ✓ yaxlit · Offsite: ✖ sozlanmagan                │
│ │ Oxirgi drill: hech qachon ▲   [ Drill natijasini kiritish ]                       │
│ └────────────────────────────────────────────────────────────────────────────────────┘
│ Uptime (30 kun): 99.97%   ▇▇▇▇▇▇▇▇▇▇▇▇▇▇▇▇▇▇▇▇▇▇▇▇▇▇▇▇▇▇ (har kun — rangli blok)
└──────────────────────────────────────────────────────────────────────────────────────────
```

### 13.5.4. SCR-06 Zaxiralar jadvali

```
Zaxiralar                                              [ Faqat muammolilar ☐ ]   [ CSV ]
┌─────────────┬────────┬──────────┬────────┬─────┬─────────┬───────────────┬───────────────┐
│ Loyiha      │ Server │ Oxirgisi │ Hajm   │ Yaxl│ Offsite │ Oxirgi drill  │ Holat         │
├─────────────┼────────┼──────────┼────────┼─────┼─────────┼───────────────┼───────────────┤
│ BiznesRadar │ main-2 │ 6 s      │ 46 MB  │ ✓   │ ✖ yo'q  │ hech qachon   │ ▲ Diqqat      │
│ Nazar       │ main-2 │ 6 s      │ 12 MB  │ ✓   │ ✖ yo'q  │ hech qachon   │ ▲ Diqqat      │
│ lutfan_ai   │ main-2 │ 31 s     │ 8 MB   │ ✓   │ ✖ yo'q  │ hech qachon   │ ✖ Kechikdi    │
│ wmg         │ main-2 │ 6 s      │ 3 MB   │ ✓   │ ✖ yo'q  │ hech qachon   │ ▲ Diqqat      │
│ Nazoratchi     │ core-1 │ 2 s      │ 5 MB   │ ✓   │ ✓ mos   │ 12 kun        │ ● Joyida      │
└─────────────┴────────┴──────────┴────────┴─────┴─────────┴───────────────┴───────────────┘
Qatorni bosish → loyiha zaxira kartasi (SCR-07): so'nggi 30 run, hajm grafigi (anomaliya nuqtalari),
fayllar ro'yxati, offsite solishtirish, drill tarixi va "Drill natijasini kiritish" formasi.
```

### 13.5.5. SCR-08 Domenlar va sertifikatlar

```
Domenlar                                       Filtr: [ Hammasi ▾ ]  [ Muddati yaqin ☐ ]  [ DNS muammolari ☐ ]
┌──────────────────────┬─────────────┬──────────┬──────────────┬──────────────┬─────────────┐
│ Domen                │ Loyiha      │ HTTP     │ Sertifikat   │ DNS          │ Domen muddati│
├──────────────────────┼─────────────┼──────────┼──────────────┼──────────────┼─────────────┤
│ nazar.avlo.ai        │ Nazar       │ ● 200    │ 41 kun ●     │ ● mos        │ 118 kun     │
│ lutfanai.uz          │ lutfan_ai   │ ✖ ulanmadi│ ?           │ ▲ GCP        │ qo'lda ▲    │
│ asadbekashurov.uz    │ asadbek...  │ ● 200    │ 82 kun ●     │ ● mos        │ qo'lda ▲    │
└──────────────────────┴─────────────┴──────────┴──────────────┴──────────────┴─────────────┘
```

### 13.5.6. SCR-09 Domen sahifasi va kesib o'tish yordamchisi

```
lutfanai.uz · DNS provayder: (aniqlanadi) · nazorat: biz
┌ DNS holati ─────────────────────────────────────────────────────────────────────────────┐
│ Kutilgan IP: 164.68.105.194                                                             │
│  Resolver               Javob               Holat                                      │
│  NS (domen NS)          34.173.220.247      ✖ eski IP (yopilgan bulut)                  │
│  Google 8.8.8.8         34.173.220.247      ✖                                          │
│  Cloudflare 1.1.1.1     34.173.220.247      ✖                                          │
│  Quad9 9.9.9.9          34.173.220.247      ✖                                          │
└─────────────────────────────────────────────────────────────────────────────────────────┘
┌ Kesib o'tish yordamchisi ───────────────────────────────────────────────────────────────┐
│ 1) Oldindan tekshirish: yangi IP [164.68.105.194]   [ Tekshirish ]                      │
│    ✓ HTTPS 200 (Host: lutfanai.uz)   ✓ Sertifikat 54 kun  ✓ javob 190 ms              │
│    ✗ www.lutfanai.uz  — sertifikat yo'q (SAN da yo'q)                                   │
│ 2) DNS ni o'zgartiring (provayderda) → [ Kuzatishni boshlash ]                          │
│ 3) Tarqalish: 0/4 resolver yangi IP da   (Google keshini tozalash: dns.google/cache)    │
└─────────────────────────────────────────────────────────────────────────────────────────┘
```

### 13.5.7. SCR-11 Incident tafsiloti

```
🟠 Server o'chdi · main-2                                       Holat: Qabul qilingan (Jasur, 09:40)
Boshlanishi: 09:33 · Davomiyligi: 12 daqiqa (davom etmoqda) · Ahamiyat: critical
├ Vaqt chizig'i ─────────────────────────────────────────────────────────────────────────────
│ 09:33  Ochildi: Server o'chdi (AL-001)
│ 09:33  +6 ta alert bostirildi (sayt ishlamayapti ×3, konteynerlar ×14, zaxira)
│ 09:33  Telegram'ga yuborildi
│ 09:40  Jasur qabul qildi
│ 09:41  Izoh: "Contabo panelida restart berdim"
├ Ta'sirlangan ──────────────────────────────────────────────────────────────────────────────
│ Loyihalar: Nazar, BiznesRadar, avlo.ai, ...  ·  Domenlar: 14  ·  Konteynerlar: 14
├ Nima qilish kerak (RB-001) ────────────────────────────────────────────────────────────────
│ 1. Provayder panelida holat ... 2. VNC ... 3. Rescue ...   [ Runbook'ni to'liq ochish ]
├ Izoh yozish ───────────────────────────────────────────────────────────────────────────────
│ [____________________________________________]  [ Qo'shish ]   [ Sabab: ▾ ]   [ Yopish ]
```

### 13.5.8. Mobil dashboard (360–414 px)

```
┌─────────────────────────┐
│ ☰ Nazoratchi        🔔 2   │
├─────────────────────────┤
│ ▲ 2 ta muammo ochiq     │
│ ┌─────────────────────┐ │
│ │🟡 Disk 7 kunda to'l │ │
│ │ main-2 · 40 daq     │ │
│ │ [Qabul]   [Ochish]  │ │
│ └─────────────────────┘ │
│ ┌─────────────────────┐ │
│ │🟡 Offsite sozlanmagan│ │
│ │ main-2 · 3 kun      │ │
│ └─────────────────────┘ │
│ Serverlar               │
│ ● main-2    CPU 12% 78% │
│ ● vmd208589 CPU  6% 10% │
│ Loyihalar (9)       ›   │
│ Zaxira: 8/8 ✓           │
├─────────────────────────┤
│ ▣    ▤    ▥    ▦    ⚑2  │
└─────────────────────────┘
```

## 13.6. Komponentlar kutubxonasi

| Komponent | Vazifa | Asosiy xususiyatlar |
|---|---|---|
| `StatusBadge` | Holat belgisi | `status` (ok/warning/high/critical/unknown/paused/info), belgi + matn, `size` |
| `StatusDot` | Kichik nuqta | Rang + `aria-label` |
| `Sparkline` | Kichik grafik | 60 nuqtagacha, rang holatga qarab, tooltip yo'q (yengil) |
| `MetricChart` | Asosiy grafik | uPlot, vaqt oralig'i, chegara chiziqlari, deploy/incident belgilari, sinxron kursor |
| `TimeRangePicker` | Oraliq tanlash | Tezkor tugmalar + maxsus; URL bilan sinxron (`?range=24h`) |
| `DataTable` | Jadval | Saralash, filtr, sahifalash/virtualizatsiya, ustunlarni yashirish, CSV |
| `IncidentCard` | Incident kartochkasi | Ahamiyat, sarlavha, vaqt, tugmalar (Qabul, Ochish) |
| `ProjectCard` | Loyiha kartochkasi | Holat, sabab, domenlar soni |
| `UptimeBar` | Kunlik uptime chizig'i | 30/90 ta rangli blok, hover → kun, foiz |
| `GaugeBar` | Foizli ko'rsatkich | Disk/RAM; chegara belgilari; bashorat yozuvi |
| `CertBadge` | Sertifikat muddati | Qolgan kun, rang chegaralari 21/7/3 |
| `BackupStatus` | Zaxira holati | Yosh, hajm, yaxlitlik, offsite, drill |
| `FreshnessLabel` | Yangilik belgisi | "3 s oldin"; > 60 s bo'lsa sariq "eskirgan" |
| `ConfirmDialog` | Tasdiqlash | Xavfli amallar uchun, nima bo'lishini yozadi |
| `CommandBlock` | Buyruq ko'rsatish | Nusxalash tugmasi (o'rnatish buyrug'i, runbook buyruqlari) |
| `EmptyState` | Bo'sh holat | Tushuntirish + keyingi qadam tugmasi |

## 13.7. Grafiklar spetsifikatsiyasi

| Mavzu | Talab |
|---|---|
| Kutubxona | uPlot (tez, kichik); ko'p grafik (20+) bir sahifada ham tez |
| Vaqt o'qi | Foydalanuvchi vaqt zonasi; oraliqqa qarab belgilar (`09:00`, `22 okt`) |
| Qiymat o'qi | Birlik bilan (`%`, `GB`, `MB/s`); bayt birliklari avtomatik (KB/MB/GB, 1024 asosida) |
| Chegara chiziqlari | Tegishli alert qoidasi chegarasi (masalan, 90%) shtrixli |
| Bo'shliqlar | `null` nuqta — chiziq uziladi, "ma'lumot yo'q" fon |
| Hodisa belgilari | Incident (rangli vertikal polosa), reboot, deploy (F3) — vertikal chiziq + tooltip |
| Tooltip | Kursor ostidagi aniq vaqt va qiymat; birdan ko'p qator bo'lsa hammasi |
| Sinxron kursor | Bir sahifadagi grafiklarda kursor vaqti sinxron |
| Zoom | Sichqoncha bilan oraliq tanlash → yaqinlashtirish; "Qaytarish" tugmasi |
| Nuqtalar soni | ≤ 1 000 (API `max_points`); undan ko'p bo'lsa backend siyraklaydi |
| Ranglar | 13.4.4 |
| Aksessibilitet | Grafik ostida "ma'lumotlar jadvali" ochiladigan blok (ekran o'quvchi uchun) |
| Yangilanish | SSE/polling bilan so'nggi nuqta qo'shiladi, butun grafik qayta chizilmaydi |
| Yuklash holati | Skeleton; xato bo'lsa "Qayta urinish" tugmasi |

## 13.8. Interaktivlik va jonli yangilanish

- **SSE** (`/api/v1/stream`) — dashboard va server sahifasi uchun. Uzilsa, avtomatik qayta ulanish
  (eksponensial, 1→30 s); 3 xatodan keyin polling (5 s) va "Jonli yangilanish o'chiq" belgisi.
- **Ma'lumot keshi:** TanStack Query; `staleTime` 10 s (ro'yxatlar), 30 s (grafiklar); ekran
  qayta fokus olganda yangilanadi.
- **Optimistik amallar:** "Qabul qilaman" — darhol UI da o'zgaradi, xato bo'lsa qaytariladi va
  sababi ko'rsatiladi.
- **Klaviatura:** `/` — qidiruv; `g d` — dashboard; `g s` — serverlar; `g p` — loyihalar; `g i` —
  incidentlar; `?` — yorliqlar ro'yxati. Matn maydonida ishlamaydi.
- **URL — holat manbai:** filtrlar, vaqt oralig'i, tab URL'da (havolani ulashish mumkin).

## 13.9. Mobil moslashuv (NFR-USA-002)

> **S9:** mobil pastki panel 5 ustun: Bosh sahifa, Serverlar, Loyihalar, Incidentlar va "Yana" menyusi (Zaxiralar, Domenlar, Texnik ish, Sozlamalar); 8 bo'lim 360 px da 3 ustunga sig'maydi.

| Element | Desktop | Mobil (< 768 px) |
|---|---|---|
| Navigatsiya | Chap panel | Pastki panel (5 band) |
| Jadvallar | To'liq ustunlar | Kartochka ko'rinishi (asosiy 3–4 maydon), qolgani "Batafsil" |
| Grafiklar | 2 ustun | 1 ustun, kamroq nuqta, tooltip bosish bilan |
| Tugmalar | Oddiy | Kamida 44×44 px |
| Incident amallari | Satr ichida | Katta tugmalar, eng muhim — "Qabul qilaman" |
| Formalar | Ko'p ustunli | 1 ustun, to'g'ri klaviatura turi (`inputmode`) |

Gorizontal sahifa skroli bo'lmasligi shart (faqat keng jadvallar ichki skroll bilan).

## 13.10. Til va formatlash (i18n)

- Tillar: `uz` (standart, lotin), `ru`, `en`. Kalitlar `i18next` JSON fayllarida:
  `dashboard.banner.ok`, `incident.status.acknowledged`, ...
- Ko'plik shakllari: o'zbekchada son bilan birga birlik birlik shaklida ("3 server", "1 daqiqa");
  rus tilida to'liq plural qoidalari (`one/few/many`).
- **Son formati:** `uz` — bo'sh joy minglik ajratgich, vergul kasr (`12 345,6`); `en` — vergul/nuqta.
  `Intl.NumberFormat` ishlatiladi; qo'lda formatlash yo'q.
- **Sana/vaqt:** `Intl.DateTimeFormat`, zona `Asia/Tashkent` (sozlanadi); mutlaq format
  `2026-10-22 14:35`; nisbiy ("5 daqiqa oldin") — tooltip'da aniq vaqt.
- **Hajm birliklari:** `bayt, KB, MB, GB, TB` (1024). **Davomiylik:** "4 kun 3 soat", "12 daqiqa".
- **Imlo:** o'zbek lotin imlosining to'g'ri harflari (`o'`, `g'`, `sh`, `ch`, `ng`); tarjimalar
  lingvistik tekshiruvdan o'tadi. ASCII almashtirishlar (`o'` o'rniga `o`) qabul qilinmaydi.

## 13.11. Aksessibilitet (NFR-USA-003)

- Klaviatura bilan to'liq boshqarish; ko'rinadigan fokus halqasi.
- ARIA: holat belgilari `role="img"` + `aria-label` ("Holat: kritik"); jonli hududlar
  (`aria-live="polite"`) incident paydo bo'lganda.
- Rang yagona signal emas (13.4.1).
- Kontrast: matn ≥ 4.5:1; katta matn/grafik ≥ 3:1 (ikkala mavzuda).
- `prefers-reduced-motion` — animatsiyalar o'chiriladi.
- Matn kattalashtirish 200% gacha tartib buzilmaydi.

## 13.12. Bo'sh, yuklanish va xato holatlari

| Holat | Ko'rsatish |
|---|---|
| Birinchi ishga tushirish (serverlar yo'q) | "Hali server qo'shilmagan" + katta "Server qo'shish" tugmasi (UC-01) |
| Ma'lumot yuklanmoqda | Skeleton (kartochka/jadval shaklida) |
| Server yangi (hali ma'lumot yo'q) | "Birinchi ma'lumot kutilmoqda…" + o'rnatish buyrug'i qayta ko'rsatiladi |
| Ma'lumot eskirgan | Sariq "Ma'lumot N daqiqa oldin yangilangan" |
| API xatosi | Qisqa xabar + "Qayta urinish" + `request_id` (nusxalash) |
| Ruxsat yo'q (403) | "Bu bo'limni ko'rish uchun ruxsat yo'q" (rolni ko'rsatadi) |
| Filtr natijasiz | "Hech narsa topilmadi" + "Filtrni tozalash" |
| Aloqa yo'q (offline) | Yuqorida banner: "Internet aloqasi yo'q"; oxirgi keshdagi ma'lumot ko'rinadi |

## 13.13. Frontend texnik tafsilotlari

```
frontend/
  src/
    app/            # router, providerlar, layout
    features/       # dashboard, servers, projects, backups, domains, incidents, alerts, settings, auth
    components/     # umumiy komponentlar (13.6)
    api/            # OpenAPI dan avtomatik yaratilgan klient va tiplar (openapi-typescript)
    lib/            # format (Intl), vaqt, yordamchilar
    i18n/           # uz.json, ru.json, en.json
    styles/         # tokens.css (13.4.3), global
  tests/            # Vitest (birlik), Playwright (E2E)
```

| Mavzu | Qaror |
|---|---|
| Til | TypeScript (`strict`) |
| Router | React Router |
| Server holati | TanStack Query |
| UI holati | React konteksti / Zustand (kichik); Redux ishlatilmaydi |
| Stil | Tailwind CSS + CSS tokenlari |
| Grafiklar | uPlot (qoplama: `MetricChart`) |
| Formalar | React Hook Form + `zod` |
| API klient | `openapi-typescript` + `openapi-fetch`; sxema o'zgarsa CI tipni qayta yaratadi |
| Test | Vitest + Testing Library; Playwright E2E (asosiy oqimlar) |
| Byudjet | Boshlang'ich JS ≤ 400 KB (gzip), LCP ≤ 2.5 s (4G), CLS < 0.1 |
| Xavfsizlik | CSP bilan mos (inline skriptsiz); XSS: React escaping, `dangerouslySetInnerHTML` taqiqlangan |

## 13.14. Forma spetsifikatsiyalari (asosiylari)

### 13.14.1. Server qo'shish (SCR-17)

| Maydon | Tur | Majburiy | Tekshiruv |
|---|---|---|---|
| Nom | matn | ha | 2–40 belgi, noyob, harf/raqam/`-`/`_` |
| Provayder | tanlov/matn | yo'q | Contabo, Hetzner, GCP, … |
| Ommaviy IPv4 | matn | yo'q (agent aniqlaydi) | IPv4 formati |
| Rol | tanlov | yo'q | production, staging, backup, core |
| Teglar | teglar | yo'q | kichik harf, `-` |
| Izoh | matn | yo'q | ≤ 500 belgi |

Yuborilgandan keyin: o'rnatish buyrug'i (`CommandBlock`), "Birinchi aloqa kutilmoqda…"
(avtomatik, SSE) → ulangach "Ulandi ✓" va server sahifasiga o'tish tugmasi.

### 13.14.2. Loyiha qo'shish (SCR-18)

| Maydon | Tur | Majburiy | Tekshiruv |
|---|---|---|---|
| Nom | matn | ha | 2–60 |
| `slug` (`appctl` papka nomi) | matn | ha | `^[A-Za-z0-9_-]+$`, noyob |
| Tur | tanlov | ha | compose / systemd / static / other |
| Server(lar) + muhit | ko'p tanlov | ha | production/staging |
| Portlar | raqamlar | yo'q | 1024–65535, serverda band emas (FR-REG-010); "Keyingi bo'sh" tugmasi |
| Domenlar | ro'yxat | yo'q | FQDN; har biri uchun kutilgan IP (standart: serverning IP si), `primary` belgisi |
| Zaxira siyosati | blok | yo'q | Kunlik DB? haftalik fayl? offsite? (standart 10.4.1) |
| Avtomatik tekshiruvlar | belgi | — | HTTP + TLS + DNS (yoqilgan) |

### 13.14.3. Silence va texnik ish

Silence: moslash (server/loyiha/qoida/…), muddat (tezkor: 1 s, 4 s, 24 s, 7 k, maxsus), sabab
(majburiy). Maintenance: qamrov, boshlanish/tugash, sabab, "Nazorat ro'yxati" (12.9.8).

## 13.15. Mikromatn qo'llanmasi (o'zbekcha)

- Qisqa, aniq, buyruq maylida: "Saqlash", "Bekor qilish", "Qabul qilaman".
- Texnik atamalar o'zgarishsiz: `Docker`, `nginx`, `DNS`, `TLS`, `appctl`; qolgan so'zlar o'zbekcha:
  "zaxira nusxa" (backup), "sertifikat", "holat", "ogohlantirish".
- Xato xabari: nima bo'ldi + nima qilish ("Domen noto'g'ri kiritilgan. Misol: `example.uz`").
- Raqam va birlik orasida bo'shliq: "12 daqiqa", "46 MB", "78 %" emas — "78%" (foiz yopishiq).
- Tasdiqlash xabarida oqibat: "Token bekor qilinadi, agent ulana olmaydi. Davom etasizmi?"
- Salbiy emas, yo'naltiruvchi: "Server qo'shilmagan" emas, "Birinchi serveringizni qo'shing".

## 13.16. Qabul sinovlari (UI)

| № | Sinov | Kutilgan natija |
|---|---|---|
| T-UI-01 | Dashboard 5 soniya qoidasi: yangi odamga ko'rsatib, "hammasi joyidami?" deb so'rash | To'g'ri javob ≤ 5 s |
| T-UI-02 | 360 px kenglikda barcha asosiy ekranlar | Gorizontal skroll yo'q, tugmalar bosiladi |
| T-UI-03 | Qorong'i va yorug' mavzu kontrasti (axe) | Jiddiy xato yo'q |
| T-UI-04 | Klaviatura bilan Dashboard → Incident → Qabul qilish | Sichqonchasiz bajariladi |
| T-UI-05 | SSE uzish | Polling'ga o'tadi, belgi chiqadi, tiklanganda qaytadi |
| T-UI-06 | 20 grafik bir sahifada | Kadr tezligi ≥ 30 fps, o'lchov ≥ 2 s ichida yuklanadi |
| T-UI-07 | Til almashtirish uz/ru/en | Hamma matn o'zgaradi, qattiq yozilgan matn yo'q |
| T-UI-08 | Ma'lumot yo'q oraliq (agent o'chgan) | Grafikda bo'shliq, chiziq tutashmaydi |
| T-UI-09 | Cheklangan viewer | Faqat o'z loyihasi ko'rinadi (F3) |
| T-UI-10 | Eski ma'lumot (agent jim) | "Eskirgan" belgisi, qiymat "hozirgi" deb ko'rsatilmaydi |
