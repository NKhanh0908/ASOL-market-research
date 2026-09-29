from __future__ import annotations

import argparse
import json
import sys
from contextlib import closing
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

from casual_scout.analysis.service import AnalysisService
from casual_scout.collection.jobs import CollectionBusyError
from casual_scout.config import Settings
from casual_scout.operations.backup import create_backup, restore_backup
from casual_scout.operations.survey import run_survey, survey_report
from casual_scout.storage import Repository

_ALLOWED_COUNTRIES = {
    "vn",
    "us",
    "bn",
    "kh",
    "id",
    "la",
    "my",
    "mm",
    "ph",
    "sg",
    "th",
    "tl",
}


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, OSError, ValueError):
            pass
    parser = argparse.ArgumentParser(
        prog="casual_scout",
        description="Casual Scout — iOS Casual Games Market Collection Tool",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # init
    init_parser = subparsers.add_parser("init", help="Initialize local SQLite database")
    init_parser.add_argument(
        "--data-dir",
        type=Path,
        default=Path("data"),
        help="Path to data directory (default: ./data)",
    )

    # collect
    collect_parser = subparsers.add_parser("collect", help="Trigger a collection run synchronously")
    collect_parser.add_argument(
        "--countries",
        "--markets",
        dest="countries",
        type=str,
        default="vn,th,id,my,ph,sg,la,kh,us",
        help="Comma-separated country codes (e.g. vn,us)",
    )
    collect_parser.add_argument(
        "--data-dir",
        type=Path,
        default=Path("data"),
        help="Path to data directory (default: ./data)",
    )
    collect_parser.add_argument(
        "--no-enrich",
        action="store_true",
        help="Skip fetching app metadata lookup",
    )
    collect_parser.add_argument(
        "--chart-type",
        "--feed-type",
        dest="chart_type",
        type=str,
        default="all",
        choices=["all", "free", "grossing", "top-free", "top-grossing"],
        help="Chart types to collect: all, free, grossing (default: all)",
    )
    collect_parser.add_argument(
        "--platform",
        "-p",
        choices=["all", "ios", "android"],
        default="ios",
        help="Target platform: ios, android, or all (default: ios)",
    )

    # work
    work_parser = subparsers.add_parser(
        "work", help="Worker process executing a specific queued run"
    )
    work_parser.add_argument(
        "--run-id",
        type=str,
        required=True,
        help="ID of the run to execute",
    )
    work_parser.add_argument(
        "--data-dir",
        type=Path,
        default=Path("data"),
        help="Path to data directory",
    )
    work_parser.add_argument(
        "--no-enrich",
        action="store_true",
        help="Skip fetching app metadata lookup",
    )

    # pipeline
    pipeline_parser = subparsers.add_parser(
        "pipeline", help="Run a collection worker and refresh daily analysis"
    )
    pipeline_parser.add_argument(
        "--run-id", type=str, required=True, help="ID of the run to execute"
    )
    pipeline_parser.add_argument(
        "--data-dir", type=Path, default=Path("data"), help="Path to data directory"
    )
    pipeline_parser.add_argument(
        "--no-enrich", action="store_true", help="Skip fetching app metadata lookup"
    )

    # serve
    serve_parser = subparsers.add_parser("serve", help="Start local web server")
    serve_parser.add_argument(
        "--data-dir",
        type=Path,
        default=Path("data"),
        help="Path to data directory",
    )
    serve_parser.add_argument(
        "--host",
        type=str,
        default="127.0.0.1",
        help="Host to bind (default: 127.0.0.1)",
    )
    serve_parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Port to bind (default: 8000)",
    )

    # survey
    survey_parser = subparsers.add_parser("survey", help="Execute scheduled survey run")
    survey_parser.add_argument(
        "--data-dir",
        type=Path,
        default=Path("data"),
        help="Path to data directory",
    )

    # survey-report
    report_parser = subparsers.add_parser("survey-report", help="Generate scheduling survey report")
    report_parser.add_argument(
        "--days",
        type=int,
        default=7,
        help="Number of days to analyze (default: 7)",
    )
    # backup
    backup_parser = subparsers.add_parser("backup", help="Create consistent local backup")
    backup_parser.add_argument(
        "--destination",
        type=Path,
        required=True,
        help="Destination directory for backup",
    )
    backup_parser.add_argument(
        "--data-dir",
        type=Path,
        default=Path("data"),
        help="Path to data directory",
    )

    # restore
    restore_parser = subparsers.add_parser("restore", help="Restore backup from manifest")
    restore_parser.add_argument(
        "--manifest",
        type=Path,
        required=True,
        help="Path to backup manifest.json",
    )
    restore_parser.add_argument(
        "--target-dir",
        "--data-dir",
        dest="target_dir",
        type=Path,
        default=Path("data"),
        help="Target data directory to restore into",
    )

    # analyze
    analyze_parser = subparsers.add_parser("analyze", help="Run daily ranking trend analysis")
    analyze_parser.add_argument(
        "--date",
        type=str,
        default=datetime.now(UTC).strftime("%Y-%m-%d"),
        help="Date to analyze in YYYY-MM-DD UTC (default: today)",
    )
    analyze_parser.add_argument(
        "--countries",
        "--markets",
        dest="countries",
        type=str,
        default=None,
        help="Comma-separated country codes (default: all)",
    )
    analyze_parser.add_argument(
        "--data-dir",
        type=Path,
        default=Path("data"),
        help="Path to data directory",
    )
    analyze_parser.add_argument(
        "--platform",
        "-p",
        choices=["ios", "android"],
        default="ios",
        help="Platform to analyze: ios or android (default: ios)",
    )

    # trends
    trends_parser = subparsers.add_parser("trends", help="Query daily trend rankings and signals")
    trends_parser.add_argument(
        "--date",
        type=str,
        default=datetime.now(UTC).strftime("%Y-%m-%d"),
        help="Date to query in YYYY-MM-DD UTC (default: today)",
    )
    trends_parser.add_argument(
        "--country",
        type=str,
        default="vn",
        help="Country code to query (default: vn)",
    )
    trends_parser.add_argument(
        "--signal",
        type=str,
        default=None,
        help="Filter by signal (fast_risers, new_entries, falling, steady)",
    )
    trends_parser.add_argument(
        "--chart-type",
        type=str,
        default="free",
        choices=["free", "grossing", "top-free", "top-grossing"],
        help="Chart to query: free or grossing (default: free)",
    )
    trends_parser.add_argument(
        "--platform",
        "-p",
        choices=["ios", "android"],
        default="ios",
        help="Platform to query: ios or android (default: ios)",
    )
    trends_parser.add_argument(
        "--json",
        action="store_true",
        help="Output raw JSON instead of table",
    )
    trends_parser.add_argument(
        "--data-dir",
        type=Path,
        default=Path("data"),
        help="Path to data directory",
    )

    # stats
    stats_parser = subparsers.add_parser("stats", help="Market statistics and opportunity radar")
    stats_subparsers = stats_parser.add_subparsers(dest="stats_command", required=True)

    # stats overview
    stats_overview_parser = stats_subparsers.add_parser(
        "overview", help="Show market summary and distribution"
    )
    stats_overview_parser.add_argument(
        "--date",
        type=str,
        default=datetime.now(UTC).strftime("%Y-%m-%d"),
        help="Target date YYYY-MM-DD",
    )
    stats_overview_parser.add_argument(
        "--country", type=str, default="all", help="Country code or 'all'"
    )
    stats_overview_parser.add_argument(
        "--platform",
        "-p",
        choices=["ios", "android"],
        default="ios",
        help="Platform to inspect: ios or android (default: ios)",
    )
    stats_overview_parser.add_argument(
        "--data-dir", type=Path, default=Path("data"), help="Path to data directory"
    )
    stats_overview_parser.add_argument("--json", action="store_true", help="Output raw JSON")

    # stats radar
    stats_radar_parser = stats_subparsers.add_parser(
        "radar", help="Show top opportunity radar games"
    )
    stats_radar_parser.add_argument(
        "--date",
        type=str,
        default=datetime.now(UTC).strftime("%Y-%m-%d"),
        help="Target date YYYY-MM-DD",
    )
    stats_radar_parser.add_argument(
        "--country", type=str, default="all", help="Country code or 'all'"
    )
    stats_radar_parser.add_argument("--limit", type=int, default=20, help="Number of games to show")
    stats_radar_parser.add_argument(
        "--monetization",
        type=str,
        default=None,
        help="Filter by monetization model (PURE_IAP, HYBRID, PURE_ADS, PAID_PREMIUM)",
    )
    stats_radar_parser.add_argument(
        "--platform",
        "-p",
        choices=["ios", "android"],
        default="ios",
        help="Platform to score: ios or android (default: ios)",
    )
    stats_radar_parser.add_argument(
        "--data-dir", type=Path, default=Path("data"), help="Path to data directory"
    )
    stats_radar_parser.add_argument("--json", action="store_true", help="Output raw JSON")

    # shortlist
    shortlist_parser = subparsers.add_parser("shortlist", help="Manage candidate game shortlist")
    shortlist_subparsers = shortlist_parser.add_subparsers(dest="shortlist_command", required=True)

    # shortlist list
    sl_list_parser = shortlist_subparsers.add_parser("list", help="List all shortlisted games")
    sl_list_parser.add_argument(
        "--status", type=str, help="Filter by status (CONSIDERING, PROTOTYPE, PASSED)"
    )
    sl_list_parser.add_argument(
        "--priority", type=str, help="Filter by priority (HIGH, MEDIUM, LOW)"
    )
    sl_list_parser.add_argument(
        "--data-dir", type=Path, default=Path("data"), help="Path to data directory"
    )
    sl_list_parser.add_argument("--json", action="store_true", help="Output raw JSON")

    # shortlist add
    sl_add_parser = shortlist_subparsers.add_parser(
        "add", help="Add or bookmark a game to shortlist"
    )
    sl_add_parser.add_argument("app_id", type=str, help="Apple Track ID")
    sl_add_parser.add_argument("--title", type=str, required=True, help="Game title")
    sl_add_parser.add_argument("--country", type=str, default="vn", help="Primary country")
    sl_add_parser.add_argument("--rank", type=int, default=100, help="Rank at bookmark")
    sl_add_parser.add_argument("--subgenre", type=str, help="Subgenre")
    sl_add_parser.add_argument("--mechanic", type=str, help="Mechanic")
    sl_add_parser.add_argument("--priority", type=str, default="MEDIUM", help="HIGH, MEDIUM, LOW")
    sl_add_parser.add_argument("--notes", type=str, help="Notes")
    sl_add_parser.add_argument(
        "--data-dir", type=Path, default=Path("data"), help="Path to data directory"
    )

    args = parser.parse_args(argv)

    if args.command == "init":
        repo = Repository(args.data_dir)
        repo.initialize()
        sys.stdout.write(f"Initialized database at {repo.database_path}\n")
        return 0

    if args.command == "collect":
        country_list = [c.strip().lower() for c in args.countries.split(",") if c.strip()]
        for c in country_list:
            if c not in _ALLOWED_COUNTRIES:
                sys.stderr.write(
                    f"Error: unknown country '{c}'. Allowed: {sorted(_ALLOWED_COUNTRIES)}\n"
                )
                return 1

        if args.platform in ("android", "all") and not set(country_list) <= {
            "vn",
            "th",
            "id",
            "my",
            "ph",
            "sg",
            "la",
            "kh",
            "us",
        }:
            sys.stderr.write("Error: unsupported Android market\n")
            return 1
        chart_types = None
        if getattr(args, "chart_type", "all") in ("free", "top-free"):
            chart_types = ["top-free"]
        elif getattr(args, "chart_type", "all") in ("grossing", "top-grossing"):
            chart_types = ["top-grossing"]
        elif getattr(args, "chart_type", "all") == "all":
            chart_types = ["top-free", "top-grossing"]

        repo = Repository(args.data_dir)
        repo.initialize()

        from casual_scout.collection import platforms

        def _log_progress(msg: str) -> None:
            sys.stdout.write(f"{msg}\n")
            sys.stdout.flush()

        statuses = []
        for target_plat in platforms.selected_platforms(getattr(args, "platform", "ios")):
            sys.stdout.write(f"\n🚀 Bắt đầu thu thập dữ liệu [Platform: {target_plat.upper()}]\n")
            sys.stdout.write(
                f"   Thị trường ({len(country_list)}): {', '.join(c.upper() for c in country_list)}\n"
            )
            chart_label = getattr(args, "chart_type", "all")
            sys.stdout.write(f"   Loại chart: {chart_label.upper()}\n")
            sys.stdout.write(
                f"   Làm giàu metadata: {'BẬT' if not args.no_enrich else 'TẮT (--no-enrich)'}\n\n"
            )
            sys.stdout.flush()

            req_key = f"cli-collect-{target_plat}-{uuid4()}"
            try:
                run_id, status = platforms.collect_platform(
                    repo,
                    target_plat,
                    country_list,
                    chart_types or ["top-free"],
                    req_key,
                    enrich=not args.no_enrich,
                    on_progress=_log_progress,
                )
            except (ValueError, KeyboardInterrupt, CollectionBusyError) as error:
                sys.stderr.write(f"Collection stopped: {error}\n")
                return 1
            statuses.append(status)
            sys.stdout.write(
                f"\n✅ Hoàn thành thu thập {target_plat.upper()} (Run ID: {run_id}) với trạng thái: {status.upper()}\n"
            )
            sys.stdout.flush()

        return 1 if any(s in ("failed", "interrupted") for s in statuses) else 0

    if args.command == "work":
        repo = Repository(args.data_dir)
        repo.initialize()
        from casual_scout.collection import platforms

        status = platforms.execute_run(repo, args.run_id, enrich=not args.no_enrich)
        return 0 if status in ("succeeded", "partial") else 1

    if args.command == "pipeline":
        repo = Repository(args.data_dir)
        repo.initialize()
        from casual_scout.collection import platforms

        status = platforms.execute_run(repo, args.run_id, enrich=not args.no_enrich)
        if status not in ("succeeded", "partial"):
            return 1
        with closing(repo._connect()) as connection:
            observed = connection.execute(
                """SELECT DISTINCT substr(s.observed_at,1,10) AS day, c.platform, c.country
                   FROM snapshots s JOIN market_runs mr ON mr.id=s.market_run_id
                   JOIN charts c ON c.id=mr.chart_id
                   WHERE mr.run_id=? AND (s.quality='complete' OR (c.platform='android' AND s.quality='partial'))
                   ORDER BY day, c.platform, c.country""",
                (args.run_id,),
            ).fetchall()
        groups: dict[tuple[str, str], list[str]] = {}
        for row in observed:
            groups.setdefault((row["day"], row["platform"]), []).append(row["country"])
        for (day, plat), countries in groups.items():
            AnalysisService(repo).analyze_date(day, countries, platform=plat)
        return 0

    if args.command == "serve":
        import uvicorn

        from casual_scout.web.app import create_app

        repo = Repository(args.data_dir)
        repo.initialize()
        settings = Settings(args.data_dir)
        app = create_app(settings)
        uvicorn.run(app, host=args.host, port=args.port)
        return 0

    if args.command == "survey":
        repo = Repository(args.data_dir)
        repo.initialize()
        run_id, status = run_survey(repo)
        if run_id:
            sys.stdout.write(f"Survey run {run_id} finished with status: {status}\n")
            return 0 if status in ("succeeded", "partial") else 1
        sys.stdout.write("Survey: No active slot window to execute at this time.\n")
        return 0

    if args.command == "survey-report":
        repo = Repository(args.data_dir)
        repo.initialize()
        now = datetime.now(UTC)
        start = now - timedelta(days=args.days)
        report = survey_report(repo, start, now)

        summary = report["summary"]
        md_lines = [
            f"# Báo Cáo Khảo Sát Lịch Chạy ({args.days} ngày gần nhất)",
            f"- Tổng số slot khảo sát: **{summary['total_slots']}**",
            f"- Số slot đã quan sát (Observed): **{summary['observed_count']}**",
            f"- Số slot bị lỡ (Missed): **{summary['missed_count']}**",
            f"- Tổng số request mẫu: **{summary['sample_count']}**",
            f"- Số lượt lỗi: **{summary['error_count']}**",
            f"- Median Latency: **{summary['median_latency_ms'] or 'null'} ms**",
            f"- P95 Latency: **{summary['p95_latency_ms'] or 'null'} ms**",
            "",
            "## Chi tiết từng Slot",
            "| Slot UTC | Trạng thái | Run ID | Ghi chú |",
            "|---|---|---|---|",
        ]
        for s in report["slots"][:28]:
            md_lines.append(
                f"| `{s['slot_utc']}` | {s['status']} | `{s.get('run_id') or '—'}` | {s.get('note') or '—'} |"
            )

        report_md = "\n".join(md_lines)
        sys.stdout.write(report_md + "\n\n")
        sys.stdout.write("JSON Data:\n" + json.dumps(report, indent=2, ensure_ascii=False) + "\n")
        return 0

    if args.command == "backup":
        repo = Repository(args.data_dir)
        repo.initialize()
        manifest_path = create_backup(repo, args.destination)
        sys.stdout.write(f"Backup completed successfully: {manifest_path}\n")
        return 0

    if args.command == "restore":
        restored_repo = restore_backup(args.manifest, args.target_dir)
        sys.stdout.write(f"Restore completed successfully into {restored_repo.data_dir}\n")
        return 0

    if args.command == "analyze":
        repo = Repository(args.data_dir)
        repo.initialize()
        service = AnalysisService(repo)
        country_list = (
            [c.strip().lower() for c in args.countries.split(",") if c.strip()]
            if args.countries
            else None
        )
        target_platform = getattr(args, "platform", "ios")
        result = service.analyze_date(args.date, country_list, platform=target_platform)
        sys.stdout.write(
            f"Analyzed {args.date} [{target_platform.upper()}] across {len(result['markets'])} markets: {', '.join(result['markets'])}\n"
        )
        return 0

    if args.command == "trends":
        repo = Repository(args.data_dir)
        repo.initialize()
        is_grossing = args.chart_type in ("grossing", "top-grossing")
        target_platform = getattr(args, "platform", "ios")
        signal_filter = None
        if args.signal:
            s = args.signal.strip().upper()
            if s in ("FAST_RISERS", "FAST_RISER"):
                signal_filter = "FAST_RISER"
            elif s in ("NEW_ENTRIES", "NEW_ENTRY"):
                signal_filter = "NEW_ENTRY"
            elif s in ("FALLING",):
                signal_filter = "FALLING"
            elif s in ("STEADY",):
                signal_filter = "STEADY"

        if is_grossing:
            if args.signal:
                sys.stderr.write("Error: --signal is only available for Top Free trends\n")
                return 1
            grossing_col = (
                "top-grossing" if target_platform == "android" else "topgrossingapplications"
            )
            snapshot_ref = repo.find_latest_complete_snapshot_for_date(
                args.date, args.country, collection=grossing_col, platform=target_platform
            )
            if snapshot_ref is None:
                records = []
            else:
                snapshot = repo.get_snapshot(snapshot_ref["id"])
                records = [
                    {
                        "app_id": entry["app_id"],
                        "current_rank": entry["rank"],
                        "name": entry["name"],
                        "chart_type": "top-grossing",
                    }
                    for entry in snapshot["entries"]
                ]
        else:
            records = repo.get_daily_analytics(
                args.date, args.country, signal_filter, platform=target_platform
            )

        if args.json:
            sys.stdout.write(json.dumps(records, indent=2, ensure_ascii=False) + "\n")
            return 0

        if is_grossing:
            md_lines = [
                f"# Top Grossing Rankings for {args.country.upper()} on {args.date} [{target_platform.upper()}]",
                f"Total records: **{len(records)}**",
                "",
                "| Rank | App ID | Title |",
                "|---|---|---|",
            ]
            for r in records:
                md_lines.append(f"| #{r['current_rank']} | `{r['app_id']}` | {r['name']} |")
            sys.stdout.write("\n".join(md_lines) + "\n")
            return 0

        # Output readable Top Free trend table
        md_lines = [
            f"# Daily Trends for {args.country.upper()} on {args.date} [{target_platform.upper()}]",
            f"Total records: **{len(records)}**",
            "",
            "| Rank | Delta 1D | Delta 3D | App ID | Signal | Mechanic | Cross-Markets |",
            "|---|---|---|---|---|---|---|",
        ]
        for r in records:
            d1 = f"{r['delta_1d']:+d}" if r["delta_1d"] is not None else "—"
            d3 = f"{r['delta_3d']:+d}" if r["delta_3d"] is not None else "—"
            cm = f"{r['cross_market_count']} ({','.join(r['cross_markets'])})"
            md_lines.append(
                f"| #{r['current_rank']} | {d1} | {d3} | `{r['app_id']}` | {r['signal']} | {r['mechanic']} | {cm} |"
            )
        sys.stdout.write("\n".join(md_lines) + "\n")
        return 0

    if args.command == "stats":
        repo = Repository(args.data_dir)
        repo.initialize()
        from casual_scout.web.views import get_dashboard_view

        target_platform = getattr(args, "platform", "ios")
        data = get_dashboard_view(
            repo, date_str=args.date, country=args.country, platform=target_platform
        )

        if args.stats_command == "overview":
            if args.json:
                sys.stdout.write(json.dumps(data["summary"], indent=2, ensure_ascii=False) + "\n")
                return 0

            s = data["summary"]
            sys.stdout.write(
                f"# Market Summary for {args.country.upper()} on {data['selected_date']}\n"
            )
            sys.stdout.write(f"- Total games: **{s['total_games']}**\n")
            sys.stdout.write(f"- Noteworthy games: **{s['noteworthy_count']}**\n")
            sys.stdout.write(f"- Fast Risers: **{s['fast_risers_count']}**\n")
            sys.stdout.write(f"- Dominant Subgenre: **{s['top_subgenre'] or '—'}**\n\n")

            sys.stdout.write("## Subgenre Breakdown\n")
            for g, val in s["genre_distribution"]["breakdown"].items():
                sys.stdout.write(f"- {g}: {val['count']} ({val['percentage']}%)\n")
            return 0

        if args.stats_command == "radar":
            radar_items = data["radar_items"]
            if args.monetization:
                m_filter = args.monetization.strip().upper()
                if m_filter in ("IAP", "PURE_IAP"):
                    radar_items = [
                        r for r in radar_items if r.get("monetization_model") == "PURE_IAP"
                    ]
                elif m_filter in ("HYBRID",):
                    radar_items = [
                        r for r in radar_items if r.get("monetization_model") == "HYBRID"
                    ]
                elif m_filter in ("ADS", "PURE_ADS"):
                    radar_items = [
                        r for r in radar_items if r.get("monetization_model") == "PURE_ADS"
                    ]
                elif m_filter in ("PAID", "PAID_PREMIUM"):
                    radar_items = [
                        r for r in radar_items if r.get("monetization_model") == "PAID_PREMIUM"
                    ]
                elif m_filter != "ALL":
                    radar_items = [
                        r for r in radar_items if r.get("monetization_model") == m_filter
                    ]

            radar_items = radar_items[: args.limit]
            if args.json:
                sys.stdout.write(json.dumps(radar_items, indent=2, ensure_ascii=False) + "\n")
                return 0

            sys.stdout.write(
                f"# Noteworthy Games (Top {len(radar_items)}) on {data['selected_date']}\n\n"
            )
            sys.stdout.write(
                "| Signal | Reasons | Rank | App ID | Title | Genre | Mechanic | Monetization | Observed presence |\n"
            )
            sys.stdout.write("|---|---|---|---|---|---|---|---|---|\n")
            for r in radar_items:
                sys.stdout.write(
                    f"| {r['noteworthy_label']} | {'; '.join(r['noteworthy_reasons'])} | #{r['current_rank']} | `{r['app_id']}` | {r.get('title') or r['app_id']} | {r.get('subgenre') or '—'} | {r.get('mechanic') or '—'} | {r.get('monetization_model') or '—'} | {r['presence_count'] if r['presence_count'] is not None else '—'}/{r['observed_market_count']} |\n"
                )
            return 0

    if args.command == "shortlist":
        repo = Repository(args.data_dir)
        repo.initialize()
        from casual_scout.stats.shortlist import ShortlistService

        service = ShortlistService(repo)

        if args.shortlist_command == "add":
            item = service.bookmark_game(
                app_id=args.app_id,
                title=args.title,
                primary_country=args.country,
                rank_at_bookmark=args.rank,
                subgenre=args.subgenre,
                mechanic=args.mechanic,
                priority=args.priority,
                notes=args.notes,
            )
            sys.stdout.write(
                f"Added/Updated shortlist item: {item['title']} (ID: {item['app_id']})\n"
            )
            return 0

        if args.shortlist_command == "list":
            items = service.list_shortlists(status=args.status, priority=args.priority)
            if args.json:
                sys.stdout.write(json.dumps(items, indent=2, ensure_ascii=False) + "\n")
                return 0

            sys.stdout.write(f"# Opportunity Shortlist ({len(items)} items)\n\n")
            sys.stdout.write(
                "| Status | Priority | Rank | App ID | Title | Genre/Mechanic | Notes |\n"
            )
            sys.stdout.write("|---|---|---|---|---|---|---|\n")
            for it in items:
                gm = f"{it.get('subgenre') or ''}/{it.get('mechanic') or ''}"
                sys.stdout.write(
                    f"| {it['status']} | {it['priority']} | #{it['rank_at_bookmark']} | `{it['app_id']}` | {it['title']} | {gm} | {it.get('notes') or '—'} |\n"
                )
            return 0

    return 0


if __name__ == "__main__":
    sys.exit(main())
