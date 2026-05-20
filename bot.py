#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Telegram-бот "Орёл и Решка" — версия для Render (webhook).

Возможности:
  • /start, /help — приветствие и инструкция
  • /flip — подбросить монетку (Орёл / Решка)
  • /choose вариант1 вариант2 [...] — выбрать случайный вариант
  • Inline-режим: набери "@имя_бота" в любом чате

Переменные окружения (задаются в Render → Environment):
  BOT_TOKEN          — токен от @BotFather
  RENDER_EXTERNAL_URL — подставляется Render автоматически
"""

import os
import random
import logging
from uuid import uuid4

import uvicorn
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import PlainTextResponse, Response
from starlette.routing import Route

from telegram import (
    Update,
    InlineQueryResultArticle,
    InputTextMessageContent,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.ext import (
    Application,
    CommandHandler,
    InlineQueryHandler,
    CallbackQueryHandler,
    ContextTypes,
)

# ─────────────────────────────────────────────────────────────
#  НАСТРОЙКИ
# ─────────────────────────────────────────────────────────────

TOKEN = os.environ.get("BOT_TOKEN", "")
RENDER_URL = os.environ.get("RENDER_EXTERNAL_URL", "")
PORT = int(os.environ.get("PORT", 10000))

HEADS = "🦅 Орёл"
TAILS = "🪙 Решка"

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────
#  ЛОГИКА МОНЕТКИ
# ─────────────────────────────────────────────────────────────

def flip_coin() -> str:
    return random.choice([HEADS, TAILS])


def make_flip_text() -> str:
    result = flip_coin()
    return f"Монетка подброшена...\n\nВыпало: *{result}*"


def flip_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("🔄 Подбросить ещё раз", callback_data="flip")]]
    )


# ─────────────────────────────────────────────────────────────
#  ОБРАБОТЧИКИ КОМАНД
# ─────────────────────────────────────────────────────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = (
        "Привет! Я бот «Орёл и Решка» 🪙\n\n"
        "*Что я умею:*\n"
        "• /flip — подбросить монетку\n"
        "• /choose вариант1 вариант2 — выбрать случайный из вариантов\n"
        "  (например: `/choose пицца суши`)\n\n"
        "*Главная фишка:* меня можно вызвать в *любом* чате, "
        "не добавляя туда. Просто набери `@"
        f"{context.bot.username}` и выбери действие из списка."
    )
    await update.message.reply_text(text, parse_mode="Markdown")


async def flip(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        make_flip_text(),
        parse_mode="Markdown",
        reply_markup=flip_keyboard(),
    )


async def choose(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    options = context.args
    if len(options) < 2:
        await update.message.reply_text(
            "Дай мне минимум 2 варианта на выбор.\n"
            "Пример: `/choose пицца суши бургер`",
            parse_mode="Markdown",
        )
        return
    winner = random.choice(options)
    await update.message.reply_text(
        f"Из вариантов: _{', '.join(options)}_\n\n"
        f"Я выбираю → *{winner}*",
        parse_mode="Markdown",
    )


# ─────────────────────────────────────────────────────────────
#  КНОПКА "Подбросить ещё раз"
# ─────────────────────────────────────────────────────────────

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    if query.data == "flip":
        await query.edit_message_text(
            make_flip_text(),
            parse_mode="Markdown",
            reply_markup=flip_keyboard(),
        )


# ─────────────────────────────────────────────────────────────
#  INLINE-РЕЖИМ (вызов в любом чате через @имя_бота)
# ─────────────────────────────────────────────────────────────

async def inline_query(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.inline_query.query.strip()
    results = []

    coin_result = flip_coin()
    results.append(
        InlineQueryResultArticle(
            id=str(uuid4()),
            title="🪙 Подбросить монетку",
            description="Орёл или Решка — нажми, чтобы отправить результат",
            input_message_content=InputTextMessageContent(
                f"Монетка подброшена...\n\nВыпало: *{coin_result}*",
                parse_mode="Markdown",
            ),
        )
    )

    if query:
        if "," in query:
            options = [o.strip() for o in query.split(",") if o.strip()]
        else:
            options = [o.strip() for o in query.split() if o.strip()]

        if len(options) >= 2:
            winner = random.choice(options)
            results.append(
                InlineQueryResultArticle(
                    id=str(uuid4()),
                    title=f"🎯 Выбрать из: {', '.join(options)}",
                    description=f"Случайный выбор из {len(options)} вариантов",
                    input_message_content=InputTextMessageContent(
                        f"Из вариантов: _{', '.join(options)}_\n\n"
                        f"Выбрано → *{winner}*",
                        parse_mode="Markdown",
                    ),
                )
            )

    await update.inline_query.answer(results, cache_time=0)


# ─────────────────────────────────────────────────────────────
#  WEBHOOK + WEB-СЕРВЕР (для Render)
# ─────────────────────────────────────────────────────────────

ptb_application: Application = None


async def telegram_webhook(request: Request) -> Response:
    """Принимает входящие обновления от Telegram."""
    data = await request.json()
    update = Update.de_json(data=data, bot=ptb_application.bot)
    await ptb_application.process_update(update)
    return Response(status_code=200)


async def health(request: Request) -> PlainTextResponse:
    """Health check — Render проверяет, что сервис жив."""
    return PlainTextResponse("OK")


routes = [
    Route("/webhook", telegram_webhook, methods=["POST"]),
    Route("/health", health, methods=["GET"]),
    Route("/", health, methods=["GET"]),
]

starlette_app = Starlette(routes=routes)


# ─────────────────────────────────────────────────────────────
#  ЗАПУСК
# ─────────────────────────────────────────────────────────────

async def post_init(application: Application) -> None:
    """Устанавливаем webhook после инициализации."""
    webhook_url = f"{RENDER_URL}/webhook"
    await application.bot.set_webhook(url=webhook_url)
    logger.info(f"Webhook установлен: {webhook_url}")


def main() -> None:
    global ptb_application
    import asyncio

    if not TOKEN:
        print("⚠️  Не задан BOT_TOKEN! Добавь его в Environment на Render.")
        return

    if not RENDER_URL:
        print("⚠️  Не задан RENDER_EXTERNAL_URL!")
        return

    ptb_application = (
        Application.builder()
        .token(TOKEN)
        .updater(None)
        .post_init(post_init)
        .build()
    )

    ptb_application.add_handler(CommandHandler(["start", "help"], start))
    ptb_application.add_handler(CommandHandler("flip", flip))
    ptb_application.add_handler(CommandHandler("choose", choose))
    ptb_application.add_handler(CallbackQueryHandler(button_callback))
    ptb_application.add_handler(InlineQueryHandler(inline_query))

    async def run():
        async with ptb_application:
            await ptb_application.start()
            logger.info(f"Бот запущен на порту {PORT}")
            config = uvicorn.Config(
                app=starlette_app,
                host="0.0.0.0",
                port=PORT,
                log_level="info",
            )
            server = uvicorn.Server(config)
            await server.serve()
            await ptb_application.stop()

    asyncio.run(run())


if __name__ == "__main__":
    main()
