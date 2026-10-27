from django.db import migrations


class Migration(migrations.Migration):
    """notifications.incident_id -> incidents(id): incidents jadvali alerts ilovasida (S3) paydo bo'ldi (TZ 8.8).
    Maydon UUIDField bo'lib qoladi (ORM'da FK emas), bog'lanish bazada ta'minlanadi."""

    dependencies = [
        ("notifications", "0001_initial"),
        ("alerts", "0001_initial"),
    ]

    operations = [
        migrations.RunSQL(
            sql=(
                "ALTER TABLE notifications_notification ADD CONSTRAINT notification_incident_fk "
                "FOREIGN KEY (incident_id) REFERENCES alerts_incident(id) "
                "ON DELETE SET NULL DEFERRABLE INITIALLY DEFERRED"
            ),
            reverse_sql="ALTER TABLE notifications_notification DROP CONSTRAINT notification_incident_fk",
        )
    ]
