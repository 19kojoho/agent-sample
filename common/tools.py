"""Shared mock tools for the credit-rating research helper.

Both the LangGraph and Strands variants call the same underlying functions
so traces look identical across the two frameworks.

The data is fictional. Issuer names below are real companies, but the
profile fields and rating history are made up for demonstration. Do not
treat any of this output as factual.
"""
from __future__ import annotations

from typing import Any

_ISSUER_PROFILES: dict[str, dict[str, Any]] = {
    "apple inc": {
        "issuer_name": "Apple Inc",
        "ticker": "AAPL",
        "sector": "Information Technology",
        "country": "United States",
        "hq_city": "Cupertino, CA",
        "last_filing_date": "2026-04-30",
        "market_cap_tier": "mega",
    },
    "microsoft corporation": {
        "issuer_name": "Microsoft Corporation",
        "ticker": "MSFT",
        "sector": "Information Technology",
        "country": "United States",
        "hq_city": "Redmond, WA",
        "last_filing_date": "2026-04-23",
        "market_cap_tier": "mega",
    },
    "tesla inc": {
        "issuer_name": "Tesla, Inc",
        "ticker": "TSLA",
        "sector": "Consumer Discretionary",
        "country": "United States",
        "hq_city": "Austin, TX",
        "last_filing_date": "2026-04-22",
        "market_cap_tier": "large",
    },
    "the boeing company": {
        "issuer_name": "The Boeing Company",
        "ticker": "BA",
        "sector": "Industrials",
        "country": "United States",
        "hq_city": "Arlington, VA",
        "last_filing_date": "2026-04-24",
        "market_cap_tier": "large",
    },
    "jpmorgan chase & co": {
        "issuer_name": "JPMorgan Chase & Co",
        "ticker": "JPM",
        "sector": "Financials",
        "country": "United States",
        "hq_city": "New York, NY",
        "last_filing_date": "2026-04-12",
        "market_cap_tier": "mega",
    },
}

_RATING_HISTORY: dict[str, list[dict[str, Any]]] = {
    "apple inc": [
        {"date": "2024-11-08", "action": "Affirm", "from_rating": "AA+", "to_rating": "AA+",
         "rationale_short": "Strong cash position and services growth offset hardware concentration risk."},
        {"date": "2022-03-14", "action": "Upgrade", "from_rating": "AA",  "to_rating": "AA+",
         "rationale_short": "Sustained free cash flow and shareholder return discipline."},
    ],
    "microsoft corporation": [
        {"date": "2025-08-19", "action": "Affirm", "from_rating": "AAA", "to_rating": "AAA",
         "rationale_short": "Diversified earnings, leading cloud position, conservative balance sheet."},
        {"date": "2020-09-30", "action": "Upgrade", "from_rating": "AA+", "to_rating": "AAA",
         "rationale_short": "Material reduction in debt-to-EBITDA and broadened recurring revenue base."},
    ],
    "tesla inc": [
        {"date": "2025-12-02", "action": "Upgrade", "from_rating": "BBB", "to_rating": "BBB+",
         "rationale_short": "Improved automotive margin and energy-segment scale."},
        {"date": "2023-10-04", "action": "Upgrade", "from_rating": "BBB-", "to_rating": "BBB",
         "rationale_short": "Investment grade migration on consistent positive free cash flow."},
    ],
    "the boeing company": [
        {"date": "2026-02-18", "action": "Downgrade", "from_rating": "BBB-", "to_rating": "BB+",
         "rationale_short": "Cash burn from production rate constraints and regulatory overhang."},
        {"date": "2024-05-30", "action": "Downgrade", "from_rating": "BBB", "to_rating": "BBB-",
         "rationale_short": "Persistent execution challenges on commercial aircraft programs."},
    ],
    "jpmorgan chase & co": [
        {"date": "2025-05-22", "action": "Affirm", "from_rating": "A+", "to_rating": "A+",
         "rationale_short": "Diversified franchise and strong capital ratios offset capital markets cyclicality."},
    ],
}


def _normalize(name: str) -> str:
    return name.lower().strip().rstrip(".").replace(",", "").replace("  ", " ")


def lookup_issuer_profile(issuer_name: str) -> dict[str, Any]:
    """Return the static profile for a known issuer.

    Args:
        issuer_name: Company name. Partial or punctuated names are tolerated.

    Returns:
        Dict with issuer_name, ticker, sector, country, hq_city,
        last_filing_date, market_cap_tier. If the issuer is not in our
        mock catalog, returns a dict with status == "not_found".
    """
    key = _normalize(issuer_name)
    for stored_key, profile in _ISSUER_PROFILES.items():
        if stored_key in key or key in stored_key:
            return {"status": "ok", **profile}
    return {
        "status": "not_found",
        "issuer_name": issuer_name,
        "message": "No profile on file. Available issuers: "
                   + ", ".join(p["issuer_name"] for p in _ISSUER_PROFILES.values()),
    }


def lookup_rating_history(issuer_name: str) -> dict[str, Any]:
    """Return the rating action history for a known issuer.

    Args:
        issuer_name: Company name. Partial or punctuated names are tolerated.

    Returns:
        Dict with issuer_name and an actions list (most recent first).
        Each action has date, action, from_rating, to_rating, rationale_short.
        If the issuer is not in our mock catalog, returns status == "not_found".
    """
    key = _normalize(issuer_name)
    for stored_key, actions in _RATING_HISTORY.items():
        if stored_key in key or key in stored_key:
            profile_name = _ISSUER_PROFILES[stored_key]["issuer_name"]
            return {"status": "ok", "issuer_name": profile_name, "actions": actions}
    return {
        "status": "not_found",
        "issuer_name": issuer_name,
        "message": "No rating actions on file for this issuer.",
    }


SYSTEM_PROMPT = (
    "You are a credit-rating research assistant. When an analyst asks about "
    "an issuer, use the lookup tools to gather facts before answering: call "
    "lookup_issuer_profile first to confirm the entity, then call "
    "lookup_rating_history to retrieve recent actions. Synthesize the result "
    "into a short briefing (4-6 sentences) that covers sector, country, the "
    "most recent rating action, and the trajectory. Cite specific dates and "
    "ratings from the tool output. Do not invent data the tools did not return."
)
