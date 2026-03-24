# Morpho — Risk Analyst Case Study

## Introduction

As a **Risk Analyst**, you are responsible for understanding how the Morpho protocol behaves under market stress. From that understanding, you build **dashboards and monitoring tools** for:

- **Internal use** — e.g. Curator Specialists coordinating with curators  
- **External use** — e.g. educating prospective integrators on Morpho risk as they decide whether to build on top of the protocol

---

## Task

### Scenario

You are on the **integration team** and are educating a **prospective integrator** (e.g. a large US asset manager) interested in becoming a **curator** on Morpho. These conversations usually include questions about **historical stress events**.

**Your assignment:** build a **dashboard** that walks the prospective integrator through the discussion points below, focused on the **xUSD** (Stream Finance) and **deUSD / sdeUSD** (Elixir USD & Staked Elixir USD) **depeg incidents in November 2025**.

### Context

Background reading (headlines summarized from reporting at the time):

- **Stream Finance / xUSD** — withdrawal and deposit stress following market events (order of ~$93M scale reported in coverage).  
- **Elixir** — wind-down / sunset of the **deUSD** synthetic stablecoin in connection with the Stream Finance situation.

Use public reporting and on-chain data to ground the narrative; cite sources in the dashboard where appropriate.

### Helpful resources

| Resource | Notes |
|----------|--------|
| **Dune Analytics** | Morpho dashboards for inspiration — **do not** copy widgets or queries verbatim without meaningful modification |
| **Morpho API** | For pulling protocol / market / vault data |

---

## Dashboard topics

The dashboard should support a walkthrough of:

1. **Exposure** — Which Morpho **markets** and **vaults** held those assets as **collateral** during the depeg?  
2. **Losses** — For exposed vaults, what were **bad debt** amounts and **exposures**?  
3. **Early exits** — Were any **curators** previously exposed to those collateral assets but **exited before** the worst of the incident?  
4. **Curator actions** — What did **vault curators** do in response?  
5. **Liquidity** — How did **vault liquidity** evolve over the period? Which vaults were **more impacted** than others?

---

## Debrief — be prepared to discuss

1. **Liquidations** — Why did the **liquidation mechanism** fail or underperform in this case? (e.g. liquidations did not occur, or were **slow** — tie to data you show.)  
2. **Liquidity sharing** — Morpho **Markets are isolated**, but some argue **liquidity risk** is still **shared** across the protocol. What is your view?  
3. **Bonus: mitigation** — What would you **change or monitor** to reduce the chance or severity of similar issues in the future?

---

## Deliverables

| Deliverable | Description |
|-------------|-------------|
| **Dashboard** | **Dune** or **Streamlit** (or similar) — data and visuals that support **all** dashboard topics above |
| **One-pager** | Short document with extra **talking points** for presenting alongside the dashboard, plus your answers to the **two** required debrief questions (liquidations + liquidity-sharing); include bonus mitigation if you addressed it |

### Streamlit dashboard (this repo)

1. Install deps: `pip install -r requirements.txt`  
2. Ingest data: `python3 etl.py`  
3. Run: `streamlit run dashboard.py`  

The app walks through the five dashboard topics and the debrief prompts using `data/*.json`.

---

## Contacts

Good questions are part of the job. You may reach Morpho Risk:

- **Denny** — [denny@morpho.org](mailto:denny@morpho.org)  
- **Thomas** — [thomas@morpho.org](mailto:thomas@morpho.org)
