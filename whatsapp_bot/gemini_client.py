"""
Gemini LLM wrapper, with an OpenAI fallback tier.

Two methods:
    classify_intent(message)       — structured intent + slots JSON
    answer_with_context(query, ctx) — RAG-style free-form answer

Mock mode (default): returns deterministic canned responses derived from
keyword matching on the message. Lets the rest of the pipeline run end-to-end
without any API key, so demos work from a fresh clone.

Three-tier cascade, real mode: Gemini, then OpenAI, then the local mock
heuristic. server.py, intent.py, and handlers.py only ever talk to
GeminiClient, and none of them know a second provider exists. OpenAiClient
(openai_client.py) is constructed here, lazily, only when OPENAI_API_KEY is
set; with no key the behaviour is exactly what it was before this fallback
existed (Gemini, then straight to the mock heuristic). The import of
OpenAiClient is deferred to inside __init__ rather than done at module load,
because openai_client.py imports the prompts and mock helpers below from
this module, and a module-level import here would be circular. See
whatsapp_bot/openai_client.py and tools/eval_llm_lang.py.

`last_provider` records which tier actually answered the most recent call
("gemini" | "openai" | "mock"), for logs and for the language eval script.
It is not persisted anywhere by itself.
"""

from __future__ import annotations
import json
import logging
import re
from typing import Any, Dict, Optional

from .config import settings

log = logging.getLogger("agriflow.llm")


# =============================================================================
# SYSTEM PROMPTS
# =============================================================================

INTENT_SYSTEM_PROMPT = """\
Anda adalah klasifikator intent untuk WhatsApp bot AgriFlow — platform
matching surplus-defisit pangan antar kabupaten Jawa Timur.

Pengguna mungkin menulis dalam Bahasa Indonesia ATAU Bahasa Jawa
(ngoko/krama). Normalisasikan ke kode kanonik Indonesia:
- "lombok" / "lombok abang" → cabai_merah
- "brambang" → bawang_merah
- "sega" / "wos" → beras
- "endhog" / "endog" → telur_ayam
- "pitik" → daging_ayam
- "jagong" → jagung
- "lengo" → minyak_goreng
- "gendis" → gula_pasir
- "glepung" → tepung_terigu
Kata kerja Jawa: "pira/regane/piro" ≈ "berapa/harga",
"adol/dodol" ≈ "jual", "tuku/tumbas" ≈ "beli", "duwe" ≈ "punya",
"golek" ≈ "cari".

Klasifikasikan pesan pengguna ke salah satu intent:

1. harga_lookup — Tanya harga komoditas di kabupaten tertentu
   slots: {"commodity": str, "kabupaten": str}
   contoh: "Harga cabai di Malang?", "Berapa beras Kediri sekarang?",
           "Pira regane lombok ing Malang?"

2. cari_pembeli — User punya supply, ingin menjual
   slots: {"commodity": str, "kabupaten_origin": str, "volume_tons": float|null}
   contoh: "Saya punya 50 ton cabai di Kediri, cari pembeli"
           "Cari pasar untuk bawang Probolinggo"
           "Aku duwe 50 ton lombok ing Kediri, golek pembeli"

3. cari_penjual — User butuh supply, ingin membeli
   slots: {"commodity": str, "kabupaten_dest": str, "volume_tons": float|null}
   contoh: "Butuh 100 ton beras untuk Surabaya"
           "Cari supplier cabai untuk Sidoarjo"
           "Butuh 100 ton sega kanggo Surabaya"

4. forecast — Prediksi/ramalan harga komoditas ke depan di suatu kota
   slots: {"commodity": str, "kabupaten": str|null}
   contoh: "Prediksi harga cabai Surabaya bulan depan"
           "Ramalan bawang merah Malang", "Prakiraan harga beras Jember"
           "Kira-kira harga telur Kediri minggu depan?"
           "Forecast cabai rawit Madiun", "Berapa harga beras ke depan?"

5. anomali — Anomali/lonjakan/penurunan harga tidak wajar suatu komoditas
   slots: {"commodity": str, "kabupaten": str|null}
   contoh: "Anomali harga cabai", "Lonjakan bawang Surabaya"
           "Ada spike harga beras?", "Harga telur Malang aneh"
           "Kenapa harga bawang tiba-tiba naik?", "Penurunan harga tidak wajar"

6. fallback — Pertanyaan umum, sapaan, atau tidak masuk kategori di atas
   slots: {}

Output HANYA JSON valid satu baris, tanpa markdown atau penjelasan.
Untuk 'commodity' selalu kembalikan kode kanonik Indonesia (cabai_merah,
bawang_merah, beras, dst.) meskipun pengguna menulis dalam Jawa.
{"intent": "...", "slots": {...}}
"""

