"""Entry point — Render-এ Webhook, লোকালি Polling."""

import asyncio
import logging
import os
import sys

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.types import BotCommand
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiohttp import web

import config
from database import Database
from handlers import admin as admin_handlers
from handlers import channel as channel_handlers
from handlers import user as user_handlers

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)
log = logging.getLogger("highlighthub")

WEBHOOK_PATH = "/webhook"


class ActivityMiddleware:
    """প্রতিটা ইউজার অ্যাক্টিভিটি ট্র্যাক করে (অ্যাডমিন স্ট্যাটসের জন্য)।"""

    def __init__(self, db: Database):
        self.db = db

    async def __call__(self, handler, event, data):
        try:
            user = getattr(event, "from_user", None)
            if user and not user.is_bot:
                await self.db.touch_user(user.id)
        except Exception:  # noqa: BLE001
            pass
        return await handler(event, data)


def create_bot_and_dispatcher() -> tuple[Bot, Dispatcher]:
    bot = Bot(
        token=config.BOT_TOKEN,
        default=DefaultBotProperties(parse_mode="HTML"),
    )
    dp = Dispatcher()
    db = Database()

    dp["db"] = db
    dp["bot"] = bot

    middleware = ActivityMiddleware(db)
    dp.message.middleware(middleware)
    dp.callback_query.middleware(middleware)

    dp.include_router(channel_handlers.router)
    dp.include_router(admin_handlers.router)
    dp.include_router(user_handlers.router)

    return bot, dp


def _webhook_base_url() -> str:
    return (
        os.getenv("WEBHOOK_BASE_URL", "").strip()
        or os.getenv("RENDER_EXTERNAL_URL", "").strip()
        or ""
    ).rstrip("/")


async def main() -> None:
    if not config.BOT_TOKEN:
        log.error("BOT_TOKEN সেট করা নেই! Environment Variable দিয়ে দিন।")
        sys.exit(1)

    bot, dp = create_bot_and_dispatcher()
    db: Database = dp["db"]
    await db.connect()
    log.info("Database ready: %s", config.DB_PATH)

    async def on_startup(bot: Bot) -> None:
        me = await bot.get_me()
        log.info("Bot started: @%s (id=%s)", me.username, me.id)
        await bot.set_my_commands(
            [
                BotCommand(command="start", description="Start / হোম"),
                BotCommand(command="help", description="Help / সাহায্য"),
                BotCommand(command="lang", description="Language / ভাষা"),
                BotCommand(command="admin", description="Admin panel"),
            ]
        )
        base = _webhook_base_url()
        if base:
            secret = os.getenv("WEBHOOK_SECRET", "").strip() or None
            await bot.set_webhook(
                base + WEBHOOK_PATH,
                drop_pending_updates=False,
                allowed_updates=dp.resolve_used_update_types(),
                secret_token=secret,
            )
            log.info("Webhook set → %s%s", base, WEBHOOK_PATH)
            for chat_id, label in (
                (config.SOURCE_CHANNEL, "SOURCE"),
                (config.DEST_CHANNEL, "DEST"),
            ):
                try:
                    chat = await bot.get_chat(chat_id)
                    log.info("%s channel OK: %s", label, chat.title)
                except Exception as exc:  # noqa: BLE001
                    log.warning("%s channel NOT accessible (%s): %s", label, chat_id, exc)

    async def on_shutdown(bot: Bot) -> None:
        await db.close()
        log.info("Shutdown complete")

    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)

    base = _webhook_base_url()
    if base:
        # ---------------------------------------------------------- webhook mode
        secret = os.getenv("WEBHOOK_SECRET", "").strip() or None
        app = web.Application()

        async def health(_request):
            return web.Response(text="✅ HighlightHub bot is running")

        app.router.add_get("/", health)
        app.router.add_get("/health", health)

        SimpleRequestHandler(
            dispatcher=dp,
            bot=bot,
            secret_token=secret,
        ).register(app, path=WEBHOOK_PATH)
        setup_application(app, dp, bot=bot)

        port = int(os.getenv("PORT", "10000"))
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, host="0.0.0.0", port=port)
        await site.start()
        log.info("Web server listening on 0.0.0.0:%s", port)
        try:
            await asyncio.Event().wait()  # সার্ভার চলতে থাকবে
        finally:
            await runner.cleanup()
    else:
        # ---------------------------------------------------------- polling mode
        await bot.delete_webhook(drop_pending_updates=False)
        log.info("No WEBHOOK_BASE_URL — running in polling mode")
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        log.info("Bot stopped")
