"""Standalone background worker entrypoint.

Run as its own process (or single-replica service) so jobs execute once. The
API runs with ENABLE_BACKGROUND_WORKER=false in production and this process
owns the queue.

    python -m app.workers.standalone
"""

from __future__ import annotations

import asyncio
import logging

from app.workers.runner import run_worker

logging.basicConfig(level=logging.INFO, format="%(levelname)-5s %(name)s: %(message)s")


def main() -> None:
    try:
        asyncio.run(run_worker())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
