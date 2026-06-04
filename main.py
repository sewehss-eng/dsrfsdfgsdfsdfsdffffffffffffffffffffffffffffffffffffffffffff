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

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# 🔹 Очередь логов
log_queue = asyncio.Queue(maxsize=1000)

def add_log(text: str):
    try:
        log_queue.put_nowait(f"🕒 {datetime.now().strftime('%H:%M:%S')} | {text}")
    except asyncio.QueueFull:
        logger.warning("⚠️ Очередь логов переполнена")

def get_user_tag(user) -> str:
    """Формирует @username или ФИО"""
    return f"@{user.username}" if user.username else user.full_name

# 🔹 Фоновая отправка логов
async def log_sender():
    if not OWNER_ID:
        logger.warning("⛔ OWNER_ID не указан. Логи не отправляются.")
        return
    
    try:
        await bot.send_message(OWNER_ID, "🔔 <b>Система логов запущена.</b>", parse_mode="HTML")
        logger.info(f"✅ Связь с владельцем ({OWNER_ID}) установлена.")
    except Exception as e:
        logger.critical(f"❌ НЕ УДАЕТСЯ ОТПРАВИТЬ ЛОГИ ВЛАДЕЛЬЦУ! Причина: {e}")
        logger.critical("💡 РЕШЕНИЕ: Найди бота, нажми /start и перезапусти скрипт.")
        return
    
    while True:
        await asyncio.sleep(5)
        logs = []
        while not log_queue.empty():
            try:
                logs.append(log_queue.get_nowait())
            except asyncio.QueueEmpty:
                break
        
        if logs:
            msg = "📋 <b>Логи активности:</b>\n" + "\n".join(logs)
            try:
                await bot.send_message(OWNER_ID, msg, parse_mode="HTML", disable_notification=True)
            except Exception as e:
                logger.error(f"❌ Ошибка отправки логов: {e}")

def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS

# 🔹 Генерация ссылки (принимает тег админа)
async def create_link(chat_id: int, info: dict, admin_tag: str) -> str:
    try:
        link = await bot.create_chat_invite_link(
            chat_id=chat_id,
            member_limit=1,
            expire_date=datetime.now() + timedelta(minutes=5)
        )
        add_log(f"👤 Админ <b>{admin_tag}</b> создал ссылку для <b>{info['name']}</b>")
        return link.invite_link
    except Exception as e:
        add_log(f"❌ Ошибка создания ссылки ({chat_id}): {e}")
        raise

#  /start
@dp.message(Command("start"))
async def cmd_start(message: Message):
    if not is_admin(message.from_user.id):
        return await message.answer("⛔ Доступ только для администраторов")
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔗 Получить ссылку", callback_data="get_links")]
    ])
    await message.answer(
        "👋 <b>Привет!</b> Нажмите кнопку для генерации ссылки.",
        reply_markup=kb,
        parse_mode="HTML"
    )

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
        await callback.message.edit_text(" Выберите канал:", reply_markup=kb)
    except:
        pass
    await callback.answer()

# 🔹 Выбор канала
@dp.callback_query(F.data.startswith("channel_"))
async def cb_channel_selected(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer(" Доступ запрещен", show_alert=True)
    
    try:
        chat_id = int(callback.data.replace("channel_", ""))
        channel_info = CHANNELS.get(chat_id)
        
        if not channel_info:
            return await callback.answer("❌ Канал не найден", show_alert=True)
        
        admin_tag = get_user_tag(callback.from_user)
        await callback.answer("⏳ Генерация...")
        invite_link = await create_link(chat_id, channel_info, admin_tag)
        
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

# 🔹 Инлайн-режим (ИСПРАВЛЕННЫЙ)
@dp.inline_query()
async def inline_handler(inline_query: InlineQuery):
    if not is_admin(inline_query.from_user.id):
        return await inline_query.answer(
            [],
            switch_pm_text="⛔ Только для админов",
            switch_pm_parameter="admin"
        )
    
    query = inline_query.query.lower().strip()
    
    # Если запрос пустой - показываем список каналов без создания ссылок
    if not query:
        results = [
            InlineQueryResultArticle(
                id=str(cid),
                title=f"📢 {info['name']}",
                description="Введите название канала для получения ссылки",
                input_message_content=InputTextMessageContent(
                    message_text=f"Выберите канал: {info['name']}"
                ),
                cache_time=0
            )
            for cid, info in CHANNELS.items()
        ]
        return await inline_query.answer(results, cache_time=0)
    
    # Фильтруем каналы по запросу
    filtered_channels = {
        cid: info for cid, info in CHANNELS.items()
        if query in info['name'].lower()
    }
    
    # Если ничего не найдено
    if not filtered_channels:
        return await inline_query.answer(
            [InlineQueryResultArticle(
                id="not_found",
                title="❌ Канал не найден",
                description="Попробуйте другой запрос",
                input_message_content=InputTextMessageContent(
                    message_text="Канал не найден. Попробуйте другой запрос."
                )
            )],
            cache_time=0
        )
    
    # Создаём ссылки только для отфильтрованных каналов
    admin_tag = get_user_tag(inline_query.from_user)
    
    async def make_res(cid, info):
        try:
            link = await create_link(cid, info, admin_tag)
            return InlineQueryResultArticle(
                id=str(cid),
                title=f"🔗 {info['name']}",
                description="Одноразовая ссылка",
                input_message_content=InputTextMessageContent(
                    message_text=f"✅ {info['name']}:\n{link}"
                ),
                cache_time=0
            )
        except:
            return None
    
    tasks = [make_res(cid, info) for cid, info in filtered_channels.items()]
    res = await asyncio.gather(*tasks)
    await inline_query.answer([r for r in res if r], cache_time=0)

# 🔹 Трекинг входов
@dp.chat_member()
async def on_chat_member_update(event: ChatMemberUpdated):
    if event.new_chat_member.status != "member" or not event.invite_link:
        return
    
    user = event.new_chat_member.user
    user_tag = get_user_tag(user)
    channel_name = CHANNELS.get(event.chat.id, {}).get("name", "Неизвестный канал")
    
    add_log(f"🚀 <b>{user_tag}</b> зашёл в <b>{channel_name}</b>")

# 🔹 Тест логов
@dp.message(Command("test_log"))
async def cmd_test_log(message: Message):
    if message.from_user.id != OWNER_ID:
        return
    add_log(f"🧪 Тест от <b>{get_user_tag(message.from_user)}</b>")
    await message.answer("✅ Тестовый лог добавлен. Придёт в течение 5 сек.")

# 🔹 Ручной вызов логов
@dp.message(Command("logs"))
async def cmd_logs(message: Message):
    if not is_admin(message.from_user.id):
        return
    
    logs = []
    while not log_queue.empty():
        try:
            logs.append(log_queue.get_nowait())
        except:
            break
    
    await message.answer(
        "📭 Логи пусты." if not logs else "📋 <b>Текущие логи:</b>\n" + "\n".join(logs),
        parse_mode="HTML"
    )

async def main():
    logger.info("🚀 Запуск фоновой задачи логирования...")
    asyncio.create_task(log_sender())
    logger.info("🤖 Бот запущен. Введите /start или @ваш_бот в чате.")
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info(" Бот остановлен.")
