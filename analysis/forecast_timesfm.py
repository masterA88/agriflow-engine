"""
analysis/forecast_timesfm.py  --  Offline forecast precompute for AgriFlow.

ARCHITECTURE:
    This script runs OFFLINE (locally, not on HF Space) because TimesFM ~2GB
    model cannot be loaded on the free-tier Space (OOM).  The output JSON files
    are committed to the repo and the backend serves them at runtime without
    importing this module or timesfm.

HONESTY POLICY:
    If TimesFM cannot be loaded (not installed, network unavailable, Python
    version incompatible), this script falls back to a seasonal-naive baseline
    that is CLEARLY labelled in the output as "method": "seasonal_naive_baseline"
    so consumers can distinguish it from a genuine TimesFM forecast.

    DO NOT change the labelling.  If you want TimesFM output, fix the environment
    and re-run.

TIMESFM STATUS (2026-05-31):
    timesfm PyPI package (1.0.0) requires Python <=3.11 + jaxlib==0.4.26.
    This project runs Python 3.12+.  TimesFM 2.0 (PyTorch variant) is on
    HuggingFace Hub but requires the same pinned JAX+Flax stack via the PyPI
    package.  Install blocker is hard on Python 3.12/3.14.

    To use real TimesFM:
      1. Run this script with Python 3.11: `py -3.11 analysis/forecast_timesfm.py`
      2. Or wait for timesfm to release a Python 3.12-compatible wheel.
      3. Check for a conda-based install path: `conda install -c conda-forge timesfm`

USAGE:
    # With TimesFM (Python 3.11 + timesfm installed):
    python analysis/forecast_timesfm.py

    # Explicit baseline (any Python):
    python analysis/forecast_timesfm.py --method baseline

OUTPUT:
    sample_data/forecasts/forecast_all.json  --  one file, all series

FORECAST SCHEMA (per record):
    commodity_code   str
    city_id          str
    city_name        str
    method           str  ("timesfm_2.0" | "seasonal_naive_baseline")
    generated_at     str  ISO 8601 UTC
    horizon_days     int  (30)
    history_end_date str  ISO 8601 -- last observed date
    forecasts:  list of {
        date   str  ISO 8601
        point  float   (IDR/kg, point forecast)
        p10    float   (IDR/kg, 10th percentile)
        p90    float   (IDR/kg, 90th percentile)
    }
"""

from __future__ import annotations

import argparse
import datetime
import functools
import json
import math
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

ROOT = Path(__file__).parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from analysis.price_anomaly import load_anomaly_region_registry
from db.price_ingest import load_source_price_history_csvs, select_active_prices

HORIZON = 30


# ---------------------------------------------------------------------------
# Seasonal-naive baseline (transparent fallback -- NOT TimesFM)
# ---------------------------------------------------------------------------

INTERVAL_METHOD_MAD = "same_month_mad"
INTERVAL_METHOD_CONFORMAL = "split_conformal_rolling_origin"
CONFORMAL_TARGET_COVERAGE = 0.80
CONFORMAL_ORIGINS = 36         # rolling origins used for calibration (3 years, monthly)
CONFORMAL_ORIGIN_STEP = 30     # days between origins; grid-searched 2026-08-28, coverage 79.5% at target 80%


