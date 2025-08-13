import os
import re
import html
import streamlit as st

from datetime import datetime, timedelta

from services.posts import (
    create_post, list_feed, get_post,
    soft_delete_post, restore_post
)
from services.reactions import toggle_like, count_likes, user_liked
from services.tags import list_posts_by_hashtag
from services.comments import create_comment, list_comments, count_comments
from services.follows import follow, unfollow, is_following, get_following
from repo.csv_repo import read_csv

# ---- App Setup --------------------------------------------------------------
st.set_page_config(page_title="My Social Feed", page_icon="🗞️", layout="centered")
st.title("My Social Feed")

CURRENT_USER = "u_0001"
DATA_DIR = "data"
POSTS_PATH = os.path.join(DATA_DIR, "posts.csv")
POST_TAGS_PATH = os.path.join(DATA_DIR, "post_hashtags.csv")
ACTIVITY_PATH = os.path.join(DATA_DIR, "activity_log.csv")

# ---- Helpers ----------------------------------------------------------------
def _all_posts_map() -> dict:
    rows = read_csv(POSTS_PATH) if os.path.exists(POSTS_PATH) else []
    return {r["post_id"]: r for r in rows}

def _post_hashtags(post_id: str):
    if not os.path.exists(POST_TAGS_PATH):
        return []
    return [row["hashtag"] for row in read_csv(POST_TAGS_PATH) if row["post_id"] == post_id]

def _matches_query(post_row: dict, q: str, all_posts_map: dict) -> bool:
    """
    q(소문자)로 본문/작성자 매칭.
    - 일반 글: 자신의 content/author_id 검사
    - 리포스트: 원본이 있으면 원본 content/author_id로 검사
    """
    q = (q or "").strip().lower()
    if not q:
        return True
    # 리포스트면 원본 row로 스왑
    orig_id = post_row.get("original_post_id", "")
    row = all_posts_map.get(orig_id, post_row) if orig_id else post_row
    content = (row.get("content") or "").lower()
    author  = (row.get("author_id") or "").lower()
    return (q in content) or (q in author)

def _highlight(text: str, q: str) -> str:
    """
    본문에 검색어 q(공백 구분 여러 단어 가능)를 <mark>로 하이라이트.
    - 대소문자 무시
    - HTML 이스케이프 처리
    """
    if not text:
        return ""
    esc = html.escape(text)
    q = (q or "").strip()
    if not q:
        return esc
    
def _created_at_dt(row: dict) -> datetime:
    """ISO created_at → datetime (파싱 실패 시 1970-01-01 반환)"""
    try:
      return datetime.fromisoformat(row.get("created_at", ""))
    except Exception:
      return datetime(1970, 1, 1)
    
    # 공백으로 분리된 여러 토큰을 각각 강조 (중복 토큰 제거)
    tokens = [t for t in {t.lower() for t in q.split() if t.strip()} if t]
    if not tokens:
        return esc
    # 토큰 길이 긴 순으로 치환(부분 중복 방지)
    tokens.sort(key=len, reverse=True)
    # 단어 경계 제한 없이 단순 부분 매칭 (한글 포함)
    for t in tokens:
        pattern = re.compile(re.escape(t), flags=re.IGNORECASE)
        esc = pattern.sub(lambda m: f"<mark>{m.group(0)}</mark>", esc)
    return esc

