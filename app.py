import streamlit as st
from services.posts import create_post, list_feed
from services.reactions import toggle_like, count_likes, user_liked

st.set_page_config(page_title="My Social Feed", page_icon="🗞️", layout="centered")
st.title("My Social Feed")

# 간단히 현재 사용자 고정 (추후 로그인/프로필로 대체)
CURRENT_USER = "u_0001"

with st.form("new_post"):
    content = st.text_area("무슨 생각을 하고 있나요?", max_chars=280, height=100, placeholder="텍스트를 입력하세요")
    submitted = st.form_submit_button("게시")
    if submitted:
        try:
            create_post(author_id=CURRENT_USER, content=content)
            st.success("작성 완료!")
            st.rerun()
        except Exception as e:
            st.error(f"오류: {e}")

st.subheader("피드")
for p in list_feed():
    with st.container(border=True):
        meta = f"작성자: {p['author_id']} · {p['created_at']}"
        st.caption(meta)
        if p["original_post_id"]:
            st.caption("🔁 리포스트")
        body = p["content"] if p["content"] else "_(본문 없음)_"
        st.write(body)

        cols = st.columns(3)
        with cols[0]:
            liked = user_liked(p["post_id"], CURRENT_USER)
            label = f"❤️ 좋아요 ({count_likes(p['post_id'])})" if liked else f"🤍 좋아요 ({count_likes(p['post_id'])})"
            if st.button(label, key=f"like-{p['post_id']}"):
                liked, cnt = toggle_like(p["post_id"], CURRENT_USER)
                st.toast(("좋아요 해제", "좋아요 추가")[liked])
                st.rerun()
        with cols[1]:
            st.button("🔁 리포스트(추가 예정)", key=f"rt-{p['post_id']}", disabled=True)
        with cols[2]:
            st.button("💬 댓글(추가 예정)", key=f"cm-{p['post_id']}", disabled=True)
