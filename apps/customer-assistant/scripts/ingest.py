"""CLI: (re)build the RAG knowledge base for one or all companies.

Usage:
    python scripts/ingest.py                       # ingest every company
    python scripts/ingest.py northwind-outdoors    # ingest one company

Run from the ``apps/customer-assistant`` directory (or set COMPANIES_ROOT).
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

# Make the package importable when run as a plain script.
_SRC = Path(__file__).resolve().parents[1] / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from customer_assistant.config import (  # noqa: E402
    CompanyConfigError,
    discover_companies,
    load_company,
)
from customer_assistant.knowledge_base import KnowledgeBase  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("ingest")

_APP_ROOT = Path(__file__).resolve().parents[1]
_COMPANIES_ROOT = _APP_ROOT / "companies"


def _ingest_one(company_id: str, company_dir: Path) -> int:
    profile = load_company(company_dir)
    kb = KnowledgeBase(profile)
    count = kb.ingest(reset=True)
    logger.info("%s: indexed %d chunks into %r", company_id, count, profile.collection_name)
    return count


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Ingest company knowledge bases.")
    parser.add_argument("company_id", nargs="?", help="company id (default: all)")
    args = parser.parse_args(argv)

    found = discover_companies(_COMPANIES_ROOT)
    if not found:
        logger.error("no companies found under %s", _COMPANIES_ROOT)
        return 1

    if args.company_id:
        if args.company_id not in found:
            logger.error("unknown company %r; known: %s", args.company_id, sorted(found))
            return 1
        targets = {args.company_id: found[args.company_id]}
    else:
        targets = found

    total = 0
    for company_id, company_dir in targets.items():
        try:
            total += _ingest_one(company_id, company_dir)
        except (CompanyConfigError, FileNotFoundError) as exc:
            logger.error("failed to ingest %r: %s", company_id, exc)
            return 1
    logger.info("done — %d chunks total across %d company(ies)", total, len(targets))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
