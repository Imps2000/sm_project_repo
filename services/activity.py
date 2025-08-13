    # services/activity.py
import os
import json
from typing import Optional, Dict, Any
from utils.time import now_kst_iso
from repo.csv_repo import append_csv, next_id

LOG_PATH = os.path.join("data", "activity_log.csv")

def log_event(
    event_type: str,
    actor_id: str,
    target_type: str,
    target_id: str,
    metadata: Optional[Dict[str, Any]] = None,
) -> str:
    """
    activity_log.csv 에 이벤트 한 줄을 기록한다.
    - event_type: 예) POST_CREATED, REPOST_CREATED, POST_DELETED, POST_RESTORED,
                   REACTION_ADDED, REACTION_REMOVED, COMMENT_CREATED
    - actor_id: 수행자 user_id
    - target_type: 'Post' | 'Comment' | 'Reaction' 등
    - target_id: 대상의 id (post_id/comment_id 등)
    - metadata: 추가 정보(dict) → JSON 문자열로 저장
    """
    log_id = next_id("log")
    row = {
        "log_id": log_id,
        "event_type": event_type,
        "actor_id": actor_id,
        "target_type": target_type,
        "target_id": target_id,
        "metadata": json.dumps(metadata or {}, ensure_ascii=False),
        "created_at": now_kst_iso(),
    }
    # activity_log.csv는 초기 헤더가 이미 만들어져 있다고 가정
    append_csv(LOG_PATH, row)
    return log_id
