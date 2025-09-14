# SPDX-License-Identifier: MIT
# Copyright (c) 2018-2024 Amano LLC
# Copyright (c) 2025 Elinsrc

import logging
from loguru import logger
import asyncio
import platform
import sys

from hydrogram import idle

from .bot import MikuBot
from .database import database
from .utils import http, InterceptHandler

logging.basicConfig(handlers=[InterceptHandler()], level=0, force=True)

# To avoid some annoying log
logging.getLogger("hydrogram.syncer").setLevel(logging.WARNING)
logging.getLogger("hydrogram.client").setLevel(logging.WARNING)

logger.remove()

logger.add(
    sys.stdout,
    format="[<green>{time:YYYY-MM-DD HH:mm:ss}</green>] "
           "[<level>{level}</level>] "
           "<white>{name}</white>.<white>{function}</white>: "
           "<level>{message}</level>",
    level="INFO",
    colorize=True,
)

try:
    import uvloop

    uvloop.install()
except ImportError:
    if platform.system() != "Windows":
        logger.warning("uvloop is not installed and therefore will be disabled.")


async def main():
    miku = MikuBot()

    try:
        # start the bot
        await database.connect()
        await miku.start()

        if "test" not in sys.argv:
            await idle()
    except KeyboardInterrupt:
        # exit gracefully
        logger.warning("Forced stop… Bye!")
    finally:
        # close https connections and the DB if open
        await miku.stop()
        await http.aclose()
        if database.is_connected:
            await database.close()


if __name__ == "__main__":
    # open new asyncio event loop
    event_policy = asyncio.get_event_loop_policy()
    event_loop = event_policy.new_event_loop()
    asyncio.set_event_loop(event_loop)

    # start the bot
    event_loop.run_until_complete(main())

    # close asyncio event loop
    event_loop.close()
