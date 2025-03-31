import asyncio
import datetime
import logging
import os
from datetime import timedelta
import urllib.parse

import aiohttp
import telebot
from scheduler.asyncio import Scheduler
from telebot import types
from telebot.async_telebot import AsyncTeleBot
from telebot.util import user_link
from marzban import MarzbanAPI, UserCreate, UserModify, ProxySettings

# Словарь с URL-схемами для разных приложений
APP_URL_SCHEMES = {
    'ios': {
        'streisand': 'streisand://import/{url}#{name}',
        'karing': 'karing://install-config?url={url}&name={name}',
        'foxray': 'foxray://yiguo.dev/sub/add/?url={url}#{name}',
        'v2box': 'v2box://install-sub?url={url}&name={name}',
        'singbox': 'sing-box://import-remote-profile?url={url}#{name}',
        'shadowrocket': 'sub://{url}',
        'happ': 'happ://add/{url}'
    },
    'android': {
        'nekoray': 'sn://subscription?url={url}&name={name}',
        'v2rayng': 'v2rayng://install-sub?url={url}&name={name}'
    },
    'pc': {
        'clashx': 'clashx://install-config?url={url}',
        'clash': 'clash://install-config?url={url}',
        'hiddify': 'hiddify://install-config/?url={url}'
    }
}

async def generate_app_specific_link(base_url: str, system: str, app: str, user_name: str) -> str:
    """Генерирует специфическую ссылку для выбранного приложения через прокси-сервер."""
    if system not in APP_URL_SCHEMES or app not in APP_URL_SCHEMES[system]:
        return base_url
    
    # Формируем URL для прокси-сервера
    proxy_url = f"https://{os.environ['PROXY_DOMAIN']}:{os.environ['PROXY_PORT']}/redirect/{system}/{app}"
    params = {
        "url": base_url,
        "name": user_name
    }
    
    # Добавляем параметры к URL
    query_string = urllib.parse.urlencode(params)
    return f"{proxy_url}?{query_string}"

LOG_LEVEL = os.environ.get('LOG_LEVEL', 'INFO').upper()

logging.basicConfig(level=LOG_LEVEL)

logger = logging.getLogger(__name__)

target_channel = int(os.environ['TARGET_CHANNEL'])
check_cooldown = int(os.environ['CHECK_COOLDOWN'])
panel_username = os.environ['PANEL_USERNAME']
panel_pass = os.environ['PANEL_PASS']
panel_address = os.environ['PANEL_ADDRESS']
bot_token = os.environ['BOT_TOKEN']
api = MarzbanAPI(base_url=panel_address)
bot = AsyncTeleBot(bot_token)
bot.user_data = {}  # Словарь для хранения данных пользователей
# panel = Marzban(panel_username, panel_pass, panel_address)

@bot.message_handler(commands=['vpn', 'start'])
async def vpn_message(message):
    tg_user_id = message.from_user.id
    tg_user = await check_user_in_channel(tg_user_id)
    welcome_message = f"Ну приветик {user_link(message.from_user)}"
    
    if tg_user:
        sub_link = await get_marzban_sub_url(tg_user_id, tg_user.user.full_name)
        keyboardmain = types.ReplyKeyboardMarkup(resize_keyboard=True)
        keyboardmain.add(types.KeyboardButton("📱 Выбрать приложение"))
        keyboardmain.add(types.KeyboardButton("🔗 Получить общую ссылку"))
        
        welcome_message += f"""\nВыберите действие:"""
        
        # Сохраняем ссылку в сессии пользователя
        bot.user_data[message.from_user.id] = {'sub_link': sub_link}
        
        await bot.send_message(
            message.chat.id, 
            text=welcome_message, 
            reply_markup=keyboardmain, 
            parse_mode='HTML'
        )
    else:
        keyboardmain = types.InlineKeyboardMarkup()
        keyboardmain.add(types.InlineKeyboardButton(text='Подписаться на бусти', url="https://boosty.to/mob5ter"))
        welcome_message = f"""\nОй, а ты не состоишь в нашем чатике для сабской элиты\nНеобходимо привязать тг к бусти, чтоб в него попасть\n\nЕсли ты состоишь в чатике, но не можешь получить через меня инструкцию по использованию прокси, свяжись по контактам ниже для решения вопроса или попроси помощи в чате.\n\n<b>@YABLADAHA</b> <b>@urbnywrt</b>"""
        await bot.send_message(message.chat.id, text=welcome_message, reply_markup=keyboardmain, parse_mode='HTML')

@bot.message_handler(func=lambda message: message.text == "📱 Выбрать приложение")
async def select_system(message: types.Message):
    """Обработчик для выбора системы."""
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add(types.KeyboardButton("iOS"))
    markup.add(types.KeyboardButton("Android"))
    markup.add(types.KeyboardButton("PC"))
    markup.add(types.KeyboardButton("🔙 Назад"))
    
    await bot.send_message(
        message.chat.id,
        "Выберите вашу операционную систему:",
        reply_markup=markup
    )

