"""
Build the interactive county map from the pipeline's forecast summary.

Reads:
  forecast_summary CSV  (county_fips, period, prob_below_P20, calibrated_median,
                         calibrated_p10, calibrated_p90, ERA5L_P20_threshold)
  LOYO metrics CSV      (optional; county_fips, period, season, cal_MSESS)
Writes:
  one self-contained HTML file (map_template.html with the numbers filled in)
"""

import json
import math
from pathlib import Path

import pandas as pd

TEMPLATE = Path(__file__).with_name("map_template.html")

LAYER_LABEL = {"sm20": "Top 20 cm", "sm100": "Top 100 cm (root zone)"}

DEFAULT_PERIODS = {
    "Week 1": (1, 7),
    "Week 2": (8, 14),
    "Week 3-4": (15, 28),
    "Week 5-6": (29, 42),
}

SEASON_OF_MONTH = {12: "DJF", 1: "DJF", 2: "DJF", 3: "MAM", 4: "MAM", 5: "MAM",
                   6: "JJA", 7: "JJA", 8: "JJA", 9: "SON", 10: "SON", 11: "SON"}


def _num(x, scale=1.0, nd=4):
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(v) else round(v * scale, nd)


def _date_range(init, first_day, last_day, day_offset):
    # lead day d covers calendar day init + d - 1 + (day_offset + 1);
    # with the pipeline's default ERA5_DAY_OFFSET = -1 that is init + d - 1
    shift = day_offset + 1
    a = init + pd.Timedelta(days=first_day - 1 + shift)
    b = init + pd.Timedelta(days=last_day - 1 + shift)
    if a.month == b.month:
        return f"{a:%b} {a.day}–{b.day}"
    return f"{a:%b} {a.day}–{b:%b} {b.day}"


def build_map(summary_csv, out_html, target, model_date,
              metrics_csv=None, periods=None, era5_day_offset=-1,
              template=TEMPLATE):
    periods = periods or DEFAULT_PERIODS
    init = pd.Timestamp(model_date)

    s = pd.read_csv(summary_csv, dtype={"county_fips": str})
    s["county_fips"] = s["county_fips"].str.zfill(5)

    skill = {}
    if metrics_csv is not None and Path(metrics_csv).exists():
        m = pd.read_csv(metrics_csv, dtype={"county_fips": str})
        m["county_fips"] = m["county_fips"].str.zfill(5)
        if "season" in m.columns:
            m = m[m["season"] == SEASON_OF_MONTH[init.month]]
        col = "cal_MSESS" if "cal_MSESS" in m.columns else None
        if col:
            skill = {(r.county_fips, r.period): _num(getattr(r, col), nd=3)
                     for r in m.itertuples()}

    period_names = [p for p in periods if p in set(s["period"])]
    if not period_names:
        raise ValueError(f"No known periods in {summary_csv}: {sorted(set(s['period']))}")

    counties = {}
    for i, per in enumerate(period_names):
        for r in s[s["period"] == per].itertuples():
            counties.setdefault(r.county_fips, [None] * len(period_names))
            counties[r.county_fips][i] = {
                "p": _num(r.prob_below_P20, scale=100.0, nd=1),
                "med": _num(getattr(r, "calibrated_median", None)),
                "p10": _num(getattr(r, "calibrated_p10", None)),
                "p90": _num(getattr(r, "calibrated_p90", None)),
                "thr": _num(getattr(r, "ERA5L_P20_threshold", None)),
                "skill": skill.get((r.county_fips, per)),
            }

    forecast = {
        "layer": target,
        "layer_label": LAYER_LABEL.get(target, target),
        "init_date": f"{init:%b} {init.day}, {init:%Y}",
        "periods": [
            {"label": p, "dates": _date_range(init, *periods[p], era5_day_offset)}
            for p in period_names
        ],
        "counties": counties,
    }

    html = Path(template).read_text(encoding="utf-8")
    html = html.replace("/*__FORECAST__*/null", json.dumps(forecast, separators=(",", ":")))

    out_html = Path(out_html)
    out_html.parent.mkdir(parents=True, exist_ok=True)
    out_html.write_text(html, encoding="utf-8")
    print(f"Map written: {out_html}  ({len(counties)} counties, {len(period_names)} periods)")
    return out_html
