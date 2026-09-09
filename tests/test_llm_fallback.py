"""
The Gemini -> OpenAI -> mock cascade in GeminiClient.

No real network calls anywhere here. Gemini's SDK client is a small fake with
a controllable `.models.generate_content`; OpenAI is exercised through
OpenAiClient itself in mock mode (already covered on its own by
TestOpenAiClientStandalone), plus one fake for the "OpenAI silently degraded"
case that the wiring must not mislabel as a real OpenAI answer.
"""
from __future__ import annotations

import dataclasses
import os
import sys

os.environ.setdefault("MOCK_MODE", "true")

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import pytest

from whatsapp_bot import gemini_client as gc
from whatsapp_bot import openai_client as oc
from whatsapp_bot.openai_client import OpenAiClient


def _with_settings(module, **changes):
    """Settings is a frozen dataclass, so a test can't mutate a field on the
    shared singleton. Rebind the module's `settings` name to a patched copy
    instead. dataclasses.replace() makes a new frozen instance with just
    the given fields changed, everything else copied from the current one.
    Returns the value to pass to monkeypatch.setattr(module, "settings", ...).
    """
    return dataclasses.replace(module.settings, **changes)


class _FakeResp:
    def __init__(self, text):
        self.text = text


class _FakeModels:
    """Stands in for genai.Client().models. `answers` is a list consumed in
    order (one entry per generate_content call); an exception instance in the
    list is raised instead of returned, so a test can script "first call
    fails, second succeeds" if it ever needs to."""

    def __init__(self, answers):
        self._answers = list(answers)
        self.calls = 0

    def generate_content(self, model, contents):
        self.calls += 1
        item = self._answers.pop(0)
        if isinstance(item, Exception):
            raise item
        return _FakeResp(item)


class _FakeGeminiSdkClient:
    def __init__(self, answers):
        self.models = _FakeModels(answers)


def make_client(answers, fallback=None) -> gc.GeminiClient:
    """A GeminiClient wired to a scripted fake SDK, with the real network and
    settings-driven fallback construction both bypassed."""
    g = gc.GeminiClient(api_key="fake", mock=False)
    g._model = _FakeGeminiSdkClient(answers)
    g._fallback = fallback
    return g


class _FakeFallback:
    """A minimal fallback double with the same last_provider contract as
    OpenAiClient, so the cascade's provenance logic can be tested without
    hitting OpenAI's SDK at all."""

    def __init__(self, classify_result=None, answer_result=None, provider="openai"):
        self._classify_result = classify_result or {"intent": "harga_lookup", "slots": {}}
        self._answer_result = answer_result or "jawaban dari fallback"
        self.last_provider = provider
        self.classify_calls = 0
        self.answer_calls = 0

    def classify_intent(self, message):
        self.classify_calls += 1
        return self._classify_result

    def answer_with_context(self, query, context):
        self.answer_calls += 1
        return self._answer_result


class TestGeminiSucceeds:
    """When Gemini answers cleanly, the fallback must never be touched."""

    def test_classify_uses_gemini_only(self):
        fb = _FakeFallback()
        g = make_client(['{"intent": "harga_lookup", "slots": {"commodity": "cabai_rawit"}}'], fallback=fb)
        result = g.classify_intent("harga cabai rawit")
        assert result == {"intent": "harga_lookup", "slots": {"commodity": "cabai_rawit"}}
        assert g.last_provider == "gemini"
        assert fb.classify_calls == 0

    def test_answer_uses_gemini_only(self):
        fb = _FakeFallback()
        g = make_client(["Skor 90 karena jarak dekat."], fallback=fb)
        result = g.answer_with_context("kenapa match ini", "skor 90")
        assert result == "Skor 90 karena jarak dekat."
        assert g.last_provider == "gemini"
        assert fb.answer_calls == 0


