## 4.8. DNS — DNS va domen monitoringi

| ID | Talab | Ust. | Faza | Qabul mezoni |
|---|---|---|---|---|
| FR-DNS-001 | **A yozuvini tekshirish.** Har domen uchun A (va ixtiyoriy AAAA) yozuvi so'raladi va reyestrdagi kutilgan IP lar bilan solishtiriladi | M | F1 | `asadbekashurov.uz` → `173.249.37.152` mos deb ko'rinadi |
| FR-DNS-002 | **Ko'p resolver.** So'rov kamida 3 ommaviy resolverga (Google 8.8.8.8, Cloudflare 1.1.1.1, Quad9 9.9.9.9) va domenning o'z NS serveriga alohida yuboriladi; natijalar alohida ko'rsatiladi | M | F1 | Panelda har resolver javobi ko'rinadi |
| FR-DNS-003 | **Mos kelmaslik alerti.** Natija kutilgan IP dan boshqa bo'lsa va 10 daqiqa davomida o'zgarmasa (tarqalish vaqtidan keyin) — alert. Eski IP ga qaragan domen (masalan, o'chirilgan GCP `34.173.220.247`) alohida sabab sifatida ko'rsatiladi | M | F1 | `lutfanai.uz` hali GCP IP da bo'lsa alert chiqadi |
| FR-DNS-004 | **Boshqa yozuv turlari.** CNAME, MX, TXT (masalan, SPF), NS yozuvlari o'zgarishi kuzatiladi; kutilgan qiymat bo'lsa solishtiriladi | C | F3 | MX o'zgarsa voqea yoziladi |
| FR-DNS-005 | **Tarqalish (propagation) rejimi.** DNS o'zgartirilgandan keyin "kutish" rejimini yoqish: har 1 daqiqada tekshiradi va barcha resolverlar yangi IP ga o'tganda xabar beradi ("o'zgarish tarqaldi") | S | F2 | Rejim yoqilgach, Telegram'ga "hamma resolver yangi IP ga o'tdi" xabari keladi |
| FR-DNS-006 | **Domen muddati (WHOIS/RDAP).** Domenning ro'yxatdan o'tgan muddati tugash sanasi (RDAP orqali; `.uz` uchun qo'lda kiritish imkoniyati, chunki RDAP har doim mavjud emas); 60, 30, 14, 7 kun qolganda ogohlantirish | S | F2 | `.com` domen uchun avtomatik, `.uz` uchun qo'lda kiritilgan sana ishlaydi |
| FR-DNS-007 | **NS kuzatuvi.** Domenning NS yozuvlari (masalan, `rdns1.ahost.uz`) o'zgarsa voqea; reyestrdagi DNS provayder maydoni bilan solishtiriladi | C | F3 | NS o'zgarsa voqea yoziladi |
| FR-DNS-008 | **DNS o'zgarishlar tarixi.** Har domen uchun yozuvlar o'zgarish tarixi (qachon, nimadan nimaga) | S | F2 | `A: 34.173.220.247 → 164.68.105.194` yozuvi vaqt bilan ko'rinadi |
| FR-DNS-009 | **Kesib o'tishdan oldingi tekshiruv (cut-over yordamchisi).** DNS o'zgartirilishidan **oldin** domenni yangi IP ga to'g'ridan-to'g'ri (`Host` va SNI saqlangan holda) HTTPS bilan tekshirish: status, sertifikat (muddati, hostname mosligi), javob vaqti; natija "tayyor / tayyor emas (sabab)". `resolve_to` parametri orqali (11.4.4, 18.4.1) | S | F2 | Sertifikati yo'q serverga tekshiruv "sertifikat yo'q" sababi bilan rad etiladi; tayyor serverga "tayyor" deydi |

## 4.9. BKP — Zaxira nusxalar monitoringi

Zaxirani `appctl` oladi; Nazoratchi uni **kuzatadi va tekshiradi** (restore drill bundan
mustasno — u tiklash jarayonini qayd etadi, 10-bo'limga qarang).

| ID | Talab | Ust. | Faza | Qabul mezoni |
|---|---|---|---|---|
| FR-BKP-001 | **Zaxira papkasini skanerlash.** Agent har 5 daqiqada `<BACKUP_ROOT>/<loyiha>/{daily,weekly}` ni skanerlaydi: fayllar ro'yxati, nomi, hajmi, o'zgarish vaqti, soni | M | F1 | Yangi fayl paydo bo'lgach 5 daqiqada panelda ko'rinadi |
| FR-BKP-002 | **Oxirgi muvaffaqiyatli zaxira yoshi.** Har loyiha uchun eng yangi to'liq (`.tmp` bo'lmagan) kunlik fayl yoshi (soat) hisoblanadi | M | F1 | `BiznesRadar` uchun yosh soat aniqligida ko'rinadi |
| FR-BKP-003 | **Loyiha zaxira kartasi.** Loyiha sahifasida: oxirgi zaxira vaqti/hajmi, kunlik/haftalik soni, offsite holati, oxirgi restore drill, 30 kunlik hajm grafigi | M | F1 | Karta barcha elementlarni ko'rsatadi |
| FR-BKP-004 | **Kechikish alerti.** Yosh > 26 soat bo'lsa — yuqori ahamiyatli alert; > 50 soat — kritik | M | F1 | `appctl backup` to'xtatilsa 26 soatdan keyin alert |
| FR-BKP-005 | **Hajm anomaliyasi.** Yangi zaxira hajmi oldingi 7 ta zaxira medianasining 50% dan kam yoki 300% dan ko'p bo'lsa — "shubhali zaxira" alerti. Birinchi 7 kunda faqat ma'lumot | M | F1 | Bo'sh/yarim dump alertni ishga tushiradi |
| FR-BKP-006 | **Yaxlitlik tekshiruvi.** Agent eng yangi `.sql.gz` ni `gzip -t` bilan tekshiradi (kuniga 1 marta, oxirgi fayl); natija `ok/corrupt`; buzuq bo'lsa kritik | M | F2 | Kesilgan gz fayl "corrupt" deb belgilanadi |
| FR-BKP-007 | **Saqlash siyosati tekshiruvi.** Kunlik fayllar soni 7 dan, haftalik 5 dan oshmasligi (appctl tozalashi ishlayotganini bilish); oshsa — ma'lumot | S | F2 | Qo'lda 12 ta fayl qo'shilsa belgi chiqadi |
| FR-BKP-008 | **O'sish tendensiyasi.** Zaxira hajmining 90 kunlik o'sishi va zaxira papkasi diskka sig'ish bashorati | C | F3 | Grafik va "N kunda to'ladi" bashorati |
| FR-BKP-009 | **Haftalik fayl zaxirasi.** `BACKUP_PATHS` tar.gz fayllari haftada bir marta (yakshanba) chiqishi kerak; 8 kundan eski bo'lsa — ogohlantirish | S | F2 | Haftalik fayl yo'q bo'lsa alert |
| FR-BKP-010 | **Offsite sozlanganligi.** Reyestrdagi har serverda `OFFSITE` bo'sh bo'lsa, panelda "Offsite zaxira yo'q" doimiy ogohlantirish (yopiq bo'lmaydigan, silence qilinguncha) | M | F1 | Hozirgi S-01 uchun ogohlantirish ko'rinadi |
| FR-BKP-011 | **Offsite oxirgi sinxronlash.** Offsite serverdagi agent shu papkani skanerlaydi; core har loyiha uchun offsite'dagi eng yangi fayl vaqtini biladi | M | F2 | Offsite'ga fayl yetib borgach, 15 daqiqada panelda ko'rinadi |
| FR-BKP-012 | **Mahalliy va offsite solishtirish.** Eng yangi mahalliy fayl nomi va hajmi offsite'dagi bilan mos bo'lishi kerak | M | F2 | Farq bo'lsa "offsite orqada" belgisi |
| FR-BKP-013 | **Offsite alerti.** Offsite oxirgi sinxronlash > 26 soat — yuqori; > 50 soat — kritik | M | F2 | Rsync to'xtatilsa alert |
| FR-BKP-014 | **Offsite diskida joy.** Offsite serverning bo'sh joyi va zaxiralarning o'sishi; < 15% — ogohlantirish | S | F2 | Offsite agent diskni ko'rsatadi |
| FR-BKP-015 | **Restore drill rejasi.** Har loyiha uchun tiklash testi davriyligi (standart: chorakda 1 marta); muddati yaqinlashsa eslatma | S | F2 | 90 kundan keyin eslatma chiqadi |
| FR-BKP-016 | **Restore drill natijasini qayd etish.** Forma: sana, zaxira fayli, davomiyligi, tiklangan jadval/qator soni, natija (muvaffaqiyat/qisman/xato), izoh, bajargan shaxs | S | F1 | Natija saqlanadi va kartada ko'rinadi |
| FR-BKP-017 | **Restore drill muddati o'tdi alerti.** 100 kun o'tib hali muvaffaqiyatli drill bo'lmasa — ogohlantirish | S | F2 | Muddati o'tgan loyiha ro'yxatda belgilanadi |
| FR-BKP-018 | **Zaxira logini tahlil qilish.** `/var/log/appctl-backup.log` ning oxirgi bajarilishi: `XATO` qatorlari bo'lsa alert matnida oxirgi 10 qator ko'rsatiladi | S | F2 | Sun'iy `XATO` qatori alert matniga tushadi |
| FR-BKP-019 | **Dump mazmuni tekshiruvi.** Dump boshi (`head`) PostgreSQL dump belgilarini o'z ichiga olishi; (ixtiyoriy) `pg_restore --list` jadvallar soni | C | F3 | Bo'sh/yaroqsiz dump aniqlanadi |
| FR-BKP-020 | **Avtomatik restore drill (`appctl drill`).** Vaqtinchalik konteynerda (bir xil PostgreSQL asosiy versiyasi) dump tiklanadi, jadval/qator soni hisoblanadi, konteyner o'chiriladi, natija API orqali yuboriladi; ishlab turgan bazaga hech qachon tegmaydi (10.8.2, 10.8.6) | C | F3 | Drill natijasi kartada "avtomatik" belgisi bilan paydo bo'ladi; ishlab turgan baza o'zgarmagan |

## 4.10. ALR — Alert tizimi

Batafsil mexanika va qoidalar katalogi — 12-bo'limda.

| ID | Talab | Ust. | Faza | Qabul mezoni |
|---|---|---|---|---|
| FR-ALR-001 | **Qoida modeli.** Qoida: nom, qamrov (server/loyiha/tekshiruv/teg), shart, davomiylik (`for`), ahamiyat, kanallar, runbook, yoqilgan/o'chirilgan | M | F1 | Qoida yaratiladi va ishlaydi |
| FR-ALR-002 | **Shart turlari.** (a) chegara (`>`, `<`, `==`), (b) yo'qlik (`absent`, ma'lumot kelmayapti), (c) o'zgarish tezligi (rate), (d) bashorat (forecast), (e) holat o'tishi (healthy → unhealthy) | M | F1 | Har tur uchun test mavjud |
| FR-ALR-003 | **Davomiylik sharti.** Shart belgilangan vaqt davomida uzluksiz bajarilsa alert (masalan, CPU > 90% 10 daqiqa) | M | F1 | Qisqa sakrash alert bermaydi |
| FR-ALR-004 | **Ahamiyat darajalari.** `info`, `warning`, `high`, `critical`. Kanal va sokin soatlar ahamiyatga bog'liq | M | F1 | Har daraja o'z kanal qoidasiga amal qiladi |
| FR-ALR-005 | **"Server o'chdi" alerti.** Heartbeat 120 s kelmasa **va** tashqi TCP:22/ICMP tekshiruvi ham muvaffaqiyatsiz bo'lsa — `critical`; faqat heartbeat yo'q bo'lsa — `high` ("agent javob bermayapti") | M | F1 | Serverni o'chirib sinab ko'riladi: 2 daqiqada alert |
| FR-ALR-006 | **Standart qoidalar to'plami.** Tizim o'rnatilganda 12-bo'limdagi qoidalar (AL-001..AL-089) tayyor keladi; foydalanuvchi ularni o'chirishi yoki chegarasini o'zgartirishi mumkin | M | F1 | Toza o'rnatishda kamida F1 qoidalari yoqilgan |
| FR-ALR-007 | **Qoidalarni tahrirlash interfeysi.** Panelda qoida chegaralari va kanallarini o'zgartirish; o'zgarish audit jurnaliga yoziladi | S | F2 | Chegara o'zgartirilgach keyingi tekshiruvda qo'llanadi |
| FR-ALR-008 | **Disk to'lishi bashorati.** Bashorat < 7 kun — `warning`; < 24 soat yoki band ≥ 90% — `critical` | M | F1 | Sun'iy o'sishda alert |
| FR-ALR-009 | **Sekin javob alerti.** HTTP javob vaqti belgilangan chegaradan (standart 3 s) 5 daqiqa davomida oshsa — `warning` | S | F2 | `tc`/sun'iy kechikish bilan alert |
| FR-ALR-010 | **Crash loop alerti.** FR-DKR-004 asosida `high` | M | F1 | Sinov konteynerida alert |
| FR-ALR-011 | **Bostirish (suppression) va bog'liqlik.** Server `critical` "o'chdi" holatida bo'lsa, shu serverdagi servis/HTTP/zaxira alertlari alohida yuborilmaydi; ular incident ichida "ta'sirlangan" ro'yxati sifatida ko'rinadi | M | F1 | Server o'chganda 1 ta xabar keladi, 20 ta emas |
| FR-ALR-012 | **Jim qilish (silence).** Qamrov va muddat (15 daqiqa … 30 kun) bilan; sabab majburiy; muddati tugagach avtomatik o'chadi; audit jurnaliga yoziladi | M | F1 | Jim qilingan alert yuborilmaydi, muddatdan keyin qayta ishlaydi |
| FR-ALR-013 | **Qabul qilish (acknowledge).** Operator incident'ni qabul qiladi; takroriy eslatmalar to'xtaydi; kim va qachon qabul qilgani yoziladi | M | F1 | Telegram tugmasi va panel orqali ishlaydi |
| FR-ALR-014 | **Tiklandi bildirishnomasi.** Shart yo'qolsa incident yopiladi va "tiklandi" xabari davomiylik bilan yuboriladi | M | F1 | Xabarda "davomiyligi: 12 daqiqa" bor |
| FR-ALR-015 | **Eskalatsiya.** `critical` alert 15 daqiqa qabul qilinmasa, ikkinchi kontaktga/kanalga yuboriladi (kechikish sozlanadi) | C | F3 | Ikkinchi chat'ga xabar keladi |
| FR-ALR-016 | **Incident tarixi.** Har incident: boshlanishi, tugashi, davomiyligi, ahamiyati, ta'sirlangan obyektlar, ack, izohlar, sabab (qo'lda) | S | F2 | Ro'yxat va filtr ishlaydi |
| FR-ALR-017 | **Runbook havolasi.** Har qoidada runbook (RB-nnn) havolasi; Telegram xabarida ko'rinadi | S | F2 | Xabarda havola bor va ochiladi |
| FR-ALR-018 | **Titrashdan himoya (flapping).** Bir alert 1 soatda 5 martadan ko'p holat o'zgartirsa, "beqaror" deb belgilanadi va yig'ma xabar bilan almashadi; gisterezis (yoqish va o'chirish chegaralari farqli) | S | F2 | Titragan HTTP tekshiruvi 1 soatda ≤ 2 xabar beradi |
| FR-ALR-019 | **Guruhlash.** Bir vaqtning o'zida 3 va undan ko'p bog'liq alert bitta yig'ma xabarga birlashadi (60 soniya oynada) | S | F2 | Sinovda 10 alert 1–2 xabarga aylanadi |
| FR-ALR-020 | **Sinov alerti.** Panel tugmasi orqali kanalni tekshirish uchun sinov xabari yuborish | M | F1 | Tugma bosilganda Telegram'ga xabar keladi |