ANSWER_SYSTEM_PROMPT = """\
Anda adalah asisten WhatsApp AgriFlow — platform Indonesia untuk
matching surplus-defisit pangan kabupaten Jawa Timur.

Jawab dalam Bahasa Indonesia yang ramah, ringkas (max 3 kalimat),
dan sertakan saran konkret bila memungkinkan. Jangan halusinasi data
harga/volume — kalau tidak yakin, sarankan pengguna gunakan format
spesifik: "Harga [komoditas] di [kabupaten]" atau
"Cari pembeli [komoditas] [kabupaten]".

Konteks AgriFlow:
{context}
"""


# =============================================================================
# CASCADE FACTORY
# =============================================================================

def build_llm_client():
    """The provider cascade, outermost tier first, per settings.llm_primary.

    Both clients satisfy the same four-part contract (classify_intent,
    answer_with_context, answer_with_tools, last_provider), so callers hold
    whichever comes back without caring which vendor is in front. That is the
    whole reason the order can be a setting instead of a refactor.

    The primary falls back to the other provider, and the other provider
    falls back to the keyword mock, so the chain is always at most:
    primary, secondary, mock.

    A primary with no API key would be born mocked and would short-circuit
    before ever reaching its fallback, stranding a perfectly good key on the
    other tier. So when the configured primary has no key and the other one
    does, the order is inverted here rather than silently degrading to mock.
    """
    from .openai_client import OpenAiClient

    primary = settings.llm_primary
    if primary == "openai" and not settings.openai_api_key and settings.gemini_api_key:
        primary = "gemini"
    elif primary != "openai" and not settings.gemini_api_key and settings.openai_api_key:
        primary = "openai"
    return OpenAiClient() if primary == "openai" else GeminiClient()


# =============================================================================
# CLIENT
# =============================================================================

