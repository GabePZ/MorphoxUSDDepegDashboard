# Morpho xUSD/deUSD Depeg Dashboard

Submission for the [Morpho Risk Analyst Case Study](https://www.notion.so/morpho-labs/Morpho-Risk-Analyst-Case-Study-2fdd69939e6d80abb067c0467ff27669).

Built to walk a prospective curator (large asset manager) through the xUSD/deUSD/sdeUSD depeg incident of November 2025 — what happened, how Morpho's architecture responded, and what it means for anyone considering building on the protocol.

---

## What's in here

| File | Description |
|------|-------------|
| `dashboard.py` | Streamlit app — the main deliverable |
| `etl.py` | Data pipeline pulling from Morpho GraphQL API and Dune Analytics |
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


---

## Talking Points

Walk a prospective curator (large asset manager) through the incident. Goal is to give them an honest picture of what happened, what the protocol did and did not protect against, and what it means for them.

---

## Opening

- Frame this as a stress test that the protocol largely passed, but with one real failure mode worth being honest about: **hardcoded oracles made the liquidation engine blind**. The isolation architecture worked. The collateral underwriting did not.
- Morpho's isolation design is the central architectural claim. This event is the clearest live proof of whether it holds.
- Two separate loss categories to keep distinct throughout: the $1.6M in public vault bad debt (relevant to retail curators) and the $68M in the TelosC private market (institutional OTC exposure, different risk surface).

---

## On the Incident Itself

- Stream Finance was running leveraged yield strategies — not a simple stablecoin. xUSD was a yield-bearing token backed by recursive lending positions across Euler, Morpho, Silo, and Gearbox simultaneously. When the fund disclosed a $93M loss, the unwind was instant.
- The cascade was structural, not just a price drop. deUSD held 65% of its reserves in Stream assets. When xUSD fell, deUSD's backing evaporated — two assets collapsed together, not sequentially. That speed matters: curators had hours, not days, to respond.
- Elixir's compensation program is worth mentioning. They announced USDC redemptions for deUSD/sdeUSD holders, which partially de-risked the situation for some affected parties post-event.

---

## On Why Liquidations Failed

**The short answer:** the oracle never moved, so the protocol never knew anything was wrong.

- Morpho Blue liquidations are triggered by comparing loan value to collateral value *at oracle price*. For xUSD and sdeUSD, that oracle was hardcoded at $1.00 — a static value with no mechanism to respond to secondary-market prices.
- This is a design choice curators must actively evaluate. A hardcoded oracle is not unusual for synthetic stablecoins — the logic is that the token is designed to be pegged. But it creates a binary failure: either the peg holds and the oracle is fine, or the peg breaks and the oracle is completely blind.
- Liquidation bots are rational actors. They only submit transactions when they expect to profit. With oracle price = $1.00, no position was ever in scope. Not one Liquidate transaction was submitted across any of the three incident markets on Ethereum or Arbitrum — confirmed by direct on-chain query.
- The bad debt therefore never appeared on-chain as `badDebtAssets`. The MEV Capital $1.6M figure is a vault NAV accounting loss, not a protocol-level event. This distinction matters: the protocol's ledger is accurate, just incomplete.
- **The implication for curators:** oracle quality is the single most important parameter to evaluate before approving a market allocation. A market-rate oracle (Chainlink, Pyth, or a TWAP) would have triggered liquidations as soon as secondary prices diverged. Static oracles on assets with real market price risk should be treated as a warning sign.

---

## On Liquidity Sharing

**My view:** isolation works as designed at the market level, but there are two real vectors of shared risk worth acknowledging.

**What isolation genuinely protects against:**
- A lender in a USDC/ETH market has zero on-chain exposure to a USDC/xUSD market. No shared reserve pool, no shared collateral, no shared bad debt. The 1,318 unaffected vaults during November 2025 are the proof — they remained fully liquid throughout.

**Where shared risk exists despite isolation:**

1. **Curator-level concentration.** If a single curator manages multiple vaults and makes the same bad collateral call across all of them, depositors in all those vaults are exposed to the same error. MEV Capital had both their ETH and Arb vaults affected. Integrators should look at curator concentration across their book, not just individual market parameters.

2. **Protocol-level reputation and liquidity.** If a large enough incident hit Morpho, the reputational impact could affect vault TVL and secondary market liquidity for MORPHO broadly — even for vaults with zero bad debt. This is a second-order effect, not a first-order one, but it's real. The November event was contained enough that it didn't materialize.

3. **Shared infrastructure.** The Morpho Blue contracts, oracle infrastructure, and liquidator ecosystem are shared. A bug in the core contracts or a liquidator outage affects all markets simultaneously. This is not unique to Morpho but worth flagging.

**Bottom line:** isolated markets are not isolated curators, and they are not isolated protocols. The architecture limits first-order contagion significantly — the data shows this clearly. Second-order risks require curator-level due diligence and diversification.

---

## On Curator Selection (the real risk variable)

- Three curators avoided this entirely through upfront underwriting: Re7 and Gauntlet by policy (synthetic stables excluded), Smokehouse by process (65% single-counterparty concentration flagged, position exited 48 hours before the event).
- MEV Capital had the same information available. The difference was not access — it was whether the risk framework asked the right questions about reserve composition and oracle quality before approving the allocation.
- For a prospective integrator evaluating curators, the questions to ask: Does the curator have a written collateral policy? Do they require independent reserve verification for synthetic stablecoins? What is their concentration limit per counterparty? How fast have they historically responded to market events?
- Curator track record through stress events is arguably the most important input. November 2025 is now a well-documented test case.

---

## On the Private Market (TelosC)

- The $68M TelosC loss is the largest number in the incident. It is also the least relevant to a prospective public vault curator.
- TelosC created a direct Morpho Blue market (permissionlessly) to use as a bilateral financing facility — USDC borrowed against xUSD collateral, at institutional scale ($123.6M), with no curator, no supply cap governance, and no retail depositors.
- This is closer to a repo desk trade than a public lending market. The party on the other side of that position was a large, informed institution that chose that exposure knowingly.
- Conflating this with the public vault system would be like blaming a retail brokerage for a prime brokerage loss. The protocol layer is the same; the user layer is completely different.
- The relevant question for prospective integrators is whether they will be operating in the public MetaMorpho system (where curator controls apply) or creating direct markets (where they are the only risk control). These require different governance entirely.

---

## Mitigation — What Would Change

1. **Oracle policy:** Require market-rate oracles for any collateral with real secondary market price risk. Propose a curator standard that flags hardcoded oracles as a required disclosure in any market approval.
2. **Reserve transparency requirement:** Before approving a synthetic stablecoin as collateral, require a public reserve breakdown with counterparty concentration limits. deUSD's 65% Stream allocation was technically disclosed but not widely scrutinized.
3. **Monitoring:** Real-time utilization alerts at 80% and 95% thresholds for flagged markets. At 80%, a curator should be reviewing the position. At 95%, active delisting should be on the table.
4. **Stress testing:** Simulate full collateral devaluation (price = $0) for every approved market allocation. The question is not "what happens if it drops 20%" but "what is the maximum loss if this collateral goes to zero and liquidations do not fire?"
5. **Curator concentration limits:** Cap the share of any single curator's book exposed to a single collateral type or counterparty. MEV Capital's dual-vault exposure to related assets amplified their loss.

---

*Dashboard: `streamlit run dashboard.py` — data sourced from Morpho GraphQL API and Dune Analytics on-chain queries.*