def _load_posts(scope: str):
    """
    scope: 'all' | 'following'
    - 해시태그 필터가 있으면 우선 적용
    - following: 내가 팔로우한 사람들 + 나 자신만
    - 마지막 단계에서 '검색' 키워드 필터 적용
    """
    # 1) 해시태그 필터 우선
    if st.session_state.get("filter_tag"):
        post_ids = set(list_posts_by_hashtag(st.session_state["filter_tag"]))
        rows = list_feed(limit=500)
        rows = [r for r in rows if r["post_id"] in post_ids]
    else:
        rows = list_feed(limit=500)

    # 2) 팔로잉 범위 필터
    if scope == "following":
        following = get_following(CURRENT_USER)
        allowed_authors = following | {CURRENT_USER}
        rows = [r for r in rows if r["author_id"] in allowed_authors]

    # 3) 키워드 검색 필터(본문/작성자, 리포스트는 원본 기준)
    q = (st.session_state.get("search_q", "") or "").strip().lower()
    if q:
        all_map = _all_posts_map()
        rows = [r for r in rows if _matches_query(r, q, all_map)]

    # 4) 기간 필터
    period = st.session_state.get("sort_period", "전체")
    now = datetime.now()
    if period == "24시간":
        cutoff = now - timedelta(days=1)
        rows = [r for r in rows if _created_at_dt(r) >= cutoff]
    elif period == "7일":
        cutoff = now - timedelta(days=7)
        rows = [r for r in rows if _created_at_dt(r) >= cutoff]
    elif period == "30일":
        cutoff = now - timedelta(days=30)
        rows = [r for r in rows if _created_at_dt(r) >= cutoff]

    # 5) 정렬
    mode = st.session_state.get("sort_mode", "최신순")
    if mode == "최신순":
        rows.sort(key=lambda r: _created_at_dt(r), reverse=True)
    elif mode == "좋아요순":
        rows.sort(key=lambda r: (count_likes(r["post_id"]), _created_at_dt(r)), reverse=True)
    elif mode == "댓글순":
        rows.sort(key=lambda r: (count_comments(r["post_id"]), _created_at_dt(r)), reverse=True)

    return rows

def _activity_rows(limit=100):
    rows = read_csv(ACTIVITY_PATH) if os.path.exists(ACTIVITY_PATH) else []
    rows.sort(key=lambda r: r["created_at"], reverse=True)
    return rows[:limit]

# ---- Tabs -------------------------------------------------------------------
tab_feed, tab_activity = st.tabs(["📰 피드", "🗂️ 활동 로그"])

