from __future__ import annotations


def evaluate_signal(
    current_rank: int,
    rank_1d: int | None,
    delta_1d: int | None,
    rank_3d: int | None,
    delta_3d: int | None,
    is_new_entry: bool = False,
) -> tuple[str, list[str]]:
    """Determine signal and reasons for a game based on rank deltas and entry status."""
    reasons: list[str] = []

    if is_new_entry:
        reasons.append(f'New entry into Top 100 at rank #{current_rank}')
        return 'NEW_ENTRY', reasons

    is_fast_riser = False
    if delta_1d is not None and delta_1d >= 20:
        reasons.append(f'delta_1d >= 20 (+{delta_1d})')
        is_fast_riser = True
    if delta_3d is not None and delta_3d >= 30:
        reasons.append(f'delta_3d >= 30 (+{delta_3d})')
        is_fast_riser = True

    if is_fast_riser:
        return 'FAST_RISER', reasons

    is_falling = False
    if delta_1d is not None and delta_1d <= -20:
        reasons.append(f'delta_1d <= -20 ({delta_1d})')
        is_falling = True
    if delta_3d is not None and delta_3d <= -30:
        reasons.append(f'delta_3d <= -30 ({delta_3d})')
        is_falling = True

    if is_falling:
        return 'FALLING', reasons

    if delta_1d is not None:
        reasons.append(f'Steady rank movement (1d: {delta_1d:+d})')
    else:
        reasons.append('Baseline data not available')

    return 'STEADY', reasons