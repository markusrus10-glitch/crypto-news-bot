"""
Crypto & Stock News Analysis Telegram Bot — Webhook mode for Render.com
"""

import os
import logging
import threading
import time
from pathlib import Path
from http.server import HTTPServer, BaseHTTPRequestHandler

from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters,
)
from groq import Groq

from scraper import scrape_all_sources
from analyzer import analyze_news
from notion_handler import save_analysis_to_notion

load_dotenv(Path(__file__).parent / ".env", override=True)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

ALLOWED_USERS: list[int] = []
AUTO_INTERVAL = 3 * 60 * 60

RENDER_URL = os.getenv("RENDER_URL", "https://crypto-news-bot-vhc2.onrender.com")

MAIN_KEYBOARD = ReplyKeyboardMarkup(
    [
        [KeyboardButton("📊 Анализ рынка"), KeyboardButton("❓ Задать вопрос")],
        [KeyboardButton("⏰ Авто каждые 3ч"), KeyboardButton("⛔ Стоп авто")],
        [KeyboardButton("📰 Источники"), KeyboardButton("🏠 Меню")],
    ],
    resize_keyboard=True,
)


def is_allowed(user_id: int) -> bool:
    return not ALLOWED_USERS or user_id in ALLOWED_USERS


def after_analysis_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 Новый анализ", callback_data="analyze")],
        [InlineKeyboardButton("❓ Задать вопрос по анализу", callback_data="ask")],
        [InlineKeyboardButton("⏰ Авто каждые 3ч", callback_data="auto_on"),
         InlineKeyboardButton("⛔ Стоп", callback_data="auto_off")],
    ])


async def send_main_menu(chat_id: int, context: ContextTypes.DEFAULT_TYPE, text: str = None) -> None:
    await context.bot.send_message(
        chat_id=chat_id,
        text=text or "Выбери действие:",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("📊 Анализ сейчас", callback_data="analyze")],
            [InlineKeyboardButton("⏰ Авто каждые 3ч", callback_data="auto_on"),
             InlineKeyboardButton("⛔ Стоп авто", callback_data="auto_off")],
            [InlineKeyboardButton("📰 Источники", callback_data="sources")],
        ]),
    )


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "🤖 *Бот анализа крипто и акций*\n\n"
        "Собираю новости с финансовых сайтов и анализирую рынок с помощью ИИ.\n"
        "Рекомендую что покупать и что продавать.\n\n"
        "⚠️ Не финансовый совет. Торгуйте на свой страх и риск.",
        parse_mode="Markdown",
        reply_markup=MAIN_KEYBOARD,
    )
    await send_main_menu(update.effective_chat.id, context)


