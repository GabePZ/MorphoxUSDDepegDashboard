#!/usr/bin/env python3
"""
ETL for the Morpho risk case study (xUSD / deUSD / sdeUSD stress).

Primary data source: Morpho public GraphQL API (https://api.morpho.org/graphql).
No query credits — cache responses under ./data/ and avoid redundant runs.

Optional: Dune Analytics. Free-tier credits are tiny; this script defaults to *no*
Dune calls. Use --dune latest to pull the last successful result without a new
execution, or --dune execute only when you accept fresh execution cost.
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
from typing import Any, Dict, List, Optional, Sequence, Tuple

import requests
from dotenv import load_dotenv

MORPHO_GRAPHQL = "https://api.morpho.org/graphql"
DATA_DIR = Path(__file__).resolve().parent / "data"
DEFAULT_CHAINS = [1, 8453, 42161]
DEFAULT_SYMBOLS = ["xUSD", "deUSD", "sdeUSD"]
VAULT_PAGE = 200
TX_PAGE = 500
MARKET_KEYS_PER_TX_QUERY = 40


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
    return body["data"]


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
    # Large max_age avoids implicit refresh / re-execution inside the client.
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
    args = parser.parse_args()

    chain_ids = [int(x.strip()) for x in args.chains.split(",") if x.strip()]
    symbols = [x.strip() for x in args.symbols.split(",") if x.strip()]

    ts_gte: Optional[int]
    ts_lte: Optional[int]
    if args.liquidations == "nov2025":
        ts_gte, ts_lte = _ts_range_nov_2025()
    else:
        ts_gte, ts_lte = None, None

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
        write_json(DATA_DIR / "morpho_bundle.json", bundle)
        # Split mirrors for smaller downstream tools
        write_json(DATA_DIR / "incident_assets.json", bundle["incidentAssets"])
        write_json(DATA_DIR / "markets.json", bundle["marketsFlat"])
        write_json(DATA_DIR / "liquidations.json", bundle["liquidations"])
        write_json(DATA_DIR / "vaults_v1_incident.json", bundle["vaultsV1WithIncidentAllocation"])
        write_json(DATA_DIR / "vaults_v2_top.json", bundle["vaultV2TopByTvlSample"])
        write_json(DATA_DIR / "supplying_vaults.json", bundle["supplyingVaultsByMarket"])
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
