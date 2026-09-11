"""Monetization model classification and correlation matrix signals."""
from __future__ import annotations

from typing import Any


def classify_monetization_model(
    price: float | None = 0.0,
    iap_list: list[dict[str, Any]] | None = None,
    free_rank: int | None = None,
    grossing_rank: int | None = None,
) -> str:
    """
    Classify game monetization model into:
    - PAID_PREMIUM: price > 0
    - HYBRID: has IAP AND free_rank is present (or appears in both Free & Grossing)
    - PURE_IAP: has IAP and grossing_rank is present with no or low free presence
    - PURE_ADS: free with no IAP
    """
    p = float(price or 0.0)
    if p > 0:
        return "PAID_PREMIUM"

    iaps = iap_list or []
    has_iap = len(iaps) > 0

    if free_rank is not None and grossing_rank is not None:
        return "HYBRID"

    if has_iap and free_rank is not None:
        return "HYBRID"

    if grossing_rank is not None and free_rank is None:
        return "PURE_IAP"

    if has_iap:
        return "HYBRID"

    return "PURE_ADS"


def compute_monetization_efficiency(
    free_rank: int | None,
    grossing_rank: int | None,
) -> str | None:
    """
    Compute Download vs. Revenue efficiency flag:
    - MEGA_HIT: free_rank <= 15 and grossing_rank <= 15
    - HIGH_GROSSING_EFFICIENCY: (free_rank is None or free_rank > 30) and grossing_rank is not None and grossing_rank <= 30
    - VIRAL_FREE: free_rank is not None and free_rank <= 10 and grossing_rank is None
    - None otherwise
    """
    if free_rank is not None and grossing_rank is not None:
        if free_rank <= 15 and grossing_rank <= 15:
            return "MEGA_HIT"

    if grossing_rank is not None and grossing_rank <= 30:
        if free_rank is None or free_rank > 30:
            return "HIGH_GROSSING_EFFICIENCY"

    if free_rank is not None and free_rank <= 10 and grossing_rank is None:
        return "VIRAL_FREE"

    return None
