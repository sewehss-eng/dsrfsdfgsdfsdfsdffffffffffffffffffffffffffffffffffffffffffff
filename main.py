# main.py
import asyncio
import logging
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import (
    InlineQuery, InlineQueryResultArticle, InputTextMessageContent,
    InlineKeyboardMarkup, InlineKeyboardButton, Message, CallbackQuery
)
from config import BOT_TOKEN, ADMIN_IDS, CHANNELS

# Настройка логирования
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS

async def create_link(chat_id: int, info: dict) -> str:
    """Генерирует одноразовую ссылку"""
    link_obj = await bot.create_chat_invite_link(
        chat_id=chat_id,
        member_limit=1,
        is_primary=False,
        expire_date=datetime.now() + timedelta(minutes=5)
    )
    return link_obj.invite_link

# 🔹 /start команда
@dp.message(Command("start"))
async def cmd_start(message: Message):
    if not is_admin(message.from_user.id):
        return await message.answer("⛔ Доступ только для администраторов")

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔗 Получить ссылку", callback_data="get_links")]
    ])
    await message.answer(
        "👋 <b>Привет!</b> Нажмите кнопку ниже, чтобы создать одноразовую ссылку.",
        reply_markup=kb, parse_mode="HTML"
    )

# 🔹 Кнопка "Получить ссылку" -> показывает каналы
@dp.callback_query(F.data == "get_links")
async def cb_get_links(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer("⛔ Доступ запрещен", show_alert=True)

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"📢 {info['name']}", callback_data=f"channel_{cid}")]
        for cid, info in CHANNELS.items()
    ])
    
    try:
        await callback.message.edit_text("🔽 Выберите канал для генерации ссылки:", reply_markup=keyboard)
    except Exception:
        pass # Игнорируем, если сообщение уже было изменено
    await callback.answer()

# 🔹 Нажатие на канал -> генерация и отправка ссылки
@dp.callback_query(F.data.startswith("channel_"))
async def cb_channel_selected(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer("⛔ Доступ запрещен", show_alert=True)

    try:
        chat_id = int(callback.data.replace("channel_", ""))
        channel_info = CHANNELS.get(chat_id)
        if not channel_info:
            raise ValueError("Канал не найден в конфиге")

        await callback.answer("⏳ Генерация...")
        invite_link = await create_link(chat_id, channel_info)

        # Отправляем ссылку новым сообщением
        await callback.message.answer(
            f"✅ Одноразовая ссылка для <b>{channel_info['name']}</b>:\n{invite_link}",
            parse_mode="HTML"
        )
        # Обновляем старое сообщение
        await callback.message.edit_text(f"🔗 Ссылка для <b>{channel_info['name']}</b> создана и отправлена выше!")
    except Exception as e:
        logger.error(f"Ошибка генерации: {e}")
        await callback.answer(f"❌ Ошибка: {str(e)}", show_alert=True)

# 🔹 Инлайн-режим (в любом чате по @имя_бота)
@dp.inline_query()
async def inline_handler(inline_query: InlineQuery):
    if not is_admin(inline_query.from_user.id):
        return await inline_query.answer(
            [], switch_pm_text="⛔ Только для админов", switch_pm_parameter="admin"
        )

    # 🚀 ПАРАЛЛЕЛЬНАЯ ГЕНЕРАЦИЯ: все запросы к API идут одновременно
    async def make_result(cid, info):
        try:
            link = await create_link(cid, info)
            return InlineQueryResultArticle(
                id=str(cid), title=f"🔗 {info['name']}", description="Одноразовая ссылка",
                input_message_content=InputTextMessageContent(message_text=f"✅ {info['name']}:\n{link}"),
                cache_time=0
            )
        except Exception as e:
            logger.error(f"Inline error {cid}: {e}")
            return None

    tasks = [make_result(cid, info) for cid, info in CHANNELS.items()]
    results = await asyncio.gather(*tasks)
    await inline_query.answer([r for r in results if r], cache_time=0)

async def main():
    logger.info("✅ Бот запущен. Используйте /start или @имя_бота в чате.")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())