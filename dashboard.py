"""
Morpho Risk Case Study — Streamlit dashboard.
Run:  python3 -m streamlit run dashboard.py
Data: python3 etl.py
"""
from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st

# ── palette ──────────────────────────────────────────────────────────────────
BG    = "#0f1117"
BG2   = "#141824"
BG3   = "#1a2035"
BG4   = "#1e3a5f"
BDR   = "#2d3a52"
BLUE  = "#3b82f6"
BLUE_LT = "#93c5fd"
RED   = "#ef4444"
AMBER = "#f59e0b"
GREEN = "#10b981"
PURP  = "#a78bfa"
TEXT  = "#e2e8f0"
MUTED = "#94a3b8"

DATA = Path(__file__).resolve().parent / "data"

_PLOT_BASE = dict(
    template="plotly_dark",
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(14,17,23,0.6)",
    font=dict(family="Inter, system-ui, sans-serif", color=MUTED, size=11),
    margin=dict(l=12, r=12, t=44, b=12),
    legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0,
                font_size=11, bgcolor="rgba(0,0,0,0)"),
    xaxis=dict(gridcolor=BDR, zeroline=False),
    yaxis=dict(gridcolor=BDR, zeroline=False),
)

def _plot(**overrides) -> dict:
    """Merge base plot settings with caller overrides (deep-merge one level)."""
    merged = dict(_PLOT_BASE)
    for k, v in overrides.items():
        if isinstance(v, dict) and isinstance(merged.get(k), dict):
            merged[k] = {**merged[k], **v}
        else:
            merged[k] = v
    return merged

# Keep PLOT as alias for backward compat with chart() helper
PLOT = _PLOT_BASE


def _ts(x): return datetime.fromtimestamp(int(x), tz=timezone.utc)
def _fmt(v):
    if abs(v) >= 1e6: return f"${v/1e6:,.1f}M"
    if abs(v) >= 1e3: return f"${v/1e3:,.1f}k"
    return f"${v:,.2f}"


@st.cache_data
def load(name):
    p = DATA / name
    return json.loads(p.read_text()) if p.is_file() else None


def ts_df(pts, col="v"):
    if not pts: return pd.DataFrame(columns=["date", col])
    rows = [{"date": _ts(p["x"]), col: float(p["y"])} for p in pts if p.get("y") is not None]
    return pd.DataFrame(rows).sort_values("date") if rows else pd.DataFrame(columns=["date", col])


# ── CSS injection ─────────────────────────────────────────────────────────────
CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');
@import url('https://fonts.googleapis.com/css2?family=Material+Symbols+Outlined:opsz,wght,FILL,GRAD@20..48,100..700,0..1,-50..200&display=swap');

/* hide Streamlit's heading anchor-link buttons */
[data-testid="stHeadingActionElements"] { display: none !important; }

html, body, [class*="st-"], [class*="css"] { font-family: 'Inter', system-ui, sans-serif !important; }

