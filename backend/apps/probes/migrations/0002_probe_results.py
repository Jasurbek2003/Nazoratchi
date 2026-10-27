from django.db import migrations

# TZ 8.5: probe_results — Timescale gipertablitsasi (ORM modeli emas). 7 kunlik bo'lak, 90 kunlik saqlash.
FORWARD = [
    """
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
        error_kind  text,
        detail      jsonb
    )
    """,
    "SELECT create_hypertable('probe_results', 'time', chunk_time_interval => INTERVAL '7 days')",
    "CREATE INDEX probe_results_idx ON probe_results (probe_id, time DESC)",
    "SELECT add_retention_policy('probe_results', INTERVAL '90 days')",
]


class Migration(migrations.Migration):
    dependencies = [("probes", "0001_initial")]

    operations = [
        migrations.RunSQL(sql=FORWARD, reverse_sql="DROP TABLE probe_results"),
    ]
