from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from casual_scout.analysis.delta import (
    compute_cross_market_presence,
    compute_rank_deltas,
)
from casual_scout.analysis.monetization import (
    classify_monetization_model,
    compute_monetization_efficiency,
)
from casual_scout.analysis.signals import evaluate_signal
from casual_scout.analysis.taxonomy import classify_app
from casual_scout.storage import Repository


class AnalysisService:
    def __init__(self, repository: Repository) -> None:
        self.repository = repository

    def analyze_date(
        self, date_str: str, countries: list[str] | None = None
    ) -> dict[str, Any]:
        """Perform daily analysis for date_str (YYYY-MM-DD UTC) across specified or all markets."""
        target_date = date.fromisoformat(date_str)

        if countries:
            target_countries = [c.lower() for c in countries]
        else:
            target_countries = [
                'vn', 'us', 'bn', 'kh', 'id', 'la', 'my', 'mm', 'ph', 'sg', 'th'
            ]

        canonical_snapshots: dict[str, dict[str, Any]] = {}
        for country in target_countries:
            canonical = self.repository.get_canonical_snapshot(date_str, country)
            if canonical is None:
                latest = self.repository.find_latest_complete_snapshot_for_date(
                    date_str, country, collection="topfreeapplications"
                ) or self.repository.find_latest_complete_snapshot_for_date(
                    date_str, country
                )
                if latest is not None:
                    self.repository.save_canonical_snapshot(
                        date_str, country, latest['id'], latest['observed_at']
                    )
                    canonical = {
                        'date': date_str,
                        'country': country,
                        'snapshot_id': latest['id'],
                        'observed_at': latest['observed_at'],
                    }
            if canonical is not None:
                canonical_snapshots[country] = canonical

        current_snapshots_data: dict[str, dict[str, Any]] = {}
        country_app_maps: dict[str, list[str]] = {}

        for country, canonical in canonical_snapshots.items():
            snap_id = canonical['snapshot_id']
            snap_data = self.repository.get_snapshot(snap_id)
            current_snapshots_data[country] = snap_data
            country_app_maps[country] = [e['app_id'] for e in snap_data['entries']]

        cross_presence = compute_cross_market_presence(country_app_maps)
        analyzed_markets = []

        for country, snap_data in current_snapshots_data.items():
            current_entries_map = {
                e['app_id']: e['rank'] for e in snap_data['entries']
            }

            # Check for Top Grossing snapshot on same date/country
            grossing_entries_map: dict[str, int] = {}
            grossing_latest = self.repository.find_latest_complete_snapshot_for_date(
                date_str, country, collection="topgrossingapplications"
            )
            if grossing_latest is not None:
                grossing_snap = self.repository.get_snapshot(grossing_latest['id'])
                grossing_entries_map = {
                    e['app_id']: e['rank'] for e in grossing_snap['entries']
                }

            past_snapshots: dict[int, dict[str, int]] = {}
            for days_ago in (1, 3, 7):
                past_date_str = (
                    target_date - timedelta(days=days_ago)
                ).isoformat()
                past_canonical = self.repository.get_canonical_snapshot(
                    past_date_str, country
                )
                if past_canonical is None:
                    past_latest = (
                        self.repository.find_latest_complete_snapshot_for_date(
                            past_date_str, country, collection="topfreeapplications"
                        ) or self.repository.find_latest_complete_snapshot_for_date(
                            past_date_str, country
                        )
                    )
                    if past_latest is not None:
                        self.repository.save_canonical_snapshot(
                            past_date_str,
                            country,
                            past_latest['id'],
                            past_latest['observed_at'],
                        )
                        past_canonical = {
                            'date': past_date_str,
                            'country': country,
                            'snapshot_id': past_latest['id'],
                            'observed_at': past_latest['observed_at'],
                        }

                if past_canonical is not None:
                    past_snap = self.repository.get_snapshot(
                        past_canonical['snapshot_id']
                    )
                    past_snapshots[days_ago] = {
                        e['app_id']: e['rank'] for e in past_snap['entries']
                    }

            deltas = compute_rank_deltas(current_entries_map, past_snapshots)
            metadata_map = self.repository.get_snapshot_metadata(snap_data['id'])

            daily_records = []
            for entry in snap_data['entries']:
                app_id = entry['app_id']
                current_rank = entry['rank']
                free_rank = current_rank
                grossing_rank = grossing_entries_map.get(app_id)
                app_name = entry['name']
                delta_info = deltas.get(app_id, {})

                rank_1d = delta_info.get('rank_1d_ago')
                delta_1d = delta_info.get('delta_1d')
                rank_3d = delta_info.get('rank_3d_ago')
                delta_3d = delta_info.get('delta_3d')
                rank_7d = delta_info.get('rank_7d_ago')
                delta_7d = delta_info.get('delta_7d')
                is_new_entry = delta_info.get('is_new_entry', False)

                signal, signal_reasons = evaluate_signal(
                    current_rank=current_rank,
                    rank_1d=rank_1d,
                    delta_1d=delta_1d,
                    rank_3d=rank_3d,
                    delta_3d=delta_3d,
                    is_new_entry=is_new_entry,
                )

                meta = metadata_map.get(app_id, {})
                genres = meta.get('genres') or entry.get('source_genres') or []
                description = meta.get('description') or ''

                taxonomy = classify_app(
                    genres=genres, title=app_name, description=description
                )

                price = meta.get('price', 0.0)
                iap_list = meta.get('inAppPurchases') or meta.get('in_app_purchases') or []
                monetization_model = classify_monetization_model(
                    price=price,
                    iap_list=iap_list,
                    free_rank=free_rank,
                    grossing_rank=grossing_rank,
                )
                monetization_efficiency_flag = compute_monetization_efficiency(
                    free_rank=free_rank,
                    grossing_rank=grossing_rank,
                )

                app_cross_markets = cross_presence.get(app_id, [country])
                cross_count = len(app_cross_markets)

                daily_records.append({
                    'date': date_str,
                    'country': country,
                    'app_id': app_id,
                    'current_rank': current_rank,
                    'rank_1d_ago': rank_1d,
                    'delta_1d': delta_1d,
                    'rank_3d_ago': rank_3d,
                    'delta_3d': delta_3d,
                    'rank_7d_ago': rank_7d,
                    'delta_7d': delta_7d,
                    'signal': signal,
                    'signal_reasons': signal_reasons,
                    'subgenre': taxonomy['subgenre'],
                    'mechanic': taxonomy['mechanic'],
                    'mechanic_evidence': taxonomy['evidence'],
                    'mechanic_confidence': taxonomy['confidence'],
                    'cross_market_count': cross_count,
                    'cross_markets': app_cross_markets,
                    'grossing_rank': grossing_rank,
                    'free_rank': free_rank,
                    'monetization_model': monetization_model,
                    'monetization_efficiency_flag': monetization_efficiency_flag,
                })

            self.repository.save_daily_analytics(daily_records)
            analyzed_markets.append(country)

        return {
            'status': 'completed',
            'date': date_str,
            'markets': analyzed_markets,
        }