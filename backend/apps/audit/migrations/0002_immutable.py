"""Audit jurnali faqat qo'shiladi (FR-AUD-004): UPDATE va DELETE ni DB triggeri taqiqlaydi.

TZ 8.8 `REVOKE UPDATE, DELETE ... FROM nazoratchi_app` deydi; trigger DB foydalanuvchisiga bog'liq emas
(superuser ham o'zgartira olmaydi, faqat triggerni o'chirib). TRUNCATE ataylab taqiqlanmagan: test bazasini
tozalash uchun kerak.
"""

from django.db import migrations

FORWARD = [
    """
    CREATE FUNCTION audit_log_immutable() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
        RAISE EXCEPTION 'audit_log faqat qo''shiladi: % taqiqlangan', TG_OP USING ERRCODE = 'integrity_constraint_violation';
    END
    $$
    """,
    """
    CREATE TRIGGER audit_log_no_change BEFORE UPDATE OR DELETE ON audit_log
    FOR EACH ROW EXECUTE FUNCTION audit_log_immutable()
    """,
]
REVERSE = [
    "DROP TRIGGER IF EXISTS audit_log_no_change ON audit_log",
    "DROP FUNCTION IF EXISTS audit_log_immutable()",
]


class Migration(migrations.Migration):
    dependencies = [("audit", "0001_initial")]
    operations = [migrations.RunSQL(sql=FORWARD, reverse_sql=REVERSE)]
