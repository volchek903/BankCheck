from __future__ import annotations

import argparse
import asyncio
import logging

from app.bot import FinanceBotApp
from app.config import load_settings
from app.scheduler import create_scheduler


def configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )


async def async_main(run_once: bool) -> None:
    settings = load_settings()
    app = FinanceBotApp(settings)
    scheduler = create_scheduler(app)

    try:
        if run_once:
            logging.getLogger(__name__).info("Running one-shot report delivery")
            await app.send_scheduled_reports()
            return

        await app.set_commands()
        scheduler.start()
        logging.getLogger(__name__).info("Scheduler started with timezone %s", settings.timezone)
        await app.run_polling()
    finally:
        if scheduler.running:
            scheduler.shutdown(wait=False)
        await app.close()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Telegram finance bot for Belarus banks")
    parser.add_argument(
        "--once",
        action="store_true",
        help="Send all enabled reports once and exit",
    )
    return parser.parse_args()


def main() -> None:
    configure_logging()
    args = parse_args()
    asyncio.run(async_main(run_once=args.once))


if __name__ == "__main__":
    main()
