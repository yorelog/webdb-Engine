"""Command-line interface for webdb-Engine.

Usage examples::

    webdb init-db
    webdb collect --url https://example.com
    webdb sync --task-id <uuid>
    webdb export-training
"""

from __future__ import annotations

import argparse
import asyncio


def _cmd_init_db(args: argparse.Namespace) -> None:  # noqa: ARG001
    from webdb.database.engine import init_db
    init_db()
    print("Database initialised.")


def _cmd_collect(args: argparse.Namespace) -> None:
    from webdb.collector.page_collector import PageCollector

    async def _run():
        async with PageCollector() as collector:
            page = await collector.collect(args.url)
        print(f"Collected: {page.url}")
        print(f"  Title : {page.title}")
        print(f"  Hash  : {page.content_hash}")
        print(f"  DOM   : {len(page.html)} chars")
        print(f"  AX    : {type(page.accessibility_tree).__name__}")

    asyncio.run(_run())


def _cmd_export_training(args: argparse.Namespace) -> None:
    from pathlib import Path

    from webdb.training.data_pipeline import TrainingDataPipeline

    output_dir = Path(args.output_dir) if args.output_dir else None
    pipeline = TrainingDataPipeline(output_dir=output_dir)
    counts = pipeline.export()
    if counts:
        for path, count in counts.items():
            print(f"  {count:>6} records → {path}")
    else:
        print("No unexported training records found.")


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="webdb",
        description="webdb-Engine: Web-as-Database automation engine",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # init-db
    p_init = sub.add_parser("init-db", help="Initialise the knowledge base database.")
    p_init.set_defaults(func=_cmd_init_db)

    # collect
    p_collect = sub.add_parser("collect", help="Collect a page from a URL.")
    p_collect.add_argument("--url", required=True, help="URL to collect.")
    p_collect.set_defaults(func=_cmd_collect)

    # export-training
    p_export = sub.add_parser("export-training", help="Export training records to JSONL.")
    p_export.add_argument("--output-dir", default=None, help="Override output directory.")
    p_export.set_defaults(func=_cmd_export_training)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
