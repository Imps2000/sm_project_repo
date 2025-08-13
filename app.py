import os
import streamlit as st

from services.posts import (
    create_post, list_feed, get_post,
    soft_delete_post, restore_post
)
from services.reactions import toggle_like, count_likes, user_liked
from services.tags import list_posts_by_hashtag
from services.comments import create_comment, list_comments, count_comments
from repo.csv_repo import read_csv

# ---- App Setup --------------------------------------------------------------
st.set_page_config(page_title="My Social Feed", page_icon="🗞️", layout="centered")
st.title("My Social Feed")

CURRENT_USER = "u_0001"
POSTS_PATH = os.path.join("data", "posts.csv")
POST_TAGS_PATH = os.path.join("data", "post_hashtags.csv")

# ---- Helpers ----------------------------------------------------------------
def _all_posts_map() -> dict:
    rows = read_csv(POSTS_PATH) if os.path.exists(POSTS_PATH) else []
    return {r["post_id"]: r for r in rows}

def _post_hashtags(post_id: str):
    if not os.path.exists(POST_TAGS_PATH):
        return []
    return [row["hashtag"] for row in read_csv(POST_TAGS_PATH) if row["post_id"] == post_id]

def _load_posts():
    """사이드바의 해시태그 필터를 고려해 피드 소스 로드"""
    if st.session_state.get("filter_tag"):
        post_ids = set(list_posts_by_hashtag(st.session_state["filter_tag"]))
        rows = list_feed(limit=500)  # 넉넉히 불러서 필터
        return [r for r in rows if r["post_id"] in post_ids]
    return list_feed()

# ---- Sidebar: Hashtag Filter ------------------------------------------------
st.sidebar.header("해시태그 필터")
filter_tag = st.sidebar.text_input("해시태그(# 없이 입력)", value=st.session_state.get("filter_tag", ""))
sb_cols = st.sidebar.columns(2)
with sb_cols[0]:
    if st.button("적용", use_container_width=True):
        st.session_state["filter_tag"] = filter_tag.strip().lower()
        st.rerun()
with sb_cols[1]:
    if st.button("해제", use_container_width=True):
        st.session_state["filter_tag"] = ""
        st.rerun()

# ---- New Post Form ----------------------------------------------------------
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

# ---- Feed -------------------------------------------------------------------
st.subheader("피드")
ALL_POSTS = _all_posts_map()
posts = _load_posts()

for p in posts:
    with st.container(border=True):
        # 상단 메타
        st.caption(f"작성자: {p['author_id']} · {p['created_at']}")
        is_repost = bool(p["original_post_id"])
        interactions_enabled = True
        tags_to_show = []

        # 본문/원본 표시
        if is_repost:
            st.caption("🔁 리포스트")
            orig = ALL_POSTS.get(p["original_post_id"])
            if (orig is None) or (orig.get("is_deleted") == "1"):
                # 정책: 원본 삭제 시 배지 + 메타만 노출, 상호작용 차단
                st.warning("삭제된 게시물")
                if orig is not None:
                    st.caption(f"원본 메타: 작성자 {orig.get('author_id','?')} · {orig.get('created_at','?')}")
                else:
                    st.caption("원본 메타: 알 수 없음")
                interactions_enabled = False
                tags_to_show = []
            else:
                st.caption(f"원본: {orig['author_id']} · {orig['created_at']}")
                st.write(orig["content"] or "_(본문 없음)_")
                tags_to_show = _post_hashtags(orig["post_id"])
        else:
            st.write(p["content"] if p["content"] else "_(본문 없음)_")
            tags_to_show = _post_hashtags(p["post_id"])

        # 해시태그 칩
        if tags_to_show:
            tag_cols = st.columns(min(4, len(tags_to_show)))
            for i, t in enumerate(tags_to_show):
                with tag_cols[i % len(tag_cols)]:
                    if st.button(f"#{t}", key=f"tag-{p['post_id']}-{t}"):
                        st.session_state["filter_tag"] = t
                        st.rerun()

        # 하단 액션 (좋아요 / 리포스트 / 댓글)
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

        # ----- 삭제/복구 UI (원본 삭제 UI 핵심) -------------------------------
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
                    # 주: 삭제된 글은 피드에서 빠지므로, 복구 버튼은 테스트용
                    if st.button("↩️ 복구(실험용)", key=f"restore-{p['post_id']}"):
                        try:
                            restore_post(p["post_id"], CURRENT_USER)
                            st.success("복구 완료")
                            st.rerun()
                        except Exception as e:
                            st.error(f"오류: {e}")

        # ----- 댓글 섹션 ------------------------------------------------------
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
                st.write(c["content"])
                for rc in replies_by_parent.get(c["comment_id"], []):
                    with st.container():
                        st.markdown(f"&nbsp;&nbsp;↳ **{rc['author_id']}** · {rc['created_at']}")
                        st.write(f"&nbsp;&nbsp;{rc['content']}")

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