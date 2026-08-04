import os

import requests
import streamlit as st

API_URL = os.environ.get("SAWTAI_API_URL", "http://api:8000/api/v1").rstrip("/")
HEADERS = {"Authorization": "Bearer sawtai-demo-token"}
TAXONOMY = {
    "تأخر جمع النفايات": "waste.collection.missed",
    "صيانة الطرق": "roads.maintenance",
    "مرافق الحدائق": "parks.facilities",
    "التصاريح الرقمية": "permits.digital",
}

st.set_page_config(page_title="SawtAI Annotation", page_icon="◉", layout="wide")
st.markdown(
    """
    <style>
      html, body, [class*="css"] { direction: rtl; text-align: right; }
      .stApp { background: #f4f6f4; }
      .sawtai-card { background: white; border: 1px solid #dfe8e4; border-radius: 14px;
                     padding: 22px; line-height: 2; }
      .sawtai-badge { display: inline-block; padding: 4px 9px; border-radius: 7px;
                      background: #e4f1ed; color: #126f64; font-size: 12px; }
    </style>
    """,
    unsafe_allow_html=True,
)

st.title("أداة وسم صوتي")
st.caption("أداة داخلية للمراجعة المزدوجة وتصحيح تصنيف الرسائل — ليست جزءاً من واجهة المنتج")


@st.cache_data(ttl=15)
def load_messages(sentiment: str) -> list[dict]:
    suffix = f"&sentiment={sentiment}" if sentiment else ""
    response = requests.get(f"{API_URL}/messages?limit=100{suffix}", headers=HEADERS, timeout=15)
    response.raise_for_status()
    return response.json()["items"]


sentiment_filter = st.sidebar.selectbox(
    "تصفية المشاعر",
    options=["", "negative", "neutral", "positive"],
    format_func=lambda value: {"": "الكل", "negative": "سلبي", "neutral": "محايد", "positive": "إيجابي"}[value],
)
annotator = st.sidebar.text_input("اسم المراجع", value="المراجع 1")
messages = load_messages(sentiment_filter)

if not messages:
    st.warning("لا توجد رسائل مطابقة.")
    st.stop()

selected_index = st.sidebar.number_input("رقم الرسالة", min_value=1, max_value=len(messages), value=1) - 1
message = messages[selected_index]
progress = (selected_index + 1) / len(messages)
st.progress(progress, text=f"{selected_index + 1} من {len(messages)}")

left, right = st.columns([1.4, 1])
with left:
    st.markdown(
        f"""
        <div class="sawtai-card">
          <span class="sawtai-badge">{message['channel']['name_ar']}</span>
          <span class="sawtai-badge">{message['dialect'].upper()}</span>
          <h3>{message['text']}</h3>
          <small>{message['occurred_at']}</small>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.subheader("قرار المراجع")
    label = st.radio("التصنيف الصحيح", options=list(TAXONOMY), horizontal=True)
    confidence = st.slider("ثقة المراجع", 0.0, 1.0, 0.9, 0.05)
    notes = st.text_area("ملاحظات الاختلاف أو الالتباس")
    if st.button("حفظ التصحيح", type="primary", use_container_width=True):
        response = requests.post(
            f"{API_URL}/messages/{message['message_id']}/review",
            headers={**HEADERS, "Content-Type": "application/json"},
            json={"occurred_at": message["occurred_at"], "node_code": TAXONOMY[label]},
            timeout=15,
        )
        if response.ok:
            st.success(f"تم حفظ تصحيح {annotator} بثقة {confidence:.0%}.")
            if notes:
                st.info("تم الاحتفاظ بالملاحظة في جلسة المراجعة الحالية فقط.")
        else:
            st.error(response.text)

with right:
    st.subheader("اقتراح النموذج")
    st.metric("التصنيف", message["classification"]["label_ar"])
    st.metric("الثقة", f"{message['classification']['confidence']:.0%}")
    st.metric("المشاعر", message["sentiment"]["label"], f"{message['sentiment']['score']:+.2f}")
    st.code(
        f"model: {message['sentiment']['model']}\n"
        f"version: {message['sentiment']['version']}\n"
        f"message_id: {message['message_id']}",
        language="yaml",
    )

st.caption("جميع الرسائل المعروضة بيانات تركيبية معلنة. لا تستخدم الأداة مع بيانات مواطنين حقيقية في بيئة النموذج الأولي.")
