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
| Backend endpoint | `POST /manychat/webhook` is built, tested, and **verified against live Gemini on 2026-09-11**: real tool calls returning real BPS numbers in Indonesian and Javanese krama. See sections 3c and 3d. Not yet on the HF Space, and `MANYCHAT_WEBHOOK_SECRET` has not been generated. |

## 1. Gemini: which model

Recommendation as of 2026-09-11: pin **`gemini-3.5-flash-lite`**. It is the fastest and cheapest of everything tested, answering tool-backed questions in 2.0 to 3.2 seconds.

This section was rewritten twice in one day and the reason matters more than the answer. The 2026-09-08 recommendation of `gemini-3.8-flash` came from the pricing page rather than from a test. The first measurement run then appeared to show most models failing, which turned out to be **an artefact of which API key was in use**, not a property of the models. Two keys on this account behave completely differently:

| Model | Key ending `uXA` | Key ending `MzeJlw` | Paid price per 1M (in / out) |
|---|---|---|---|
| `gemini-3.5-flash-lite` | 504 | **OK, 1.0s plain, 2.0 to 3.2s with tools** | $0.30 / $2.50 |
| `gemini-3.8-flash` | 504 | OK but slow and variable, 4.5 to 11.7s | $0.75 / $3.75 (rises after 2026-12-31) |
| `gemini-3.7-flash` | OK, 4.5s | OK, 2.3s | $0.75 / $3.75 |
| `gemini-2.5-flash` | 404, "no longer available to new users" | OK, 1.6s | $0.30 / $2.50 |
| `gemini-2.5-flash-lite` | 404 | 404 | withdrawn |

Three things to take from that table.

The repo default until 2026-09-11 was `gemini-2.5-flash-lite`, which is **withdrawn on both keys**, so the default shipped in `config.py` would have failed outright on any fresh deployment. It is now `gemini-3.5-flash-lite`.

`gemini-2.5-flash` answers on the older key but returns "no longer available to new users" on the newer one, which is the clearest sign the two keys sit on different projects with different grandfathering. **Use the key ending `MzeJlw`.**

And a model being listed and priced is not evidence it will serve your key. Neither is one key's behaviour evidence for another's. Re-run this sweep whenever the key changes, not just when the model does.

Notes that matter for the decision:

- Javanese is no longer the open question. On 2026-09-11 both `gemini-3.8-flash` and `gemini-3.5-flash-lite` answered Javanese questions in Javanese with the price taken from a real tool call, and 3.8-flash produced correct krama. Section 3's eval still matters for breadth, but the register is not a blocker.
- Cost is not the deciding factor. A bot turn is roughly 3,000 input tokens (system prompt, tool schema, session summary, tool results) and 300 output tokens. On 3.8 Flash that is about $0.0034 per turn, on 3.5 Flash-Lite about $0.0017. At 1,000 conversations a month with five turns each, the difference is about $9 a month.
- `gemini-3.5-flash-lite` also chains tools correctly: asked what happens if Semeru erupts, it called `list_presets` then `run_whatif` and returned a real scenario result in 3.2 seconds.
- Function calling is what the orchestrator relies on; all Flash models support it. Do not use a preview model in production.
- Rate limits are per project, not per key, and the numbers are shown only inside AI Studio (Rate Limit page). The free tier is enough for the eval and local development. Tier 1 (billing on) is enough for the pilot.

Set in the environment:

```
GEMINI_MODEL=gemini-3.5-flash-lite
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

- Local: **`whatsapp_bot/.env`**, not the repo-root `.env`. `config.py` loads `whatsapp_bot/.env` first and stops there, so bot settings written to the root file are silently ignored. Both files are gitignored. Never paste a key into chat, a commit, or the dashboard.
- Production: Hugging Face Space `masterAAA123/agriflow-api`, Settings, Variables and secrets, add secret `GEMINI_API_KEY`, and set `GEMINI_MODEL=gemini-3.5-flash-lite` and `MOCK_MODE=false`. Restart the Space.

## 3. Gemini: prove Indonesian and Javanese before pinning

Run the 30-utterance eval (15 Indonesian, 8 Javanese ngoko, 7 Javanese krama). It needs only the key; it does not touch the AgriFlow API.

```
python tools/eval_llm_lang.py --out .tmp/eval_lang.md
python tools/eval_llm_lang.py --models gemini-3.5-flash-lite gemini-3.8-flash
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