class GeminiClient:
    """Wrapper for google-generativeai, with an optional OpenAI fallback tier."""

    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None,
                 mock: Optional[bool] = None, enable_fallback: bool = True):
        self.api_key = api_key if api_key is not None else settings.gemini_api_key
        self.model_name = model or settings.gemini_model
        self.mock = mock if mock is not None else (
            settings.mock_mode or not self.api_key
        )
        self._model = None
        self.last_provider = "mock" if self.mock else "gemini"
        if not self.mock:
            self._init_real_client()
        # The fallback is a second, independently-mocked client: constructing
        # it never raises (OpenAiClient itself falls back to mock with no
        # key), so this is safe even when self.mock is True (fallback simply
        # goes unused, since the methods below short-circuit before reaching
        # it). Deferred import; see the module docstring for why.
        #
        # enable_fallback=False is how the two clients avoid recursing into
        # each other now that either one can be primary: whichever is built
        # as the other's fallback is built without one of its own, so a
        # cascade is always exactly two tiers deep plus mock.
        self._fallback = None
        if enable_fallback and not self.mock and settings.openai_api_key:
            from .openai_client import OpenAiClient
            self._fallback = OpenAiClient(enable_fallback=False)

    def _init_real_client(self) -> None:
        try:
            from google import genai
        except ImportError as e:
            raise RuntimeError(
                "google-genai not installed. "
                "Run: pip install google-genai"
            ) from e
        # Modern SDK: single Client, model picked per-call
        self._model = genai.Client(api_key=self.api_key)

    # -------------------------------------------------------------------------
    # Intent classification
    # -------------------------------------------------------------------------

    def classify_intent(self, message: str) -> Dict[str, Any]:
        """Return {"intent": str, "slots": dict}. Falls back to {"intent": "fallback"}."""
        if self.mock:
            self.last_provider = "mock"
            return _mock_classify(message)

        prompt = f"{INTENT_SYSTEM_PROMPT}\n\nPesan pengguna: {message!r}\n\nOutput JSON:"
        try:
            resp = self._model.models.generate_content(
                model=self.model_name, contents=prompt,
            )
            text = (resp.text or "").strip()
            # Strip ```json fences if present
            text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.MULTILINE).strip()
            parsed = json.loads(text)
            if "intent" not in parsed:
                raise ValueError("Gemini response carried no 'intent' key")
            parsed.setdefault("slots", {})
            self.last_provider = "gemini"
            return parsed
        except Exception as exc:
            log.warning("llm.gemini_classify_failed err=%s", type(exc).__name__)
            if self._fallback is not None:
                # OpenAiClient never raises here: it degrades to its own mock
                # internally. Trust its last_provider rather than the fact
                # that the call returned, or a silent OpenAI failure would be
                # mislabelled "openai".
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
        prompt = f"{system}\n\nPertanyaan pengguna: {query}\n\nJawaban:"
        try:
            resp = self._model.models.generate_content(
                model=self.model_name, contents=prompt,
            )
            text = (resp.text or "").strip()
            if not text:
                raise ValueError("Gemini returned an empty answer")
            self.last_provider = "gemini"
            return text
        except Exception as exc:
            log.warning("llm.gemini_answer_failed err=%s", type(exc).__name__)
            if self._fallback is not None:
                text = self._fallback.answer_with_context(query, context)
                self.last_provider = self._fallback.last_provider
                return text
            self.last_provider = "mock"
            return _mock_answer(query, context)

    # -------------------------------------------------------------------------
    # Function-calling answer over the data tools (whatsapp_bot/tools.py)
    # -------------------------------------------------------------------------

    _gemini_tool: Any = None  # built once per process; TOOL_SPECS is static

    def answer_with_tools(self, system: str, message: str) -> "ToolAnswer":
        """
        Answer one turn with access to every read-only data tool in
        tools.py. Up to two model round trips: the model may call a tool
        once, see the result, and either answer or make one more call before
        being forced to answer. This is the brain behind the ManyChat
        orchestrator's route+compose steps; classify_intent/answer_with_context
        above remain the simpler pipeline the Twilio and /chat paths use.

        Cascades to OpenAI exactly like the two methods above: any Gemini
        exception here falls through to self._fallback.answer_with_tools,
        then to a fixed apology if that also fails or no fallback exists.
        Mock mode never reaches the model at all: it returns a fixed
        "kirim pertanyaan spesifik" nudge, since the keyword mock heuristic
        has no tools to call and would only hallucinate specifics.
        """
        from .tools import ToolAnswer

        if self.mock:
            self.last_provider = "mock"
            return ToolAnswer(text=_MOCK_TOOL_ANSWER)

        try:
            answer = self._gemini_answer_with_tools(system, message)
            self.last_provider = "gemini"
            return answer
        except Exception as exc:
            log.warning("llm.gemini_tools_failed err=%s", type(exc).__name__)
            if self._fallback is not None:
                answer = self._fallback.answer_with_tools(system, message)
                self.last_provider = self._fallback.last_provider
                return answer
            self.last_provider = "mock"
            return ToolAnswer(text=_MOCK_TOOL_ANSWER)

    @staticmethod
    def _for_gemini_schema(schema: Any) -> Any:
        """Drop keys Gemini's function-declaration schema does not define.

        Gemini takes an OpenAPI 3.0 subset with no additionalProperties, and
        rejects the ENTIRE request with 400 INVALID_ARGUMENT when it sees one,
        naming every declaration at once. OpenAI accepts the same schema with
        or without it while strict is off, so the key stays in TOOL_SPECS (one
        spec list, both providers) and is dropped only on this path.
        """
        if isinstance(schema, dict):
            return {k: GeminiClient._for_gemini_schema(v)
                    for k, v in schema.items() if k != "additionalProperties"}
        if isinstance(schema, list):
            return [GeminiClient._for_gemini_schema(v) for v in schema]
        return schema

    def _gemini_answer_with_tools(self, system: str, message: str) -> "ToolAnswer":
        from google.genai import types
        from .tools import TOOL_SPECS, ToolAnswer, execute_tool
        _for_gemini = GeminiClient._for_gemini_schema

        if GeminiClient._gemini_tool is None:
            GeminiClient._gemini_tool = types.Tool(function_declarations=[
                types.FunctionDeclaration(name=t["name"], description=t["description"],
                                           parameters=_for_gemini(t["parameters"]))
                for t in TOOL_SPECS
            ])
        config = types.GenerateContentConfig(system_instruction=system, tools=[GeminiClient._gemini_tool])

        contents: list = [types.Content(role="user", parts=[types.Part(text=message)])]
        calls_made: List[Dict[str, Any]] = []
        # Up to 2 tool calls per turn (spec 2.2 step 7), each its own model
        # round trip: call, see whether it wants a tool, execute it, loop.
        # A response with no tool call returns immediately, at 1 round trip
        # for the common case of a question the model can answer outright
        # (get_data_freshness, "what can you do", etc.).
        for _ in range(2):
            resp = self._model.models.generate_content(model=self.model_name, contents=contents, config=config)
            candidate = resp.candidates[0] if resp.candidates else None
            parts = candidate.content.parts if candidate and candidate.content else []
            fn_parts = [p for p in parts if getattr(p, "function_call", None)]
            if not fn_parts:
                text = (resp.text or "").strip()
                if not text:
                    raise ValueError("Gemini returned neither a tool call nor text")
                return ToolAnswer(text=text, tool_calls=calls_made)
            fc = fn_parts[0].function_call
            args = dict(fc.args or {})
            result = execute_tool(fc.name, args)
            calls_made.append({"name": fc.name, "args": args, "ok": "error" not in result})
            contents.append(candidate.content)
            contents.append(types.Content(
                role="user",
                parts=[types.Part.from_function_response(name=fc.name, response={"result": result})],
            ))
        # Both allowed tool calls are spent. One more call, tools disabled,
        # forces a text answer instead of a third round; a real model never
        # returns a function call here since none was offered, so reading
        # .text directly is safe, and an empty one still raises cleanly.
        no_tools_config = types.GenerateContentConfig(system_instruction=system)
        resp = self._model.models.generate_content(model=self.model_name, contents=contents, config=no_tools_config)
        text = (resp.text or "").strip()
        if not text:
            raise ValueError("Gemini produced no final text after the tool round trip")
        return ToolAnswer(text=text, tool_calls=calls_made)


