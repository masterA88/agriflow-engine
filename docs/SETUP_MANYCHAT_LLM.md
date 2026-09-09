# Setup: ManyChat + Gemini + OpenAI for the AgriFlow WhatsApp bot

Author: Hilmi (https://master-hilmi.vercel.app/)
Date: 2026-09-08, OpenAI fallback section added 2026-09-09, section 3c (the built orchestrator) added 2026-09-10. Facts below were checked against the vendor pages on those dates; prices and model names move fast on both sides (Gemini moved 2.5 to 3.8 in four months; OpenAI's lineup turned over just as much), so re-check before paying.

This is the operator runbook. The architecture and the reasons behind it live in the build-ready spec (`k1/research/agriflow-chatbot-architecture/drafts/spec-manychat-gemini-behaviour-2026-09-08.md`). That spec describes a single-provider (Gemini-only) orchestrator that answers from a short RAG context; the fallback in section 3b sits underneath it as an implementation detail the spec's route/compose steps call into, and section 3c below describes how those same route/compose steps were actually built: not a RAG context, but function-calling tools over the live engine data, so a question can be about anything the platform tracks, not only what a static context blob anticipated.

**Where this lives in ManyChat: nowhere.** ManyChat only ever calls one thing, `POST /manychat/webhook` on our backend. Which LLM answers a given message, and which of the 15 data tools it calls to do so, is decided entirely inside that backend (`whatsapp_bot/orchestrator.py`, calling into `whatsapp_bot/gemini_client.py`'s provider cascade), turn by turn. Nothing in the ManyChat flow builder changes because there are two providers, or fifteen tools, behind the webhook instead of a fixed script.

## 0. Where things stand today

| Item | State on 2026-09-08 |
|---|---|
| Google AI Studio | Signed in as the founder. One Gemini key already exists (`...cSlc`) on project `chatbot Project` (`gen-lang-client-0750284801`), created 2026-05-18, **Free tier**. |
| Gemini billing | Not set up. The "Set up billing" link is on the API keys page. |
| ManyChat | Account exists (`fb5562173`), plan **Trial**, no channel connected. The WhatsApp connect wizard is at "Which number do you want to use?". |
| WhatsApp number | None usable. The number in `whatsapp_bot/config.py` is Twilio's shared sandbox (`+14155238886`), which cannot move. |
| Backend endpoint | `POST /manychat/webhook` is built and tested (670 tests passing as of 2026-09-10): shared-secret auth, session memory, quota, the Gemini-then-OpenAI tool-calling cascade over 15 data tools, and the 7.5s deadline/pending push. See section 3c. Not yet on the HF Space, and `MANYCHAT_WEBHOOK_SECRET` has not been generated. |

## 1. Gemini: which model

Recommendation: pin **`gemini-3.8-flash`** for the bot, and keep **`gemini-3.5-flash-lite`** as the cheap fallback. Decide between them with the language eval in section 3, not by feel.

Why this pair, from the Gemini API pricing and models pages (2026-09-08):

| Model | Status | Paid price per 1M tokens (input / output) | Free tier |
|---|---|---|---|
| `gemini-3.8-flash` | New stable, current general-purpose Flash | $0.75 / $3.75 (rises to $1.50 / $7.50 after 2026-12-31) | yes |
| `gemini-3.7-flash` | Stable | $0.75 / $3.75 (same schedule) | yes |
| `gemini-3.5-flash-lite` | Stable, cheapest current line | $0.30 / $2.50 | yes |
| `gemini-2.5-flash` | Still listed, older generation | $0.30 / $2.50 | yes |
| `gemini-2.5-flash-lite` | Still listed, repo default today | $0.10 / $0.40 | yes |

Notes that matter for the decision:

- Any Gemini model answers Indonesian well. Javanese, especially krama, is the open question, and newer models are the safer bet. That is why the default is 3.8 Flash and the eval exists.
- Cost is not the deciding factor. A bot turn is roughly 3,000 input tokens (system prompt, tool schema, session summary, tool results) and 300 output tokens. On 3.8 Flash that is about $0.0034 per turn, on 3.5 Flash-Lite about $0.0017. At 1,000 conversations a month with five turns each, the difference is about $9 a month.
- The repo default `gemini-2.5-flash-lite` (`config.py:57`) carries a comment saying it retires on 16 October 2026. The deprecations page shows no shutdown date for it as of today, so the comment is unverified. Change the default anyway; the 2.5 line is two generations old.
- Function calling is what the orchestrator relies on; all Flash models support it. Do not use a preview model in production.
- Rate limits are per project, not per key, and the numbers are shown only inside AI Studio (Rate Limit page). The free tier is enough for the eval and local development. Tier 1 (billing on) is enough for the pilot.

Set in the environment:

```
GEMINI_MODEL=gemini-3.8-flash
```

## 2. Gemini: billing (founder does this, about 10 minutes)

Both the free and paid tiers are available in Indonesia (Gemini API available-regions page). A Google Cloud billing account and a payment card are required.

1. Open https://aistudio.google.com/api-keys (already signed in). On the row for `chatbot Project`, click **Set up billing**.
2. Choose or create a Google Cloud billing account. Fill in contact details and the card. Pick **Prepay** with the minimum $5 if you want a hard ceiling for the hackathon, or **Postpay** if you want the bot to keep working past $5.
3. After it completes, the row shows **Tier 1** instead of Free tier. Tier 1 has a $250 per month cap; Tier 2 comes automatically after $100 paid and 3 days.
4. Go to https://aistudio.google.com/spend and set a project spend cap (for example $30 a month for the pilot). Note that the cap is not a hard stop for long-running jobs.
5. Paid tier prompts and responses are not used to improve Google products; free tier ones can be. This is another reason to switch to paid before real farmers talk to the bot.
6. Optional but recommended: create a **second key** on the same project named `agriflow-prod` and use the old key only for local development. Keys can be restricted and rotated independently; billing and rate limits stay per project.

Where the key goes, and nowhere else:

- Local: `.env` at the repo root, line `GEMINI_API_KEY=...` (the file is gitignored; never paste the key into chat, commits or the dashboard).
- Production: Hugging Face Space `masterAAA123/agriflow-api`, Settings, Variables and secrets, add secret `GEMINI_API_KEY`, and set `GEMINI_MODEL=gemini-3.8-flash` and `MOCK_MODE=false`. Restart the Space.

## 3. Gemini: prove Indonesian and Javanese before pinning

Run the 30-utterance eval (15 Indonesian, 8 Javanese ngoko, 7 Javanese krama). It needs only the key; it does not touch the AgriFlow API.

```
python tools/eval_llm_lang.py --out .tmp/eval_lang.md
python tools/eval_llm_lang.py --models gemini-3.8-flash gemini-3.5-flash-lite gemini-2.5-flash
```

What to look at in the report:

- Did the reply stay in the user's language, and in the same register (ngoko back to ngoko, krama back to krama)? The script's automatic check is crude; a Javanese speaker on the team grades the 15 Javanese rows.
- Did the model refuse to invent a price? The system prompt tells it the data tool is unavailable; a model that answers "Rp 48.000" here will hallucinate on the real bot too.
- Latency per call, printed on each line. The ManyChat External Request timeout is 10 seconds and the spec's deadline is 7.5 seconds, so a model that regularly takes more than 3 seconds for a plain reply is a problem once tool calls are added.

Pin the cheapest model that passes the Javanese grading. If none passes krama, the spec's fallback applies: detect Javanese, reply in Indonesian with one Javanese courtesy line.

## 3b. OpenAI: the second tier, tried only when Gemini fails

**What this is, plainly.** The bot's brain (`whatsapp_bot/gemini_client.py`) now tries Gemini first, and only if Gemini raises an error, times out, or hands back something it cannot parse, tries OpenAI with the identical prompt and the identical question. If OpenAI also fails, the bot falls back to the built-in keyword heuristic, same as it always did when there was only one provider. This is a reliability upgrade, not a feature switch: a farmer never sees which provider answered, and the two providers are never both called for the same message unless the first one broke.

**Why add it at all.** Gemini is still the primary and still the cheaper choice; nothing about that changes. The founder asked for a second provider after the Twilio outage that forced the ManyChat switch, and the same instinct applies here: one upstream dependency is one thing that can go down at the worst moment (mid-demo, mid-pilot). A same-quality second vendor with no shared infrastructure with Google is the standard way to remove that single point of failure, at the cost of one more account to manage.

**Setup, about 10 minutes:**

1. Go to https://platform.openai.com, sign in or create an account, and open **Settings → Billing**. Add a payment method and set a monthly budget limit (start at $10 to $20; the fallback tier is rarely called, so this is a ceiling, not an expected spend). A small number of test requests work before billing is added, but production traffic needs it.
2. **Settings → API keys**, create a new secret key, name it `agriflow-fallback`. Copy it immediately; it is shown once.
3. Put it in `.env` locally and as an HF Space secret, same pattern as `GEMINI_API_KEY`:
   ```
   OPENAI_API_KEY=sk-...
   OPENAI_MODEL=gpt-5.6-luna
   ```
   Leaving `OPENAI_API_KEY` empty disables this tier entirely: the bot behaves exactly as it did before, Gemini then straight to the keyword mock. There is no code path that requires it.
4. Model choice, verified against OpenAI's pricing page on 2026-09-09: `gpt-5.6-luna` ($0.20 / $1.20 per 1M input/output tokens) is the cheap, fast tier and the closest analogue to Gemini's cheap Flash-Lite tier, actually a little cheaper on input. `gpt-5.6-terra` ($2.00 / $12.00) is the mid tier, worth trying only if Luna's Javanese replies fail grading. Both support function/tool calling and a 1M-token context window; multilingual capability is stated on the model page but, exactly like Gemini, that claim has not been tested here. Run the eval before trusting it.
5. Run the same 30-utterance eval against OpenAI, side by side with Gemini:
   ```
   python tools/eval_llm_lang.py --provider openai --models gpt-5.6-luna gpt-5.6-terra
   python tools/eval_llm_lang.py --provider both --out .tmp/eval_lang_both.md
   ```
   Grade the Javanese rows the same way as section 3. If OpenAI's Javanese is markedly weaker than Gemini's, that is fine: it is the fallback, used rarely, and a slightly worse reply during a Gemini outage beats no reply at all. It only matters if it fails badly enough to be unusable even as a stopgap.
6. Data policy: OpenAI's API does not use platform (non-ChatGPT) data to train its models by default, unmodified since well before this project started (verified on https://developers.openai.com/api/docs/guides/your-data on 2026-09-09). This matches Gemini's paid-tier policy, so neither provider is training on farmer conversations once both are on paid billing.
7. Nothing else changes. No new ManyChat configuration, no new webhook, no new custom fields. See the note at the top of this document.

**Watching which provider actually answered.** `GeminiClient.last_provider` is set to `"gemini"`, `"openai"`, or `"mock"` after every call and logged as a warning line (`llm.gemini_classify_failed`, `llm.openai_classify_failed`, etc.) whenever a tier fails over. There is no dashboard for this yet; for now, `grep llm\\. ` in the HF Space logs during the pilot to see how often the fallback actually fires. If it fires often, that is itself a signal Gemini's rate limit or model choice needs attention, not that OpenAI needs to become primary.

## 3c. What got built: the tool-calling orchestrator (2026-09-10)

The single-provider, fixed-context design the spec describes has been replaced end to end by function-calling tools over the live engine data, so the bot is no longer limited to the six hand-classified intents the Twilio path still uses (`whatsapp_bot/intent.py`). A ManyChat message can now ask about anything the platform tracks, in Indonesian or Javanese, and the model itself decides which tools to call to answer it.

**The 15 tools** (`whatsapp_bot/tools.py`; one JSON-Schema spec list shared by both providers, so Gemini and OpenAI see identical capabilities):

| Tool | Answers |
|---|---|
| `list_commodities` | Every commodity code and its Indonesian name |
| `list_kabupaten` | All 38 kabupaten/kota: id, name, coordinates, IPM, population |
| `get_price` | Producer or consumer price for one commodity in one kabupaten |
| `get_surplus_deficit` | Every kabupaten's surplus or deficit volume and price for one commodity |
| `find_buyers` | Which deficit areas a surplus kabupaten's output was actually matched to |
| `find_suppliers` | Ranked suppliers for a deficit kabupaten, and which were chosen |
| `explain_match` | Full score breakdown behind a match, including why a rival supplier lost |
| `get_forecast` | 30-day price forecast with a P10 to P90 band |
| `get_price_history` | Observed daily prices over the last N days |
| `get_anomalies` | Detected price spikes or drops (Hampel/MAD scan) |
| `get_summary` | Headline KPIs: surplus, deficit and matched tons, coverage, arbitrage value |
| `run_whatif` | Re-runs the engine under a disruption preset and diffs it against baseline |
| `list_presets` | The named what-if scenarios `run_whatif` accepts |
| `get_data_freshness` | The exact dates behind every number the bot can cite |
| `get_report_link` | A downloadable CSV link for the full match list |

Every tool calls the same payload-builder function the dashboard's own REST API already calls, so a WhatsApp answer and the dashboard can never disagree about a number. For example, `find_buyers` reuses `_matches_payload`, the exact function behind `GET /api/v1/matches`. `search_policy` from the original spec is left out on purpose: the `policy_docs` table it would read from is still empty.

**How a turn is answered** (`whatsapp_bot/orchestrator.py`): Gemini gets the message plus the 15 tool specs. It may call up to two tools, one round trip each, seeing the real result before deciding whether to call another or answer. A third round is never offered; the model is forced to answer in text after the second tool result. If Gemini itself errors, times out, or returns nothing usable, the identical prompt and identical tools go to OpenAI (section 3b's fallback, now extended to carry the tool-calling loop too). If both fail, a fixed apology is returned, never a guessed number.

**Memory.** Each subscriber's last 10 turns plus a rolling summary are kept in the `chat_session` table (Postgres, when `SUPABASE_DB_URL` is set) so a follow-up like "harganya di sana gimana" resolves against what was just discussed. Without a database configured, the same session shape lives in an in-process dictionary instead; memory then does not survive a restart.

**Language.** Every turn is classified Indonesian or Javanese (`whatsapp_bot/language.py`) before the model sees it, and a language-specific system prompt, not a translation step, tells the model which language and register to answer in. Language never changes which tools exist or what they return, only the words wrapped around the numbers.

**The 7.5-second deadline.** ManyChat's own External Request action times out at 10 seconds. If the tool-calling round trip has not finished by 7.5s, the webhook replies immediately with a short holding line in the user's language and `agriflow_status: "pending"`; the same answer keeps computing in the background and is pushed the moment it finishes through ManyChat's Public API (`POST /fb/sending/sendContent`), which requires the 24-hour customer-service window still be open. Either path ends in exactly one answer reaching the user; "pending" only changes how it arrives, never whether it arrives.

**Billing and quota are unchanged.** `MULAI`, `BANTUAN`, `STATUS`, `PRO`, `BERHENTI` are still free and unmetered, and a metered turn still only consumes quota when a tool call actually returned data, so an unanswerable question costs nothing, exactly as the Twilio path already worked.

**Test coverage as of 2026-09-10:** 670 tests passing. `tests/test_tool_calling.py` covers the round-trip loop against fake Gemini and OpenAI SDK responses, `tests/test_orchestrator.py` covers the full pipeline (commands before quota, quota before the model, the language switch, the deadline split, session persistence), and `tests/test_manychat_webhook.py` covers the real FastAPI route: the auth header is enforced, an unset secret fails closed, and a correctly authenticated request gets a real mock-mode answer back.

**What is left is not code.** Generate `MANYCHAT_WEBHOOK_SECRET` and set it plus the other `MANYCHAT_*` variables (section 6) as HF Space secrets, redeploy the Space, then do sections 4 and 5 below: the WhatsApp number and the ManyChat flow itself still do not exist.

## 4. ManyChat: plan, number, connection (founder does this)

Verified from ManyChat's help centre (articles 25800276116508 and 25800228332572, updated early September 2026):

- WhatsApp is **not** available on the Essential plan. **Pro** is required: $39 a month, or $29 a month billed annually, includes 2,500 active contacts, then $0.05 per extra contact per month ($0.038 on annual). Active contacts are billed per distinct person per month, not per message. Take monthly for the first month.
- The trial the account is on now may allow you to connect a channel and build flows; upgrade to Pro before the demo so nothing pauses mid-pitch.

Steps:

1. **Get a number.** You need an Indonesian mobile number that is either linked to the WhatsApp Business App or not on any WhatsApp account at all. A number on the personal WhatsApp app must be removed from WhatsApp first. ManyChat also offers to sell a new number in the wizard (the "New number" card). For the pitch, a real +62 number reads better than a foreign one.
2. **Meta Business Portfolio.** Use the AgriFlow business (not a personal profile). Have the business name, address and website (https://agriflow.farm) ready; Meta asks for them in the embedded signup.
3. In ManyChat: Home, **Connect Channels**, **WhatsApp**, **Connect**. The wizard is already open in the browser at "Which number do you want to use?". Choose the card, then **Connect Through Meta**. Log in to Facebook, pick or create the Business Portfolio, enter the number, receive the SMS or voice code. This step grants ManyChat access to your WhatsApp Business Account; only the account owner should click it.
4. After connection, the account starts with Meta's default messaging limit (unverified businesses can message a limited number of unique users per day). Complete **business verification** in Meta Business Manager when you can; it takes days, so start it now.
5. Settings, **API**, generate the token. Store it as `MANYCHAT_API_TOKEN` in `.env` locally and as an HF Space secret. Refreshing the token disables everything that used the old one.
6. Settings, **AI**: turn every ManyChat AI feature **off** (AI Step, Intentions, AI-generated replies). Gemini in our backend is the only model that talks to users, and ManyChat's AI terms allow them to use inputs and outputs to improve their features.

## 5. ManyChat: the flow (after the backend is deployed)

The endpoint itself is built (section 3c); do this once `MANYCHAT_WEBHOOK_SECRET` is set on the HF Space and the Space has been redeployed with this code, since until then the External Request has nothing to authenticate against. The exact request and response JSON, the custom-field mapping and the 7.5-second deadline rule are in the spec, sections 1.3 to 1.7, and now also built exactly that way in `whatsapp_bot/manychat.py` and `whatsapp_bot/orchestrator.py`. In short:

1. Settings, **Fields**, create custom fields (text unless noted): `agriflow_reply`, `agriflow_status`, `agriflow_lang`, `agriflow_intent`, `agriflow_token`. Note each field's numeric id (Public API `getCustomFields`); they go into the `MANYCHAT_FIELD_*` variables.
2. Automation, **Default Reply** (fires on any message that matches no keyword): one **External Request** action, `POST https://masteraaa123-agriflow-api.hf.space/manychat/webhook`, header `X-AgriFlow-Key: <MANYCHAT_WEBHOOK_SECRET>`, body with `subscriber_id`, `phone`, `first_name`, `last_input_text`, `last_interaction`. Map the response fields to the custom fields above.
3. Next node: **Send Message** with text `{{agriflow_reply}}`. Add a condition: if `agriflow_status` equals `pending`, send the short holding message instead; the backend pushes the full answer through the Public API.
4. Keyword triggers for `MULAI`, `BANTUAN`, `STATUS`, `PRO`, `BERHENTI` so the commands stay free of quota and never reach the model.
5. Test with the built-in preview, then with your own phone. Remember: response mapping does not run in ManyChat's Test mode, so the real check is a message from a real number.

## 6. Environment variables (full list is in the spec, section 6.4)

```
GEMINI_API_KEY=                 # secret
GEMINI_MODEL=gemini-3.8-flash
OPENAI_API_KEY=                 # secret; empty disables the fallback tier entirely
OPENAI_MODEL=gpt-5.6-luna
MANYCHAT_WEBHOOK_SECRET=        # 32 random bytes, base64url; production refuses to boot without it
MANYCHAT_API_TOKEN=             # secret, from ManyChat Settings > API
MANYCHAT_API_BASE=https://api.manychat.com
MANYCHAT_DEADLINE_SECONDS=7.5   # how long the webhook waits before replying "pending" instead of the full answer
MANYCHAT_FIELD_REPLY_ID=
MANYCHAT_FIELD_STATUS_ID=
MANYCHAT_FIELD_TOKEN_ID=
MANYCHAT_FIELD_LANG_ID=
MANYCHAT_FIELD_INTENT_ID=
MOCK_MODE=false
```

Generate the webhook secret with:

```
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

## 7. Order of operations

1. Founder: Gemini billing (section 2), then run the language eval (section 3) and pick the model.
2. Founder: OpenAI billing and key (section 3b), then run the same eval against it for comparison. This step is independent of everything else and can happen any time before launch. It does not block or get blocked by ManyChat setup.
3. Founder: WhatsApp number, Meta Business Portfolio, ManyChat Pro, connect the channel, API token, AI features off (section 4). Start Meta business verification the same day.
4. Done: `POST /manychat/webhook`, `chat_session` memory, `intent_event` logging, and the Gemini-then-OpenAI tool-calling orchestrator over the 15 data tools are built and tested (section 3c). What is left here is deployment, not code: generate `MANYCHAT_WEBHOOK_SECRET` (section 6), set it plus the other `MANYCHAT_*` variables as HF Space secrets, and redeploy.
5. Founder with the team: build the ManyChat flow (section 5), test from a real phone, then rehearse the Javanese demo script.

## 8. Costs to expect for the pilot month

| Line | Amount |
|---|---|
| ManyChat Pro, monthly | $39 |
| Gemini, 1,000 conversations of 5 turns on 3.8 Flash | about $17 |
| OpenAI fallback, gpt-5.6-luna | close to $0 if Gemini rarely fails; budget a $10 to $20 monthly cap as a ceiling, not an expected spend |
| Meta conversation charges | $0 until 2026-10-01; after that, service messages beyond 1,000 free per number per month are billed at the utility rate (roughly $175 a month at pilot scale per the spec's estimate) |
| WhatsApp number | depends on the carrier or ManyChat's number offer |
