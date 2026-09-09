"""
GeminiClient.answer_with_tools and OpenAiClient.answer_with_tools: the
function-calling loop that lets the bot answer arbitrary data questions
instead of the six hand-classified intents in intent.py.

No real network calls and no real tool execution against server.py: a fake
tool registry is monkeypatched in for every test, so this file is testing
the ROUND-TRIP LOOP (does it call the tool, does it feed the result back,
does it stop after two rounds), not whether get_price is implemented
correctly (tools.py's own manual smoke test in this session covered that
against real data; test_llm_fallback.py covers the Gemini/OpenAI cascade
these methods also use).

Fakes mirror the real SDK shapes exactly, inspected against the installed
google-genai 2.3.0 and openai 3.11.0 packages on 2026-09-09:
  Gemini:  resp.candidates[0].content.parts[i].function_call.{name, args}
  OpenAI:  resp.output (list of items with .type == "function_call", plus
           .name, .arguments (a JSON string), .call_id), resp.output_text
"""
from __future__ import annotations

import json
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
from whatsapp_bot import tools as tools_mod
from whatsapp_bot.openai_client import OpenAiClient


@pytest.fixture(autouse=True)
def fake_tool_registry(monkeypatch):
    """Every test in this file gets a small, fixed tool: get_price(commodity,
    kabupaten) -> a canned dict, or {"error": ...} for one magic input, so
    the loop's error-relay path is exercised too. Patched onto the real
    tools module so both clients' `from .tools import ... execute_tool`
    pick it up (they import the module-level name at call time, not the
    object identity, so this patch is visible without touching either
    client file)."""
    calls = []

    def fake_execute_tool(name, args):
        calls.append((name, dict(args)))
        if args.get("kabupaten") == "NOWHERE":
            return {"error": "tidak ditemukan"}
        return {"commodity": args.get("commodity"), "kabupaten": args.get("kabupaten"), "price_per_kg": 32500}

    monkeypatch.setattr(tools_mod, "execute_tool", fake_execute_tool)
    monkeypatch.setattr(tools_mod, "TOOL_SPECS", [{
        "name": "get_price",
        "description": "test tool",
        "parameters": {"type": "object", "properties": {
            "commodity": {"type": "string"}, "kabupaten": {"type": "string"},
        }, "required": ["commodity", "kabupaten"], "additionalProperties": False},
    }])
    return calls


# =============================================================================
# Gemini fakes, matching google.genai's real response shape
# =============================================================================

class _FnCall:
    def __init__(self, name, args):
        self.name = name
        self.args = args


class _Part:
    def __init__(self, function_call=None):
        self.function_call = function_call


class _Content:
    def __init__(self, parts):
        self.parts = parts


class _Candidate:
    def __init__(self, parts):
        self.content = _Content(parts)


class _GeminiResp:
    def __init__(self, *, text=None, function_call=None):
        self._text = text
        parts = [_Part(function_call=function_call)] if function_call else [_Part()]
        self.candidates = [_Candidate(parts)]
        self.text = text


class _FakeGeminiModels:
    """`responses` is a list consumed in order, one per generate_content call."""

    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = 0

    def generate_content(self, model, contents, config=None):
        self.calls += 1
        return self._responses.pop(0)


class _FakeGeminiSdk:
    def __init__(self, responses):
        self.models = _FakeGeminiModels(responses)


def make_gemini(responses) -> gc.GeminiClient:
    g = gc.GeminiClient(api_key="fake", mock=False)
    g._model = _FakeGeminiSdk(responses)
    g._fallback = None
    return g


