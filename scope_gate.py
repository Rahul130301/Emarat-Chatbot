# scope_gate.py
"""Pre-agent gate: blocks non-English and off-topic messages in code, before
they reach the agent. This is deliberately NOT a prompt instruction — prompt-
only 'stay in scope/English' guidance is followed inconsistently across
turns (same lesson as the validate_sql/run_sql fix earlier in this project).
One LLM call judges both language and scope together, because a script-based
language detector would incorrectly pass romanized/Hinglish text as English."""
import os
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv(override=True)

_client = OpenAI(
    base_url=f"{os.environ['AZURE_OPENAI_ENDPOINT'].rstrip('/')}/openai/v1",
    api_key=os.environ["AZURE_OPENAI_API_KEY"],
)
_DEPLOYMENT = os.environ["AZURE_OPENAI_DEPLOYMENT_NAME"]

SCOPE_DESCRIPTIONS = {
    "contracts": "commercial contracts, sales transactions, client companies, contract values, renewal terms, and contract documents/clauses",
    "aviation": "aircraft refueling operations, fuel uplifts (measured in Litres), flight movements, airline fuel consumption, aircraft types, and parking stands",
}

LANGUAGE_DECLINE = "I'm only able to help in English right now. Could you please ask your question in English?"

def _scope_decline(agent_type: str) -> str:
    topic = SCOPE_DESCRIPTIONS.get(agent_type, SCOPE_DESCRIPTIONS["contracts"])
    label = "Aviation Operations" if agent_type == "aviation" else "Contracts"
    return (
        f"I'm the Emarat {label} assistant, and I can only help with questions about "
        f"{topic}. That's outside what I have data for — is there something in that "
        f"area I can help with instead?"
    )

# scope_gate.py — updated check_gate()

META_DECLINE = (
    "I can't share internal query or system implementation details — that's "
    "not something I expose. Happy to explain what a result means, or rerun "
    "it with different filters, if that helps."
)

def check_gate(message: str, agent_type: str) -> str | None:
    """Returns a decline message if the request should be blocked, else None."""
    topic = SCOPE_DESCRIPTIONS.get(agent_type, SCOPE_DESCRIPTIONS["contracts"])
    prompt = (
        f"A chatbot only answers ENGLISH-language questions about: {topic}.\n"
        f"It must never reveal internal implementation details — SQL queries, "
        f"table/column names, schema structure, which internal tool or "
        f"function handled the request, or how it works internally.\n"
        f"User message: {message!r}\n\n"
        "1. Is this written in English? (Romanized/transliterated text in another "
        "language — e.g. Hindi written in Latin letters — counts as NOT English, "
        "even though the letters look Latin.)\n"
        "2. Is this asking about the system's internal implementation (its SQL, "
        "database schema, table/column names, which tool/function ran, source "
        "code, or 'how do you work') rather than about the data itself?\n"
        "3. If neither of the above, is it within the topic scope above, OR a "
        "reasonable follow-up about the conversation itself (e.g. 'show that as "
        "a chart', 'what did you mean', greetings, thanks)?\n\n"
        "Reply with EXACTLY one word: OK or NOT_ENGLISH or META or OUT_OF_SCOPE"
    )
    resp = _client.chat.completions.create(
        model=_DEPLOYMENT, messages=[{"role": "user", "content": prompt}],
    )
    verdict = resp.choices[0].message.content.strip().upper()
    if "NOT_ENGLISH" in verdict:
        return LANGUAGE_DECLINE
    if "META" in verdict:
        return META_DECLINE
    if "OUT_OF_SCOPE" in verdict:
        return _scope_decline(agent_type)
    return None