1. Go to https://platform.openai.com, sign in or create an account, and open **Settings → Billing**. Add a payment method and set a monthly budget limit. **Since 2026-09-11 OpenAI is the PRIMARY provider** (see section 3d), so this is an expected spend rather than a rarely-touched ceiling: budget for roughly every turn hitting it, not the small fraction a fallback would take. A small number of test requests work before billing is added, but production traffic needs it.
2. **Settings → API keys**, create a new secret key, name it `agriflow-fallback`. Copy it immediately; it is shown once.
3. Put it in `.env` locally and as an HF Space secret, same pattern as `GEMINI_API_KEY`:
   ```
   OPENAI_API_KEY=sk-...
   OPENAI_MODEL=gpt-5.6-luna
   ```
   Leaving `OPENAI_API_KEY` empty does not break anything: `build_llm_client()` sees the configured primary has no key, inverts the order, and puts Gemini in front with no fallback beneath it. That guard exists because a keyless primary would otherwise be born mocked and short-circuit before ever reaching a perfectly good key on the other tier.
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
## 3d. Live verification, 2026-09-11: two bugs the unit tests could not catch

The orchestrator was run against live Gemini for the first time on 2026-09-11. It did not work, and both failures were invisible to `tests/test_tool_calling.py` because that file asserts against **fake** SDK response objects. It proves the loop logic and nothing about whether either vendor accepts our tool schema.

**Gemini rejected every request.** `400 INVALID_ARGUMENT`, naming all 15 declarations at once: `Unknown name "additional_properties"`. Gemini's function-declaration schema is an OpenAPI 3.0 subset with no `additionalProperties`, and one occurrence fails the whole call. Fixed by stripping the key on the Gemini path only (`GeminiClient._for_gemini_schema`), so `TOOL_SPECS` stays a single shared list.

**OpenAI rejected the second round trip.** `Unknown parameter: 'input[1].status'`. The Responses API stamps a read-only `status` on output items and then refuses that same field back as input. The item has to be echoed to preserve the `call_id` linkage, so the fix drops the field instead.

After both fixes, measured end to end with real engine data:

| Question | Time | Tools called | Result |
|---|---|---|---|
| "Berapa harga cabai rawit di Kabupaten Kediri?" | 17.9s | `get_price`, `get_data_freshness` | Rp30.750/kg, dated |
| "Kabupaten mana saja yang surplus bawang merah?" | 10.2s | `get_surplus_deficit`, `get_data_freshness` | Nganjuk 190.610,19 t, ranked list |
| "Regane bawang abang ing Kabupaten Nganjuk pinten?" | 14.9s | `get_price` | Rp24.375/kg, answered in Javanese krama |

Javanese krama works without a separate translation layer or an Indonesian-specialist model.

Gemini's latency, however, was 10 to 18 seconds per answer, above both the 7.5 second deadline and ManyChat's 10 second timeout. That is why the cascade was flipped later the same day: `LLM_PRIMARY` now defaults to `openai`, with Gemini as the tier underneath. Re-measured with OpenAI in front on `gpt-5.6-luna`, the same two questions took **6.0s and 4.6s, both inside the deadline**, each with a successful tool call and the same prices. Set `LLM_PRIMARY=gemini` to put Gemini back in front with no code change.

One register caveat: on the Javanese question Gemini answered in krama ("Regi ... inggih punika") while OpenAI answered in ngoko ("Regane ... saben kg"). If formal register matters for a particular audience, that is a point in Gemini's favour worth weighing against the latency.

The test gap remains open: nothing in the suite would catch a third schema incompatibility. A contract test that sends one real request per provider, skipped when no key is present, is the fix.

## 4. ManyChat: plan, number, connection (founder does this)

Budget about two hours for this section if nothing goes wrong, and expect the Meta step to be where it does go wrong.

### 4.1 Buy the Pro plan

Re-verified on 2026-09-11 against ManyChat's own plan pages. **WhatsApp cannot be connected on Essential at any price.** Essential ($17 a month, 250 active contacts) covers two channels and those are Instagram and Facebook Messenger only. WhatsApp appears as a connectable channel starting at **Pro** ($39 monthly, $29 a month if billed annually, 2,500 active contacts, then $0.05 per extra contact).

Take the monthly option. An annual commitment for a pilot that has not started is money spent on a guess.