## 4.11. NTF — Bildirishnomalar

| ID | Talab | Ust. | Faza | Qabul mezoni |
|---|---|---|---|---|
| FR-NTF-001 | **Telegram kanali.** Bot orqali bir yoki bir nechta chatga (shaxsiy, guruh) xabar yuborish; bot tokeni maxfiy saqlanadi (shifrlangan) | M | F1 | Sinov xabari keladi |
| FR-NTF-002 | **Chuqur havola.** Har xabarda tegishli incident/obyekt sahifasiga havola | M | F1 | Havola brauzerda to'g'ri sahifani ochadi |
| FR-NTF-003 | **Xabar formati.** Ahamiyat belgisi (🔴/🟠/🟡/🔵), qisqa sarlavha, server/loyiha, qiymat va chegara, boshlanish vaqti (mahalliy zonada, Asia/Tashkent), runbook havolasi; xabar 1000 belgidan oshmaydi | M | F1 | Namuna xabarlar 12.9-bo'limga mos |
| FR-NTF-004 | **Qayta urinish va zaxira kanal.** Yuborish muvaffaqiyatsiz bo'lsa — eksponensial kutish bilan 5 marta; hali yetmasa — ikkinchi kanal (email); kanal ishlamayotgani panelda ko'rinadi | M | F1 | Telegram bloklanganda email ketadi |
| FR-NTF-005 | **Email kanali.** SMTP orqali (matn va HTML); `critical` va kunlik hisobot uchun | S | F2 | Email keladi |
| FR-NTF-006 | **Sokin soatlar.** Belgilangan vaqtda (masalan, 23:00–07:00) faqat `critical` darrov; qolganlari ertalabgacha yig'iladi va 07:00 da bitta xabar bo'ladi | S | F2 | Kechasi `warning` kelmaydi |
| FR-NTF-007 | **Webhook kanali.** Ixtiyoriy URL ga JSON POST (HMAC imzo bilan) | C | F3 | Sinov server webhookni oladi va imzoni tekshiradi |
| FR-NTF-008 | **Davriy hisobotlar.** Kunlik qisqa (08:00) va haftalik batafsil (dushanba 09:00): incidentlar, uptime, zaxira holati, sertifikat muddatlari, disk bashorati | S | F2 | Hisobot jadvalga ko'ra keladi |
| FR-NTF-009 | **Telegram tugmalari.** Xabarda "Qabul qilaman", "1 soat jim", "Panelda ochish" inline tugmalari; bosish faqat ruxsat etilgan chat ID lardan qabul qilinadi | S | F2 | Tugma bosilganda incident ack bo'ladi |

