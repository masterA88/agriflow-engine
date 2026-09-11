"""
OpenAI LLM wrapper. The second tier of the classify/answer cascade.

Same two-method contract as gemini_client.GeminiClient (classify_intent,
answer_with_context), the same system prompts, and the same keyword-based
mock fallback, so GeminiClient can hold one of these as a fallback and call
either interchangeably. This file has no callers of its own: server.py,
intent.py, and handlers.py only ever import GeminiClient. This client is
constructed BY GeminiClient (see gemini_client.py) when OPENAI_API_KEY is
set, and is also usable standalone for the language eval in
tools/eval_llm_lang.py.

Uses the Responses API (client.responses.create), which is OpenAI's current
recommended interface as of September 2026, not the older Chat Completions
API. Verified against https://developers.openai.com/api/docs/quickstart and
https://developers.openai.com/api/docs/pricing on 2026-09-09. Re-check
before trusting the model name or price in a comment here after that date;
this line of models turns over as fast as Gemini's did (2.5 to 3.8 in four
months, see docs/SETUP_MANYCHAT_LLM.md).
"""

from __future__ import annotations
import json
import logging
import re
from typing import Any, Dict, Optional

from .config import settings

log = logging.getLogger("agriflow.llm")
from .gemini_client import (
    ANSWER_SYSTEM_PROMPT,
    INTENT_SYSTEM_PROMPT,
    _mock_answer,
    _mock_classify,
)


