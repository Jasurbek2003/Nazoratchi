# 3. Foydalanuvchilar, rollar va foydalanish stsenariylari

## 3.1. Foydalanuvchi turlari (personalar)

### P-1. Egasi (Owner) — "Jasurbek"

- Barcha loyihalarning egasi, ayni paytda DevOps ham o'zi.
- Kuniga bir necha marta telefondan (Telegram) va kompyuterdan panelga kiradi.
- Ehtiyoji: "Hammasi joyidami?" degan savolga 5 soniyada javob olish; muammo bo'lsa,
  nima qilishni darrov bilish; kechasi faqat haqiqiy muhim narsa uchun uyg'otilish.
- Texnik savodxonligi yuqori (Linux, Docker, nginx, Django), lekin vaqti kam.

### P-2. Operator

- Egasi ishonib topshirgan dasturchi yoki yordamchi.
- Incident'larni qabul qiladi (acknowledge), alertlarni jim qiladi, texnik ish oynalarini
  rejalashtiradi, reyestrga yangi loyiha qo'shadi.
- Serverga SSH orqali kira oladi, lekin Nazoratchi sozlamalarini (foydalanuvchilar, tokenlar) o'zgartira olmaydi.

### P-3. Kuzatuvchi (Viewer)

- Faqat o'qiydi: mijoz vakili yoki jamoa a'zosi. Masalan, wmg.uz mijozi o'z loyihasining
  holatini ko'radi.
