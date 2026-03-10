# ─── analytics.py ────────────────────────────────────────────────────────────
# All business intelligence computation.
# Pure functions — no API calls, no UI, no LLM.
# Takes enriched deal/WO dicts from normaliser.py, returns metric dicts.

from datetime import date
from normaliser import fmt_inr
from config import DQ_GOOD, DQ_WARN

# ── Closed statuses excluded from active pipeline ─────────────────────────────
_CLOSED = {"Closed Won", "Closed Lost", "Cancelled", "Dead"}
_WON    = {"Closed Won"}
_LOST   = {"Closed Lost"}
_DEAD   = {"Dead"}
_COMPLETE_WO = {"Completed", "Closed Won", "Delivered", "Done"}


# ── Pipeline Health ───────────────────────────────────────────────────────────
def pipeline_health(deals: list) -> dict:
    """
    Compute pipeline metrics from enriched deal dicts.

    Win rate = Won / (Won + Lost + Dead)
    This treats Dead as unrecovered deals — more accurate than Won/Total.
    Dead is kept as its own label (not "Lost") to preserve ambiguity.

    Returns:
        active, won, lost, dead: filtered deal lists
        total_pipeline: sum of active deal values
        total_won: sum of won deal values
        win_rate: float percentage
        stages: {status_label: count} for active deals only
    """
    won    = [d for d in deals if d["_status"] in _WON]
    lost   = [d for d in deals if d["_status"] in _LOST]
    dead   = [d for d in deals if d["_status"] in _DEAD]
    active = [d for d in deals if d["_status"] not in _CLOSED]

    total_pipeline = sum(d["_value"] or 0 for d in active)
    total_won      = sum(d["_value"] or 0 for d in won)
    total_lost     = sum(d["_value"] or 0 for d in lost)

    decided  = len(won) + len(lost) + len(dead)
    win_rate = round(len(won) / decided * 100, 1) if decided else 0

    stages = {}
    for d in active:
        s = d["_status"]
        stages[s] = stages.get(s, 0) + 1

    return dict(
        active=active, won=won, lost=lost, dead=dead,
        total_pipeline=total_pipeline,
        total_won=total_won,
        total_lost=total_lost,
        win_rate=win_rate,
        stages=stages,
    )


# ── Revenue Metrics ───────────────────────────────────────────────────────────
def revenue_metrics(work_orders: list) -> dict:
    """
    Compute work order revenue metrics.

    Returns:
        completed: list of completed WOs
        in_progress: list of ongoing WOs
        total_revenue: sum of completed WO values
        in_progress_value: sum of ongoing WO values
    """
    completed   = [w for w in work_orders if w["_status"] in _COMPLETE_WO]
    in_progress = [w for w in work_orders if w["_status"] == "In Progress"]

    return dict(
        completed=completed,
        in_progress=in_progress,
        total_revenue=sum(w["_value"] or 0 for w in completed),
        in_progress_value=sum(w["_value"] or 0 for w in in_progress),
    )


# ── Sector Breakdown ──────────────────────────────────────────────────────────
def by_sector(items: list) -> list:
    """
    Group items by _sector, returning sorted list of (sector, {count, value}).
    Sorted by value descending.
    """
    smap = {}
    for item in items:
        s = item.get("_sector") or "Other"
        if s not in smap:
            smap[s] = {"count": 0, "value": 0.0}
        smap[s]["count"] += 1
        smap[s]["value"] += item.get("_value") or 0

    return sorted(smap.items(), key=lambda x: -x[1]["value"])


