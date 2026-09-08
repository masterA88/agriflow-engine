Language / Bahasa: **English** · [Bahasa Indonesia](./README.md)

<p align="center"><img src="assets/logo-mark.png" alt="AgriFlow logo" width="300"/></p>

<h1 align="center">AgriFlow</h1>

<p align="center">
  <strong>AI-Powered Food Security Intelligence Platform</strong><br/>
  <em>Inter-Regional Agricultural Supply–Demand Matching Platform</em>
</p>

<p align="center"><b>Detect · Predict · Distribute</b></p>

<p align="center">
  <img src="https://img.shields.io/badge/PIDI-DIGDAYA%20%C3%97%20Hackathon%202026-1B5E20?style=for-the-badge" alt="Hackathon"/>
  <img src="https://img.shields.io/badge/Problem%20Statement-2%20Matching%20Demand–Supply-4CAF50?style=for-the-badge" alt="PS"/>
  <img src="https://img.shields.io/badge/tests-544%20passing-brightgreen?style=for-the-badge" alt="Tests"/>
</p>

> **Project roadmap spans 3 Phases.** Full technical documentation from previous versions is archived at [`README_v13.md`](README_v13.md) (latest snapshot), [`README_v12.md`](README_v12.md), and [`README_v11.md`](README_v11.md).

---

<details>
<summary><b>🖼️ View Research Poster (click to expand)</b></summary>

<br/>

<p align="center"><img src="poster/agriflow-poster.jpg" alt="AgriFlow Research Poster" width="100%"/></p>

</details>

---

# Phase 1 — Team & Links

## Team

