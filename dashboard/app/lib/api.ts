// Typed thin wrapper around the FastAPI dashboard endpoints (v1.1).
//
// Every number the dashboard shows comes through here. There are no
// fallbacks: when the API is unreachable the caller gets an error and the UI
// says so, instead of rendering invented data (audit temuan 6, review v2).

import { getSupabase } from "./supabase";

export const API_BASE =
  process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "") ||
  "http://localhost:8000";

export type Commodity = { code: string; nama: string };

export type BillingStatus = {
  plan: "FREE" | "PRO";
  is_pro: boolean;
  expires_at: string | null;
  used_today: number;
  limit: number;
  remaining: number; // -1 means unlimited (PRO)
};

export type Kabupaten = {
  id: string;
  nama: string;
  lat: number;
  lng: number;
  tier: string;
  ipm: number;
  population: number;
};

export type SurplusDeficitRow = {
  kab_id: string;
  kab_nama: string;
  lat: number;
  lng: number;
  tier: string;
  role: "surplus" | "deficit";
  volume_tons: number;
  price_per_kg: number;
};

export type SurplusDeficitResponse = {
  commodity: { code: string; nama: string };
  rows: SurplusDeficitRow[];
  totals: { surplus_tons: number; deficit_tons: number; balance_tons: number };
};

export type Breakdown = {
  distance: number;
  volume: number;
  price: number;
  perishability: number;
  climate: number;
};

export type MatchEnd = {
  kab_id: string;
  kab_nama: string;
  lat: number;
  lng: number;
  price_per_kg: number;
};

export type Match = {
  surplus: MatchEnd;
  deficit: MatchEnd;
  commodity_code: string;
  commodity_nama: string;
  matched_volume_tons: number;
  distance_km: number;
  final_score: number;
  confidence: string;
  flags: string[];
  // v1.1 explainability
  base_score: number;
  equity_multiplier: number;
  segment_multiplier: number;
  deficit_ipm: number;
  breakdown: Breakdown;
  price_spread_idr_per_kg: number;
  gross_arbitrage_idr: number;
  notes: string;
  why: string[];
};

export type MatchesResponse = { count: number; matches: Match[] };

export type ForecastPoint = { date: string; point: number; p10: number; p90: number };

export type ForecastResponse = {
  commodity_code: string;
  city_id: string;
  city_name: string;
  method: string; // "timesfm_2.0" | "seasonal_naive_baseline"
  interval_method?: string; // "split_conformal_rolling_origin" | "same_month_mad"
  interval_target_coverage?: number | null;
  calibration_residuals?: number;
  generated_at: string;
  horizon_days: number;
  history_end_date: string;
  forecasts: ForecastPoint[];
};

export type PriceHistoryResponse = {
  commodity_code: string;
  city_id: string;
  city_name: string;
  source: string;
  history_end_date: string;
  n: number;
  points: { date: string; price: number }[];
};

export type AnomalyRecord = {
  date: string;
  price: number;
  rolling_median: number;
  deviation_pct: number;
  type: "SPIKE" | "DROP";
  score: number;
  commodity_code: string;
  city_id: string;
  city_name: string;
  persistent: boolean;
};

export type AnomaliesResponse = { count: number; method: string; anomalies: AnomalyRecord[] };

export type Meta = {
  engine_version: string;
  git_commit: string | null;
  data_backend: string;
  allocator: string | null;
  anomaly_gate: string | null;
  anomaly_method: string;
  anomaly_gate_window_days: number;
  anomaly_gate_active_pairs: number;
  data_as_of: {
    price_history_end: string | null;
    anomaly_scan_generated_at: string | null;
    anomaly_last_date: string | null;
    forecast_generated_at: string | null;
    forecast_history_end: string | null;
    forecast_interval_methods: string[];
    bps_reference_year: number;
    ipm_year: number;
    road_distance: string;
  };
  coverage: { kabupaten: number; commodities: string[]; forecast_series: number; matches: number };
  engine_run: {
    latency_ms: number | null;
    welfare: number | null;
    welfare_greedy: number | null;
    welfare_gain_pct: number | null;
    matched_tons: number | null;
    candidate_pairs_evaluated: number | null;
    active_event: string | null;
  };
};

