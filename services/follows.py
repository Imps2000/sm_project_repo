# services/follows.py
import os
from typing import List, Set
from repo.csv_repo import read_csv, write_csv, append_csv
from utils.time import now_kst_iso
from services.activity import log_event  # 활동 로그

FOLLOWS = os.path.join("data", "follows.csv")

def _load() -> List[dict]:
    return read_csv(FOLLOWS)

def get_following(user_id: str) -> Set[str]:
    """user_id가 팔로우하는 대상들"""
    return {r["followee_id"] for r in _load() if r["follower_id"] == user_id}

def get_followers(user_id: str) -> Set[str]:
    """user_id를 팔로우하는 사람들"""
    return {r["follower_id"] for r in _load() if r["followee_id"] == user_id}

def is_following(follower_id: str, followee_id: str) -> bool:
    return any(r for r in _load() if r["follower_id"] == follower_id and r["followee_id"] == followee_id)

def follow(follower_id: str, followee_id: str) -> bool:
    """
    성공 시 True, 이미 팔로우 상태거나 자기 자신이면 False
    """
    if follower_id == followee_id:
        return False
    if is_following(follower_id, followee_id):
        return False
    append_csv(FOLLOWS, {
        "follower_id": follower_id,
        "followee_id": followee_id,
        "created_at": now_kst_iso()
    })
    log_event("USER_FOLLOWED", follower_id, "User", followee_id, {})
    return True

def unfollow(follower_id: str, followee_id: str) -> bool:
    """
    성공 시 True (한 줄 제거), 없으면 False
    """
    rows = _load()
    new_rows = [r for r in rows if not (r["follower_id"] == follower_id and r["followee_id"] == followee_id)]
    if len(new_rows) == len(rows):
        return False
    write_csv(FOLLOWS, new_rows)
    log_event("USER_UNFOLLOWED", follower_id, "User", followee_id, {})
    return True