def _conformal_offsets(
    series: list[tuple[datetime.date, float]],
    horizon: int,
    n_origins: int | None = None,
    step: int | None = None,
    alpha: float | None = None,
) -> tuple[float, float, int] | None:
    """
    Split-conformal calibration of the interval, rolling-origin style.

    For each of `n_origins` cut points inside the training series, re-run the
    point forecaster on the data before the cut and collect the residuals
    (actual - point) over the next `horizon` days. The lower and upper
    quantiles of the pooled residuals (with the usual finite-sample
    correction) become additive offsets on the point forecast.

    Why: the same-month MAD band shipped in v1.0 covered only 42% of actuals
    while labelled 80% (analysis/backtest_baseline.py). Conformal offsets are
    distribution-free and calibrated on held-out residuals of the very same
    forecaster, so the label matches the measurement. Calibration only ever
    sees data strictly before the forecast origin, so backtests stay
    leakage-free.

    Returns (lower_offset, upper_offset, n_residuals) or None when the series
    is too short to calibrate.
    """
    import numpy as np

    # Read module constants at call time so calibration studies can tune them.
    n_origins = CONFORMAL_ORIGINS if n_origins is None else n_origins
    step = CONFORMAL_ORIGIN_STEP if step is None else step
    alpha = (1.0 - CONFORMAL_TARGET_COVERAGE) if alpha is None else alpha

    n = len(series)
    residuals: list[float] = []
    for i in range(1, n_origins + 1):
        cut = n - i * step
        if cut < 60:
            break
        train = series[:cut]
        test = series[cut:cut + horizon]
        if not test:
            continue
        fc = _seasonal_naive_forecast(train, horizon=horizon, conformal=False)
        by_date = {datetime.date.fromisoformat(r["date"]): r["point"] for r in fc}
        for d, actual in test:
            pt = by_date.get(d)
            if pt is None or actual <= 0:
                continue
            residuals.append(actual - pt)
    if len(residuals) < 20:
        return None
    r = np.array(residuals, dtype=float)
    m = len(r)
    # Finite-sample corrected quantile levels (Lei et al. 2018 style).
    q_hi = min(1.0, np.ceil((m + 1) * (1 - alpha / 2)) / m)
    q_lo = max(0.0, np.floor((m + 1) * (alpha / 2)) / m)
    lower = float(np.quantile(r, q_lo))
    upper = float(np.quantile(r, q_hi))
    return lower, upper, m


def _seasonal_naive_forecast(
    series: list[tuple[datetime.date, float]],
    horizon: int = HORIZON,
    conformal: bool = True,
) -> list[dict[str, Any]]:
    """
    Seasonal-naive: for day h, predict = median of same-calendar-month prices
    observed in the training series.

    Uncertainty band:
        conformal=True  (default since v1.1): point + calibrated residual
                        quantiles from _conformal_offsets, target 80%.
        conformal=False (v1.0 behaviour): +/- 1.4826 MAD of the same-month
                        observations.

    This is a statistical method, not a foundation model.  It is labelled as
    "seasonal_naive_baseline" everywhere it appears; the interval method is
    reported separately in the "interval_method" field.
    """
    import numpy as np

    prices = [p for _, p in series]
    dates  = [d for d, _ in series]
    arr    = np.array(prices, dtype=float)

    # Build per-month (median, MAD) from the last 2 years of observed data
    cutoff = dates[-1] - datetime.timedelta(days=2 * 365)
    recent = [(d, p) for d, p in series if d >= cutoff]
    if len(recent) < 30:
        recent = series  # fall back to full series for short series

    month_stats: dict[int, tuple[float, float]] = {}
    from collections import defaultdict
    month_vals: dict[int, list[float]] = defaultdict(list)
    for d, p in recent:
        month_vals[d.month].append(p)
    for m, vals in month_vals.items():
        v = np.array(vals)
        med = float(np.median(v))
        mad = float(np.median(np.abs(v - med)))
        month_stats[m] = (med, mad)

    # Overall fallback stats
    overall_med = float(np.median(arr[-30:]))
    overall_mad = float(np.median(np.abs(arr[-30:] - overall_med)))

    offsets = _conformal_offsets(series, horizon) if conformal else None

    last_date = dates[-1]
    result = []
    for h in range(1, horizon + 1):
        target_date = last_date + datetime.timedelta(days=h)
        med, mad = month_stats.get(target_date.month, (overall_med, overall_mad))
        if offsets is not None:
            lo_off, hi_off, _m = offsets
            # Residual quantiles can sit on one side of zero when the point
            # forecaster is biased; keep the band containing the point so the
            # p10 <= point <= p90 contract holds (widening never lowers coverage).
            p10 = med + min(0.0, lo_off)
            p90 = med + max(0.0, hi_off)
        else:
            # CI: +/- 1.4826 * MAD (same scaling as the anomaly detector)
            ci_half = 1.4826 * mad if mad > 0 else 0.05 * med
            p10, p90 = med - ci_half, med + ci_half
        result.append({
            "date":  target_date.isoformat(),
            "point": round(med, 2),
            "p10":   round(max(0, p10), 2),
            "p90":   round(p90, 2),
        })
    return result


