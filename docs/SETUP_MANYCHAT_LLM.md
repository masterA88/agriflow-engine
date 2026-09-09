# Setup: ManyChat + Gemini + OpenAI for the AgriFlow WhatsApp bot

Author: Hilmi (https://master-hilmi.vercel.app/)
Date: 2026-09-08, OpenAI fallback section added 2026-09-09. Facts below were checked against the vendor pages on those dates; prices and model names move fast on both sides (Gemini moved 2.5 to 3.8 in four months; OpenAI's lineup turned over just as much), so re-check before paying.

This is the operator runbook. The architecture and the reasons behind it live in the build-ready spec (`k1/research/agriflow-chatbot-architecture/drafts/spec-manychat-gemini-behaviour-2026-09-08.md`). That spec still describes a single-provider (Gemini-only) orchestrator; the fallback in section 3b below sits underneath it as an implementation detail the spec's route/compose steps can call into, whichever provider answers.

**Where this lives in ManyChat: nowhere.** ManyChat only ever calls one thing, `POST /manychat/webhook` on our backend. Which LLM answers a given message is decided entirely inside that backend (whatsapp_bot/gemini_client.py), turn by turn. Nothing in the ManyChat flow builder changes because there are now two providers behind the webhook instead of one.

## 0. Where things stand today

| Item | State on 2026-09-08 |
|---|---|
| Google AI Studio | Signed in as the founder. One Gemini key already exists (`...cSlc`) on project `chatbot Project` (`gen-lang-client-0750284801`), created 2026-05-18, **Free tier**. |
| Gemini billing | Not set up. The "Set up billing" link is on the API keys page. |
| ManyChat | Account exists (`fb5562173`), plan **Trial**, no channel connected. The WhatsApp connect wizard is at "Which number do you want to use?". |
| WhatsApp number | None usable. The number in `whatsapp_bot/config.py` is Twilio's shared sandbox (`+14155238886`), which cannot move. |
| Backend endpoint | `POST /manychat/webhook` does not exist yet; it is part of the DEA build from the spec. ManyChat cannot be wired end to end until it is deployed on the HF Space. |

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

## 5. ManyChat: the flow (after the backend endpoint is live)

Do this only once DEA has deployed `POST /manychat/webhook` on the HF Space; until then the External Request has nothing to call. The exact request and response JSON, the custom-field mapping and the 7.5-second deadline rule are in the spec, sections 1.3 to 1.7. In short:

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
4. DEA: build `POST /manychat/webhook`, `chat_session`, `intent_event`, the Gemini-then-OpenAI orchestrator, deploy to the HF Space with the secrets above.
5. Founder with the team: build the ManyChat flow (section 5), test from a real phone, then rehearse the Javanese demo script.

## 8. Costs to expect for the pilot month

| Line | Amount |
|---|---|
| ManyChat Pro, monthly | $39 |
| Gemini, 1,000 conversations of 5 turns on 3.8 Flash | about $17 |
| OpenAI fallback, gpt-5.6-luna | close to $0 if Gemini rarely fails; budget a $10 to $20 monthly cap as a ceiling, not an expected spend |
| Meta conversation charges | $0 until 2026-10-01; after that, service messages beyond 1,000 free per number per month are billed at the utility rate (roughly $175 a month at pilot scale per the spec's estimate) |
| WhatsApp number | depends on the carrier or ManyChat's number offer |
