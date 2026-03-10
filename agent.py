# ─── agent.py ────────────────────────────────────────────────────────────────
# LLM agent layer — system prompt, conversation management, model fallback.
# All AI interaction lives here. Nothing in here knows about Streamlit.

import json
from datetime import datetime
from config import PRIMARY_MODEL, FALLBACK_MODEL, MAX_TOKENS, HISTORY_WINDOW

# ── System Prompt ─────────────────────────────────────────────────────────────
_SYSTEM_PROMPT = """You are Skylark BI — a sharp, senior business intelligence advisor for Skylark Drones, a B2B drone services company in India.

You have access to live data from their Monday.com Deals and Work Orders boards. Think like a CFO, talk like a trusted advisor — direct, confident, grounded in the numbers.

ADAPT YOUR RESPONSE STYLE TO THE QUESTION TYPE:

1. SIMPLE or FOLLOW-UP questions ("what is X?", "why is that?", "how much?")
   → Answer in 2-4 sentences. Conversational. No headings, no bullet lists.
   → Only add a caveat if data quality genuinely changes the answer.

2. ANALYTICAL questions ("which sector is best?", "what deals are at risk?")
   → Lead with a 1-sentence direct answer, then 2-4 supporting bullets if needed.
   → Only include sections that are relevant to THIS specific question.

3. DEEP ANALYSIS requests ("analyse", "break down", "explain in detail", "compare", "what's the risk in")
   → Full detailed response: context, numbers, sector breakdown, risks, recommendation.
   → Use headers and bullets freely. Be thorough. Don't hold back.

4. LEADERSHIP UPDATE or BOARD SUMMARY requests ONLY:
   → Use this exact structure:
   **📊 Headline** → one-sentence business status
   **Key Metrics** → 3-5 bullets with numbers
   **⚠️ Risks** → what needs attention
   **💡 Opportunities** → what to double down on
   **✅ Actions** → 2-3 specific next steps

ALWAYS:
- Use INR formatting: ₹ Lakhs / Crores
- Never fabricate data — if it is not in the board data, say so
- Only mention data quality when it actually changes your answer
- Be opinionated — give a recommendation, not just a summary
- Cross-reference deals and work orders when the question calls for it

NEVER:
- Use the same rigid subheadings on every response regardless of question type
- Add structure sections to simple conversational answers
- Pad with sections that add no value for the specific question asked

Current date: {date}"""


def build_system_prompt() -> str:
    """Return the system prompt with the current date injected."""
    return _SYSTEM_PROMPT.format(date=datetime.now().strftime("%B %Y"))


# ── Agent Call ────────────────────────────────────────────────────────────────
def ask_agent(client, data_ctx: dict, conversation_history: list) -> str:
    """
    Send a conversation to Groq Llama with automatic model fallback.

    Tries PRIMARY_MODEL (llama-3.3-70b-versatile) first.
    On rate-limit (429) or token-limit (413) errors, retries with
    FALLBACK_MODEL (llama-3.1-8b-instant) and appends a small note.

    Args:
        client:               Groq client instance
        data_ctx:             Pre-computed analytics context dict (from analytics.py)
        conversation_history: Full list of {role, content} message dicts

    Returns:
        str: The assistant's response text

    Raises:
        RuntimeError: If both models fail
    """
    system_content = (
        build_system_prompt()
        + "\n\n## LIVE MONDAY.COM DATA\n```json\n"
        + json.dumps(data_ctx, indent=2)
        + "\n```"
    )

    # Trim history to last N messages to stay within token limits
    trimmed = conversation_history[-HISTORY_WINDOW:]
    messages = [{"role": "system", "content": system_content}] + trimmed

    for model in [PRIMARY_MODEL, FALLBACK_MODEL]:
        try:
            response = client.chat.completions.create(
                model=model,
                max_tokens=MAX_TOKENS,
                messages=messages,
            )
            text = response.choices[0].message.content

            if model == FALLBACK_MODEL:
                text += "\n\n*⚡ Answered using llama-3.1-8b (fallback — 70B rate limit reached)*"

            return text

        except Exception as e:
            err = str(e)
            is_rate_limit = any(code in err for code in ["413", "429", "rate_limit", "tokens"])
            if is_rate_limit and model == PRIMARY_MODEL:
                continue  # Retry with fallback model
            raise  # Non-rate-limit error — bubble up

    raise RuntimeError("Both models failed. Please wait a moment and try again.")
