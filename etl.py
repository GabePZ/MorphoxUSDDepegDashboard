#!/usr/bin/env python3
"""
ETL for the Morpho risk case study (xUSD / deUSD / sdeUSD stress).

Primary data source: Morpho public GraphQL API (https://api.morpho.org/graphql).
No query credits — cache responses under ./data/ and avoid redundant runs.

Optional: Dune Analytics. Free-tier credits are tiny; this script defaults to *no*
Dune calls. Use --dune latest to pull the last successful result without a new
execution, or --dune execute only when you accept fresh execution cost.

-------------------------------------------------------------------------------
DATA PLAN (what we ingest and why — for dashboard + debrief prep)
-------------------------------------------------------------------------------
1) Core snapshot (always): incident assets, collateral markets, liquidations,
   V1 vaults whose queues touch those markets, top TVL V2 vaults (curators),
   supplyingVaults per market.
2) Extended analysis (default on; --no-extended to skip): time series over the
   incident window for liquidity / borrow / collateral (markets), TVL & share
   price (vaults), Morpho-marked collateral USD price (oracle view), top
   borrowers per market, non-liquidation market flows, MetaMorpho vault
   deposits/withdraws, liquidation rollups.
3) Still out of scope without Dune / extra work: DEX TWAP vs oracle, off-chain
   curator comms, full V2 adapter→market mapping, subgraph-level traces.

Extended pulls use the *analysis window* (--history-start/--history-end or
default November 2025 UTC), which can differ from the liquidation time filter.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

import requests
from dotenv import load_dotenv

MORPHO_GRAPHQL = "https://api.morpho.org/graphql"
DATA_DIR = Path(__file__).resolve().parent / "data"
DEFAULT_CHAINS = [1, 8453, 42161]
DEFAULT_SYMBOLS = ["xUSD", "deUSD", "sdeUSD"]
VAULT_PAGE = 200
TX_PAGE = 500
MARKET_KEYS_PER_TX_QUERY = 40

MARKET_ACTIVITY_TYPES = [
    "MarketBorrow",
    "MarketRepay",
    "MarketSupply",
    "MarketWithdraw",
    "MarketSupplyCollateral",
    "MarketWithdrawCollateral",
]
METAMORPHO_TYPES = [
    "MetaMorphoDeposit",
    "MetaMorphoWithdraw",
    "MetaMorphoTransfer",
    "MetaMorphoFee",
]


def _ts_range_nov_2025() -> Tuple[int, int]:
    start = datetime(2025, 11, 1, tzinfo=timezone.utc)
    end = datetime(2025, 12, 1, tzinfo=timezone.utc)
    return (int(start.timestamp()), int(end.timestamp()) - 1)


def morpho_post(payload: Dict[str, Any], session: requests.Session) -> Dict[str, Any]:
    r = session.post(
        MORPHO_GRAPHQL,
        json=payload,
        headers={"Content-Type": "application/json"},
        timeout=120,
    )
    r.raise_for_status()
    body = r.json()
    if body.get("errors"):
        raise RuntimeError(f"GraphQL errors: {body['errors']}")
    data = body.get("data")
    if data is None:
        raise RuntimeError("GraphQL returned no data")
    return data


def morpho_post_maybe(payload: Dict[str, Any], session: requests.Session) -> Optional[Dict[str, Any]]:
    """POST GraphQL; return None on a single NOT_FOUND error (e.g. wrong vault version)."""
    r = session.post(
        MORPHO_GRAPHQL,
        json=payload,
        headers={"Content-Type": "application/json"},
        timeout=120,
    )
    r.raise_for_status()
    body = r.json()
    errors = body.get("errors") or []
    if errors:
        if len(errors) == 1 and errors[0].get("status") == "NOT_FOUND":
            return None
        raise RuntimeError(f"GraphQL errors: {errors}")
    return body.get("data")


def write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, default=str)


def fetch_incident_assets(
    session: requests.Session, chain_ids: Sequence[int], symbols: Sequence[str]
) -> List[Dict[str, Any]]:
    q = """
    query Assets($where: AssetsFilters) {
      assets(first: 1000, where: $where) {
        items {
          address
          symbol
          decimals
          chain { id network }
        }
      }
    }
    """
    data = morpho_post(
        {"query": q, "variables": {"where": {"chainId_in": list(chain_ids), "symbol_in": list(symbols)}}},
        session,
    )
    return data["assets"]["items"]


def fetch_markets_for_collateral(
    session: requests.Session, chain_id: int, collateral_addresses: Sequence[str]
) -> List[Dict[str, Any]]:
    if not collateral_addresses:
        return []
    q = """
    query Markets($where: MarketFilters!) {
      markets(first: 1000, where: $where, orderBy: BorrowAssetsUsd, orderDirection: Desc) {
        items {
          uniqueKey
          lltv
          oracleAddress
          irmAddress
          loanAsset { address symbol decimals chain { id } }
          collateralAsset { address symbol decimals chain { id } }
          state {
            borrowAssets borrowAssetsUsd
            supplyAssets supplyAssetsUsd
            collateralAssets collateralAssetsUsd
            liquidityAssets liquidityAssetsUsd
            utilization
            supplyApy borrowApy
          }
          warnings { type level }
        }
      }
    }
    """
    data = morpho_post(
        {
            "query": q,
            "variables": {
                "where": {
                    "chainId_in": [chain_id],
                    "collateralAssetAddress_in": list(collateral_addresses),
                }
            },
        },
        session,
    )
    return data["markets"]["items"]


def fetch_supplying_vaults(
    session: requests.Session, unique_key: str, chain_id: int
) -> List[Dict[str, Any]]:
    q = """
    query SupplyingVaults($uniqueKey: String!, $chainId: Int!) {
      marketByUniqueKey(uniqueKey: $uniqueKey, chainId: $chainId) {
        uniqueKey
        supplyingVaults {
          address
          symbol
          name
        }
      }
    }
    """
    data = morpho_post(
        {"query": q, "variables": {"uniqueKey": unique_key, "chainId": chain_id}},
        session,
    )
    m = data.get("marketByUniqueKey") or {}
    return m.get("supplyingVaults") or []


def fetch_vault_summary(
    session: requests.Session,
    incident_collateral_symbols: Sequence[str],
) -> Dict[str, Any]:
    """Fetch total vault count and which vaults have incident-asset allocations."""
    incident_syms = set(incident_collateral_symbols)
    q = """
    query VaultSummary($skip: Int!) {
      vaults(first: 500, skip: $skip, orderBy: TotalAssetsUsd, orderDirection: Desc) {
        pageInfo { count countTotal }
        items {
          address name symbol listed
          state {
            totalAssetsUsd
            allocation {
              supplyAssetsUsd
              market {
                uniqueKey
                collateralAsset { symbol }
                loanAsset { symbol }
              }
            }
          }
        }
      }
    }
    """
    all_vaults: List[Dict[str, Any]] = []
    total_count = 0
    skip = 0
    while True:
        data = morpho_post({"query": q, "variables": {"skip": skip}}, session)
        vaults_data = data.get("vaults") or {}
        items = vaults_data.get("items") or []
        if not total_count:
            total_count = (vaults_data.get("pageInfo") or {}).get("countTotal") or 0
        all_vaults.extend(items)
        if len(items) < 500:
            break
        skip += 500
        time.sleep(0.3)

    incident_vaults = []
    for v in all_vaults:
        state = v.get("state") or {}
        allocs = state.get("allocation") or []
        incident_allocs = []
        for a in allocs:
            mkt = a.get("market") or {}
            coll_sym = (mkt.get("collateralAsset") or {}).get("symbol") or ""
            if coll_sym in incident_syms:
                incident_allocs.append({
                    "market_key": mkt.get("uniqueKey"),
                    "collateral_symbol": coll_sym,
                    "loan_symbol": (mkt.get("loanAsset") or {}).get("symbol"),
                    "supply_usd": a.get("supplyAssetsUsd") or 0,
                })
        if incident_allocs:
            incident_vaults.append({
                "address": v.get("address"),
                "name": v.get("name"),
                "symbol": v.get("symbol"),
                "listed": v.get("listed"),
                "total_assets_usd": (state.get("totalAssetsUsd") or 0),
                "incident_allocations": incident_allocs,
            })

    total_listed_tvl = sum(
        float((v.get("state") or {}).get("totalAssetsUsd") or 0)
        for v in all_vaults if v.get("listed")
    )
    total_all_tvl = sum(
        float((v.get("state") or {}).get("totalAssetsUsd") or 0)
        for v in all_vaults
    )

    return {
        "total_vault_count": total_count,
        "fetched_count": len(all_vaults),
        "total_listed_tvl_usd": total_listed_tvl,
        "total_all_tvl_usd": total_all_tvl,
        "incident_vault_count": len(incident_vaults),
        "incident_vaults": incident_vaults,
    }


def fetch_liquidations(
    session: requests.Session,
    market_keys: Sequence[str],
    chain_ids: Sequence[int],
    ts_gte: Optional[int],
    ts_lte: Optional[int],
) -> List[Dict[str, Any]]:
    q = """
    query Liqs($where: TransactionFilters!, $first: Int!, $skip: Int!) {
      transactions(first: $first, skip: $skip, orderBy: Timestamp, orderDirection: Desc, where: $where) {
        pageInfo { count countTotal }
        items {
          timestamp
          blockNumber
          hash
          type
          chain { id network }
          user { address }
          data {
            ... on MarketLiquidationTransactionData {
              seizedAssets
              repaidAssets
              seizedAssetsUsd
              repaidAssetsUsd
              badDebtAssetsUsd
              badDebtShares
              liquidator
              market { uniqueKey }
            }
          }
        }
      }
    }
    """
    out: List[Dict[str, Any]] = []
    keys = list(market_keys)
    for i in range(0, len(keys), MARKET_KEYS_PER_TX_QUERY):
        chunk = keys[i : i + MARKET_KEYS_PER_TX_QUERY]
        where: Dict[str, Any] = {
            "type_in": ["MarketLiquidation"],
            "marketUniqueKey_in": chunk,
            "chainId_in": list(chain_ids),
        }
        if ts_gte is not None:
            where["timestamp_gte"] = ts_gte
        if ts_lte is not None:
            where["timestamp_lte"] = ts_lte
        skip = 0
        while True:
            data = morpho_post(
                {"query": q, "variables": {"where": where, "first": TX_PAGE, "skip": skip}},
                session,
            )
            conn = data["transactions"]
            items = conn["items"]
            out.extend(items)
            if len(items) < TX_PAGE:
                break
            skip += TX_PAGE
            time.sleep(0.05)
        time.sleep(0.05)
    return out


def fetch_vaults_v1_touching_markets(
    session: requests.Session,
    chain_ids: Sequence[int],
    target_market_keys: set,
) -> List[Dict[str, Any]]:
    """Morpho Vaults V1: scan allocations for links to incident markets."""
    q = """
    query Vaults($where: VaultFilters!, $first: Int!, $skip: Int!) {
      vaults(first: $first, skip: $skip, where: $where) {
        pageInfo { count countTotal }
        items {
          address
          name
          chain { id network }
          state {
            totalAssets
            totalAssetsUsd
            allocation {
              market { uniqueKey }
            }
          }
        }
      }
    }
    """
    hits: List[Dict[str, Any]] = []
    for chain_id in chain_ids:
        skip = 0
        while True:
            data = morpho_post(
                {
                    "query": q,
                    "variables": {
                        "where": {"chainId_in": [chain_id]},
                        "first": VAULT_PAGE,
                        "skip": skip,
                    },
                },
                session,
            )
            conn = data["vaults"]
            items = conn["items"]
            for v in items:
                alloc = (v.get("state") or {}).get("allocation") or []
                keys = {a["market"]["uniqueKey"] for a in alloc if a.get("market")}
                overlap = keys & target_market_keys
                if overlap:
                    hits.append(
                        {
                            "address": v["address"],
                            "name": v.get("name"),
                            "chain": v.get("chain"),
                            "totalAssetsUsd": (v.get("state") or {}).get("totalAssetsUsd"),
                            "matchingMarketUniqueKeys": sorted(overlap),
                        }
                    )
            if len(items) < VAULT_PAGE:
                break
            skip += VAULT_PAGE
            time.sleep(0.05)
    return hits


def fetch_vault_v2_curators_sample(
    session: requests.Session, chain_ids: Sequence[int], first: int
) -> List[Dict[str, Any]]:
    """Light snapshot of large V2 vaults (TVL) with curator addresses — not market-filtered."""
    q = """
    query V2($where: VaultV2sFilters!, $first: Int!) {
      vaultV2s(first: $first, orderBy: TotalAssetsUsd, orderDirection: Desc, where: $where) {
        items {
          address
          name
          symbol
          listed
          chain { id network }
          totalAssetsUsd
          liquidityUsd
          owner { address }
          curators {
            items {
              addresses { address }
            }
          }
        }
      }
    }
    """
    data = morpho_post(
        {"query": q, "variables": {"where": {"chainId_in": list(chain_ids)}, "first": first}},
        session,
    )
    return data["vaultV2s"]["items"]


def rollup_liquidations(liquidations: List[Dict[str, Any]]) -> Dict[str, Any]:
    by_market: Dict[str, Dict[str, Any]] = defaultdict(
        lambda: {
            "liquidation_count": 0,
            "bad_debt_usd": 0.0,
            "repaid_usd": 0.0,
            "seized_usd": 0.0,
        }
    )
    per_day: Dict[str, int] = defaultdict(int)
    for tx in liquidations:
        d = tx.get("data") or {}
        mk = (d.get("market") or {}).get("uniqueKey") or "unknown"
        agg = by_market[mk]
        agg["liquidation_count"] += 1
        agg["bad_debt_usd"] += float(d.get("badDebtAssetsUsd") or 0)
        agg["repaid_usd"] += float(d.get("repaidAssetsUsd") or 0)
        agg["seized_usd"] += float(d.get("seizedAssetsUsd") or 0)
        ts = tx.get("timestamp")
        if ts is not None:
            day = datetime.fromtimestamp(int(ts), tz=timezone.utc).strftime("%Y-%m-%d")
            per_day[day] += 1
    total_bad = sum(m["bad_debt_usd"] for m in by_market.values())
    return {
        "byMarket": {k: dict(v) for k, v in by_market.items()},
        "liquidationsPerDayUtc": dict(sorted(per_day.items())),
        "totals": {
            "liquidation_txs": len(liquidations),
            "bad_debt_usd": total_bad,
        },
    }


def fetch_market_history(
    session: requests.Session,
    unique_key: str,
    chain_id: int,
    options: Dict[str, Any],
) -> Dict[str, Any]:
    q = """
    query MHist($uniqueKey: String!, $chainId: Int!, $options: TimeseriesOptions!) {
      marketByUniqueKey(uniqueKey: $uniqueKey, chainId: $chainId) {
        uniqueKey
        collateralAsset { symbol address }
        loanAsset { symbol }
        historicalState {
          borrowAssetsUsd(options: $options) { x y }
          supplyAssetsUsd(options: $options) { x y }
          liquidityAssetsUsd(options: $options) { x y }
          collateralAssetsUsd(options: $options) { x y }
          utilization(options: $options) { x y }
          borrowApy(options: $options) { x y }
          supplyApy(options: $options) { x y }
        }
      }
    }
    """
    data = morpho_post(
        {"query": q, "variables": {"uniqueKey": unique_key, "chainId": chain_id, "options": options}},
        session,
    )
    m = data.get("marketByUniqueKey")
    if not m:
        raise RuntimeError(f"market not found: {unique_key}")
    return {"chainId": chain_id, **m}


def fetch_vault_v1_history(
    session: requests.Session, address: str, chain_id: int, options: Dict[str, Any]
) -> Dict[str, Any]:
    q = """
    query V1H($address: String!, $chainId: Int!, $options: TimeseriesOptions!) {
      vaultByAddress(address: $address, chainId: $chainId) {
        address
        name
        historicalState {
          totalAssetsUsd(options: $options) { x y }
          sharePriceUsd(options: $options) { x y }
        }
      }
    }
    """
    data = morpho_post(
        {"query": q, "variables": {"address": address, "chainId": chain_id, "options": options}},
        session,
    )
    v = data.get("vaultByAddress")
    if not v:
        raise RuntimeError(f"V1 vault not found: {address}")
    return {"vaultKind": "v1", "chainId": chain_id, **v}


def fetch_vault_v2_history(
    session: requests.Session, address: str, chain_id: int, options: Dict[str, Any]
) -> Dict[str, Any]:
    q = """
    query V2H($address: String!, $chainId: Int!, $options: TimeseriesOptions!) {
      vaultV2ByAddress(address: $address, chainId: $chainId) {
        address
        name
        historicalState {
          totalAssetsUsd(options: $options) { x y }
          sharePrice(options: $options) { x y }
          idleAssetsUsd(options: $options) { x y }
          realAssetsUsd(options: $options) { x y }
        }
      }
    }
    """
    data = morpho_post(
        {"query": q, "variables": {"address": address, "chainId": chain_id, "options": options}},
        session,
    )
    v = data.get("vaultV2ByAddress")
    if not v:
        raise RuntimeError(f"V2 vault not found: {address}")
    return {"vaultKind": "v2", "chainId": chain_id, **v}


def fetch_collateral_price_history(
    session: requests.Session, address: str, chain_id: int, options: Dict[str, Any]
) -> Dict[str, Any]:
    q = """
    query A($address: String!, $chainId: Int!, $options: TimeseriesOptions!) {
      assetByAddress(address: $address, chainId: $chainId) {
        address
        symbol
        historicalPriceUsd(options: $options) { x y }
      }
    }
    """
    data = morpho_post(
        {"query": q, "variables": {"address": address, "chainId": chain_id, "options": options}},
        session,
    )
    a = data.get("assetByAddress")
    if not a:
        raise RuntimeError(f"asset not found: {address}")
    return {"chainId": chain_id, **a}


def fetch_top_market_positions(
    session: requests.Session, unique_key: str, first: int
) -> List[Dict[str, Any]]:
    q = """
    query Pos($uk: String!, $n: Int!) {
      marketPositions(
        first: $n
        orderBy: BorrowShares
        orderDirection: Desc
        where: { marketUniqueKey_in: [$uk] }
      ) {
        items {
          user { address }
          state {
            borrowAssets borrowAssetsUsd
            collateral collateralUsd
            supplyAssets supplyAssetsUsd
          }
        }
      }
    }
    """
    data = morpho_post({"query": q, "variables": {"uk": unique_key, "n": first}}, session)
    return data["marketPositions"]["items"]


def fetch_market_activity_capped(
    session: requests.Session,
    unique_key: str,
    chain_id: int,
    ts_gte: int,
    ts_lte: int,
    cap: int,
) -> List[Dict[str, Any]]:
    q = """
    query Act($where: TransactionFilters!, $first: Int!, $skip: Int!) {
      transactions(first: $first, skip: $skip, orderBy: Timestamp, orderDirection: Desc, where: $where) {
        items {
          timestamp
          blockNumber
          hash
          type
          user { address }
          data { __typename }
        }
      }
    }
    """
    where: Dict[str, Any] = {
        "marketUniqueKey_in": [unique_key],
        "chainId_in": [chain_id],
        "type_in": list(MARKET_ACTIVITY_TYPES),
        "timestamp_gte": ts_gte,
        "timestamp_lte": ts_lte,
    }
    out: List[Dict[str, Any]] = []
    skip = 0
    while len(out) < cap:
        first = min(TX_PAGE, cap - len(out))
        data = morpho_post(
            {"query": q, "variables": {"where": where, "first": first, "skip": skip}},
            session,
        )
        items = data["transactions"]["items"]
        out.extend(items)
        if len(items) < first:
            break
        skip += first
        time.sleep(0.04)
    return out[:cap]


def fetch_metamorpho_activity_capped(
    session: requests.Session,
    vault_addresses: Sequence[str],
    chain_id: int,
    ts_gte: int,
    ts_lte: int,
    cap_per_vault: int,
) -> Dict[str, List[Dict[str, Any]]]:
    q = """
    query Mv($where: TransactionFilters!, $first: Int!, $skip: Int!) {
      transactions(first: $first, skip: $skip, orderBy: Timestamp, orderDirection: Desc, where: $where) {
        items {
          timestamp
          blockNumber
          hash
          type
          user { address }
          data { __typename }
        }
      }
    }
    """
    result: Dict[str, List[Dict[str, Any]]] = {}
    for addr in vault_addresses:
        where: Dict[str, Any] = {
            "vaultAddress_in": [addr],
            "chainId_in": [chain_id],
            "type_in": list(METAMORPHO_TYPES),
            "timestamp_gte": ts_gte,
            "timestamp_lte": ts_lte,
        }
        rows: List[Dict[str, Any]] = []
        skip = 0
        while len(rows) < cap_per_vault:
            first = min(TX_PAGE, cap_per_vault - len(rows))
            data = morpho_post(
                {"query": q, "variables": {"where": where, "first": first, "skip": skip}},
                session,
            )
            items = data["transactions"]["items"]
            rows.extend(items)
            if len(items) < first:
                break
            skip += first
            time.sleep(0.04)
        result[addr] = rows[:cap_per_vault]
    return result


def market_key_to_chain(flat_markets: List[Dict[str, Any]]) -> Dict[str, int]:
    key_to_chain: Dict[str, int] = {}
    for m in flat_markets:
        la = m.get("loanAsset") or {}
        ch = (la.get("chain") or {}).get("id")
        if ch is not None:
            key_to_chain[m["uniqueKey"]] = int(ch)
    return key_to_chain


def run_extended_analysis(
    session: requests.Session,
    bundle: Dict[str, Any],
    hist_start: int,
    hist_end: int,
    history_interval: str,
    positions_limit: int,
    market_activity_cap: int,
    metamorpho_cap: int,
    include_supplying_metamorpho: bool,
) -> Dict[str, Any]:
    """Heavy pulls for charts, rollups, and flow timelines."""
    options = {
        "startTimestamp": hist_start,
        "endTimestamp": hist_end,
        "interval": history_interval,
    }
    errors: List[Dict[str, Any]] = []
    flat = bundle["marketsFlat"]
    k2c = market_key_to_chain(flat)

    liquidation_summary = rollup_liquidations(bundle.get("liquidations") or [])

    historical_markets: List[Dict[str, Any]] = []
    for m in flat:
        uk = m["uniqueKey"]
        cid = k2c.get(uk)
        if cid is None:
            continue
        try:
            historical_markets.append(fetch_market_history(session, uk, cid, options))
        except Exception as exc:  # noqa: BLE001
            errors.append({"phase": "market_history", "market": uk, "error": str(exc)})
        time.sleep(0.05)

    v2_keys: Set[Tuple[str, int]] = {
        (v["address"].lower(), int(v["chain"]["id"])) for v in bundle["vaultV2TopByTvlSample"]
    }

    historical_vaults: List[Dict[str, Any]] = []
    for v in bundle["vaultsV1WithIncidentAllocation"]:
        addr = v["address"]
        cid = int(v["chain"]["id"])
        if (addr.lower(), cid) in v2_keys:
            continue
        try:
            historical_vaults.append(fetch_vault_v1_history(session, addr, cid, options))
        except Exception as exc:  # noqa: BLE001
            errors.append({"phase": "vault_v1_history", "vault": addr, "error": str(exc)})
        time.sleep(0.05)

    for v in bundle["vaultV2TopByTvlSample"]:
        addr = v["address"]
        cid = int(v["chain"]["id"])
        data = morpho_post_maybe(
            {
                "query": """
                query V2H($address: String!, $chainId: Int!, $options: TimeseriesOptions!) {
                  vaultV2ByAddress(address: $address, chainId: $chainId) {
                    address
                    name
                    historicalState {
                      totalAssetsUsd(options: $options) { x y }
                      sharePrice(options: $options) { x y }
                      idleAssetsUsd(options: $options) { x y }
                      realAssetsUsd(options: $options) { x y }
                    }
                  }
                }
                """,
                "variables": {"address": addr, "chainId": cid, "options": options},
            },
            session,
        )
        if not data or not data.get("vaultV2ByAddress"):
            errors.append({"phase": "vault_v2_history", "vault": addr, "error": "not_found"})
            continue
        historical_vaults.append(
            {"vaultKind": "v2", "chainId": cid, **data["vaultV2ByAddress"]}
        )
        time.sleep(0.05)

    collateral_prices: List[Dict[str, Any]] = []
    seen_asset: Set[Tuple[str, int]] = set()
    for a in bundle["incidentAssets"]:
        addr = a["address"]
        cid = int(a["chain"]["id"])
        key = (addr.lower(), cid)
        if key in seen_asset:
            continue
        seen_asset.add(key)
        try:
            collateral_prices.append(fetch_collateral_price_history(session, addr, cid, options))
        except Exception as exc:  # noqa: BLE001
            errors.append({"phase": "collateral_price", "asset": addr, "error": str(exc)})
        time.sleep(0.05)

    market_top_positions: Dict[str, Any] = {}
    for m in flat:
        uk = m["uniqueKey"]
        try:
            market_top_positions[uk] = fetch_top_market_positions(session, uk, positions_limit)
        except Exception as exc:  # noqa: BLE001
            errors.append({"phase": "market_positions", "market": uk, "error": str(exc)})
            market_top_positions[uk] = []
        time.sleep(0.04)

    market_activity: Dict[str, Any] = {}
    for m in flat:
        uk = m["uniqueKey"]
        cid = k2c.get(uk)
        if cid is None:
            continue
        try:
            market_activity[uk] = fetch_market_activity_capped(
                session, uk, cid, hist_start, hist_end, market_activity_cap
            )
        except Exception as exc:  # noqa: BLE001
            errors.append({"phase": "market_activity", "market": uk, "error": str(exc)})
            market_activity[uk] = []
        time.sleep(0.04)

    metamorpho_targets: Dict[str, int] = {}
    for v in bundle["vaultsV1WithIncidentAllocation"]:
        metamorpho_targets[v["address"]] = int(v["chain"]["id"])
    if include_supplying_metamorpho:
        for uk, svs in (bundle.get("supplyingVaultsByMarket") or {}).items():
            cid = k2c.get(uk)
            if cid is None:
                continue
            for sv in svs:
                metamorpho_targets[sv["address"]] = cid

    metamorpho_activity: Dict[str, Any] = {}
    by_chain_vaults: Dict[int, List[str]] = defaultdict(list)
    for addr, cid in metamorpho_targets.items():
        by_chain_vaults[cid].append(addr)
    for cid, addrs in by_chain_vaults.items():
        for addr in addrs:
            try:
                metamorpho_activity[addr] = fetch_metamorpho_activity_capped(
                    session, [addr], cid, hist_start, hist_end, metamorpho_cap
                ).get(addr, [])
            except Exception as exc:  # noqa: BLE001
                errors.append({"phase": "metamorpho", "vault": addr, "error": str(exc)})
                metamorpho_activity[addr] = []
            time.sleep(0.04)

    return {
        "fetchedAt": datetime.now(timezone.utc).isoformat(),
        "historyWindow": {
            "startTimestamp": hist_start,
            "endTimestamp": hist_end,
            "interval": history_interval,
        },
        "liquidationSummary": liquidation_summary,
        "historicalMarkets": historical_markets,
        "historicalVaults": historical_vaults,
        "collateralPrices": collateral_prices,
        "marketTopPositions": market_top_positions,
        "marketActivityTransactions": market_activity,
        "metamorphoVaultActivity": metamorpho_activity,
        "errors": errors,
    }


def parse_query_ids() -> List[int]:
    raw = os.environ.get("DUNE_QUERY_IDS", "").strip()
    if not raw:
        return []
    out: List[int] = []
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        out.append(int(part))
    return out


def dune_fetch_latest(query_id: int, api_key: str) -> Dict[str, Any]:
    from dune_client.client import DuneClient

    client = DuneClient(api_key)
    resp = client.get_latest_result(query_id, max_age_hours=8760)
    rows = resp.get_rows()
    return {
        "query_id": query_id,
        "execution_id": resp.execution_id,
        "state": str(resp.state),
        "row_count": len(rows),
        "rows": rows,
    }


def dune_execute(query_id: int, api_key: str) -> Dict[str, Any]:
    from dune_client.client import DuneClient
    from dune_client.query import QueryBase

    client = DuneClient(api_key)
    resp = client.run_query(QueryBase(name="etl", query_id=query_id))
    rows = resp.get_rows()
    return {
        "query_id": query_id,
        "execution_id": resp.execution_id,
        "state": str(resp.state),
        "row_count": len(rows),
        "rows": rows,
    }


def run_morpho_etl(
    session: requests.Session,
    chain_ids: Sequence[int],
    symbols: Sequence[str],
    liq_ts_gte: Optional[int],
    liq_ts_lte: Optional[int],
    skip_vault_scan: bool,
    v2_top_n: int,
) -> Dict[str, Any]:
    assets = fetch_incident_assets(session, chain_ids, symbols)
    by_chain: Dict[int, List[str]] = defaultdict(list)
    for a in assets:
        cid = a["chain"]["id"]
        by_chain[cid].append(a["address"])

    markets_by_chain: Dict[str, List[Dict[str, Any]]] = {}
    flat_markets: List[Dict[str, Any]] = []
    for cid, addrs in sorted(by_chain.items()):
        ms = fetch_markets_for_collateral(session, cid, addrs)
        markets_by_chain[str(cid)] = ms
        flat_markets.extend(ms)

    market_keys = [m["uniqueKey"] for m in flat_markets]
    key_to_chain: Dict[str, int] = {}
    for m in flat_markets:
        la = m.get("loanAsset") or {}
        ch = (la.get("chain") or {}).get("id")
        if ch is not None:
            key_to_chain[m["uniqueKey"]] = int(ch)

    supplying: Dict[str, List[Dict[str, Any]]] = {}
    for m in flat_markets:
        uk = m["uniqueKey"]
        cid = key_to_chain.get(uk)
        if cid is None:
            continue
        supplying[uk] = fetch_supplying_vaults(session, uk, cid)
        time.sleep(0.04)

    liquidations: List[Dict[str, Any]] = []
    if market_keys:
        liquidations = fetch_liquidations(
            session, market_keys, chain_ids, liq_ts_gte, liq_ts_lte
        )

    vaults_v1: List[Dict[str, Any]] = []
    if not skip_vault_scan and market_keys:
        vaults_v1 = fetch_vaults_v1_touching_markets(session, chain_ids, set(market_keys))

    vaults_v2_top = fetch_vault_v2_curators_sample(session, chain_ids, v2_top_n)

    vault_summary = fetch_vault_summary(session, list(symbols))

    return {
        "fetchedAt": datetime.now(timezone.utc).isoformat(),
        "chains": list(chain_ids),
        "symbols": list(symbols),
        "incidentAssets": assets,
        "marketsByChain": markets_by_chain,
        "marketsFlat": flat_markets,
        "supplyingVaultsByMarket": supplying,
        "liquidations": liquidations,
        "liquidationFilter": {"timestamp_gte": liq_ts_gte, "timestamp_lte": liq_ts_lte},
        "vaultsV1WithIncidentAllocation": vaults_v1,
        "vaultV2TopByTvlSample": vaults_v2_top,
        "vaultSummary": vault_summary,
    }


def main() -> int:
    load_dotenv()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dune",
        choices=("off", "latest", "execute"),
        default="off",
        help="off = skip Dune (default). latest = download last successful result (no new "
        "execution). execute = run queries (consumes Dune credits).",
    )
    parser.add_argument(
        "--chains",
        type=str,
        default=",".join(str(c) for c in DEFAULT_CHAINS),
        help="Comma-separated chain IDs (default: 1,8453,42161).",
    )
    parser.add_argument(
        "--symbols",
        type=str,
        default=",".join(DEFAULT_SYMBOLS),
        help="Comma-separated collateral symbols to resolve (default: xUSD,deUSD,sdeUSD).",
    )
    parser.add_argument(
        "--liquidations",
        choices=("nov2025", "all"),
        default="nov2025",
        help="nov2025: only liquidations in Nov 2025 UTC. all: entire history for incident markets.",
    )
    parser.add_argument(
        "--skip-vault-scan",
        action="store_true",
        help="Skip scanning all V1 vault allocations (faster; less curator/exposure context).",
    )
    parser.add_argument(
        "--v2-top",
        type=int,
        default=30,
        help="How many top TVL Vault V2s per snapshot (default: 30).",
    )
    parser.add_argument(
        "--no-morpho",
        action="store_true",
        help="Only run Dune steps (if any).",
    )
    parser.add_argument(
        "--no-extended",
        action="store_true",
        help="Skip extended analysis (history series, positions, activity txs, rollups).",
    )
    parser.add_argument(
        "--history-start",
        type=int,
        default=None,
        help="Analysis window start (Unix UTC). Default: 2025-11-01 00:00 UTC.",
    )
    parser.add_argument(
        "--history-end",
        type=int,
        default=None,
        help="Analysis window end (Unix UTC). Default: 2025-11-30 23:59:59 UTC.",
    )
    parser.add_argument(
        "--history-interval",
        type=str,
        default="DAY",
        help="Timeseries interval for Morpho historicalState (default: DAY).",
    )
    parser.add_argument(
        "--positions-limit",
        type=int,
        default=25,
        help="Top borrow-share market positions per incident market (default: 25).",
    )
    parser.add_argument(
        "--market-activity-cap",
        type=int,
        default=200,
        help="Max non-liquidation txs to keep per incident market in the analysis window.",
    )
    parser.add_argument(
        "--metamorpho-activity-cap",
        type=int,
        default=150,
        help="Max MetaMorpho txs per vault in the analysis window.",
    )
    parser.add_argument(
        "--include-supplying-metamorpho",
        action="store_true",
        help="Also pull MetaMorpho activity for markets' supplyingVaults addresses (more API calls).",
    )
    args = parser.parse_args()

    chain_ids = [int(x.strip()) for x in args.chains.split(",") if x.strip()]
    symbols = [x.strip() for x in args.symbols.split(",") if x.strip()]

    ts_gte: Optional[int]
    ts_lte: Optional[int]
    if args.liquidations == "nov2025":
        ts_gte, ts_lte = _ts_range_nov_2025()
    else:
        ts_gte, ts_lte = None, None

    hist_start = args.history_start if args.history_start is not None else _ts_range_nov_2025()[0]
    hist_end = args.history_end if args.history_end is not None else _ts_range_nov_2025()[1]

    DATA_DIR.mkdir(parents=True, exist_ok=True)

    if not args.no_morpho:
        session = requests.Session()
        bundle = run_morpho_etl(
            session,
            chain_ids,
            symbols,
            ts_gte,
            ts_lte,
            args.skip_vault_scan,
            args.v2_top,
        )
        if not args.no_extended:
            bundle["extended"] = run_extended_analysis(
                session,
                bundle,
                hist_start,
                hist_end,
                args.history_interval,
                args.positions_limit,
                args.market_activity_cap,
                args.metamorpho_activity_cap,
                args.include_supplying_metamorpho,
            )
        write_json(DATA_DIR / "morpho_bundle.json", bundle)
        write_json(DATA_DIR / "incident_assets.json", bundle["incidentAssets"])
        write_json(DATA_DIR / "markets.json", bundle["marketsFlat"])
        write_json(DATA_DIR / "liquidations.json", bundle["liquidations"])
        write_json(DATA_DIR / "vaults_v1_incident.json", bundle["vaultsV1WithIncidentAllocation"])
        write_json(DATA_DIR / "vaults_v2_top.json", bundle["vaultV2TopByTvlSample"])
        write_json(DATA_DIR / "supplying_vaults.json", bundle["supplyingVaultsByMarket"])
        write_json(DATA_DIR / "vault_summary.json", bundle["vaultSummary"])
        if not args.no_extended and bundle.get("extended"):
            ext = bundle["extended"]
            write_json(DATA_DIR / "liquidation_summary.json", ext["liquidationSummary"])
            write_json(DATA_DIR / "historical_markets.json", ext["historicalMarkets"])
            write_json(DATA_DIR / "historical_vaults.json", ext["historicalVaults"])
            write_json(DATA_DIR / "collateral_prices.json", ext["collateralPrices"])
            write_json(DATA_DIR / "market_top_positions.json", ext["marketTopPositions"])
            write_json(DATA_DIR / "market_activity_tx.json", ext["marketActivityTransactions"])
            write_json(DATA_DIR / "metamorpho_activity.json", ext["metamorphoVaultActivity"])
            write_json(DATA_DIR / "etl_extended_errors.json", ext["errors"])
        print(f"Wrote Morpho extracts under {DATA_DIR}/")

    if args.dune != "off":
        api_key = os.environ.get("DUNE_API_KEY", "").strip()
        if not api_key:
            print("DUNE_API_KEY missing; set it in .env for Dune steps.", file=sys.stderr)
            return 1
        qids = parse_query_ids()
        if not qids:
            print(
                "No Dune query IDs: set DUNE_QUERY_IDS in .env (comma-separated integers).",
                file=sys.stderr,
            )
            return 1
        if args.dune == "execute":
            print(
                "WARNING: --dune execute runs fresh executions and spends Dune credits.",
                file=sys.stderr,
            )
        for qid in qids:
            path = DATA_DIR / f"dune_query_{qid}.json"
            if args.dune == "latest":
                payload = dune_fetch_latest(qid, api_key)
            else:
                payload = dune_execute(qid, api_key)
            write_json(path, payload)
            print(f"Wrote {path} ({payload['row_count']} rows, state={payload['state']})")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
