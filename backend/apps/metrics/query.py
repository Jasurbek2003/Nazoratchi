"""Vaqt qatori so'rovi: oraliqqa qarab jadval tanlash (TZ 8.4.3) va nuqtalarni siyraklash."""

import math
from datetime import datetime, timedelta

from django.db import connection

HOUR = timedelta(hours=1)
DAY = timedelta(days=1)


def pick_source(span: timedelta) -> str:
    """TZ 8.4.3: <= 6 soat xom, <= 3 kun 1m, <= 30 kun 5m, undan ko'p 1h."""
    if span <= 6 * HOUR:
        return "raw"
    if span <= 3 * DAY:
        return "1m"
    if span <= 30 * DAY:
        return "5m"
    return "1h"


NATIVE_STEP_S = {"raw": 1, "1m": 60, "5m": 300, "1h": 3600}
_TABLE = {"1m": "metric_1m", "5m": "metric_5m", "1h": "metric_1h"}
_RAW_AGG = {
    "avg": "avg(value)",
    "min": "min(value)",
    "max": "max(value)",
    "last": "last(value, time)",
}
_CAGG_AGG = {
    "avg": "sum(v_sum) / sum(n)",
    "min": "min(v_min)",
    "max": "max(v_max)",
    "last": "sum(v_sum) / sum(n)",  # agregatda oxirgi qiymat saqlanmaydi; o'rtacha beriladi
}


def run_query(
    series_id: int, start: datetime, end: datetime, max_points: int = 1000, agg: str = "avg"
) -> tuple[str, int, list[list[float]]]:
    """(manba, qadam soniyada, [[vaqt_ms, qiymat], ...])."""
    if agg not in _RAW_AGG:
        raise ValueError(f"agg noto'g'ri: {agg}")
    span = end - start
    source = pick_source(span)
    step = max(NATIVE_STEP_S[source], math.ceil(span.total_seconds() / max(max_points, 1)))
    if source == "raw":
        sql = f"""
            SELECT extract(epoch FROM time_bucket(%s * interval '1 second', time)) * 1000 AS t,
                   {_RAW_AGG[agg]} AS v
            FROM metric_samples
            WHERE series_id = %s AND time >= %s AND time <= %s
            GROUP BY 1 ORDER BY 1
        """  # noqa: S608 (agg faqat oq ro'yxatdan)
    else:
        sql = f"""
            SELECT extract(epoch FROM time_bucket(%s * interval '1 second', bucket)) * 1000 AS t,
                   {_CAGG_AGG[agg]} AS v
            FROM {_TABLE[source]}
            WHERE series_id = %s AND bucket >= %s AND bucket <= %s
            GROUP BY 1 ORDER BY 1
        """  # noqa: S608 (jadval nomi faqat oq ro'yxatdan)
    with connection.cursor() as cursor:
        cursor.execute(sql, [step, series_id, start, end])
        points = [[float(t), float(v)] for t, v in cursor.fetchall()]
    return source, step, points