@bot.message_handler(func=lambda message: message.text == "🔗 Получить общую ссылку")
async def get_general_link(message: types.Message):
    """Обработчик для получения общей ссылки."""
    if message.from_user.id not in bot.user_data or 'sub_link' not in bot.user_data[message.from_user.id]:
        await bot.send_message(message.chat.id, "Ошибка: не удалось найти вашу ссылку. Пожалуйста, начните заново с команды /start")
        return
    
    sub_link = bot.user_data[message.from_user.id]['sub_link']
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton(text="🔗 Открыть ссылку", url=sub_link))
    
    await bot.send_message(
        message.chat.id,
        "Нажмите на кнопку ниже, чтобы открыть вашу ссылку:",
        reply_markup=markup
    )

@bot.message_handler(func=lambda message: message.text in ["iOS", "Android", "PC"])
async def select_app(message: types.Message):
    """Обработчик для выбора приложения."""
    system = message.text.lower()
    if system not in APP_URL_SCHEMES:
        await bot.send_message(message.chat.id, "Неверный выбор системы")
        return

    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    for app in APP_URL_SCHEMES[system].keys():
        markup.add(types.KeyboardButton(app.capitalize()))
    markup.add(types.KeyboardButton("🔙 Назад"))
    
    await bot.send_message(
        message.chat.id,
        "Выберите приложение:",
        reply_markup=markup
    )

@bot.message_handler(func=lambda message: message.text in [app.capitalize() for apps in APP_URL_SCHEMES.values() for app in apps])
async def generate_app_link(message: types.Message):
    """Обработчик для генерации ссылки для конкретного приложения."""
    if message.from_user.id not in bot.user_data or 'sub_link' not in bot.user_data[message.from_user.id]:
        await bot.send_message(message.chat.id, "Ошибка: не удалось найти вашу ссылку. Пожалуйста, начните заново с команды /start")
        return

    app = message.text.lower()
    system = None
    
    # Определяем систему по приложению
    for sys_name, apps in APP_URL_SCHEMES.items():
        if app in apps:
            system = sys_name
            break
    
    if not system:
        await bot.send_message(message.chat.id, "Ошибка: приложение не найдено")
        return

    # Получаем базовую ссылку
    base_url = bot.user_data[message.from_user.id]['sub_link']
    
    # Генерируем специфическую ссылку
    app_link = await generate_app_specific_link(
        base_url,
        system,
        app,
        f"SubVPN_{message.from_user.id}"
    )

    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton(text=f"🔗 Открыть ссылку для {message.text}", url=app_link))
    
    await bot.send_message(
        message.chat.id,
        f"Нажмите на кнопку ниже, чтобы открыть вашу ссылку для {message.text}:",
        reply_markup=markup
    )

@bot.message_handler(func=lambda message: message.text == "🔙 Назад")
async def go_back(message: types.Message):
    """Обработчик для возврата в главное меню."""
    keyboardmain = types.ReplyKeyboardMarkup(resize_keyboard=True)
    keyboardmain.add(types.KeyboardButton("📱 Выбрать приложение"))
    keyboardmain.add(types.KeyboardButton("🔗 Получить общую ссылку"))
    
    await bot.send_message(
        message.chat.id,
        "Главное меню:",
        reply_markup=keyboardmain
    )

async def update_listener(messages):
    for message in messages:
        try:
            if (message.content_type == 'new_chat_members' or message.content_type == 'left_chat_member') and int(message.chat.id) == target_channel:
                await bot.delete_message(message.chat.id, message.message_id)
            else:
                logger.debug(message)
        except Exception as e:
            logger.error(f"[TELEGRAM] ERROR update_listener:\n {e}")


async def get_marzban_sub_url(tg_user_id, tg_user_full_name):
    marzban_user = await check_user_marzban(tg_user_id)
    if marzban_user:
        logger.debug(f"[MARZBAN] USER FOUND\ntg: {tg_user_full_name} - Marzban: {marzban_user.username}")
        return marzban_user.subscription_url
    else:
        logger.debug(f"[MARZBAN] CREATING NEW USER\ntg: {tg_user_full_name} - Marzban: SUB_{tg_user_id}")
        marzban_new_user = await add_marzban_user(tg_user_id, tg_user_full_name)
        return marzban_new_user.subscription_url


async def check_user_in_channel(user_id):
    try:
        user = await bot.get_chat_member(chat_id=target_channel, user_id=user_id)
        if user.status in ['member', 'administrator', 'creator', 'restricted']:
            logger.debug(f"[TELEGRAM] USER FOUND\ntg: {user_id}-{user.user.full_name}")
            return user
    except telebot.asyncio_helper.ApiTelegramException as e:
        logger.warning(f"[TELEGRAM] ApiTelegramException check_user_in_channel:\nuser_id:{user_id}\n{e}")
        pass
    except Exception as e:
        logger.error(f"[TELEGRAM] ERROR check_user_in_channel:\n {e}")
        pass
    return False