async def cmd_analyze(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_allowed(update.effective_user.id):
        await update.message.reply_text("❌ Нет доступа.")
        return
    await run_analysis(update.effective_chat.id, context)


async def run_analysis(chat_id: int, context: ContextTypes.DEFAULT_TYPE) -> None:
    msg = await context.bot.send_message(chat_id=chat_id, text="⏳ Собираю новости...")
    try:
        articles = await scrape_all_sources()
        await context.bot.edit_message_text(
            chat_id=chat_id, message_id=msg.message_id,
            text=f"📰 Собрано {len(articles)} статей. Анализирую с ИИ...",
        )
        if not articles:
            await context.bot.edit_message_text(
                chat_id=chat_id, message_id=msg.message_id,
                text="❌ Не удалось получить новости. Попробуйте позже.",
            )
            await send_main_menu(chat_id, context)
            return

        result = await analyze_news(articles)
        if not result["success"]:
            await context.bot.edit_message_text(
                chat_id=chat_id, message_id=msg.message_id,
                text=f"❌ Ошибка анализа: {result.get('message', 'Неизвестная ошибка')}",
            )
            await send_main_menu(chat_id, context)
            return

        analysis = result["analysis"]
        await context.bot.delete_message(chat_id=chat_id, message_id=msg.message_id)
        context.bot_data[f"last_analysis_{chat_id}"] = analysis

        parts = [analysis[i:i+4000] for i in range(0, len(analysis), 4000)]
        for i, part in enumerate(parts):
            await context.bot.send_message(
                chat_id=chat_id, text=part, disable_web_page_preview=True,
                reply_markup=after_analysis_keyboard() if i == len(parts) - 1 else None,
            )

        saved = await save_analysis_to_notion(result)
        if saved:
            await context.bot.send_message(chat_id=chat_id, text="✅ Сохранено в Notion.")

    except Exception as e:
        logger.exception("Error in run_analysis")
        try:
            await context.bot.edit_message_text(
                chat_id=chat_id, message_id=msg.message_id, text=f"❌ Ошибка: {str(e)}",
            )
        except Exception:
            await context.bot.send_message(chat_id=chat_id, text=f"❌ Ошибка: {str(e)}")
        await send_main_menu(chat_id, context)


async def answer_question(chat_id: int, question: str, context: ContextTypes.DEFAULT_TYPE) -> None:
    msg = await context.bot.send_message(chat_id=chat_id, text="🤔 Думаю над ответом...")
    last_analysis = context.bot_data.get(f"last_analysis_{chat_id}", "")
    user_content = question
    if last_analysis:
        user_content = f"Контекст последнего анализа:\n{last_analysis[:3000]}\n\nВопрос: {question}"
    try:
        client = Groq(api_key=os.getenv("GROQ_API_KEY", ""))
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": "Ты финансовый аналитик по крипте и акциям. Отвечай на русском. Давай конкретные ответы. Всегда добавляй: 'Это не финансовый совет.'"},
                {"role": "user", "content": user_content},
            ],
            max_tokens=1000, temperature=0.7,
        )
        answer = response.choices[0].message.content
        await context.bot.edit_message_text(
            chat_id=chat_id, message_id=msg.message_id, text=answer,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("❓ Ещё вопрос", callback_data="ask")],
                [InlineKeyboardButton("📊 Новый анализ", callback_data="analyze")],
                [InlineKeyboardButton("🏠 Меню", callback_data="menu")],
            ]),
        )
    except Exception as e:
        await context.bot.edit_message_text(
            chat_id=chat_id, message_id=msg.message_id, text=f"❌ Ошибка: {str(e)}",
        )
        await send_main_menu(chat_id, context)


async def auto_analysis_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    await run_analysis(context.job.chat_id, context)


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    if not is_allowed(query.from_user.id):
        await query.edit_message_text("❌ Нет доступа.")
        return
    chat_id = query.message.chat_id

    if query.data == "analyze":
        await query.edit_message_text("🔄 Запускаю анализ...")
        await run_analysis(chat_id, context)
    elif query.data == "ask":
        await query.edit_message_text(
            "❓ Напиши свой вопрос по рынку или по последнему анализу.\n\n"
            "Например:\n• Стоит ли сейчас покупать Bitcoin?\n"
            "• Что думаешь про Ethereum?\n• Какие акции перспективны?",
        )
    elif query.data == "auto_on":
        for job in context.job_queue.get_jobs_by_name(f"auto_{chat_id}"):
            job.schedule_removal()
        context.job_queue.run_repeating(
            auto_analysis_job, interval=AUTO_INTERVAL, first=AUTO_INTERVAL,
            chat_id=chat_id, name=f"auto_{chat_id}",
        )
        await query.edit_message_text(
            "✅ Авто-анализ включён! Первый анализ придёт через 3 часа.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("⛔ Остановить", callback_data="auto_off")],
                [InlineKeyboardButton("🏠 Меню", callback_data="menu")],
            ]),
        )
    elif query.data == "auto_off":
        for job in context.job_queue.get_jobs_by_name(f"auto_{chat_id}"):
            job.schedule_removal()
        await query.edit_message_text(
            "⛔ Авто-анализ отключён.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📊 Анализ сейчас", callback_data="analyze")],
                [InlineKeyboardButton("🏠 Меню", callback_data="menu")],
            ]),
        )
    elif query.data == "sources":
        await query.edit_message_text(
            "📰 *Источники новостей:*\n\n"
            "• Fortune • CoinGecko • CoinDesk\n"
            "• CoinMarketCap • CryptoPanic • Decrypt\n"
            "• The Block • Cointelegraph • Reuters\n"
            "• MarketWatch • Yahoo Finance",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Меню", callback_data="menu")]]),
        )
    elif query.data == "menu":
        await query.edit_message_text(
            "Выбери действие:",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📊 Анализ сейчас", callback_data="analyze")],
                [InlineKeyboardButton("⏰ Авто каждые 3ч", callback_data="auto_on"),
                 InlineKeyboardButton("⛔ Стоп авто", callback_data="auto_off")],
                [InlineKeyboardButton("📰 Источники", callback_data="sources")],
            ]),
        )


