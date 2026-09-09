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
                 mock: Optional[bool] = None):
        self.api_key = api_key if api_key is not None else settings.openai_api_key
        self.model_name = model or settings.openai_model
        self.mock = mock if mock is not None else (
            settings.mock_mode or not self.api_key
        )
        self._client = None
        # Read by GeminiClient's cascade after it calls into this client, so
        # a silent internal degrade to the mock heuristic (network error,
        # bad key, rate limit) is reported honestly instead of being labelled
        # "openai" just because this class was the one holding the call.
        self.last_provider = "mock" if self.mock else "openai"
        if not self.mock:
            self._init_real_client()

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
            self.last_provider = "mock"
            return _mock_answer(query, context)
