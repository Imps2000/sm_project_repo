import os
import re
import html
import streamlit as st

from services.auth import (
    try_signup, try_login,
    get_current_user_id, set_current_user_id,
    get_display_name, get_user_by_id
)
from services.auth import get_username

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

from services.profile import get_profile, update_profile
from services.follows import get_followers  # 새 함수
# ---- App Setup --------------------------------------------------------------
st.set_page_config(page_title="My Social Feed", page_icon="🗞️", layout="centered")
st.title("My Social Feed")
# 로그인된 사용자 세션에서 읽기 (없으면 None)
CURRENT_USER = get_current_user_id(st)
DATA_DIR = "data"
AVATAR_DIR = os.path.join(DATA_DIR, "avatars")
os.makedirs(AVATAR_DIR, exist_ok=True)
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

def _created_at_dt(row: dict) -> datetime:
    """ISO created_at → datetime (파싱 실패 시 1970-01-01 반환)"""
    try:
        return datetime.fromisoformat(row.get("created_at", ""))
    except Exception:
        return datetime(1970, 1, 1)

def _load_posts(scope: str):
    """
    scope: 'all' | 'following'
    - 해시태그 필터가 있으면 우선 적용
    - following: 내가 팔로우한 사람들 + 나 자신만
    - 마지막 단계에서 '검색' 키워드 필터 적용
    - (추가) 기간 필터 + 정렬
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

# ---- Auth Gate (로그인/회원가입) --------------------------------------------
if CURRENT_USER is None:
    st.header("🔐 로그인 / 회원가입")

    # 로그인 / 회원가입 탭
    tab_login, tab_signup = st.tabs(["로그인", "회원가입"])

    # 공용 상단 안내 (회원가입 직후)
    if st.session_state.get("signup_done"):
        st.success("회원가입이 완료되었습니다! 이제 로그인하세요.")

    # ----- 로그인 탭 -----
    with tab_login:
        # 회원가입 직후라면 추가 안내 + 아이디 프리필
        if st.session_state.get("signup_done"):
            st.info("아래에 아이디를 확인하고 로그인해 주세요.")

        with st.form("login_form", clear_on_submit=False):
            li_user = st.text_input(
                "아이디(사용자명)",
                value=st.session_state.get("post_signup_username", ""),
                key="li_user",
            )
            li_pw = st.text_input("비밀번호", type="password", key="li_pw")
            ok = st.form_submit_button("로그인", use_container_width=True)
            if ok:
                uid = try_login(li_user.strip(), li_pw)
                if uid:
                    set_current_user_id(st, uid)
                    st.success("로그인 성공!")
                    # 회원가입 상태/프리필 정리
                    st.session_state.pop("post_signup_username", None)
                    st.session_state.pop("signup_done", None)
                    st.rerun()
                else:
                    st.error("아이디 또는 비밀번호가 올바르지 않습니다.")

    # ----- 회원가입 탭 -----
    with tab_signup:
        if st.session_state.get("signup_done"):
            # 입력 폼 숨기고 안내만 표시
            st.info("회원가입이 완료되었습니다. 로그인 탭으로 이동해 로그인해 주세요.")
            # 원하면 폼을 다시 열 수 있음
            if st.button("🔄 회원가입 입력 다시 열기", use_container_width=True):
                st.session_state["signup_done"] = False
                st.rerun()
        else:
            with st.form("signup_form", clear_on_submit=False):
                su_user = st.text_input("아이디(사용자명)", key="su_user")
                su_pw = st.text_input("비밀번호", type="password", key="su_pw")
                su_name = st.text_input("표시 이름(선택)", key="su_name")
                ok2 = st.form_submit_button("회원가입", use_container_width=True)
                if ok2:
                    try:
                        _ = try_signup(su_user.strip(), su_pw, su_name.strip() or None)
                        # 상태 저장 후 즉시 새로고침 → 상단 성공 배너/폼 숨김 반영
                        st.session_state["post_signup_username"] = su_user.strip()
                        st.session_state["signup_done"] = True
                        st.rerun()
                    except Exception as e:
                        st.error(f"회원가입 실패: {e}")

    st.stop()

# ---- Main Menu (Feed / Profile) --------------------------------------------

if "nav_to" in st.session_state:
    st.session_state["main_menu"] = st.session_state.pop("nav_to")

# 기본값 보정
if "main_menu" not in st.session_state:
    st.session_state["main_menu"] = "피드"

# 라디오 생성 (유일한 라디오, key='main_menu')
menu = st.sidebar.radio("메뉴", ["피드", "내 프로필"], horizontal=True, key="main_menu")
if menu == "피드" and st.session_state.get("view_user_id"):
    st.session_state.pop("view_user_id", None)
    
if menu == "피드":
    # ---- Tabs -------------------------------------------------------------------
    tab_feed, tab_activity = st.tabs(["📰 피드", "🗂️ 활동 로그"])

    with tab_feed:
        # ---- Sidebar: Account / Scope / Hashtag / Search ------------------------
        with st.sidebar:
            _disp = get_display_name(CURRENT_USER)
            _handle = get_username(CURRENT_USER)
            st.markdown(f"**계정:** {_disp} · @{_handle}")

            # (선택) 개발자 정보 보기 - 내부 ID를 원할 때만 토글로 노출
            _dev = st.checkbox("🔧 내부ID(개발자용 후에 표기삭제)", value=False)
            if _dev:
                st.caption(f"internal_id: `{CURRENT_USER}`")

            if st.button("로그아웃", key="logout-btn"):
                set_current_user_id(st, None)
                st.success("로그아웃 되었습니다.")
                st.rerun()

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
            index={"최신순": 0, "좋아요순": 1, "댓글순": 2}.get(st.session_state.get("sort_mode", "최신순"), 0),
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

        # 🔎 프로필에서 넘어온 "특정 글만 보기" 포커스
        focus_id = st.session_state.get("focus_post_id")
        if focus_id:
            focused = [r for r in posts if r.get("post_id") == focus_id]
            if focused:
                posts = focused
                st.info("선택한 게시물만 표시 중")
                if st.button("⬅️ 모두 보기", key="clear-focus"):
                    st.session_state.pop("focus_post_id", None)
                    st.rerun()
            else:
                # 포커스 대상이 없으면 상태 정리
                st.session_state.pop("focus_post_id", None)

        for p in posts:
            with st.container(border=True):
                # 상단: 작성자/시간 + 팔로우 토글 (내 글이면 숨김)
                left, right = st.columns([0.70, 0.30])
                with left:
                    author_id = p["author_id"]
                    author_disp = get_display_name(author_id) or author_id
                    author_handle = get_username(author_id) or author_id
                    st.caption(f"{p['created_at']}")

                    # 작성자 이름/핸들을 클릭하면 프로필로 이동
                    if st.button(f"👤 {author_disp} · @{author_handle}", key=f"open-prof-{p['post_id']}", use_container_width=False):
                        st.session_state["nav_to"] = "내 프로필"
                        st.session_state["view_user_id"] = author_id
                        st.rerun()

                with right:
                    if p["author_id"] != CURRENT_USER:
                        if st.button("프로필 보기", key=f"viewprof-{p['post_id']}"):
                            st.session_state["nav_to"] = "내 프로필"
                            st.session_state["view_user_id"] = p["author_id"]
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
                        st.markdown('<div style="margin-left: 1.25rem">', unsafe_allow_html=True)  # 시각적 들여쓰기
                        with st.expander("↳ 대댓글 달기", expanded=False):
                            form_key = f"rform-{p['post_id']}-{c['comment_id']}"
                            with st.form(form_key, clear_on_submit=True):
                                # 더 작게: 한 줄 입력 + 좁은 레이아웃
                                col_in, col_btn = st.columns([0.80, 0.20])
                                with col_in:
                                    sub = st.text_input(
                                        label="대댓글 달기",
                                        key=f"rinput-{p['post_id']}-{c['comment_id']}",
                                        placeholder="대댓글을 입력하세요",
                                        label_visibility="collapsed",
                                    )
                                with col_btn:
                                    sbm = st.form_submit_button("등록", disabled=not interactions_enabled, use_container_width=True)

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
                        st.markdown('</div>', unsafe_allow_html=True)

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

# ---- Profile Page ------------------------------------------------------------
if menu == "내 프로필":
    # (추가) 어떤 프로필을 볼지 결정: 기본은 나, 피드에서 넘어오면 view_user_id 사용
    target_user_id = st.session_state.get("view_user_id", CURRENT_USER)
    is_me = (target_user_id == CURRENT_USER)

    # (추가) 공통 프로필 정보 로드
    target = get_user_by_id(target_user_id) or {}
    disp = target.get("display_name") or target.get("username") or target_user_id
    handle = get_username(target_user_id) or target_user_id

    # (추가) 헤더/서브헤더
    st.header("👤 프로필")
    st.subheader(f"{disp}")
    st.caption(f"@{handle} · 가입일: {target.get('created_at','N/A')}")

    if not is_me:
        top_cols = st.columns([0.5, 0.5])
        with top_cols[0]:
            # 피드로 돌아가기
            if st.button("⬅️ 피드로", key="back-to-feed"):
                st.session_state["nav_to"] = "피드"
                st.session_state.pop("view_user_id", None)
                st.rerun()
        with top_cols[1]:
            # 팔로우/언팔로우 토글
            following_now = is_following(CURRENT_USER, target_user_id)
            fl_label = "언팔로우" if following_now else "팔로우"
            if st.button(fl_label, key=f"follow-on-prof-{target_user_id}"):
                if following_now:
                    unfollow(CURRENT_USER, target_user_id)
                    st.success("언팔로우 완료")
                else:
                    follow(CURRENT_USER, target_user_id)
                    st.success("팔로우 완료")
                st.rerun()

        st.markdown("---")
        st.subheader("📜 게시글")
        others_posts = [r for r in list_feed(limit=200) if r.get("author_id") == target_user_id]
        if not others_posts:
            st.info("게시글이 없습니다.")
        else:
            for p in others_posts:
                with st.container(border=True):
                    st.caption(f"{p.get('created_at','')}")
                    st.write(p.get("content") or "_(본문 없음)_")

                    tags = _post_hashtags(p["post_id"])
                    if tags:
                        tag_cols = st.columns(min(4, len(tags)))
                        for i, t in enumerate(tags):
                            with tag_cols[i % len(tag_cols)]:
                                st.button(f"#{t}", key=f"othertag-{p['post_id']}-{t}", disabled=True)

                    likes = count_likes(p["post_id"])
                    cmts  = count_comments(p["post_id"])
                    st.caption(f"❤️ {likes} · 💬 {cmts}")

                    if st.button("👀 피드에서 보기", key=f"goto-feed-from-other-{p['post_id']}"):
                        st.session_state["nav_to"] = "피드"
                        st.session_state["focus_post_id"] = p["post_id"]
                        st.rerun()

        # 여기서 종료 → 아래의 "내 프로필" UI는 실행되지 않음
        st.stop()

    # 탭: 프로필 / 내 글 / 내 활동
    t_profile, t_my_posts, t_my_activity = st.tabs(["프로필", "내 글", "내 활동"])

    # ========== 프로필 탭 ==========
    with t_profile:
        me = get_profile(CURRENT_USER) or {}
        disp = me.get("display_name") or me.get("username") or CURRENT_USER
        handle = get_username(CURRENT_USER)
        st.subheader(f"{disp}")
        st.caption(f"@{handle} · 가입일: {me.get('created_at','N/A')}")

        # 팔로워/팔로잉 카운트 + 펼치기
        from services.follows import get_following, follow_counts
        fcnt, gcnt = follow_counts(CURRENT_USER)  # (followers, following)
        c1, c2 = st.columns(2)
        with c1:
            with st.expander(f"👥 팔로워 {fcnt}명"):
                followers = list(get_followers(CURRENT_USER))
                if followers:
                    for uid in followers:
                        st.write(f"- {uid}")
                else:
                    st.caption("아직 팔로워가 없습니다.")
        with c2:
            with st.expander(f"➡️ 팔로잉 {gcnt}명"):
                following = list(get_following(CURRENT_USER))
                if following:
                    for uid in following:
                        st.write(f"- {uid}")
                else:
                    st.caption("아직 팔로잉이 없습니다.")

        st.markdown("---")

        # 아바타 미리보기
        avatar_path = me.get("avatar_path") or ""
        if avatar_path and os.path.exists(avatar_path):
            st.image(avatar_path, width=120, caption="내 아바타")

        # 프로필 편집 폼
        with st.form("profile_edit", clear_on_submit=False):
            new_disp = st.text_input("표시 이름", value=disp)
            new_bio  = st.text_area("소개(프로필 한 줄/여러 줄 가능)", value=me.get("bio",""), height=80)
            up = st.file_uploader("아바타 업로드 (PNG/JPG)", type=["png","jpg","jpeg"])
            s1, s2 = st.columns([0.5, 0.5])
            with s1:
                ok = st.form_submit_button("저장")
            with s2:
                cancel = st.form_submit_button("취소")

            if ok:
                avatar_save = avatar_path
                if up is not None:
                    # 파일명: user_id 확장자 유지
                    ext = os.path.splitext(up.name)[1].lower() or ".png"
                    avatar_save = os.path.join(AVATAR_DIR, f"{CURRENT_USER}{ext}")
                    with open(avatar_save, "wb") as f:
                        f.write(up.read())
                if update_profile(CURRENT_USER, display_name=new_disp.strip(), bio=new_bio.strip(), avatar_path=avatar_save):
                    st.success("프로필이 저장되었습니다.")
                    st.rerun()
                else:
                    st.error("프로필 저장에 실패했습니다.")

    # ========== 내 글 탭 ==========
    with t_my_posts:
        st.subheader("📜 내가 쓴 글")
        my_posts = [r for r in list_feed(limit=500) if r.get("author_id") == CURRENT_USER]
        if not my_posts:
            st.info("아직 작성한 글이 없습니다.")
        else:
            for p in my_posts:
                with st.container(border=True):
                    st.caption(f"{p.get('created_at','')}")
                    body = p.get("content") or "_(본문 없음)_"
                    st.write(body)

                    # 해시태그 칩
                    tags = _post_hashtags(p["post_id"])
                    if tags:
                        tag_cols = st.columns(min(4, len(tags)))
                        for i, t in enumerate(tags):
                            with tag_cols[i % len(tag_cols)]:
                                st.button(f"#{t}", key=f"mytag-{p['post_id']}-{t}", disabled=True)

                    # 좋아요/댓글 카운트 + 피드에서 보기
                    likes = count_likes(p["post_id"])
                    cmts  = count_comments(p["post_id"])
                    st.caption(f"❤️ {likes} · 💬 {cmts}")

                    if st.button("👀 피드에서 보기", key=f"goto-feed-{p['post_id']}"):
                        st.session_state["nav_to"] = "피드"
                        st.session_state["focus_post_id"] = p["post_id"]
                        st.rerun()

    # ========== 내 활동 탭 ==========
    with t_my_activity:
        st.subheader("🗂️ 내 활동")
        # 기존 activity_log에서 내 것만 필터
        rows = _activity_rows(limit=300)
        my_rows = [r for r in rows if r.get("actor_id") == CURRENT_USER]
        if not my_rows:
            st.info("아직 활동 내역이 없습니다.")
        else:
            show_cols = ["created_at", "event_type", "target_type", "target_id", "metadata"]
            for r in my_rows:
                line = " | ".join(str(r.get(c, "")) for c in show_cols)
                st.text(line)