- Hech narsani o'zgartira olmaydi; boshqa loyihalarni ko'rmaydi (loyiha bo'yicha cheklash, F2).

### P-4. Agent (mashina foydalanuvchi)

- Server tomonidagi dastur; faqat o'z hosti uchun ma'lumot yuboradi. Token bilan autentifikatsiya.

### P-5. Tashqi tekshiruvchi (Watchdog)

- Nazoratchi'ning o'zi ishlayotganini tashqaridan tekshiruvchi mustaqil xizmat.
  Nazoratchi tomonidan har 1 daqiqada heartbeat oladi; kelmasa Telegram'ga alohida xabar yuboradi.

## 3.2. Rollar va ruxsatlar matritsasi

Belgilar: ✔ — ruxsat; ✖ — taqiqlangan; (L) — faqat o'ziga biriktirilgan loyihalar.

| Amal | Owner | Operator | Viewer |
|---|---|---|---|
| Dashboard, grafiklar, ro'yxatlarni ko'rish | ✔ | ✔ | ✔ (L) |
| Incident'ni ko'rish | ✔ | ✔ | ✔ (L) |
| Incident'ni qabul qilish (ack) / izoh yozish | ✔ | ✔ | ✖ |
| Alertni jim qilish (silence) | ✔ | ✔ | ✖ |
| Maintenance window yaratish | ✔ | ✔ | ✖ |
| Host qo'shish / o'chirish | ✔ | ✔ (qo'shish) | ✖ |
| Agent tokenini yaratish / bekor qilish | ✔ | ✖ | ✖ |
| Loyiha / domen / servis qo'shish va tahrirlash | ✔ | ✔ | ✖ |
| Faol tekshiruv (HTTP/TCP/DNS) yaratish | ✔ | ✔ | ✖ |
| Alert qoidalarini yaratish / o'zgartirish | ✔ | ✔ (mavjudini sozlash) | ✖ |
| Bildirishnoma kanallarini sozlash | ✔ | ✖ | ✖ |
| Restore drill natijasini kiritish | ✔ | ✔ | ✖ |
| Foydalanuvchilarni boshqarish | ✔ | ✖ | ✖ |
| Audit jurnalini ko'rish | ✔ | ✖ | ✖ |
| Tizim sozlamalari, retention | ✔ | ✖ | ✖ |
| Hisobotlarni yuklab olish (CSV/PDF) | ✔ | ✔ | ✔ (L) |

## 3.3. Foydalanuvchi hikoyalari (User Stories)

Format: "Rol sifatida men ... xohlayman, shunda ...". Har hikoya talablarga bog'langan.

### 3.3.1. Umumiy ko'rinish

| ID | Hikoya | Ustuvorlik | Talablar |
|---|---|---|---|
| US-001 | Egasi sifatida men bosh sahifada barcha serverlar va loyihalarning umumiy holatini (yashil/sariq/qizil) bir qarashda ko'rishni xohlayman, shunda bir necha soniyada hammasi joyida ekanini bilaman | M | FR-UI-001, FR-UI-002 |
| US-002 | Egasi sifatida men har serverning CPU, RAM, disk va tarmoq grafiklarini oxirgi 1 soat / 24 soat / 7 kun / 30 kun uchun ko'rishni xohlayman | M | FR-HST-001..008, FR-UI-005 |
| US-003 | Egasi sifatida men barcha loyihalar ro'yxatini ko'rishni xohlayman: domen, server, port, holat, oxirgi zaxira, sertifikat muddati | M | FR-REG-001..004, FR-UI-003 |
| US-004 | Egasi sifatida men tizimni telefonda ham qulay ishlatishni xohlayman | S | NFR-USA-002 |
| US-005 | Egasi sifatida men interfeysni o'zbek tilida ko'rishni xohlayman | M | NFR-USA-001 |

### 3.3.2. Serverlar

| ID | Hikoya | Ustuvorlik | Talablar |
|---|---|---|---|
| US-006 | Operator sifatida men yangi serverni bitta buyruq bilan Nazoratchi'ga qo'shishni xohlayman | M | FR-AGT-001..003 |
| US-007 | Egasi sifatida men server o'chib qolsa 2 daqiqa ichida Telegram'da xabar olishni xohlayman | M | FR-ALR-005, FR-AGT-006 |
| US-008 | Egasi sifatida men disk 80% to'lganda va kunlar bo'yicha qachon to'lishini bashorat qilib xabar olishni xohlayman | M | FR-HST-005, FR-ALR-008 |
| US-009 | Operator sifatida men serverda kutilayotgan reboot (yangi kernel) borligini ko'rishni xohlayman | S | FR-HST-009 |
| US-010 | Egasi sifatida men RAM yoki CPU uzoq vaqt yuqori turgan serverni ko'rsatuvchi ro'yxatni xohlayman | S | FR-UI-007 |
| US-011 | Operator sifatida men SSH ga muvaffaqiyatsiz urinishlar sonini ko'rishni xohlayman, shunda bruteforce ni sezaman | C | FR-HST-014 |
| US-012 | Egasi sifatida men serverni vaqtincha kuzatuvdan to'xtatishni (pauza) xohlayman, masalan, ko'chirish paytida | M | FR-HST-016, FR-ALR-012 |

### 3.3.3. Loyihalar va servislar

| ID | Hikoya | Ustuvorlik | Talablar |
|---|---|---|---|
| US-013 | Egasi sifatida men har loyiha uchun saytning ishlayotganini (HTTP 200) tekshirishni xohlayman | M | FR-HTTP-001 |
| US-014 | Egasi sifatida men sayt javob vaqti sekinlashganini bilishni xohlayman | S | FR-HTTP-006, FR-ALR-009 |
| US-015 | Operator sifatida men qaysi Docker konteyner qayta-qayta ishga tushayotganini (crash loop) bilishni xohlayman | M | FR-DKR-004, FR-ALR-010 |
| US-016 | Operator sifatida men systemd servis (masalan, `avlo-contact`) to'xtasa xabar olishni xohlayman | M | FR-SVC-002 |
| US-017 | Egasi sifatida men yangi loyiha qo'shganda uni reyestrga bir formada kiritishni xohlayman | M | FR-REG-005 |
| US-018 | Egasi sifatida men eski serverdan hali ko'chirilmagan loyihalarni ham ro'yxatda ko'rishni xohlayman | S | FR-REG-007 |
| US-019 | Operator sifatida men kontainerning resurs sarfini (CPU/RAM) ko'rishni xohlayman | S | FR-DKR-003 |

### 3.3.4. Zaxira nusxalar

| ID | Hikoya | Ustuvorlik | Talablar |
|---|---|---|---|
| US-020 | Egasi sifatida men har loyihaning oxirgi muvaffaqiyatli zaxirasi qachon olinganini ko'rishni xohlayman | M | FR-BKP-001..003 |
| US-021 | Egasi sifatida men kunlik zaxira olinmasa yoki hajmi keskin kichraysa xabar olishni xohlayman | M | FR-BKP-004..006 |
| US-022 | Egasi sifatida men zaxiralar offsite (boshqa serverga) yetib borganini tasdiqlashni xohlayman | M | FR-BKP-010..013 |
| US-023 | Operator sifatida men zaxira tiklash testini (restore drill) rejalashtirib, natijasini qayd etishni xohlayman | S | FR-BKP-015..017 |
| US-024 | Egasi sifatida men zaxira hajmi o'sish tendensiyasini ko'rishni xohlayman | C | FR-BKP-008 |
| US-025 | Egasi sifatida men offsite serverdagi bo'sh joyni kuzatishni xohlayman | S | FR-BKP-014 |

### 3.3.5. Domen, DNS va sertifikat

| ID | Hikoya | Ustuvorlik | Talablar |
|---|---|---|---|
| US-026 | Egasi sifatida men har domen sertifikati tugashiga 21/7/3 kun qolganda xabar olishni xohlayman | M | FR-TLS-002, FR-TLS-003 |
| US-027 | Egasi sifatida men domen A yozuvi kutilgan IP dan boshqasiga qarab qolsa xabar olishni xohlayman | M | FR-DNS-001..003 |
| US-028 | Egasi sifatida men domen ro'yxatdan o'tgan muddati (WHOIS) tugashini kuzatishni xohlayman | S | FR-DNS-006 |
| US-029 | Operator sifatida men DNS o'zgartirilgandan keyin o'zgarish tarqalganini (propagation) bir nechta DNS serverdan tekshirishni xohlayman | C | FR-DNS-005 |
| US-030 | Egasi sifatida men certbot yangilanishi muvaffaqiyatsiz bo'lsa xabar olishni xohlayman | S | FR-TLS-006 |

### 3.3.6. Alertlar va incidentlar

| ID | Hikoya | Ustuvorlik | Talablar |
|---|---|---|---|
| US-031 | Egasi sifatida men alertni Telegram'da olishni va xabardan to'g'ridan-to'g'ri paneldagi incident sahifasiga o'tishni xohlayman | M | FR-NTF-001..003 |
| US-032 | Operator sifatida men alertni "qabul qildim" deb belgilashni xohlayman, shunda takroriy eslatma to'xtaydi | M | FR-ALR-013 |
| US-033 | Operator sifatida men ma'lum muammo uchun alertni belgilangan muddatga jim qilishni xohlayman | M | FR-ALR-012 |
| US-034 | Egasi sifatida men kechasi faqat "kritik" alertlar kelishini xohlayman (sokin soatlar) | S | FR-NTF-006 |
| US-035 | Egasi sifatida men muammo hal bo'lganda "tiklandi" xabarini olishni xohlayman | M | FR-ALR-014 |
| US-036 | Operator sifatida men har alertda "nima qilish kerak" (runbook) havolasini ko'rishni xohlayman | S | FR-ALR-017, 18-bo'lim |
| US-037 | Egasi sifatida men o'tgan oydagi incidentlar tarixini va ularning davomiyligini ko'rishni xohlayman | S | FR-ALR-016, FR-UI-012 |
| US-038 | Egasi sifatida men kritik alert 15 daqiqa qabul qilinmasa, ikkinchi shaxsga yuborilishini xohlayman | C | FR-ALR-015 |

### 3.3.7. Xavfsizlik va boshqaruv

| ID | Hikoya | Ustuvorlik | Talablar |
|---|---|---|---|
| US-039 | Egasi sifatida men tizimga faqat parol + ikki bosqichli tasdiqlash bilan kirishni xohlayman | S | FR-AUTH-003 |
| US-040 | Egasi sifatida men har bir agent uchun alohida token berishni va kerak bo'lsa bekor qilishni xohlayman | M | FR-AGT-002, FR-AUTH-006 |
| US-041 | Egasi sifatida men kim nimani o'zgartirganini audit jurnalidan ko'rishni xohlayman | S | FR-AUD-001..003 |
| US-042 | Egasi sifatida men mijozga faqat o'z loyihasini ko'rsatuvchi hisob berishni xohlayman | C | FR-AUTH-005 |
| US-043 | Egasi sifatida men Nazoratchi'ning o'zi o'chib qolsa xabar olishni xohlayman | M | FR-SYS-002 |

## 3.4. Foydalanish stsenariylari (Use Cases)

### UC-01. Yangi serverni qo'shish

- **Aktyor:** Operator / Owner.
- **Old shart:** Panelga kirilgan; yangi serverda root huquqi bor.
- **Asosiy oqim:**
  1. Panelda "Serverlar → Server qo'shish" bosiladi.
  2. Nom (masalan, `main-2`), provayder, rol va teglar kiritiladi.
  3. Tizim bir martalik **o'rnatish buyrug'ini** ko'rsatadi:
     `curl -fsSL https://<core>/install.sh | sudo bash -s -- --token <ENROLL_TOKEN>`.
  4. Operator buyruqni yangi serverda ishga tushiradi.
  5. Skript agent faylini yuklaydi, yagona imzoni tekshiradi, systemd unit yaratadi,
     bir martalik enroll tokenini doimiy agent tokeniga almashtiradi.
  6. Agent birinchi ma'lumotni yuboradi; panelda server "Yangi" holatidan "Onlayn" ga o'tadi.
  7. Tizim hostning OS/CPU/RAM/disk ma'lumotini avtomatik to'ldiradi.
- **Muqobil oqim:** Enroll tokeni 1 soatdan keyin eskiradi → panelda qayta yaratish.
- **Natija:** Server reyestrda, grafiklar chiza boshlaydi, standart alert qoidalari qo'llanadi.

### UC-02. Server o'chganda aniqlash va xabar berish

- **Aktyor:** Tizim → Owner.
- **Asosiy oqim:**
  1. Agent heartbeat 15 soniyada bir marta yuboradi.
  2. Markaziy server 120 soniya heartbeat olmasa, host holatini "Aloqa yo'q" qiladi.
  3. Tizim parallel ravishda hostning ommaviy IP siga ICMP/TCP:22 tekshiruvi bajaradi
     (agent muammosini server muammosidan ajratish uchun).
  4. Ikkala tekshiruv ham muvaffaqiyatsiz bo'lsa — "Server o'chdi" (kritik) alerti yaratiladi.
     Faqat agent jim bo'lsa — "Agent javob bermayapti" (ogohlantirish).
  5. Telegram'ga xabar: server nomi, oxirgi ko'rilgan vaqt, ta'sirlangan loyihalar ro'yxati,
     runbook RB-001 havolasi.
  6. Server qaytganda "Tiklandi" xabari va to'xtash davomiyligi yuboriladi.

### UC-03. Disk to'lishi haqida ogohlantirish

- **Aktyor:** Tizim → Owner/Operator.
- **Asosiy oqim:**
  1. Agent har 30 soniyada `/` bo'limi bandligini yuboradi.
  2. Markaziy server oxirgi 6 soatlik chiziqli regressiya bilan to'lish vaqtini bashorat qiladi.
  3. Bashorat 7 kundan kam bo'lsa — ogohlantirish; 24 soatdan kam yoki bandlik ≥ 90% bo'lsa — kritik.
  4. Xabarda: bandlik, o'sish tezligi (GB/kun), eng katta papkalar (agent "top-N" ma'lumoti, F2).
  5. Runbook RB-004: `docker system df`, log tozalash, eski image'lar.

### UC-04. Zaxira muvaffaqiyatsiz bo'lganini aniqlash

- **Aktyor:** Tizim → Owner.
- **Old shart:** Agent zaxira papkasini kuzatadi.
- **Asosiy oqim:**
  1. Agent har 5 daqiqada `/opt/applications/backups/*/daily` ni skanerlaydi: eng yangi fayl vaqti, hajmi, soni.
  2. Markaziy server har loyiha uchun "oxirgi zaxira yoshi" ni hisoblaydi.
  3. Yosh > 26 soat bo'lsa — "Zaxira kechikdi" alerti.
  4. Yangi fayl hajmi oldingi 7 kun medianasining 50% dan kam bo'lsa — "Zaxira shubhali" alerti.
  5. Xabarda: loyiha, oxirgi muvaffaqiyatli zaxira, `/var/log/appctl-backup.log` dan oxirgi 10 qator.

### UC-05. Offsite zaxira tekshiruvi

- **Aktyor:** Tizim → Owner.
- **Asosiy oqim:**
  1. Offsite zaxira S-00 da (core bilan bir serverda); S-00 dagi agent ham o'rnatilgan.
  2. Agent offsite papkani (`/srv/backups/main-server`) kuzatadi.
  3. Markaziy server mahalliy (S-01) va offsite (S-00) ro'yxatlarini solishtiradi:
     oxirgi fayl nomi va hajmi mos kelishi kerak.
  4. Farq 26 soatdan oshsa — "Offsite sinxronlash to'xtadi" alerti.

### UC-06. Sertifikat muddati yaqinlashishi

- **Aktyor:** Tizim → Owner.
- **Asosiy oqim:**
  1. Markaziy server har 6 soatda domenga TLS ulanib `notAfter` ni o'qiydi.
  2. 21 kun qolsa — ogohlantirish; 7 kun — yuqori; 3 kun — kritik.
  3. Xabarda: domen, server, sertifikat chiqaruvchi, ehtimoliy sabab (certbot log yoki
     DNS o'zgargani) va runbook RB-006.

### UC-07. Domen noto'g'ri IP ga qarab qolishi

- **Aktyor:** Tizim → Owner.
- **Asosiy oqim:**
  1. Reyestrda `asadbekashurov.uz` uchun kutilgan IP: `173.249.37.152`.
  2. Tizim har 5 daqiqada bir nechta ommaviy DNS (8.8.8.8, 1.1.1.1, 9.9.9.9) va domenning
     o'z NS serveridan A yozuvini so'raydi.
  3. Natija kutilgan IP ga mos kelmasa va 10 daqiqadan beri o'zgarmasa — "DNS mos emas" alerti.
  4. Qisqa farq (propagation) bo'lsa, "ehtimoliy tarqalish" belgisi bilan ogohlantirishsiz.

### UC-08. Texnik ish oynasi (maintenance)

- **Aktyor:** Operator.
- **Asosiy oqim:**
  1. "Texnik ish" yaratiladi: qamrov (server yoki loyiha), boshlanish va tugash vaqti, sabab.
  2. Shu vaqt davomida qamrovdagi alertlar yuborilmaydi, lekin yig'iladi (jim rejim).
  3. Oyna tugagach, hali yechilmagan alertlar bo'lsa, ular yuboriladi.
  4. Davomiylik hisobotlarida bu vaqt "rejalashtirilgan to'xtash" deb alohida hisoblanadi.

### UC-09. Incident bilan ishlash

- **Aktyor:** Operator.
- **Asosiy oqim:**
  1. Telegram'dagi xabardagi tugma: "Qabul qilaman" (ack).
  2. Incident holati "Qabul qilingan" ga o'tadi, takroriy eslatma to'xtaydi.
  3. Operator panelda izoh yozadi ("nginx konfigini tuzatdim").
  4. Shart yo'qolgach, incident avtomatik "Yechildi" bo'ladi; tizim davomiylikni hisoblaydi.
  5. Haftalik hisobotga qo'shiladi.

### UC-10. Yangi loyiha qo'shish

- **Aktyor:** Operator / Owner.
- **Asosiy oqim:**
  1. "Loyihalar → Qo'shish": nom, server, domenlar, portlar, turi (compose/systemd/static).
  2. Tizim domen uchun avtomatik HTTP, TLS va DNS tekshiruvlarini taklif qiladi.
  3. Docker compose loyihasi bo'lsa, agent loyiha nomi bo'yicha konteynerlarni bog'laydi.
  4. Zaxira papkasi nomi ko'rsatiladi; tizim mos qoidalarni qo'llaydi.
  5. Reyestr yangilanadi; loyiha kartasi paydo bo'ladi.

### UC-11. Restore drill (tiklash testi)

- **Aktyor:** Operator.
- **Asosiy oqim:**
  1. Panel chorakda bir marta eslatadi: "BiznesRadar tiklash testi muddati o'tdi".
  2. Operator test serverda (yoki vaqtinchalik konteynerda) `appctl restore` ni sinab ko'radi.
  3. Panelda natija kiritiladi: sana, zaxira fayli, davomiyligi, jadvallar soni, qator soni, muvaffaqiyat/xato, izoh.
  4. Tizim "oxirgi muvaffaqiyatli restore" sanasini loyiha kartasida ko'rsatadi.

### UC-12. Nazoratchi'ning o'zi o'chganda

- **Aktyor:** Watchdog → Owner.
- **Asosiy oqim:**
  1. Nazoratchi har daqiqada watchdog xizmatiga "ping" yuboradi.
  2. 5 daqiqa ping kelmasa, watchdog Telegram orqali (Nazoratchi botidan boshqa botdan) xabar yuboradi.
  3. Xabarda: "Nazoratchi ishlamayapti", oxirgi ping vaqti, runbook RB-012.

## 3.5. Stsenariylarga bog'liq o'zgarmas qoidalar

1. Alert hech qachon "jimgina" yo'qolmasligi kerak: kanal xatosi bo'lsa, qayta urinish va
   ikkinchi kanalga o'tish (FR-NTF-004).
2. Hostning o'zi o'chganda, uning ichidagi barcha servislar uchun alohida alertlar yuborilmaydi
   (bostirish, "suppression"): bitta "Server o'chdi" incident'i yetarli (FR-ALR-011).
3. Agent yig'ilgan ma'lumotni yuborib bo'lmasa, 15 daqiqagacha mahalliy buferda saqlaydi
   va aloqa tiklangach yuboradi (FR-AGT-007).
4. Foydalanuvchi interfeysida hech qachon parol, token yoki `.env` qiymati ko'rsatilmaydi.
