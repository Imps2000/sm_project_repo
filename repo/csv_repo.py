import csv, os, json, tempfile
from typing import Iterable, Dict, Any, List

DATA_DIR = "data"
COUNTERS = os.path.join(DATA_DIR, "counters.json")

def _atomic_write(path: str, rows: Iterable[Dict[str, Any]], fieldnames: List[str]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), text=True)
    os.close(fd)
    with open(tmp, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in rows:
            w.writerow(r)
    os.replace(tmp, path)

def read_csv(path: str) -> List[Dict[str, str]]:
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))

def write_csv(path: str, rows: List[Dict[str, Any]]) -> None:
    fieldnames = list(rows[0].keys()) if rows else []
    _atomic_write(path, rows, fieldnames)

def append_csv(path: str, row: Dict[str, Any]) -> None:
    rows = read_csv(path)
    fieldnames = list(rows[0].keys()) if rows else list(row.keys())
    rows.append(row)
    _atomic_write(path, rows, fieldnames)

def next_id(kind: str) -> str:
    os.makedirs(DATA_DIR, exist_ok=True)
    data = {}
    if os.path.exists(COUNTERS):
        with open(COUNTERS, "r", encoding="utf-8") as f:
            data = json.load(f)
    n = int(data.get(kind, 0)) + 1
    data[kind] = n
    with open(COUNTERS, "w", encoding="utf-8") as f:
        json.dump(data, f)
    prefix = {"user": "u", "post": "p", "repost": "r", "comment": "c", "log": "l"}.get(kind, "x")
    return f"{prefix}_{n:04d}"
