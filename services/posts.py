# services/posts.py
import os
from typing import List, Dict, Optional

from utils.time import now_kst_iso
from repo.csv_repo import append_csv, read_csv, write_csv, next_id
from services.tags import update_post_hashtags  # 해시태그 색인

POSTS = os.path.join("data", "posts.csv")


def create_post(author_id: str, content: str, original_post_id: Optional[str] = None) -> str:
    """
    새 게시물 생성.
    - 원본 글: content 필수
    - 리포스트: original_post_id 지정, content는 비어도 됨
    """
    if not original_post_id and (not content or not content.strip()):
        raise ValueError("content is required for original posts")

    post_id = next_id("post")
    row = {
        "post_id": post_id,
        "author_id": author_id,
        "content": (content or "").strip(),
        "created_at": now_kst_iso(),
        "original_post_id": original_post_id or "",
        "is_deleted": "0",
    }
    append_csv(POSTS, row)

    # 원본 글(본문 있는 경우)에 한해 해시태그 자동 색인
    if row["content"]:
        update_post_hashtags(post_id, row["content"])

    return post_id


def list_feed(limit: int = 50) -> List[Dict[str, str]]:
    """
    삭제되지 않은 최신 글을 최신순으로 최대 limit개 반환
    """
    rows = read_csv(POSTS)
    rows = [r for r in rows if r.get("is_deleted") != "1"]
    rows.sort(key=lambda r: r["created_at"], reverse=True)
    return rows[:limit]


def get_post(post_id: str) -> Optional[Dict[str, str]]:
    """
    post_id로 단일 게시물 행 반환 (없으면 None)
    """
    rows = read_csv(POSTS)
    for r in rows:
        if r["post_id"] == post_id:
            return r
    return None


def soft_delete_post(post_id: str, actor_id: str) -> None:
    """
    소프트 삭제: 해당 행의 is_deleted=1 로 마킹.
    - 본인 글만 삭제 가능
    - 리포스트/원본 모두 동일 정책
    """
    rows = read_csv(POSTS)
    changed = False
    for r in rows:
        if r["post_id"] == post_id:
            if r["author_id"] != actor_id:
                raise PermissionError("you can delete only your own posts")
            if r.get("is_deleted") == "1":
                return
            r["is_deleted"] = "1"
            changed = True
            break
    if changed:
        write_csv(POSTS, rows)


def restore_post(post_id: str, actor_id: str) -> None:
    """
    소프트 삭제 복구: is_deleted=0 으로 되돌림.
    - 본인 글만 복구 가능
    - 실제 운영에선 별도 '보관함' 화면에서 노출하는 것을 권장
    """
    rows = read_csv(POSTS)
    changed = False
    for r in rows:
        if r["post_id"] == post_id:
            if r["author_id"] != actor_id:
                raise PermissionError("you can restore only your own posts")
            if r.get("is_deleted") == "0":
                return
            r["is_deleted"] = "0"
            changed = True
            break
    if changed:
        write_csv(POSTS, rows)