with tab_feed:
    # ---- Sidebar: Scope / Hashtag / Search ---------------------------------
    st.sidebar.header("보기")
    scope = st.sidebar.radio(
        "피드 범위",
        options=["전체", "팔로잉"],
        index=0 if st.session_state.get("scope", "전체") == "전체" else 1,
        horizontal=True,
    )
    st.session_state["scope"] = scope

    st.sidebar.header("해시태그 필터")
    filter_tag = st.sidebar.text_input("해시태그(# 없이 입력)", value=st.session_state.get("filter_tag", ""))
    sb_cols = st.sidebar.columns(2)
    with sb_cols[0]:
        if st.button("해시태그 적용", use_container_width=True):
            st.session_state["filter_tag"] = filter_tag.strip().lower()
            st.rerun()
    with sb_cols[1]:
        if st.button("해시태그 해제", use_container_width=True):
            st.session_state["filter_tag"] = ""
            st.rerun()

    # 🔎 검색 추가
    st.sidebar.header("검색")
    search_q = st.sidebar.text_input("키워드 (공백으로 여러 단어)", value=st.session_state.get("search_q", ""))
    sc1, sc2 = st.sidebar.columns(2)
    with sc1:
        if st.button("검색 적용", use_container_width=True):
            st.session_state["search_q"] = (search_q or "").strip()
            st.rerun()
    with sc2:
        if st.button("검색 해제", use_container_width=True):
            st.session_state["search_q"] = ""
            st.rerun()

    # --- 정렬/기간 ---
    st.sidebar.header("정렬/기간")
    sort_mode = st.sidebar.selectbox(
        "정렬",
        options=["최신순", "좋아요순", "댓글순"],
        index={"최신순":0, "좋아요순":1, "댓글순":2}.get(st.session_state.get("sort_mode", "최신순"), 0),
    )
    st.session_state["sort_mode"] = sort_mode

    period = st.sidebar.radio(
        "기간",
        options=["전체", "24시간", "7일", "30일"],
        index=["전체", "24시간", "7일", "30일"].index(st.session_state.get("sort_period", "전체")),
        horizontal=True,
    )
    st.session_state["sort_period"] = period

    # ---- New Post Form ------------------------------------------------------
    with st.form("new_post"):
        content = st.text_area(
            "무슨 생각을 하고 있나요?",
            max_chars=280,
            height=100,
            placeholder="텍스트를 입력하세요. 예) 오늘도 코딩! #python #streamlit",
        )
        submitted = st.form_submit_button("게시")
        if submitted:
            try:
                create_post(author_id=CURRENT_USER, content=content)
                st.success("작성 완료!")
                st.rerun()
            except Exception as e:
                st.error(f"오류: {e}")

    # ---- Feed ---------------------------------------------------------------
    st.subheader("피드")
    ALL_POSTS = _all_posts_map()
    scope_key = "all" if scope == "전체" else "following"
    posts = _load_posts(scope_key)

    active_query = (st.session_state.get("search_q", "") or "").strip()

    for p in posts:
        with st.container(border=True):
            # 상단: 작성자/시간 + 팔로우 토글 (내 글이면 숨김)
            left, right = st.columns([0.70, 0.30])
            with left:
                st.caption(f"작성자: {p['author_id']} · {p['created_at']}")
            with right:
                if p["author_id"] != CURRENT_USER:
                    following_now = is_following(CURRENT_USER, p["author_id"])
                    label = "언팔로우" if following_now else "팔로우"
                    if st.button(label, key=f"follow-{p['author_id']}-{p['post_id']}"):
                        if following_now:
                            ok = unfollow(CURRENT_USER, p["author_id"])
                            st.toast("언팔로우 완료" if ok else "이미 언팔로우 상태")
                        else:
                            ok = follow(CURRENT_USER, p["author_id"])
                            st.toast("팔로우 완료" if ok else "팔로우할 수 없습니다")
                        st.rerun()

            is_repost = bool(p["original_post_id"])
            interactions_enabled = True
            tags_to_show = []

            # 본문/원본 표시 및 정책 처리
            if is_repost:
                st.caption("🔁 리포스트")
                orig = ALL_POSTS.get(p["original_post_id"])
                if (orig is None) or (orig.get("is_deleted") == "1"):
                    st.warning("삭제된 게시물")
                    if orig is not None:
                        st.caption(f"원본 메타: 작성자 {orig.get('author_id','?')} · {orig.get('created_at','?')}")
                    else:
                        st.caption("원본 메타: 알 수 없음")
                    interactions_enabled = False
                    tags_to_show = []
                else:
                    st.caption(f"원본: {orig['author_id']} · {orig['created_at']}")
                    # 하이라이트 적용: 원본 본문
                    orig_content = orig.get("content") or "_(본문 없음)_"
                    if active_query:
                        st.markdown(_highlight(orig_content, active_query), unsafe_allow_html=True)
                    else:
                        st.write(orig_content)
                    tags_to_show = _post_hashtags(orig["post_id"])
            else:
                # 일반 포스트 본문 (하이라이트 적용)
                content_to_show = p["content"] if p["content"] else "_(본문 없음)_"
                if active_query:
                    st.markdown(_highlight(content_to_show, active_query), unsafe_allow_html=True)
                else:
                    st.write(content_to_show)
                tags_to_show = _post_hashtags(p["post_id"])

            # 해시태그 칩
            if tags_to_show:
                tag_cols = st.columns(min(4, len(tags_to_show)))
                for i, t in enumerate(tags_to_show):
                    with tag_cols[i % len(tag_cols)]:
                        if st.button(f"#{t}", key=f"tag-{p['post_id']}-{t}"):
                            st.session_state["filter_tag"] = t
                            st.rerun()

            # 하단 버튼: 좋아요 / 리포스트 / 댓글
            cols = st.columns(3)
            with cols[0]:
                liked_now = user_liked(p["post_id"], CURRENT_USER)
                like_label = f"{'❤️' if liked_now else '🤍'} 좋아요 ({count_likes(p['post_id'])})"
                if st.button(like_label, key=f"like-{p['post_id']}", disabled=not interactions_enabled):
                    liked, _ = toggle_like(p["post_id"], CURRENT_USER)
                    st.toast(("좋아요 해제", "좋아요 추가")[liked])
                    st.rerun()

            with cols[1]:
                if st.button("🔁 리포스트", key=f"rt-{p['post_id']}", disabled=not interactions_enabled):
                    try:
                        create_post(author_id=CURRENT_USER, content="", original_post_id=p["post_id"])
                        st.success("리포스트 완료!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"오류: {e}")

            with cols[2]:
                st.button("💬 댓글", key=f"cm-btn-{p['post_id']}", disabled=not interactions_enabled)

            # 삭제/복구 UI (내 글만)
            is_my_post = (p["author_id"] == CURRENT_USER)
            if is_my_post:
                with st.expander("게시물 관리", expanded=False):
                    c1, c2 = st.columns(2)
                    with c1:
                        if st.button("🗑️ 삭제", key=f"del-{p['post_id']}"):
                            try:
                                soft_delete_post(p["post_id"], CURRENT_USER)
                                st.success("삭제 완료 (소프트 딜리트)")
                                st.rerun()
                            except Exception as e:
                                st.error(f"오류: {e}")
                    with c2:
                        if st.button("↩️ 복구(실험용)", key=f"restore-{p['post_id']}"):
                            try:
                                restore_post(p["post_id"], CURRENT_USER)
                                st.success("복구 완료")
                                st.rerun()
                            except Exception as e:
                                st.error(f"오류: {e}")

            # ----- 댓글 섹션 --------------------------------------------------
            st.markdown("---")
            st.caption(f"💬 댓글 {count_comments(p['post_id'])}개")

            comments = list_comments(p["post_id"])
            roots = [c for c in comments if not c["parent_comment_id"]]
            replies_by_parent = {}
            for c in comments:
                pid = c["parent_comment_id"]
                if pid:
                    replies_by_parent.setdefault(pid, []).append(c)

            for c in roots:
                with st.container():
                    st.markdown(f"**{c['author_id']}** · {c['created_at']}")
                    # 댓글 본문도 하이라이트
                    c_body = c["content"]
                    if active_query:
                        st.markdown(_highlight(c_body, active_query), unsafe_allow_html=True)
                    else:
                        st.write(c_body)

                    for rc in replies_by_parent.get(c["comment_id"], []):
                        with st.container():
                            st.markdown(f"&nbsp;&nbsp;↳ **{rc['author_id']}** · {rc['created_at']}")
                            rc_body = rc["content"]
                            if active_query:
                                st.markdown(f"&nbsp;&nbsp;{_highlight(rc_body, active_query)}", unsafe_allow_html=True)
                            else:
                                st.write(f"&nbsp;&nbsp;{rc_body}")

                    # 대댓글 작성
                    reply_key = f"reply-{p['post_id']}-{c['comment_id']}"
                    with st.form(reply_key, clear_on_submit=True):
                        sub = st.text_input("대댓글 달기", key=f"reply-input-{reply_key}", placeholder="대댓글을 입력하세요")
                        sbm = st.form_submit_button("등록", disabled=not interactions_enabled)
                        if sbm:
                            try:
                                create_comment(
                                    post_id=p["post_id"],
                                    author_id=CURRENT_USER,
                                    content=sub,
                                    parent_comment_id=c["comment_id"],
                                )
                                st.success("대댓글 작성 완료!")
                                st.rerun()
                            except Exception as e:
                                st.error(f"오류: {e}")

            # 루트 댓글 작성
            with st.form(f"comment-{p['post_id']}", clear_on_submit=True):
                comment_text = st.text_input("댓글 달기", placeholder="댓글을 입력하세요")
                c_submit = st.form_submit_button("등록", disabled=not interactions_enabled)
                if c_submit:
                    try:
                        create_comment(post_id=p["post_id"], author_id=CURRENT_USER, content=comment_text)
                        st.success("댓글 작성 완료!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"오류: {e}")

with tab_activity:
    st.subheader("최근 활동 로그")
    st.caption("POST/REPOST/DELETE/RESTORE/REACTION/COMMENT/USER_FOLLOW 등 이벤트")
    rows = _activity_rows(limit=100)
    if not rows:
        st.info("로그가 아직 없습니다.")
    else:
        show_cols = ["created_at", "event_type", "actor_id", "target_type", "target_id", "metadata"]
        for r in rows:
            line = " | ".join(str(r.get(c, "")) for c in show_cols)
            st.text(line)