class TestGeminiToolLoop:
    def test_answers_directly_with_no_tool_call(self, fake_tool_registry):
        g = make_gemini([_GeminiResp(text="Halo, ada yang bisa saya bantu?")])
        answer = g.answer_with_tools("system", "halo")
        assert answer.text == "Halo, ada yang bisa saya bantu?"
        assert answer.tool_calls == []
        assert fake_tool_registry == []

    def test_one_tool_call_then_final_answer(self, fake_tool_registry):
        g = make_gemini([
            _GeminiResp(function_call=_FnCall("get_price", {"commodity": "cabai_rawit", "kabupaten": "Malang"})),
            _GeminiResp(text="Harga cabai rawit di Malang Rp 32.500/kg."),
        ])
        answer = g.answer_with_tools("system", "harga cabai di malang")
        assert answer.text == "Harga cabai rawit di Malang Rp 32.500/kg."
        assert answer.tool_calls == [{"name": "get_price", "args": {"commodity": "cabai_rawit", "kabupaten": "Malang"}, "ok": True}]
        assert fake_tool_registry == [("get_price", {"commodity": "cabai_rawit", "kabupaten": "Malang"})]
        assert g._model.models.calls == 2

    def test_tool_error_is_relayed_not_raised(self, fake_tool_registry):
        g = make_gemini([
            _GeminiResp(function_call=_FnCall("get_price", {"commodity": "cabai_rawit", "kabupaten": "NOWHERE"})),
            _GeminiResp(text="Maaf, kabupaten itu tidak ditemukan."),
        ])
        answer = g.answer_with_tools("system", "harga cabai di NOWHERE")
        assert answer.text == "Maaf, kabupaten itu tidak ditemukan."
        assert answer.tool_calls[0]["ok"] is False

    def test_two_tool_calls_are_allowed(self, fake_tool_registry):
        g = make_gemini([
            _GeminiResp(function_call=_FnCall("get_price", {"commodity": "cabai_rawit", "kabupaten": "Malang"})),
            _GeminiResp(function_call=_FnCall("get_price", {"commodity": "bawang_merah", "kabupaten": "Malang"})),
        ])
        # Third call (post-loop, tools disabled) supplies the final text.
        g._model.models._responses.append(_GeminiResp(text="Cabai 32.500, bawang juga 32.500."))
        answer = g.answer_with_tools("system", "harga cabai dan bawang di malang")
        assert answer.text == "Cabai 32.500, bawang juga 32.500."
        assert len(answer.tool_calls) == 2
        assert g._model.models.calls == 3

    def test_forced_final_call_with_empty_text_degrades_to_mock(self, fake_tool_registry):
        """After 2 tool calls, the 3rd call has tools disabled and must
        produce text. If even that comes back empty (should not happen with
        a real model, but a test should not trust that), the method degrades
        to the fixed apology rather than raising out to the caller, since
        there is no fallback configured here."""
        g = make_gemini([
            _GeminiResp(function_call=_FnCall("get_price", {"commodity": "a", "kabupaten": "b"})),
            _GeminiResp(function_call=_FnCall("get_price", {"commodity": "c", "kabupaten": "d"})),
            _GeminiResp(text=""),
        ])
        answer = g.answer_with_tools("system", "banyak pertanyaan sekaligus")
        assert "tidak bisa mengambil data" in answer.text
        assert g.last_provider == "mock"
        assert len(fake_tool_registry) == 2  # both tool calls still ran before the final call failed

    def test_falls_back_to_openai_on_gemini_exception(self, fake_tool_registry):
        from whatsapp_bot.tools import ToolAnswer
        from tests.test_llm_fallback import _FakeFallback  # reuse the double

        fb = _FakeFallback(provider="openai")
        fb.answer_with_tools = lambda system, message: ToolAnswer(text="dari openai", tool_calls=[])
        g = make_gemini([RuntimeError("boom")])
        g._fallback = fb
        answer = g.answer_with_tools("system", "test")
        assert answer.text == "dari openai"
        assert g.last_provider == "openai"

    def test_mock_mode_never_touches_the_model(self, fake_tool_registry):
        g = gc.GeminiClient(mock=True)
        answer = g.answer_with_tools("system", "test")
        assert "tidak bisa mengambil data" in answer.text
        assert answer.tool_calls == []
        assert fake_tool_registry == []


# =============================================================================
# OpenAI fakes, matching the Responses API's real output shape
# =============================================================================

class _OaFnCallItem:
    type = "function_call"

    def __init__(self, name, arguments: str, call_id="call_1"):
        self.name = name
        self.arguments = arguments
        self.call_id = call_id

    def model_dump(self):
        return {"type": self.type, "name": self.name, "arguments": self.arguments, "call_id": self.call_id}


class _OaResp:
    def __init__(self, *, output_text=None, output=None):
        self.output_text = output_text
        self.output = output or []


class _FakeOpenAiResponses:
    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = []

    def create(self, model, instructions, input, tools=None):
        self.calls.append({"input": input, "tools": tools})
        return self._responses.pop(0)


class _FakeOpenAiSdk:
    def __init__(self, responses):
        self.responses = _FakeOpenAiResponses(responses)


def make_openai(responses) -> OpenAiClient:
    o = OpenAiClient(api_key="fake", mock=False)
    o._client = _FakeOpenAiSdk(responses)
    return o


class TestOpenAiToolLoop:
    def test_answers_directly_with_no_tool_call(self, fake_tool_registry):
        o = make_openai([_OaResp(output_text="Halo!")])
        answer = o.answer_with_tools("system", "halo")
        assert answer.text == "Halo!"
        assert answer.tool_calls == []

    def test_one_tool_call_then_final_answer(self, fake_tool_registry):
        o = make_openai([
            _OaResp(output=[_OaFnCallItem("get_price", json.dumps({"commodity": "cabai_rawit", "kabupaten": "Malang"}))]),
            _OaResp(output_text="Rp 32.500/kg."),
        ])
        answer = o.answer_with_tools("system", "harga cabai di malang")
        assert answer.text == "Rp 32.500/kg."
        assert answer.tool_calls == [{"name": "get_price", "args": {"commodity": "cabai_rawit", "kabupaten": "Malang"}, "ok": True}]
        assert fake_tool_registry == [("get_price", {"commodity": "cabai_rawit", "kabupaten": "Malang"})]
        # second create() call must carry the function_call_output keyed by call_id
        second_call_input = o._client.responses.calls[1]["input"]
        assert any(item.get("type") == "function_call_output" and item.get("call_id") == "call_1" for item in second_call_input)

    def test_malformed_arguments_degrade_to_empty_dict_not_a_crash(self, fake_tool_registry):
        o = make_openai([
            _OaResp(output=[_OaFnCallItem("get_price", "not valid json")]),
            _OaResp(output_text="baiklah"),
        ])
        answer = o.answer_with_tools("system", "test")
        assert answer.text == "baiklah"
        assert fake_tool_registry[0] == ("get_price", {})

    def test_empty_response_raises_and_is_caught_as_mock_degrade(self, fake_tool_registry):
        o = make_openai([_OaResp(output_text="")])
        answer = o.answer_with_tools("system", "test")
        assert "tidak bisa mengambil data" in answer.text
        assert o.last_provider == "mock"

    def test_mock_mode_never_touches_the_model(self, fake_tool_registry):
        o = OpenAiClient(mock=True)
        answer = o.answer_with_tools("system", "test")
        assert "tidak bisa mengambil data" in answer.text
        assert fake_tool_registry == []