An "active contact" is a distinct person who messaged you or triggered an automation inside the billing month, counted once no matter how many messages they send. A demo audience of judges plus a few test numbers is nowhere near 2,500.

### 4.2 Get a WhatsApp number

The number must be one of:

- a number not currently registered on any WhatsApp account, or
- a number already on the **WhatsApp Business App**, which can be migrated, or
- a new number, including the one ManyChat offers to sell inside the connect wizard.

A number sitting on the ordinary personal WhatsApp app must be **deleted from WhatsApp first**, which wipes that account's chat history. Do not use a personal number you rely on.

The number in `whatsapp_bot/config.py` is Twilio's shared sandbox (`+14155238886`) and cannot be moved here. For a pitch, a real Indonesian `+62` number reads far better than a foreign one.

The number must be able to receive an SMS or a voice call for the verification code during setup.

### 4.3 Prepare the Meta Business Portfolio before you start

Meta's embedded signup asks for these mid-flow, and hunting for them with the wizard open is how people get stuck:

- Business legal name
- Business address
- Business website, use `https://agriflow.farm`
- A Facebook account that is an admin of the Business Portfolio

Use the AgriFlow business portfolio, not a personal profile. Only the account owner should click through this step, because it grants ManyChat access to your WhatsApp Business Account.

### 4.4 Connect the channel

1. ManyChat **Home**, then **Connect Channels**, then **WhatsApp**, then **Connect**.
2. At "Which number do you want to use?", pick the card matching your situation from 4.2.
3. Click **Connect Through Meta**. A Facebook popup opens.
4. Log in, select or create the Business Portfolio, and fill in the business details from 4.3.
5. Enter the phone number, choose SMS or voice, and enter the code.
6. Accept the WhatsApp Business terms and finish. The channel should then show as connected in ManyChat.

If the popup stalls or loops, close it and restart from step 1. A half-finished embedded signup is common and usually clears on a clean retry rather than by clicking through the stuck screen.

### 4.5 Understand your messaging limit on day one

An unverified business starts on Meta's lowest tier and can message only a limited number of unique users per day. That is enough for a demo and a small pilot.

Start **business verification** in Meta Business Manager the same day you connect. It takes days rather than hours, so it cannot be rushed before a demo, and the demo does not need it.

### 4.6 Generate the API token

ManyChat **Settings**, then **API**, then generate the token. Store it as `MANYCHAT_API_TOKEN`.

This token is what lets the backend push a late answer back to the user, which per section 5.6 is the normal path rather than the exception. Without it, slow answers are silently dropped.

Refreshing this token invalidates everything using the old one, so generate it once and put it straight into the Space secrets.

### 4.7 Turn ManyChat's own AI off

ManyChat **Settings**, then **AI**. Switch off every AI feature: AI Step, Intentions, AI-generated replies.

Two reasons. Gemini in our backend is the only model that should talk to users, and ManyChat's AI terms permit them to use inputs and outputs to improve their own features, which is not something to hand farmer conversations to.

## 5. ManyChat: the flow, node by node

The endpoint is built and tested (section 3c). Do this once `MANYCHAT_WEBHOOK_SECRET` is set on the HF Space and the Space is redeployed, because until then every request is correctly rejected with 401.

### 5.1 Create the five custom fields

ManyChat **Settings**, then **Fields**, then **New Field**. All five are type **Text**:

| Field name | Holds |
|---|---|
| `agriflow_reply` | The answer text, or the holding line |
| `agriflow_status` | `ok` or `pending` |
| `agriflow_lang` | `id` or `jv` |
| `agriflow_intent` | Which tools ran, useful for debugging |
| `agriflow_token` | Reserved, currently always empty |

Name them exactly as written. They match the JSON keys the backend returns, so the mapping is one to one and you never have to remember a translation.

### 5.2 Create the Default Reply automation

**Automation**, then **Default Reply**. This fires on any message that matches no keyword trigger, which is every real question a farmer will ask.

### 5.3 Add the External Request node

Add an action block, then **Make External Request**. Fill it in as:

- **Request type**: `POST`
- **URL**: `https://masteraaa123-agriflow-api.hf.space/manychat/webhook`
- **Headers**:
  - `Content-Type` with value `application/json`
  - `X-AgriFlow-Key` with the value of your `MANYCHAT_WEBHOOK_SECRET`

Only HTTPS URLs are accepted, which the Space already is.