export type CommoditySummary = {
  surplus_tons: number;
  deficit_tons: number;
  matched_tons: number;
  coverage_pct: number | null;
  n_matches: number;
  n_surplus_kab: number;
  n_deficit_kab: number;
  gross_arbitrage_idr: number;
  equity_boosted_matches: number;
  low_ipm_deficit_fulfillment_pct: number | null;
  unmatched_deficit_kab: string[];
};

export type SummaryTotals = {
  surplus_tons: number;
  deficit_tons: number;
  matched_tons: number;
  coverage_pct: number | null;
  n_matches: number;
  gross_arbitrage_idr: number;
};

export type DemandSignalRow = {
  day: string; event_type: string; intent: string | null; commodity: string | null;
  kabupaten_id: string | null; event_count: number; unique_users: number;
};

export type DemandSignal = {
  source: string; channel: "web"; days: number; commodity: string | null; count: number; rows: DemandSignalRow[];
};

export type Summary = {
  data_as_of: { price_history_end: string | null; bps_reference_year: number };
  per_commodity: Record<string, CommoditySummary>;
  totals: SummaryTotals;
  engine: {
    allocator: string | null;
    welfare: number | null;
    welfare_gain_pct_vs_greedy: number | null;
    latency_ms: number | null;
    anomaly_gate: string | null;
  };
};

export type ExplainRow = {
  surplus_kab_id: string;
  surplus_kab: string;
  available_tons: number;
  distance_km: number;
  base_score: number;
  equity_multiplier: number;
  final_score: number;
  breakdown: Breakdown;
  chosen: boolean;
  allocated_tons: number;
};

export type ExplainResponse = {
  deficit: {
    kab_id: string; kab_nama: string; ipm: number; volume_tons: number;
    price_per_kg: number; commodity_code: string;
  };
  weights_used: Record<string, number>;
  allocator: string | null;
  n_viable_suppliers: number;
  ranking: ExplainRow[];
  reason_not_chosen: string;
};

export type SimulateRequest = {
  presets?: string[];
  unreachable_kab?: string[];
  humanitarian_kab?: string[];
  blackout_kab?: string[];
  ramadan?: boolean;
  bbm_pct?: number;
  import_policy?: boolean;
  commodity?: string | null;
  reference_date?: string | null;
  allocator?: string | null;
  limit?: number;
};

export type SimulateResponse = {
  scenario: {
    labels: string[];
    applied: {
      unreachable_kab: string[]; humanitarian_kab: string[]; blackout_kab: string[];
      ramadan: boolean; bbm_pct: number; import_policy: boolean;
    };
    allocator: string | null;
    active_event: string | null;
    weights_used: Record<string, number> | null;
  };
  baseline: SummaryTotals;
  result: SummaryTotals;
  delta: {
    matched_tons: number;
    coverage_pct: number | null;
    n_matches: number;
    welfare: number;
    latency_ms: number | null;
  };
  removed_matches: Match[];
  added_matches: Match[];
  matches: Match[];
  warnings: string[];
  external_opportunities: string[];
};

export type ChatResponse = { reply: string };

// Thrown when the API rejects our token. Callers can catch this specifically
// to send the user back to /login instead of showing a generic error.
export class UnauthorizedError extends Error {
  constructor(path: string) {
    super(`${path} requires sign-in`);
    this.name = "UnauthorizedError";
  }
}

async function authHeaders(): Promise<Record<string, string>> {
  const headers: Record<string, string> = {};
  // Attach the Supabase access token when there is a session. getSession()
  // refreshes it if it is close to expiry, so a tab left open overnight sends
  // a live token rather than a stale one.
  const supabase = getSupabase();
  if (supabase) {
    const { data } = await supabase.auth.getSession();
    const token = data.session?.access_token;
    if (token) headers.Authorization = `Bearer ${token}`;
  }
  return headers;
}

async function fetchJson<T>(path: string): Promise<T> {
  const headers = await authHeaders();
  const r = await fetch(`${API_BASE}${path}`, { cache: "no-store", headers });
  if (r.status === 401) throw new UnauthorizedError(path);
  if (!r.ok) throw new Error(`${path} failed: ${r.status}`);
  return r.json() as Promise<T>;
}

