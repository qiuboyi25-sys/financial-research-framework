#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Generate a self-contained HTML factor-analysis report from a factor panel."""

from __future__ import annotations

import argparse
import base64
import html
import io
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

import matplotlib
import numpy as np
import pandas as pd

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib import font_manager  # noqa: E402

from factors.evaluation import (  # noqa: E402
    analyze_factors as analyze_factor_panel,
)
from factors.evaluation import (
    normalize_factor_panel,
)

META_COLS = {
    "fwd_ret",
    "layer",
    "close",
    "stock_code",
    "order_book_id",
    "date",
    "symbol",
    "name",
    "full_name",
}


def _setup_chinese_font() -> None:
    candidates = [
        "Microsoft YaHei",
        "SimHei",
        "PingFang SC",
        "Noto Sans CJK SC",
        "Source Han Sans SC",
        "Arial Unicode MS",
    ]
    available = {f.name for f in font_manager.fontManager.ttflist}
    for name in candidates:
        if name in available:
            plt.rcParams["font.sans-serif"] = [name, "DejaVu Sans"]
            plt.rcParams["axes.unicode_minus"] = False
            return
    plt.rcParams["axes.unicode_minus"] = False


_setup_chinese_font()


def _fig_to_base64(fig: plt.Figure, dpi: int = 120) -> str:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=dpi, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    buf.seek(0)
    return base64.b64encode(buf.read()).decode("ascii")


def _pct(x: Any, digits: int = 2) -> str:
    if x is None or (isinstance(x, float) and (np.isnan(x) or np.isinf(x))):
        return "—"
    try:
        return f"{float(x) * 100:.{digits}f}%"
    except Exception:
        return "—"


def _num(x: Any, digits: int = 2) -> str:
    if x is None or (isinstance(x, float) and (np.isnan(x) or np.isinf(x))):
        return "—"
    try:
        return f"{float(x):.{digits}f}"
    except Exception:
        return "—"


def normalize_panel(panel: pd.DataFrame) -> pd.DataFrame:
    """Ensure MultiIndex (date, order_book_id)."""
    return normalize_factor_panel(panel)


def infer_factors(panel: pd.DataFrame, factors: Optional[Sequence[str]] = None) -> List[str]:
    if factors:
        missing = [f for f in factors if f not in panel.columns]
        if missing:
            raise KeyError(f"factors not in panel: {missing}")
        return list(factors)
    out = []
    for c in panel.columns:
        if c in META_COLS:
            continue
        if not np.issubdtype(panel[c].dtype, np.number):
            continue
        out.append(c)
    if not out:
        raise ValueError("no numeric factor columns found")
    return out


def _corr_series(
    cross: pd.DataFrame, fac: str, ret_col: str, method: str
) -> float:
    s = cross[[fac, ret_col]].dropna()
    if len(s) < 5:
        return np.nan
    return float(s[fac].corr(s[ret_col], method=method))


def _ic_by_date(
    panel: pd.DataFrame,
    fac: str,
    ret_col: str,
    method: str = "pearson",
) -> pd.Series:
    dates = panel.index.get_level_values(0).unique().sort_values()
    vals = []
    idx = []
    for dt in dates:
        cross = panel.xs(dt, level=0)
        vals.append(_corr_series(cross, fac, ret_col, method))
        idx.append(dt)
    return pd.Series(vals, index=pd.DatetimeIndex(idx), name=fac)


def _group_ls_returns(
    panel: pd.DataFrame,
    fac: str,
    ret_col: str,
    n_groups: int = 5,
) -> pd.Series:
    """Monthly long-short return: top group minus bottom group (equal-weight)."""
    dates = panel.index.get_level_values(0).unique().sort_values()
    out = []
    idx = []
    for dt in dates:
        cross = panel.xs(dt, level=0)[[fac, ret_col]].dropna()
        if len(cross) < n_groups * 2:
            out.append(np.nan)
            idx.append(dt)
            continue
        try:
            q = pd.qcut(cross[fac].rank(method="first"), n_groups, labels=False)
        except ValueError:
            out.append(np.nan)
            idx.append(dt)
            continue
        long_r = cross.loc[q == n_groups - 1, ret_col].mean()
        short_r = cross.loc[q == 0, ret_col].mean()
        out.append(float(long_r - short_r))
        idx.append(dt)
    return pd.Series(out, index=pd.DatetimeIndex(idx), name=fac)


def _nav_from_returns(r: pd.Series) -> pd.Series:
    s = r.dropna()
    if s.empty:
        return s
    return (1.0 + s).cumprod()


