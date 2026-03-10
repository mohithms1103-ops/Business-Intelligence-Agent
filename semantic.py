# ─── semantic.py ─────────────────────────────────────────────────────────────
# Semantic column detection — maps Monday.com column names to semantic fields.
#
# Strategy (in priority order):
#   1. MiniLM-L6-v2 (sentence-transformers) — fast, offline, most accurate
#   2. Groq LLM fallback — if sentence-transformers not installed
#   3. Silent empty dict — normaliser.py keyword matching kicks in
#
# Called ONCE per board load. Result is cached in session state.

import json
import re
from config import FIELD_CONCEPTS, MINILM_ANCHORS

# ── Check MiniLM availability ─────────────────────────────────────────────────
try:
    from sentence_transformers import SentenceTransformer, util
    _model = SentenceTransformer("all-MiniLM-L6-v2")
    MINILM_AVAILABLE = True
except ImportError:
    MINILM_AVAILABLE = False


# ── Public API ────────────────────────────────────────────────────────────────
def semantic_column_map(columns: list, board_type: str, groq_client=None) -> dict:
    """
    Map column names to semantic fields: value, status, sector, date.

    Tries MiniLM first (offline, fast), then Groq LLM (API), then returns {}
    so normaliser.py keyword matching handles it silently.

    Args:
        columns:      List of column name strings from the Monday.com board
        board_type:   Human label e.g. "Deals/Pipeline" (used in Groq prompt)
        groq_client:  Groq client instance (only used if MiniLM unavailable)

    Returns:
        dict like {"value": "Masked Deal value", "status": "Deal Status", ...}
        Only includes fields where a confident match was found.
    """
    clean_cols = [c for c in columns if c and not c.startswith("_")]
    if not clean_cols:
        return {}

    if MINILM_AVAILABLE:
        return _map_with_minilm(clean_cols)
    elif groq_client:
        return _map_with_groq(clean_cols, board_type, groq_client)
    else:
        return {}


def mapping_method_label() -> str:
    """Return a human-readable label for which mapping method is active."""
    return "MiniLM-L6-v2 (local, offline)" if MINILM_AVAILABLE else "Groq LLM (API fallback)"


# ── MiniLM Implementation ─────────────────────────────────────────────────────
def _map_with_minilm(columns: list) -> dict:
    """
    Use sentence-transformers MiniLM-L6-v2 to embed column names and anchors,
    then find the closest column for each semantic field via cosine similarity.

    Threshold: 0.35 — columns below this score are skipped (no forced match).
    """
    THRESHOLD = 0.35

    # Embed all column names at once (batched, fast)
    col_embeddings = _model.encode(columns, convert_to_tensor=True)

    mapping = {}
    for field, anchor_phrase in MINILM_ANCHORS.items():
        anchor_embedding = _model.encode(anchor_phrase, convert_to_tensor=True)
        scores = util.cos_sim(anchor_embedding, col_embeddings)[0]

        best_idx   = int(scores.argmax())
        best_score = float(scores[best_idx])

        if best_score >= THRESHOLD:
            mapping[field] = columns[best_idx]

    return mapping


# ── Groq LLM Fallback ─────────────────────────────────────────────────────────
def _map_with_groq(columns: list, board_type: str, groq_client) -> dict:
    """
    Ask Llama 3.3 70B to map column names to semantic fields.
    Used when sentence-transformers is not installed.
    Returns {} silently on any failure.
    """
    col_list = "\n".join(f"- {c}" for c in columns)
    concepts = "\n".join(f'- "{k}": {v}' for k, v in FIELD_CONCEPTS.items())

    prompt = f"""You are mapping column names from a {board_type} board to semantic fields.

Column names:
{col_list}

Map each semantic field to the BEST matching column. Return ONLY valid JSON, no explanation.
Semantic fields:
{concepts}

Example: {{"value": "Masked Deal value", "status": "Deal Status", "sector": "Sector/service", "date": "Close Date (A)"}}"""

    try:
        response = groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            max_tokens=200,
            messages=[{"role": "user", "content": prompt}],
        )
        text = response.choices[0].message.content.strip()
        text = re.sub(r"```json|```", "", text).strip()
        mapping = json.loads(text)
        # Only keep mappings where the column actually exists
        return {k: v for k, v in mapping.items() if v in columns}
    except Exception:
        return {}  # Silently fall through to keyword matching
