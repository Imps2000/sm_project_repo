import os
from typing import List, Dict, Tuple
from repo.csv_repo import read_csv, write_csv, append_csv
from utils.time import now_kst_iso

REACTIONS = os.path.join("data", "reactions.csv")

def count_likes(post_id: str) -> int:
    return sum(1 for r in read_csv(REACTIONS) if r["post_id"] == post_id)

def user_liked(post_id: str, user_id: str) -> bool:
    return any(r for r in read_csv(REACTIONS) if r["post_id"] == post_id and r["user_id"] == user_id)

def toggle_like(post_id: str, user_id: str) -> Tuple[bool, int]:
    rows = read_csv(REACTIONS)
    before = len(rows)
    # remove if exists
    rows = [r for r in rows if not (r["post_id"] == post_id and r["user_id"] == user_id)]
    if len(rows) < before:
        write_csv(REACTIONS, rows)  # unliked
        return (False, count_likes(post_id))
    # else add
    append_csv(REACTIONS, {"post_id": post_id, "user_id": user_id, "created_at": now_kst_iso()})
    return (True, count_likes(post_id))
