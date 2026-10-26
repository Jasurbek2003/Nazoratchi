"""TimescaleDB: gipertablitsa, siqish, saqlash va ierarxik agregatlar (TZ 8.4.1, 8.4.2).

`CREATE MATERIALIZED VIEW ... WITH (timescaledb.continuous)` tranzaksiya ichida bajarilmaydi,
shuning uchun migratsiya `atomic = False` (TZ 8.12).
"""

from django.db import migrations

FORWARD = [
    "CREATE EXTENSION IF NOT EXISTS timescaledb",
    """
    CREATE TABLE metric_samples (
        time      timestamptz      NOT NULL,
        series_id bigint           NOT NULL,
        value     double precision NOT NULL
    )
    """,
    "SELECT create_hypertable('metric_samples', 'time', chunk_time_interval => INTERVAL '1 day')",
    "CREATE UNIQUE INDEX metric_samples_uq ON metric_samples (series_id, time)",
    """
    ALTER TABLE metric_samples SET (
        timescaledb.compress,
        timescaledb.compress_segmentby = 'series_id',
        timescaledb.compress_orderby   = 'time DESC'
    )
    """,
    "SELECT add_compression_policy('metric_samples', INTERVAL '2 days')",
    "SELECT add_retention_policy('metric_samples', INTERVAL '14 days')",
    # --- 1 daqiqalik agregat: yig'indi va son saqlanadi (o'rtacha = sum/n). Faqat `rollup` seriyalar
    #     (TZ 8.4.2 / R-102: JOIN li agregat TimescaleDB 2.17.2 da sinalgan, 5m/1h unga ierarxik bog'lanadi). ---
    """
    CREATE MATERIALIZED VIEW metric_1m
    WITH (timescaledb.continuous) AS
    SELECT time_bucket('1 minute', m.time) AS bucket,
           m.series_id,
           min(m.value) AS v_min,
           max(m.value) AS v_max,
           sum(m.value) AS v_sum,
           count(*)     AS n
    FROM metric_samples m
    JOIN metrics_series s ON s.id = m.series_id
    WHERE s.rollup
    GROUP BY bucket, m.series_id
    WITH NO DATA
    """,
    """
    SELECT add_continuous_aggregate_policy('metric_1m',
        start_offset => INTERVAL '30 minutes', end_offset => INTERVAL '1 minute',
        schedule_interval => INTERVAL '1 minute')
    """,
    "SELECT add_retention_policy('metric_1m', INTERVAL '90 days')",
    # --- 5 daqiqalik: 1m dan (ierarxik agregat, TimescaleDB >= 2.9) ---
    """
    CREATE MATERIALIZED VIEW metric_5m
    WITH (timescaledb.continuous) AS
    SELECT time_bucket('5 minutes', bucket) AS bucket,
           series_id,
           min(v_min) AS v_min, max(v_max) AS v_max, sum(v_sum) AS v_sum, sum(n) AS n
    FROM metric_1m
    GROUP BY 1, series_id
    WITH NO DATA
    """,
    """
    SELECT add_continuous_aggregate_policy('metric_5m',
        start_offset => INTERVAL '2 hours', end_offset => INTERVAL '5 minutes',
        schedule_interval => INTERVAL '5 minutes')
    """,
    "SELECT add_retention_policy('metric_5m', INTERVAL '365 days')",
    # --- 1 soatlik: 5m dan ---
    """
    CREATE MATERIALIZED VIEW metric_1h
    WITH (timescaledb.continuous) AS
    SELECT time_bucket('1 hour', bucket) AS bucket,
           series_id,
           min(v_min) AS v_min, max(v_max) AS v_max, sum(v_sum) AS v_sum, sum(n) AS n
    FROM metric_5m
    GROUP BY 1, series_id
    WITH NO DATA
    """,
    """
    SELECT add_continuous_aggregate_policy('metric_1h',
        start_offset => INTERVAL '1 day', end_offset => INTERVAL '1 hour',
        schedule_interval => INTERVAL '1 hour')
    """,
    "SELECT add_retention_policy('metric_1h', INTERVAL '1095 days')",
]

REVERSE = [
    "DROP MATERIALIZED VIEW IF EXISTS metric_1h",
    "DROP MATERIALIZED VIEW IF EXISTS metric_5m",
    "DROP MATERIALIZED VIEW IF EXISTS metric_1m",
    "DROP TABLE IF EXISTS metric_samples",
]


class Migration(migrations.Migration):
    atomic = False

    dependencies = [("metrics", "0001_initial")]

    operations = [migrations.RunSQL(sql=FORWARD, reverse_sql=REVERSE)]
