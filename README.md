# Skylark Drones — Business Intelligence Agent

A conversational AI agent that connects to Monday.com and lets founders ask natural-language business questions about pipeline health, revenue, sector performance, and operational metrics.

**Stack:** Streamlit · Groq (Llama 3.3 70B + 3.1 8B fallback) · Monday.com GraphQL API · MiniLM-L6-v2 (semantic column detection)

---

## Quick Start

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Run
streamlit run app.py
```

Open **http://localhost:8501** in your browser and enter your API keys.

---

## What You Need

| Credential | Where to Get It |
|---|---|
| Monday.com API Token | Monday.com → avatar (bottom-left) → **Developers** → **API v2 Token** |
| Groq API Key | [console.groq.com](https://console.groq.com) → **API Keys** → **Create Key** (free) |

---

## Module Structure

The codebase is split into single-responsibility modules — nothing is bundled into one file.

```
skylark-bi-agent/
├── app.py               # Streamlit UI only — no business logic
├── config.py            # All constants: model names, mappings, thresholds
├── monday_client.py     # Monday.com GraphQL API — fetch boards and items
├── normaliser.py        # Data cleaning: dates, currency, status, sector
├── semantic.py          # Column detection: MiniLM-L6-v2 → Groq → keyword fallback
├── analytics.py         # BI metrics: pipeline, win rate, sector, data quality
├── agent.py             # LLM layer: system prompt, ask_agent, model fallback
├── requirements.txt     # Python dependencies
└── .streamlit/
    └── config.toml      # Dark theme
```

### What each module does

**`config.py`** — Single source of truth for all constants. Change model names, API URLs, status mappings, or colour codes here without touching any other file.

**`monday_client.py`** — All Monday.com interaction. `fetch_boards()`, `fetch_board_items()`. Handles auth headers, GraphQL queries, error handling, and raw item flattening. Nothing here knows about Streamlit or the LLM.

**`normaliser.py`** — Pure data transformation. `parse_date()`, `parse_money()`, `normalise_status()`, `normalise_sector()`, `enrich_deal()`, `enrich_work_order()`. Stateless functions — independently unit-testable.

**`semantic.py`** — Column name detection. Tries MiniLM-L6-v2 first (offline, fast), falls back to Groq LLM, then returns `{}` so `normaliser.py` keyword matching handles it. Called once per board load, result passed through.

**`analytics.py`** — All BI computation. `pipeline_health()`, `revenue_metrics()`, `by_sector()`, `data_quality()`, `build_data_context()`. Pre-computes all aggregates server-side before the LLM ever sees data.

**`agent.py`** — LLM interaction. Holds the system prompt, `ask_agent()` with automatic model fallback (70B → 8B on rate limits). Nothing here knows about Streamlit.

**`app.py`** — Thin Streamlit UI. Imports from all other modules. Handles session state, config step, chat step, sidebar rendering. No business logic here.

---

## Architecture

```
Browser (Streamlit app.py)
│
├── monday_client.py     GraphQL API → raw item dicts
│
├── semantic.py          Column name → semantic field mapping
│     ├── MiniLM-L6-v2  (sentence-transformers, offline)
│     └── Groq LLM      (API fallback if MiniLM not installed)
│
├── normaliser.py        Raw dicts → enriched typed dicts
│     ├── parse_date()   7 format parsers + ISO fallback
│     ├── parse_money()  ₹L/Cr/plain number handling
│     ├── normalise_status()   STATUS_MAP keyword matching
│     └── normalise_sector()   SECTOR_MAP keyword sets
│
├── analytics.py         Enriched dicts → BI metrics
│     ├── pipeline_health()    win rate = won/(won+lost+dead)
│     ├── revenue_metrics()    completed WO revenue
│     ├── by_sector()          grouped sector breakdown
│     └── build_data_context() pre-aggregated JSON for LLM
│
└── agent.py             Metrics + history → LLM response
      ├── Llama 3.3 70B  (primary)
      └── Llama 3.1 8B   (auto-fallback on 413/429)
```

---

## Semantic Column Detection

The biggest data resilience feature. Instead of checking if "value" appears in a column name, the agent uses embeddings to match column names to semantic concepts:

**MiniLM-L6-v2 (primary):** Embeds all column names + concept anchors → cosine similarity → picks best match. Runs locally, offline, ~50ms. No API call needed.

**Groq LLM (fallback):** If `sentence-transformers` isn't installed, sends column names to Llama 3.3 70B with a structured prompt. Adds ~2s to load time.

**Keyword matching (last resort):** If both above fail, `normaliser.py` scans column names for substrings like "value", "status", "sector".

This 3-layer approach correctly handles columns like:
- `"Masked Deal value"` → value field
- `"Amount in Rupees (Excl of GST) (Masked)"` → value field
- `"Execution Status"` → status field
- `"Sector/service"` → sector field

---

## Win Rate Formula

```
Win Rate = Won / (Won + Lost + Dead) = 165 / (165 + 0 + 127) = 56.5%
```

- `Dead` deals are **not** mapped to `Lost` — they may mean cold, disqualified, or on hold
- `Dead` **is** included in the denominator — treating them as unrecovered deals
- This avoids the misleading results of `Won/Total` (47.7%) or `Won/(Won+Lost)` (100%)

---

## Deploying to Streamlit Cloud

1. Push this folder to a GitHub repo
2. Go to [share.streamlit.io](https://share.streamlit.io) → **New app**
3. Select your repo, set main file: `app.py`
4. Deploy — you get a public shareable URL

> **Note on MiniLM:** Streamlit Cloud will install `sentence-transformers` from `requirements.txt`. The first cold start may take 2-3 minutes while it downloads the model weights (~90MB). Subsequent starts are fast.

---

## Data Handling

| Issue | How It's Handled |
|---|---|
| Missing value/amount | Null, excluded from aggregations, flagged in quality score |
| Inconsistent dates | 7 format parsers + ISO substring fallback |
| Mixed currency (₹L/Cr/plain) | Regex parser handles all Indian notation variants |
| Status variations | `STATUS_MAP` keyword matching in `normaliser.py` |
| Unusual column names | MiniLM semantic embedding → Groq LLM → keyword fallback |
| "Dead" deals | Own status label. Included in win rate denominator. |
| Data quality score | 0–100% per board, shown in sidebar, passed to LLM as caveat |

---

## Known Limitations

- Max 500 items per board (Monday.com API page limit — pagination can be added)
- Data refreshed on page load only — no real-time sync
- API keys entered in UI — use Streamlit secrets in production
- 25-row sample sent to LLM — all aggregates pre-computed accurately server-side
- MiniLM cold start on Streamlit Cloud takes ~2-3 min on first deploy
