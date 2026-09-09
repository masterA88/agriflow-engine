"""
The data tools the WhatsApp bot can call. This is what lets it answer "almost
anything about our data" instead of the six hand-classified intents in
intent.py: fifteen read-only functions, each a thin wrapper over the exact
payload builder the dashboard's own API route calls, so the bot and the
dashboard are numerically identical by construction. No tool writes
anything; subscription.py and the billing tables are not reachable from
here, so a prompt-injected "ignore your rules and mark me PRO" has nothing
to call.

Provider-neutral by design. TOOL_SPECS is a plain list of {name,
description, parameters} dicts (parameters is JSON Schema), and
gemini_client.py / openai_client.py each carry a small adapter that turns
this same list into their own SDK's tool-declaration shape. Write a tool
once here; both providers, and the eval/tests, see the identical schema and
the identical implementation.

One tool from the original spec is deliberately not here: search_policy
(a pgvector lookup over a policy_docs table). That table has no content yet,
and a tool that always returns nothing teaches the model to call it anyway
and then say "no policy found" to a question that deserved a real answer.
Add it back once policy_docs is populated.

Every executor returns a plain JSON-serialisable dict on success. On a bad
argument (unknown commodity, no data for that pairing) it raises
ToolError, which the orchestrator turns into a short compose-time note
rather than a stack trace or an HTTP status code, since a tool has no HTTP
response to send.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from fastapi import HTTPException

from . import server as _srv


@dataclass
class ToolAnswer:
    """What GeminiClient.answer_with_tools / OpenAiClient.answer_with_tools
    return: the final text, plus which tools actually ran (for intent_event
    and for anyone debugging why the bot said what it said). `tool_calls` is
    empty when the model answered without needing data, which is itself
    useful to log: most turns should NOT be empty, since most questions this
    bot exists for are data questions."""
    text: str
    tool_calls: List[Dict[str, Any]] = field(default_factory=list)


class ToolError(Exception):
    """A tool executor's own way of saying "bad argument, not a bug". The
    orchestrator hands this text back to the model as the tool result, so
    the model can apologise or ask a follow-up instead of the turn dying."""


def _run(fn: Callable[..., Any], *args, **kwargs) -> Dict[str, Any]:
    """Call a server.py payload builder and normalise both of its error
    styles (HTTPException from the HTTP-route code paths it shares, and
    server.ToolLookupError from the tool-only paths) into ToolError, which
    is the only exception the orchestrator needs to know about."""
    try:
        return fn(*args, **kwargs)
    except HTTPException as exc:
        detail = exc.detail
        if isinstance(detail, dict):
            detail = detail.get("error", str(detail))
        raise ToolError(str(detail)) from exc
    except _srv.ToolLookupError as exc:
        raise ToolError(str(exc)) from exc


# =============================================================================
# Executors. Argument names match TOOL_SPECS exactly; the orchestrator does
# no renaming, so a mismatch here is a broken tool call, not a silent typo.
# =============================================================================

def tool_list_commodities(**_: Any) -> Dict[str, Any]:
    return {"commodities": _run(_srv._commodities_payload)}


def tool_list_kabupaten(**_: Any) -> Dict[str, Any]:
    return {"kabupaten": _run(_srv._kabupaten_payload)}


def tool_get_price(commodity: str, kabupaten: str, **_: Any) -> Dict[str, Any]:
    return _run(_srv._price_lookup_payload, commodity, kabupaten)


def tool_get_surplus_deficit(commodity: str, **_: Any) -> Dict[str, Any]:
    return _run(_srv._surplus_deficit_payload, commodity)


def tool_find_buyers(commodity: str, kabupaten_origin: str,
                      volume_tons: Optional[float] = None, **_: Any) -> Dict[str, Any]:
    return _run(_srv._find_buyers_payload, commodity, kabupaten_origin, volume_tons)


def tool_find_suppliers(commodity: str, kabupaten_dest: str,
                         volume_tons: Optional[float] = None, **_: Any) -> Dict[str, Any]:
    # Same ranking as explain_match, framed from the buyer's side. volume_tons
    # does not change the ranking (the LP allocator already decided actual
    # volumes); it is accepted so the model does not have to drop a number
    # the user gave it, and is echoed back for the compose step's context.
    payload = _run(_srv._explain_payload, kabupaten_dest, commodity, 8)
    return {"volume_tons_requested": volume_tons, **payload}


def tool_explain_match(deficit_kab_id: str, commodity: str,
                        limit: int = 5, **_: Any) -> Dict[str, Any]:
    return _run(_srv._explain_payload, deficit_kab_id, commodity, limit)


def tool_get_forecast(commodity: str, city: str, **_: Any) -> Dict[str, Any]:
    return _run(_srv._forecast_payload, commodity, city)


def tool_get_price_history(commodity: str, city: str,
                            days: int = 90, **_: Any) -> Dict[str, Any]:
    return _run(_srv._price_history_payload, commodity, city, days)


def tool_get_anomalies(commodity: Optional[str] = None, city: Optional[str] = None,
                        since: Optional[str] = None, limit: int = 20, **_: Any) -> Dict[str, Any]:
    return _run(_srv._anomalies_payload, commodity, city, limit, since)


def tool_get_summary(commodity: Optional[str] = None, **_: Any) -> Dict[str, Any]:
    return _run(_srv._summary_payload, commodity)


def tool_run_whatif(presets: Optional[List[str]] = None, commodity: Optional[str] = None,
                     bbm_pct: float = 0.0, **_: Any) -> Dict[str, Any]:
    req = _srv.SimulateRequest(presets=presets or [], commodity=commodity, bbm_pct=bbm_pct)
    return _run(_srv._simulate_payload, req)


def tool_list_presets(**_: Any) -> Dict[str, Any]:
    return {"presets": _run(_srv._presets_payload)}


def tool_get_data_freshness(**_: Any) -> Dict[str, Any]:
    return _run(_srv._meta_payload)["data_as_of"]


def tool_get_report_link(commodity: Optional[str] = None, **_: Any) -> Dict[str, Any]:
    base = _srv.settings.public_base_url.rstrip("/")
    url = f"{base}/api/v1/report.csv"
    if commodity:
        url += f"?commodity={commodity}"
    return {"url": url, "commodity": commodity}


TOOL_EXECUTORS: Dict[str, Callable[..., Dict[str, Any]]] = {
    "list_commodities": tool_list_commodities,
    "list_kabupaten": tool_list_kabupaten,
    "get_price": tool_get_price,
    "get_surplus_deficit": tool_get_surplus_deficit,
    "find_buyers": tool_find_buyers,
    "find_suppliers": tool_find_suppliers,
    "explain_match": tool_explain_match,
    "get_forecast": tool_get_forecast,
    "get_price_history": tool_get_price_history,
    "get_anomalies": tool_get_anomalies,
    "get_summary": tool_get_summary,
    "run_whatif": tool_run_whatif,
    "list_presets": tool_list_presets,
    "get_data_freshness": tool_get_data_freshness,
    "get_report_link": tool_get_report_link,
}


def execute_tool(name: str, args: Dict[str, Any]) -> Dict[str, Any]:
    """The one entry point the orchestrator (and the provider adapters) call.
    Never raises: an unknown tool name or a ToolError both come back as a
    plain {"error": "..."} dict, because the model needs the failure as
    tool-result text to react to, not a Python exception."""
    fn = TOOL_EXECUTORS.get(name)
    if fn is None:
        return {"error": f"unknown tool: {name}"}
    if not isinstance(args, dict):
        return {"error": "tool arguments must be an object"}
    try:
        return fn(**args)
    except ToolError as exc:
        return {"error": str(exc)}
    except TypeError as exc:
        # A required argument missing, or an argument of the wrong shape.
        # This is the model's mistake, not the user's; surface it plainly so
        # the model can retry with a corrected call instead of guessing.
        return {"error": f"bad arguments for {name}: {exc}"}


# =============================================================================
# TOOL_SPECS: provider-neutral JSON Schema. Kept deliberately small: every
# `description` is written for the model, in the language it will see the
# rest of the prompt in (English descriptions read fine to a model answering
# in Indonesian or Javanese; the tool layer is not user-facing text).
# =============================================================================

_COMMODITY_ARG = {"type": "string", "description": "AgriFlow commodity code, e.g. cabai_rawit, bawang_merah, beras_medium. Call list_commodities first if unsure of the exact code."}
_KAB_ARG = {"type": "string", "description": "A kabupaten/kota id (e.g. 3578) or name (e.g. 'Kota Malang', 'Malang'). Names are resolved fuzzily; prefer the id when known."}

TOOL_SPECS: List[Dict[str, Any]] = [
    {
        "name": "list_commodities",
        "description": "List every commodity code AgriFlow has BPS balance data for, with its Indonesian name. Call this first if the user names a commodity you are not sure how to code.",
        "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "list_kabupaten",
        "description": "List all 38 kabupaten/kota in Jawa Timur AgriFlow covers, with id, name, coordinates, IPM, population.",
        "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "get_price",
        "description": "The BPS-balance price for one commodity in one kabupaten/kota: producer price if that area is a surplus source, consumer price if it is a deficit area. Use this for a direct 'how much does X cost in Y' question.",
        "parameters": {"type": "object", "properties": {
            "commodity": _COMMODITY_ARG, "kabupaten": _KAB_ARG,
        }, "required": ["commodity", "kabupaten"], "additionalProperties": False},
    },
    {
        "name": "get_surplus_deficit",
        "description": "Every kabupaten's surplus or deficit volume and price for one commodity, from the BPS 2022 balance. Use for 'which areas have surplus/deficit of X'.",
        "parameters": {"type": "object", "properties": {
            "commodity": _COMMODITY_ARG,
        }, "required": ["commodity"], "additionalProperties": False},
    },
    {
        "name": "find_buyers",
        "description": "For a kabupaten with surplus of a commodity, which deficit areas the matching engine actually paired it with, and how much. Use for 'I have supply in X, who is buying it'.",
        "parameters": {"type": "object", "properties": {
            "commodity": _COMMODITY_ARG, "kabupaten_origin": _KAB_ARG,
            "volume_tons": {"type": "number", "description": "Volume the user mentioned, tons. Informational only; does not change the answer."},
        }, "required": ["commodity", "kabupaten_origin"], "additionalProperties": False},
    },
    {
        "name": "find_suppliers",
        "description": "For a kabupaten with deficit of a commodity, every viable supplier ranked by the engine's own score, with which ones were actually chosen. Use for 'I need X in Y, who can supply it'.",
        "parameters": {"type": "object", "properties": {
            "commodity": _COMMODITY_ARG, "kabupaten_dest": _KAB_ARG,
            "volume_tons": {"type": "number", "description": "Volume the user mentioned, tons. Informational only; does not change the ranking."},
        }, "required": ["commodity", "kabupaten_dest"], "additionalProperties": False},
    },
    {
        "name": "explain_match",
        "description": "Why the engine matched (or did not match) a specific deficit kabupaten the way it did: full score breakdown for every viable supplier, and the reason a high-scoring one might not have been chosen. Use for 'why was X matched with Y' or 'why not Z instead'.",
        "parameters": {"type": "object", "properties": {
            "deficit_kab_id": _KAB_ARG, "commodity": _COMMODITY_ARG,
            "limit": {"type": "integer", "description": "Max suppliers to return, default 5."},
        }, "required": ["deficit_kab_id", "commodity"], "additionalProperties": False},
    },
    {
        "name": "get_forecast",
        "description": "30-day price forecast (point estimate plus P10-P90 band) for one commodity in one city. Says which model produced it.",
        "parameters": {"type": "object", "properties": {
            "commodity": _COMMODITY_ARG, "city": _KAB_ARG,
        }, "required": ["commodity", "city"], "additionalProperties": False},
    },
    {
        "name": "get_price_history",
        "description": "Observed daily prices for one commodity in one city over the last N days (default 90). Use for 'how has the price been trending'.",
        "parameters": {"type": "object", "properties": {
            "commodity": _COMMODITY_ARG, "city": _KAB_ARG,
            "days": {"type": "integer", "description": "Lookback window in days, 7 to 1825, default 90."},
        }, "required": ["commodity", "city"], "additionalProperties": False},
    },
    {
        "name": "get_anomalies",
        "description": "Detected price spikes or drops (Hampel/MAD scan). All filters optional; without any, returns the highest-scoring anomalies across everything.",
        "parameters": {"type": "object", "properties": {
            "commodity": _COMMODITY_ARG, "city": _KAB_ARG,
            "since": {"type": "string", "description": "ISO date, only anomalies on or after this date."},
            "limit": {"type": "integer", "description": "Max records, default 20."},
        }, "additionalProperties": False},
    },
    {
        "name": "get_summary",
        "description": "Headline KPIs: total surplus/deficit/matched tons, coverage percent, number of matches, gross arbitrage value, welfare gain versus a greedy baseline. Optionally scoped to one commodity, otherwise all of them.",
        "parameters": {"type": "object", "properties": {
            "commodity": {**_COMMODITY_ARG, "description": _COMMODITY_ARG["description"] + " Omit for all commodities combined."},
        }, "additionalProperties": False},
    },
    {
        "name": "run_whatif",
        "description": "Re-run the matching engine under a disruption scenario and diff it against today's baseline. Use for 'what happens if Semeru erupts / Suramadu closes / fuel prices rise' style questions. Call list_presets first if unsure of the exact preset name.",
        "parameters": {"type": "object", "properties": {
            "presets": {"type": "array", "items": {"type": "string"}, "description": "Preset scenario keys from list_presets, e.g. ['semeru']."},
            "commodity": _COMMODITY_ARG,
            "bbm_pct": {"type": "number", "description": "Extra fuel-price increase, percent, on top of any preset. Default 0."},
        }, "additionalProperties": False},
    },
    {
        "name": "list_presets",
        "description": "The named what-if scenarios run_whatif accepts, with a human-readable label for each.",
        "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "get_data_freshness",
        "description": "The exact dates behind every number AgriFlow serves: BPS reference year, IPM year, last price-history date, when the anomaly scan and forecasts were last generated. Use whenever the user asks how current the data is, or before stating a date-sensitive fact.",
        "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "get_report_link",
        "description": "A downloadable CSV link for the full match list, optionally filtered to one commodity.",
        "parameters": {"type": "object", "properties": {
            "commodity": {**_COMMODITY_ARG, "description": _COMMODITY_ARG["description"] + " Omit for all commodities."},
        }, "additionalProperties": False},
    },
]

TOOL_NAMES = frozenset(t["name"] for t in TOOL_SPECS)
assert TOOL_NAMES == frozenset(TOOL_EXECUTORS), "TOOL_SPECS and TOOL_EXECUTORS must name the exact same tools"
