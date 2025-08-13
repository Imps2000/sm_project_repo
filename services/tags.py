import os
from typing import List, Set
from utils.time import now_kst_iso
from utils.hashtags import extract_hashtags
from repo.csv_repo import read_csv, write_csv

HASHTAGS = os.path.join("data", "hashtags.csv")
POST_TAGS = os.path.join("data", "post_hashtags.csv")

def _ensure_files():
    # 최소 헤더는 처음에 CMD로 만들어둠 (이미 있음)
    for path, header in [
        (HASHTAGS, ["hashtag", "first_seen_at", "last_seen_at"]),
        (POST_TAGS, ["post_id", "hashtag"]),
    ]:
        if not os.path.exists(path):
            write_csv(path, [])  # 빈 파일 생성

def update_post_hashtags(post_id: str, content: str) -> List[str]:
    """
    포스트 본문에서 해시태그를 추출하여
    - hashtags.csv: 신규 태그 first_seen_at, last_seen_at 갱신
    - post_hashtags.csv: (post_id, tag) 매핑 추가(중복 방지)
    반환: 이번 포스트에서 추출된 태그 리스트
    """
    _ensure_files()
    tags = extract_hashtags(content or "")
    if not tags:
        return []

    # load
    hashtags = read_csv(HASHTAGS)
    post_tags = read_csv(POST_TAGS)

    now = now_kst_iso()
    existing_tags: Set[str] = {row["hashtag"] for row in hashtags}
    existing_pairs: Set[tuple] = {(row["post_id"], row["hashtag"]) for row in post_tags}

    # upsert hashtags table
    changed = False
    for t in tags:
        if t not in existing_tags:
            hashtags.append({"hashtag": t, "first_seen_at": now, "last_seen_at": now})
            existing_tags.add(t)
            changed = True
        else:
            # update last_seen_at
            for row in hashtags:
                if row["hashtag"] == t:
                    row["last_seen_at"] = now
                    changed = True
                    break
    if changed:
        # keep field order
        write_csv(HASHTAGS, hashtags)

    # upsert post_hashtags (no duplicates)
    changed = False
    for t in tags:
        key = (post_id, t)
        if key not in existing_pairs:
            post_tags.append({"post_id": post_id, "hashtag": t})
            existing_pairs.add(key)
            changed = True
    if changed:
        write_csv(POST_TAGS, post_tags)

    return tags

def list_posts_by_hashtag(tag: str) -> List[str]:
    """해시태그로 post_id 목록을 반환"""
    _ensure_files()
    tag = (tag or "").lower()
    return [row["post_id"] for row in read_csv(POST_TAGS) if row["hashtag"] == tag]
