import asyncio
import logging
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import (
    InlineQuery, InlineQueryResultArticle, InputTextMessageContent,
    InlineKeyboardMarkup, InlineKeyboardButton, Message, CallbackQuery,
    ChatMemberUpdated
)
from config import BOT_TOKEN, ADMIN_IDS, CHANNELS, OWNER_ID

# Настройка логирования
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# 🔹 Очередь логов
log_queue = asyncio.Queue()

def add_log(text: str):
    log_queue.put(f"🕒 {datetime.now().strftime('%H:%M:%S')} | {text}")

# 🔹 Фоновая отправка логов владельцу
async def log_sender():
    if not OWNER_ID: return
    while True:
        await asyncio.sleep(5)  # Пакет каждые 5 сек
        logs = []
        while not log_queue.empty():
            try: logs.append(log_queue.get_nowait())
            except asyncio.QueueEmpty: break
        if logs:
            msg = "📋 <b>Логи активности бота:</b>\n" + "\n".join(logs)
            try:
                await bot.send_message(OWNER_ID, msg, parse_mode="HTML")
            except Exception as e:
                logger.error(f"Не удалось отправить логи: {e}")

def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS

# 🔹 Генерация ссылки с тегом для трекинга
async def create_link(chat_id: int, info: dict, admin_id: int) -> str:
    try:
        link = await bot.create_chat_invite_link(
            chat_id=chat_id,
            member_limit=1,
            expire_date=datetime.now() + timedelta(minutes=5),
            name=f"adm_{admin_id}_ch_{chat_id}"  # Тег для отслеживания входа
        )
        add_log(f"👤 Админ <code>{admin_id}</code> создал ссылку для <b>{info['name']}</b>")
        return link.invite_link
    except Exception as e:
        add_log(f"❌ Ошибка создания ссылки ({chat_id}): {e}")
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
    try: await callback.message.edit_text("🔽 Выберите канал:", reply_markup=kb)
    except: pass
    await callback.answer()

# 🔹 Выбор канала
@dp.callback_query(F.data.startswith("channel_"))
async def cb_channel_selected(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer("⛔ Доступ запрещен", show_alert=True)
    try:
        chat_id = int(callback.data.replace("channel_", ""))
        channel_info = CHANNELS.get(chat_id)
        if not channel_info:
            return await callback.answer("❌ Канал не найден", show_alert=True)

        await callback.answer("⏳ Генерация...")
        invite_link = await create_link(chat_id, channel_info, callback.from_user.id)

        await callback.message.answer(
            f"✅ Одноразовая ссылка для <b>{channel_info['name']}</b>:\n{invite_link}",
            parse_mode="HTML"
        )
        await callback.message.edit_text(
            f"🔗 Ссылка для <b>{channel_info['name']}</b> готова!",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔗 Ещё ссылку", callback_data="get_links")]
            ])
        )
    except Exception as e:
        await callback.answer(f"❌ Ошибка: {e}", show_alert=True)

# 🔹 Инлайн-режим
@dp.inline_query()
async def inline_handler(inline_query: InlineQuery):
    if not is_admin(inline_query.from_user.id):
        return await inline_query.answer([], switch_pm_text="⛔ Только для админов", switch_pm_parameter="admin")
    
    async def make_res(cid, info):
        try:
            link = await create_link(cid, info, inline_query.from_user.id)
            return InlineQueryResultArticle(
                id=str(cid), title=f"🔗 {info['name']}", description="Одноразовая ссылка",
                input_message_content=InputTextMessageContent(message_text=f"✅ {info['name']}:\n{link}"),
                cache_time=0
            )
        except: return None

    tasks = [make_res(cid, info) for cid, info in CHANNELS.items()]
    res = await asyncio.gather(*tasks)
    await inline_query.answer([r for r in res if r], cache_time=0)

# 🔹 Трекинг входов (работает если бот админ канала с правами управления)
@dp.chat_member()
async def on_chat_member_update(event: ChatMemberUpdated):
    if event.new_chat_member.status != "member" or not event.invite_link:
        return
    user = event.new_chat_member.user
    link = event.invite_link
    channel_id = event.chat.id
    channel_name = CHANNELS.get(channel_id, {}).get("name", "Неизвестный канал")
    
    admin_id = "unknown"
    if link.name and link.name.startswith("adm_"):
        try: admin_id = link.name.split("_ch_")[0].replace("adm_", "")
        except: pass

    add_log(f"🚀 <b>{user.full_name}</b> (<code>{user.id}</code>) зашёл в <b>{channel_name}</b> по ссылке от админа <code>{admin_id}</code>")

# 🔹 Ручной вызов логов
@dp.message(Command("logs"))
async def cmd_logs(message: Message):
    if not is_admin(message.from_user.id): return
    logs = []
    while not log_queue.empty():
        try: logs.append(log_queue.get_nowait())
        except: break
    if not logs:
        return await message.answer("📭 Логи пусты.")
    await message.answer("📋 <b>Текущие логи:</b>\n" + "\n".join(logs), parse_mode="HTML")

async def main():
    logger.info("🚀 Бот запущен. Логи отправляются владельцу.")
    asyncio.create_task(log_sender())  # Запускаем фоновую задачу
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())