def _summarize_ic(ic: pd.Series) -> Dict[str, float]:
    x = ic.dropna()
    if len(x) < 3:
        return {
            "ic_mean": np.nan,
            "ic_std": np.nan,
            "icir": np.nan,
            "ic_pos_ratio": np.nan,
            "n_months": float(len(x)),
        }
    mu = float(x.mean())
    sd = float(x.std(ddof=0))
    return {
        "ic_mean": mu,
        "ic_std": sd,
        "icir": mu / sd if sd > 0 else np.nan,
        "ic_pos_ratio": float((x > 0).mean()),
        "n_months": float(len(x)),
    }


def _legacy_analyze_factors(
    panel: pd.DataFrame,
    factors: Optional[Sequence[str]] = None,
    fwd_ret_col: str = "fwd_ret",
    layer_col: Optional[str] = "layer",
    n_groups: int = 5,
    ic_method: str = "both",
) -> Tuple[pd.DataFrame, Dict[str, pd.DataFrame], Dict[str, pd.Series]]:
    """
    Returns
    -------
    summary : DataFrame
        One row per (layer, factor). layer='ALL' for full sample.
    ic_panels : dict
        Keys like 'ALL|pearson|iv' -> IC series
    ls_navs : dict
        Keys like 'ALL|iv' -> cumulative long-short NAV
    """
    df = normalize_panel(panel)
    if fwd_ret_col not in df.columns:
        raise KeyError(f"missing fwd_ret_col={fwd_ret_col}")
    facs = infer_factors(df, factors)
    use_layer = layer_col and layer_col in df.columns

    scopes: List[Tuple[str, pd.DataFrame]] = [("ALL", df)]
    if use_layer:
        for ly in sorted(df[layer_col].dropna().astype(str).unique()):
            scopes.append((ly, df[df[layer_col].astype(str) == ly]))

    methods = []
    if ic_method in ("pearson", "both"):
        methods.append("pearson")
    if ic_method in ("spearman", "both"):
        methods.append("spearman")
    if not methods:
        methods = ["pearson"]

    rows = []
    ic_panels: Dict[str, pd.DataFrame] = {}
    ls_navs: Dict[str, pd.Series] = {}

    for scope_name, sub in scopes:
        for fac in facs:
            coverage = float(sub[[fac, fwd_ret_col]].dropna().shape[0] / max(len(sub), 1))
            row: Dict[str, Any] = {
                "layer": scope_name,
                "factor": fac,
                "coverage": coverage,
            }
            for method in methods:
                ic = _ic_by_date(sub, fac, fwd_ret_col, method=method)
                key = f"{scope_name}|{method}|{fac}"
                ic_panels[key] = ic
                stats = _summarize_ic(ic)
                prefix = "ic" if method == "pearson" else "rank_ic"
                row[f"{prefix}_mean"] = stats["ic_mean"]
                row[f"{prefix}_std"] = stats["ic_std"]
                row[f"{prefix}ir"] = stats["icir"]
                row[f"{prefix}_pos_ratio"] = stats["ic_pos_ratio"]
                row["n_months"] = stats["n_months"]

            ls = _group_ls_returns(sub, fac, fwd_ret_col, n_groups=n_groups)
            nav = _nav_from_returns(ls)
            ls_navs[f"{scope_name}|{fac}"] = nav
            if len(ls.dropna()) >= 3:
                # annualize approx by periods/year ~ 12 for monthly
                mu = float(ls.dropna().mean())
                row["ls_ann"] = (1 + mu) ** 12 - 1
            else:
                row["ls_ann"] = np.nan
            rows.append(row)

    summary = pd.DataFrame(rows)
    # sort ALL by |icir| then factor
    if "icir" in summary.columns:
        summary["_abs"] = summary["icir"].abs()
        summary = summary.sort_values(
            ["layer", "_abs", "factor"], ascending=[True, False, True]
        ).drop(columns="_abs")
    return summary.reset_index(drop=True), ic_panels, ls_navs


def analyze_factors(
    panel: pd.DataFrame,
    factors: Optional[Sequence[str]] = None,
    fwd_ret_col: str = "fwd_ret",
    layer_col: Optional[str] = "layer",
    n_groups: int = 5,
    ic_method: str = "both",
) -> Tuple[pd.DataFrame, Dict[str, pd.Series], Dict[str, pd.Series]]:
    """调用框架评价内核，并保持原报告生成器的返回契约。"""
    result = analyze_factor_panel(
        panel,
        factors=factors,
        fwd_ret_col=fwd_ret_col,
        layer_col=layer_col,
        n_groups=n_groups,
        ic_method=ic_method,
    )
    summary = result.summary.rename(
        columns={
            "ic_positive_ratio": "ic_pos_ratio",
            "rank_ic_positive_ratio": "rank_ic_pos_ratio",
            "long_short_ann_return": "ls_ann",
            "n_periods": "n_months",
        }
    )
    return summary, result.ic_series, result.long_short_nav


