"""
analysis/price_anomaly.py  --  Robust deseasonalised Hampel/MAD price anomaly detector.

METHOD: deseasonalise, then rolling Hampel/MAD on residuals (label "hampel_mad_v2")
    NOTE (v1.1): earlier versions called this "S-H-ESD". It is not: S-H-ESD
    (Hochenbaum, Vallis, Kejariwal 2017) runs an iterative Generalized ESD test
    on STL residuals, while this detector applies a rolling MAD threshold with
    persistence and floor gates, i.e. a Hampel-style filter. The July 2026 audit
    (finding F3) flagged the mislabel; the method is unchanged, the name is fixed.
    Original inspiration: Seasonal-Hybrid ESD
    Based on: Hochenbaum, Vallis, Kejariwal (2017), "Automatic Anomaly Detection in
    the Cloud Via Statistical Learning", arXiv:1704.07706.
    Validated against: Liu & Paparrizos, NeurIPS 2024, "Elephant in the Room" --
    which confirms that robust statistical TSAD remains preferred over transformer-based
    methods when interpretability and policy transparency are required.

PIPELINE (per city x commodity series):
    1. Decompose: price = trend + seasonal + residual
       - trend    : rolling median over `trend_window` observations (robust to level
                    shifts; same justification as original MAD detector).
       - seasonal : median of (price - trend) grouped by *calendar month*.  Month
                    granularity is correct for Indonesian agricultural seasonality
                    (Ramadan, harvest cycles, year-end).  day-of-year would be noisier
                    given the 5-year series length.
       - residual : price - trend - seasonal
    2. MAD on residual:
       flag when |residual_t - rolling_median(residual)| > k * 1.4826 * MAD(residual)
       using a rolling window of `window` observations over the residuals.
    3. Persistence threshold: flag only if the breach persists for >= `persist` days
       (default 2).  One-day noise (telur spike 16 Nov) is filtered.
    4. MAD floor: if MAD(residual window) < `mad_floor_pct` * rolling_median(price),
       skip flagging for that window.  Prevents over-sensitivity on low-volatility
       commodities (beras_medium, beras_premium).
    5. Min relative-change gate: flag only if |deviation_pct| >= `min_dev_pct`
       (default 3 %).  Nominal IDR fluctuations in flat series are noise.

WHY numpy-first (no statsmodels):
    STL (statsmodels) would be cleaner for non-integer period series, but adds a
    heavy dependency the project doesn't already carry.  Monthly medians over 5 years
    of daily observations capture the dominant Indonesian agricultural seasonality
    pattern with zero extra deps.  This is documented as a known simplification.

HONEST LIMITATIONS:
    1. Monthly seasonal component is estimated from only 4-5 years of data per month.
       For commodities with irregular seasonality (Hijri calendar shifts, e.g. Ramadan
       drifts ~11 days/year), the seasonal estimate will lag by up to 2 weeks.  This
       means a Ramadan spike at an unusual calendar date may still be partially flagged.
    2. Trend window is rolling median -- it will lag a step-change by up to trend_window/2
       observations.  Residuals during a rapid price-regime shift will be elevated until
       the trend catches up, producing a cluster of alerts at the breakpoint.  This is
       intentional for the policy-alert use case.
    3. Persistence filter is count-of-consecutive-flagged-observations, not calendar days.
       For weekly-sampled data, N=2 means "two consecutive weeks", not "two days".
    4. This is a robust statistical detector, not AI or ML.  It does not learn from
       labelled anomaly data.  False negatives (missed true anomalies) and false positives
       (flagged non-events) both exist.  The k and persist parameters must be tuned for
       each deployment context.
    5. beras_medium/premium are averages of two PIHPS sub-grades; single-grade commodities
       will have somewhat sharper MAD estimates.

Public API (backward-compatible with v1):
    load_series(commodity_code, city_id, price_dir) -> list[(date, price)]
    detect_anomalies(series, window=30, k=3.0, trend_window=30,
                     persist=2, mad_floor_pct=0.005, min_dev_pct=3.0) -> list[dict]
    scan_all(price_dir, window=30, k=3.0, trend_window=30,
             persist=2, mad_floor_pct=0.005, min_dev_pct=3.0) -> list[dict]

Output schema (each dict):
    date            datetime.date
    price           float           observed price (IDR/kg)
    rolling_median  float           rolling median of residuals at this point
    deviation_pct   float           (price - trend) / trend * 100, signed  [v2: vs trend not raw median]
    type            str             'SPIKE' or 'DROP'
    score           float           |residual dev| / (1.4826 * MAD(residual)), higher = more anomalous
    commodity_code  str             populated by scan_all; empty str from detect_anomalies
    city_id         str             populated by scan_all; empty str from detect_anomalies
    persistent      bool            True if breach lasted >= persist days
"""

