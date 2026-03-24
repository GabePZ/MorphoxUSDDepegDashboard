# Morpho xUSD/deUSD Depeg Dashboard

Submission for the [Morpho Risk Analyst Case Study](https://www.notion.so/morpho-labs/Morpho-Risk-Analyst-Case-Study-2fdd69939e6d80abb067c0467ff27669).

Built to walk a prospective curator (large asset manager) through the xUSD/deUSD/sdeUSD depeg incident of November 2025 — what happened, how Morpho's architecture responded, and what it means for anyone considering building on the protocol.

---

## What's in here

| File | Description |
|------|-------------|
| `dashboard.py` | Streamlit app — the main deliverable |
| `etl.py` | Data pipeline pulling from Morpho GraphQL API and Dune Analytics |
| `TALKING_POINTS.md` | Presentation one-pager with debrief answers |
| `analysis.ipynb` | Exploratory analysis and data QA |
| `data/` | Cached JSON from ETL runs |

---

## Running it

```bash
pip install -r requirements.txt
python3 etl.py          # fetch data (requires DUNE_API_KEY in .env)
streamlit run dashboard.py
```

Copy `.env.example` to `.env` and add your Dune API key before running the ETL.

---

## The short answer

**The isolation architecture worked. The collateral underwriting did not.**

- 1,318 of 1,320 Morpho vaults had $0 bad debt throughout the incident
- The 2 affected public vaults (MEV Capital) lost $1.6M — 0.13% of public vault TVL
- Liquidations never fired because the oracle was hardcoded at $1.00. The protocol's ledger is accurate; it just never knew the collateral was worthless
- The $68M TelosC figure is a private institutional market — structurally different from the public vault system, closer to an OTC repo position than a retail lending product
- Curators with written collateral policies (Re7, Gauntlet) and concentration monitoring (Smokehouse) avoided the incident entirely. MEV Capital did not

The event is a clean proof of concept for isolated markets — and a clear demonstration that curator due diligence is the primary risk control, not protocol mechanics.