class TestFallsBackToOpenAiOnGeminiFailure:
    """A Gemini exception, or a response that fails to parse, must reach the
    fallback rather than jumping straight to the mock heuristic."""

    def test_classify_falls_back_on_exception(self):
        fb = _FakeFallback(classify_result={"intent": "cari_pembeli", "slots": {}})
        g = make_client([RuntimeError("network blip")], fallback=fb)
        result = g.classify_intent("golek pembeli lombok")
        assert result == {"intent": "cari_pembeli", "slots": {}}
        assert g.last_provider == "openai"
        assert fb.classify_calls == 1

    def test_classify_falls_back_when_gemini_json_has_no_intent_key(self):
        fb = _FakeFallback(classify_result={"intent": "forecast", "slots": {}})
        g = make_client(['{"slots": {}}'], fallback=fb)  # valid JSON, missing "intent"
        result = g.classify_intent("prakiraan harga")
        assert result == {"intent": "forecast", "slots": {}}
        assert g.last_provider == "openai"

    def test_classify_falls_back_on_unparsable_json(self):
        fb = _FakeFallback()
        g = make_client(["not json at all"], fallback=fb)
        g.classify_intent("test")
        assert g.last_provider == "openai"
        assert fb.classify_calls == 1

    def test_answer_falls_back_on_exception(self):
        fb = _FakeFallback(answer_result="jawaban gpt")
        g = make_client([RuntimeError("timeout")], fallback=fb)
        result = g.answer_with_context("q", "ctx")
        assert result == "jawaban gpt"
        assert g.last_provider == "openai"
        assert fb.answer_calls == 1

    def test_answer_falls_back_on_empty_gemini_response(self):
        fb = _FakeFallback(answer_result="jawaban gpt")
        g = make_client([""], fallback=fb)
        result = g.answer_with_context("q", "ctx")
        assert result == "jawaban gpt"
        assert g.last_provider == "openai"


class TestFallsThroughToMockWhenBothProvidersFail:
    def test_classify_no_fallback_configured_matches_pre_fallback_behaviour(self):
        g = make_client([RuntimeError("down")], fallback=None)
        result = g.classify_intent("test")
        assert result == {"intent": "fallback", "slots": {}}
        assert g.last_provider == "mock"

    def test_answer_no_fallback_configured_uses_mock_heuristic(self):
        g = make_client([RuntimeError("down")], fallback=None)
        result = g.answer_with_context("test", "ctx")
        assert isinstance(result, str) and len(result) > 0
        assert g.last_provider == "mock"

    def test_provider_reported_honestly_when_openai_itself_degrades(self):
        """The fallback returning successfully does not mean OpenAI answered.
        OpenAiClient itself degrades to mock internally on its own
        failures. The cascade must read last_provider off the fallback, not
        assume "it returned, so it must have been openai"."""
        silently_degraded_fallback = _FakeFallback(provider="mock")
        g = make_client([RuntimeError("gemini down")], fallback=silently_degraded_fallback)
        g.classify_intent("test")
        assert g.last_provider == "mock"
        assert silently_degraded_fallback.classify_calls == 1


class TestWiring:
    """The one line that decides whether a fallback gets constructed at all."""

    def test_fallback_constructed_when_openai_key_present(self, monkeypatch):
        monkeypatch.setattr(gc, "settings", _with_settings(gc, openai_api_key="sk-test"))
        g = gc.GeminiClient(api_key="fake", mock=False)
        assert isinstance(g._fallback, OpenAiClient)

    def test_no_fallback_when_openai_key_absent(self, monkeypatch):
        monkeypatch.setattr(gc, "settings", _with_settings(gc, openai_api_key=""))
        g = gc.GeminiClient(api_key="fake", mock=False)
        assert g._fallback is None

    def test_no_fallback_in_mock_mode_even_with_openai_key(self, monkeypatch):
        """mock=True must stay a total short-circuit: the whole point of
        mock mode is a fresh clone works with zero API keys and zero network
        calls, of any kind."""
        monkeypatch.setattr(gc, "settings", _with_settings(gc, openai_api_key="sk-test"))
        g = gc.GeminiClient(mock=True)
        assert g._fallback is None
        assert g.last_provider == "mock"


class TestOpenAiClientStandalone:
    """OpenAiClient mirrors GeminiClient's own mock-mode contract, since the
    language eval (tools/eval_llm_lang.py) and any future direct use both
    depend on it behaving like a drop-in peer, not a lesser cousin."""

    def test_mock_mode_classify(self):
        o = OpenAiClient(mock=True)
        result = o.classify_intent("harga cabai di malang")
        assert result["intent"] == "harga_lookup"
        assert o.last_provider == "mock"

    def test_mock_mode_answer_is_nonempty(self):
        o = OpenAiClient(mock=True)
        result = o.answer_with_context("test", "ctx")
        assert isinstance(result, str) and len(result) > 0
        assert o.last_provider == "mock"

    def test_defaults_to_mock_without_api_key(self, monkeypatch):
        # Isolate this from the file-wide MOCK_MODE=true forcing, so the
        # assertion is actually about the "no key" branch, not the
        # "mock_mode env var" branch.
        monkeypatch.setattr(oc, "settings", _with_settings(oc, mock_mode=False, openai_api_key=""))
        o = OpenAiClient()
        assert o.mock is True
