from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path

from .adapters import fetch_enabled_ats_sources
from .connections import build_connection_rankings, import_linkedin_export
from .docx_import import recruiter_rows_from_docx
from .io import write_csv
from .pipeline import build
from .recruiters import RECRUITER_FIELDS, validate_recruiters
from .sheets import create_google_sheet, pull_from_sheet, push_to_sheet
from .tool_imports import import_apify_jobs, import_fullenrich_export
from .workflow import build_enrichment_queue, build_weekly_queue, ensure_workflow_files


def main() -> None:
    parser = argparse.ArgumentParser(description="Build product-role outreach review exports.")
    parser.add_argument(
        "command",
        choices=[
            "init",
            "unlock-code",
            "build",
            "fetch-ats",
            "setup-workflow",
            "build-enrichment-queue",
            "build-weekly-queue",
            "import-fullenrich-export",
            "import-apify-jobs",
            "create-google-sheet",
            "push-sheet",
            "pull-sheet",
            "import-recruiters-docx",
            "validate-recruiters",
            "import-linkedin-export",
            "build-connection-rankings",
            "serve",
            "discovery-start",
            "discovery-import",
            "discovery-progress",
            "discovery-finish",
        ],
    )
    parser.add_argument("input_path", nargs="?", help="Input file path for import commands.")
    parser.add_argument("--data-dir", default="data", help="Directory containing seed CSV files.")
    parser.add_argument("--out-dir", default="out", help="Directory for generated CSV exports.")
    parser.add_argument("--today", default="", help="Override today's date as YYYY-MM-DD for reproducible scoring.")
    parser.add_argument("--title", default="Apply Desk Job Search", help="Title for a new Google Sheet.")
    parser.add_argument("--spreadsheet-id", default="", help="Existing Google Sheets spreadsheet ID.")
    parser.add_argument("--limit", type=int, default=30, help="Queue/export row limit where applicable.")
    parser.add_argument("--host", default="127.0.0.1", help="Host for the local web app.")
    parser.add_argument("--port", type=int, default=8765, help="Port for the local web app.")
    parser.add_argument("--sources", default="", help="Comma-separated discovery source IDs.")
    parser.add_argument("--run-id", default="", help="Manual discovery run ID.")
    parser.add_argument("--source-id", default="", help="Manual discovery source ID.")
    parser.add_argument("--phase", default="", help="Reader progress message.")
    parser.add_argument("--error", default="", help="Reader failure message.")
    args = parser.parse_args()

    project_dir = Path.cwd()
    if args.command == 'unlock-code':
        import json
        path=project_dir / 'data/.session-key'
        if not path.exists(): raise SystemExit('Start the local server first.')
        print(json.loads(path.read_text())['code'])
        return
    if args.command == 'init':
        from .initialization import initialize_workspace
        initialize_workspace(project_dir)
        print('Initialized local workspace without overwriting existing files.')
        return
    if args.command.startswith("discovery-"):
        import json
        from .manual_discovery import start_run, import_source, update_source, finish_run
        if args.command == "discovery-start":
            result = start_run(project_dir, args.sources.split(",") if args.sources else None)
        elif args.command == "discovery-import":
            if not args.input_path:
                raise SystemExit("Provide a source evidence JSON file")
            result = import_source(project_dir, json.loads(Path(args.input_path).read_text()))
            build(project_dir / "data", project_dir / "out")
        elif args.command == "discovery-progress":
            result = update_source(project_dir, args.run_id, args.source_id, phase=args.phase, error=args.error)
        else:
            result = finish_run(project_dir, args.run_id)
        print(json.dumps(result, ensure_ascii=False))
        return

    if args.command == "serve":
        from .web import serve

        serve(project_dir, host=args.host, port=args.port)
        return

    if args.command == "setup-workflow":
        ensure_workflow_files(Path(args.data_dir))
        print("Set up workflow files: contacts CRM, message log, and workflow config.")
        return

    if args.command == "import-linkedin-export":
        if not args.input_path:
            raise SystemExit("input_path is required for import-linkedin-export")
        counts = import_linkedin_export(Path(args.input_path), project_dir)
        ranking_counts = build_connection_rankings(Path(args.data_dir), Path(args.out_dir))
        print(
            "Imported LinkedIn export: "
            f"{counts['connections']} connections, {counts['with_messages']} with message history, "
            f"{ranking_counts['tier1']} Tier 1, {ranking_counts['tier2']} Tier 2"
        )
        return

    if args.command == "build-connection-rankings":
        today = date.fromisoformat(args.today) if args.today else None
        counts = build_connection_rankings(Path(args.data_dir), Path(args.out_dir), today=today)
        print(
            "Built connection rankings: "
            f"{counts['tier1']} Tier 1, {counts['tier2']} Tier 2, {counts['watchlist']} watchlist"
        )
        return

    if args.command == "build-enrichment-queue":
        counts = build_enrichment_queue(Path(args.data_dir), Path(args.out_dir), limit=args.limit)
        print(f"Built FullEnrich queue: {counts['queued']} contacts into {Path(args.out_dir) / 'fullenrich_queue.csv'}")
        return

    if args.command == "build-weekly-queue":
        today = date.fromisoformat(args.today) if args.today else None
        counts = build_weekly_queue(Path(args.data_dir), Path(args.out_dir), today=today)
        print(
            "Built weekly queue: "
            f"{counts['new']} new, {counts['follow_ups']} follow-ups, {counts['total']} total"
        )
        return

    if args.command == "import-fullenrich-export":
        if not args.input_path:
            raise SystemExit("input_path is required for import-fullenrich-export")
        counts = import_fullenrich_export(Path(args.input_path), Path(args.data_dir) / "contacts_seed.csv")
        print(f"Imported FullEnrich export: {counts['updated']} updated, {counts['added']} added")
        return

    if args.command == "import-apify-jobs":
        if not args.input_path:
            raise SystemExit("input_path is required for import-apify-jobs")
        counts = import_apify_jobs(Path(args.input_path), Path(args.data_dir) / "jobs_seed.csv")
        print(
            "Imported Apify jobs: "
            f"{counts['added']} added, {counts['skipped_linkedin']} LinkedIn rows skipped, "
            f"{counts['skipped_non_product']} non-product rows skipped"
        )
        return

    if args.command == "create-google-sheet":
        result = create_google_sheet(project_dir, args.title)
        print(f"Created Google Sheet: {result['spreadsheet_url']}")
        return

    if args.command == "push-sheet":
        counts = push_to_sheet(project_dir, spreadsheet_id=args.spreadsheet_id or None)
        print(f"Pushed {counts['tabs']} tabs to Google Sheets")
        return

    if args.command == "pull-sheet":
        counts = pull_from_sheet(project_dir, spreadsheet_id=args.spreadsheet_id or None)
        print(f"Pulled {counts['tabs']} editable tabs from Google Sheets")
        return

    if args.command == "fetch-ats":
        data_dir = Path(args.data_dir)
        count = fetch_enabled_ats_sources(data_dir / "ats_sources.csv", data_dir / "jobs_fetched.csv")
        print(f"Fetched {count} ATS roles into {data_dir / 'jobs_fetched.csv'}")
        return

    if args.command == "import-recruiters-docx":
        if not args.input_path:
            raise SystemExit("input_path is required for import-recruiters-docx")
        data_dir = Path(args.data_dir)
        rows = recruiter_rows_from_docx(Path(args.input_path))
        write_csv(data_dir / "recruiters_seed.csv", rows, RECRUITER_FIELDS)
        print(f"Imported {len(rows)} recruiters into {data_dir / 'recruiters_seed.csv'}")
        return

    if args.command == "validate-recruiters":
        counts = validate_recruiters(Path(args.data_dir), Path(args.out_dir))
        print(
            "Validated recruiters: "
            f"{counts['recruiters']} total, {counts['high']} high, "
            f"{counts['review']} review, {counts['low']} low"
        )
        return

    if args.command == "build":
        today = date.fromisoformat(args.today) if args.today else None
        counts = build(Path(args.data_dir), Path(args.out_dir), today=today)
        print(
            "Built exports: "
            f"{counts['roles']} roles, {counts['contacts']} contacts, "
            f"{counts['tier1']} Tier 1, {counts['tier2']} Tier 2"
        )


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, FileNotFoundError) as exc:
        raise SystemExit(str(exc)) from exc