# A fixed, honest degrade for the tool-calling path when every provider
# fails. Distinct from _mock_answer (which pattern-matches keywords and can
# sound like a real answer), because a wrong-sounding guess on a data
# question is worse here than an admission the bot could not look it up.
_MOCK_TOOL_ANSWER = (
    "Maaf, saya sedang tidak bisa mengambil data untuk menjawab ini. "
    "Coba lagi sebentar lagi, atau buka dashboard di agriflow.farm."
)


# =============================================================================
# MOCK FALLBACKS — lightweight keyword heuristics
# =============================================================================

_COMMODITY_KEYWORDS = {
    # Each list mixes Bahasa Indonesia + Bahasa Jawa ngoko (basic colloquial)
    # so a single keyword pass handles both languages.
    "cabai_merah": ["cabai merah", "cabe merah", "cabai", "cabe", "lombok abang", "lombok"],
    "cabai_rawit": ["cabai rawit", "cabe rawit", "rawit", "lombok cilik"],
    "bawang_merah": ["bawang merah", "bawang", "brambang"],
    "bawang_putih": ["bawang putih", "bawang putih", "bawang bodas"],
    "beras_premium": ["beras premium", "beras", "sega", "wos"],
    "beras_medium": ["beras medium"],
    "jagung": ["jagung", "jagong"],
    "kedelai": ["kedelai", "kedele", "dele"],
    "tomat": ["tomat", "rangkem"],
    "kentang": ["kentang"],
    "telur_ayam": ["telur", "endhog", "endog"],
    "daging_ayam": ["daging ayam", "ayam", "pitik"],
    "daging_sapi": ["daging sapi", "sapi"],
    "ikan_tongkol": ["tongkol", "iwak tongkol"],
    "minyak_goreng": ["minyak goreng", "minyak", "lengo"],
    "gula_pasir": ["gula", "gendis"],
    "tepung_terigu": ["tepung", "terigu", "glepung"],
}

_KABUPATEN_KEYWORDS = [
    "surabaya", "malang", "kediri", "blitar", "madiun", "mojokerto", "pasuruan",
    "probolinggo", "jember", "banyuwangi", "sidoarjo", "gresik", "lamongan",
    "tuban", "bojonegoro", "ngawi", "magetan", "ponorogo", "trenggalek",
    "tulungagung", "nganjuk", "jombang", "bangkalan", "sampang", "pamekasan",
    "sumenep", "lumajang", "bondowoso", "situbondo", "batu",
]

_VOLUME_RE = re.compile(r"(\d+(?:[.,]\d+)?)\s*(ton|kg|kuintal)", re.IGNORECASE)


