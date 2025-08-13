from datetime import datetime, timezone, timedelta

KST = timezone(timedelta(hours=9))

def now_kst_iso() -> str:
    return datetime.now(tz=KST).isoformat()