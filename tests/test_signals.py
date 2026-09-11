from casual_scout.analysis.signals import evaluate_signal


def test_signal_fast_riser_1d():
    signal, reasons = evaluate_signal(
        current_rank=5,
        rank_1d=30,
        delta_1d=25,
        rank_3d=None,
        delta_3d=None,
        is_new_entry=False,
    )
    assert signal == 'FAST_RISER'
    assert any('1d' in r for r in reasons)


def test_signal_fast_riser_3d():
    signal, reasons = evaluate_signal(
        current_rank=10,
        rank_1d=15,
        delta_1d=5,
        rank_3d=45,
        delta_3d=35,
        is_new_entry=False,
    )
    assert signal == 'FAST_RISER'
    assert any('3d' in r for r in reasons)


def test_signal_new_entry():
    signal, reasons = evaluate_signal(
        current_rank=20,
        rank_1d=None,
        delta_1d=None,
        rank_3d=None,
        delta_3d=None,
        is_new_entry=True,
    )
    assert signal == 'NEW_ENTRY'
    assert any('New entry' in r or 'new entry' in r.lower() for r in reasons)


def test_signal_falling():
    signal, reasons = evaluate_signal(
        current_rank=50,
        rank_1d=20,
        delta_1d=-30,
        rank_3d=15,
        delta_3d=-35,
        is_new_entry=False,
    )
    assert signal == 'FALLING'
    assert any('falling' in r.lower() or '-30' in r or 'dropped' in r.lower() for r in reasons)


def test_signal_steady():
    signal, _ = evaluate_signal(
        current_rank=10,
        rank_1d=12,
        delta_1d=2,
        rank_3d=9,
        delta_3d=-1,
        is_new_entry=False,
    )
    assert signal == 'STEADY'


def test_signal_null_deltas_no_baseline():
    signal, _ = evaluate_signal(
        current_rank=10,
        rank_1d=None,
        delta_1d=None,
        rank_3d=None,
        delta_3d=None,
        is_new_entry=False,
    )
    assert signal == 'STEADY'