def _detect_commodity(message: str) -> Optional[str]:
    msg = message.lower()
    # Rank every (keyword, code) pair globally by keyword length so the most
    # specific phrase present in the message wins. v1.0 ranked per commodity
    # by its longest keyword, which let "cabai" (via cabai_merah's 12-char
    # "lombok abang") beat "cabai rawit" and answer a rawit question with
    # cabai merah data.
    pairs = sorted(
        ((kw, code) for code, kws in _COMMODITY_KEYWORDS.items() for kw in kws),
        key=lambda p: -len(p[0]),
    )
    for kw, code in pairs:
        if kw in msg:
            return code
    return None


def _detect_kabupaten(message: str) -> Optional[str]:
    msg = message.lower()
    for kab in _KABUPATEN_KEYWORDS:
        if kab in msg:
            return kab.title()
    return None


def _detect_volume_tons(message: str) -> Optional[float]:
    m = _VOLUME_RE.search(message)
    if not m:
        return None
    num = float(m.group(1).replace(",", "."))
    unit = m.group(2).lower()
    if unit == "kg":
        return num / 1000.0
    if unit == "kuintal":
        return num / 10.0
    return num  # ton


def _mock_classify(message: str) -> Dict[str, Any]:
    """Keyword heuristic that mimics what a real LLM would extract."""
    msg = message.lower()
    commodity = _detect_commodity(message)
    kabupaten = _detect_kabupaten(message)
    volume = _detect_volume_tons(message)

    # Order matters: more specific patterns first.
    # Each list mixes Bahasa Indonesia + Bahasa Jawa ngoko so the same
    # heuristic handles both. Examples:
    #   "pira" / "regane" / "piro" / "rega" / "pinten" — Jawa for "berapa/harga"
    #   "adol" / "dodol" / "duwe" — Jawa for "jual/punya"
    #   "tuku" / "tumbas" — Jawa for "beli"

    # anomali intent — checked first so "lonjakan harga" → anomali not harga_lookup
    if any(kw in msg for kw in [
        "anomali", "anomaly", "spike", "lonjakan", "aneh",
        "tidak wajar", "naik tiba-tiba", "turun tiba-tiba",
        "penurunan tidak wajar", "kenaikan tidak wajar",
        "deteksi harga",
    ]):
        return {
            "intent": "anomali",
            "slots": {"commodity": commodity, "kabupaten": kabupaten},
        }

    # forecast intent — check before harga_lookup (shares "harga" keyword)
    # Note: "akan" removed — it is a suffix in many Indonesian words (lonjakan, etc.)
    if any(kw in msg for kw in [
        "prediksi", "forecast", "ramalan", "prakiraan",
        "kira-kira", "perkiraan", "ke depan", "bulan depan",
        "minggu depan",
    ]):
        return {
            "intent": "forecast",
            "slots": {"commodity": commodity, "kabupaten": kabupaten},
        }

    if any(kw in msg for kw in [
        "harga", "berapa", "price",
        "pira", "piro", "regane", "rega", "pinten",  # jawa
    ]):
        return {
            "intent": "harga_lookup",
            "slots": {"commodity": commodity, "kabupaten": kabupaten},
        }
    if any(kw in msg for kw in [
        "cari pembeli", "jual", "punya", "surplus", "pasar untuk",
        "golek tuku", "golek pembeli", "adol", "dodol", "duwe",  # jawa
    ]):
        return {
            "intent": "cari_pembeli",
            "slots": {
                "commodity": commodity,
                "kabupaten_origin": kabupaten,
                "volume_tons": volume,
            },
        }
    if any(kw in msg for kw in [
        "butuh", "beli", "supplier", "cari penjual", "cari supplier",
        "tuku", "tumbas", "golek penjual", "butuhe", "perlu",  # jawa
    ]):
        return {
            "intent": "cari_penjual",
            "slots": {
                "commodity": commodity,
                "kabupaten_dest": kabupaten,
                "volume_tons": volume,
            },
        }
    return {"intent": "fallback", "slots": {}}


def _mock_answer(query: str, context: str) -> str:
    """Generic helpful response when there is no LLM available."""
    return (
        "Halo! Saya asisten AgriFlow. Coba kirim pesan dengan format:\n"
        "• \"Harga cabai di Malang\"\n"
        "• \"Cari pembeli 50 ton cabai Kediri\"\n"
        "• \"Butuh 100 ton beras untuk Surabaya\"\n\n"
        "Saya akan bantu cari match terbaik dari engine AgriFlow."
    )
