# services/auth.py
import os
import hashlib
from typing import Optional, Dict
from utils.time import now_kst_iso
from repo.csv_repo import read_csv, write_csv, append_csv, next_id

USERS = os.path.join("data", "users.csv")

def _hash(pw: str) -> str:
    # 교육용 간단 해시 (실서비스용 아님: salt/bcrypt 권장)
    return hashlib.sha256(pw.encode("utf-8")).hexdigest()

def _load_users():
    return read_csv(USERS)

def _find_by_username(username: str) -> Optional[Dict[str, str]]:
    uname = (username or "").strip().lower()
    for r in _load_users():
        if (r.get("username") or "").lower() == uname:
            return r
    return None

def try_signup(username: str, password: str, display_name: Optional[str] = None) -> str:
    """
    회원가입: 중복 아이디 체크 후 생성, 반환값은 user_id
    """
    if not username or not password:
        raise ValueError("username/password is required")
    if _find_by_username(username):
        raise ValueError("이미 존재하는 사용자명입니다.")

    uid = next_id("user")
    row = {
        "user_id": uid,
        "username": username.strip(),
        "password_hash": _hash(password),
        "display_name": (display_name or username).strip(),
        "created_at": now_kst_iso(),
    }
    append_csv(USERS, row)
    return uid

def try_login(username: str, password: str) -> Optional[str]:
    """
    로그인: 성공 시 user_id 반환, 실패 시 None
    """
    r = _find_by_username(username)
    if not r:
        return None
    if r.get("password_hash") != _hash(password):
        return None
    return r.get("user_id")

def get_current_user_id(st) -> Optional[str]:
    """
    Streamlit 세션에서 현재 로그인 사용자 반환 (없으면 None)
    """
    return st.session_state.get("auth_user_id")

def set_current_user_id(st, user_id: Optional[str]) -> None:
    """
    세션에 현재 사용자 설정/해제
    """
    if user_id is None:
        st.session_state.pop("auth_user_id", None)
    else:
        st.session_state["auth_user_id"] = user_id

def get_display_name(user_id: str) -> str:
    """
    user_id → display_name 조회 (없으면 user_id)
    """
    for r in _load_users():
        if r.get("user_id") == user_id:
            return r.get("display_name") or r.get("username") or user_id
    return user_id

def get_username(user_id: str) -> str:
    """
    user_id → username 조회 (없으면 user_id 반환)
    """
    for r in _load_users():
        if r.get("user_id") == user_id:
            return r.get("username") or user_id
    return user_id

def get_user_by_id(user_id: str):
    """
    users.csv 에서 user_id로 한 명 조회 (없으면 None)
    """
    for r in _load_users():
        if r.get("user_id") == user_id:
            return r
    return None