The secret goes in a header and never in the URL. ManyChat logs request URLs in its own flow history, so a secret in a query string would sit in plain view inside the ManyChat UI.

### 5.4 Fill in the request body

The body is JSON. Use the field picker in the body editor to insert each ManyChat value rather than typing the token by hand, because the exact token text differs between accounts and the picker always inserts the correct one.

```json
{
  "subscriber_id": "<System Field: Contact Id>",
  "phone": "<System Field: Phone>",
  "first_name": "<System Field: First Name>",
  "last_input_text": "<System Field: Last Text Input>",
  "last_interaction": "<System Field: Last Interaction>"
}
```

Only `subscriber_id` and `last_input_text` are required by the backend. `phone` supplies the quota identity when present, and the backend falls back to hashing `subscriber_id` when it is empty, so a missing phone degrades quota tracking rather than breaking the turn.

`last_input_text` also carries the **media file URL** when the user sends a voice note or an image instead of text. The backend does not yet distinguish those, so it would treat that URL as though it were a typed question. Until that is handled, either accept odd replies to voice notes or add a **Last Reply Type** condition ahead of this node that routes audio to a message asking the user to type instead.

### 5.5 Map the response

Open **Response Mapping**. ManyChat shows the JSON structure that came back and lets you map each value into a custom field by its JSONPath. Map all five:

| JSONPath | Custom field |
|---|---|
| `$.agriflow_reply` | `agriflow_reply` |
| `$.agriflow_status` | `agriflow_status` |
| `$.agriflow_lang` | `agriflow_lang` |
| `$.agriflow_intent` | `agriflow_intent` |
| `$.agriflow_token` | `agriflow_token` |

### 5.6 Branch on status, and expect "pending" to be the normal case

Add a **Condition** node after the request, testing whether `agriflow_status` equals `ok`.

- **If `ok`**: a **Send Message** node with the text `{{agriflow_reply}}` and nothing else.
- **If not `ok`**, meaning `pending`: a **Send Message** node with `{{agriflow_reply}}`, which at that point holds the short holding line in the user's own language. The real answer then arrives on its own, pushed by the backend through the Public API.

Build this branch properly even though it should now be the rarer path. Measured on 2026-09-11 with OpenAI primary (`gpt-5.6-luna`), answers took 4.6 to 6.0 seconds, inside the 7.5 second deadline, so most turns should return `ok` and answer in the webhook response itself. With Gemini primary the same questions took 10 to 18 seconds and would almost always return `pending`.

Latency is not guaranteed, though. A slow upstream, a question needing two tool calls, or a cold Space can push any turn past the deadline. If this branch is empty when that happens, the user gets silence. Fill it.

### 5.7 Add keyword triggers for the billing commands

Create keyword triggers so these never reach the model and never consume quota: `MULAI`, `BANTUAN`, `STATUS`, `PRO`, `BERHENTI`.

They can point at the same External Request flow. The backend detects them before the quota check and answers them free. Giving them their own triggers simply keeps them out of the Default Reply path.

### 5.8 Test in the right order

1. **Check the request reaches the backend.** Watch the HF Space logs while you send a message. A 401 means the header secret does not match the Space's `MANYCHAT_WEBHOOK_SECRET`.
2. **Test from a real phone, not Test mode.** Response mapping does not run in ManyChat's preview, so a flow that looks correct in Test mode can still fail to fill the custom fields.
3. **Send a question with a known answer**, for example "Berapa harga cabai rawit di Kabupaten Kediri?", and confirm the number matches what the dashboard shows for the same commodity and kabupaten. They share one code path, so any disagreement is a bug worth stopping for.
4. **Send a Javanese question** such as "Regane bawang abang ing Nganjuk pinten?" and confirm the reply comes back in Javanese.
5. **Confirm the late answer arrives.** Because most answers are `pending`, verify that the second message actually lands. If it never does, `MANYCHAT_API_TOKEN` is missing or wrong on the Space.

## 6. Environment variables (full list is in the spec, section 6.4)

```
GEMINI_API_KEY=                 # secret
GEMINI_MODEL=gemini-3.5-flash-lite
OPENAI_API_KEY=                 # secret; empty disables the fallback tier entirely
OPENAI_MODEL=gpt-5.6-luna
LLM_PRIMARY=openai              # which provider answers first; the other becomes its fallback
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
