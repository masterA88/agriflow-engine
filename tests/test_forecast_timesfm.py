"""Unit contract for TimesFM 2.5 point and quantile channel mapping."""
from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from analysis import forecast_timesfm


def test_timesfm_uses_dedicated_point_and_ordered_quantile_channels(monkeypatch) -> None:
    """Channel 0 is not P10; public point output and channels 1/9 are used."""
    quantiles = np.zeros((1, 2, 10), dtype=float)
    quantiles[0, :, 0] = [99.0, 98.0]  # Must never appear in the artifact.
    quantiles[0, :, 1] = [10.0, 11.0]
    quantiles[0, :, 5] = [20.0, 21.0]
    quantiles[0, :, 9] = [30.0, 31.0]

    class FakeModel:
        def forecast(self, **_kwargs):
            return np.array([[20.0, 21.0]]), quantiles

    monkeypatch.setattr(forecast_timesfm, "_load_timesfm_model", lambda _path: FakeModel())
    output = forecast_timesfm._timesfm_forecast(
        [(dt.date(2026, 8, 15), 25_000.0)], horizon=2, model_path="fake"
    )

    assert output == [
        {"date": "2026-08-16", "point": 20.0, "p10": 10.0, "p90": 30.0},
        {"date": "2026-08-17", "point": 21.0, "p10": 11.0, "p90": 31.0},
    ]