# ── Data Quality ──────────────────────────────────────────────────────────────
def data_quality(items: list, label: str) -> dict:
    """
    Score data completeness for a list of enriched items.
    Score = % of records with non-null value, status, and sector.

    Returns:
        score: int 0-100
        issues: list of human-readable issue strings
        badge_class: "quality-good" | "quality-warn" | "quality-bad"
    """
    if not items:
        return {"score": 0, "issues": [f"No {label} records found"], "badge_class": "quality-bad"}

    n = len(items)
    missing_value  = sum(1 for i in items if not i.get("_value"))
    missing_status = sum(1 for i in items if not i.get("_status") or i["_status"] == "Unknown")
    missing_sector = sum(1 for i in items if not i.get("_sector") or i["_sector"] == "Other")

    # Score based on 3 dimensions — value weighted most heavily
    value_score  = round((1 - missing_value  / n) * 100)
    status_score = round((1 - missing_status / n) * 100)
    sector_score = round((1 - missing_sector / n) * 100)
    score = round(value_score * 0.5 + status_score * 0.3 + sector_score * 0.2)

    issues = []
    if missing_value  > 0: issues.append(f"{missing_value}/{n} records missing value/amount")
    if missing_status > 0: issues.append(f"{missing_status}/{n} records missing status")
    if missing_sector > 0: issues.append(f"{missing_sector}/{n} records missing sector")

    if score >= DQ_GOOD:
        badge_class = "quality-good"
    elif score >= DQ_WARN:
        badge_class = "quality-warn"
    else:
        badge_class = "quality-bad"

    return {"score": score, "issues": issues, "badge_class": badge_class}


# ── LLM Context Builder ───────────────────────────────────────────────────────
def build_data_context(deals: list, work_orders: list) -> dict:
    """
    Build the JSON context blob sent to the LLM.
    Keeps it small (pre-aggregated + 25-row samples) to stay within
    Groq free tier token limits while preserving analytical accuracy.
    All aggregates are computed here server-side — the LLM only summarises.
    """
    ph = pipeline_health(deals)
    rm = revenue_metrics(work_orders)
    dq_deals = data_quality(deals, "deals")
    dq_wo    = data_quality(work_orders, "work orders")

    return {
        "summary": {
            "total_deals":             len(deals),
            "total_work_orders":       len(work_orders),
            "active_pipeline":         fmt_inr(ph["total_pipeline"]),
            "closed_won_revenue":      fmt_inr(ph["total_won"]),
            "win_rate_pct":            ph["win_rate"],
            "win_rate_formula":        "won / (won + lost + dead)",
            "completed_wo_revenue":    fmt_inr(rm["total_revenue"]),
            "in_progress_wo_value":    fmt_inr(rm["in_progress_value"]),
        },
        "pipeline": {
            "by_stage":      ph["stages"],
            "active_count":  len(ph["active"]),
            "won_count":     len(ph["won"]),
            "lost_count":    len(ph["lost"]),
            "dead_count":    len(ph["dead"]),
            "note":          "Dead = cold/disqualified/on-hold. Included in win rate denominator but kept as separate status label.",
        },
        "deals_by_sector": [
            {"sector": s, "count": d["count"], "value": fmt_inr(d["value"])}
            for s, d in by_sector(deals)
        ],
        "work_orders_by_sector": [
            {"sector": s, "count": d["count"], "value": fmt_inr(d["value"])}
            for s, d in by_sector(work_orders)
        ],
        "data_quality": {
            "deals":       {k: v for k, v in dq_deals.items() if k != "badge_class"},
            "work_orders": {k: v for k, v in dq_wo.items()    if k != "badge_class"},
        },
        "deals_sample": [
            {
                "name":       d["_name"],
                "value":      fmt_inr(d["_value"]),
                "status":     d["_status"],
                "sector":     d["_sector"],
                "close_date": str(d["_close_date"]) if d.get("_close_date") else None,
            }
            for d in deals[:25]
        ],
        "dead_deals_sample": [
            {
                "name":   d["_name"],
                "value":  fmt_inr(d["_value"]),
                "sector": d["_sector"],
            }
            for d in ph["dead"][:25]
        ],
        "work_orders_sample": [
            {
                "name":   w["_name"],
                "value":  fmt_inr(w["_value"]),
                "status": w["_status"],
                "sector": w["_sector"],
            }
            for w in work_orders[:25]
        ],
    }