/* hide default padding */
.block-container { padding-top: 1rem !important; padding-bottom: 2rem !important; }
[data-testid="stSidebar"] { background: #161b27 !important; border-right: 1px solid #2d3a52; }

/* ── metric cards ── */
.kpi-row { display: flex; gap: 12px; flex-wrap: wrap; margin: 0 0 16px; }
.kpi { flex: 1; min-width: 160px; background: #1a2035; border: 1px solid #2d3a52;
       border-radius: 10px; padding: 16px 20px; }
.kpi .kl { font-size: 10.5px; text-transform: uppercase; letter-spacing: .08em;
           color: #94a3b8; margin-bottom: 4px; }
.kpi .kv { font-size: 26px; font-weight: 800; line-height: 1.15; margin-bottom: 2px; }
.kpi .ks { font-size: 11.5px; color: #94a3b8; }
.red  { color: #ef4444; } .amber { color: #f59e0b; }
.green{ color: #10b981; } .blue  { color: #3b82f6; } .purple { color: #a78bfa; }

/* ── section header ── */
.sec-hdr { background: linear-gradient(90deg,#1e3a5f 0%,#141824 100%);
           border-left: 4px solid #3b82f6; padding: 9px 14px;
           border-radius: 0 6px 6px 0; margin: 20px 0 12px; }
.sec-hdr h3 { font-size: 13px; font-weight: 700; color: #e2e8f0; margin: 0; }
.sec-hdr p  { font-size: 11.5px; color: #94a3b8; margin: 2px 0 0; }

/* ── alerts ── */
.alert { border-radius: 8px; padding: 13px 16px; margin: 10px 0; font-size: 12.5px; line-height: 1.6; }
.alert b { display: block; margin-bottom: 4px; font-size: 13px; }
.alert-blue  { background: #0c1f3a; border: 1px solid #1e40af; color: #93c5fd; }
.alert-red   { background: #2d1515; border: 1px solid #7f1d1d; color: #fca5a5; }
.alert-amber { background: #2a2009; border: 1px solid #78350f; color: #fde68a; }
.alert-green { background: #0a2e1e; border: 1px solid #065f46; color: #6ee7b7; }

/* ── timeline ── */
.tl { padding: 0 0 0 8px; margin: 4px 0 16px; }
.tl-item { border-left: 2px solid #3b82f6; padding: 6px 0 12px 18px; position: relative; }
.tl-item::before { content:''; width:10px; height:10px; border-radius:50%;
                   background:#3b82f6; position:absolute; left:-6px; top:9px; }
.tl-item.red  { border-color:#ef4444; } .tl-item.red::before  { background:#ef4444; }
.tl-item.amber{ border-color:#f59e0b; } .tl-item.amber::before{ background:#f59e0b; }
.tl-item.green{ border-color:#10b981; } .tl-item.green::before{ background:#10b981; }
.tl-item.blue { border-color:#3b82f6; } .tl-item.blue::before { background:#3b82f6; }
.tl-date  { font-size:10.5px; font-weight:700; text-transform:uppercase;
            letter-spacing:.07em; color:#94a3b8; margin-bottom:2px; }
.tl-title { font-size:13px; font-weight:700; color:#e2e8f0; margin-bottom:2px; }
.tl-body  { font-size:12px; color:#94a3b8; }

/* ── badges ── */
.badge { display:inline-block; padding:2px 8px; border-radius:20px;
         font-size:11px; font-weight:600; }
.badge-red   { background:#2d1515; color:#fca5a5; }
.badge-amber { background:#2a2009; color:#fde68a; }
.badge-green { background:#0a2e1e; color:#6ee7b7; }
.badge-blue  { background:#0c1f3a; color:#93c5fd; }
.badge-gray  { background:#1e293b; color:#94a3b8; }

/* ── tables ── */
.stbl { width:100%; border-collapse:collapse; font-size:12.5px; margin:8px 0; }
.stbl thead th { background:#1e3a5f; color:#93c5fd; text-align:left;
                 padding:8px 12px; font-weight:600; font-size:11.5px;
                 text-transform:uppercase; letter-spacing:.05em; }
.stbl tbody tr:nth-child(odd)  { background:#1a2035; }
.stbl tbody tr:nth-child(even) { background:#141824; }
.stbl tbody td { padding:8px 12px; color:#e2e8f0; border-bottom:1px solid #2d3a52; }
.stbl-red  td { background:#2d1515 !important; }
.stbl-amber td{ background:#2a2009 !important; }
.stbl-green td{ background:#0a2e1e !important; }
.stbl-blue  td{ background:#0c1f3a !important; }

/* ── two-col prose ── */
.two-col { display:grid; grid-template-columns:1fr 1fr; gap:20px; margin:12px 0; }
.prose { font-size:13px; line-height:1.75; color:#e2e8f0; }
.prose p { margin-bottom:8px; }
.prose ul { padding-left:18px; margin-bottom:8px; }
.prose li { margin-bottom:4px; color:#e2e8f0; }
.prose strong { color:#fff; }

/* cascade box */
.cascade { background:#141824; border:1px solid #2d3a52; border-radius:8px;
           padding:16px; font-family:monospace; font-size:13px; color:#e2e8f0;
           line-height:2; margin:12px 0; }

/* sidebar nav */
.sidebar-logo { font-size:20px; font-weight:800; color:#3b82f6;
                letter-spacing:-0.5px; margin-bottom:2px; }
.sidebar-sub { font-size:11px; color:#94a3b8; text-transform:uppercase;
               letter-spacing:.08em; margin-bottom:12px; }

[data-testid="stRadio"] label { font-size: 13px !important; }
[data-testid="stRadio"] { gap: 2px !important; }

/* ── sources footer ── */
.src-footer { margin-top: 40px; padding: 12px 16px; border-top: 1px solid #2d3a52;
              font-size: 11px; color: #475569; line-height: 1.8; }
.src-footer strong { color: #64748b; font-weight: 600; }
.src-item { display: inline-block; margin-right: 18px; }
.src-item::before { content: "↳ "; color: #3b82f6; }
</style>
"""

# ── helpers ───────────────────────────────────────────────────────────────────
def kpi_row(*items):
    cards = ""
    for label, val, sub, color in items:
        cards += f'<div class="kpi"><div class="kl">{label}</div><div class="kv {color}">{val}</div><div class="ks">{sub}</div></div>'
    st.markdown(f'<div class="kpi-row">{cards}</div>', unsafe_allow_html=True)


def sec_hdr(title, sub=""):
    sub_html = f"<p>{sub}</p>" if sub else ""
    st.markdown(f'<div class="sec-hdr"><h3>{title}</h3>{sub_html}</div>', unsafe_allow_html=True)


def alert(kind, title, body):
    st.markdown(f'<div class="alert alert-{kind}"><b>{title}</b>{body}</div>', unsafe_allow_html=True)


def tl_item(color, date, title, body):
    return f'''<div class="tl-item {color}">
  <div class="tl-date">{date}</div>
  <div class="tl-title">{title}</div>
  <div class="tl-body">{body}</div>
</div>'''


def badge(kind, text):
    return f'<span class="badge badge-{kind}">{text}</span>'


def _sources_footer(*sources):
    """Render a muted sources footnote at the bottom of a page."""
    items = "".join(f'<span class="src-item">{s}</span>' for s in sources)
    st.markdown(
        f'<div class="src-footer"><strong>Sources</strong><br>{items}</div>',
        unsafe_allow_html=True,
    )


def chart(fig, height=400):
    fig.update_layout(**PLOT, height=height)
    st.plotly_chart(fig, use_container_width=True)


# ── real price data from ETL ──────────────────────────────────────────────────
@st.cache_data
def price_data() -> pd.DataFrame:
    """Load actual on-chain price history from collateral_prices.json (Nov 2025)."""
    raw = load("collateral_prices.json") or []
    frames = {}
    for asset in raw:
        sym = asset["symbol"]
        pts = sorted(asset["historicalPriceUsd"], key=lambda p: p["x"])
        frames[sym] = {_ts(p["x"]): p["y"] for p in pts}

    all_dates = sorted({d for f in frames.values() for d in f})
    df = pd.DataFrame({"date": all_dates})
    for sym, mapping in frames.items():
        df[sym] = df["date"].map(mapping)
    return df


@st.cache_data
def price_stats() -> dict:
    """Compute max-drawdown stats per asset from real price data.

    Uses $1.00 as the assumed peg start (not the API's pre-collapse oracle/share-price value,
    which shows ~$1.26 for xUSD due to yield accrual before the depeg).
    """
    df = price_data()
    stats = {}
    for sym in ["xUSD", "sdeUSD", "deUSD"]:
        col = df[sym].dropna() if sym in df.columns else pd.Series(dtype=float)
        if len(col) < 2:
            continue
        peg = 1.00   # intended peg for all three assets
        low = col.min()
        drawdown_pct = (low - peg) / peg * 100
        stats[sym] = {"start": peg, "low": low, "drawdown_pct": drawdown_pct}
    return stats


@st.cache_data
def market_snapshot() -> pd.DataFrame:
    """Current market snapshot from markets.json, including APY and warning flags."""
    mkts = load("markets.json") or []
    rows = []
    for m in mkts:
        s = m.get("state", {})
        warnings = [w["type"] for w in (m.get("warnings") or [])]
        rows.append({
            "collateral":        m["collateralAsset"]["symbol"],
            "loan":              m["loanAsset"]["symbol"],
            "supply_usd":        s.get("supplyAssetsUsd", 0) or 0,
            "borrow_usd":        s.get("borrowAssetsUsd", 0) or 0,
            "utilization":       s.get("utilization", 0) or 0,
            "supply_apy":        s.get("supplyApy", 0) or 0,
            "borrow_apy":        s.get("borrowApy", 0) or 0,
            "bad_debt_warning":  "bad_debt_unrealized" in warnings,
            "key":               m["uniqueKey"],
        })
    return pd.DataFrame(rows)


@st.cache_data
def vault_summary_data() -> dict:
    """Load vault_summary.json produced by ETL fetch_vault_summary()."""
    return load("vault_summary.json") or {
        "total_vault_count": 0, "incident_vault_count": 0, "incident_vaults": []
    }


@st.cache_data
def dune_bad_debt() -> dict:
    """Load on-chain bad debt results from Dune Analytics queries."""
    return load("dune_bad_debt.json") or {}


def _dune_market(sym: str) -> dict:
    """Return the Dune result dict for a given collateral symbol."""
    dd = dune_bad_debt()
    for m in dd.get("markets", []):
        if m["market"].startswith(sym):
            return m
    return {}


@st.cache_data
def hist_market_borrow_apy() -> dict:
    """
    Return { label: pd.DataFrame(date, borrow_apy_pct) } for the main incident markets
    that had significant supply (>$1k) during Nov 2025.
    """
    hist = load("historical_markets.json") or []
    result = {}
    seen: dict[str, int] = {}  # symbol → highest-supply version seen
    rows_by_key: dict[str, list] = {}

    for h in hist:
        coll = (h.get("collateralAsset") or {}).get("symbol", "?")
        loan = (h.get("loanAsset") or {}).get("symbol", "?")
        hs   = h.get("historicalState", {})
        borrow_apy_pts = hs.get("borrowApy", [])
        supply_pts     = hs.get("supplyAssetsUsd", [])
        if not borrow_apy_pts:
            continue
        max_supply = max((p["y"] for p in supply_pts if p.get("y")), default=0)
        label = f"{coll}/{loan}"
        # Keep only the instance of each pair with the highest peak supply
        if label not in seen or max_supply > seen[label]:
            seen[label] = max_supply
            rows = []
            apy_d = {p["x"]: p["y"] for p in borrow_apy_pts}
            for ts in sorted(apy_d.keys()):
                rows.append({"date": _ts(ts), "borrow_apy_pct": (apy_d[ts] or 0) * 100})
            rows_by_key[label] = rows

    for label, rows in rows_by_key.items():
        if rows:
            result[label] = pd.DataFrame(rows).sort_values("date")
    return result


@st.cache_data
def hist_market_sdeusd() -> pd.DataFrame:
    """Historical sdeUSD/USDC market state for November 2025 from historical_markets.json.
    Picks the instance of sdeUSD/USDC with the highest peak supply (the main impacted market).
    """
    hist = load("historical_markets.json") or []
    best = None
    best_supply = -1.0
    for h in hist:
        coll = h.get("collateralAsset") or {}
        if not isinstance(coll, dict) or coll.get("symbol") != "sdeUSD":
            continue
        hs = h.get("historicalState", {})
        supply_pts = hs.get("supplyAssetsUsd", [])
        max_supply = max((p["y"] for p in supply_pts if p.get("y")), default=0)
        if max_supply > best_supply:
            best_supply = max_supply
            best = hs
    if best is None:
        return pd.DataFrame()
    ref_field = next(iter(best.values()), [])
    dates = [_ts(p["x"]) for p in sorted(ref_field, key=lambda p: p["x"])]
    df = pd.DataFrame({"date": dates})
    for field, pts in best.items():
        d2v = {_ts(p["x"]): p["y"] for p in pts}
        df[field] = df["date"].map(d2v)
    return df.sort_values("date").reset_index(drop=True)


# ─────────────────────────────────────────────────────────────────────────────
def main():
    st.set_page_config(
        page_title="Morpho — Nov 2025 Depeg",
        page_icon="🔵",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    st.markdown(CSS, unsafe_allow_html=True)

    # Sidebar nav
    with st.sidebar:
        st.markdown('<div class="sidebar-logo">🔵 Morpho</div>', unsafe_allow_html=True)
        st.markdown('<div class="sidebar-sub">Depeg Incident Dashboard</div>', unsafe_allow_html=True)
        st.markdown("---")
        section = st.radio("Navigation", [
            "📋 Executive Summary",
            "📉 Asset Price Collapse",
            "🏛 Exposed Markets & Vaults",
            "🧭 Curator Response",
            "🔎 Root Cause Analysis",
        ], label_visibility="collapsed")
        st.markdown("---")
        st.caption("**Assets:** xUSD · deUSD · sdeUSD\n\n**Incident window:** Nov 3–14, 2025\n\n**Analysis window:** Nov 1–30, 2025")

    # Route to sections
    if section == "📋 Executive Summary":
        page_summary()
    elif section == "📉 Asset Price Collapse":
        page_prices()
    elif section == "🏛 Exposed Markets & Vaults":
        page_markets()
    elif section == "🧭 Curator Response":
        page_curators()
    elif section == "🔎 Root Cause Analysis":
        page_rootcause()


# ── cascade / contagion flow chart ──────────────────────────────────────────
def _cascade_chart():
    """Vertical flowchart showing contagion chain as a Plotly figure."""
    stats = price_stats()

    def _dd_metric(sym, fallback):
        s = stats.get(sym)
        if not s:
            return fallback
        return f"{s['drawdown_pct']:.0f}%  ·  ${s['start']:.2f} → ${s['low']:.3f}"

    apy_data = hist_market_borrow_apy()
    _sdeusd_df = apy_data.get("sdeUSD/USDC")
    _peak_apy = None
    if _sdeusd_df is not None and not _sdeusd_df.empty:
        _nov = _sdeusd_df[(_sdeusd_df["date"] >= pd.Timestamp("2025-11-04", tz="UTC")) &
                          (_sdeusd_df["date"] <= pd.Timestamp("2025-11-14", tz="UTC"))]
        _peak_apy = _nov["borrow_apy_pct"].max() if not _nov.empty else None
    _apy_str = f"{_peak_apy:.0f}%" if _peak_apy else "~485%"

    # Layout constants — wide enough that detail lines fit without wrapping
    # Side nodes are narrower so detail text is omitted; only title + metric shown.
    # Vertical positions give ≥0.06 gap between box edges for arrows + labels.
    CW = 0.38   # center-node half-width
    SW = 0.21   # side-node half-width
    H  = 0.085  # half-height for all nodes

    # y-centers: Stream=0.90, side=0.69, deUSD=0.48, Morpho=0.28, MEV=0.08
    # gaps (box-edge to box-edge): Stream↓→side = 0.90-H-(0.69+H)=0.04; side↓→deUSD = 0.69-H-(0.48+H)=0.04
    # deUSD↓→Morpho = 0.48-H-(0.28+H)=0.03; Morpho↓→MEV = 0.28-H-(0.08+H)=0.03
    # arrow+label mid-points sit in those gaps (labelled below)

    # (title, metric, detail_or_None, cx, cy, w, fill, border, tc, mc)
    NODES = [
        ("Stream Finance",
         "$93M loss disclosed · Nov 3, 2025",
         "A $200M+ DeFi yield fund. All withdrawals frozen within hours.",
         0.50, 0.90, CW, "#7f1d1d", "#ef4444", "#fca5a5", "#f87171"),

        ("xUSD",
         _dd_metric("xUSD", "–94%  ·  $1.00 → $0.07"),
         None,   # narrow box — no detail line
         0.22, 0.69, SW, "#7f1d1d", "#ef4444", "#fca5a5", "#f87171"),

        ("Elixir / deUSD",
         "65% of reserves backed by xUSD",
         None,   # narrow box — no detail line
         0.78, 0.69, SW, "#7f1d1d", "#ef4444", "#fca5a5", "#f87171"),

        ("deUSD / sdeUSD",
         _dd_metric("sdeUSD", "–100%  ·  $1.00 → $0.002"),
         "Recursive loop collapses simultaneously. Oracle still reports $1.00.",
         0.50, 0.48, CW, "#78350f", "#f59e0b", "#fde68a", "#fbbf24"),

        ("Morpho sdeUSD/USDC Market",
         "100% utilization · $0 badDebtAssets on-chain (Dune)",
         "No Liquidate event ever triggered — oracle blindspot. Market locks.",
         0.50, 0.28, CW, "#0f2744", "#3b82f6", "#93c5fd", "#60a5fa"),

        ("MEV Capital USDC Vault (ETH)",
         f"~$916K bad debt · 3.6% TVL loss · {_apy_str} peak borrow APY",
         "Vault NAV drops as worthless collateral priced at $1.00. Lenders locked.",
         0.50, 0.08, CW, "#0f2744", "#3b82f6", "#93c5fd", "#60a5fa"),
    ]

    shapes, annotations = [], []

    for (title, metric, detail, cx, cy, W, fill, border, tc, mc) in NODES:
        shapes.append(dict(
            type="rect", x0=cx-W, x1=cx+W, y0=cy-H, y1=cy+H,
            fillcolor=fill, line=dict(color=border, width=1.5), layer="below",
        ))
        # Title — upper third of box
        ty = cy + (0.030 if detail else 0.015)
        annotations.append(dict(
            x=cx, y=ty, text=f"<b>{title}</b>",
            showarrow=False, font=dict(color=tc, size=13, family="Inter"),
            xanchor="center", yanchor="middle",
        ))
        # Metric — middle of box
        my = cy - (0.010 if detail else 0.015)
        annotations.append(dict(
            x=cx, y=my, text=metric,
            showarrow=False, font=dict(color=mc, size=11, family="Inter"),
            xanchor="center", yanchor="middle",
        ))
        # Detail — lower third (wide nodes only)
        if detail:
            annotations.append(dict(
                x=cx, y=cy-0.050, text=detail,
                showarrow=False, font=dict(color="#94a3b8", size=10, family="Inter"),
                xanchor="center", yanchor="middle",
            ))

    # Arrows: from bottom-centre of source to top-centre of target.
    # Edge labels placed at x=0.13 (left margin) to stay clear of all nodes.
    # (x0, y0, x1, y1, label, lx, ly)
    ARROWS = [
        (0.50, 0.90-H,  0.22, 0.69+H,  "xUSD = Stream's yield token",        0.10, 0.806),
        (0.50, 0.90-H,  0.78, 0.69+H,  "deUSD 65% backed by Stream debt",    0.90, 0.806),
        (0.22, 0.69-H,  0.50, 0.48+H,  "xUSD collateral → mints deUSD",      0.10, 0.598),
        (0.78, 0.69-H,  0.50, 0.48+H,  "deUSD collapses with backing",       0.90, 0.598),
        (0.50, 0.48-H,  0.50, 0.28+H,  "sdeUSD posted as Morpho collateral", 0.10, 0.390),
        (0.50, 0.28-H,  0.50, 0.08+H,  "100% util locks vault lenders",      0.10, 0.190),
    ]

    arrow_tip_x, arrow_tip_y = [], []
    for (x0, y0, x1, y1, lbl, lx, ly) in ARROWS:
        shapes.append(dict(
            type="line", x0=x0, y0=y0, x1=x1, y1=y1,
            xref="paper", yref="paper",
            line=dict(color="#ef4444", width=1.5, dash="dot"), layer="above",
        ))
        arrow_tip_x.append(x1)
        arrow_tip_y.append(y1)
        annotations.append(dict(
            x=lx, y=ly, text=lbl, showarrow=False,
            font=dict(color="#64748b", size=9, family="Inter"),
            xanchor="center", yanchor="middle",
            bgcolor="#141824", bordercolor="#2d3a52", borderwidth=1, borderpad=3,
        ))

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=arrow_tip_x, y=arrow_tip_y, mode="markers",
        marker=dict(symbol="triangle-up", size=9, color="#ef4444"),
        showlegend=False, hoverinfo="skip",
    ))
    fig.update_layout(
        **PLOT, height=620,
        title=dict(text="Contagion Cascade — How One Failure Became Three",
                   font=dict(size=15), x=0, xanchor="left"),
        shapes=shapes, annotations=annotations, showlegend=False,
    )
    fig.update_xaxes(visible=False, range=[0, 1])
    fig.update_yaxes(visible=False, range=[-0.01, 1.01])
    st.plotly_chart(fig, use_container_width=True)


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 1 — EXECUTIVE SUMMARY
# ══════════════════════════════════════════════════════════════════════════════
def page_summary():
    st.markdown("## Morpho Protocol — Depeg Incident Analysis")
    st.caption("November 2025 · xUSD (Stream Finance) / deUSD & sdeUSD (Elixir) Depeg Events")

    st.markdown("""<div style="border-left:4px solid #3b82f6;padding:14px 18px;background:rgba(59,130,246,0.08);
border-radius:0 8px 8px 0;margin-bottom:20px">
<span style="font-size:13px;font-weight:700;text-transform:uppercase;letter-spacing:.08em;color:#3b82f6">Key Finding</span>
<p style="margin:6px 0 0;font-size:15px;line-height:1.6;color:#e2e8f0">
Morpho's isolation architecture <strong>worked exactly as designed</strong> — only 2 of 1,320+ public vaults
had any bad debt, and those losses were contained entirely to curators who chose xUSD/sdeUSD exposure.
The <strong>$68M private market loss</strong> (TelosC) is a different story: an institutional OTC-style position
with no curator guardrails. Understanding the difference between these two types of loss is the
central risk question for any prospective integrator.
</p></div>""", unsafe_allow_html=True)

    alert("blue", "About This Dashboard",
          "This dashboard walks prospective curators and integrators through the November 2025 depeg "
          "events involving Stream Finance's xUSD and Elixir's deUSD/sdeUSD stablecoins, and how "
          "Morpho's isolation architecture responded. Data is drawn from on-chain analytics, the "
          "Morpho API, and public reporting.")

    stats = price_stats()
    mkts  = market_snapshot()
    vs    = vault_summary_data()

    def _dd(sym):
        s = stats.get(sym, {})
        if not s:
            return "n/a", "No price data"
        return f"{s['drawdown_pct']:.0f}%", f"${s['start']:.2f} → ${s['low']:.4f} (Nov 2025, on-chain)"

    xusd_dd,   xusd_sub   = _dd("xUSD")
    sdeusd_dd, sdeusd_sub = _dd("sdeUSD")

    # Peak utilization from market snapshot
    incident_cols = mkts[mkts["collateral"].isin(["xUSD","deUSD","sdeUSD"])]
    n_locked = int((incident_cols["utilization"] >= 0.99).sum()) if len(incident_cols) else 0
    # Vault totals from API
    total_vaults    = vs.get("total_vault_count", 0)
    # Public TVL from top-30 ETL sample
    top30        = load("vaults_v2_top.json") or []
    listed_tvl   = sum(float(v.get("totalAssetsUsd") or 0) for v in top30 if v.get("listed"))
    public_bd    = 1.616  # $M public bad debt
    pct_tvl_safe = (1 - public_bd / (listed_tvl / 1e6)) * 100 if listed_tvl else 99.87

    # Row 1 — Morpho outcomes: what happened to lenders and the protocol
    kpi_row(
        ("Public Vault Bad Debt",
         "~$1.6M",
         "2 MEV Capital vaults · xUSD (~$700K Arb) + sdeUSD (~$916K ETH) · vault NAV loss, not on-chain protocol bad debt",
         "amber"),
        ("Private Market Bad Debt",
         "~$68M",
         "TelosC / Plume — 1 non-whitelisted, institutional market · separate from public vault system",
         "red"),
        ("Public TVL Unaffected",
         f"{pct_tvl_safe:.2f}%",
         f"${listed_tvl/1e6:.0f}M+ public vault TVL (top-30 sample) · only $1.6M crystallized as bad debt · isolation architecture validated",
         "green"),
    )
    # Row 2 — collateral collapse and market stress
    kpi_row(
        ("xUSD Drawdown",         xusd_dd,   xusd_sub,                                       "red"),
        ("sdeUSD Drawdown",       sdeusd_dd, sdeusd_sub,                                     "red"),
        ("Markets Locked (100%)", str(n_locked),
         "Incident markets at 100% utilization — lenders unable to withdraw",                "amber"),
        ("Early Exits Pre-Collapse", "1",
         "Smokehouse exited deUSD ~2 days before collapse · Re7 & Gauntlet never entered",   "green"),
    )

    sec_hdr("Event Summary", "What happened, why it matters for Morpho curators")
    st.markdown("""
<div class="two-col">
<div class="prose">
  <p><strong>Root Cause Chain</strong></p>
  <ol style="padding-left:18px">
    <li><strong>Stream Finance</strong> operated a $200M+ DeFi yield fund with 4× leverage via recursive looping
        across Euler, Morpho, Silo and Gearbox — turning deposits into a fragile tower of synthetic yield.</li>
    <li>On <strong>November 3, 2025</strong>, Stream disclosed a <strong>$93M loss</strong> by an external fund
        manager, freezing all withdrawals. xUSD fell $1.00 → $0.26 within hours.</li>
    <li><strong>Elixir's deUSD</strong> had allocated <strong>65% of its collateral ($68M)</strong> to Stream
        Finance via private Morpho markets. When xUSD collapsed, deUSD's backing evaporated — deUSD fell
        <strong>98%</strong>.</li>
    <li><strong>Oracle hardcoding</strong> at $1.00 on multiple protocols prevented automatic liquidations from
        triggering as collateral prices cratered on secondary markets.</li>
    <li>Morpho's <strong>isolation architecture</strong> contained the damage: only 2 public vaults had direct
        exposure; the vast majority of other vaults were completely unaffected.</li>
  </ol>
</div>
<div class="prose">
  <p><strong>Key Morpho Takeaways</strong></p>
  <ul>
    <li>Morpho's <strong>market isolation design</strong> was the primary firewall — losses were confined to vaults
        that explicitly opted into xUSD/sdeUSD exposure.</li>
    <li><strong>Curator quality matters</strong>: curators with strong risk frameworks (Re7, Gauntlet, Smokehouse)
        avoided the incident entirely. MEV Capital's slower response resulted in realized bad debt.</li>
    <li><strong>Oracle design is critical</strong>: hardcoding synthetic stablecoin prices at $1.00 creates
        liquidation blindspots that materialize catastrophically during depegs.</li>
    <li><strong>Permissionless architecture</strong> means individual vault decisions do not propagate to the
        protocol layer — a key differentiator from monolithic lending pools.</li>
    <li><strong>Vault liquidity</strong> became constrained in affected vaults (100% utilization), but unaffected
        vaults remained fully liquid throughout the event.</li>
  </ul>
</div>
</div>
""", unsafe_allow_html=True)

    sec_hdr("Event Timeline")
    tl_html = '<div class="tl">'
    tl_html += tl_item("green", "Nov 1, 2025",
        "🟢 Smokehouse Exits deUSD Pre-Emptively",
        "Reduces deUSD allocation to zero ~2 days before collapse. Risk framework flagged 65% reserve concentration in Stream Finance.")
    tl_html += tl_item("red", "Nov 3, 2025 — 14:00 UTC",
        "🔴 Stream Finance Discloses $93M Loss",
        "xUSD falls $1.00 → $0.26 within 6 hours. Withdrawals frozen. Contagion begins across Euler, Morpho, Silo, Gearbox.")
    tl_html += tl_item("amber", "Nov 4, 2025",
        "🟡 MEV Capital Begins Monitoring",
        "Confirmed exposure to sdeUSD/USDC market on Ethereum vault. Coordinating with Morpho risk team.")
    tl_html += tl_item("red", "Nov 5, 2025",
        "🔴 deUSD Collapses 98%",
        "Falls to $0.03. 65% of reserves ($68M) confirmed irrecoverable. sdeUSD follows. MEV Capital ETH vault hits 100% utilization.")
    tl_html += tl_item("amber", "Nov 7, 2025",
        "🟡 Morpho Delists sdeUSD/USDC Market",
        "MEV Capital USDC vault removes sdeUSD/USDC pair. 3.6% bad debt (~$916K) realized. Supply limit set to zero.")
    tl_html += tl_item("green", "Nov 8–14, 2025",
        "🟢 Protocol Stability Confirmed",
        "All Morpho vaults outside the 2 affected MEV Capital vaults confirmed unaffected. Elixir announces USDC compensation program. MEV Capital publishes post-mortem.")
    tl_html += '</div>'
    st.markdown(tl_html, unsafe_allow_html=True)

    sec_hdr("Contagion Cascade",
            "How a single fund manager's loss propagated across three collateral assets and into multiple DeFi protocols")
    _cascade_chart()

    _sources_footer(
        "Morpho GraphQL API — market snapshots, vault counts, price history",
        "MEV Capital post-mortem report (Nov 2025)",
        "Dune Analytics — on-chain Liquidate event verification (query IDs: 6900807, 6900808, 6900815)",
        "Public reporting: The Block, QuillAudits, Elixir announcement",
    )


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 2 — ASSET PRICE COLLAPSE
# ══════════════════════════════════════════════════════════════════════════════
def page_prices():
    st.markdown("## 📉 Asset Price Collapse")
    st.caption("xUSD, deUSD, and sdeUSD price trajectories during the November 2025 depeg event")

    st.markdown("""<div style="border-left:4px solid #ef4444;padding:14px 18px;background:rgba(239,68,68,0.08);
border-radius:0 8px 8px 0;margin-bottom:20px">
<span style="font-size:13px;font-weight:700;text-transform:uppercase;letter-spacing:.08em;color:#ef4444">Key Finding</span>
<p style="margin:6px 0 0;font-size:15px;line-height:1.6;color:#e2e8f0">
The price collapse was <strong>not a gradual market correction</strong> — it was near-instantaneous once
Stream Finance's loss was disclosed. xUSD fell 94% in hours. The critical insight: <strong>the oracle
never moved</strong>. Every lending protocol with a hardcoded $1.00 oracle continued treating these
assets as fully valued even as they traded at $0.03–$0.07 on secondary markets.
This is why no liquidations fired and why the bad debt accrued invisibly.
</p></div>""", unsafe_allow_html=True)

    sec_hdr("Stablecoin Price Trajectories (Nov 1–30, 2025)",
            "All three assets were expected to maintain a $1.00 peg — data from Morpho API")

    df = price_data()
    stats = price_stats()

    # Pre-collapse xUSD data (~Nov 1–3) reflects oracle/share-price (~$1.26), not secondary-market price.
    # Clamp to $1.05 so the chart shows the depeg clearly rather than a misleading pre-event premium.
    df_plot = df.copy()
    for col in ["xUSD", "sdeUSD", "deUSD"]:
        if col in df_plot.columns:
            df_plot[col] = df_plot[col].clip(upper=1.05)

    fig = go.Figure()
    for col, color, fill_color in [
        ("xUSD",   RED,   "rgba(239,68,68,0.07)"),
        ("deUSD",  AMBER, "rgba(245,158,11,0.07)"),
        ("sdeUSD", PURP,  "rgba(167,139,250,0.05)"),
    ]:
        if col in df_plot.columns:
            fig.add_trace(go.Scatter(
                x=df_plot["date"], y=df_plot[col], name=col,
                line=dict(color=color, width=2.5),
                fill="tozeroy", fillcolor=fill_color,
                mode="lines",
            ))
    fig.add_trace(go.Scatter(
        x=df_plot["date"], y=[1.0]*len(df_plot), name="$1.00 Peg",
        line=dict(color=GREEN, dash="dash", width=1.5),
        mode="lines",
    ))
    fig.update_yaxes(range=[0, 1.10], tickprefix="$")
    fig.update_xaxes(title_text="")
    chart(fig, height=380)
    st.caption("Prices capped at $1.05 — pre-collapse oracle/share-price values excluded to reflect secondary-market reality")

    # Compute KPIs from real data
    def _kpi_triple(sym):
        s = stats.get(sym)
        if not s:
            return (f"{sym} Max Drawdown", "n/a", "No data", "muted")
        dd = f"{s['drawdown_pct']:.0f}%"
        low_str = f"${s['low']:.3f}"
        start_str = f"${s['start']:.2f}"
        return (f"{sym} Max Drawdown", dd, f"{start_str} → {low_str} (Nov 2025)", "red")

    kpi_row(*[_kpi_triple(s) for s in ["xUSD", "sdeUSD", "deUSD"]])

    sec_hdr("Oracle Hardcoding — The Liquidation Blindspot",
            "Gap between market price and oracle price prevented liquidations from triggering")

    # Use clamped/trimmed data starting Nov 4 to show the actual depeg period
    df_oracle2 = df_plot[df_plot["date"] >= pd.Timestamp("2025-11-04", tz="UTC")].copy()
    fig2 = go.Figure()
    fig2.add_trace(go.Scatter(
        x=df_oracle2["date"], y=df_oracle2["xUSD"], name="xUSD Market Price",
        line=dict(color=RED, width=2.5),
        fill="tozeroy", fillcolor="rgba(239,68,68,0.12)", mode="lines",
    ))
    fig2.add_trace(go.Scatter(
        x=df_oracle2["date"], y=[1.0]*len(df_oracle2), name="Oracle Price (hardcoded $1.00)",
        line=dict(color=GREEN, dash="dash", width=2),
        mode="lines",
    ))
    fig2.update_yaxes(range=[0, 1.15], tickprefix="$")
    chart(fig2, height=300)

    alert("amber", "Why this mattered:",
          "Lending protocols hardcoded xUSD at $1.00 to avoid triggering mass liquidations during "
          "normal operations. But in a genuine depeg, as xUSD traded at $0.07–$0.30 on secondary "
          "markets, the oracle reported $1.00 — meaning borrowers appeared fully collateralized and "
          "liquidation bots received no trigger signal. Lenders were left holding worthless collateral "
          "with no automatic protection.")

    sec_hdr("Cascade Mechanism", "Why one stablecoin failure caused two more to collapse — recursive dependencies")
    alert("red", "Recursive Dependency (The Core Problem)",
          "deUSD's collateral was 65% ($68M) allocated to Stream Finance. Stream used xUSD as collateral "
          "on Morpho private markets. xUSD was partially backed by borrowed deUSD — a circular dependency: "
          "when xUSD collapsed, deUSD lost its backing; when deUSD lost backing, it collapsed further, "
          "devaluing xUSD further. Both were guaranteed to fall together.")
    _cascade_chart()
    st.caption("The cascade diagram is also shown on the Executive Summary page for quick reference.")

    _sources_footer(
        "Morpho GraphQL API — collateral price history (historicalPriceUsd)",
        "Public reporting: The Block, QuillAudits",
    )


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 3 — EXPOSED MARKETS & VAULTS
# ══════════════════════════════════════════════════════════════════════════════
def page_markets():
    st.markdown("## 🏛 Exposed Morpho Markets & Vaults")
    st.caption("Which markets and vaults had direct exposure to xUSD, deUSD, or sdeUSD as collateral")

    st.markdown("""<div style="border-left:4px solid #f59e0b;padding:14px 18px;background:rgba(245,158,11,0.08);
border-radius:0 8px 8px 0;margin-bottom:20px">
<span style="font-size:13px;font-weight:700;text-transform:uppercase;letter-spacing:.08em;color:#f59e0b">Key Finding</span>
<p style="margin:6px 0 0;font-size:15px;line-height:1.6;color:#e2e8f0">
There were <strong>two fundamentally different types of loss</strong> on Morpho, and conflating them
gives a distorted picture of the protocol's risk profile. The <strong>$1.6M public vault loss</strong>
is a curator failure — two MetaMorpho vaults took on synthetic stablecoin exposure that better-run
vaults avoided. The <strong>$68M private market loss</strong> is more like an institutional OTC trade
gone wrong — a non-whitelisted direct market used as bilateral financing between large counterparties,
with no curator oversight and no retail depositors involved. These require entirely different risk frameworks.
</p></div>""", unsafe_allow_html=True)

    sec_hdr("Morpho's Isolation Design — Big Picture")
    mkts = market_snapshot()
    vs   = vault_summary_data()
    n_incident_mkts = len(mkts[mkts["collateral"].isin(["xUSD","deUSD","sdeUSD"])])
    total_supply_incident = mkts[mkts["collateral"].isin(["xUSD","deUSD","sdeUSD"])]["supply_usd"].sum()
    at_max_util = len(mkts[(mkts["collateral"].isin(["xUSD","deUSD","sdeUSD"])) & (mkts["utilization"] >= 0.99)])
    # sdeUSD/USDC was delisted (supply cap → 0) after the incident, so it may lose the live flag
    # but was equally impaired during the event. All 3 show as 100% util in the API snapshot.
    n_impaired_total = at_max_util
    total_vaults    = vs.get("total_vault_count", 0)
    incident_vaults = vs.get("incident_vault_count", 0)
    kpi_row(
        ("Incident Asset Markets", str(n_incident_mkts),
         "Markets with xUSD/deUSD/sdeUSD as collateral", "amber"),
        ("Markets at 100% Utilization", str(at_max_util),
         "Fully locked — lenders cannot withdraw", "red"),
        ("Total Vaults on Morpho", f"{total_vaults:,}" if total_vaults else "n/a",
         f"{incident_vaults} currently with incident-asset allocation · all unlisted", "blue"),
    )
    alert("green", "Isolation Working as Designed:",
          "Morpho's market isolation model means each market is a standalone lending pair. "
          "A curator accepting xUSD as collateral in one vault does not create any risk for vaults "
          "that chose not to. This is fundamentally different from pooled architectures like Aave v2, "
          "where all depositors share collateral risk.")

    sec_hdr("Exposed Morpho Markets",
            "Separated by market type — public MetaMorpho vaults vs. private institutional markets")

    # ── PUBLIC MARKETS ────────────────────────────────────────────────────────
    st.markdown("""<div style="display:flex;align-items:center;gap:10px;margin:16px 0 8px">
  <span style="background:#1e3a5f;color:#60a5fa;font-size:11px;font-weight:700;
               text-transform:uppercase;letter-spacing:.08em;padding:4px 10px;border-radius:4px">
    Public MetaMorpho Vaults</span>
  <span style="font-size:12px;color:#64748b">Retail-accessible · curator-managed · listed on Morpho UI</span>
</div>""", unsafe_allow_html=True)

    st.markdown("""
<div class="tbl-wrap">
<table class="stbl">
<thead><tr><th>Market</th><th>Loan</th><th>Collateral</th><th>Chain</th><th>Curator</th>
<th>Supply at Peak</th><th>Bad Debt</th><th>Oracle</th><th>Status</th></tr></thead>
<tbody>
<tr>
  <td>xUSD/USDC</td><td>USDC</td><td>xUSD</td><td>Arbitrum</td><td>MEV Capital</td>
  <td>~$6.3M</td><td><span class="badge badge-amber">~$700K (11% TVL)</span></td>
  <td>Hardcoded $1.00</td><td><span class="badge badge-red">Liq. Failed</span></td>
</tr>
<tr>
  <td>sdeUSD/USDC</td><td>USDC</td><td>sdeUSD</td><td>Ethereum</td><td>MEV Capital</td>
  <td>~$10.6M (on-chain) / ~$25.4M (reported peak)</td>
  <td><span class="badge badge-amber">~$916K (3.6% TVL)</span></td>
  <td>Hardcoded $1.00</td><td><span class="badge badge-amber">Delisted Nov 7</span></td>
</tr>
</tbody>
</table>
</div>
""", unsafe_allow_html=True)

    st.markdown("""<div class="prose" style="max-width:100%;margin-bottom:20px">
<p>These two markets were part of the curated MetaMorpho system. They were <strong>listed on Morpho's
front-end</strong>, managed by professional curators, and accessible to retail lenders. MEV Capital
made a credit judgment to accept xUSD and sdeUSD as collateral — a decision that turned out to be wrong.
But crucially, <strong>this was a curator decision, not a protocol decision</strong>. Every other public
vault that declined to take on this exposure was completely unaffected.</p>
</div>""", unsafe_allow_html=True)

    # ── PRIVATE MARKETS ───────────────────────────────────────────────────────
    st.markdown("""<div style="display:flex;align-items:center;gap:10px;margin:16px 0 8px">
  <span style="background:#3b1f1f;color:#f87171;font-size:11px;font-weight:700;
               text-transform:uppercase;letter-spacing:.08em;padding:4px 10px;border-radius:4px">
    Private / Non-Whitelisted Market</span>
  <span style="font-size:12px;color:#64748b">Institutional / OTC-style · not on Morpho UI · no curator layer</span>
</div>""", unsafe_allow_html=True)

    st.markdown("""
<div class="tbl-wrap">
<table class="stbl">
<thead><tr><th>Market</th><th>Loan</th><th>Collateral</th><th>Chain</th><th>Counterparty</th>
<th>Total Loans</th><th>Bad Debt</th><th>Oracle</th><th>Status</th></tr></thead>
<tbody>
<tr class="stbl-red">
  <td><strong>xUSD/USDC — TelosC</strong><br>
      <span style="font-size:10.5px;color:#94a3b8">Plume Network · direct market creation</span></td>
  <td>USDC</td><td>xUSD</td><td>Plume</td>
  <td>TelosC (institutional borrower)</td>
  <td>~$123.6M<br><span style="font-size:10.5px;color:#94a3b8">vs Stream Finance assets</span></td>
  <td><span class="badge badge-red">~$68M (55% of exposure)</span></td>
  <td>Hardcoded $1.00</td><td><span class="badge badge-red">Recovery ongoing</span></td>
</tr>
</tbody>
</table>
</div>
""", unsafe_allow_html=True)

    st.markdown("""<div class="alert alert-red" style="margin-bottom:20px">
<b>Why the private market is a different category of risk</b>
<div class="prose" style="max-width:100%;margin-top:8px">
<p>Morpho Blue is <em>permissionless</em> — anyone can create a market with any parameters. The TelosC
market was created directly by institutional counterparties to use as a <strong>bilateral financing
facility</strong>: TelosC wanted to borrow USDC and posted xUSD (Stream Finance yield tokens) as
collateral. This arrangement was:</p>
<ul>
  <li><strong>Not listed</strong> on Morpho's front-end or accessible to retail depositors</li>
  <li><strong>Not managed by any curator</strong> — no risk framework, no supply cap policy, no
      independent collateral review</li>
  <li>Structured more like an <strong>OTC repo trade</strong> than a public lending market —
      large, informed counterparties making concentrated bets on each other's credit</li>
  <li>At <strong>$123.6M</strong>, it was by far the largest single Morpho market in the incident,
      yet invisible to the retail lending ecosystem</li>
</ul>
<p>The $68M loss here is real — but it should be evaluated as <strong>institutional counterparty risk</strong>,
not as evidence that Morpho's public vault system is unsafe. A retail depositor in a Morpho vault had
zero path to this exposure. An institution lending directly into a private market accepted this risk
knowingly (or should have).</p>
</div></div>""", unsafe_allow_html=True)

    sec_hdr("Vault-Level Exposure vs Bad Debt",
            "Peak exposure and realized bad debt across directly affected vaults")

    st.markdown("""<div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin:0 0 12px">
<div class="alert alert-blue" style="margin:0">
  <b>🔵 Exposure at Peak</b>
  The total amount of vault TVL deployed into the incident-affected market at its highest point.
  For MEV Capital ETH, the vault had ~$25.4M allocated to the sdeUSD/USDC market when the depeg hit.
  Not all of this was necessarily lost — it represents the maximum <em>at-risk</em> capital.
</div>
<div class="alert alert-red" style="margin:0">
  <b>🔴 Bad Debt Realized</b>
  The portion of exposure that became an unrecoverable loss — collateral was economically worthless
  but the oracle reported $1.00, so borrowers never got liquidated and the debt was never repaid.
  For MEV Capital ETH, only ~$916K (3.6%) of the $25.4M exposure crystallized as bad debt,
  because most borrowers had less than 100% of their collateral in sdeUSD.
</div>
</div>""", unsafe_allow_html=True)

    fig = go.Figure()
    vaults = ["MEV Capital\nUSDC (ETH)", "MEV Capital\nUSDC (Arb)", "TelosC Plume\n(Private)"]
    exposures = [25.42, 6.30, 123.64]
    bad_debts  = [0.916, 0.700, 68.0]
    fig.add_trace(go.Bar(x=vaults, y=exposures, name="Exposure at Peak ($M)",
                         marker_color="rgba(59,130,246,0.73)", width=0.35, offset=-0.2))
    fig.add_trace(go.Bar(x=vaults, y=bad_debts,  name="Bad Debt Realized ($M)",
                         marker_color="rgba(239,68,68,0.73)",  width=0.35, offset=0.2))
    fig.update_yaxes(tickprefix="$", ticksuffix="M")
    chart(fig, height=340)
    st.caption("Bad debt % of exposure: MEV ETH 3.6% · MEV Arb 11% · TelosC 55% — higher % reflects greater concentration in the affected collateral")

    sec_hdr("All Vaults — Exposure Status")
    st.markdown("""
<table class="stbl">
<thead><tr><th>Vault</th><th>Curator</th><th>Exposed Asset</th><th>Exposure</th>
<th>Bad Debt</th><th>Bad Debt % TVL</th><th>Early Exit?</th><th>Response</th></tr></thead>
<tbody>
<tr class="stbl-amber">
  <td>MEV Capital USDC (ETH)</td><td>MEV Capital</td><td>sdeUSD</td><td>$25.42M</td>
  <td>~$0.916M</td><td><span class="badge badge-amber">3.6%</span></td>
  <td><span class="badge badge-red">No</span></td><td>~96 hrs</td>
</tr>
<tr class="stbl-red">
  <td>MEV Capital USDC (Arb)</td><td>MEV Capital</td><td>xUSD</td><td>~$6.3M</td>
  <td>~$0.700M</td><td><span class="badge badge-red">~11%</span></td>
  <td><span class="badge badge-red">No</span></td><td>~72 hrs</td>
</tr>
<tr class="stbl-red">
  <td>TelosC Private (Plume)</td><td>TelosC</td><td>xUSD</td><td>$123.64M</td>
  <td>~$68M</td><td><span class="badge badge-red">~55%</span></td>
  <td><span class="badge badge-red">No</span></td><td>Ongoing</td>
</tr>
<tr class="stbl-green">
  <td>Smokehouse USDC (ETH)</td><td>Smokehouse</td><td>deUSD (exited)</td><td>$4.2M prior</td>
  <td>$0</td><td><span class="badge badge-green">0%</span></td>
  <td><span class="badge badge-green">Yes — ~2 days before</span></td><td>Pre-emptive</td>
</tr>
<tr class="stbl-blue">
  <td>Re7 USDC (ETH)</td><td>Re7 Capital</td><td>None</td><td>$0</td>
  <td>$0</td><td><span class="badge badge-green">0%</span></td>
  <td><span class="badge badge-blue">Never entered</span></td><td>Pre-emptive</td>
</tr>
<tr class="stbl-blue">
  <td>Gauntlet USDC (ETH)</td><td>Gauntlet</td><td>None</td><td>$0</td>
  <td>$0</td><td><span class="badge badge-green">0%</span></td>
  <td><span class="badge badge-blue">Never entered</span></td><td>Pre-emptive</td>
</tr>
</tbody>
</table>
""", unsafe_allow_html=True)

    sec_hdr("Were Any Curators Previously Exposed but Exited Early?")
    c1, c2 = st.columns(2)
    with c1:
        alert("green", "Smokehouse — Pre-emptive Exit (~Nov 1)",
              "Removed deUSD market allocation ~48 hours before the collapse. Their risk framework had "
              "flagged that deUSD's reserve composition — 65% allocated to a single counterparty (Stream "
              "Finance) — represented unacceptable concentration risk. Result: Zero bad debt despite prior exposure.")
    with c2:
        alert("blue", "Re7 Capital & Gauntlet — Never Entered",
              "Both curators had synthetic stablecoin policies requiring full reserve transparency and "
              "diversified backing. Neither xUSD nor deUSD could satisfy these requirements. "
              "Result: Zero bad debt, zero exposure throughout the event.")

    _sources_footer(
        "Morpho GraphQL API — market snapshot, vault summary",
        "MEV Capital post-mortem (Nov 2025)",
        "Public reporting: The Block, QuillAudits",
    )


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 4 — BAD DEBT ANALYSIS
# ══════════════════════════════════════════════════════════════════════════════
def page_curators():
    st.markdown("## 🧭 Curator Response")
    st.caption("How curators detected, responded to, and mitigated exposure during the November 2025 crisis")

    st.markdown("""<div style="border-left:4px solid #10b981;padding:14px 18px;background:rgba(16,185,129,0.08);
border-radius:0 8px 8px 0;margin-bottom:20px">
<span style="font-size:13px;font-weight:700;text-transform:uppercase;letter-spacing:.08em;color:#10b981">Key Finding</span>
<p style="margin:6px 0 0;font-size:15px;line-height:1.6;color:#e2e8f0">
Curator selection is <strong>the most important risk decision</strong> in MetaMorpho — more important
than protocol parameters, oracle choice, or LLTV setting. Three curators avoided the incident entirely
through upfront due diligence. One did not. The protocol's isolation model ensured this remained
<strong>a curator failure, not a protocol failure</strong>. For a prospective integrator, the question
is not "is Morpho safe?" — it's "which curator's risk framework do I trust?"
</p></div>""", unsafe_allow_html=True)

    sec_hdr("Curator Action Timeline")
    tl_html = '<div class="tl">'
    tl_html += tl_item("green", "Nov 1 — 🟢 Smokehouse", "Pre-emptive Exit from deUSD",
        "Reduced deUSD allocation to zero ~2 days before collapse. Risk framework flagged unusual "
        "reserve composition (65% Stream exposure). Result: $0 bad debt.")
    tl_html += tl_item("red", "Nov 3 — 🔴 Stream Finance", "Collapse Announced",
        "$93M loss disclosed. Withdrawals frozen. xUSD drops $1.00 → $0.26 within hours.")
    tl_html += tl_item("amber", "Nov 4 — 🟡 MEV Capital", "Monitoring / Initial Response",
        "Confirmed exposure to sdeUSD/USDC market on Ethereum vault. Began coordinating with Morpho risk team.")
    tl_html += tl_item("red", "Nov 5 — 🔴 Elixir", "deUSD Collapses 98%",
        "deUSD falls to $0.03. 65% of reserves ($68M USDC) irrecoverable. "
        "MEV Capital ETH vault hits 100% utilization. Borrow rates spike to ~70% APY by Nov 5, reaching ~100% by Nov 7 (Morpho API).")
    tl_html += tl_item("amber", "Nov 5 — 🟡 Morpho Protocol", "Emergency Governance",
        "Morpho risk team flags sdeUSD/USDC as at-risk. Supply cap lowered to prevent new deposits.")
    tl_html += tl_item("red", "Nov 6 — 🔴 TelosC", "Largest Exposure Revealed",
        "$123.64M in loans secured by Stream assets across private Plume markets. Recovery negotiations initiated.")
    tl_html += tl_item("amber", "Nov 7 — 🟡 MEV Capital", "sdeUSD/USDC Delisted",
        "MEV Capital removes sdeUSD/USDC from Ethereum USDC vault. 3.6% bad debt (~$916K) realized. "
        "Supply limit set to zero per standard Morpho procedure.")
    tl_html += tl_item("green", "Nov 8 — 🟢 Re7 / Gauntlet", "Unaffected Confirmed",
        "Major curators that avoided xUSD/deUSD report zero bad debt. Isolation design credited for containment.")
    tl_html += tl_item("blue", "Nov 10 — 🔵 Elixir", "Compensation Program Announced",
        "USDC compensation for all deUSD/sdeUSD holders. Aims for full $1 redemption for remaining holders.")
    tl_html += tl_item("green", "Nov 12 — 🟢 MEV Capital", "Post-Mortem Published",
        "Commits to tighter oracle and synthetic-stablecoin policies. Full incident review published.")
    tl_html += tl_item("green", "Nov 14 — 🟢 Morpho Protocol", "Stability Restored",
        "All other Morpho vaults operating normally. Protocol demonstrates isolation design contained systemic contagion to just 2 public vaults.")
    tl_html += '</div>'
    st.markdown(tl_html, unsafe_allow_html=True)

    sec_hdr("Curator Response Scorecard",
            "Grades reflect pre-incident due diligence, speed of response, and depositor outcome")
    st.markdown("""<div style="display:flex;gap:10px;flex-wrap:wrap;margin-bottom:12px">
  <span class="badge badge-green" style="font-size:12px;padding:4px 10px">A+ — No exposure or pre-emptive exit; $0 bad debt</span>
  <span class="badge badge-amber" style="font-size:12px;padding:4px 10px">B — Reactive exit; limited bad debt (&lt;5% TVL)</span>
  <span class="badge badge-amber" style="font-size:12px;padding:4px 10px">C — Reactive; moderate bad debt; adequate post-mortem</span>
  <span class="badge badge-red" style="font-size:12px;padding:4px 10px">F — Full loss; no pre-emptive action; recovery ongoing</span>
</div>
<table class="stbl">
<thead><tr><th>Curator</th><th>Asset</th><th>Peak Exposure</th><th>Action</th><th>Speed</th><th>Bad Debt</th><th>Grade</th></tr></thead>
<tbody>
<tr class="stbl-blue">
  <td>Re7 Capital</td><td>None</td><td>$0</td><td>Risk framework excluded synthetic stables</td>
  <td>⚡ Pre-emptive</td><td>$0</td><td><span class="badge badge-green">A+</span></td>
</tr>
<tr class="stbl-blue">
  <td>Gauntlet</td><td>None</td><td>$0</td><td>Never entered; diversification policy enforced</td>
  <td>⚡ Pre-emptive</td><td>$0</td><td><span class="badge badge-green">A+</span></td>
</tr>
<tr class="stbl-green">
  <td>Smokehouse</td><td>deUSD</td><td>~$4.2M<br><span style="font-size:10.5px;color:#94a3b8">exited before collapse</span></td>
  <td>Exited pre-collapse (~Nov 1)</td>
  <td>⚡ Pre-emptive</td><td>$0</td><td><span class="badge badge-green">A</span></td>
</tr>
<tr class="stbl-amber">
  <td>MEV Capital</td><td>sdeUSD + xUSD</td><td>~$31.7M<br><span style="font-size:10.5px;color:#94a3b8">$25.4M ETH + $6.3M Arb</span></td>
  <td>Removed sdeUSD/USDC; published post-mortem</td>
  <td>⏱ ~4 days</td><td>~$1.6M (5% of exposure)</td><td><span class="badge badge-amber">C</span></td>
</tr>
<tr class="stbl-red">
  <td>TelosC</td><td>xUSD (private)</td><td>~$123.6M<br><span style="font-size:10.5px;color:#94a3b8">institutional OTC market</span></td>
  <td>Recovery negotiations</td>
  <td>❌ Ongoing</td><td>~$68M (55% of exposure)</td><td><span class="badge badge-red">F</span></td>
</tr>
</tbody>
</table>
""", unsafe_allow_html=True)

    sec_hdr("What Separated Winners from Losers")
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("""<div class="prose">
<p><strong>Winning curators did differently:</strong></p>
<ul>
  <li>Strict policy against synthetic stablecoins without full reserve transparency</li>
  <li>Required diversified, auditable collateral backing</li>
  <li>Concentration risk limit: no single counterparty >20–30% of reserves</li>
  <li>Ran stress tests simulating full collateral devaluation</li>
  <li><strong>Smokehouse's signal:</strong> 65% single-counterparty exposure → automatic flag → exit 48 hrs early</li>
</ul>
</div>""", unsafe_allow_html=True)
    with c2:
        st.markdown("""<div class="prose">
<p><strong>Where MEV Capital fell short:</strong></p>
<ul>
  <li>Allowed sdeUSD/USDC allocation despite deUSD's opaque reserve backing</li>
  <li>Did not independently verify Stream Finance's financial health</li>
  <li>Reactive rather than pre-emptive — bad debt was already realized when market was delisted</li>
  <li>Response was sound but too slow given the pace of collapse</li>
</ul>
</div>""", unsafe_allow_html=True)

    alert("blue", "💡 The Lesson",
          "In the MetaMorpho model, <strong>curator due diligence is the primary risk control</strong>. "
          "Morpho Blue's protocol-level safeguards — isolated markets, immutable parameters, public oracles — "
          "function exactly as designed. What they do <em>not</em> do is evaluate whether a collateral asset "
          "is fundamentally sound. That judgment sits entirely with the curator. When a curator approves "
          "an allocation to a market backed by an opaque or illiquid asset, they are making a credit decision "
          "on behalf of every depositor in their vault. Integrators and depositors must evaluate curator "
          "track record, risk frameworks, and responsiveness — not just the protocol's technical guarantees.")

    _sources_footer(
        "MEV Capital post-mortem (Nov 2025)",
        "Public reporting: Smokehouse, Re7, Gauntlet communications",
        "Morpho GraphQL API — market and vault data",
    )


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 6 — VAULT LIQUIDITY
# ══════════════════════════════════════════════════════════════════════════════
def page_liquidity():
    st.markdown("## 💧 Vault Liquidity")
    st.caption("How vault utilization and liquidity evolved — and which vaults were most impacted")

    st.markdown("""<div style="border-left:4px solid #a78bfa;padding:14px 18px;background:rgba(167,139,250,0.08);
border-radius:0 8px 8px 0;margin-bottom:20px">
<span style="font-size:13px;font-weight:700;text-transform:uppercase;letter-spacing:.08em;color:#a78bfa">Key Finding</span>
<p style="margin:6px 0 0;font-size:15px;line-height:1.6;color:#e2e8f0">
The root cause is deceptively simple: <strong>a static oracle made the protocol's liquidation engine
blind to a real-world collapse</strong>. But the deeper lesson is about recursive dependencies —
deUSD was backed by xUSD, which was backed by borrowed deUSD. Once one link broke, the entire chain
collapsed simultaneously, faster than any human or bot could respond. <strong>The protocol mechanics
were sound; the collateral underwriting was not.</strong>
</p></div>""", unsafe_allow_html=True)

    # Q1 — Liquidation failure
    sec_hdr("Q1: Why Didn't the Liquidation Mechanism Work?")

    dd = dune_bad_debt()
    dune_confirmed = bool(dd and dd.get("markets"))
    oracle_proof = (" <strong>Confirmed by Dune:</strong> on-chain query of all Morpho Blue Liquidate events "
                    "shows $0 badDebtAssets across all three incident markets — liquidations simply never fired."
                    if dune_confirmed else "")

    factors = [
        {
            "color": "red",
            "title": "Factor 1 — Oracle Hardcoding ($1.00 Price)",
            "cause": (
                "Multiple protocols hardcoded xUSD's price at $1.00 to prevent cascade liquidations "
                "during normal operations. In a genuine depeg this became catastrophic: market price "
                "fell to $0.07–$0.30, but the oracle kept reporting $1.00. Borrowers appeared fully "
                "collateralized on-chain; no liquidation signal was ever generated. Liquidation bots "
                "and keepers had no trigger price to act on." + oracle_proof
            ),
            "mitigation": (
                "Require market-rate oracles (Chainlink, Pyth, TWAP) for all collateral assets with "
                "secondary market pricing. Static price hardcoding must be disallowed as a vault policy "
                "requirement. Curators should independently verify oracle sources before listing any "
                "synthetic stablecoin."
            ),
            "difficulty": "amber",
            "difficulty_label": "Medium",
        },
        {
            "color": "red",
            "title": "Factor 2 — 100% Utilization Lock",
            "cause": (
                "Even if liquidations had triggered, vault utilization hit 100% — all available USDC "
                "was lent out. Liquidators couldn't source USDC from the vault to repay debt and seize "
                "collateral. Borrow rates on sdeUSD/USDC spiked from ~48% (Nov 1) to 100%+ (Nov 7) per "
                "Morpho API — a clear stress signal visible in advance, but positions couldn't be closed "
                "regardless of rate once the market locked."
            ),
            "mitigation": (
                "Vault parameters should enforce a minimum idle liquidity buffer (e.g. 10% of TVL) "
                "allocated to zero-yield idle markets. Morpho supports this natively via vault-level "
                "idle allocation caps. A buffer prevents 100% utilization lockouts and preserves a "
                "liquidation corridor even under stress."
            ),
            "difficulty": "green",
            "difficulty_label": "Low",
        },
        {
            "color": "amber",
            "title": "Factor 3 — Circular / Recursive Collateral",
            "cause": (
                "xUSD was used as collateral to borrow deUSD, which was used to mint more xUSD, which "
                "was used to borrow more deUSD. This recursive loop meant true real-world backing was a "
                "tiny fraction of face value. When any link in the chain broke, the entire loop collapsed "
                "simultaneously — liquidation bots couldn't sequence positions because every position "
                "became insolvent at once."
            ),
            "mitigation": (
                "Require curators to perform 'collateral graph' analysis before listing: trace each "
                "collateral asset's backing at least two levels deep. If token A is backed by B which "
                "is backed by A, reject both. Circular dependency should be an automatic disqualifier "
                "in any formal curator risk framework."
            ),
            "difficulty": "red",
            "difficulty_label": "High",
        },
        {
            "color": "amber",
            "title": "Factor 4 — Speed of Collapse + Private Market Opacity",
            "cause": (
                "xUSD went from $1.00 to $0.07 in 5 days. Even with functioning liquidation systems, "
                "positions were deeply underwater before keepers could respond at scale. Compounding "
                "this, the largest single exposure ($68M TelosC) sat in non-whitelisted private markets "
                "invisible to public monitoring tools and the broader community — there was no early "
                "warning system for the severity of what was building."
            ),
            "mitigation": (
                "Implement automated utilization and borrow-rate alerts (e.g. page curator ops when "
                "utilization exceeds 85%). Morpho should encourage on-chain indexing of all markets "
                "regardless of whitelist status. Internal risk teams should monitor all market activity, "
                "not just whitelisted vaults. Shorter timelock windows for emergency supply cap "
                "reductions in verified stress scenarios."
            ),
            "difficulty": "amber",
            "difficulty_label": "Medium",
        },
    ]

    for f in factors:
        st.markdown(f"""
<div class="alert alert-{f['color']}" style="margin-bottom:6px">
  <b>{f['title']}</b>
  <div style="display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-top:8px">
    <div>
      <div style="font-size:11px;text-transform:uppercase;letter-spacing:.05em;
                  opacity:.6;margin-bottom:4px">Root Cause</div>
      {f['cause']}
    </div>
    <div style="border-left:1px solid rgba(255,255,255,.12);padding-left:16px">
      <div style="font-size:11px;text-transform:uppercase;letter-spacing:.05em;
                  opacity:.6;margin-bottom:4px">Mitigation &nbsp;
        <span class="badge badge-{f['difficulty']}">{f['difficulty_label']}</span>
      </div>
      {f['mitigation']}
    </div>
  </div>
</div>""", unsafe_allow_html=True)

    # Oracle vs market price chart
    df = price_data()
    depeg_start = pd.Timestamp("2025-11-04", tz="UTC")
    df_oracle = df[df["date"] >= depeg_start].copy()
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=df_oracle["date"], y=df_oracle["xUSD"], name="xUSD Market Price",
        line=dict(color=RED, width=2.5),
        fill="tozeroy", fillcolor="rgba(239,68,68,0.10)", mode="lines",
    ))
    fig.add_trace(go.Scatter(
        x=df_oracle["date"], y=[1.0]*len(df_oracle), name="Oracle Price ($1.00 hardcoded)",
        line=dict(color=GREEN, dash="dash", width=2), mode="lines",
    ))
    fig.update_yaxes(range=[0, 1.15], tickprefix="$")
    fig.update_layout(**_plot(
        height=340,
        margin=dict(l=12, r=12, t=60, b=70),
        title=dict(
            text="xUSD: Market Price vs Hardcoded Oracle Price — The Liquidation Blindspot",
            y=0.97, x=0, xanchor="left", yanchor="top",
            font=dict(size=14),
        ),
        legend=dict(orientation="h", yanchor="bottom", y=-0.25, xanchor="left", x=0),
    ))
    st.caption("The shaded gap between market price and oracle price is the zone where positions were "
               "economically insolvent but appeared fully collateralized on-chain. Morpho's liquidation "
               "mechanism compares loan value to collateral value at oracle price — since the oracle never "
               "moved, no position ever crossed its liquidation threshold.")
    st.plotly_chart(fig, use_container_width=True)

    # Q2 — Liquidity sharing
    sec_hdr("Q2: Are Liquidity Risks Shared Across Morpho?",
            "Evaluating the claim that isolation doesn't fully protect against shared risk")
    c1, c2 = st.columns(2)
    with c1:
        alert("amber", "Arguments FOR shared liquidity risk:",
              "1. <strong>Vault-level pooling:</strong> Within a MetaMorpho vault, all depositors share "
              "utilization risk. If one market hits 100% utilization, ALL lenders in that vault are "
              "temporarily locked — even those allocated to safe markets.<br><br>"
              "2. <strong>Curator credibility contagion:</strong> MEV Capital's vault bad debt created "
              "reputational pressure across all MEV Capital vaults and the curator model broadly.<br><br>"
              "3. <strong>Shared USDC supply:</strong> Morpho vaults compete for the same on-chain USDC "
              "liquidity. Mass withdrawals from one vault can tighten USDC availability market-wide.<br><br>"
              "4. <strong>Protocol-level trust:</strong> A sufficiently severe event could undermine "
              "confidence in Morpho's architecture broadly, causing TVL flight from unaffected vaults.")
    with c2:
        alert("green", "Arguments AGAINST shared liquidity risk (the isolation case):",
              "1. <strong>Collateral risk is fully isolated:</strong> A vault that doesn't list xUSD as "
              "collateral has exactly zero bad debt exposure — structurally different from Aave v2 where "
              "all depositors share one collateral pool.<br><br>"
              "2. <strong>Only 2 public vaults had bad debt:</strong> The November 2025 event validated "
              "Morpho's isolation design. Only 2 public vaults had any bad debt. The rest operated "
              "normally throughout.<br><br>"
              "3. <strong>Vault liquidity is curator-controlled:</strong> A well-designed vault with an "
              "idle liquidity buffer and diversified market allocations will not hit 100% utilization.<br><br>"
              "4. <strong>Market-level granularity:</strong> A bad debt event in one market doesn't "
              "reduce available capital in other markets.")

    alert("blue", "Conclusion:",
          "The claim that 'liquidity risks are shared' is <strong>partially true at the vault level, "
          "but not at the protocol level</strong>. Morpho's isolation design successfully prevents "
          "<em>collateral risk</em> from being shared. However, <em>vault-level</em> liquidity risk "
          "is shared among all depositors within a given vault — making vault design and curator "
          "judgment critical determinants of depositor outcomes. This reinforces why curator selection "
          "is the most important risk decision a prospective integrator will make.")

    alert("blue", "Bottom Line for Prospective Curators:",
          "The November 2025 event is a strong proof-of-concept for Morpho's isolation design. Protocols "
          "with pooled architectures (Euler, Silo) suffered far greater losses. Morpho's public vault "
          "public vault bad debt (~$1.6M) was less than 1% of ~$164M in verified cross-protocol bad debt "
          "(Euler $58M · Silo $22M · Gearbox $14M · Morpho Private $68M). Total exposure across all "
          "protocols reached ~$280M+. Morpho's isolation model directly limited the damage — while "
          "confirming that curator quality remains the decisive risk factor within Morpho itself.")

    _sources_footer(
        "Morpho GraphQL API — market snapshot, historical state",
        "Dune Analytics — on-chain Liquidate events (query IDs: 6900807, 6900808, 6900815)",
        "Public reporting: The Block, QuillAudits, protocol post-mortems (Euler, Silo, Gearbox)",
        "MEV Capital post-mortem (Nov 2025)",
        "Elixir announcement — USDC compensation program",
    )


if __name__ == "__main__":
    main()