from __future__ import annotations

import csv
import datetime
import functools
import math
from collections import defaultdict
from pathlib import Path
from typing import List, Tuple, Dict, Any, Iterable

import numpy as np


# ---------------------------------------------------------------------------
# Commodity code normalisation (mirrors db/price_ingest.py)
# ---------------------------------------------------------------------------

_COMMODITY_MAP: Dict[str, str] = {
    "bawang_merah":   "bawang_merah",
    "bawang_putih":   "bawang_putih",
    "daging_ayam":    "daging_ayam",
    "telur_ayam":     "telur_ayam",
    "cabe_rawit":     "cabai_rawit",
    "beras_medium_1": "beras_medium",
    "beras_medium_2": "beras_medium",
    "beras_super_1":  "beras_premium",
    "beras_super_2":  "beras_premium",
}

# Human-readable city names for reporting (IHK Jatim cities)
CITY_NAMES: Dict[str, str] = {
    "3509": "Jember",
    "3510": "Banyuwangi",
    "3529": "Sumenep",
    "3571": "Kota Kediri",
    "3573": "Kota Malang",
    "3574": "Kota Probolinggo",
    "3577": "Kota Madiun",
    "3578": "Kota Surabaya",
}


# ---------------------------------------------------------------------------
# Internal: load raw CSV
# ---------------------------------------------------------------------------

