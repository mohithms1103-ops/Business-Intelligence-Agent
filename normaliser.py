# ─── normaliser.py ───────────────────────────────────────────────────────────
# Pure data transformation — no API calls, no UI, no LLM.
# Takes raw Monday.com row dicts and produces clean, typed, enriched dicts.
# All functions are stateless and independently testable.

import re
from datetime import datetime, date
from config import STATUS_MAP, SECTOR_MAP

# ── Date Parser ───────────────────────────────────────────────────────────────
_DATE_FORMATS = [
    "%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y",
    "%d-%m-%Y", "%d %b %Y", "%d %B %Y", "%Y/%m/%d",
]

def parse_date(raw) -> date | None:
    """Parse a date string in any of 7 common formats. Returns date or None."""
    if not raw:
        return None
    s = str(raw).strip()
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            pass
    # ISO substring fallback e.g. "2024-03-15T00:00:00Z"
    try:
        return datetime.fromisoformat(s[:10]).date()
    except (ValueError, TypeError):
        return None


# ── Currency Parser ───────────────────────────────────────────────────────────
def parse_money(raw) -> float | None:
    """
    Parse Indian currency strings into a float (rupees).
    Handles: ₹1.5L, 2.3Cr, Rs. 50,000, 1,50,000, plain floats.
    Returns None if unparseable.
    """
    if not raw:
        return None
    s = str(raw).replace(",", "").strip()

    lakh  = re.match(r"[₹Rs.\s]*([\d.]+)\s*[Ll]", s)
    crore = re.match(r"[₹Rs.\s]*([\d.]+)\s*[Cc][Rr]", s)
    if lakh:
        return float(lakh.group(1)) * 100_000
    if crore:
        return float(crore.group(1)) * 10_000_000

    nums = re.sub(r"[^\d.]", "", s)
    try:
        return float(nums) if nums else None
    except ValueError:
        return None


def fmt_inr(n: float | None) -> str:
    """Format a float (rupees) as a human-readable INR string."""
    if n is None:
        return "N/A"
    if n >= 10_000_000:
        return f"₹{n / 10_000_000:.2f}Cr"
    if n >= 100_000:
        return f"₹{n / 100_000:.1f}L"
    return f"₹{n:,.0f}"


# ── Status Normaliser ─────────────────────────────────────────────────────────
def normalise_status(raw: str | None) -> str:
    """
    Map raw status strings to canonical labels using STATUS_MAP.
    Tries exact match, then substring match.
    Returns raw string (title-cased) if no match found.
    """
    if not raw:
        return "Unknown"
    s = raw.strip().lower()

    # Exact match
    if s in STATUS_MAP:
        return STATUS_MAP[s]

    # Substring match — find the longest matching key
    best = None
    best_len = 0
    for key, canonical in STATUS_MAP.items():
        if key in s and len(key) > best_len:
            best = canonical
            best_len = len(key)
    if best:
        return best

    return raw.strip().title()


# ── Sector Normaliser ─────────────────────────────────────────────────────────
def normalise_sector(raw: str | None) -> str:
    """
    Map raw sector/industry strings to canonical sector labels using SECTOR_MAP.
    Returns "Other" if no match found.
    """
    if not raw:
        return "Other"
    s = raw.strip().lower()

    for keywords, canonical in SECTOR_MAP.items():
        if any(kw in s for kw in keywords):
            return canonical

    return raw.strip().title()


# ── Row Enrichment ────────────────────────────────────────────────────────────
def enrich_deal(row: dict, mapping: dict = None) -> dict:
    """
    Enrich a raw deal row with typed, normalised fields.
    Uses semantic mapping dict if provided, falls back to keyword search.
    Adds _value, _status, _sector, _close_date, _type fields.
    """
    m = mapping or {}
    raw_value  = _get_field(row, "value",  m, ["value", "amount", "revenue", "deal size", "contract", "price"])
    raw_status = _get_field(row, "status", m, ["status", "stage", "phase", "pipeline"])
    raw_sector = _get_field(row, "sector", m, ["sector", "industry", "vertical", "segment", "category"])
    raw_date   = _get_field(row, "date",   m, ["close", "expected", "target date", "due date", "date"])

    return {
        **row,
        "_value":      parse_money(raw_value),
        "_status":     normalise_status(raw_status),
        "_sector":     normalise_sector(raw_sector),
        "_close_date": parse_date(raw_date),
        "_type":       "deal",
    }


def enrich_work_order(row: dict, mapping: dict = None) -> dict:
    """
    Enrich a raw work order row with typed, normalised fields.
    Uses semantic mapping dict if provided, falls back to keyword search.
    Adds _value, _status, _sector, _date, _type fields.
    """
    m = mapping or {}
    raw_value  = _get_field(row, "value",  m, ["value", "amount", "contract", "price", "revenue"])
    raw_status = _get_field(row, "status", m, ["status", "stage", "phase"])
    raw_sector = _get_field(row, "sector", m, ["sector", "industry", "vertical", "type", "category"])
    raw_date   = _get_field(row, "date",   m, ["date", "start", "end", "delivery", "due", "created"])

    return {
        **row,
        "_value":  parse_money(raw_value),
        "_status": normalise_status(raw_status),
        "_sector": normalise_sector(raw_sector),
        "_date":   parse_date(raw_date),
        "_type":   "workorder",
    }


# ── Internal Field Lookup ─────────────────────────────────────────────────────
def _get_field(row: dict, field: str, mapping: dict, fallback_patterns: list) -> str | None:
    """
    Get a field value using semantic mapping first, keyword fallback second.
    mapping: {field_name: column_title}
    fallback_patterns: list of substrings to search in column titles
    """
    # Semantic mapping — use exact column name from mapping
    col = mapping.get(field)
    if col and row.get(col):
        return row[col]

    # Keyword fallback — scan all column titles
    for key, val in row.items():
        if key.startswith("_"):
            continue
        if any(p.lower() in key.lower() for p in fallback_patterns) and val:
            return val

    return None
