# ─── app.py ──────────────────────────────────────────────────────────────────
# Streamlit UI — the only file that imports Streamlit.
# All business logic lives in the other modules:
#   config.py        → constants and mappings
#   monday_client.py → Monday.com API
#   normaliser.py    → data cleaning and enrichment
#   semantic.py      → column detection (MiniLM / Groq fallback)
#   analytics.py     → BI metrics and LLM context
#   agent.py         → LLM system prompt and conversation

import json
import streamlit as st
from groq import Groq

from monday_client import fetch_boards, fetch_board_items
from normaliser   import enrich_deal, enrich_work_order
from semantic     import semantic_column_map, mapping_method_label, MINILM_AVAILABLE
from analytics    import pipeline_health, revenue_metrics, data_quality, build_data_context, by_sector, fmt_inr
from agent        import ask_agent
from config       import COLOUR_PIPELINE, COLOUR_WON, COLOUR_WINRATE, COLOUR_REVENUE

# ── Page Config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Skylark BI Agent",
    page_icon="🚁",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── CSS ───────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
  @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=DM+Mono&display=swap');

  html, body, [class*="css"] { font-family: 'Inter', sans-serif; }
  .stApp { background: #0D1117; }

  [data-testid="stSidebar"] {
    background: #161B22 !important;
    border-right: 1px solid #30363D;
  }
  [data-testid="stSidebar"] * { color: #C9D1D9 !important; }

  .metric-card {
    background: #161B22;
    border: 1px solid #30363D;
    border-top: 3px solid #1F6FEB;
    border-radius: 10px;
    padding: 16px;
    margin-bottom: 10px;
  }
  .metric-label { font-size: 11px; color: #6E7681; text-transform: uppercase; letter-spacing: 0.08em; margin-bottom: 6px; }
  .metric-value { font-size: 22px; font-weight: 700; color: #F0F6FC; font-family: 'DM Mono', monospace; }
  .metric-sub   { font-size: 11px; color: #484F58; margin-top: 4px; }

  .quality-good { color: #3FB950; background: #1A2F1C; border: 1px solid #3FB95040; padding: 3px 10px; border-radius: 20px; font-size: 12px; font-weight: 600; }
  .quality-warn { color: #D29922; background: #2A1E09; border: 1px solid #D2992240; padding: 3px 10px; border-radius: 20px; font-size: 12px; font-weight: 600; }
  .quality-bad  { color: #F85149; background: #2A0A0A; border: 1px solid #F8514940; padding: 3px 10px; border-radius: 20px; font-size: 12px; font-weight: 600; }

  .section-header {
    font-size: 10px; color: #484F58; text-transform: uppercase;
    letter-spacing: 0.12em; margin: 16px 0 8px;
    border-bottom: 1px solid #21262D; padding-bottom: 4px;
  }

  .stButton > button {
    background: #161B22 !important; border: 1px solid #30363D !important;
    color: #58A6FF !important; border-radius: 20px !important;
    font-size: 12px !important; padding: 4px 12px !important;
  }
  .stButton > button:hover { background: #1F2937 !important; border-color: #58A6FF !important; }

  .caveat-box { background: #1C1A09; border: 1px solid #D2992240; border-radius: 8px; padding: 10px 14px; margin-top: 12px; }
  .caveat-title { font-size: 10px; color: #D29922; text-transform: uppercase; letter-spacing: 0.08em; margin-bottom: 6px; }
  .caveat-item { font-size: 11px; color: #7A6B35; margin-bottom: 2px; }

  #MainMenu, footer, header { visibility: hidden; }
  .block-container { padding-top: 1rem !important; }
</style>
""", unsafe_allow_html=True)


# ── Session State ─────────────────────────────────────────────────────────────
def _init_state():
    defaults = {
        "step":         "config",
        "deals":        [],
        "work_orders":  [],
        "data_ctx":     None,
        "boards":       [],
        "messages":     [],
        "monday_token": "",
        "groq_key":     "",
        "client":       None,
        "ph":           None,
        "rm":           None,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

_init_state()


# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown(f"""
    <div style='padding:16px 0 8px'>
      <div style='font-size:18px;font-weight:700;color:#F0F6FC'>🚁 Skylark BI Agent</div>
      <div style='font-size:11px;color:#484F58;margin-top:2px'>Founder-level intelligence</div>
    </div>
    """, unsafe_allow_html=True)

    if st.session_state.step == "chat":
        ph = st.session_state.ph
        rm = st.session_state.rm

        st.markdown('<div class="section-header">Live Metrics</div>', unsafe_allow_html=True)

        # Pipeline + Won
        c1, c2 = st.columns(2)
        with c1:
            st.markdown(f"""
            <div class="metric-card" style="border-top-color:{COLOUR_PIPELINE}">
              <div class="metric-label">Pipeline</div>
              <div class="metric-value" style="font-size:16px">{fmt_inr(ph['total_pipeline'])}</div>
              <div class="metric-sub">{len(ph['active'])} active deals</div>
            </div>""", unsafe_allow_html=True)
        with c2:
            st.markdown(f"""
            <div class="metric-card" style="border-top-color:{COLOUR_WON}">
              <div class="metric-label">Won</div>
              <div class="metric-value" style="font-size:16px;color:#3FB950">{fmt_inr(ph['total_won'])}</div>
              <div class="metric-sub">{len(ph['won'])} deals</div>
            </div>""", unsafe_allow_html=True)

        # Win rate
        st.markdown(f"""
        <div class="metric-card" style="border-top-color:{COLOUR_WINRATE}">
          <div class="metric-label">Win Rate</div>
          <div class="metric-value">{ph['win_rate']}%</div>
          <div class="metric-sub">{len(ph['won'])} won · {len(ph['lost'])} lost · {len(ph['dead'])} dead</div>
        </div>""", unsafe_allow_html=True)

        # WO Revenue
        if rm:
            st.markdown(f"""
            <div class="metric-card" style="border-top-color:{COLOUR_REVENUE}">
              <div class="metric-label">WO Revenue</div>
              <div class="metric-value" style="font-size:16px">{fmt_inr(rm['total_revenue'])}</div>
              <div class="metric-sub">{len(rm['completed'])} completed orders</div>
            </div>""", unsafe_allow_html=True)

        # Pipeline stages
        if ph["stages"]:
            st.markdown('<div class="section-header">Pipeline Stages</div>', unsafe_allow_html=True)
            for stage, count in sorted(ph["stages"].items(), key=lambda x: -x[1]):
                st.markdown(f"""
                <div style='display:flex;justify-content:space-between;padding:4px 0;font-size:13px;color:#C9D1D9'>
                  <span>{stage}</span><span style='color:#58A6FF;font-weight:600'>{count}</span>
                </div>""", unsafe_allow_html=True)

        # Sector bars
        if st.session_state.deals:
            st.markdown('<div class="section-header">Deals by Sector</div>', unsafe_allow_html=True)
            sectors = by_sector(st.session_state.deals)
            max_val = sectors[0][1]["value"] if sectors else 1
            for sector, info in sectors[:8]:
                pct = int(info["value"] / max_val * 100) if max_val else 0
                st.markdown(f"""
                <div style='margin-bottom:8px'>
                  <div style='display:flex;justify-content:space-between;font-size:12px;color:#C9D1D9;margin-bottom:3px'>
                    <span>{sector}</span><span style='color:#484F58'>{fmt_inr(info['value'])}</span>
                  </div>
                  <div style='background:#21262D;border-radius:3px;height:3px'>
                    <div style='background:linear-gradient(90deg,#1F6FEB,#58A6FF);width:{pct}%;height:3px;border-radius:3px'></div>
                  </div>
                </div>""", unsafe_allow_html=True)

        # Data quality
        dq = st.session_state.data_ctx.get("data_quality", {}) if st.session_state.data_ctx else {}
        if dq:
            st.markdown('<div class="section-header">Data Quality</div>', unsafe_allow_html=True)
            for label, info in dq.items():
                score = info.get("score", 0)
                cls   = "quality-good" if score >= 85 else "quality-warn" if score >= 60 else "quality-bad"
                st.markdown(f"""
                <div style='display:flex;justify-content:space-between;align-items:center;margin-bottom:6px'>
                  <span style='font-size:12px;color:#C9D1D9'>{label.replace("_", " ").title()}</span>
                  <span class="{cls}">{score}%</span>
                </div>""", unsafe_allow_html=True)

            all_issues = dq.get("deals", {}).get("issues", []) + dq.get("work_orders", {}).get("issues", [])
            if all_issues:
                issues_html = "".join(f'<div class="caveat-item">• {i}</div>' for i in all_issues[:4])
                st.markdown(f'<div class="caveat-box"><div class="caveat-title">⚠ Data Caveats</div>{issues_html}</div>', unsafe_allow_html=True)

        # Semantic mapping method badge
        method = mapping_method_label()
        colour = "#3FB950" if MINILM_AVAILABLE else "#D29922"
        st.markdown(f"""
        <div style='margin-top:12px;font-size:10px;color:{colour}'>🧠 Column mapping: {method}</div>
        """, unsafe_allow_html=True)

        st.markdown("---")
        if st.button("🔄 Reload Data"):
            for k in ["deals", "work_orders", "data_ctx", "messages", "ph", "rm", "boards"]:
                st.session_state[k] = [] if isinstance(st.session_state.get(k), list) else None
            st.session_state.step = "config"
            st.rerun()

    else:
        st.markdown("Connect your Monday.com workspace to start asking founder-level business intelligence questions.")
        st.markdown("---")
        st.markdown("**What you can ask:**")
        for q in ["Pipeline health this quarter", "Win rate by sector", "Revenue vs targets",
                  "Leadership update", "At-risk deals", "Analyse energy sector performance"]:
            st.markdown(f"• {q}")


# ── Config Step ───────────────────────────────────────────────────────────────
if st.session_state.step == "config":
    _, col, _ = st.columns([1, 2, 1])
    with col:
        st.markdown("""
        <div style='text-align:center;padding:40px 0 20px'>
          <div style='font-size:11px;color:#58A6FF;letter-spacing:0.15em;text-transform:uppercase;margin-bottom:8px'>Skylark Drones</div>
          <h1 style='color:#F0F6FC;font-size:36px;font-weight:800;margin:0 0 8px'>BI Agent</h1>
          <p style='color:#6E7681;font-size:15px'>Connect Monday.com · Ask anything · Get founder-level insights</p>
        </div>
        """, unsafe_allow_html=True)

        with st.form("config_form"):
            st.markdown("**🔑 API Credentials**")
            monday_token = st.text_input(
                "Monday.com API Token", type="password",
                placeholder="eyJhbGciOiJIUzI1NiJ9...",
                help="Monday.com → Profile → Developers → API v2 Token",
            )
            groq_key = st.text_input(
                "Groq API Key", type="password",
                placeholder="gsk_...",
                help="Free key from console.groq.com",
            )
            submitted = st.form_submit_button("Connect & Load Boards →", use_container_width=True)

        if submitted:
            if not monday_token or not groq_key:
                st.error("Both API keys are required.")
            else:
                with st.spinner("Connecting to Monday.com..."):
                    try:
                        boards = fetch_boards(monday_token)
                        st.session_state.boards       = boards
                        st.session_state.monday_token = monday_token
                        st.session_state.groq_key     = groq_key
                        st.session_state.client       = Groq(api_key=groq_key)
                        st.success(f"Connected! Found {len(boards)} boards.")
                    except Exception as e:
                        st.error(f"Connection failed: {e}")

        if st.session_state.boards:
            st.markdown("---")
            st.markdown("**📋 Select Your Boards**")
            board_options = {b["name"]: b["id"] for b in st.session_state.boards}
            board_names   = list(board_options.keys())

            with st.form("board_form"):
                deals_board = st.selectbox("Deals / Pipeline Board", board_names,
                                           help="Your sales pipeline or CRM board")
                wo_board    = st.selectbox("Work Orders Board", board_names,
                                           help="Your project execution or work orders board")
                load = st.form_submit_button("Load Data & Start Chatting →", use_container_width=True)

            if load:
                if deals_board == wo_board:
                    st.warning("Please select different boards for Deals and Work Orders.")
                else:
                    progress = st.progress(0, "Loading deals...")
                    try:
                        raw_deals = fetch_board_items(st.session_state.monday_token, board_options[deals_board])
                        progress.progress(30, "Loading work orders...")
                        raw_wos   = fetch_board_items(st.session_state.monday_token, board_options[wo_board])
                        progress.progress(55, "Semantic column mapping...")

                        # Semantic column detection (MiniLM → Groq → keyword fallback)
                        deals_cols   = [k for k in raw_deals[0] if not k.startswith("_")] if raw_deals else []
                        wo_cols      = [k for k in raw_wos[0]   if not k.startswith("_")] if raw_wos   else []
                        deals_map    = semantic_column_map(deals_cols, "Deals/Pipeline", st.session_state.client)
                        wo_map       = semantic_column_map(wo_cols,    "Work Orders",    st.session_state.client)
                        method       = mapping_method_label()

                        progress.progress(75, f"Normalising via {method}...")
                        deals       = [enrich_deal(r,        deals_map) for r in raw_deals]
                        work_orders = [enrich_work_order(r,  wo_map)    for r in raw_wos]

                        st.session_state.deals       = deals
                        st.session_state.work_orders = work_orders
                        st.session_state.ph          = pipeline_health(deals)
                        st.session_state.rm          = revenue_metrics(work_orders)
                        st.session_state.data_ctx    = build_data_context(deals, work_orders)

                        dq_d = data_quality(deals,       "deals")
                        dq_w = data_quality(work_orders, "work orders")
                        progress.progress(100, "Done!")

                        st.session_state.messages = [{
                            "role": "assistant",
                            "content": (
                                f"✅ **Connected!** Loaded **{len(deals)} deals** and **{len(work_orders)} work orders**.\n\n"
                                f"**🧠 Column mapping via {method}**\n"
                                f"Deals: `{json.dumps(deals_map)}`\n"
                                f"Work Orders: `{json.dumps(wo_map)}`\n\n"
                                f"**Data quality:** Deals {dq_d['score']}% · Work Orders {dq_w['score']}%"
                                + (f"\n\n⚠️ **Caveats:** {'; '.join(dq_d['issues'][:2])}" if dq_d["issues"] else "")
                                + "\n\nWhat would you like to know? Ask about pipeline health, revenue, sector performance, at-risk deals — or request a leadership update."
                            ),
                        }]
                        st.session_state.step = "chat"
                        st.rerun()

                    except Exception as e:
                        st.error(f"Failed to load data: {e}")


# ── Chat Step ─────────────────────────────────────────────────────────────────
elif st.session_state.step == "chat":
    n_deals = len(st.session_state.deals)
    n_wo    = len(st.session_state.work_orders)

    st.markdown(f"""
    <div style='display:flex;align-items:center;padding:0 0 16px;border-bottom:1px solid #30363D;margin-bottom:20px'>
      <div>
        <h2 style='color:#F0F6FC;margin:0;font-size:22px'>🚁 Skylark BI Agent</h2>
        <div style='color:#3FB950;font-size:12px;margin-top:2px'>● {n_deals} deals · {n_wo} work orders · Live from Monday.com</div>
      </div>
    </div>
    """, unsafe_allow_html=True)

    # Suggestion chips — only before first user message
    user_msgs = [m for m in st.session_state.messages if m["role"] == "user"]
    if not user_msgs:
        st.markdown("**Quick questions:**")
        suggestions = [
            "How's our pipeline looking this quarter?",
            "Which sector has the most potential?",
            "Give me a leadership update",
            "Analyse our energy sector in detail",
            "Which deals are at risk of slipping?",
            "Compare energy vs mining pipeline",
        ]
        cols = st.columns(3)
        for i, s in enumerate(suggestions):
            if cols[i % 3].button(s, key=f"sug_{i}"):
                st.session_state.messages.append({"role": "user", "content": s})
                with st.spinner("Analysing..."):
                    try:
                        reply = ask_agent(st.session_state.client, st.session_state.data_ctx, st.session_state.messages)
                        st.session_state.messages.append({"role": "assistant", "content": reply})
                    except Exception as e:
                        st.session_state.messages.append({"role": "assistant", "content": f"Error: {e}"})
                st.rerun()
        st.markdown("---")

    # Render chat history
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    # Chat input
    user_input = st.chat_input("Ask anything about your pipeline, revenue, deals, or request a leadership update...")
    if user_input and user_input.strip():
        st.session_state.messages.append({"role": "user", "content": user_input.strip()})
        with st.spinner("Analysing..."):
            try:
                reply = ask_agent(st.session_state.client, st.session_state.data_ctx, st.session_state.messages)
                st.session_state.messages.append({"role": "assistant", "content": reply})
            except Exception as e:
                st.session_state.messages.append({"role": "assistant", "content": f"Error: {e}"})
        st.rerun()

    st.markdown("""
    <div style='text-align:center;margin-top:16px;font-size:11px;color:#484F58'>
      Powered by Llama 3 (Groq) · Data from Monday.com · Read-only access
    </div>""", unsafe_allow_html=True)