def _plot_ic_grid(
    ic_panels: Dict[str, pd.Series],
    factor_names: Sequence[str],
    scope: str = "ALL",
    method: str = "pearson",
) -> Optional[str]:
    keys = [f"{scope}|{method}|{f}" for f in factor_names if f"{scope}|{method}|{f}" in ic_panels]
    if not keys:
        return None
    n = len(keys)
    ncols = 2
    nrows = int(np.ceil(n / ncols))
    fig, axes = plt.subplots(nrows, ncols, figsize=(10, 2.6 * nrows), squeeze=False)
    for i, key in enumerate(keys):
        ax = axes[i // ncols][i % ncols]
        s = ic_panels[key].dropna()
        fac = key.split("|")[-1]
        ax.plot(s.index, s.values, color="#1f4e79", linewidth=1.0)
        ax.axhline(0, color="#999", linewidth=0.8)
        ax.set_title(f"IC — {fac}", fontsize=10)
        ax.grid(True, alpha=0.25)
    for j in range(n, nrows * ncols):
        axes[j // ncols][j % ncols].axis("off")
    fig.suptitle(f"IC 时序（{scope} / {method}）", fontsize=12, y=1.01)
    fig.tight_layout()
    return _fig_to_base64(fig)


def _plot_ls_nav(
    ls_navs: Dict[str, pd.Series],
    factor_names: Sequence[str],
    scope: str = "ALL",
) -> Optional[str]:
    fig, ax = plt.subplots(figsize=(10, 3.8))
    plotted = 0
    for fac in factor_names:
        key = f"{scope}|{fac}"
        if key not in ls_navs:
            continue
        nav = ls_navs[key].dropna()
        if nav.empty:
            continue
        ax.plot(nav.index, nav.values, label=fac, linewidth=1.2)
        plotted += 1
    if plotted == 0:
        plt.close(fig)
        return None
    ax.set_title(f"分组多空累计净值（{scope}）", fontsize=12)
    ax.set_ylabel("净值")
    ax.legend(loc="upper left", fontsize=8, frameon=False, ncol=2)
    ax.grid(True, alpha=0.25)
    fig.autofmt_xdate()
    return _fig_to_base64(fig)


def build_factor_report_html(
    summary: pd.DataFrame,
    ic_panels: Dict[str, pd.Series],
    ls_navs: Dict[str, pd.Series],
    title: str = "因子分析报告",
    subtitle: str = "",
    notes: str = "",
    top_n_charts: int = 6,
    date_range: str = "",
) -> str:
    all_sum = summary[summary["layer"] == "ALL"].copy()
    if all_sum.empty:
        all_sum = summary.copy()

    # top factors by |icir| or |rank_icir|
    score_col = "icir" if "icir" in all_sum.columns else "rank_icir"
    if score_col in all_sum.columns:
        top_facs = (
            all_sum.assign(_a=all_sum[score_col].abs())
            .sort_values("_a", ascending=False)["factor"]
            .head(top_n_charts)
            .tolist()
        )
    else:
        top_facs = all_sum["factor"].head(top_n_charts).tolist()

    method_for_plot = "pearson" if any("|pearson|" in k for k in ic_panels) else "spearman"
    ic_img = _plot_ic_grid(ic_panels, top_facs, scope="ALL", method=method_for_plot)
    ls_img = _plot_ls_nav(ls_navs, top_facs, scope="ALL")

    # summary table columns
    display_cols = [
        ("factor", "因子", "str"),
        ("coverage", "覆盖率", "pct"),
        ("ic_mean", "IC均值", "num"),
        ("icir", "ICIR", "num"),
        ("icir_ann", "年化ICIR", "num"),
        ("rank_ic_mean", "RankIC", "num"),
        ("rank_icir", "RankICIR", "num"),
        ("rank_icir_ann", "年化RankICIR", "num"),
        ("ic_pos_ratio", "IC>0占比", "pct"),
        ("ls_ann", "多空年化", "pct"),
        ("n_months", "期数", "num0"),
    ]

    def fmt(kind: str, v: Any) -> str:
        if kind == "str":
            return html.escape(str(v)) if v is not None else "—"
        if kind == "pct":
            return _pct(v)
        if kind == "num0":
            if v is None or (isinstance(v, float) and np.isnan(v)):
                return "—"
            return f"{int(v)}"
        return _num(v)

    header = "".join(
        f"<th>{html.escape(label)}</th>"
        for key, label, _ in display_cols
        if key == "factor" or key in all_sum.columns
    )
    body_rows = []
    for _, r in all_sum.iterrows():
        cells = []
        for key, _label, kind in display_cols:
            if key != "factor" and key not in all_sum.columns:
                continue
            cells.append(f"<td>{fmt(kind, r.get(key))}</td>")
        body_rows.append("<tr>" + "".join(cells) + "</tr>")

    layer_section = ""
    layers = [x for x in summary["layer"].unique() if x != "ALL"]
    if layers and "icir" in summary.columns:
        # pivot layer x factor icir
        piv = summary[summary["layer"] != "ALL"].pivot_table(
            index="factor", columns="layer", values="icir", aggfunc="first"
        )
        lh = "<th>因子</th>" + "".join(f"<th>{html.escape(str(c))}</th>" for c in piv.columns)
        lb = []
        for fac, row in piv.iterrows():
            lb.append(
                "<tr><td>"
                + html.escape(str(fac))
                + "</td>"
                + "".join(f"<td>{_num(v)}</td>" for v in row.values)
                + "</tr>"
            )
        layer_section = f"""
<section>
  <h2>分层 ICIR</h2>
  <table class="data">
    <thead><tr>{lh}</tr></thead>
    <tbody>{''.join(lb)}</tbody>
  </table>
</section>
"""

    ic_section = (
        f'<div class="chart"><img src="data:image/png;base64,{ic_img}" alt="ic"/></div>'
        if ic_img
        else '<p class="muted">无 IC 时序图</p>'
    )
    ls_section = (
        f'<div class="chart"><img src="data:image/png;base64,{ls_img}" alt="ls"/></div>'
        if ls_img
        else '<p class="muted">无多空净值图</p>'
    )
    notes_html = (
        f'<section><h2>备注</h2><p class="notes">{html.escape(notes)}</p></section>'
        if notes
        else ""
    )
    generated = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>{html.escape(title)}</title>
<style>
  :root {{
    --bg: #f6f7f9; --card: #ffffff; --text: #1a1d21; --muted: #5c6570;
    --line: #e4e7eb; --accent: #1f4e79; --accent-soft: #e8eef5;
  }}
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0; font-family: "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif;
    background: var(--bg); color: var(--text); line-height: 1.5;
  }}
  .wrap {{ max-width: 1100px; margin: 0 auto; padding: 32px 20px 64px; }}
  header {{
    background: linear-gradient(135deg, #1f4e79 0%, #2f6f9f 100%);
    color: #fff; padding: 28px 24px; border-radius: 12px; margin-bottom: 24px;
  }}
  header h1 {{ margin: 0 0 6px; font-size: 1.6rem; font-weight: 650; }}
  header .sub {{ opacity: 0.9; font-size: 0.95rem; }}
  header .meta {{ margin-top: 12px; font-size: 0.85rem; opacity: 0.85; }}
  section {{
    background: var(--card); border: 1px solid var(--line);
    border-radius: 12px; padding: 20px 22px; margin-bottom: 18px;
  }}
  h2 {{ margin: 0 0 14px; font-size: 1.1rem; color: var(--accent); }}
  .chart img {{ width: 100%; height: auto; display: block; }}
  table.data {{ width: 100%; border-collapse: collapse; font-size: 0.88rem; }}
  table.data th, table.data td {{
    border-bottom: 1px solid var(--line); padding: 7px 8px; text-align: right;
  }}
  table.data th:first-child, table.data td:first-child {{ text-align: left; }}
  table.data thead th {{ background: var(--accent-soft); color: var(--accent); }}
  .muted {{ color: var(--muted); font-size: 0.9rem; }}
  p.notes {{ white-space: pre-wrap; margin: 0; }}
  footer {{ text-align: center; color: var(--muted); font-size: 0.8rem; margin-top: 12px; }}
</style>
</head>
<body>
<div class="wrap">
  <header>
    <h1>{html.escape(title)}</h1>
    <div class="sub">{html.escape(subtitle)}</div>
    <div class="meta">
      区间：{html.escape(date_range or "—")} &nbsp;|&nbsp;
      生成：{html.escape(generated)} &nbsp;|&nbsp;
      因子数：{len(all_sum)}
    </div>
  </header>

  <section>
    <h2>因子汇总（全样本）</h2>
    <p class="muted">按 |ICIR| 降序；多空为五分组最高组减最低组等权收益年化近似。</p>
    <table class="data">
      <thead><tr>{header}</tr></thead>
      <tbody>{''.join(body_rows)}</tbody>
    </table>
  </section>

  {layer_section}

  <section>
    <h2>IC 时序（|ICIR| Top {len(top_facs)}）</h2>
    {ic_section}
  </section>

  <section>
    <h2>分组多空净值（|ICIR| Top {len(top_facs)}）</h2>
    {ls_section}
  </section>

  {notes_html}

  <footer>Generated by Financial Research Framework · self-contained HTML</footer>
</div>
</body>
</html>
"""


def write_factor_report(
    panel: pd.DataFrame,
    output_path: Union[str, Path],
    title: str = "因子分析报告",
    subtitle: str = "",
    notes: str = "",
    factors: Optional[Sequence[str]] = None,
    fwd_ret_col: str = "fwd_ret",
    layer_col: Optional[str] = "layer",
    n_groups: int = 5,
    ic_method: str = "both",
    top_n_charts: int = 6,
) -> Path:
    df = normalize_panel(panel)
    dates = df.index.get_level_values(0)
    date_range = f"{pd.Timestamp(dates.min()).date()} ~ {pd.Timestamp(dates.max()).date()}"
    summary, ic_panels, ls_navs = analyze_factors(
        df,
        factors=factors,
        fwd_ret_col=fwd_ret_col,
        layer_col=layer_col,
        n_groups=n_groups,
        ic_method=ic_method,
    )
    html_str = build_factor_report_html(
        summary,
        ic_panels,
        ls_navs,
        title=title,
        subtitle=subtitle,
        notes=notes,
        top_n_charts=top_n_charts,
        date_range=date_range,
    )
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html_str, encoding="utf-8")
    # also dump summary csv next to html
    summary.to_csv(out.with_suffix(".csv"), index=False)
    return out.resolve()


def _demo_panel(n_dates: int = 36, n_assets: int = 80) -> pd.DataFrame:
    rng = np.random.default_rng(42)
    dates = pd.bdate_range("2021-01-29", periods=n_dates * 2, freq="BME")[:n_dates]
    assets = [f"A{i:03d}" for i in range(n_assets)]
    rows = []
    for dt in dates:
        for a in assets:
            f1 = rng.normal()
            f2 = rng.normal()
            noise = rng.normal(scale=0.02)
            fwd = 0.004 * f1 - 0.003 * f2 + noise
            layer = "debt" if f1 < -0.3 else ("equity" if f1 > 0.3 else "neutral")
            rows.append(
                {
                    "date": dt,
                    "order_book_id": a,
                    "alpha": f1,
                    "beta_fac": f2,
                    "noise_fac": rng.normal(),
                    "fwd_ret": fwd,
                    "layer": layer,
                }
            )
    return pd.DataFrame(rows).set_index(["date", "order_book_id"])


def main(argv: Optional[Sequence[str]] = None) -> None:
    parser = argparse.ArgumentParser(description="Factor analysis HTML report")
    parser.add_argument("--demo", action="store_true", help="run synthetic demo")
    parser.add_argument("-o", "--output", default="outputs/factor_demo.html")
    parser.add_argument("--panel", default=None, help="parquet path to factor panel")
    parser.add_argument("--title", default="因子分析报告")
    parser.add_argument("--subtitle", default="")
    parser.add_argument("--notes", default="")
    parser.add_argument("--fwd-ret-col", default="fwd_ret")
    parser.add_argument("--layer-col", default="layer")
    parser.add_argument("--no-layer", action="store_true")
    args = parser.parse_args(argv)

    if args.demo:
        panel = _demo_panel()
        notes = args.notes or "演示数据：合成因子，非实盘。"
    elif args.panel:
        panel = pd.read_parquet(args.panel)
        notes = args.notes
    else:
        parser.error("请使用 --demo 或 --panel path.parquet")

    path = write_factor_report(
        panel,
        args.output,
        title=args.title,
        subtitle=args.subtitle or ("演示面板" if args.demo else Path(args.panel).name),
        notes=notes,
        fwd_ret_col=args.fwd_ret_col,
        layer_col=None if args.no_layer else args.layer_col,
    )
    print(path)


if __name__ == "__main__":
    main()
