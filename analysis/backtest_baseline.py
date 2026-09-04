"""
analysis/backtest_baseline.py  --  Reproducible holdout backtest of the DEPLOYED
seasonal-naive forecaster (the method actually served by the dashboard when
TimesFM is unavailable).

WHY THIS EXISTS:
    The deployed forecast_all.json is produced by `_seasonal_naive_forecast`
    (analysis/forecast_timesfm.py).  This script measures that exact function's
    accuracy on a real holdout so the proposal can cite a reproducible MAPE for
    what is actually running -- not an unbacked number.

METHOD (honest, leakage-free):
    For every (commodity, city) daily series in sample_data/price_history/:
      1. Hold out the LAST `horizon` calendar days as the test window.
      2. Train = everything strictly before the holdout.
      3. Forecast with the SAME _seasonal_naive_forecast used in production.
      4. Align forecast dates to actual observed test dates and score.

    Metrics per series: MAPE, MAE, RMSE, and 80%-CI coverage (share of actuals
    inside [p10, p90]).  Aggregated per commodity (mean over cities) and overall.

USAGE:
    python analysis/backtest_baseline.py                 # 30-day holdout, all series
    python analysis/backtest_baseline.py --horizon 14
    python analysis/backtest_baseline.py --json analysis/output/backtest_baseline.json

OUTPUT:
    - prints per-commodity + overall table
    - optional JSON dump of full results
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from db.price_ingest import load_source_price_history_csvs, select_active_prices
from forecast_timesfm import _seasonal_naive_forecast  # the deployed baseline

PRICE_DIR = ROOT / "sample_data" / "price_history"


def _load_active_series(price_dir: Path = PRICE_DIR):
    """Load source-aware active prices and group one date-sorted series per (commodity, city).

    This is the exact public-loader sequence that produces ``forecast_all.json``
    (``load_source_price_history_csvs`` followed by ``select_active_prices``), so
    the seasonal-naive baseline is measured on the same cleaned Siskaperbapo-first
    active data served by the dashboard.
    """
    source_records = load_source_price_history_csvs(Path(price_dir))
    active_records = select_active_prices(source_records)
    grouped: dict[str, dict[str, list]] = defaultdict(lambda: defaultdict(list))
    for row in active_records:
        grouped[row["commodity_code"]][str(row["city_id"])].append(
            (row["date"], float(row["price_per_kg"]))
        )
    return {
        commodity: {
            city_id: sorted(points, key=lambda point: point[0])
            for city_id, points in by_city.items()
        }
        for commodity, by_city in grouped.items()
    }


def _score(series, horizon: int, conformal: bool = True):
    """Holdout-backtest one series. Returns metrics dict or None if too short."""
    if len(series) < horizon + 60:
        return None
    train = series[:-horizon]
    test = series[-horizon:]                       # (date, actual)
    fc = _seasonal_naive_forecast(train, horizon=horizon, conformal=conformal)
    fc_by_date = {datetime.date.fromisoformat(r["date"]): r for r in fc}

    pairs = []
    cov_hits = 0
    for d, actual in test:
        r = fc_by_date.get(d)
        if r is None or actual <= 0:
            continue
        pred = r["point"]
        pairs.append((actual, pred))
        if r["p10"] <= actual <= r["p90"]:
            cov_hits += 1
    if not pairs:
        return None
    a = np.array([p[0] for p in pairs], dtype=float)
    f = np.array([p[1] for p in pairs], dtype=float)
    mape = float(np.mean(np.abs((a - f) / a)) * 100)
    mae = float(np.mean(np.abs(a - f)))
    rmse = float(np.sqrt(np.mean((a - f) ** 2)))
    cov = float(cov_hits / len(pairs) * 100)
    return {"n": len(pairs), "mape": mape, "mae": mae, "rmse": rmse, "coverage_80": cov}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--horizon", type=int, default=30)
    ap.add_argument("--json", default=None, help="optional path to dump full results")
    ap.add_argument("--no-conformal", action="store_true",
                    help="use the v1.0 same-month MAD band instead of the conformal band")
    args = ap.parse_args()
    conformal = not args.no_conformal

    active = _load_active_series(PRICE_DIR)

    per_commodity: dict[str, list[dict]] = defaultdict(list)
    detail = []
    for comm, by_city in sorted(active.items()):
        for cid, series in sorted(by_city.items()):
            m = _score(series, args.horizon)
            if m is None:
                continue
            m2 = {"commodity": comm, "city_id": cid, **m}
            per_commodity[comm].append(m2)
            detail.append(m2)

    # aggregate per commodity (mean over cities) then overall (mean over commodities)
    print(f"\nHoldout backtest of DEPLOYED seasonal-naive forecaster "
          f"(horizon={args.horizon} days, leakage-free, interval="
          f"{'split_conformal_rolling_origin' if conformal else 'same_month_mad'})\n")
    print(f"  {'Commodity':<16}{'series':>7}{'MAPE%':>9}{'MAE(Rp)':>11}{'RMSE(Rp)':>11}{'CI80%':>8}")
    print("  " + "-" * 60)
    comm_means = []
    for comm in sorted(per_commodity):
        rows = per_commodity[comm]
        mape = np.mean([r["mape"] for r in rows])
        mae = np.mean([r["mae"] for r in rows])
        rmse = np.mean([r["rmse"] for r in rows])
        cov = np.mean([r["coverage_80"] for r in rows])
        comm_means.append(mape)
        print(f"  {comm:<16}{len(rows):>7}{mape:>9.1f}{mae:>11,.0f}{rmse:>11,.0f}{cov:>7.0f}%")
    print("  " + "-" * 60)
    overall_mape = float(np.mean([r["mape"] for r in detail]))
    overall_cov = float(np.mean([r["coverage_80"] for r in detail]))
    print(f"  {'OVERALL (per-series mean)':<40}{overall_mape:>9.1f}{'':22}{overall_cov:>7.0f}%")
    print(f"\n  Series evaluated: {len(detail)} | commodities: {len(per_commodity)}\n")

    if args.json:
        os.makedirs(os.path.dirname(args.json), exist_ok=True)
        payload = {
            "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "method": "seasonal_naive_baseline",
            "interval_method": "split_conformal_rolling_origin" if conformal else "same_month_mad",
            "horizon_days": args.horizon,
            "holdout": "last N calendar days, leakage-free",
            "overall_mape_pct": round(overall_mape, 2),
            "overall_ci80_coverage_pct": round(overall_cov, 1),
            "per_commodity": {
                c: {
                    "mape_pct": round(float(np.mean([r["mape"] for r in rows])), 2),
                    "mae_idr": round(float(np.mean([r["mae"] for r in rows])), 0),
                    "rmse_idr": round(float(np.mean([r["rmse"] for r in rows])), 0),
                    "ci80_coverage_pct": round(float(np.mean([r["coverage_80"] for r in rows])), 1),
                    "n_series": len(rows),
                }
                for c, rows in per_commodity.items()
            },
            "detail": detail,
        }
        with open(args.json, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2)
        print(f"  Wrote {args.json}")


if __name__ == "__main__":
    main()
