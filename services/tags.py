import os
import re
from typing import List, Set, Iterable
from utils.time import now_kst_iso
from utils.hashtags import extract_hashtags
from repo.csv_repo import read_csv, write_csv

HASHTAGS = os.path.join("data", "hashtags.csv")
POST_TAGS = os.path.join("data", "post_hashtags.csv")


def _ensure_files():
    """
    필요 CSV가 없으면 빈 파일로 생성.
    (헤더는 최초 프로젝트 세팅 때 만들었으니 여기선 내용만 보장)
    """
    for path in [HASHTAGS, POST_TAGS]:
        if not os.path.exists(path):
            write_csv(path, [])


# ----------------------------
# [A] 본문에서 자동 추출해 저장
# ----------------------------
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
    """해시태그로 post_id 목록을 반환 (정규화는 호출 측에서 했다고 가정하되, 여기서도 소문자화)"""
    _ensure_files()
    tag = (tag or "").lower()
    return [row["post_id"] for row in read_csv(POST_TAGS) if row["hashtag"] == tag]


# ----------------------------
# [B] 수동 입력(칩) 태그 저장
# ----------------------------
def _normalize_tag(raw: str) -> str:
    """
    수동 입력된 태그를 저장용으로 정규화:
    - 앞뒤 공백 제거, 앞의 # 제거
    - 소문자화
    - 연속 공백은 단일 하이픈(-)으로
    - 허용: 한글/영문/숫자/언더바(_) / 하이픈(-)
    - 길이 1~30자만 허용
    """
    if not raw:
        return ""
    s = raw.strip()
    if s.startswith("#"):
        s = s[1:]
    s = s.lower()
    # 공백류 → 하이픈
    s = re.sub(r"\s+", "-", s)
    # 허용 문자만 남기기
    s = re.sub(r"[^0-9a-zA-Zㄱ-ㅎ가-힣_-]", "", s)
    # 길이 제한
    if not (1 <= len(s) <= 30):
        return ""
    return s


def add_hashtags(post_id: str, tags: Iterable[str]) -> List[str]:
    """
    칩 UI 등에서 수동 입력된 태그들을 저장.
    - 입력 태그들을 정규화(_normalize_tag)
    - hashtags.csv: 신규 태그는 first_seen_at/last_seen_at, 기존 태그는 last_seen_at 갱신
    - post_hashtags.csv: (post_id, hashtag) 매핑 upsert (중복 방지)
    반환: 실제로 추가(또는 갱신)된 태그 목록(정규화 후)
    """
    _ensure_files()
    # 정규화 + 공백/빈값/중복 제거
    normed = []
    seen = set()
    for raw in (tags or []):
        t = _normalize_tag(str(raw))
        if not t:
            continue
        if t in seen:
            continue
        seen.add(t)
        normed.append(t)

    if not normed:
        return []

    hashtags = read_csv(HASHTAGS)
    post_tags = read_csv(POST_TAGS)

    now = now_kst_iso()
    existing_tags: Set[str] = {row["hashtag"] for row in hashtags}
    existing_pairs: Set[tuple] = {(row["post_id"], row["hashtag"]) for row in post_tags}

    # upsert hashtags table
    changed_ht = False
    for t in normed:
        if t not in existing_tags:
            hashtags.append({"hashtag": t, "first_seen_at": now, "last_seen_at": now})
            existing_tags.add(t)
            changed_ht = True
        else:
            # update last_seen_at
            for row in hashtags:
                if row["hashtag"] == t:
                    row["last_seen_at"] = now
                    changed_ht = True
                    break
    if changed_ht:
        write_csv(HASHTAGS, hashtags)

    # upsert post_hashtags
    changed_pt = False
    for t in normed:
        key = (post_id, t)
        if key not in existing_pairs:
            post_tags.append({"post_id": post_id, "hashtag": t})
            existing_pairs.add(key)
            changed_pt = True
    if changed_pt:
        write_csv(POST_TAGS, post_tags)

    return normed