## 4.12. UI — Interfeys

Batafsil ekranlar va wireframe — 13-bo'limda.

| ID | Talab | Ust. | Faza | Qabul mezoni |
|---|---|---|---|---|
| FR-UI-001 | **Bosh sahifa (dashboard).** Umumiy holat bannerlari ("Hammasi joyida" / "N ta muammo"), serverlar va loyihalar soni, ochiq incidentlar, eng yaqin muddatlar (sertifikat, domen, drill) | M | F1 | Banner holati ochiq incidentlarga mos |
| FR-UI-002 | **Holat kartochkalari.** Har server va har loyiha uchun rangli holat (yashil/sariq/qizil/kulrang) va qisqa ko'rsatkichlar (CPU, RAM, disk) | M | F1 | Rang qoidalari 13.4 ga mos |
| FR-UI-003 | **Loyihalar ro'yxati.** FR-REG-004 ustunlari, filtr, qidiruv, saralash | M | F1 | 50 loyiha bilan tez ishlaydi |
| FR-UI-004 | **Serverlar ro'yxati.** Har server: holat, uptime, CPU/RAM/disk mini-grafiklar (sparkline), agent versiyasi, so'nggi aloqa | M | F1 | Ro'yxat 5 soniyada yangilanadi |
| FR-UI-005 | **Server sahifasi.** CPU, yuklama, RAM, swap, disk (hajm va I/O), tarmoq, konteynerlar, servislar, incidentlar bo'limlari; vaqt oralig'i (1 s, 6 s, 24 s, 7 k, 30 k, 90 k, maxsus) | M | F1 | Barcha grafiklar tanlangan oraliqda chiziladi |
| FR-UI-006 | **Loyiha sahifasi.** Domenlar, HTTP/TLS/DNS holati, konteynerlar/servislar, zaxira kartasi, incidentlar, havolalar | M | F1 | Barcha bo'limlar ko'rinadi |
| FR-UI-007 | **Eng yuklangan ro'yxati.** CPU/RAM/disk bo'yicha eng ko'p ishlatayotgan serverlar va konteynerlar | S | F2 | Ro'yxat ma'lumotga mos |
| FR-UI-008 | **Zaxiralar sahifasi.** Barcha loyihalar bo'yicha jadval: oxirgi zaxira, yoshi, hajmi, offsite holati, drill; qizil/sariq belgilash | M | F1 | `appctl backup all` dan keyin yangilanadi |
| FR-UI-009 | **Domenlar va sertifikatlar sahifasi.** Domen, qolgan kun (sertifikat, ro'yxat), DNS mosligi; muddati bo'yicha saralash | M | F1 | Eng yaqin muddat tepada |
| FR-UI-010 | **Incidentlar sahifasi.** Ochiq va yopilgan; filtr (ahamiyat, server, loyiha, vaqt); incident tafsiloti: vaqt chizig'i, ta'sirlanganlar, izohlar | M | F1 | Incident ochiladi va izoh qo'shiladi |
| FR-UI-011 | **Texnik ishlar sahifasi.** Maintenance oynalari yaratish/ko'rish (UC-08) va jim qilishlar ro'yxati | M | F1 | Oyna yaratilgach alertlar jim bo'ladi |
| FR-UI-012 | **Hisobotlar.** Oylik/chorak uptime, incident soni, MTTR, zaxira muvaffaqiyat foizi; CSV va PDF eksport | S | F2 | Hisobot sonlari ma'lumotga mos |
| FR-UI-013 | **Sozlamalar.** Kanallar, standart chegaralar, retention, foydalanuvchilar, tokenlar, vaqt zonasi, til | M | F1 | Sozlamalar saqlanadi |
| FR-UI-014 | **Qorong'i/yorug' mavzu.** Tizim sozlamasiga mos avtomatik va qo'lda almashtirish | S | F2 | Ikkala mavzuda kontrast WCAG AA |
| FR-UI-015 | **Global qidiruv.** Server, loyiha, domen, incident bo'yicha (`/` tugmasi) | C | F3 | "biznes" yozilganda BiznesRadar topiladi |
| FR-UI-016 | **Jonli yangilanish.** Dashboard va server sahifasi sahifani qayta yuklamasdan SSE orqali yangilanadi | S | F2 | Yangi ma'lumot 5 soniyada ko'rinadi |
| FR-UI-017 | **Maxsus oraliq va yaqinlashtirish.** Grafikda vaqt oralig'ini tanlab yaqinlashtirish, tooltip da aniq qiymat | S | F2 | Zoom ishlaydi |
| FR-UI-018 | **CSV eksport.** Har jadval va grafik ma'lumotini CSV qilish | C | F3 | Fayl to'g'ri ochiladi |
| FR-UI-019 | **Ommaviy holat sahifasi (status page).** Tanlangan loyihalar uchun avtorizatsiyasiz o'qiladigan sahifa (masalan, mijoz uchun) | C | F3 | Alohida URL, faqat tanlangan loyihalar |

## 4.13. AUTH — Autentifikatsiya va kirish

| ID | Talab | Ust. | Faza | Qabul mezoni |
|---|---|---|---|---|
| FR-AUTH-001 | **Kirish.** Email/login va parol; parollar `argon2id` bilan xeshlanadi | M | F1 | Noto'g'ri parol rad etiladi |
| FR-AUTH-002 | **Parol siyosati.** Kamida 12 belgi; mashhur parollar ro'yxatida bo'lmasligi | M | F1 | Zaif parol qabul qilinmaydi |
| FR-AUTH-003 | **Ikki bosqichli tasdiqlash (TOTP).** Authenticator ilovasi bilan; zaxira kodlari | S | F2 | TOTP bilan kirish ishlaydi |
| FR-AUTH-004 | **Sessiyalar.** Xavfsiz cookie (`HttpOnly`, `Secure`, `SameSite=Lax`), 12 soat harakatsizlik muddati; faol sessiyalar ro'yxati va "hammasidan chiqish" | M | F1 | Muddatdan keyin qayta kirish talab etiladi |
| FR-AUTH-005 | **Loyiha bo'yicha cheklangan viewer.** Viewer faqat biriktirilgan loyihalarni ko'radi (boshqa server/loyiha/incident yashirin) | C | F3 | Cheklangan viewer boshqa loyihani ko'rmaydi |
| FR-AUTH-006 | **Token boshqaruvi.** Agent tokenlari va API tokenlari: yaratish, nomlash, oxirgi ishlatilgan vaqt, bekor qilish; token faqat yaratilganda bir marta ko'rsatiladi, bazada faqat xesh | M | F1 | Bekor qilingan token bilan so'rov 401 |
| FR-AUTH-007 | **Kirishga urinishlar cheklovi.** 5 ta xato → 15 daqiqa blok (IP + hisob bo'yicha); barcha urinishlar audit jurnalida | M | F1 | 6-urinish rad etiladi |
| FR-AUTH-008 | **Parolni tiklash.** Telegram bot orqali bir martalik havola (egasining ruxsat etilgan chat ID siga) | C | F3 | Havola 15 daqiqa amal qiladi |

## 4.14. AUD — Audit jurnali

| ID | Talab | Ust. | Faza | Qabul mezoni |
|---|---|---|---|---|
| FR-AUD-001 | **Yoziladigan hodisalar.** Kirish/chiqish, rolga oid o'zgarish, obyekt yaratish/o'zgartirish/arxivlash, qoida o'zgarishi, silence/maintenance, token yaratish/bekor qilish, restore drill kiritish, sozlama o'zgarishi | M | F1 | Har hodisa jurnalda paydo bo'ladi |
| FR-AUD-002 | **Yozuv tarkibi.** Vaqt (UTC), foydalanuvchi, IP, amal turi, obyekt, eski va yangi qiymat (maxfiy maydonlar maskalanadi) | M | F1 | Parol/token qiymatlari jurnalda yo'q |
| FR-AUD-003 | **Ko'rish va filtr.** Faqat Owner; foydalanuvchi, amal, sana bo'yicha filtr | S | F2 | Filtr ishlaydi |
| FR-AUD-004 | **Saqlash va eksport.** Kamida 1 yil; jurnal faqat qo'shiladi (o'zgartirilmaydi/o'chirilmaydi); CSV eksport | S | F2 | UI/API orqali o'chirib bo'lmaydi |

## 4.15. INT — Integratsiyalar

| ID | Talab | Ust. | Faza | Qabul mezoni |
|---|---|---|---|---|
| FR-INT-001 | **`appctl list --json`.** Mavjud `appctl` ga JSON chiqarish rejimi qo'shiladi: loyiha, holat, konteynerlar soni; Nazoratchi agenti shu bilan loyiha holatini oladi | M | F1 | `appctl list --json \| jq .` xatosiz ishlaydi |
| FR-INT-002 | **`appctl status --json`.** Disk, xotira, konteynerlar, sertifikatlar (qolgan kun), oxirgi zaxira vaqtlari JSON formatda | M | F1 | Chiqish 18-bo'limdagi sxemaga mos |
| FR-INT-003 | **Zaxira holati fayli.** `appctl backup` oxirida `/opt/applications/backups/<loyiha>/state.json` yozadi: vaqt, natija (ok/fail), fayl nomi, hajm, davomiylik, xato matni (offsite natijasi `_run.json` da, 10.3.2). Agent shuni o'qiydi; papka skaneridan ishonchliroq | M | F1 | Zaxira muvaffaqiyatsiz bo'lsa `state.json` da `status: "fail"` va sabab bor |
| FR-INT-004 | **Docker API (faqat o'qish).** Agent Docker ma'lumotini `docker-socket-proxy` orqali oladi (`CONTAINERS=1`, `INFO=1`, `IMAGES=1`, `VOLUMES=1`; yozuvchi so'rovlar taqiqlangan) | M | F1 | Proksi POST so'rovlarini 403 bilan rad etadi |
| FR-INT-005 | **Kiruvchi heartbeat endpointi.** Har qanday cron/skript `curl https://<core>/hb/<token>` bilan "bajarildim" deb xabar bera oladi (muvaffaqiyat/xato parametri bilan) | M | F1 | Endpoint 200 qaytaradi, voqea yoziladi |
| FR-INT-006 | **Deploy belgilari.** `appctl deploy` yakunida core'ga "deploy" voqeasi yuboriladi (loyiha, versiya/commit, natija); grafiklarda vertikal chiziq sifatida ko'rinadi | C | F3 | Deploy'dan keyin grafikda belgi |

## 4.16. SYS — Tizimning o'zi

| ID | Talab | Ust. | Faza | Qabul mezoni |
|---|---|---|---|---|
| FR-SYS-001 | **O'z-o'zini kuzatish.** Core'ning o'z metrikalari: qabul qilish tezligi, navbat uzunligi, bazaga yozish kechikishi, alert hisoblash vaqti, xatolar soni | M | F1 | `/metrics` va panelda ko'rinadi |
| FR-SYS-002 | **Watchdog (alohida serverda).** Core har 60 soniyada S-01 dagi watchdog'ga ping yuboradi (3.1 P-5); 5 daqiqa kelmasa, watchdog mustaqil Telegram bot orqali xabar beradi. O'zaro kuzatuv: S-01 ni core (agent heartbeat) kuzatadi | M | F1 | Core to'xtatilsa 5–6 daqiqada xabar keladi |
| FR-SYS-003 | **O'z zaxirasi (Telegram orqali).** Nazoratchi bazasi (reyestr, incident, audit, kanal va qoida sozlamalari; metrikalarsiz) va sozlamalari kunlik zaxiralanadi, `age` bilan shifrlanadi va bot orqali **Owner'ning shaxsiy Telegram chatiga** (guruhga emas) fayl sifatida yuboriladi. Fayl 45 MB dan oshsa bo'laklanadi. Yuborish natijasi qayd etiladi; yuborilmasa alert. Zaxira o'zi ham FR-BKP qoidalariga bo'ysunadi | M | F1 | Chatda shifrlangan fayl bor; undan yangi serverda tiklash sinab ko'rilgan |
| FR-SYS-004 | **Saqlash muddati vazifasi.** Kunlik ish: xom ma'lumotlarni siyraklashtirish (downsampling) va muddati o'tganini o'chirish (8-bo'lim) | M | F1 | Bazada eski xom ma'lumot qolmaydi |
| FR-SYS-005 | **Sog'liq endpointi.** `/healthz` (baza va navbat tekshiruvi bilan), alohida `/readyz`; tashqi tekshiruvchi uchun | M | F1 | Baza o'chiq bo'lsa 503 |
| FR-SYS-006 | **Xavfsiz migratsiya.** Sxema o'zgarishlari orqaga qaytariladigan migratsiyalar bilan; yangilash vaqtida ma'lumot qabul qilish to'xtamaydi (agent buferi qoplaydi) | S | F2 | Yangilash paytida ma'lumot yo'qolmaydi |

## 4.17. Talablar xulosasi (jami)

| Modul | M | S | C | Jami |
|---|---|---|---|---|
| REG | 6 | 4 | 2 | 12 |
| HST | 8 | 6 | 3 | 17 |
| AGT | 10 | 4 | 0 | 14 |
| DKR | 3 | 5 | 2 | 10 |
| SVC | 3 | 2 | 1 | 6 |
| HTTP | 4 | 5 | 1 | 10 |
| TLS | 3 | 3 | 2 | 8 |
| DNS | 3 | 4 | 2 | 9 |
| BKP | 10 | 7 | 3 | 20 |
| ALR | 13 | 6 | 1 | 20 |
| NTF | 4 | 4 | 1 | 9 |
| UI | 11 | 5 | 3 | 19 |
| AUTH | 5 | 1 | 2 | 8 |
| AUD | 2 | 2 | 0 | 4 |
| INT | 5 | 0 | 1 | 6 |
| SYS | 5 | 1 | 0 | 6 |
| **Jami FR** | **95** | **59** | **24** | **178** |

Sonlar hujjat qismlaridan skript bilan sanalgan (har talab bir marta, takrorlanish yo'q).
Nofunksional talablar (5-bo'lim): 65 ta; umumiy sanoq va bosqichlar bo'yicha taqsimot — 18.7.