| Name | Role | LinkedIn |
|------|------|----------|
| Chelsea | Data Analyst | [Chelsea](https://linkedin.com/in/chelseaayu) |
| Hilmi | Data Architect | [Hilmi](https://linkedin.com/in/hilmi888/) |
| Monika | UX Researcher | [Monika](https://linkedin.com/in/monika-hermiani) |
| Irpan | Data Engineer | [Irpan](https://linkedin.com/in/irpanpilihanrambe) |

## Links

| Resource | Link |
|----------|------|
| Pitch Deck | [Canva](https://www.canva.com/design/DAHETj2ulzg/VIvgxVkQ6I9R24ucphy2mQ/view) |
| Dashboard (Live Demo) | [agriflow.farm](https://agriflow.farm/) |
| Proposal (v13) | [docs/AgriFlow_Proposal_v13.pdf](docs/AgriFlow_Proposal_v13.pdf) |
| Supporting Evidence | [Five evidence categories](#supporting-evidence) — after Phase 3 |
| User Feedback | [5 early testers + 4 farmer interviews](#user-feedback) |

---

# Phase 2 — What We Have Built (MVP)

## The Problem

Every year Indonesia loses trillions of rupiah in food — **40% occurs in distribution, not production**. In one district farmers throw away chilli because prices collapse; in the next district prices spike because supply is scarce. Local governments often discover the crisis **2–3 weeks too late**.

## The Solution

**AgriFlow matches surplus districts with deficit districts** — like "Uber for food", but aware of perishability, real road distances, and **equity for underserved regions**. Three core functions:

- **Detect** — find price anomalies (spikes/drops) from daily price data.
- **Predict** — forecast prices 30 days ahead.
- **Distribute** — intelligently and equitably match surplus to deficit.

## Architecture (High-Level)

```
   REAL DATA SOURCES             AGRIFLOW ENGINE                   ACCESS
  (BPS · PIHPS · OSRM)      ┌──────────────────────────┐
  production · consumption ─▶│ DETECT   price anomalies  │ ──┐
  prices · population        │ PREDICT  30-day forecast  │   ├──▶ Map dashboard
  per-district East Java     │ DISTRIBUTE 4-layer match  │   └──▶ WhatsApp bot
                             └──────────────────────────┘
```

All three functions (Detect · Predict · Distribute) share one real data source, then served via Dashboard and WhatsApp.

📄 **Full methodology detail — rationale, how it works, evaluation, validation, and paper citations: [Architecture Document (PDF)](docs/AgriFlow_Architecture.pdf).**

## Features Already Running

| Function | Feature | Status |
|----------|---------|:------:|
| **Distribute** | 4-layer matching engine (hard constraints → multi-objective scoring → equity) running on **real BPS per-district data (2022)** | ✅ |
| **Detect** | Price anomaly detection (deseasonalize + robust statistics) on daily PIHPS prices **2021–2025** | ✅ |
| **Predict** | 30-day price forecasting for 38 regencies/cities x 7 commodities. What is **served since 2026-09-08** is **TimesFM 2.0 zero-shot** (`timesfm_2.0`) with a P10 to P90 band from the model quantiles (uncalibrated, no backtest on this data yet; an accuracy figure follows once the rolling-origin backtest has been run). The seasonal-naive baseline with split-conformal intervals remains as the fallback, and that is the model behind the **10.8% MAPE** on the [holdout backtest](docs/evidence/pengujian.md#3-model-evaluation) | ✅ |
| **Accessibility** | **WhatsApp Chatbot** (ask price & recommendations) + **interactive map Dashboard** | ✅ |
| **Security** | The site is *login-first*: opening it shows a login page. Judges click **"Masuk sebagai Tamu" (Enter as Guest)** to review without creating an account. A Supabase account system (server-side JWT verification, Row Level Security on 12 tables, password reset) is ready for a subscription model; sensitive subscriber & billing data stays JWT-protected server-side. | ✅ |
| **Real data** | **6 real commodities** per-district: premium & medium rice, large & cayenne chilli, red & garlic onion + 5 years of PIHPS prices | ✅ |

> **Quality:** 544 automated tests pass (552 collected, 8 skipped) — the engine is tested, reproducible, and honest about its limitations (see [Testing & Scenarios](#testing--scenarios) and Phase 3).
>
> 📁 Full evidence lives in [**Supporting Evidence**](#supporting-evidence) after Phase 3: five categories, including [testing evidence](docs/evidence/pengujian.md) and [usability testing with 5 real users](docs/evidence/usability-early-testing.md).

### Snapshots

**Dashboard** — East Java map with per-district surplus/deficit bubbles, a *top matches* list, plus a **price Forecast & Anomaly** panel (all three functions on one screen):

![AgriFlow Dashboard](assets/dashboard.png)

**WhatsApp Bot** — ask prices, find buyers/suppliers, get price forecasts & anomalies via chat. Supports **Indonesian** and **Javanese** (inclusion for rural farmers):

| Indonesian | Javanese |
|:---:|:---:|
| ![WhatsApp Indonesian](assets/whatsapp-id.png) | ![WhatsApp Javanese](assets/whatsapp-jawa.png) |

## Testing & Scenarios

Because AgriFlow's output drives inter-district food allocation that touches low-HDI districts, claims of "fair" and "robust" must be re-auditable — not just narrative. The test suite locks food-balance figures as *golden numbers* (reproducibility), guards sensitive policy parameters against accidental drift (regression-safety), and tests anomaly detection adversarially.

**552 tests collected · 544 pass · 8 skipped · cross-OS on CI.** ([raw output](docs/evidence/runs/pytest.txt))
(Skip = `test_timesfm_importorskip`: skipped when the heavy TimesFM library isn't installed on the runner; the forecasting path is still tested via fallback + API contract.)

The production server loads **real BPS data by default** (`DATA_BACKEND=csv`, the default). The old synthetic 19-commodity fixture is still used by 13 test files (`DATA_BACKEND=demo`) to exercise engine logic across a wider commodity range — it is never served to users.

| Category | Count | Coverage |
|---|---|---|
| Per-layer unit (L0–L3) | 73 | IPM tier, distance/perishability constraints, scoring, equity allocation |
| 25 edge-case scenarios (A–F) | 64 | Volume, spatial, temporal, disruption, political, quality |
| Real BPS/PIHPS data validation | 57 | Rice + horticulture 2022 food-balance, reproducible pipeline |
| Price anomaly detection | 49 | Season-aware Hampel/MAD on deseasonalized residuals (previously labeled S-H-ESD) |
| Forecast & API | 40 | Forecast/anomaly endpoints + fallback |
| Baseline & equity | 39 | greedy/uniform/proportional vs AgriFlow + supply-constrained scenario |
| Ingest & integration | 73 | DB loader, PIHPS ingest, OSRM distance, WhatsApp bot |
| Dashboard auth & WhatsApp quota | 117 | Supabase login, server-side JWT verification, RLS on 12 tables, password reset, WhatsApp free-tier quota (disabled by default) |

The **25 edge-case scenarios** map to real East Java events, e.g.: Ramadan spike (C1), Mt. Semeru eruption in Lumajang → unreachable (D4), multi-district flood of rice belts (D5), fuel-price hike → higher logistics cost (E5), and Bulog contract-reserve priority (E3).

**Key results:**
- **Equity proven under scarcity, at zero efficiency cost.** *This is a hypothetical stress test, not a result from the real BPS data:* on the 2022 data East Java is in fact heavily in surplus (6.6× ratio), so the equity value would not surface. To show how the mechanism works we built a synthetic scarcity scenario (the `surplus_deficit_constrained.csv` fixture, surplus 3962t vs deficit 5249t). In it, pure greedy abandons Madura — Sampang **0%**, Bangkalan **20%**; AgriFlow lifts both to **100%** at *identical aggregate coverage* (0.6649), with Gini dropping (0.3017 → 0.2905). We do not claim an equity advantage under abundance, nor that this scenario comes from real data.
- **Season-aware anomalies.** A ~60% price drop is flagged, but a pure seasonal pattern (pre-Eid cycle) does **not** trigger false positives; genuine anomalies riding on top of the seasonal pattern are still caught.
- **The data reveals a structural deficit, not a bug.** Garlic (bawang putih) produces **0 matches** across all 38 districts on the 2022 BPS data — East Java is deficit in garlic in every district, consistent with Indonesia being a net garlic importer. The engine is working correctly; the data is what's speaking.

📄 Full detail (why, the 25-scenario list, paper citations): [Architecture Document](docs/AgriFlow_Architecture.pdf) §Testing & Validation.

## Why Our Tech Stack Is LEAN (not as large as the original proposal)?

The initial proposal listed a large stack (Qdrant, LangChain, Redis, n8n, multi-cloud, etc.). After actually building, we **intentionally cut it** — *honest engineering* for current scale (38 districts in East Java):

| Original Plan | What We Use | Reason |
|---|---|---|
| Qdrant (separate vector DB) | **Supabase pgvector** | Small corpus — no need for a dedicated vector service |
| LangChain | **Gemini API directly** | RAG this simple doesn't need a heavy framework |
| Redis cache | **In-process cache** | Load doesn't require it yet; engine is deterministic |
| 5 hosting platforms | **2 (HF Spaces + Vercel)** | Fewer failure points, cheaper |

**Our principle: use what's sufficient, not what's fashionable.** Big components earn their place when scale justifies them — that's **Phase 3**.

---

# Phase 3 — Future Plans & Scaling

Phase 3 covers two things we keep honestly separate: features we intentionally deferred because they aren't needed at the current scale, and limits we've measured on the running engine and scheduled fixes for.

## What's deferred (waiting on data or real load)

| Plan | Purpose | Trigger |
|---|---|---|
| National scale, 514 districts | From 38 East Java districts to all of Indonesia | spatial partitioning + distance precompute |
| Exogenous forecasting (ENSO index, Ramadan calendar) | Accuracy improves under climate shocks & holidays | exogenous data available |
| Broiler chicken & eggs (real data) | Completes the 6 core commodities | per-district broiler & layer-egg production data released |
| Granular per-city/market prices | Real gap can be Rp5,000 to 15,000/kg (chilli interview) | open market price feed |
| Facilitating inter-district transactions | Price info alone is "not effective enough" without a buy/sell channel (onion & rice interviews) | distribution partnership |
| Source transparency & transaction security | User-trust requirement (interviews) | formal partnership stage |
| Sahabat-AI (Javanese/Madurese) + phone IVR | Inclusion for elderly farmers & feature-phone users | channel-scaling stage |
| Qdrant / Redis / n8n | Vector scale, caching, orchestration | when real load arrives |

## Coverage limits today (the gate is data availability, not architecture)

The engine is already ready to process any data it's given; what limits it is the availability of public per-district data. Once a source opens up, the same pipeline processes it immediately with no architecture change.

| Coverage today | The gate |
|---|---|
| 6 core commodities | awaiting per-district production data for other commodities to be released by BPS |
| Reference year 2022 | the most complete year across all per-district sources; a newer year is simply ingested when available |
| Broiler chicken & eggs not yet | the other 13 commodities remain synthetic placeholders, not served to users (`DATA_BACKEND=csv`) |
| Chilli/onion consumption via national figures | rice consumption is already per-district & used for real; the rest awaits publication |
| Tier-2 prices (non-IHK districts) | Bapanas Panel Harga is under maintenance; once the feed is restored, 30+ districts are covered immediately |

## Quantified engineering debt (scheduled fixes)

We measured these two limits ourselves against the engine's own achievable ceiling, with benchmarks committed and reproducible by a judge.

1. ~~The allocator is not yet optimal.~~ **Closed in v1.1.** Measured against the exact LP transportation optimum on real BPS data: the stable tier leaves 25.4% of equity-weighted welfare on the table, the greedy tier 11.1%. Concrete evidence: Sumenep's cabai_merah demand is only 26% filled even though reachable supply (2,662 t within 200 km) exceeds the need (1,418 t), greedy already committed that supply elsewhere first. So this is an optimality problem, not a scarcity problem. `ALLOCATOR=lp` is now the API default, a capacitated LP transportation solve (scipy HiGHS) with equity inside the objective, measured welfare +3.9% over greedy on real BPS data; greedy stays available as a fallback. See [Backend v1.1](#backend-v11-august-2026) and `benchmarks/output/lp_allocator.json`. Old root cause: `matching_engine/allocation.py:307`.
2. ~~Unify the anomaly detectors.~~ **Closed in v1.1.** The user-facing anomaly panel already used robust S-H-ESD (`analysis/price_anomaly.py`). But the internal D3 pre-filter gate (`matching_engine/engine.py:62`) still used a non-robust 3σ z-score, on 70,953 real PIHPS observations it recalled only 14.4% of validated anomalies, and a D3 flag excluded a node from matching entirely. The D3 gate now reads the same Hampel/MAD scanner output as the user panel (`analysis/anomaly_gate.py`); the API label is `hampel_mad_v2`, not S-H-ESD. See [Backend v1.1](#backend-v11-august-2026).

## Scaling Up

National-scale growth is gated by the pace of public per-district data opening up, not technical readiness. Our approach: prove value at province scale with real data first, then expand as data becomes available.

---

## Running (quick technical)

```bash
pip install -r requirements.txt
python examples/run_demo_real.py   # matching demo on real BPS 2022 data
pytest tests/                      # 544 pass, 8 skipped
```

Full engineering detail in [`README_v12.md`](README_v12.md).

### Backend v1.1 (August 2026)

Server-side changes that close Phase 3 engineering-debt items 1 and 2, plus audit findings F1, F3, F7. All verified by 544 passing tests (552 collected, 8 skipped).

| Change | Where | Evidence |
|---|---|---|
| Optimal L3 allocator: capacitated LP transportation (scipy HiGHS), equity inside the objective; greedy stays as fallback | `matching_engine/allocation.py::lp_optimal_allocate`, `ALLOCATOR=lp` default in the API | `python benchmarks/lp_allocator.py` (welfare vs greedy logged in `run_metadata.welfare_gain_pct`) |
| One anomaly detector: the D3 gate uses the same Hampel/MAD scanner output as the panel; API label `hampel_mad_v2` (not S-H-ESD) | `analysis/anomaly_gate.py`, `run_matching(anomaly_keys=...)` | `run_metadata.anomaly_gate == "batch_hampel_mad"` |
| Calibrated forecast interval on the seasonal-naive baseline (fallback): split-conformal rolling-origin, measured 80% coverage (was 42%) at the same 10.8% MAPE; the served TimesFM artefact still uses uncalibrated model quantiles | `analysis/forecast_timesfm.py`, field `interval_method` | `python analysis/backtest_baseline.py` |
| Calendar bug (audit F1): explicit Ramadan now wins over SCHOOL_START; import policy composes on top of the event profile | `matching_engine/engine.py`, `scoring.apply_import_policy` | `tests/test_backend_v11.py::TestCalendarPriority` |
| New endpoints: `/api/v1/meta` (data-as-of), `/api/v1/summary` (computed KPIs), `/api/v1/report.csv`, `/api/v1/matches/explain`, `POST /api/v1/simulate` (presets: semeru, banjir_sentra_padi, banjir_madura, ramadan, bbm_20, impor, suramadu_tutup) | `whatsapp_bot/server.py` | `tests/test_backend_v11.py::TestApiV11` |
| Match cards carry a 5-dimension `breakdown`, `base_score`, `equity_multiplier`, `why` | `_serialize_match` | `GET /api/v1/matches` |
| The `city` parameter now accepts a city name (audit F7) | `_resolve_city` | `GET /api/v1/forecast?commodity=cabai_rawit&city=Kota%20Surabaya` |
| Daily artefact refresh (anomalies, forecast, backtest) via GitHub Actions | `.github/workflows/refresh-data.yml` | automatic `data: daily refresh ...` commit |

---

# Supporting Evidence

All of AgriFlow's supporting evidence is organised along the five categories in the submission
guide. The summary lives here; each category has a detailed page under
[`docs/evidence/`](docs/evidence/README.md).

The rule we hold to: **if something has not been run, its status says it has not been run.** No
result was invented to fill a table, and findings that reflect badly on us are included anyway.
Every number comes with a command to reproduce it.

## The five categories

| # | Category | Status | Detail page |
|---|---|---|---|
| 1 | **Digital product** | ✅ 9 of 9 items | [produk-digital.md](docs/evidence/produk-digital.md) |
| 2 | **Testing** | ✅ 10 of 11 items | [pengujian.md](docs/evidence/pengujian.md) |
| 3 | **Users** | ✅ 7 of 8 items | [pengguna.md](docs/evidence/pengguna.md) |
| 4 | **Non-digital early implementation** | ⚠️ 1 of 9 items, 2 partial | [implementasi-non-digital.md](docs/evidence/implementasi-non-digital.md) |
| 5 | **External readiness** | ✅ 4 of 7 items | [kesiapan-pihak-luar.md](docs/evidence/kesiapan-pihak-luar.md) |

## Fastest way to be convinced

| To see | Open |
|---|---|
| The product genuinely runs | [Live production API responses](docs/evidence/runs/api-live-responses.md) — 6 endpoints, captured 22 July 2026 |
| The engine genuinely computes | [Real BPS 2022 demo](docs/evidence/runs/demo_real_bps.txt) — 84 matches, 467k tonnes |
| Real users have tried it | [5 early-tester sessions](docs/evidence/usability-early-testing.md) — 100% task completion |
| We test ourselves hard | [Full audit, July 2026](docs/AgriFlow_Audit_2026-07.pdf) — 7 findings, including the ones against us |

<details>
<summary><b>1. Digital product — 9 of 9 items</b> (click to expand)</summary>

<br/>

Status today: **an MVP running in production**, not a mockup and not a proof of concept.

| Item requested | Status | Evidence |
|---|:---:|---|
| Functional prototype | ✅ | Dashboard + WhatsApp bot + API, all three running |
| MVP | ✅ | Three pillars (detect, predict, distribute) already serving users |
| Proof of concept | ✅ | [Real BPS 2022 demo](docs/evidence/runs/demo_real_bps.txt) |
| Source code repository | ✅ | This repository, open licence |
| API test | ✅ | [Live production API responses](docs/evidence/runs/api-live-responses.md) · 40 automated endpoint tests |
| Working dashboard | ✅ | [agriflow.farm](https://agriflow.farm/) |
| Alpha/beta version | ✅ | Public beta, guest access without registration |
| Demo with real input & output | ✅ | [Demo output](docs/evidence/runs/demo_real_bps.txt) · [API responses](docs/evidence/runs/api-live-responses.md) |
| Runnable rule engine | ✅ | [`matching_engine/`](matching_engine), 4 layers, one command |

Seven real calls against the production API are recorded as they came back: six 200s, and one
deliberately malformed request that returns a 404 listing the available pairs so the caller can
correct itself.

**Two things worth stating plainly.** `GET /health` reports `"mock_mode": true`: the food data
served is entirely real (38 regencies, 6 BPS commodities), but the natural-language layer still
returns canned replies because we run the public demo without paid keys. The repository also has
no numbered release yet.

📄 [Full page](docs/evidence/produk-digital.md)

</details>

<details>
<summary><b>2. Testing — 10 of 11 items</b> (click to expand)</summary>

<br/>

| Item requested | Status | Evidence |
|---|:---:|---|
| Test case | ✅ | [544 passing, 8 skipped](docs/evidence/runs/pytest.txt) · [`tests/`](tests) · [CI, 4 legs](.github/workflows/test.yml) |
| Experiment results | ✅ | greedy vs optimal · [weight sensitivity](docs/evidence/runs/weight_sensitivity.txt) · [detector gap](docs/evidence/runs/anomaly_detector_gap.txt) |
| Model evaluation | ✅ | [Holdout backtest of the seasonal-naive baseline, 10.8% MAPE](docs/evidence/runs/backtest_baseline.txt); the TimesFM 2.0 backtest has not been run yet |
| Performance test | ✅ | [latency](docs/evidence/runs/latency.txt) · [national scale](docs/evidence/runs/national_scale.txt) · [dashboard load](docs/evidence/runs/dashboard_load.txt) |
| A/B test | ✅ | [Haversine vs road distance](docs/evidence/runs/ab_test_road_distance.txt) |
| Simulation results | ✅ | 25 edge-case scenarios · [supply-constrained scenario](docs/evidence/runs/equity_comparison_constrained.txt) |
| Validation report | ✅ | [Full audit](docs/AgriFlow_Audit_2026-07.pdf) · [real-data methodology](REAL_DATA_METHODOLOGY.md) |
| Initial security testing | ✅ | [Summary](docs/evidence/security-review.md) · 117 auth/quota/RLS tests |
| Error log | ✅ | [JSON log sample](docs/evidence/runs/api-request-log-sample.jsonl) · [`request_log.py`](whatsapp_bot/request_log.py) |
| Usability testing | ✅ | [5 sessions, 20-22 July 2026](docs/evidence/usability-early-testing.md) |
| UAT | ⏳ | [Instrument ready](docs/evidence/uat-test-cases.md), **not yet run** |

**Key numbers:** engine p99 of 69 ms against a 500 ms target · 1,096 req/s with 0 failures at
1,000 users · national scale at **3,022 ms, still 6× over target**, which we state as it is.

**A defect we know about:** `tests/test_auth_jwks.py` is flaky, recorded three times (twice in
CI on the Windows py3.11 leg, once locally). The root cause has not been found and we **do not
claim it is fixed**.

📄 [Full page](docs/evidence/pengujian.md)

</details>

<details>
<summary><b>3. Users — 7 of 8 items</b> (click to expand)</summary>

<br/>

| Item requested | Status | Evidence |
|---|:---:|---|
| User feedback | ✅ | [5 session records + screenshots](docs/evidence/early-testing/) |
| Interview after testing | ✅ | The "impressions & feedback" section of each session record |
| Early tester | ✅ | [5 testers, 20-22 July 2026](docs/evidence/usability-early-testing.md) |
| Completion rate | ✅ | 5 of 5 sessions completed |
| Task success rate | ✅ | **20 of 20 tasks (100%)** |
| Initial satisfaction score | ✅ | Ease 4.6 · usefulness 4.8 · recommend 4.4 out of 5 |
| User testimonials | ✅ | [5 direct quotes](docs/evidence/usability-early-testing.md#kutipan) |
| Usage observation results | ⚠️ | An observer attended every session, but the per-task timing column was left blank |

Participants, per-person scores, quotes, what they asked for, and what limits this feedback are
all in [**User Feedback**](#user-feedback) below, with a link to each session record.

📄 [Full page](docs/evidence/pengguna.md)

</details>

<details>
<summary><b>4. Non-digital early implementation — 1 of 9 items, 2 partial</b> (click to expand)</summary>

<br/>

**This is our thinnest category and we do not pretend otherwise.**

| Item requested | Status | Note |
|---|:---:|---|
| Method demonstration | ✅ | 5 sessions demonstrated directly to users, with an observer |
| Process simulation | ⚠️ | 25 simulation scenarios exist, but they run as code, not as human role-play |
| Public service prototype | ⚠️ | The dashboard is publicly accessible, but it is digital |
| Service pilot | ❌ | A pilot-willingness letter exists; the pilot itself has not run |
| Role-play | ❌ | Not yet |
| Limited class or module | ❌ | Not yet |
| Policy sandbox | ❌ | No formal discussion with a regulator yet |
| SOP testing | ❌ | No operational SOP has been written |
| Limited community activity | ❌ | Not yet |

AgriFlow was born as a digital product and was tested through digital channels. SOP testing and
a policy sandbox only start to make sense once an institutional partner runs allocation off
AgriFlow's output; while the output is advice to individual users, there is no SOP to test.

📄 [Full page](docs/evidence/implementasi-non-digital.md)

</details>

<details>
<summary><b>5. External readiness — 4 of 7 items</b> (click to expand)</summary>

<br/>

| Item requested | Status | Evidence |
|---|:---:|---|
| Letter of Intent | ✅ | Signed pilot-willingness letter, 20 July 2026 |
| Willingness to pilot | ✅ | East Java pilot, dashboard + WhatsApp chatbot |
| Domain-expert validation | ✅ | A BRIN postdoctoral researcher tested it directly and gave feedback |
| Data access evidence | ✅ | [BPS](sample_data/bps_real/PROVENANCE.md) · [PIHPS Bapanas](sample_data/price_history/SOURCE.md) · OSRM |
| Exploration agreement | ⚠️ | The letter calls itself "a basis for further discussion"; that discussion has not happened |
| Institutional letter of support | ❌ | Not yet |
| Pilot discussion minutes | ❌ | Not yet, because the discussion has not happened |

Signatory: **Medina Uli Alba Somala, PhD**, Postdoctoral Researcher, Badan Riset dan Inovasi
Nasional. The letter describes itself as **an initial statement of interest, not a binding
agreement**, and we quote it as such. The file itself is deliberately not published in this
repository because it carries a personal phone number, address, and signature; a copy can be
handed to the organisers directly.

All food data traces back to its source files: 70,953 daily PIHPS price rows from 2021 to 2025,
and BPS production and consumption across 38 regencies. All of it is public data, and we make
**no** claim to a privileged data-sharing agreement.

📄 [Full page](docs/evidence/kesiapan-pihak-luar.md)

</details>

---

# User Feedback

The supporting evidence above answers "does the product work". This section answers a different
question: **what did the people using it actually say.** The original session records, including
the screenshots taken at the time, are included, so nothing here has to be taken on trust.

## Early testers — 5 sessions, 20 to 22 July 2026

Every participant was given the same four tasks: check the price of their commodity in their own
regency, find a buyer for a surplus, look at a price forecast or anomaly, and locate what they
were after on the dashboard map.

| Respondent | Profile | Channel | Tasks | Ease | Useful | Recommend | Session record |
|---|---|---|:---:|:---:|:---:|:---:|---|
| **Aji** | Chilli, Kalanganyar, 8 months | Dashboard + WA | 4/4 | 5 | 5 | 5 | [📄](docs/evidence/early-testing/Aji_cabai_kalanganyar.docx) |
| **Denisa Septalian Alhamda** | Shallot, Nganjuk, 5 years | Dashboard | 4/4 | 5 | 5 | 4 | [📄](docs/evidence/early-testing/Deniz_bawang%20merah_nganjuk.docx) |
| **Labib** | Potato, Dieng, 2 years | Dashboard | 4/4 | 4 | 5 | 4 | [📄](docs/evidence/early-testing/labib_kentang_dieng.docx) |
| **Anisa** | Rice, Tapanuli Selatan, 15 years | Dashboard + WA | 4/4 | 4 | 4 | 4 | [📄](docs/evidence/early-testing/anisa_padi_tapanuli%20selatan.docx) |
| **Medina Uli Alba Somala, PhD** | Postdoctoral Researcher, BRIN | Dashboard + WA | 4/4 | 5 | 5 | 5 | [📄](docs/evidence/early-testing/Alba_Peneliti%20Pascadoktoral.docx) |
| | | **Average** | **100%** | **4.6** | **4.8** | **4.4** | |

## What they said

> "The system is good and sophisticated" — **Aji**, chilli farmer

> "Good innovation, and the pricing is reasonable, though for a start I would probably try the
> pay-as-you-go package first" — **Denisa**, shallot farmer

> "Good innovation at a cheap price" — **Labib**, potato farmer

> "A good innovation and easy to use" — **Anisa**, rice farmer

> "A very good innovation, and useful for the nation" — **Medina Uli Alba Somala, PhD**,
> postdoctoral researcher, BRIN

*(Quotes translated from Indonesian; the originals are in the session records.)*

## What they asked for, and what we did

High scores are easy to collect in sessions moderated by the people who built the thing. The
repeated patterns are worth more:

| What we heard | Participants | Our response |
|---|:---:|---|
| Seller/supplier information | **3 of 5** | On the backlog. The same request had already surfaced in the field interviews before the product existed, so two different methods point at the same gap |
| Hard to read the baseline forecast | 1 | Matches the measured finding that [the forecaster's confidence interval is not calibrated](docs/evidence/pengujian.md#3-model-evaluation): a band labelled 80% achieves 42% |
| Subscription pricing is confusing | 1 | Pricing needs a clearer explanation before wider rollout |
| Mobile layout is poor | 1 | Responsive fixes |
| Wants to buy and sell inside the platform | 1 | Out of scope for now. AgriFlow matches; it does not yet facilitate transactions |

## What limits this feedback

Stated here, not in a footnote:

- **Every session was moderated by a team member.** The presence of the product's authors raises
  success rates and suppresses criticism. Read 4 out of 4 as "the task could be completed", not
  "completed unaided".
- **Five participants is a small sample**, and the segment most at risk, older farmers with low
  digital literacy, is not represented at all.
- **Per-task timing was not recorded**, even though the session sheet had a column for it.

[The round-2 protocol](docs/evidence/usability-test-protocol.md) is designed to close all three:
a moderator from outside the team, a quota for low-literacy participants, and mandatory timing.

## Feedback from before the product existed

Separately from the sessions above, we interviewed **4 farmers across commodities, with audio
recordings**, between May and July 2026, when there was nothing yet to try. That material is
evidence of *need*, not of *usability*, and we do not count it as usability testing. Transcripts:
[shallot](interview/transcript-bawang-merah.md) · [rice](interview/transcript-padi.md) ·
[chilli](interview/transcript-cabai.md) · [potato](interview/transcript-kentang.md). The full
table with audio links is in the [Indonesian README](README.md#-validasi-lapangan--wawancara-petani).

📄 Full write-up of the five sessions: [usability-early-testing.md](docs/evidence/usability-early-testing.md) ·
User-evidence category: [pengguna.md](docs/evidence/pengguna.md)

---

## License

MIT License — &copy; 2026 Hilmi. See [`LICENSE`](LICENSE).

<p align="center"><em>Detect · Predict · Distribute — for Indonesian food security.</em></p>
