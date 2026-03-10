# ─── config.py ───────────────────────────────────────────────────────────────
# Central place for all constants, model names, and mappings.
# Change model names, URLs, or thresholds here — nothing else needs to change.

# ── Monday.com ────────────────────────────────────────────────────────────────
MONDAY_URL    = "https://api.monday.com/v2"
MONDAY_LIMIT  = 500          # Max items per board fetch

# ── LLM Models ────────────────────────────────────────────────────────────────
PRIMARY_MODEL  = "llama-3.3-70b-versatile"
FALLBACK_MODEL = "llama-3.1-8b-instant"
MAX_TOKENS     = 800
HISTORY_WINDOW = 6           # Number of past messages sent to LLM

# ── Semantic Mapping ──────────────────────────────────────────────────────────
# Concepts the semantic mapper tries to find a column for
FIELD_CONCEPTS = {
    "value":  "The monetary value, price, contract amount, or deal size in rupees",
    "status": "The current stage, phase, or pipeline status of the deal or work order",
    "sector": "The industry sector, vertical, or business segment of the client",
    "date":   "A relevant date such as close date, delivery date, or expected completion",
}

# MiniLM anchor phrases — what each concept "sounds like" as natural language
MINILM_ANCHORS = {
    "value":  "deal value contract amount price revenue rupees money",
    "status": "status stage phase pipeline state progress",
    "sector": "sector industry vertical segment category domain",
    "date":   "date close expected delivery due target deadline",
}

# ── Status Normalisation Map ──────────────────────────────────────────────────
STATUS_MAP = {
    "won":            "Closed Won",
    "closed won":     "Closed Won",
    "closed - won":   "Closed Won",
    "close won":      "Closed Won",

    "lost":           "Closed Lost",
    "closed lost":    "Closed Lost",
    "closed - lost":  "Closed Lost",

    "dead":           "Dead",
    "dead deal":      "Dead",
    "no go":          "Dead",
    "disqualified":   "Dead",

    "in progress":    "In Progress",
    "active":         "In Progress",
    "wip":            "In Progress",
    "ongoing":        "In Progress",
    "executed":       "In Progress",

    "prospect":       "Prospect",
    "lead":           "Prospect",
    "new":            "Prospect",

    "negotiation":    "Negotiation",
    "negotiating":    "Negotiation",

    "proposal":       "Proposal",
    "proposed":       "Proposal",

    "qualified":      "Qualified",

    "completed":      "Completed",
    "done":           "Completed",
    "delivered":      "Completed",
    "closed":         "Completed",

    "pending":        "Pending",
    "waiting":        "Pending",
    "on hold":        "Pending",
    "pause":          "Pending",
    "paused":         "Pending",
    "struck":         "Pending",

    "cancelled":      "Cancelled",
    "canceled":       "Cancelled",

    "open":           "Open",
    "not started":    "Not Started",
}

# ── Sector Normalisation Map ──────────────────────────────────────────────────
SECTOR_MAP = {
    frozenset(["energy", "solar", "wind", "powerline", "electricity", "utilities"]):       "Powerline",
    frozenset(["renewable"]):       "Renewable",
    frozenset(["construction", "infra", "infrastructure", "building", "civil", "real estate"]):     "Construction",
    frozenset(["agriculture", "agri", "farming", "crop", "farm"]):                                  "Agriculture",
    frozenset(["mining", "mine", "quarry", "mineral", "excavation"]):                               "Mining",
    frozenset(["telecom", "telecommunication", "telecomm", "network", "tower", "5g"]):              "Telecom",
    frozenset(["defence", "defense", "military", "armed", "army", "navy", "air force"]):            "Defence",
    frozenset(["logistics", "supply chain", "transport", "freight", "delivery", "warehouse"]):      "Logistics",
    frozenset(["survey", "inspection", "mapping", "lidar", "photogrammetry", "gis"]):               "Survey & Inspection",
    frozenset(["oil", "gas", "petroleum", "refinery", "pipeline", "upstream", "downstream"]):       "Oil & Gas",
    frozenset(["government", "govt", "municipal", "public sector", "smart city", "psu"]):           "Government",
    frozenset(["aviation", "airport", "airline", "aircraft", "aerospace"]):                         "Aviation",
    frozenset(["railways", "railway", "rail", "metro", "train"]):                                   "Railways",
    frozenset(["tender", "bid", "rfp", "rfi", "rfq", "dsp"]):                                      "Tender",
}

# ── Data Quality Thresholds ───────────────────────────────────────────────────
DQ_GOOD = 85    # score >= 85 → green
DQ_WARN = 60    # score >= 60 → yellow, else red

# ── UI Colours ────────────────────────────────────────────────────────────────
COLOUR_PIPELINE = "#1F6FEB"
COLOUR_WON      = "#3FB950"
COLOUR_WINRATE  = "#D29922"
COLOUR_REVENUE  = "#A371F7"