class OpenAiClient:
    """Wrapper for the openai package. Auto-falls back to mock if no API key."""

    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None,
                 mock: Optional[bool] = None, enable_fallback: bool = True):
        self.api_key = api_key if api_key is not None else settings.openai_api_key
        self.model_name = model or settings.openai_model
        self.mock = mock if mock is not None else (
            settings.mock_mode or not self.api_key
        )
        self._client = None
        # Read by the cascade after it calls into this client, so a silent
        # internal degrade to the mock heuristic (network error, bad key,
        # rate limit) is reported honestly instead of being labelled
        # "openai" just because this class was the one holding the call.
        self.last_provider = "mock" if self.mock else "openai"
        if not self.mock:
            self._init_real_client()
        # Symmetric to GeminiClient: when this client is primary, Gemini is
        # the tier underneath it. Built with enable_fallback=False so the two
        # never construct each other in a loop.
        self._fallback = None
        if enable_fallback and not self.mock and settings.gemini_api_key:
            from .gemini_client import GeminiClient
            self._fallback = GeminiClient(enable_fallback=False)

    def _init_real_client(self) -> None:
        try:
            from openai import OpenAI
        except ImportError as e:
            raise RuntimeError(
                "openai package not installed. Run: pip install openai"
            ) from e
        self._client = OpenAI(api_key=self.api_key)

    # -------------------------------------------------------------------------
    # Intent classification
    # -------------------------------------------------------------------------

    def classify_intent(self, message: str) -> Dict[str, Any]:
        """Return {"intent": str, "slots": dict}. Falls back to {"intent": "fallback"}."""
        if self.mock:
            self.last_provider = "mock"
            return _mock_classify(message)

        try:
            resp = self._client.responses.create(
                model=self.model_name,
                instructions=INTENT_SYSTEM_PROMPT,
                input=f"Pesan pengguna: {message!r}\n\nOutput JSON:",
            )
            text = (resp.output_text or "").strip()
            text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.MULTILINE).strip()
            parsed = json.loads(text)
            if "intent" not in parsed:
                raise ValueError("OpenAI response carried no 'intent' key")
            parsed.setdefault("slots", {})
            self.last_provider = "openai"
            return parsed
        except Exception as exc:
            log.warning("llm.openai_classify_failed err=%s", type(exc).__name__)
            if self._fallback is not None:
                # Trust the fallback's own last_provider rather than the fact
                # that the call returned, or a silent degrade inside it would
                # be mislabelled "gemini".
                parsed = self._fallback.classify_intent(message)
                self.last_provider = self._fallback.last_provider
                return parsed
            self.last_provider = "mock"
            return {"intent": "fallback", "slots": {}}

    # -------------------------------------------------------------------------
    # Free-form answer with RAG context
    # -------------------------------------------------------------------------

    def answer_with_context(self, query: str, context: str) -> str:
        if self.mock:
            self.last_provider = "mock"
            return _mock_answer(query, context)

        system = ANSWER_SYSTEM_PROMPT.format(context=context)
        try:
            resp = self._client.responses.create(
                model=self.model_name,
                instructions=system,
                input=f"Pertanyaan pengguna: {query}\n\nJawaban:",
            )
            text = (resp.output_text or "").strip()
            if not text:
                raise ValueError("OpenAI returned an empty answer")
            self.last_provider = "openai"
            return text
        except Exception as exc:
            log.warning("llm.openai_answer_failed err=%s", type(exc).__name__)
            if self._fallback is not None:
                text = self._fallback.answer_with_context(query, context)
                self.last_provider = self._fallback.last_provider
                return text
            self.last_provider = "mock"
            return _mock_answer(query, context)

    # -------------------------------------------------------------------------
    # Function-calling answer over the data tools (whatsapp_bot/tools.py)
    # -------------------------------------------------------------------------

    _openai_tools: Any = None  # built once per process; TOOL_SPECS is static

    def answer_with_tools(self, system: str, message: str) -> "ToolAnswer":
        """Mirrors GeminiClient.answer_with_tools exactly: same system
        prompt, same tools.py, same two-round-trip bound, same tool-call
        logging shape. See that method's docstring for the full contract.

        Falls through to self._fallback (a GeminiClient) when this client is
        the primary tier, and straight to the fixed apology when it is not.
        Which case applies is decided at construction by enable_fallback, so
        a cascade is never more than two providers deep in either order."""
        from .tools import ToolAnswer

        if self.mock:
            self.last_provider = "mock"
            return ToolAnswer(text=_MOCK_TOOL_ANSWER)
        try:
            answer = self._openai_answer_with_tools(system, message)
            self.last_provider = "openai"
            return answer
        except Exception as exc:
            log.warning("llm.openai_tools_failed err=%s", type(exc).__name__)
            if self._fallback is not None:
                answer = self._fallback.answer_with_tools(system, message)
                self.last_provider = self._fallback.last_provider
                return answer
            self.last_provider = "mock"
            return ToolAnswer(text=_MOCK_TOOL_ANSWER)

    def _openai_answer_with_tools(self, system: str, message: str) -> "ToolAnswer":
        from .tools import TOOL_SPECS, ToolAnswer, execute_tool

        if OpenAiClient._openai_tools is None:
            OpenAiClient._openai_tools = [
                {"type": "function", "name": t["name"], "description": t["description"],
                 "parameters": t["parameters"], "strict": False}
                for t in TOOL_SPECS
            ]
            # strict=False: several tool schemas here have optional fields
            # (not every property in `required`), which OpenAI's strict mode
            # rejects outright. Loosening this is the honest tradeoff, not a
            # workaround for a bug: the same schema also serves Gemini, which
            # has no equivalent strict flag.

        conversation: list = [{"role": "user", "content": message}]
        calls_made: List[Dict[str, Any]] = []
        # Same bound as GeminiClient.answer_with_tools: up to 2 tool calls,
        # each its own round trip, before a final tools-disabled call forces
        # a text answer. See that method's comment for the full rationale.
        for _ in range(2):
            resp = self._client.responses.create(
                model=self.model_name, instructions=system,
                input=conversation, tools=OpenAiClient._openai_tools,
            )
            fn_calls = [item for item in resp.output if getattr(item, "type", None) == "function_call"]
            if not fn_calls:
                text = (resp.output_text or "").strip()
                if not text:
                    raise ValueError("OpenAI returned neither a tool call nor text")
                return ToolAnswer(text=text, tool_calls=calls_made)
            fc = fn_calls[0]
            try:
                args = json.loads(fc.arguments or "{}")
            except json.JSONDecodeError:
                args = {}
            result = execute_tool(fc.name, args)
            calls_made.append({"name": fc.name, "args": args, "ok": "error" not in result})
            for item in resp.output:
                dumped = item.model_dump() if hasattr(item, "model_dump") else dict(item)
                # The Responses API stamps read-only bookkeeping on output items
                # and then refuses the same field back as input on the next turn
                # ("Unknown parameter: 'input[1].status'"). Echoing the item is
                # required to keep the call_id linkage, so drop the field instead.
                dumped.pop("status", None)
                conversation.append(dumped)
            conversation.append({
                "type": "function_call_output", "call_id": fc.call_id,
                "output": json.dumps(result, ensure_ascii=False),
            })
        resp = self._client.responses.create(model=self.model_name, instructions=system, input=conversation)
        text = (resp.output_text or "").strip()
        if not text:
            raise ValueError("OpenAI produced no final text after the tool round trip")
        return ToolAnswer(text=text, tool_calls=calls_made)


# Same fixed degrade string GeminiClient uses, kept as one shared string
# would require an import cycle; two literals this short are not worth one.
_MOCK_TOOL_ANSWER = (
    "Maaf, saya sedang tidak bisa mengambil data untuk menjawab ini. "
    "Coba lagi sebentar lagi, atau buka dashboard di agriflow.farm."
)