async def check_user_marzban(tg_id):
    try:
        marzban_token = await api.get_token(username=panel_username, password=panel_pass)
        user = await api.get_user(username=f"SUB_{tg_id}", token=marzban_token.access_token)
        logger.debug(f"[MARZBAN] USER FOUND: SUB_{tg_id}-{user.note}")
        return user
    except aiohttp.client_exceptions.ClientResponseError as e:
        logger.warning(f"[MARZBAN] NOT FOUND OR ERROR check_user_marzban: {e}")
        return False
    except Exception as e:
        logger.warning(f"[MARZBAN] NOT FOUND OR ERROR check_user_marzban: {e}")
        return False


async def add_marzban_user(tg_id, tg_name):
    try:
        marzban_token = await api.get_token(username=panel_username, password=panel_pass)
        sub_date = datetime.datetime.today() + timedelta(days=31)
        new_user = UserCreate(username=f"SUB_{tg_id}",
                                              note=f"{tg_name}",
                                              proxies={
                                                  "vless": ProxySettings(flow="xtls-rprx-vision")                                                  
                                              },
                                              expire= int(sub_date.timestamp()),                                            
                                              status="active",
                                              inbounds={
                                                  "vless": [
                                                      "VLESS TCP REALITY"
                                                  ]
                                              })
        # print(new_user)
        user = await api.add_user(user=new_user, token=marzban_token.access_token)

        logging.info(f"[MARZBAN] USER CREATED: SUB_{tg_id}-{user.note}")
        return user
    except Exception as e:
        logging.warning(f"[MARZBAN] ERROR add_marzban_user: {e}")
        return False


async def check_tg_and_recharge():
    logger.debug("CHECK FOR EXPIRED USERS")
    marzban_token = await api.get_token(username=panel_username, password=panel_pass)
    users = await api.get_users(token=marzban_token.access_token)
    try:
        for item in users.users:
            if item.status == 'expired' and "SUB_" in item.username:
                # print(item.username + " " + item.status)


                tg_user_id = str(item.username).replace("SUB_", "")
                user = await check_user_in_channel(user_id=int(tg_user_id))
                if user:
                    # print(user.user.full_name, user.status
                    sub_date = datetime.datetime.today() + timedelta(days=31)

                    await api.modify_user(username=f"SUB_{tg_user_id}", user=UserModify(username=f"SUB_{tg_user_id}",
                                                                                         note=f"{user.user.full_name}",
                                                                                         proxies=item.proxies,
                                                                                         data_limit=0,
                                                                                         expire=int(sub_date.timestamp()),
                                                                                         data_limit_reset_strategy="no_reset",
                                                                                         status="active",
                                                                                         inbounds={
                                                                                             "vless": [
                                                                                                 "VLESS TCP REALITY"
                                                                                             ]
                                                                                         }), token=marzban_token.access_token)
                    #await panel.reset_user_traffic(user_username=f"SUB_{tg_user_id}", token=mytoken)
                    logger.info(f"[MARZBAN] user SUB_{tg_user_id} - {user.user.full_name} has been recharged")
                else:
                    logger.debug(f"[MARZBAN] user SUB_{tg_user_id} not found in channel")
                    if datetime.datetime.now() - datetime.datetime.fromtimestamp(item.expire) > timedelta(days=30):
                        await api.remove_user(username=item.username, token=marzban_token.access_token)
                        logger.info(f"[MARZBAN] USER EXPIRED FOR 30 DAYS AND DELETED : {item.username}")
    except Exception as e:
        logger.warning(f"[MARZBAN] ERROR check_tg_and_recharge:\n {e}")


async def main():
    
    chat = await bot.get_chat(target_channel)
    bot.set_update_listener(update_listener)
    logger.info(f"[INIT]BOT STARTED for {chat.title}")
    telebot.apihelper.RETRY_ON_ERROR = True
    await asyncio.gather(bot.infinity_polling(
        allowed_updates=['message', 'edited_message', 'channel_post', 'edited_channel_post', 'inline_query',
                         'chosen_inline_result', 'callback_query', 'shipping_query', 'pre_checkout_query', 'poll',
                         'poll_answer', 'my_chat_member', 'chat_member', 'chat_join_request', 'message_reaction',
                         'message_reaction_count', 'chat_boost', 'removed_chat_boost', 'business_connection',
                         'business_message', 'edited_business_message', 'deleted_business_messages']), schedule_task())


async def schedule_task():
    loop = asyncio.get_running_loop()
    schedule = Scheduler(loop=loop)
    schedule.once(datetime.timedelta(seconds=10), check_tg_and_recharge)
    schedule.cyclic(datetime.timedelta(minutes=check_cooldown), check_tg_and_recharge)

    while True:
        await asyncio.sleep(2)


asyncio.run(main())
