"""
Indonesian vs Javanese detection for one incoming message.

A crude keyword-cue heuristic, not a classifier: the same approach already
used by tools/eval_llm_lang.py to grade replies, formalised here into the
one function the orchestrator actually calls to decide which language
instruction to put in the system prompt for this turn. It is deliberately
biased toward the session's prior language on a tie or on a very short
message ("piro?" alone is Javanese; "ok" alone tells you nothing), since a
wrong guess mid-conversation reads far worse than staying in the language
the last few turns were already in.

This is not meant to be precise. It is meant to be cheap, dependency-free,
and right often enough that a wrong guess is rare and self-correcting: the
system prompt always tells the model to answer in whichever language the
user's own message is actually in, so this function's job is only to pick
the STARTING instruction, not to be the final word on what language comes
back.
"""
from __future__ import annotations

# Javanese function words and the survival vocabulary this project's own
# system prompts already teach the model (see gemini_client.INTENT_SYSTEM_PROMPT),
# kept in sync with tools/eval_llm_lang.py's JV_CUES by hand since the two
# serve different purposes (grading a reply vs routing a question) and a
# shared import would couple a test tool to production code.
JV_CUES = frozenset({
    "ing", "iki", "iku", "kuwi", "pira", "piro", "regane", "piye", "kepiye",
    "endi", "sing", "kang", "opo", "apa", "ora", "mboten", "nggih", "inggih",
    "sampeyan", "panjenengan", "kula", "aku", "dhewe", "kabeh", "kadospundi",
    "menapa", "pundi", "wonten", "saking", "dhateng", "badhe", "arep", "golek",
    "tuku", "tumbas", "adol", "dodol", "duwe", "gadhah", "lombok", "brambang",
    "sega", "wos", "endhog", "pitik", "dinten", "dina", "regi", "rega",
})
ID_CUES = frozenset({
    "yang", "di", "ini", "itu", "berapa", "bagaimana", "mana", "apa", "anda",
    "kamu", "saya", "tidak", "harga", "data", "untuk", "dengan", "adalah",
    "hari", "kapan", "kenapa", "mengapa", "dimana", "bisa", "mau", "ingin",
})


def detect_language(text: str, prior_lang: str = "id") -> str:
    """Return "id" or "jv". `prior_lang` is the session's language from the
    last turn (or "id" for a brand-new session); it wins ties and very short
    messages, since staying consistent within a conversation matters more
    than reacting to a single ambiguous word."""
    words = [w.strip(".,?!:;()\"'").lower() for w in text.split()]
    words = [w for w in words if w]
    if len(words) < 2:
        return prior_lang if prior_lang in ("id", "jv") else "id"
    jv_hits = sum(1 for w in words if w in JV_CUES)
    id_hits = sum(1 for w in words if w in ID_CUES)
    if jv_hits == 0 and id_hits == 0:
        return prior_lang if prior_lang in ("id", "jv") else "id"
    if jv_hits == id_hits:
        return prior_lang if prior_lang in ("id", "jv") else "id"
    return "jv" if jv_hits > id_hits else "id"
