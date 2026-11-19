"""
Build the interactive county map from the pipeline's forecast summary.

Reads:
  forecast_summary CSV  (county_fips, period, prob_below_P20, calibrated_median,
                         calibrated_p10, calibrated_p90, ERA5L_P20_threshold)
  LOYO metrics CSV      (optional; county_fips, period, season, cal_MSESS, cal_ACC)
                        -- the seasonally pooled test from the Section 17 library
  single-date metrics   (optional; county_fips, period, calibrated_correlation)
                        -- the single-date test for this forecast's start date
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
              template=TEMPLATE, single_metrics_csv=None, report_url=None,
              single_date=None):
    periods = periods or DEFAULT_PERIODS
    init = pd.Timestamp(model_date)

    s = pd.read_csv(summary_csv, dtype={"county_fips": str})
    s["county_fips"] = s["county_fips"].str.zfill(5)

    season = SEASON_OF_MONTH[init.month]
    skill, acc, single = {}, {}, {}
    if metrics_csv is not None and Path(metrics_csv).exists():
        m = pd.read_csv(metrics_csv, dtype={"county_fips": str})
        m["county_fips"] = m["county_fips"].str.zfill(5)
        if "season" in m.columns:
            m = m[m["season"] == season]
        if "cal_MSESS" in m.columns:
            skill = {(r.county_fips, r.period): _num(r.cal_MSESS, nd=3) for r in m.itertuples()}
        if "cal_ACC" in m.columns:
            acc = {(r.county_fips, r.period): _num(r.cal_ACC, nd=3) for r in m.itertuples()}
    if single_metrics_csv is not None and Path(single_metrics_csv).exists():
        sd = pd.read_csv(single_metrics_csv, dtype={"county_fips": str})
        sd["county_fips"] = sd["county_fips"].str.zfill(5)
        single = {(r.county_fips, r.period): _num(r.calibrated_correlation, nd=3) for r in sd.itertuples()}
        if single_date is None and "reforecast_date" in sd.columns and len(sd):
            single_date = str(sd["reforecast_date"].iloc[0])

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
                "acc": acc.get((r.county_fips, per)),
                "single": single.get((r.county_fips, per)),
            }

    forecast = {
        "layer": target,
        "layer_label": LAYER_LABEL.get(target, target),
        "init_date": f"{init:%b} {init.day}, {init:%Y}",
        "season": season,
        "single_date": (f"{pd.Timestamp(single_date):%b} {pd.Timestamp(single_date).day}, "
                        f"{pd.Timestamp(single_date):%Y}") if single_date else None,
        "report": report_url,
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