def _read_csv_rows(csv_path: Path) -> List[Dict[str, Any]]:
    """
    Read one *_cleaned.csv; return list of dicts with canonical commodity codes.
    Silently skips rows with unrecognised commodity codes.
    """
    rows = []
    with csv_path.open(newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            raw_code = row["commodity_code"].strip()
            canonical = _COMMODITY_MAP.get(raw_code)
            if canonical is None:
                continue
            rows.append({
                "date": datetime.date.fromisoformat(row["date"].strip()),
                "city_id": row["city_id"].strip(),
                "commodity_code": canonical,
                "price": float(row["price_per_kg"].strip()),
            })
    return rows


def _load_all_rows(price_dir: Path) -> Dict[Tuple[str, str], List[Tuple[datetime.date, float]]]:
    """
    Load all *_cleaned.csv; return (commodity_code, city_id) -> sorted [(date, price)].
    Multiple sub-grades on the same (date, city) are averaged.
    """
    price_dir = Path(price_dir)
    if not price_dir.is_dir():
        raise FileNotFoundError(f"Price directory not found: {price_dir}")

    accumulated: Dict[Tuple[str, str, datetime.date], List[float]] = {}
    for csv_path in sorted(price_dir.glob("*_cleaned.csv")):
        for row in _read_csv_rows(csv_path):
            key = (row["commodity_code"], row["city_id"], row["date"])
            accumulated.setdefault(key, []).append(row["price"])

    series_map: Dict[Tuple[str, str], List[Tuple[datetime.date, float]]] = {}
    for (commodity, city, date), prices in accumulated.items():
        avg_price = sum(prices) / len(prices)
        series_map.setdefault((commodity, city), []).append((date, avg_price))

    for key in series_map:
        series_map[key].sort(key=lambda x: x[0])

    return series_map


# ---------------------------------------------------------------------------
# Source-aware anomaly adapter (new public path; legacy functions stay below)
# ---------------------------------------------------------------------------

ANOMALY_ARTIFACT_SCHEMA_VERSION = "source-aware-anomaly/v1"
ACTIVE_SOURCE_POLICY = "SISKAPERBAPO_EXACT_KEY_THEN_PIHPS"
SUPPORTED_ANOMALY_COMMODITIES = (
    "beras_premium", "beras_medium", "daging_ayam", "telur_ayam",
    "bawang_merah", "bawang_putih", "cabai_rawit",
)
_SOURCE_NAMES = ("SISKAPERBAPO", "PIHPS")
MARKET_QUALITY_UNAVAILABLE = "UNAVAILABLE_DERIVED_FILE_HAS_FOUR_COLUMNS"
ROOT = Path(__file__).parent.parent
DEFAULT_REGION_REGISTRY = ROOT / "sample_data" / "kabupaten_jatim.csv"


@functools.lru_cache(maxsize=16)
def _cached_anomaly_registry(reference_path: str) -> tuple[tuple[str, str], ...]:
    """Read the authoritative anomaly registry and reject incomplete variants."""
    path = Path(reference_path)
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        required = {"kab_id", "nama"}
        missing = required - set(reader.fieldnames or ())
        if missing:
            raise ValueError(f"{path}: missing required columns: {', '.join(sorted(missing))}")
        rows: list[tuple[str, str]] = []
        for line_number, row in enumerate(reader, start=2):
            city_id = (row.get("kab_id") or "").strip()
            city_name = (row.get("nama") or "").strip()
            if not city_id or not city_name:
                raise ValueError(f"{path}:{line_number}: kab_id and nama must be nonempty")
            rows.append((city_id, city_name))

    ids = [city_id for city_id, _ in rows]
    names = [city_name for _, city_name in rows]
    if len(rows) != 38:
        raise ValueError(f"{path}: expected exactly 38 regions, found {len(rows)}")
    if len(set(ids)) != 38:
        raise ValueError(f"{path}: kab_id values must be unique")
    if len(set(names)) != 38:
        raise ValueError(f"{path}: nama values must be unique")
    return tuple(rows)


def load_anomaly_region_registry(
    reference_path: str | Path = DEFAULT_REGION_REGISTRY,
) -> tuple[tuple[str, str], ...]:
    """Return cached `(city_id, city_name)` registry rows in file order."""
    return _cached_anomaly_registry(str(Path(reference_path).resolve()))


def group_active_price_series(
    active_records: Iterable[Dict[str, Any]],
    registry: Iterable[tuple[str, str]] | None = None,
) -> Dict[Tuple[str, str], List[Dict[str, Any]]]:
    """Group selected public-loader records without filling or blending history.

    This adapter deliberately receives the result of `select_active_prices`; it
    never applies source precedence itself. Unsupported commodities and regions
    outside the authoritative registry are not anomaly-series inputs.
    """
    region_ids = {city_id for city_id, _ in (registry or load_anomaly_region_registry())}
    grouped: Dict[Tuple[str, str], List[Dict[str, Any]]] = defaultdict(list)
    for row in active_records:
        commodity = row["commodity_code"]
        city_id = str(row["city_id"])
        source = row["data_source"]
        price = float(row["price_per_kg"])
        if commodity not in SUPPORTED_ANOMALY_COMMODITIES or city_id not in region_ids:
            continue
        if source not in _SOURCE_NAMES:
            raise ValueError(f"Unsupported selected data_source {source!r}")
        if not math.isfinite(price) or price <= 0:
            raise ValueError(f"Invalid selected price for {(row['date'], city_id, commodity)!r}")
        if not isinstance(row["date"], datetime.date):
            raise ValueError("Selected active price date must be datetime.date")
        grouped[(commodity, city_id)].append({
            "date": row["date"],
            "city_id": city_id,
            "commodity_code": commodity,
            "price_per_kg": price,
            "data_source": source,
        })

    ordered: Dict[Tuple[str, str], List[Dict[str, Any]]] = {}
    for key in sorted(grouped):
        observations = sorted(grouped[key], key=lambda record: record["date"])
        dates = [record["date"] for record in observations]
        if len(dates) != len(set(dates)):
            raise ValueError(f"Duplicate selected active observation for {key!r}")
        ordered[key] = observations
    return ordered


def _history_status(
    city_id: str,
    city_name: str,
    commodity_code: str,
    observations: List[Dict[str, Any]],
    generation_date: datetime.date,
) -> Dict[str, Any]:
    """Return honest selected-history metadata for one fixed status matrix cell."""
    count = len(observations)
    source_counts = {
        source: sum(record["data_source"] == source for record in observations)
        for source in _SOURCE_NAMES
    }
    base: Dict[str, Any] = {
        "city_id": city_id,
        "city_name": city_name,
        "commodity_code": commodity_code,
        "observation_count": count,
        "active_history_source_counts": source_counts,
        "market_quality": None,
        "market_quality_availability": MARKET_QUALITY_UNAVAILABLE,
    }
    if count == 0:
        return {
            **base,
            "series_status": "NO_ACTIVE_HISTORY",
            "history_start_date": None,
            "latest_observation_date": None,
            "history_coverage_ratio": None,
            "history_confidence": None,
            "latest_observation_source": None,
            "observation_freshness_days": None,
        }

    history_start = observations[0]["date"]
    latest = observations[-1]
    coverage = round(count / ((latest["date"] - history_start).days + 1), 6)
    confidence = "HIGH" if coverage >= 0.90 else "MEDIUM" if coverage >= 0.70 else "LOW"
    return {
        **base,
        "series_status": "DETECTABLE" if count >= 30 else "INSUFFICIENT_HISTORY",
        "history_start_date": history_start.isoformat(),
        "latest_observation_date": latest["date"].isoformat(),
        "history_coverage_ratio": coverage,
        "history_confidence": confidence,
        "latest_observation_source": latest["data_source"],
        "observation_freshness_days": (generation_date - latest["date"]).days,
    }


def build_source_aware_anomaly_result(
    active_records: Iterable[Dict[str, Any]],
    generated_at: datetime.datetime,
    registry_path: str | Path = DEFAULT_REGION_REGISTRY,
) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Evaluate selected active history into 266 statuses and provenance events.

    The detector is intentionally called only after a series is labelled
    `DETECTABLE`; this leaves 0 and 1--29 observation series unavailable rather
    than inventing a numerical result.
    """
    if generated_at.tzinfo is None:
        generated_at = generated_at.replace(tzinfo=datetime.timezone.utc)
    registry = load_anomaly_region_registry(registry_path)
    grouped = group_active_price_series(active_records, registry)
    statuses: List[Dict[str, Any]] = []
    events: List[Dict[str, Any]] = []

    for city_id, city_name in registry:
        for commodity_code in SUPPORTED_ANOMALY_COMMODITIES:
            observations = grouped.get((commodity_code, city_id), [])
            status = _history_status(
                city_id, city_name, commodity_code, observations, generated_at.date()
            )
            statuses.append(status)
            if status["series_status"] != "DETECTABLE":
                continue

            numerical_series = [
                (record["date"], record["price_per_kg"]) for record in observations
            ]
            observation_by_date = {record["date"]: record for record in observations}
            for anomaly in detect_anomalies(numerical_series):
                selected = observation_by_date[anomaly["date"]]
                events.append({
                    "date": anomaly["date"].isoformat(),
                    "price": float(anomaly["price"]),
                    "rolling_median": float(anomaly["rolling_median"]),
                    "deviation_pct": float(anomaly["deviation_pct"]),
                    "type": anomaly["type"],
                    "score": float(anomaly["score"]),
                    "persistent": bool(anomaly["persistent"]),
                    "city_id": city_id,
                    "city_name": city_name,
                    "commodity_code": commodity_code,
                    "observation_provenance": {
                        "data_source": selected["data_source"],
                        "observation_date": selected["date"].isoformat(),
                        "price_per_kg": float(selected["price_per_kg"]),
                    },
                })

    events.sort(
        key=lambda event: (
            -event["score"], event["commodity_code"], event["city_id"], event["date"]
        )
    )
    return statuses, events


# ---------------------------------------------------------------------------
# Decomposition: trend + seasonal via numpy (no external dep)
# ---------------------------------------------------------------------------

def _rolling_median(arr: np.ndarray, window: int) -> np.ndarray:
    """
    Rolling median, left-aligned (uses the `window` most recent values up to t).
    Positions with fewer than `window` values use the available prefix (min_periods=1).
    Returns array same length as arr.
    """
    n = len(arr)
    result = np.empty(n, dtype=float)
    for t in range(n):
        lo = max(0, t - window + 1)
        result[t] = float(np.median(arr[lo : t + 1]))
    return result


def _decompose(
    prices: np.ndarray,
    dates: List[datetime.date],
    trend_window: int,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    Decompose a price series into (trend, seasonal, residual).

    trend    = rolling median over trend_window observations
    seasonal = per-month median of (price - trend), applied back to each observation
               by month.  This captures the dominant Indonesian agricultural calendar
               (Ramadan, harvest, year-end) without requiring statsmodels.
    residual = price - trend - seasonal

    Design notes:
    - Month-level seasonality (12 bins) is appropriate here: the dataset spans 5 years
      of daily observations.  Day-of-year (365 bins) would produce 5 samples/bin on
      average -- too noisy.
    - Seasonal is estimated on detrended prices (price - trend), not raw prices, to
      avoid trend contamination in the seasonal component.
    - Seasonal is set to 0 for any month with fewer than 2 detrended observations
      (edge case for very short or gappy series).
    """
    n = len(prices)
    trend = _rolling_median(prices, trend_window)
    detrended = prices - trend

    # Build month -> median of detrended prices
    month_vals: Dict[int, List[float]] = defaultdict(list)
    for i, d in enumerate(dates):
        month_vals[d.month].append(detrended[i])

    monthly_median: Dict[int, float] = {}
    for m, vals in month_vals.items():
        monthly_median[m] = float(np.median(vals)) if len(vals) >= 2 else 0.0

    seasonal = np.array(
        [monthly_median.get(d.month, 0.0) for d in dates],
        dtype=float,
    )

    residual = prices - trend - seasonal
    return trend, seasonal, residual


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def load_series(
    commodity_code: str,
    city_id: str,
    price_dir: str | Path,
) -> List[Tuple[datetime.date, float]]:
    """
    Load the price time series for one (commodity_code, city_id) pair.

    Parameters
    ----------
    commodity_code : str
        AgriFlow canonical code (e.g. "cabai_rawit", "bawang_merah").
        Also accepts raw PIHPS codes (e.g. "cabe_rawit") -- normalised automatically.
    city_id : str
        IHK city identifier (e.g. "3578" for Surabaya).
    price_dir : str or Path
        Directory containing *_cleaned.csv files.

    Returns
    -------
    list of (datetime.date, float)
        Sorted by date ascending.  Empty list if no data found.

    Raises
    ------
    FileNotFoundError
        If price_dir does not exist.
    """
    canonical = _COMMODITY_MAP.get(commodity_code, commodity_code)
    series_map = _load_all_rows(Path(price_dir))
    return series_map.get((canonical, city_id), [])


def detect_anomalies(
    series: List[Tuple[datetime.date, float]],
    window: int = 30,
    k: float = 3.0,
    trend_window: int = 30,
    persist: int = 2,
    mad_floor_pct: float = 0.005,
    min_dev_pct: float = 3.0,
) -> List[Dict[str, Any]]:
    """
    Detect price anomalies with the deseasonalised Hampel/MAD rule: remove trend
    and monthly seasonal medians, then apply a rolling MAD threshold on the
    residuals (persistence and floor gates on top).

    Steps
    -----
    1. Decompose series: trend (rolling median) + seasonal (monthly median of
       detrended) + residual.
    2. Apply rolling MAD on residuals with threshold k * 1.4826 * MAD.
    3. Persistence filter: retain only flags that appear in a streak of >= persist
       consecutive observations.
    4. MAD floor: skip windows where MAD(residual) < mad_floor_pct * rolling median
       of raw prices (protects beras_medium / beras_premium from over-sensitivity).
    5. Min relative change gate: skip flags where |price - trend| / trend * 100
       < min_dev_pct (filters nominal IDR noise).

    Parameters
    ----------
    series : list of (datetime.date, float)
        Price observations, sorted ascending.
    window : int, default 30
        Rolling window for MAD on residuals.  Minimum to flag is window (same as v1).
    k : float, default 3.0
        Sensitivity multiplier.  k=3 corresponds to ~0.3 % tail on Gaussian data;
        effectively ~1-2 % on fat-tailed commodity residuals after deseasonalisation.
    trend_window : int, default 30
        Rolling window for trend estimation.  Larger = smoother trend but more lag.
        Set equal to `window` by default so the two rolling calculations are aligned.
    persist : int, default 2
        Minimum consecutive flagged observations for a flag to be reported.
        Setting persist=1 disables the persistence filter (reverts to v1 behaviour).
    mad_floor_pct : float, default 0.005
        MAD floor as a fraction of the rolling median of raw prices.  E.g. 0.005 means
        the MAD must be at least 0.5 % of the current price level.  Prevents
        over-sensitivity on low-volatility series (beras).
    min_dev_pct : float, default 3.0
        Minimum absolute deviation from trend (as % of trend) to flag.
        Filters nominal fluctuations that pass MAD test only due to very small MAD.

    Returns
    -------
    list of dict, each with keys:
        date            datetime.date
        price           float           observed price (IDR/kg)
        rolling_median  float           rolling median of RESIDUALS at this point
        deviation_pct   float           (price - trend) / trend * 100, signed
        type            str             'SPIKE' or 'DROP'
        score           float           |residual dev| in MAD units
        commodity_code  str             populated by scan_all; empty str here
        city_id         str             populated by scan_all; empty str here
        persistent      bool            True if streak >= persist

    Notes
    -----
    - Series shorter than window returns empty list (same as v1).
    - MAD == 0 on residual window: no flag (perfectly flat residuals mean no
      anomalous structure).
    - Result sorted by score descending.
    """
    if len(series) < window:
        return []

    dates = [d for d, _ in series]
    prices = np.array([p for _, p in series], dtype=float)
    n = len(prices)

    # Step 1: decompose
    trend, seasonal, residual = _decompose(prices, dates, trend_window)

    # Step 2: rolling MAD on residuals — same left-aligned logic as v1
    raw_flags: List[Dict[str, Any]] = []

    for t in range(window - 1, n):
        res_window = residual[t - window + 1 : t + 1]
        roll_med_res = float(np.median(res_window))
        abs_devs = np.abs(res_window - roll_med_res)
        mad = float(np.median(abs_devs))

        raw_dev_res = residual[t] - roll_med_res

        # --- gate logic ---
        if mad == 0.0:
            # Perfectly flat residual window: any non-zero deviation is a
            # step-change (e.g. spike into a perfectly flat series).  We skip
            # the MAD floor (which would fire trivially on mad==0) and score the
            # deviation as percentage of the current price level instead.
            if raw_dev_res == 0.0:
                continue  # truly flat: nothing to flag
            price_level = float(np.median(prices[t - window + 1 : t + 1]))
            score = float(abs(raw_dev_res) / price_level) * 100.0 if price_level > 0 else 0.0
            # still apply min relative-change gate
            raw_price_dev = prices[t] - trend[t]
            dev_pct = (raw_price_dev / trend[t]) * 100.0 if trend[t] > 0 else 0.0
            if abs(dev_pct) < min_dev_pct:
                continue
            raw_flags.append({
                "idx":            t,
                "date":           dates[t],
                "price":          float(prices[t]),
                "rolling_median": round(roll_med_res, 2),
                "deviation_pct":  round(dev_pct, 2),
                "type":           "SPIKE" if raw_price_dev > 0 else "DROP",
                "score":          round(score, 3),
                "commodity_code": "",
                "city_id":        "",
                "persistent":     False,
            })
            continue

        # Step 4: MAD floor -- skip if both (a) MAD is tiny relative to price
        # level AND (b) the current residual deviation is also tiny.
        # This protects against over-sensitivity on low-volatility series
        # (beras_medium / beras_premium) where the residual MAD and the
        # deviation itself are both small IDR amounts.
        # We guard condition (b) so that a genuine large anomaly (large |dev|)
        # is never blocked even if the window MAD happens to be below the floor.
        price_level = float(np.median(prices[t - window + 1 : t + 1]))
        if price_level > 0 and mad < mad_floor_pct * price_level:
            # Only skip if the deviation is also small (< 2x the floor threshold).
            # A 100k deviation on a 54k series must NOT be blocked by the floor.
            dev_abs = abs(raw_dev_res)
            floor_val = mad_floor_pct * price_level
            if dev_abs < 2.0 * floor_val:
                continue

        threshold = k * 1.4826 * mad
        score = float(abs(raw_dev_res) / (1.4826 * mad))

        if abs(raw_dev_res) > threshold:
            # Step 5: min relative-change gate (vs trend, not vs raw median)
            raw_price_dev = prices[t] - trend[t]
            dev_pct = (raw_price_dev / trend[t]) * 100.0 if trend[t] > 0 else 0.0
            if abs(dev_pct) < min_dev_pct:
                continue

            raw_flags.append({
                "idx":            t,
                "date":           dates[t],
                "price":          float(prices[t]),
                "rolling_median": round(roll_med_res, 2),
                "deviation_pct":  round(dev_pct, 2),
                "type":           "SPIKE" if raw_price_dev > 0 else "DROP",
                "score":          round(score, 3),
                "commodity_code": "",
                "city_id":        "",
                "persistent":     False,  # filled in step 3
            })

    # Step 3: persistence filter
    # A flag is "persistent" if the consecutive run of flagged indices that
    # contains it has total length >= persist.
    # Algorithm: for each flagged index, walk backward to the run start, then
    # measure the run forward from there.  Cache run-start -> run-length to
    # avoid O(n^2) re-computation for long streaks.
    flagged_indices = {f["idx"] for f in raw_flags}
    run_length_cache: Dict[int, int] = {}

    def _run_length(idx: int) -> int:
        # Walk to run start
        start = idx
        while (start - 1) in flagged_indices:
            start -= 1
        if start in run_length_cache:
            return run_length_cache[start]
        # Measure run from start
        length = 0
        cur = start
        while cur in flagged_indices:
            length += 1
            cur += 1
        run_length_cache[start] = length
        return length

    anomalies: List[Dict[str, Any]] = []

    for flag in raw_flags:
        is_persistent = _run_length(flag["idx"]) >= persist
        flag["persistent"] = is_persistent
        if is_persistent:
            anomalies.append(flag)

    # Remove internal idx key
    for a in anomalies:
        del a["idx"]

    anomalies.sort(key=lambda x: x["score"], reverse=True)
    return anomalies


def scan_all(
    price_dir: str | Path,
    window: int = 30,
    k: float = 3.0,
    trend_window: int = 30,
    persist: int = 2,
    mad_floor_pct: float = 0.005,
    min_dev_pct: float = 3.0,
) -> List[Dict[str, Any]]:
    """
    Scan all (commodity_code, city_id) combinations and return all detected
    anomalies, sorted by score descending.

    Parameters
    ----------
    price_dir : str or Path
        Directory containing *_cleaned.csv files.
    window, k, trend_window, persist, mad_floor_pct, min_dev_pct
        Passed directly to detect_anomalies().

    Returns
    -------
    list of dict
        Same schema as detect_anomalies() output, with commodity_code and
        city_id populated.  Sorted by score descending.

    Raises
    ------
    FileNotFoundError
        If price_dir does not exist.
    """
    series_map = _load_all_rows(Path(price_dir))
    all_anomalies: List[Dict[str, Any]] = []

    for (commodity, city), series in series_map.items():
        anomalies = detect_anomalies(
            series,
            window=window,
            k=k,
            trend_window=trend_window,
            persist=persist,
            mad_floor_pct=mad_floor_pct,
            min_dev_pct=min_dev_pct,
        )
        for a in anomalies:
            a["commodity_code"] = commodity
            a["city_id"] = city
        all_anomalies.extend(anomalies)

    all_anomalies.sort(key=lambda x: x["score"], reverse=True)
    return all_anomalies
