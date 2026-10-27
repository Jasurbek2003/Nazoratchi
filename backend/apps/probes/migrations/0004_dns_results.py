from django.db import migrations

# TZ 8.5: dns_results — Timescale gipertablitsasi (ORM modeli emas). 7 kunlik bo'lak, 90 kunlik saqlash.
FORWARD = [
    """
    CREATE TABLE dns_results (
        time       timestamptz NOT NULL,
        domain_id  uuid        NOT NULL,
        probe_id   uuid        NOT NULL,
        resolver   text        NOT NULL,
        rtype      text        NOT NULL DEFAULT 'A',
        answers    text[]      NOT NULL DEFAULT '{}',
        matches    boolean     NOT NULL,
        rcode      text,
        latency_ms int
    )
    """,
    "SELECT create_hypertable('dns_results', 'time', chunk_time_interval => INTERVAL '7 days')",
    "CREATE INDEX dns_results_idx ON dns_results (domain_id, time DESC)",
    "SELECT add_retention_policy('dns_results', INTERVAL '90 days')",
]


class Migration(migrations.Migration):
    dependencies = [("probes", "0003_dnschange_certstatus")]

    operations = [migrations.RunSQL(sql=FORWARD, reverse_sql="DROP TABLE dns_results")]
