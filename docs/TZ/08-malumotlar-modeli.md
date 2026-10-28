# 8. Ma'lumotlar modeli

## 8.1. Umumiy tamoyillar

1. **Identifikatorlar.** Reyestr va holat jadvallarida `uuid` (v7, vaqt bo'yicha tartiblangan);
   vaqt qatorlarida ixcham `bigint`. API da UUID satr ko'rinishida.
2. **Vaqt.** Hamma vaqt `timestamptz` (UTC).
3. **Yumshoq o'chirish.** Reyestr obyektlari o'chirilmaydi: `status = 'archived'` (FR-REG-006).
4. **Qattiq cheklovlar.** `NOT NULL`, `CHECK`, `UNIQUE`, `FOREIGN KEY` bazada, faqat kodda emas.
5. **JSONB** faqat haqiqatan o'zgaruvchan tuzilma uchun (`facts`, `config`, `labels`); qidiriladigan
   maydonlar alohida ustun.
6. **Maxfiy maydonlar** (`*_enc`) ilova darajasida AES-256-GCM bilan shifrlangan `bytea`.
7. **Nomlash.** Jadvallar — ko'plik, `snake_case`; tashqi kalit — `<obyekt>_id`.

## 8.2. Mantiqiy (ER) diagramma

```
 users ─┬──< user_projects >──┐
        │                      │
        └──< audit_log         ▼
                          projects ──< project_servers >── servers ──< agent_tokens
                             │  │                              │  │
                             │  └──< domains ──< dns_results   │  └──< series ──< metric_samples
                             │        │  └──< dns_changes      │          │ └─ series_latest
                             │        └──< cert_status         │          └─ metric_1m/5m/1h (caggs)
                             │        └── domain_whois         │
                             ├──< probes ──< probe_results     ├──< host_events
                             │                                  └──< backup_snapshots
                             ├──< backup_runs                       (host×project×kind)
                             ├──< restore_drills
                             └──< heartbeat_jobs

 alert_rules ──< alert_instances >── incidents ──< incident_events
                                          │
                    silences, maintenance_windows (scope bo'yicha moslik)
                                          │
                  channels ──< notifications >┘
```

## 8.3. Reyestr jadvallari

> **Yaratish tartibi.** Quyidagi DDL o'qish qulayligi uchun mavzu bo'yicha guruhlangan. Amalda
> Django migratsiyalari bog'liqlik tartibini o'zi hal qiladi; qo'lda bajarilsa tartib:
> `users` (8.8) → `servers` → `projects` → `project_servers` → `domains` → qolganlari.

```sql
CREATE EXTENSION IF NOT EXISTS timescaledb;
CREATE EXTENSION IF NOT EXISTS pgcrypto;   -- gen_random_uuid()

CREATE TABLE servers (
  id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  name             text NOT NULL UNIQUE,
  provider         text,
  public_ipv4      inet,
  public_ipv6      inet,
  role             text,
  tags             text[] NOT NULL DEFAULT '{}',
  location         text,
  monthly_cost_usd numeric(8,2),
  notes            text NOT NULL DEFAULT '',
  status           text NOT NULL DEFAULT 'new'
                   CHECK (status IN ('new','online','offline','paused','archived')),
  last_seen_at     timestamptz,
  paused_at        timestamptz,
  paused_by        uuid REFERENCES users(id),
  agent_version    text,
  facts            jsonb NOT NULL DEFAULT '{}',
  created_at       timestamptz NOT NULL DEFAULT now(),
  updated_at       timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE projects (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  slug          text NOT NULL UNIQUE CHECK (slug ~ '^[a-zA-Z0-9_-]+$'), -- appctl papka nomi
  name          text NOT NULL,
  description   text NOT NULL DEFAULT '',
  owner_name    text,                -- mijoz/mas'ul
  owner_contact text,
  kind          text NOT NULL CHECK (kind IN ('compose','systemd','static','other')),
  moved         boolean NOT NULL DEFAULT true,   -- false = "ko'chirilmagan"
  status        text NOT NULL DEFAULT 'active' CHECK (status IN ('active','archived')),
  tags          text[] NOT NULL DEFAULT '{}',
  links         jsonb NOT NULL DEFAULT '[]',     -- [{label,url}]
  notes         text NOT NULL DEFAULT '',
  created_at    timestamptz NOT NULL DEFAULT now(),
  updated_at    timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE project_servers (
  project_id  uuid NOT NULL REFERENCES projects(id),
  server_id   uuid NOT NULL REFERENCES servers(id),
  environment text NOT NULL DEFAULT 'production'
              CHECK (environment IN ('production','staging','dev')),
  ports       int[] NOT NULL DEFAULT '{}',      -- 127.0.0.1 portlar (backend/frontend)
  PRIMARY KEY (project_id, server_id, environment)
);
-- Bir serverda bir xil port ikki loyihaga berilmasligi (FR-REG-010) — ilova darajasida tekshiriladi.

CREATE TABLE domains (
  id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id     uuid REFERENCES projects(id),
  fqdn           text NOT NULL UNIQUE CHECK (fqdn = lower(fqdn)),
  expected_ips   inet[] NOT NULL DEFAULT '{}',  -- DNS mosligi uchun
  dns_provider   text,                          -- 'ahost.uz', 'Namecheap', 'Beget', ...
  registrar      text,
  controlled_by  text NOT NULL DEFAULT 'self' CHECK (controlled_by IN ('self','client','other')),
  tls_enabled    boolean NOT NULL DEFAULT true,
  status         text NOT NULL DEFAULT 'active' CHECK (status IN ('active','archived')),
  notes          text NOT NULL DEFAULT '',
  created_at     timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX domains_project_idx ON domains(project_id);

CREATE TABLE agent_tokens (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  server_id     uuid NOT NULL REFERENCES servers(id),
  name          text NOT NULL,
  token_hash    bytea NOT NULL UNIQUE,   -- SHA-256(token)
  created_at    timestamptz NOT NULL DEFAULT now(),
  created_by    uuid REFERENCES users(id),
  last_used_at  timestamptz,
  last_used_ip  inet,
  revoked_at    timestamptz
);
CREATE INDEX agent_tokens_server_idx ON agent_tokens(server_id) WHERE revoked_at IS NULL;

CREATE TABLE enroll_tokens (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  token_hash  bytea NOT NULL UNIQUE,
  server_id   uuid NOT NULL REFERENCES servers(id),
  expires_at  timestamptz NOT NULL,
  used_at     timestamptz,
  created_by  uuid REFERENCES users(id)
);

CREATE TABLE host_events (          -- reboot, kernel o'zgardi, agent yangilandi, ...
  id         bigserial PRIMARY KEY,
  server_id  uuid NOT NULL REFERENCES servers(id),
  time       timestamptz NOT NULL DEFAULT now(),
  type       text NOT NULL,         -- 'reboot','fact_changed','agent_updated','enrolled','paused','resumed'
  data       jsonb NOT NULL DEFAULT '{}'
);
CREATE INDEX host_events_idx ON host_events(server_id, time DESC);
```

## 8.4. Vaqt qatorlari

### 8.4.1. Series va namunalar

```sql
CREATE TABLE series (
  id          bigserial PRIMARY KEY,
  server_id   uuid NOT NULL REFERENCES servers(id),
  name        text NOT NULL,                 -- 'cpu_busy_percent'
  labels      jsonb NOT NULL DEFAULT '{}',   -- {"mount":"/","device":"/dev/sda1"}
  labels_hash text NOT NULL,                 -- md5(labels::text) tartiblangan kalit bilan
  unit        text,
  kind        text NOT NULL DEFAULT 'gauge' CHECK (kind IN ('gauge','counter')),
  rollup      boolean NOT NULL DEFAULT false, -- agregat darajalarda saqlansinmi (muhim metrika)
  first_seen  timestamptz NOT NULL DEFAULT now(),
  last_seen   timestamptz NOT NULL DEFAULT now(),
  UNIQUE (server_id, name, labels_hash)
);
CREATE INDEX series_lookup_idx ON series(server_id, name);

CREATE TABLE metric_samples (
  time      timestamptz      NOT NULL,
  series_id bigint           NOT NULL,
  value     double precision NOT NULL
);
SELECT create_hypertable('metric_samples', 'time', chunk_time_interval => INTERVAL '1 day');
CREATE UNIQUE INDEX metric_samples_uq ON metric_samples (series_id, time);

ALTER TABLE metric_samples SET (
  timescaledb.compress,
  timescaledb.compress_segmentby = 'series_id',
  timescaledb.compress_orderby   = 'time DESC'
);
SELECT add_compression_policy('metric_samples', INTERVAL '2 days');
SELECT add_retention_policy  ('metric_samples', INTERVAL '14 days');

CREATE TABLE series_latest (            -- eng oxirgi qiymat (tez so'rovlar va alert uchun)
  series_id bigint PRIMARY KEY REFERENCES series(id),
  time      timestamptz      NOT NULL,
  value     double precision NOT NULL
);
```

> **Idempotentlik chegarasi.** `ON CONFLICT DO NOTHING` (takroriy namunani o'tkazib yuborish)
> faqat siqilmagan bo'laklarda (so'nggi 2 kun) ishlaydi; agent buferi 15 daqiqa bilan
> cheklangani uchun takror paket har doim shu oraliqda keladi.
> **P-02 da tasdiqlandi** (TimescaleDB 2.17.2): siqilgan bo'lakka takror yozuv dublikat hosil qiladi
> (41 → 82 qator), UNIQUE indeks siqilgan ma'lumotda ishlamaydi. Shuning uchun ingest 1 soatdan eski
> namunani yozmaydi (`MAX_SAMPLE_AGE_S`). Siqilgan bo'lakdan qo'lda `DELETE` ham cheklangan
> (`max_tuples_decompressed_per_dml_transaction`, 100 000): eski ma'lumot faqat retention (`drop_chunks`)
> bilan o'chiriladi.

### 8.4.2. Agregatlar (continuous aggregates)

Agregat daraja uchun `sum` va `count` saqlanadi (o'rtacha = `sum/count`); shunda yuqori darajalar
quyi darajalardan to'g'ri hisoblanadi.

```sql
CREATE MATERIALIZED VIEW metric_1m
WITH (timescaledb.continuous) AS
SELECT time_bucket('1 minute', time) AS bucket,
       series_id,
       min(value) AS v_min,
       max(value) AS v_max,
       sum(value) AS v_sum,
       count(*)   AS n
FROM metric_samples
GROUP BY bucket, series_id
WITH NO DATA;

SELECT add_continuous_aggregate_policy('metric_1m',
  start_offset => INTERVAL '30 minutes', end_offset => INTERVAL '1 minute',
  schedule_interval => INTERVAL '1 minute');
SELECT add_retention_policy('metric_1m', INTERVAL '90 days');

CREATE MATERIALIZED VIEW metric_5m
WITH (timescaledb.continuous) AS
SELECT time_bucket('5 minutes', bucket) AS bucket,
       series_id,
       min(v_min) AS v_min, max(v_max) AS v_max, sum(v_sum) AS v_sum, sum(n) AS n
FROM metric_1m
GROUP BY 1, series_id
WITH NO DATA;

SELECT add_continuous_aggregate_policy('metric_5m',
  start_offset => INTERVAL '2 hours', end_offset => INTERVAL '5 minutes',
  schedule_interval => INTERVAL '5 minutes');
SELECT add_retention_policy('metric_5m', INTERVAL '365 days');

CREATE MATERIALIZED VIEW metric_1h
WITH (timescaledb.continuous) AS
SELECT time_bucket('1 hour', bucket) AS bucket,
       series_id,
       min(v_min) AS v_min, max(v_max) AS v_max, sum(v_sum) AS v_sum, sum(n) AS n
FROM metric_5m
GROUP BY 1, series_id
WITH NO DATA;

SELECT add_continuous_aggregate_policy('metric_1h',
  start_offset => INTERVAL '1 day', end_offset => INTERVAL '1 hour',
  schedule_interval => INTERVAL '1 hour');
SELECT add_retention_policy('metric_1h', INTERVAL '1095 days');
```

Eslatmalar:
- Ierarxik agregatlar (agregat ustida agregat) TimescaleDB 2.9+ da mavjud; versiya shu
  talabga ko'ra tanlanadi.
- `series.rollup = false` bo'lgan qatorlar (har-yadro, har-konteyner tarmoq va h.k.) uchun
  agregat saqlanmaydi (5.1.3 dagi hajm tejashi). **P-02 da sinab ko'rildi (R-102, hal bo'ldi):**
  `metric_1m` agregati `JOIN series ... WHERE rollup` bilan TimescaleDB 2.17.2 da yaratiladi va ishlaydi;
  5m va 1h unga ierarxik bog'lanadi (faqat `rollup` seriyalar materiallashadi). Cheklov: filtr
  yangilash paytida hisoblanadi, shuning uchun `rollup` bayrog'i seriya yaratilganda qo'yiladi va
  keyin o'zgartirilmaydi. Namuna: `backend/apps/metrics/migrations/0002_timescale.py`.
- Agregat siyosati `start_offset` dan eskisini qayta hisoblamaydi, shuning uchun xom
  ma'lumotni 14 kunda o'chirish agregatlarni buzmaydi.

### 8.4.3. Tarixiy ma'lumot qaysi jadvaldan olinadi (so'rov marshrutizatsiyasi)

| Vaqt oralig'i | Jadval | Nuqtalar soni (taxminan) |
|---|---|---|
| ≤ 6 soat | `metric_samples` (xom) | ≤ 1 440 |
| 6 soat — 3 kun | `metric_1m` | ≤ 4 320 → UI uchun 1 000 nuqtagacha qayta siyraklanadi |
| 3 kun — 30 kun | `metric_5m` | ≤ 8 640 → siyraklanadi |
| > 30 kun | `metric_1h` | ≤ 2 160 (90 kun) |

Backend oraliqqa qarab jadvalni tanlaydi va natijani `max_points=1000` ga keltirib
(`time_bucket` bilan) qaytaradi.

## 8.5. Faol tekshiruvlar

```sql
CREATE TABLE probes (
  id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id   uuid REFERENCES projects(id),
  domain_id    uuid REFERENCES domains(id),
  type         text NOT NULL CHECK (type IN ('http','tcp','tls','dns','whois')),
  name         text NOT NULL,
  config       jsonb NOT NULL,       -- tur bo'yicha sxema (18.4)
  interval_s   int  NOT NULL DEFAULT 60 CHECK (interval_s BETWEEN 10 AND 86400),
  timeout_s    int  NOT NULL DEFAULT 10 CHECK (timeout_s BETWEEN 1 AND 60),
  enabled      boolean NOT NULL DEFAULT true,
  state        text NOT NULL DEFAULT 'unknown' CHECK (state IN ('up','down','unknown','paused')),
  state_since  timestamptz,
  consecutive_failures int NOT NULL DEFAULT 0,
  last_run_at  timestamptz,
  next_run_at  timestamptz NOT NULL DEFAULT now(),
  secrets_enc  bytea,                -- shifrlangan sarlavhalar (Authorization va h.k.)
  created_at   timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX probes_due_idx ON probes(next_run_at) WHERE enabled;

CREATE TABLE probe_results (
  time        timestamptz NOT NULL,
  probe_id    uuid        NOT NULL,
  ok          boolean     NOT NULL,
  status_code int,
  total_ms    int,
  dns_ms      int,
  connect_ms  int,
  tls_ms      int,
  ttfb_ms     int,
  error_kind  text,        -- 'timeout','dns','connect','tls','status','keyword','redirect_loop'
  detail      jsonb
);
SELECT create_hypertable('probe_results', 'time', chunk_time_interval => INTERVAL '7 days');
CREATE INDEX probe_results_idx ON probe_results(probe_id, time DESC);
SELECT add_retention_policy('probe_results', INTERVAL '90 days');

CREATE TABLE probe_uptime_daily (    -- uzoq muddatli uptime hisobi (FR-HTTP-009)
  probe_id        uuid NOT NULL REFERENCES probes(id),
  day             date NOT NULL,
  checks_total    int  NOT NULL,
  checks_ok       int  NOT NULL,
  maintenance_s   int  NOT NULL DEFAULT 0,   -- rejalashtirilgan to'xtash vaqti
  avg_total_ms    int,
  p95_total_ms    int,
  PRIMARY KEY (probe_id, day)
);

-- S5: `cert_status` ORM da; UNIQUE (name, source, server) NULL larni teng hisoblaydi (agentsiz yozuvda server NULL).
-- Yangi: `settings(key, value jsonb)` — tizim sozlamalari (hozircha `retired_ips`, Q-12; `seed_registry` yozadi).
CREATE TABLE cert_status (           -- eng oxirgi sertifikat holati (TLS probe yoki agent)
  id          bigserial PRIMARY KEY,
  domain_id   uuid REFERENCES domains(id),
  server_id   uuid REFERENCES servers(id),
  name        text NOT NULL,               -- 'avlo.ai' yoki papka nomi
  source      text NOT NULL CHECK (source IN ('probe','agent')),
  not_after   timestamptz NOT NULL,
  issuer      text,
  subject     text,
  san         text[] NOT NULL DEFAULT '{}',
  chain_ok    boolean,
  hostname_ok boolean,
  checked_at  timestamptz NOT NULL DEFAULT now(),
  UNIQUE (name, source, server_id)
);

CREATE TABLE dns_results (
  time       timestamptz NOT NULL,
  domain_id  uuid        NOT NULL,
  probe_id   uuid        NOT NULL,   -- S5: qaysi DNS tekshiruvi (bir domenda bir nechta bo'lishi mumkin)
  resolver   text        NOT NULL,     -- '8.8.8.8','1.1.1.1','9.9.9.9','ns:rdns1.ahost.uz'
  rtype      text        NOT NULL DEFAULT 'A',
  answers    text[]      NOT NULL DEFAULT '{}',
  matches    boolean     NOT NULL,     -- kutilgan IP lar bilan mosmi
  rcode      text,
  latency_ms int
);
SELECT create_hypertable('dns_results', 'time', chunk_time_interval => INTERVAL '7 days');
CREATE INDEX dns_results_idx ON dns_results(domain_id, time DESC);
SELECT add_retention_policy('dns_results', INTERVAL '90 days');

CREATE TABLE dns_changes (
  id         bigserial PRIMARY KEY,
  domain_id  uuid NOT NULL REFERENCES domains(id),
  resolver   text NOT NULL,
  rtype      text NOT NULL,
  old_answers text[] NOT NULL,
  new_answers text[] NOT NULL,
  changed_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE domain_whois (
  domain_id   uuid PRIMARY KEY REFERENCES domains(id),
  expires_at  timestamptz,
  registrar   text,
  source      text NOT NULL CHECK (source IN ('rdap','manual')),
  checked_at  timestamptz NOT NULL DEFAULT now()
);
```

## 8.6. Zaxira nusxalar

```sql
-- S6: loyiha zaxira siyosati `projects.backup jsonb` ({expect_daily, expect_weekly_files, require_offsite, db}; seed `backup:` dan).
-- `backup_runs` agent yuborgan state.json dan emas, `backup_*` METRIKALARIDAN hosil bo'ladi: har safar `backup_last_success_timestamp` yangilansa evaluator
-- bitta qator yozadi (faqat kind='daily', server_id, project_slug, finished_at, size_bytes; UNIQUE shu to'rtlikda). Qolgan ustunlar (status, error, offsite_*) —
-- F2 (restore drill bilan birga). Hajm anomaliyasi (AL-071/072) va 30 kunlik grafik shu tarixdan.
CREATE TABLE backup_runs (            -- appctl state.json dan (agent yuboradi)
  id            bigserial PRIMARY KEY,
  server_id     uuid NOT NULL REFERENCES servers(id),
  project_id    uuid REFERENCES projects(id),
  project_slug  text NOT NULL,
  kind          text NOT NULL CHECK (kind IN ('daily','weekly','files')),
  status        text NOT NULL CHECK (status IN ('ok','fail')),
  started_at    timestamptz,
  finished_at   timestamptz NOT NULL,
  duration_s    int,
  file_name     text,
  size_bytes    bigint,
  error         text,
  offsite_status text CHECK (offsite_status IN ('ok','fail','skipped')),
  offsite_finished_at timestamptz,
  UNIQUE (server_id, project_slug, kind, finished_at)
);
CREATE INDEX backup_runs_idx ON backup_runs(project_slug, finished_at DESC);

CREATE TABLE backup_snapshots (       -- papka skaneri natijasi (har host × loyiha × tur uchun 1 qator)
  server_id       uuid NOT NULL REFERENCES servers(id),
  project_slug    text NOT NULL,
  kind            text NOT NULL,
  newest_file     text,
  newest_mtime    timestamptz,
  newest_size     bigint,
  files_count     int,
  dir_bytes       bigint,
  gz_ok           boolean,
  checked_at      timestamptz NOT NULL,
  PRIMARY KEY (server_id, project_slug, kind)
);

CREATE TABLE restore_drills (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id    uuid NOT NULL REFERENCES projects(id),
  performed_at  timestamptz NOT NULL,
  performed_by  uuid REFERENCES users(id),
  backup_file   text NOT NULL,
  backup_age_h  int,
  duration_s    int,
  tables_count  int,
  rows_count    bigint,
  result        text NOT NULL CHECK (result IN ('success','partial','failed')),
  notes         text NOT NULL DEFAULT ''
);
CREATE INDEX restore_drills_idx ON restore_drills(project_id, performed_at DESC);

CREATE TABLE heartbeat_jobs (          -- cron/skript "bajarildim" signallari (FR-SVC-004, FR-INT-005)
  id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  name           text NOT NULL UNIQUE,   -- 'appctl-backup@main-2'
  server_id      uuid REFERENCES servers(id),
  project_id     uuid REFERENCES projects(id),
  token_hash     bytea NOT NULL UNIQUE,
  expected_every_s int NOT NULL,
  grace_s        int NOT NULL DEFAULT 3600,
  last_beat_at   timestamptz,
  last_ok        boolean,
  enabled        boolean NOT NULL DEFAULT true
);
```

## 8.7. Alert tizimi

```sql
CREATE TABLE alert_rules (
  id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  key          text NOT NULL UNIQUE,        -- 'AL-003'
  name         text NOT NULL,
  description  text NOT NULL DEFAULT '',
  scope        jsonb NOT NULL,              -- {"type":"host"|"project"|"probe"|"domain", "tags":[...], "ids":[...]}
  condition    jsonb NOT NULL,              -- 12.3 sxemasi
  for_seconds  int  NOT NULL DEFAULT 0,
  resolve_after_seconds int NOT NULL DEFAULT 60,
  severity     text NOT NULL CHECK (severity IN ('info','warning','high','critical')),
  channels     uuid[] NOT NULL DEFAULT '{}',   -- bo'sh bo'lsa standart kanallar
  runbook_key  text,                           -- 'RB-004'
  enabled      boolean NOT NULL DEFAULT true,
  built_in     boolean NOT NULL DEFAULT false,
  updated_at   timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE incidents (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  scope_key     text NOT NULL,              -- 'host:<server_id>' | 'project:<id>' | 'domain:<id>'
  title         text NOT NULL,
  severity      text NOT NULL CHECK (severity IN ('info','warning','high','critical')),
  status        text NOT NULL DEFAULT 'open' CHECK (status IN ('open','acknowledged','resolved')),
  started_at    timestamptz NOT NULL DEFAULT now(),
  acked_at      timestamptz,
  acked_by      uuid REFERENCES users(id),
  resolved_at   timestamptz,
  suppressed    boolean NOT NULL DEFAULT false,   -- silence/maintenance ichida ochilgan
  root_cause    text,
  summary       jsonb NOT NULL DEFAULT '{}'
);
CREATE UNIQUE INDEX incidents_one_open_per_scope
  ON incidents(scope_key) WHERE status <> 'resolved';
CREATE INDEX incidents_time_idx ON incidents(started_at DESC);

CREATE TABLE alert_instances (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  rule_id       uuid NOT NULL REFERENCES alert_rules(id),
  subject_type  text NOT NULL,            -- 'host','probe','domain','project','container','unit'
  subject_id    text NOT NULL,            -- UUID yoki 'host:container' kabi kalit
  fingerprint   text NOT NULL,            -- hash(rule_id, subject_type, subject_id, labels)
  state         text NOT NULL CHECK (state IN ('ok','pending','firing','resolving')),
  pending_since timestamptz,
  firing_since  timestamptz,
  resolving_since timestamptz,
  last_eval_at  timestamptz NOT NULL DEFAULT now(),
  last_value    double precision,
  labels        jsonb NOT NULL DEFAULT '{}',
  incident_id   uuid REFERENCES incidents(id),
  UNIQUE (fingerprint)
);
CREATE INDEX alert_instances_state_idx ON alert_instances(state) WHERE state <> 'ok';

-- Amalga oshirishda qo'shilgan ustunlar (S4): servers.paused_until, servers.pause_reason (pauza muddati va sababi, FR-HST-016);
-- probe_results — ORM modeli emas, migratsiyada SQL bilan yaratilgan gipertablitsa; probes.secrets_enc hozircha ishlatilmaydi.
-- Amalga oshirishda qo'shilgan ustunlar (S3):
--   alert_rules.runbook_hint text         -- xabardagi "Nima qilish kerak" matni
--   incidents.last_notified_at, reminders_sent   -- takroriy eslatmalar (12.4.1)
--   alert_instances.subject_name, detail, suppressed, notified_at   -- xabar matni va bostirish holati
-- `evaluator_state` (id=1, last_run_at, last_duration_ms): dvigatel ishlayotganini bildiradi (AL-084).
-- notifications.incident_id -> incidents(id) ON DELETE SET NULL (migratsiya bilan bog'langan).

CREATE TABLE incident_events (
  id          bigserial PRIMARY KEY,
  incident_id uuid NOT NULL REFERENCES incidents(id),
  time        timestamptz NOT NULL DEFAULT now(),
  type        text NOT NULL,   -- opened, alert_added, alert_resolved, acked, comment, notified, escalated, resolved, severity_changed
  user_id     uuid REFERENCES users(id),
  data        jsonb NOT NULL DEFAULT '{}'
);
CREATE INDEX incident_events_idx ON incident_events(incident_id, time);

CREATE TABLE silences (
  id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  matchers   jsonb NOT NULL,      -- [{"label":"server","op":"=","value":"main-2"}, ...]
  starts_at  timestamptz NOT NULL DEFAULT now(),
  ends_at    timestamptz NOT NULL CHECK (ends_at > starts_at),
  reason     text NOT NULL CHECK (length(reason) > 0),
  created_by uuid REFERENCES users(id),
  created_at timestamptz NOT NULL DEFAULT now(),
  cancelled_at timestamptz
);

CREATE TABLE maintenance_windows (
  id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  scope      jsonb NOT NULL,      -- {"servers":[...], "projects":[...]}
  starts_at  timestamptz NOT NULL,
  ends_at    timestamptz NOT NULL CHECK (ends_at > starts_at),
  reason     text NOT NULL,
  created_by uuid REFERENCES users(id),
  cancelled_at timestamptz
);
```

## 8.8. Bildirishnomalar, foydalanuvchilar, audit

```sql
CREATE TABLE channels (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  type          text NOT NULL CHECK (type IN ('telegram','email','webhook')),
  name          text NOT NULL UNIQUE,
  config_enc    bytea NOT NULL,        -- shifrlangan JSON: bot_token, chat_id / smtp / url, secret
  min_severity  text NOT NULL DEFAULT 'warning'
                CHECK (min_severity IN ('info','warning','high','critical')),
  quiet_hours   jsonb,                 -- {"from":"23:00","to":"07:00","tz":"Asia/Tashkent","pass":["critical"]}
  is_default    boolean NOT NULL DEFAULT false,
  enabled       boolean NOT NULL DEFAULT true,
  last_ok_at    timestamptz,
  last_error    text
);

CREATE TABLE notifications (
  id           bigserial PRIMARY KEY,
  incident_id  uuid REFERENCES incidents(id),
  channel_id   uuid NOT NULL REFERENCES channels(id),
  event        text NOT NULL,         -- 'opened','escalated','resolved','reminder','digest','test'
  status       text NOT NULL CHECK (status IN ('queued','sent','failed','suppressed')),
  attempts     int  NOT NULL DEFAULT 0,
  created_at   timestamptz NOT NULL DEFAULT now(),
  sent_at      timestamptz,
  external_id  text,                  -- Telegram message_id (tahrirlash uchun)
  error        text,
  payload      jsonb NOT NULL,        -- yuboriladigan xabar {"text","buttons"} (sirlarsiz); qayta urinish uchun
  next_attempt_at timestamptz NOT NULL DEFAULT now()   -- status='queued' bo'lganda keyingi urinish vaqti
);
-- incident_id: incidents jadvali S3 da yaratiladi; shu paytgacha FK emas (keyin migratsiya bilan bog'lanadi).
CREATE INDEX notifications_due_idx ON notifications(next_attempt_at) WHERE status = 'queued';
CREATE INDEX notifications_idx ON notifications(incident_id, created_at);

CREATE TABLE users (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  login         text NOT NULL UNIQUE,
  email         text UNIQUE,
  password_hash text NOT NULL,          -- argon2id
  role          text NOT NULL CHECK (role IN ('owner','operator','viewer')),
  totp_secret_enc bytea,
  telegram_chat_id bigint,
  language      text NOT NULL DEFAULT 'uz' CHECK (language IN ('uz','ru','en')),
  timezone      text NOT NULL DEFAULT 'Asia/Tashkent',
  is_active     boolean NOT NULL DEFAULT true,
  failed_logins int NOT NULL DEFAULT 0,
  locked_until  timestamptz,
  last_login_at timestamptz,
  created_at    timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE user_projects (          -- viewer cheklovi (FR-AUTH-005)
  user_id    uuid NOT NULL REFERENCES users(id),
  project_id uuid NOT NULL REFERENCES projects(id),
  PRIMARY KEY (user_id, project_id)
);

CREATE TABLE user_sessions (          -- Django sessiya saqlagichi + egasi (FR-AUTH-004); amalda Django nomi: accounts_usersession
  session_key  varchar(40) PRIMARY KEY,
  session_data text NOT NULL,
  expire_date  timestamptz NOT NULL,
  user_id      uuid,                           -- users.id; FK emas (Django sessiyani ro'yxatdan o'tkazmasdan yozadi); NULL: kirilmagan sessiya
  public_id    uuid NOT NULL DEFAULT gen_random_uuid(),  -- API'da ko'rinadigan id; session_key hech qachon chiqmaydi
  ip           inet,
  user_agent   varchar(300) NOT NULL DEFAULT '',
  created_at   timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX user_sessions_expire_idx ON user_sessions(expire_date);
CREATE INDEX user_sessions_user_idx ON user_sessions(user_id);
CREATE INDEX user_sessions_public_idx ON user_sessions(public_id);   -- UNIQUE emas, pastga qarang
-- `public_id` ataylab UNIQUE emas: Django `cycle_key()` yangi qatorni eskisi o'chirilishidan OLDIN
-- yaratadi, UNIQUE bo'lsa `create()` cheksiz qayta uriniladi (S1 da topilgan). Ro'yxat/o'chirish
-- so'rovlari `user_id` bilan birga filtrlanadi, shuning uchun to'qnashuv xavfsizlikka ta'sir qilmaydi.

CREATE TABLE audit_log (
  id          bigserial PRIMARY KEY,
  time        timestamptz NOT NULL DEFAULT now(),
  user_id     uuid REFERENCES users(id),
  ip          inet,
  action      text NOT NULL,          -- 'login','logout','server.create','rule.update','silence.create',...
  object_type text,
  object_id   text,
  before      jsonb,
  after       jsonb
);
CREATE INDEX audit_log_idx ON audit_log(time DESC);
-- Audit jurnali faqat qo'shiladi: ilova foydalanuvchisiga UPDATE/DELETE huquqi berilmaydi.
REVOKE UPDATE, DELETE ON audit_log FROM nazoratchi_app;
```

## 8.9. Kritik so'rovlar va kutilgan rejalar

| № | So'rov | Maqsad | Indeks / yo'l | Kutilgan vaqt |
|---|---|---|---|---|
| Q1 | Host sahifasidagi "hozirgi" qiymatlar | Eng oxirgi qiymatlar | `series (server_id)` → `series_latest` PK | < 20 ms |
| Q2 | Grafik: 1 qator, 24 soat | UI grafigi | `metric_1m` (series_id, bucket) | < 100 ms |
| Q3 | Barcha loyihalar uchun zaxira yoshi | Zaxiralar sahifasi | `backup_runs (project_slug, finished_at desc)` + `backup_snapshots` PK | < 50 ms |
| Q4 | Ochiq incidentlar | Dashboard | `incidents` qisman indeks (status <> 'resolved') | < 10 ms |
| Q5 | Probe uptime 30 kun | Uptime foizi | `probe_uptime_daily` PK | < 30 ms |
| Q6 | Disk bashorati (regressiya) | Alert/forecast | `metric_samples (series_id, time)` oxirgi 6 soat | < 100 ms |
| Q7 | "Jim" hostlar | Server o'chdi | `servers (last_seen_at)` | < 10 ms |

Namuna (Q1):

```sql
SELECT s.name, s.labels, l.value, l.time
FROM series s
JOIN series_latest l ON l.series_id = s.id
WHERE s.server_id = $1;
```

Namuna (Q2, 24 soatlik CPU):

```sql
SELECT bucket AS t, v_sum / n AS avg, v_min, v_max
FROM metric_1m
WHERE series_id = $1 AND bucket >= now() - INTERVAL '24 hours'
ORDER BY bucket;
```

Namuna (Q6, to'lishga qolgan vaqt):

```sql
WITH pts AS (
  SELECT extract(epoch FROM time) AS x, value AS y
  FROM metric_samples
  WHERE series_id = $1 AND time >= now() - INTERVAL '6 hours'
), fit AS (
  SELECT regr_slope(y, x) AS slope, regr_intercept(y, x) AS icpt, regr_r2(y, x) AS r2
  FROM pts
)
SELECT slope, r2,
       CASE WHEN slope > 0 THEN ($2 - (slope * extract(epoch FROM now()) + icpt)) / slope END AS seconds_to_full
FROM fit;   -- $2 = fs_total_bytes
```

## 8.10. Saqlash siyosati (retention) xulosasi

| Ma'lumot | Saqlash | Mexanizm |
|---|---|---|
| `metric_samples` (xom) | 14 kun (2 kundan keyin siqiladi) | Timescale retention + compression |
| `metric_1m` | 90 kun | CAgg retention |
| `metric_5m` | 365 kun | CAgg retention |
| `metric_1h` | 3 yil | CAgg retention |
| `probe_results` | 90 kun | Timescale retention |
| `probe_uptime_daily` | cheksiz (kichik) | — |
| `dns_results` | 90 kun | Timescale retention |
| `dns_changes`, `host_events` | cheksiz | — |
| `incidents`, `incident_events` | cheksiz (yiliga ~ yuzlab) | — |
| `notifications` | 1 yil | Celery vazifasi |
| `audit_log` | ≥ 1 yil (tavsiya: cheksiz) | Faqat qo'shiladi |
| `backup_runs` | 2 yil | Celery vazifasi |

Sozlamalar paneldan o'zgartiriladi (NFR-DAT-002), o'zgarish audit jurnaliga yoziladi.

## 8.11. Boshlang'ich ma'lumot (seed)

Birinchi o'rnatishda reyestr 2-bo'limdagi inventardan to'ldiriladi (`seed/inventory.yaml`,
18-bo'limdagi format): S-00, S-01, S-02 (S-03 arxivda), 7 ishlayotgan loyiha, ~20 domen, kutilgan IP lar,
DNS provayderlar va "ko'chirilmagan" loyihalar. Shu bilan 90-kunlik KPI (G-6) dastlabki
kundan boshlanadi.

## 8.12. Migratsiya qoidalari

- Django migratsiyalari + Timescale maxsus buyruqlari (`RunSQL`) bilan; har migratsiya
  qaytariladigan (`reverse_sql`).
- Gipertablitsa va agregatlar migratsiyasi tranzaksiyadan tashqarida bajarilishi kerak
  (`atomic = False`; `CREATE MATERIALIZED VIEW ... WITH (timescaledb.continuous)` talabi).
- Katta jadvallarga ustun qo'shish `DEFAULT` siz va `NULL` ruxsat bilan (qulflanishni
  oldini olish), keyin to'ldirish va cheklov qo'shish.
- Sxema o'zgarishi paytida ingest to'xtamaydi; agentlar buferi bilan qoplaydi (FR-SYS-006).
