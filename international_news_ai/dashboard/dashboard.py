import streamlit as st
import pandas as pd
from streamlit_autorefresh import st_autorefresh
#import international_news_extract as collector
import requests
import os

API_URL = os.getenv("API_URL", "http://127.0.0.1:8000").rstrip("/")
NEWS_COLUMNS = ["fetched_at", "source", "category", "impact", "title", "url", "breaking_flag",
                "content", "image_url", "video_url", "video_platform"]
st.set_page_config("International Fast News Intelligence", layout="wide")


## styling
st.markdown("""
<style>
.kpi-card{
            background: linear-gradient(135deg, #ffffff, #f6f8fa);
            border-radius: 16px;
            padding: 18px 20px;
            box-shadow: 0 6px 18px rgba(0,0,0,0.06);
            border-left: 6px solid #4f8bf9;
            height: 110px;
            }
.kpi-title { 
            font-size: 14px;
             color: #6b7280;
             }
.kpi-value {
             font-size: 30px; 
            font-weight: 700; 
            }
            
.header-card {
             background: linear-gradient(135deg, #eef2ff, #ffffff); 
             border-radius: 20px; 
             padding: 30px;
             margin-bottom: 30px;
             }
            
.feed-card { 
            background: #ffffff;
            border-radius: 16px; 
            padding: 18px;
            box-shadow: 0 6px 18px rgba(0,0,0,0.06);
            margin-bottom: 20px; 
            }
            
.feed-kpi { 
            background: linear-gradient(135deg, #ffffff, #f9fafb);
            border-radius: 14px;
            padding: 14px;
            box-shadow: 0 4px 14px rgba(0,0,0,0.05); 
            border-left: 5px solid #3b82f6; 
            }
            
.feed-kpi-title { 
            font-size: 13px; 
            color: #6b7280; 
            }
            
.feed-kpi-value { 
            font-size: 22px;
            font-weight: 700; 
            }

.breaking { 
            background-color: #ffeded !important;
            }

.breaking-badge {
             color: #ef4444;
             font-weight: bold;
             }
</style>          
""", unsafe_allow_html=True)

# =========================
# SESSION STATE INIT
# =========================
if "collector_running" not in st.session_state:
    st.session_state.collector_running = False


# =========================
# AUTO REFRESH
# =========================

if "article_open" not in st.session_state:
    st.session_state.article_open = False

# =========================
# DATA LOADER
# =========================
def load_data():
    """Returns (df, backend_ok). df always has NEWS_COLUMNS so the UI can render when empty."""
    try:
        res = requests.get(f"{API_URL}/news/latest?limit=50", timeout=75)  # free-tier backend can take ~60s to wake
        res.raise_for_status()
        df = pd.DataFrame(res.json(), columns=NEWS_COLUMNS)
        df["fetched_at"] = pd.to_datetime(df["fetched_at"], errors="coerce")
        return df.dropna(subset=["fetched_at"]), True
    except Exception as e:
        print("LOAD ERROR:", e)
        df = pd.DataFrame(columns=NEWS_COLUMNS)
        df["fetched_at"] = pd.to_datetime(df["fetched_at"])
        return df, False


def call_backend(action):
    try:
        requests.post(f"{API_URL}/news/{action}", timeout=75).raise_for_status()
        return True
    except Exception as e:
        st.sidebar.error(f"Backend not reachable at {API_URL} — is uvicorn running?")
        print(f"{action.upper()} ERROR:", e)
        return False





# =========================
# SIDEBAR
# =========================
page = st.sidebar.radio("📂 Navigation", ["📊 Overview", "📰 News Feed"])
st.sidebar.divider()

st.sidebar.title("🧠 Collector Control")

# ---- START BUTTON ----
if st.sidebar.button("▶ Start Collector", disabled=st.session_state.collector_running):
    if call_backend("start"):
        st.session_state.collector_running = True
        st.sidebar.success("Collector started")

# ---- STOP BUTTON ----
if st.sidebar.button("⏹ Stop Collector", disabled=not st.session_state.collector_running):
    if call_backend("stop"):
        st.session_state.collector_running = False
        st.sidebar.warning("Collector stopped")

# ---- STATUS ----
status = "🟢 Running" if st.session_state.collector_running else "🔴 Stopped"
st.sidebar.markdown(f"**Status:** {status}")

st.sidebar.divider()
st.sidebar.markdown("### 🎯 Categories")
st.sidebar.markdown("- Immigration\n- Trade\n- Tariff\n- Sports")

# =========================
# DATA
# =========================
df, backend_ok = load_data()
if not backend_ok:
    st.error(f"⚠️ Backend not reachable at {API_URL}. It may be waking up — refresh in a minute.")
elif df.empty:
    st.info("🕒 Collector not started or no articles yet. Click ▶ Start Collector.")

# Refresh periodically while collecting so new articles appear
if st.session_state.collector_running and not st.session_state.get("article_open", False):
    st_autorefresh(interval=15000, key="data_refresh")


