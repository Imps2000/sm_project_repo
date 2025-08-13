# services/comments.py
import os
from typing import List, Dict, Optional
from repo.csv_repo import read_csv, write_csv, append_csv, next_id
from utils.time import now_kst_iso
from services.activity import log_event  # ★ 활동 로그

COMMENTS = os.path.join("data", "comments.csv")

def create_comment(post_id: str, author_id: str, content: str, parent_comment_id: Optional[str] = None) -> str:
    if not content or not content.strip():
        raise ValueError("comment content is required")
    # 1단계 대댓글만 허용
    if parent_comment_id:
        rows = read_csv(COMMENTS)
        parent = next((r for r in rows if r["comment_id"] == parent_comment_id), None)
        if not parent:
            raise ValueError("parent comment not found")
        if parent.get("parent_comment_id"):
            raise ValueError("only one-level replies are allowed")

    cid = next_id("comment")
    row = {
        "comment_id": cid,
        "post_id": post_id,
        "author_id": author_id,
        "content": content.strip(),
        "created_at": now_kst_iso(),
        "parent_comment_id": parent_comment_id or "",
        "is_deleted": "0",
    }
    append_csv(COMMENTS, row)

    log_event(
        event_type="COMMENT_CREATED",
        actor_id=author_id,
        target_type="Comment",
        target_id=cid,
        metadata={"post_id": post_id, "preview": row["content"][:40]},
    )
    return cid

def list_comments(post_id: str) -> List[Dict[str, str]]:
    rows = [r for r in read_csv(COMMENTS) if r["post_id"] == post_id and r.get("is_deleted") != "1"]
    rows.sort(key=lambda r: r["created_at"])
    return rows

def delete_comment(comment_id: str, actor_id: str) -> None:
    rows = read_csv(COMMENTS)
    changed = False
    for r in rows:
        if r["comment_id"] == comment_id:
            r["is_deleted"] = "1"
            changed = True
            break
    if changed:
        write_csv(COMMENTS, rows)
        log_event(
            event_type="COMMENT_DELETED",
            actor_id=actor_id,
            target_type="Comment",
            target_id=comment_id,
            metadata={},
        )

def count_comments(post_id: str) -> int:
    return sum(1 for r in read_csv(COMMENTS) if r["post_id"] == post_id and r.get("is_deleted") != "1")