async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_allowed(update.effective_user.id):
        return
    text = update.message.text.strip()
    chat_id = update.effective_chat.id

    if text == "📊 Анализ рынка":
        await run_analysis(chat_id, context)
    elif text == "⏰ Авто каждые 3ч":
        for job in context.job_queue.get_jobs_by_name(f"auto_{chat_id}"):
            job.schedule_removal()
        context.job_queue.run_repeating(
            auto_analysis_job, interval=AUTO_INTERVAL, first=AUTO_INTERVAL,
            chat_id=chat_id, name=f"auto_{chat_id}",
        )
        await update.message.reply_text("✅ Авто-анализ включён! Первый анализ через 3 часа.", reply_markup=MAIN_KEYBOARD)
    elif text == "⛔ Стоп авто":
        for job in context.job_queue.get_jobs_by_name(f"auto_{chat_id}"):
            job.schedule_removal()
        await update.message.reply_text("⛔ Авто-анализ отключён.", reply_markup=MAIN_KEYBOARD)
    elif text == "📰 Источники":
        await update.message.reply_text(
            "📰 *Источники:*\n\n• Fortune • CoinGecko • CoinDesk\n"
            "• CoinMarketCap • CryptoPanic • Decrypt\n"
            "• The Block • Cointelegraph • Reuters\n"
            "• MarketWatch • Yahoo Finance",
            parse_mode="Markdown", reply_markup=MAIN_KEYBOARD,
        )
    elif text in ("🏠 Меню", "/start"):
        await cmd_start(update, context)
    elif text == "❓ Задать вопрос":
        await update.message.reply_text(
            "❓ Напиши свой вопрос по рынку:\n\n"
            "• Стоит ли покупать Bitcoin сейчас?\n"
            "• Что думаешь про Ethereum?\n"
            "• Какие акции перспективны?",
            reply_markup=MAIN_KEYBOARD,
        )
    else:
        await answer_question(chat_id, text, context)


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "📖 *Команды:*\n\n/start — главное меню\n/analyze — запустить анализ\n\n"
        "Или используй кнопки внизу.\nЛюбой текст — вопрос аналитику.\n\n⚠️ Не финансовый совет.",
        parse_mode="Markdown", reply_markup=MAIN_KEYBOARD,
    )


def main() -> None:
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        raise ValueError("TELEGRAM_BOT_TOKEN не задан")

    port = int(os.getenv("PORT", 10000))
    webhook_url = f"{RENDER_URL}/{token}"

    app = Application.builder().token(token).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("analyze", cmd_analyze))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))

    logger.info(f"Starting webhook on port {port}, url: {webhook_url}")

    app.run_webhook(
        listen="0.0.0.0",
        port=port,
        url_path=token,
        webhook_url=webhook_url,
        drop_pending_updates=True,
    )


if __name__ == "__main__":
    main()
