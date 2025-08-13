import os
import streamlit as st
from repo.csv_repo import read_csv
from services.posts import create_post, list_feed
from services.reactions import toggle_like, count_likes, user_liked
from services.tags import list_posts_by_hashtag

st.set_page_config(page_title="My Social Feed", page_icon="🗞️", layout="centered")
st.title("My Social Feed")

CURRENT_USER = "u_0001"
POSTS_PATH = os.path.join("data", "posts.csv")
POST_TAGS_PATH = os.path.join("data", "post_hashtags.csv")

# --- helpers ---

def _all_posts_map():
    """posts.csv 전체를 딕셔너리로 로드(post_id -> row). 리포스트 원본 표시용."""
    rows = read_csv(POSTS_PATH)
    return {r["post_id"]: r for r in rows}


def _post_hashtags(post_id: str):
    if not os.path.exists(POST_TAGS_PATH):
        return []
    return [row["hashtag"] for row in read_csv(POST_TAGS_PATH) if row["post_id"] == post_id]


ALL_POSTS = _all_posts_map()

# --- Sidebar: hashtag filter ---
st.sidebar.header("필터")
filter_tag = st.sidebar.text_input("해시태그로 필터(# 없이 입력)", value=st.session_state.get("filter_tag", ""))
col_sb = st.sidebar.columns(2)
with col_sb[0]:
    if st.button("적용", use_container_width=True):
        st.session_state["filter_tag"] = (filter_tag or "").strip().lower()
        st.rerun()
with col_sb[1]:
    if st.button("해제", use_container_width=True):
        st.session_state["filter_tag"] = ""
        st.rerun()

# --- New Post Form ---
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

st.subheader("피드")

# --- feed source (hashtag filter if set) ---

def _load_posts():
    if st.session_state.get("filter_tag"):
        post_ids = set(list_posts_by_hashtag(st.session_state["filter_tag"]))
        rows = list_feed(limit=500)  # 넉넉히 가져와 필터링
        return [r for r in rows if r["post_id"] in post_ids]
    return list_feed()


posts = _load_posts()

for p in posts:
    with st.container(border=True):
        meta = f"작성자: {p['author_id']} · {p['created_at']}"
        st.caption(meta)

        is_repost = bool(p["original_post_id"])
        tags_to_show = []
        interactions_disabled = False

        if is_repost:
            st.caption("🔁 리포스트")
            orig = ALL_POSTS.get(p["original_post_id"])  # 원본 게시물
            if (not orig) or orig.get("is_deleted") == "1":
                # 예외 정책: 원본 삭제 시 본문 숨기고 배지 + 메타만
                st.warning("삭제된 게시물")
                if orig:
                    st.caption(f"원본 작성일: {orig['created_at']}")
                interactions_disabled = True  # 상호작용 제한(추후 필요 시 세부 분기)
            else:
                # 원본이 존재하면 원본 본문을 표시
                st.caption(f"원본: {orig['author_id']} · {orig['created_at']}")
                st.write(orig["content"])
                tags_to_show = _post_hashtags(orig["post_id"])  # 태그는 원본 기준으로 표시
        else:
            body = p["content"] if p["content"] else "_(본문 없음)_"
            st.write(body)
            tags_to_show = _post_hashtags(p["post_id"])  # 일반 포스트는 자신의 태그

        # 해시태그 칩
        if tags_to_show:
            tag_cols = st.columns(min(4, len(tags_to_show)))
            for i, t in enumerate(tags_to_show):
                with tag_cols[i % len(tag_cols)]:
                    if st.button(f"#{t}", key=f"tag-{p['post_id']}-{t}"):
                        st.session_state["filter_tag"] = t
                        st.rerun()

        cols = st.columns(3)
        with cols[0]:
            liked = user_liked(p["post_id"], CURRENT_USER)
            like_label = (f"❤️ 좋아요 ({count_likes(p['post_id'])})" if liked
                          else f"🤍 좋아요 ({count_likes(p['post_id'])})")
            if st.button(like_label, key=f"like-{p['post_id']}", disabled=interactions_disabled):
                liked, cnt = toggle_like(p["post_id"], CURRENT_USER)
                st.toast(("좋아요 해제", "좋아요 추가")[liked])
                st.rerun()
        with cols[1]:
            if st.button("🔁 리포스트", key=f"rt-{p['post_id']}", disabled=interactions_disabled):
                try:
                    create_post(author_id=CURRENT_USER, content="", original_post_id=p["post_id"])  # 본문 없이 원본 공유
                    st.success("리포스트 완료!")
                    st.rerun()
                except Exception as e:
                    st.error(f"오류: {e}")
        with cols[2]:
            st.button("💬 댓글(추가 예정)", key=f"cm-{p['post_id']}", disabled=True)