# ========================= # OVERVIEW PAGE # =========================
if page == "📊 Overview":
    st.markdown("""
                 <div class="header-card"> 
                <h1>🌍 International Fast News Intelligence</h1>
                 <p><b>Real-time global monitoring & extraction system</b></p>
                 </div>
                 """, unsafe_allow_html=True)
    total_articles = len(df)
    breaking_articles = int(df['breaking_flag'].fillna(False).astype(bool).sum())
    last_fetched = df['fetched_at'].max().strftime("%Y-%m-%d %H:%M:%S") if not df.empty else "—"

    c1, c2, c3 = st.columns(3)
    with c1:
        st.markdown(f"""
                    <div class="kpi-card">
                    <div class="kpi-title">📰 TOTAL ARTICLES</div>
                    <div class="kpi-value">{total_articles}</div>
                    </div>
                    """, unsafe_allow_html=True)
    with c2:
        st.markdown(f"""
                    <div class="kpi-card">
                    <div class="kpi-title">🚨 BREAKING NEWS</div>
                    <div class="kpi-value">{breaking_articles}</div>
                    </div>
                    """, unsafe_allow_html=True)
    with c3:
        st.markdown(f"""
                    <div class="kpi-card">
                    <div class="kpi-title">⏱ LAST FETCHED</div>
                    <div class="kpi-value">{last_fetched}</div>
                    </div>
                    """, unsafe_allow_html=True)
  

    # =========================
    # BREAKING ALERTS (LIVE)
    # =========================
    st.markdown("## 🚨 LIVE BREAKING ALERTS")

    breaking_df = df[df["breaking_flag"].fillna(False).astype(bool)].sort_values("fetched_at", ascending=False)

    if breaking_df.empty:
        st.success("No breaking news right now.")
    else:
        for _, r in breaking_df.head(6).iterrows():
            st.error(f"**{r['category'].upper()}** — {r['title']}")

    st.divider()


# =========================
# NEWS FEED PAGE
# =========================
else:
    st.markdown("<h2>📰 Focused Global News Feed</h2>", unsafe_allow_html=True)
    st.caption("Only Immigration, Trade, Tariff & Sports news")

    today_count = df[df["fetched_at"].dt.date == pd.Timestamp.now().date()].shape[0]
    total_sources = df["source"].nunique()

    k1, k2 = st.columns(2)
    with k1:
        st.markdown(f"""
                    <div class="feed-kpi">
                    <div class="feed-kpi-title">🗞 Articles Today</div>
                    <div class="feed-kpi-value">{today_count}</div>
                    </div>
                    """, unsafe_allow_html=True)
    with k2:
        st.markdown(f"""
                    <div class="feed-kpi">
                    <div class="feed-kpi-title">🌐 Sources</div>
                    <div class="feed-kpi-value">{total_sources}</div>
                    </div>
                    """, unsafe_allow_html=True)
    st.divider()

    # =========================
    # MAIN FEED
    # =========================
    st.markdown("## 📰 Global News Feed")

    if df.empty:
        st.info("No articles to show yet.")
        st.stop()

    df_sorted = df.sort_values("fetched_at", ascending=False)

    #Add breaking badge column
    df_sorted["breaking_badge"] = df_sorted["breaking_flag"].apply(lambda x: "🛑 BREAKING" if x else "")

    # Table with breaking news highlighted
    table_df = df_sorted[["fetched_at", "source", "category", "impact", "title", "url", "breaking_flag", "breaking_badge","image_url","video_url"]].copy()
    st.dataframe(table_df.style.apply(lambda x: ["background-color: #ffeded" if x.breaking_badge else "" for _ in x], axis=1), width='stretch', height=520)
    st.divider()

    # =========================
    # ARTICLE VIEWER
    # =========================
    selected_title = st.selectbox("📰 Select article", df_sorted["title"].tolist(),key="article_select")
    article_row = df_sorted[df_sorted["title"] == selected_title].iloc[0]

    @st.dialog("📄 Article Details", width="large")
    def article_popup(article):
        left, right = st.columns([2, 3])
        with left:
            st.markdown(f"## {article['title']}")
            st.markdown(
                f"""
        **Source:** {article['source']} 
        **Fetched:** {article['fetched_at'].strftime('%Y-%m-%d %H:%M')}
        **Category:** {article['category']}
                {"🛑 BREAKING" if article['breaking_flag'] else ""}
                """ 
            )
            st.markdown(f"[🔗 Read original article]({article['url']})")
        with right:
        # ---- IMAGE ----
            if article.get("image_url"):
                st.image(article["image_url"], use_container_width=True)

            # ---- VIDEO ----
            if article.get("video_url"):
                st.video(article["video_url"])

            st.divider()

            # ---- TEXT CONTENT ----
            st.markdown("### 🧠 Extracted Content")
            st.write(article["content"])
    if st.session_state.get("article_open", False):
        article_popup(article_row)
        st.session_state.article_open = False
   
    if st.button("📖 Open Article"):
            st.session_state.article_open = True
            #article_popup(article_row)
            #st.session_state.article_open = False


    if st.session_state.get("article_open", False):
        st_autorefresh(interval=5000, key="refresh")