def interval_method_for(series: list[tuple[datetime.date, float]], horizon: int = HORIZON) -> dict[str, Any]:
    """Describe which interval method a series will get, for the JSON record."""
    off = _conformal_offsets(series, horizon)
    if off is None:
        return {"interval_method": INTERVAL_METHOD_MAD, "interval_target_coverage": None,
                "calibration_residuals": 0}
    return {"interval_method": INTERVAL_METHOD_CONFORMAL,
            "interval_target_coverage": CONFORMAL_TARGET_COVERAGE,
            "calibration_residuals": off[2]}


# ---------------------------------------------------------------------------
# TimesFM path (gated on successful import)
# ---------------------------------------------------------------------------

def _timesfm_available() -> bool:
    try:
        import timesfm  # noqa: F401
        return True
    except ImportError:
        return False


@functools.lru_cache(maxsize=2)
def _load_timesfm_model(model_path: str):
    """
    Load the TimesFM 2.0 (500m PyTorch) checkpoint once and cache it.

    The 2.0-500m checkpoint is a 50-layer, 2048-context model; the library
    defaults (20 layers, 512 context) target the 1.0 checkpoint and will not
    load the 2.0 weights. Loading is expensive (~2 GB download on first run +
    model init), so this is cached and reused across all 266 series instead of
    being rebuilt per call.
    """
    import timesfm

    return timesfm.TimesFm(
        hparams=timesfm.TimesFmHparams(
            backend="cpu",
            per_core_batch_size=1,
            horizon_len=HORIZON,
            context_len=2048,        # 2.0-500m context (multiple of input_patch_len=32)
            num_layers=50,           # 2.0-500m has 50 transformer layers (1.0 had 20)
            num_heads=16,
            use_positional_embedding=False,
        ),
        checkpoint=timesfm.TimesFmCheckpoint(
            huggingface_repo_id=model_path,
        ),
    )


