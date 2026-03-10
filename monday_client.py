# ─── monday_client.py ────────────────────────────────────────────────────────
# All Monday.com GraphQL API interaction.
# Handles auth, queries, pagination, and raw item flattening.
# Nothing in here knows about Streamlit or the LLM.

import json
import requests
from config import MONDAY_URL, MONDAY_LIMIT

# ── GraphQL Queries ───────────────────────────────────────────────────────────
GET_BOARDS = "{ boards(limit: 50) { id name } }"

GET_BOARD_DATA = """
query($id: ID!) {
  boards(ids: [$id]) {
    id name
    columns { id title type }
    items_page(limit: """ + str(MONDAY_LIMIT) + """) {
      items {
        id name
        column_values { id text value column { title type } }
      }
    }
  }
}
"""

# ── API Client ────────────────────────────────────────────────────────────────
def monday_query(token: str, query: str, variables: dict = None) -> dict:
    """
    Execute a Monday.com GraphQL query.
    Returns the data dict on success.
    Raises ConnectionError or ValueError on failure.
    """
    payload = {"query": query}
    if variables:
        payload["variables"] = variables

    try:
        res = requests.post(
            MONDAY_URL,
            headers={
                "Content-Type":  "application/json",
                "Authorization": token,
                "API-Version":   "2024-01",
            },
            json=payload,
            timeout=30,
        )
        res.raise_for_status()
        data = res.json()

        if "errors" in data:
            raise ValueError(data["errors"][0].get("message", "Monday API error"))

        return data.get("data", {})

    except requests.exceptions.Timeout:
        raise ConnectionError("Monday.com request timed out. Please try again.")
    except requests.exceptions.ConnectionError:
        raise ConnectionError("Cannot reach Monday.com API. Check your internet connection.")


def fetch_boards(token: str) -> list:
    """Return list of {id, name} dicts for all boards in the workspace."""
    data = monday_query(token, GET_BOARDS)
    return data.get("boards", [])


def fetch_board_items(token: str, board_id: str) -> list:
    """
    Fetch all items from a board and flatten them to dicts.
    Returns list of flat dicts: {column_title: value, ...}
    """
    data  = monday_query(token, GET_BOARD_DATA, {"id": board_id})
    items = data["boards"][0]["items_page"]["items"]
    return [_flatten_item(i) for i in items]


# ── Internal Helpers ──────────────────────────────────────────────────────────
def _flatten_item(item: dict) -> dict:
    """
    Convert a Monday.com item (with column_values array) into a flat dict.
    Column title → text value.
    Handles JSON-encoded values (status labels, dropdown labels, etc.).
    """
    obj = {"_id": item["id"], "_name": item["name"]}

    for cv in item.get("column_values", []):
        title   = cv.get("column", {}).get("title") or cv.get("id", "unknown")
        val     = cv.get("text") or None
        raw_val = cv.get("value")

        # Try to extract richer label from JSON-encoded value
        if raw_val and raw_val != "null":
            try:
                parsed = json.loads(raw_val)
                if isinstance(parsed, dict):
                    val = parsed.get("text") or parsed.get("label") or val
                elif isinstance(parsed, str):
                    val = parsed
            except (json.JSONDecodeError, TypeError):
                pass  # Keep the text value

        obj[title] = val

    return obj
