import os
from typing import List, Dict, Optional
from utils.time import now_kst_iso
from repo.csv_repo import append_csv, read_csv, next_id
from services.tags import update_post_hashtags   # ★ 추가

POSTS = os.path.join("data", "posts.csv")

def create_post(author_id: str, content: str, original_post_id: Optional[str] = None) -> str:
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

    # ★ 해시태그 색인 (원본 텍스트가 있을 때만)
    if row["content"]:
        update_post_hashtags(post_id, row["content"])

    return post_id

def list_feed(limit: int = 50) -> List[Dict[str, str]]:
    rows = read_csv(POSTS)
    rows = [r for r in rows if r.get("is_deleted") != "1"]
    rows.sort(key=lambda r: r["created_at"], reverse=True)
    return rows[:limit]

