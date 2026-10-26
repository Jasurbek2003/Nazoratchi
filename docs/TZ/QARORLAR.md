# Owner qarorlari (TZ 17.11 savollariga javoblar)

Sana: 2026-10-26. Manba: TZ 17.11 (Q-01…Q-14). TZ matni shu qarorlarga moslashtirilgan (v1.2);
nomuvofiqlik chiqsa, shu fayl ustun.

| № | Savol | Qaror | TZ ga ta'siri |
|---|---|---|---|
| Q-01 | Qurish yoki tayyor yechim | To'liq F0 → F1 → F2 → F3 (F1-lite shart emas) | ROADMAP.md |
| Q-02 | Core qayerda | **S-00 (`185.214.135.9`)**, Contabo, 200 GB SSD, tozalanib qayta o'rnatiladi | 6.6.1, 15.2, 15.7, 15.8, 17, seed |
| Q-03 | Agent tili | Go (F0 da Python prototip) | O'zgarish yo'q |
| Q-04 | Telegram | Guruh, 2 kishi | O'zgarish yo'q |
| Q-05 | Domen | `nazoratchi.avlo.ai` (tasdiqlanadi) | |
| Q-06 | Loyiha nomi | **Nazoratchi** (oldingi "Qarovul") | Butun TZ, `nazoratchi-agent`, `/etc/nazoratchi`, `NAZORATCHI_MASTER_KEY`, `nzr_` |
| Q-07 | Offsite | **S-03 ishlatilmaydi.** S-01 zaxiralari S-00 ga (`/srv/backups/main-server`) | 10.6.3, FR-BKP-010…014, seed |
| Q-08 | `appctl` o'zgartirish | Ha, ehtiyotkorlik bilan (R-109 chorasi) | O'zgarish yo'q |
| Q-09 | Mijozlarga holat ko'rsatish | Berilmadi; TZ standarti: F3 (status sahifa) | |
| Q-10 | S-02 ga agent | Server ham, repo ham egasida; ruxsat kerak emas | R-114 chorasi (nginx.conf) saqlanadi |
| Q-11 | S-01 kernel -147 reboot | Hozircha reboot qilinmaydi | AL-032/AL-033 eslatib turadi |
| Q-12 | GCP IP `34.173.220.247` | **Mavjud emas** (o'chirilgan). `retired_ips = [34.173.220.247]` | 11.4.2, 18.4.4, 18.5, `.env`. `lutfanai.uz`, `lutfan.israilov.uz`, `*.wmg.uz` DNS yangilanishi kerak |
| Q-13 | Nazoratchi o'z zaxirasi qayerda | `age` bilan shifrlanib **Owner'ning shaxsiy Telegram chatiga** (bot orqali) yuboriladi | FR-SYS-003, NFR-SEC-010 (C/F3 → M/F1), 14.10, 15.9, RB-044 |
| Q-14 | Watchdog | **S-01 da** (tashqi xizmat emas). S-00 va S-01 bir-birini kuzatadi | ADR-014, FR-SYS-002, 6.2, 6.6.1, 15.13 |

## Qabul qilingan xavflar

1. **S-00 va S-01 bir provayderda (Contabo), RS-06.** Ikkalasi bir vaqtda tushsa, hech kim xabar bermaydi.
   Bitta server tushsa, ikkinchisi xabar beradi. Qo'shimcha tashqi xizmat ixtiyoriy.
2. **O'z zaxirasi Telegram'da (RS-07).** Bot API fayl chegarasi 50 MB (bo'laklanadi, metrikalar zaxiraga
   kirmaydi); Telegram yoki Owner hisobi yo'qolsa zaxira yo'qoladi; `age` maxfiy kaliti yo'qolsa fayl
   ochilmaydi. Chat o'chirilmasligi va kalit parol menejerida saqlanishi shart.
3. **Core, S-01 offsite nusxasi bilan bir serverda.** S-01 zaxiralari S-01 da ham qoladi, shuning uchun
   ikkala server yo'qolmasa ma'lumot saqlanadi.
4. **S-00 oldin yuklanmagan** (sababi aniqlanmagan, 1.3.1). Qayta o'rnatishdan keyin darhol snapshot.
5. **Kernel -147 kutmoqda (S-01).** Kutilmagan reboot bo'lsa yuklanmasligi mumkin (R-002).
6. **S-01 ga ortiqcha yuk.** U ishchi loyihalar va watchdog'ni olib yuradi; watchdog juda yengil bo'lishi kerak.

## Boshqa o'zgarishlar

- **imraninc.com** boshqa odamlarga tegishli, Nazoratchi loyihasi emas: reyestr, inventar, tekshiruv
  to'plami va namunalardan olib tashlangan. Ishlayotgan loyihalar 8 dan 7 ga tushdi.
- **GCP o'chirilgani oqibati:** `lutfanai.uz`, `lutfan.israilov.uz` va `*.wmg.uz` hozir mavjud bo'lmagan IP ga
  qaraydi, ya'ni ishlamayapti. DNS ni S-01 (`164.68.105.194`) ga yo'naltirish kerak (`*.wmg.uz` — mijoz
  nazoratida). `avloai.uz` ham `185.214.135.9` (core) ga qaraydi, uni ham ko'chirish kerak.

## S-00 ni core qilishdan oldingi ishlar

- Core nginx'ida `default_server` `return 444` (S-00 IP siga qaragan begona domenlar panelga tushmasin).
- Offsite papka: alohida foydalanuvchi, `rrsync` bilan faqat shu papkaga yozish (10.6.3).
- Docker log limiti va `unattended-upgrades` (avtomatik reboot **o'chiq**) 15.2.2 bo'yicha.
- Contabo snapshot (qayta o'rnatishdan keyin va keyin kunlik).
