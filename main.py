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

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger(__name__)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS

async def create_link(chat_id: int, info: dict) -> str:
    """Создаёт ссылку с детальной обработкой ошибок"""
    try:
        link = await bot.create_chat_invite_link(
            chat_id=chat_id,
            member_limit=1,
            expire_date=datetime.now() + timedelta(minutes=30)
        )
        logger.info(f"✅ Ссылка создана для {info['name']} ({chat_id})")
        return link.invite_link
    except Exception as e:
        logger.error(f"❌ Ошибка API для {chat_id} ({info['name']}): {e}")
        raise

# 🔹 /start
@dp.message(Command("start"))
async def cmd_start(message: Message):
    if not is_admin(message.from_user.id):
        return await message.answer("⛔ Доступ только для администраторов")
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔗 Получить ссылку", callback_data="get_links")]
    ])
    await message.answer("👋 <b>Привет!</b> Нажмите кнопку для генерации ссылки.", reply_markup=kb, parse_mode="HTML")

# 🔹 Показать каналы
@dp.callback_query(F.data == "get_links")
async def cb_get_links(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer("⛔ Доступ запрещен", show_alert=True)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"📢 {info['name']}", callback_data=f"channel_{cid}")]
        for cid, info in CHANNELS.items()
    ])
    try:
        await callback.message.edit_text("🔽 Выберите канал:", reply_markup=kb)
    except Exception as e:
        logger.debug(f"Edit text skipped: {e}")
    await callback.answer()

# 🔹 Выбор канала
@dp.callback_query(F.data.startswith("channel_"))
async def cb_channel_selected(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer("⛔ Доступ запрещен", show_alert=True)

    try:
        raw_id = callback.data.replace("channel_", "")
        chat_id = int(raw_id)
        channel_info = CHANNELS.get(chat_id)
        
        if not channel_info:
            await callback.answer("❌ Канал не найден в config.py", show_alert=True)
            return

        await callback.answer("⏳ Генерация...")
        invite_link = await create_link(chat_id, channel_info)

        await callback.message.answer(
            f"✅ Одноразовая ссылка для <b>{channel_info['name']}</b>:\n{invite_link}",
            parse_mode="HTML"
        )
        # Обновляем старое сообщение
        await callback.message.edit_text(
            f"🔗 Ссылка для <b>{channel_info['name']}</b> готова!\nНажмите ниже для новой ссылки.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔗 Получить ссылку", callback_data="get_links")]
            ])
        )
    except ValueError:
        await callback.answer("❌ Ошибка: неверный ID канала", show_alert=True)
    except Exception as e:
        err_msg = f"❌ Не удалось создать ссылку. Проверь консоль."
        await callback.answer(err_msg, show_alert=True)
        logger.error(f"Callback failed for {callback.data}: {e}", exc_info=True)

# 🔹 Инлайн-режим
@dp.inline_query()
async def inline_handler(inline_query: InlineQuery):
    if not is_admin(inline_query.from_user.id):
        return await inline_query.answer(
            [], switch_pm_text="⛔ Только для админов", switch_pm_parameter="admin"
        )
    async def make_res(cid, info):
        try:
            link = await create_link(cid, info)
            return InlineQueryResultArticle(
                id=str(cid), title=f"🔗 {info['name']}", description="Одноразовая ссылка",
                input_message_content=InputTextMessageContent(message_text=f"✅ {info['name']}:\n{link}"),
                cache_time=0
            )
        except Exception as e:
            logger.error(f"Inline fail {cid}: {e}")
            return None
    tasks = [make_res(cid, info) for cid, info in CHANNELS.items()]
    res = await asyncio.gather(*tasks)
    await inline_query.answer([r for r in res if r], cache_time=0)

# 🔹 Диагностика (полезно при отладке)
@dp.message(Command("check"))
async def cmd_check(message: Message):
    if not is_admin(message.from_user.id): return
    out = "🔍 <b>Проверка доступа к каналам:</b>\n"
    for cid, info in CHANNELS.items():
        try:
            await bot.get_chat(cid)
            out += f"✅ <code>{cid}</code> ({info['name']})\n"
        except Exception as e:
            out += f"❌ <code>{cid}</code> ({info['name']}) → {e}\n"
    await message.answer(out, parse_mode="HTML")

async def main():
    logger.info("🚀 Бот запущен. Введите /start или @ваш_бот в чате.")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())