async function postJson<T>(path: string, body: unknown): Promise<T> {
  const headers = await authHeaders();
  headers["Content-Type"] = "application/json";
  const r = await fetch(`${API_BASE}${path}`, {
    method: "POST", cache: "no-store", headers, body: JSON.stringify(body),
  });
  if (r.status === 401) throw new UnauthorizedError(path);
  if (!r.ok) {
    let detail = "";
    try { detail = JSON.stringify((await r.json()).detail); } catch { /* ignore */ }
    throw new Error(`${path} failed: ${r.status} ${detail}`);
  }
  return r.json() as Promise<T>;
}

export const api = {
  commodities: () => fetchJson<Commodity[]>("/api/v1/commodities"),
  kabupaten: () => fetchJson<Kabupaten[]>("/api/v1/kabupaten"),
  surplusDeficit: (commodity: string) =>
    fetchJson<SurplusDeficitResponse>(
      `/api/v1/surplus-deficit?commodity=${encodeURIComponent(commodity)}`,
    ),
  matches: (params: { commodity?: string; kab_id?: string; limit?: number }) => {
    const q = new URLSearchParams();
    if (params.commodity) q.set("commodity", params.commodity);
    if (params.kab_id) q.set("kab_id", params.kab_id);
    if (params.limit) q.set("limit", String(params.limit));
    return fetchJson<MatchesResponse>(`/api/v1/matches?${q.toString()}`);
  },
  explain: (params: { deficit_kab_id: string; commodity: string; limit?: number }) => {
    const q = new URLSearchParams({
      deficit_kab_id: params.deficit_kab_id, commodity: params.commodity,
      limit: String(params.limit ?? 6),
    });
    return fetchJson<ExplainResponse>(`/api/v1/matches/explain?${q.toString()}`);
  },
  forecast: (params: { commodity: string; city: string }) =>
    fetchJson<ForecastResponse>(
      `/api/v1/forecast?commodity=${encodeURIComponent(params.commodity)}&city=${encodeURIComponent(params.city)}`,
    ),
  priceHistory: (params: { commodity: string; city: string; days?: number }) =>
    fetchJson<PriceHistoryResponse>(
      `/api/v1/price-history?commodity=${encodeURIComponent(params.commodity)}&city=${encodeURIComponent(params.city)}&days=${params.days ?? 90}`,
    ),
  anomalies: (params: { commodity?: string; city?: string; limit?: number; since?: string }) => {
    const q = new URLSearchParams();
    if (params.commodity) q.set("commodity", params.commodity);
    if (params.city) q.set("city", params.city);
    if (params.limit) q.set("limit", String(params.limit));
    if (params.since) q.set("since", params.since);
    return fetchJson<AnomaliesResponse>(`/api/v1/anomalies?${q.toString()}`);
  },
  meta: () => fetchJson<Meta>("/api/v1/meta"),
  insightDemand: (p: { commodity?: string; days?: number }) =>
    fetchJson<DemandSignal>(`/api/v1/insight/demand?days=${p.days ?? 30}${p.commodity ? `&commodity=${encodeURIComponent(p.commodity)}` : ""}`),
  summary: (commodity?: string) =>
    fetchJson<Summary>(`/api/v1/summary${commodity ? `?commodity=${encodeURIComponent(commodity)}` : ""}`),
  simulatePresets: () => fetchJson<Record<string, string>>("/api/v1/simulate/presets"),
  simulate: (body: SimulateRequest) => postJson<SimulateResponse>("/api/v1/simulate", body),
  chat: (message: string) => postJson<ChatResponse>("/chat", { message }),
  reportCsvUrl: (commodity?: string) =>
    `${API_BASE}/api/v1/report.csv${commodity ? `?commodity=${encodeURIComponent(commodity)}` : ""}`,
  // Plan + remaining free-tier quota for a WhatsApp number. The API hashes the
  // number server-side; it is never stored in raw form.
  billingStatus: (phone: string) =>
    fetchJson<BillingStatus>(`/billing/status?phone=${encodeURIComponent(phone)}`),
};
