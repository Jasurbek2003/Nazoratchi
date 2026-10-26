## 18.7. Talablar sanog'i

Sonlar hujjat jadvallaridan skript bilan sanalgan (ID bo'yicha, takrorlanishsiz) va hujjat
nashriga qadar qayta tekshiriladi.

### 18.7.1. Ustuvorlik va bosqich bo'yicha

| | F1 | F2 | F3 | Jami |
|---|---|---|---|---|
| Funksional (FR) | 91 | 63 | 24 | **178** |
| Nofunksional (NFR) | 40 | 22 | 3 | **65** |
| **Jami talablar** | **131** | **85** | **27** | **243** |

| | M | S | C | Jami |
|---|---|---|---|---|
| Funksional (FR) | 95 | 59 | 24 | 178 |
| Nofunksional (NFR) | 47 | 15 | 3 | 65 |
| **Jami** | **142** | **74** | **27** | **243** |

### 18.7.2. Boshqa ro'yxatlar

| Ro'yxat | Soni | Qayerda |
|---|---|---|
| Foydalanuvchi hikoyalari (US) | 43 | 3.3 |
| Foydalanish stsenariylari (UC) | 12 | 3.4 |
| Alert qoidalari (AL) | 89 | 12.7 |
| Runbook'lar (RB) | 34 | 18.2 |
| Loyiha xavflari (R-101…R-123) | 23 | 17.7 |
| Joriy infratuzilma xavflari (R-001…R-009) | 9 | 2.8 |
| Arxitektura qarorlari (ADR) | 14 | 6.3 |
| Metrikalar (nomlangan; faktlarsiz) | ≈ 130 | 7.4 |
| Ma'lumotlar bazasi jadvallari | 32 (+ 3 agregat ko'rinish) | 8 |
| API endpointlari (metod + yo'l juftliklari) | 114 | 9 |
| Ekranlar (SCR) | 20 | 13.3 |
| Owner qarori kerak bo'lgan savollar | 11 | 17.11 |

### 18.7.3. Talablarni bosqichlarga o'tkazish qoidasi

- **F1 ga kiradi:** server/loyiha reyestri, agent (tizim, disk, tarmoq, Docker, systemd, zaxira,
  sertifikat), heartbeat, HTTP/TLS/DNS tekshiruvlari (asosiy), 32 ta alert (server o'chdi, resurslar,
  konteyner, sayt, sertifikat, DNS, zaxira, heartbeat, o'zini kuzatish), Telegram + ack, asosiy panel,
  watchdog, o'z zaxirasi, deploy va asosiy runbook'lar.
- **F2 ga kiradi:** 2FA, kengaytirilgan zaxira (yaxlitlik, offsite 2-daraja, drill), kesib o'tish
  yordamchisi, qoidalar UI, titrash/guruhlash, hisobotlar, ru/en, qorong'i mavzu, SSE, yangilanish.
- **F3 ga kiradi:** viewer cheklovi, status sahifa, ko'p lokatsiyali tekshiruv, avto-drill,
  eskalatsiya, qo'shimcha xavfsizlik metrikalari, supply-chain mustahkamlash.