def _timesfm_forecast(
    series: list[tuple[datetime.date, float]],
    horizon: int = HORIZON,
    model_path: str = "google/timesfm-2.0-500m-pytorch",
) -> list[dict[str, Any]]:
    """
    Run TimesFM 2.0 (PyTorch variant) on one price series.
    Uses the process-cached model (see `_load_timesfm_model`).
    Caller must ensure timesfm is installed and Python 3.10/3.11 is active.
    """
    import numpy as np

    prices = np.array([p for _, p in series], dtype=float)
    dates  = [d for d, _ in series]

    tfm = _load_timesfm_model(model_path)

    forecast_input = [prices]
    freq           = [0]  # 0 = high-frequency (daily)

    # timesfm 1.3.0 API: forecast() returns (point_forecast, quantile_forecast).
    # quantile_forecast has shape (batch, horizon, 10): index 0 is the mean and
    # indices 1..9 map to quantiles 0.1..0.9. So p10 = col 1, p90 = col 9.
    point_forecasts, quantile_forecasts = tfm.forecast(forecast_input, freq=freq)

    pf = point_forecasts[0]     # (horizon,)
    qf = quantile_forecasts[0]  # (horizon, 10)
    last_date = dates[-1]
    result = []
    for h in range(horizon):
        target_date = last_date + datetime.timedelta(days=h + 1)
        point = float(pf[h])
        p10   = float(qf[h, 1])
        p90   = float(qf[h, 9])
        # TimesFM 2.0 quantile heads are uncalibrated (per the model card) and
        # can cross on very flat series. Enforce p10 <= point <= p90 so the
        # dashboard forecast band always renders correctly.
        p10   = min(p10, point)
        p90   = max(p90, point)
        result.append({
            "date":  target_date.isoformat(),
            "point": round(point, 2),
            "p10":   round(max(0, p10), 2),
            "p90":   round(p90, 2),
        })
    return result


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main(
    price_dir: Path,
    out_dir: Path,
    method: str,
    model_path: str,
) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "forecast_all.json"

    # Determine actual method
    if method == "auto":
        if _timesfm_available():
            method = "timesfm"
            print("TimesFM detected â€” will use real model.")
        else:
            method = "baseline"
            print(
                "WARNING: timesfm not importable on this Python version.\n"
                "Falling back to seasonal_naive_baseline.\n"
                "To get real TimesFM output, run with Python 3.10 or 3.11 + timesfm installed.\n"
                "The output JSON will be labelled method=seasonal_naive_baseline."
            )

    generated_at = datetime.datetime.utcnow().isoformat() + "Z"

    source_records = load_source_price_history_csvs(price_dir)
    active_records  = select_active_prices(source_records)
    city_lookup      = dict(load_anomaly_region_registry())

    series_map: Dict[Tuple[str, str], List[Tuple[datetime.date, float]]] = {}
    for record in active_records:


        key = (record["commodity_code"], str(record["city_id"]))
        if key not in series_map:
            series_map[key] = []
        series_map[key].append(
            (record["date"], float(record["price_per_kg"]))
        )

    for key, pts in series_map.items():
        pts.sort(key=lambda x: x[0])

    print(f"Forecasting {len(series_map)} series ...")
    all_records: list[dict[str, Any]] = []

    for (commodity, city), series in sorted(series_map.items()):
        if len(series) < 30:
            print(f"  Skipping {commodity}/{city}: too short ({len(series)} obs)")
            continue

        if method == "timesfm":
            try:
                fc_points = _timesfm_forecast(series, horizon=HORIZON, model_path=model_path)
                method_label = "timesfm_2.0"
            except Exception as exc:
                print(f"  TimesFM failed for {commodity}/{city}: {exc} â€” using baseline")
                fc_points    = _seasonal_naive_forecast(series, horizon=HORIZON)
                method_label = "seasonal_naive_baseline"
        else:
            fc_points    = _seasonal_naive_forecast(series, horizon=HORIZON)
            method_label = "seasonal_naive_baseline"

        interval_info = (
            interval_method_for(series, HORIZON)
            if method_label == "seasonal_naive_baseline"
            else {"interval_method": "model_quantiles", "interval_target_coverage": 0.80,
                  "calibration_residuals": 0}
        )
        all_records.append({
            "commodity_code":   commodity,
            "city_id":          city,
            "city_name":        city_lookup.get(city, city),
            "method":           method_label,
            **interval_info,
            "generated_at":     generated_at,
            "horizon_days":     HORIZON,
            "history_end_date": series[-1][0].isoformat(),
            "forecasts":        fc_points,
        })
        print(f"  {commodity}/{city}: {method_label} â€” last obs {series[-1][0]}")

    with out_path.open("w", encoding="utf-8") as fh:
        json.dump(all_records, fh, ensure_ascii=False, separators=(",", ":"))

    size_kb = out_path.stat().st_size / 1024
    print(f"\nWrote {len(all_records)} series forecasts to {out_path}  ({size_kb:.1f} KB)")
    if any(r["method"] == "seasonal_naive_baseline" for r in all_records):
        print(
            "\nNOTE: Output labelled 'seasonal_naive_baseline'.  "
            "This is a transparent statistical baseline, NOT TimesFM.  "
            "Re-run with Python 3.10/3.11 + timesfm installed for real forecasts."
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Precompute 30-day forecasts (TimesFM or seasonal baseline)."
    )
    parser.add_argument(
        "--price-dir",
        type=Path,
        default=ROOT / "sample_data" / "price_history",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=ROOT / "sample_data" / "forecasts",
    )
    parser.add_argument(
        "--method",
        choices=["auto", "timesfm", "baseline"],
        default="auto",
        help=(
            "auto: use TimesFM if available, else baseline. "
            "baseline: force seasonal_naive_baseline (honest fallback). "
            "timesfm: force TimesFM (will fail if not installed)."
        ),
    )
    parser.add_argument(
        "--model",
        default="google/timesfm-2.0-500m-pytorch",
        help="HuggingFace model ID for TimesFM 2.0 PyTorch variant.",
    )
    args = parser.parse_args()
    main(args.price_dir, args.out_dir, args.method, args.model)
