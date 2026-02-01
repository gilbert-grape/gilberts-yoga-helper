"""
CLI commands for Gilbert's Yoga Helper.

Provides command-line interface for:
- Running crawls (for cron jobs)
- Database management

Usage:
    python -m backend.cli crawl
    python -m backend.cli --help
"""
import asyncio
import sys
import argparse

from backend.database import SessionLocal
from backend.services.crawler import (
    run_crawl_async,
    get_lock_holder_info,
    is_crawl_locked,
)
from backend.utils.logging import get_logger

logger = get_logger(__name__)


def cmd_crawl(args: argparse.Namespace) -> int:
    """
    Run a complete crawl of all active sources.

    Returns:
        0 on success (even with partial failures)
        1 on complete failure or exception
        2 if another crawl is already running
    """
    # Check if a crawl is already running (before starting)
    if is_crawl_locked():
        lock_holder = get_lock_holder_info()
        print(f"Crawl skipped - another crawl is already running: {lock_holder}", file=sys.stderr)
        logger.warning(f"CLI crawl skipped - lock held by: {lock_holder}")
        return 2

    logger.info("Starting crawl from CLI")
    print("Starting crawl...")

    session = SessionLocal()
    try:
        # Use trigger="cli" to identify CLI-initiated crawls in the lock file
        result = asyncio.run(run_crawl_async(session, trigger="cli"))

        # Print summary to stdout (for cron logs)
        print("\n" + "=" * 50)
        print("CRAWL COMPLETE")
        print("=" * 50)
        print(f"Sources attempted: {result.sources_attempted}")
        print(f"Sources succeeded: {result.sources_succeeded}")
        print(f"Sources failed: {result.sources_failed}")
        print(f"Listings scraped: {result.total_listings}")
        print(f"New matches: {result.new_matches}")
        print(f"Duplicates skipped: {result.duplicate_matches}")
        print(f"Duration: {result.duration_seconds:.1f} seconds")

        if result.failed_sources:
            print(f"\nFailed sources: {', '.join(result.failed_sources)}")

        print("=" * 50)

        # Return success if at least some sources succeeded
        if result.sources_succeeded > 0:
            print("\nCrawl completed successfully.")
            return 0
        elif result.sources_attempted == 0:
            print("\nNo sources to crawl.")
            return 0
        else:
            print("\nCrawl failed - all sources failed.")
            return 1

    except RuntimeError as e:
        # Lock acquisition failed (race condition)
        if "already running" in str(e):
            print(f"Crawl skipped - another crawl started: {e}", file=sys.stderr)
            logger.warning(f"CLI crawl aborted due to lock: {e}")
            return 2
        raise

    except Exception as e:
        logger.exception(f"Crawl failed with exception: {e}")
        print(f"\nCrawl failed with error: {e}", file=sys.stderr)
        return 1

    finally:
        session.close()


def main() -> int:
    """Main entry point for CLI."""
    parser = argparse.ArgumentParser(
        prog="yoga-helper",
        description="Gilbert's Yoga Helper CLI"
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Crawl command
    crawl_parser = subparsers.add_parser(
        "crawl",
        help="Run a complete crawl of all active sources"
    )
    crawl_parser.set_defaults(func=cmd_crawl)

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        return 0

    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
