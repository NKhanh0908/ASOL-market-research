from casual_scout.analysis.monetization import (
    classify_monetization_model,
    compute_monetization_efficiency,
)


def test_classify_paid_premium():
    model = classify_monetization_model(price=2.99, iap_list=[], free_rank=None, grossing_rank=5)
    assert model == "PAID_PREMIUM"


def test_classify_hybrid():
    model = classify_monetization_model(price=0.0, iap_list=[{"name": "No Ads", "price": 1.99}], free_rank=10, grossing_rank=25)
    assert model == "HYBRID"


def test_classify_pure_ads():
    model = classify_monetization_model(price=0.0, iap_list=[], free_rank=5, grossing_rank=None)
    assert model == "PURE_ADS"


def test_classify_pure_iap():
    # App is heavily grossing without free rank or has high IAP tiers
    model = classify_monetization_model(price=0.0, iap_list=[{"name": "1000 Gems", "price": 99.99}], free_rank=None, grossing_rank=12)
    assert model == "PURE_IAP"


def test_monetization_efficiency_signals():
    # Whale monetization: Free #60 (or >30), Grossing #15 (<=30)
    sig1 = compute_monetization_efficiency(free_rank=60, grossing_rank=15)
    assert sig1 == "HIGH_GROSSING_EFFICIENCY"

    # Mega Hit: Free #3 (<=15), Grossing #5 (<=15)
    sig2 = compute_monetization_efficiency(free_rank=3, grossing_rank=5)
    assert sig2 == "MEGA_HIT"

    # Viral Free: Free #2 (<=10), Not in Grossing
    sig3 = compute_monetization_efficiency(free_rank=2, grossing_rank=None)
    assert sig3 == "VIRAL_FREE"

    # Normal case: Free #50, Grossing #80 -> None
    sig4 = compute_monetization_efficiency(free_rank=50, grossing_rank=80)
    assert sig4 is None
