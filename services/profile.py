import os
from typing import Optional, Dict
from repo.csv_repo import read_csv, write_csv

DATA_DIR = "data"
USERS_PATH = os.path.join(DATA_DIR, "users.csv")

# users.csv 컬럼 예: user_id, username, password_hash, display_name, created_at, ...
# bio, avatar_path는 없을 수 있으므로 안전하게 처리

def _load_users():
    return read_csv(USERS_PATH) if os.path.exists(USERS_PATH) else []

def _save_users(rows):
    # 컬럼 합치기(누락 컬럼 자동 추가)
    base_cols = ["user_id", "username", "password_hash", "display_name", "created_at", "bio", "avatar_path"]

    # 모든 행의 키 유니온
    keys = set()
    for r in rows:
        keys.update(r.keys())
    fieldnames = list(dict.fromkeys(base_cols + list(keys)))

    # 모든 행을 동일 키 집합으로 정규화
    normalized_rows = []
    for r in rows:
        normalized_rows.append({k: r.get(k, "") for k in fieldnames})

    # csv_repo.write_csv는 fieldnames 인자를 받지 않음
    write_csv(USERS_PATH, normalized_rows)


def get_profile(user_id: str) -> Optional[Dict]:
    for r in _load_users():
        if r.get("user_id") == user_id:
            # 누락 필드 보정
            r.setdefault("display_name", r.get("username", ""))
            r.setdefault("bio", "")
            r.setdefault("avatar_path", "")
            return r
    return None

def update_profile(user_id: str, display_name: Optional[str]=None,
                   bio: Optional[str]=None, avatar_path: Optional[str]=None) -> bool:
    rows = _load_users()
    updated = False
    for r in rows:
        if r.get("user_id") == user_id:
            if display_name is not None:
                r["display_name"] = display_name
            if bio is not None:
                r["bio"] = bio
            if avatar_path is not None:
                r["avatar_path"] = avatar_path
            updated = True
            break
    if updated:
        _save_users(rows)
    return updated
