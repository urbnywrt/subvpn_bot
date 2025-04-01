import asyncio
import datetime
import logging
import os
from datetime import timedelta
import urllib.parse
from logging.handlers import RotatingFileHandler

import aiohttp
import telebot
from scheduler.asyncio import Scheduler
from telebot import types
from telebot.async_telebot import AsyncTeleBot
from telebot.util import user_link
from marzban import MarzbanAPI, UserCreate, UserModify, ProxySettings

# Настройка логирования
LOG_LEVEL = os.environ.get('LOG_LEVEL', 'INFO').upper()
LOG_FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
LOG_DIR = '/var/log'
LOG_MAX_BYTES = 10 * 1024 * 1024  # 10 MB
LOG_BACKUP_COUNT = 5

# Создаем директорию для логов, если она не существует
os.makedirs(LOG_DIR, exist_ok=True)

# Настраиваем логгер
logger = logging.getLogger(__name__)
logger.setLevel(LOG_LEVEL)

# Форматтер для логов
formatter = logging.Formatter(LOG_FORMAT)

# Обработчик для обычных логов
info_handler = RotatingFileHandler(
    os.path.join(LOG_DIR, 'bot.log'),
    maxBytes=LOG_MAX_BYTES,
    backupCount=LOG_BACKUP_COUNT,
    encoding='utf-8'
)
info_handler.setFormatter(formatter)
info_handler.setLevel(logging.INFO)

# Обработчик для ошибок
error_handler = RotatingFileHandler(
    os.path.join(LOG_DIR, 'bot.err.log'),
    maxBytes=LOG_MAX_BYTES,
    backupCount=LOG_BACKUP_COUNT,
    encoding='utf-8'
)
error_handler.setFormatter(formatter)
error_handler.setLevel(logging.ERROR)

# Добавляем обработчики к логгеру
logger.addHandler(info_handler)
logger.addHandler(error_handler)

# Также выводим логи в консоль для отладки
console_handler = logging.StreamHandler()
console_handler.setFormatter(formatter)
console_handler.setLevel(LOG_LEVEL)
logger.addHandler(console_handler)

# Загрузка переменных окружения
target_channel = int(os.environ['TARGET_CHANNEL'])
check_cooldown = int(os.environ['CHECK_COOLDOWN'])
panel_username = os.environ['PANEL_USERNAME']
panel_pass = os.environ['PANEL_PASS']
panel_address = os.environ['PANEL_ADDRESS']
bot_token = os.environ['BOT_TOKEN']
proxy_domain = os.environ['PROXY_DOMAIN']
proxy_port = os.environ['PROXY_PORT']
admin_ids = [int(id.strip()) for id in os.environ.get('ADMIN_ID', '').split(',') if id.strip()]
SUPPORT_CHAT_ID = int(os.environ.get('SUPPORT_CHAT_ID', 0))  # ID чата для поддержки
SUPPORT_BOT_USERNAME = os.environ.get('SUPPORT_BOT_USERNAME', '')  # Username бота поддержки

# Логируем важные переменные при запуске
logger.info(f"Загруженные переменные окружения:")
logger.info(f"SUPPORT_CHAT_ID: {SUPPORT_CHAT_ID}")
logger.info(f"SUPPORT_BOT_USERNAME: {SUPPORT_BOT_USERNAME}")
logger.info(f"ADMIN_IDS: {admin_ids}")

# Словарь с URL-схемами для разных приложений
APP_URL_SCHEMES = {
    'ios': {
        'streisand': 'streisand://import/{url}#{name}',
        # 'karing': 'karing://install-config?url={url}&name={name}',  # Закомментировали URL-схему для Karing
        'foxray': 'foxray://yiguo.dev/sub/add/?url={url}#{name}',
        'v2box': 'v2box://install-sub?url={url}&name={name}',
        'singbox': 'sing-box://import-remote-profile?url={url}#{name}'
    },
    'android': {
        'v2rayng': 'v2rayng://install-sub?url={url}&name={name}',
        'hiddify': 'hiddify://install-config/?url={url}'
    },
    'pc': {
        'hiddify': 'hiddify://install-config/?url={url}'
    }
}

# Словарь со ссылками на скачивание приложений
APP_DOWNLOAD_LINKS = {
    'ios': {
        'streisand': 'https://apps.apple.com/app/streisand/id6450534064',
        'karing': 'https://apps.apple.com/app/karing/id6472431552',
        'foxray': 'https://apps.apple.com/app/foxray/id6448898396',
        'v2box': 'https://apps.apple.com/app/v2box/id6446814690',
        # 'singbox': 'https://apps.apple.com/app/sing-box/id6450509028',
        'shadowrocket': 'https://apps.apple.com/app/shadowrocket/id932747118',
        'happ': 'https://apps.apple.com/app/happ-proxy-utility/id6504287215'
    },
    'android': {
        'v2rayng': 'https://play.google.com/store/apps/details?id=com.v2ray.ang',
        'hiddify': 'https://play.google.com/store/apps/details?id=app.hiddify.com',
        'V2RayTun': 'https://play.google.com/store/apps/details?id=com.v2raytun.android',
    },
    'pc': {
        'hiddify': 'https://apps.microsoft.com/store/detail/hiddify-next/9N2B0K8Z5Z5F',
        'v2rayN': 'https://github.com/2dust/v2rayN/releases/latest',
        'karing': 'https://github.com/KaringX/karing/releases/latest'
    }
}

async def generate_app_specific_link(base_url: str, system: str, app: str, user_name: str) -> str:
    """Генерирует специфическую ссылку для выбранного приложения через прокси-сервер."""
    if system not in APP_URL_SCHEMES or app not in APP_URL_SCHEMES[system]:
        return base_url
    
    # Формируем URL для прокси-сервера
    proxy_url = f"https://{proxy_domain}:{proxy_port}/redirect/{system}/{app}"
    
    # Для всех приложений используем прямой формат без кодирования
    return f"{proxy_url}?url={base_url}&name={user_name}"

# Инициализация API и бота
api = MarzbanAPI(base_url=panel_address)
bot = AsyncTeleBot(bot_token)
bot.user_data = {}
# panel = Marzban(panel_username, panel_pass, panel_address)

@bot.message_handler(commands=['vpn', 'start'])
async def vpn_message(message):
    if message.chat.type != 'private':
        return
    tg_user_id = message.from_user.id
    tg_user = await check_user_in_channel(tg_user_id)
    welcome_message = f"👋 Привет, {user_link(message.from_user)}!\n\n"
    
    if tg_user:
        sub_link = await get_marzban_sub_url(tg_user_id, tg_user.user.full_name)
        
        # Сохраняем ссылку в сессии пользователя
        bot.user_data[message.from_user.id] = {'sub_link': sub_link}
        
        welcome_message += """🎉 Добро пожаловать в бота SubVPN!

Я помогу вам настроить VPN на вашем устройстве. У нас есть поддержка следующих платформ:
• 📱 iOS/MacOS
• 🤖 Android
• 💻 Windows

Выберите вашу платформу, и я предоставлю подробные инструкции по установке и настройке VPN.

ℹ️ Если у вас возникнут вопросы, не стесняйтесь обращаться в чат поддержки."""
        
        # Создаем inline-кнопки для выбора платформы
        markup = types.InlineKeyboardMarkup(row_width=2)
        markup.add(
            types.InlineKeyboardButton("📱 iOS/MacOS", callback_data="platform_ios"),
            types.InlineKeyboardButton("🤖 Android", callback_data="platform_android"),
            types.InlineKeyboardButton("💻 PC", callback_data="platform_pc")
        )
        markup.add(types.InlineKeyboardButton("💬 Поддержка", callback_data="support"))
        
        await bot.send_message(
            message.chat.id, 
            text=welcome_message, 
            reply_markup=markup, 
            parse_mode='HTML'
        )
    else:
        # Создаем кнопку для подписки
        keyboardmain = types.InlineKeyboardMarkup()
        keyboardmain.add(types.InlineKeyboardButton(text='Подписаться на бусти', url="https://boosty.to/mob5ter"))
        keyboardmain.add(types.InlineKeyboardButton(text='💬 Поддержка', callback_data="support"))
        welcome_message = f"""❌ Упс! Похоже, вы не являетесь подписчиком нашего сервиса.

Для получения доступа к прокси необходимо:
1. Подписаться на наш Boosty
2. Привязать Telegram к аккаунту Boosty
3. Получить доступ к закрытому каналу

Если у вас уже есть подписка, но вы не можете получить доступ:
• Обратитесь за помощью в поддержку"""
        await bot.send_message(message.chat.id, text=welcome_message, reply_markup=keyboardmain, parse_mode='HTML')

@bot.callback_query_handler(func=lambda call: call.data.startswith('platform_'))
async def handle_platform_selection(call):
    """Обработчик выбора платформы."""
    if call.message.chat.type != 'private':
        return
    platform = call.data.split('_')[1]
    platform_names = {
        'ios': 'iOS/MacOS',
        'android': 'Android',
        'pc': 'PC'
    }
    
    # Создаем inline-кнопки для приложений
    markup = types.InlineKeyboardMarkup(row_width=2)
    for app in APP_DOWNLOAD_LINKS[platform].keys():
        markup.add(types.InlineKeyboardButton(
            text=app.capitalize(),
            callback_data=f"app_{platform}_{app}"
        ))
    markup.add(types.InlineKeyboardButton(text="🏠 В главное меню", callback_data="refresh_menu"))
    
    await bot.edit_message_text(
        f"Вы выбрали {platform_names[platform]}\n\nВыберите приложение:",
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        reply_markup=markup
    )

@bot.callback_query_handler(func=lambda call: call.data.startswith('app_'))
async def handle_app_selection(call):
    """Обработчик выбора приложения."""
    if call.message.chat.type != 'private':
        return
    _, platform, app = call.data.split('_')
    app_name = app.capitalize()
    
    if call.from_user.id not in bot.user_data or 'sub_link' not in bot.user_data[call.from_user.id]:
        await bot.answer_callback_query(call.id, "Ошибка: не удалось найти вашу ссылку. Пожалуйста, начните заново с команды /start")
        return
    
    base_url = bot.user_data[call.from_user.id]['sub_link']
    
    # Создаем сообщение с информацией о приложении
    message_text = f"📱 {app_name}\n\n"
    
    # Добавляем ссылку на скачивание
    download_link = APP_DOWNLOAD_LINKS[platform][app]
    message_text += f"📥 Скачать приложение: {download_link}\n\n"
    
    # Создаем markup в начале
    markup = types.InlineKeyboardMarkup()
    
    # Проверяем, есть ли URL-схема для приложения
    if platform in APP_URL_SCHEMES and app in APP_URL_SCHEMES[platform]:
        # Генерируем специфическую ссылку
        app_link = await generate_app_specific_link(
            base_url,
            platform,
            app,
            f"SubVPN_{call.from_user.id}"
        )
        message_text += f"🔗 Нажмите кнопку ниже для автоматической настройки:"
        markup.add(types.InlineKeyboardButton(text="⚙️ Настроить автоматически", url=app_link))
    else:
        # Показываем инструкцию для ручного добавления
        if app == 'V2RayTun':
            message_text += f"""⚙️ Инструкция по настройке {app_name}:

1. Нажмите на кнопку "Открыть общую ссылку" ниже и скопируйте её
2. Откройте приложение {app_name}
3. Нажмите на кнопку "+" в правом верхнем углу
4. Выберите "Импорт из буфера обмена"

После добавления конфигурации, нажмите "Подключиться" или "Start"."""
            markup.add(types.InlineKeyboardButton(text="🔗 Открыть общую ссылку", url=base_url))
        elif app == 'v2rayN':
            message_text += f"""⚙️ Инструкция по настройке {app_name}:

1. Нажмите на кнопку "Открыть общую ссылку" ниже и скопируйте её

2. В приложении V2RayN нажмите «Сервера» → «Импорт массива URL из буфера обмена».

3. Затем нажмите кнопку «Группа подписки» → «Обновить подписку без прокси». В приложении загрузится список всех доступных локаций.

4. Активируйте VPN:
   • Выберите нужную вам локацию, кликните по ней правой кнопкой мыши и выберите «Установить как активный сервер».
   • В нижней части окна приложения установите параметр «Системный прокси» в режим «Установить системный прокси». Иконка приложения изменится на красную - значит, подключение установлено.
   • Активируйте «Режим VPN» в клиенте. Он находится рядом с параметром «Системный прокси» внизу.

Готово! Теперь на вашем устройстве настроен быстрый и надёжный VPN.

ℹ️ Для отключения VPN:
   • Смените параметр «Системный прокси» на «Очистить системный прокси»
   • Выключите «Режим VPN»."""
            markup.add(types.InlineKeyboardButton(text="🔗 Открыть общую ссылку", url=base_url))
        elif app == 'karing':
            # Добавляем информацию об установке в зависимости от платформы
            if platform == 'android':
                message_text += f"""📥 Установка приложения:
• Скачайте APK-файл по ссылке выше
• Установите приложение с помощью APK-файла

"""
            elif platform == 'pc':
                message_text += f"""📥 Установка приложения:
• Скачайте установочный файл по ссылке выше
• Запустите установщик от имени Администратора

"""
            elif platform == 'ios':
                message_text += f"""📥 Установка приложения:
• Установите приложение из App Store по ссылке выше

"""

            message_text += f"""⚙️ Настройка приложения:

1. Запустите приложение "Karing"
2. Согласитесь с политиками приложения
3. В разделе "Язык" выберите русский язык и нажмите "Next"
4. В разделе "Страна или регион" найдите и выберите "Российская Федерация", нажмите "Дальше"
5. В разделе "Шаблоны личных правил" нажмите "Дальше"
6. В разделе "Настройка" оставьте переключатель "Режим новичка" включенным, нажмите "Готово"

🔗 Импорт конфигурации:
1. Нажмите на кнопку "Открыть общую ссылку" ниже и скопируйте её
2. В разделе "Добавить профиль" нажмите "Импорт из буфера обмена"
3. Вверху экрана нажмите на галочку и "Ок" в появившемся окне
4. Выйдите из раздела "Добавить профиль" нажав на стрелку в левом верхнем углу

🔄 Активация:
1. Включите приложение с помощью большой кнопки"""

            # Добавляем информацию о первом запуске в зависимости от платформы
            if platform == 'pc':
                message_text += f"""
2. При первом запуске на Windows:
   • Позвольте доступ к сети
   • Включите режим работы "Системный прокси"
   • Выберите режим работы правил перенаправления "Глобально":
     • "Правила" - через ВПН будут работать только указанные сайты
     • "Глобально" - через ВПН будут работать все сайты без исключений"""
            elif platform == 'ios':
                message_text += f"""
2. При первом запуске:
   • Позвольте приложению добавить новый ВПН-профиль в настройки системы
   • Включите режим работы "Системный прокси"
   • Выберите режим работы правил перенаправления "Глобально":
     • "Правила" - через ВПН будут работать только указанные сайты
     • "Глобально" - через ВПН будут работать все сайты без исключений
   • Перейдите в настройки iOS/MacOS
   • Выберите "VPN и управление устройством"
   • Найдите профиль Karing и нажмите "Установить"
   • Введите пароль устройства для подтверждения
   • Нажмите "Установить" в появившемся окне
   • Вернитесь в приложение Karing"""
            else:  # android
                message_text += f"""
2. Включите режим работы "Системный прокси"
3. Выберите режим работы правил перенаправления "Глобально":
   • "Правила" - через ВПН будут работать только указанные сайты
   • "Глобально" - через ВПН будут работать все сайты без исключений"""
            
            markup.add(types.InlineKeyboardButton(text="🔗 Открыть общую ссылку", url=base_url))
        else:
            # Универсальная инструкция для остальных приложений
            message_text += f"""⚙️ Инструкция по настройке {app_name}:

1. Нажмите на кнопку "Открыть общую ссылку" ниже и скопируйте её
2. Откройте приложение {app_name}
3. Найдите раздел "Импорт" или "Добавить подписку"
4. Вставьте скопированную ссылку
5. Сохраните конфигурацию
6. Включите VPN

ℹ️ Если у вас возникнут проблемы:
• Убедитесь, что ссылка скопирована полностью
• Проверьте подключение к интернету
• Попробуйте перезапустить приложение
• При необходимости обратитесь к администраторам"""
            markup.add(types.InlineKeyboardButton(text="🔗 Открыть общую ссылку", url=base_url))
    
    # Добавляем кнопки навигации
    markup.add(types.InlineKeyboardButton(text="🔙 Назад к выбору приложений", callback_data=f"platform_{platform}"))
    markup.add(types.InlineKeyboardButton(text="🏠 В главное меню", callback_data="refresh_menu"))
    
    await bot.edit_message_text(
        message_text,
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        reply_markup=markup
    )

@bot.callback_query_handler(func=lambda call: call.data == "refresh_menu")
async def handle_refresh_menu(call):
    """Обработчик обновления меню."""
    if call.message.chat.type != 'private':
        return
    tg_user_id = call.from_user.id
    tg_user = await check_user_in_channel(tg_user_id)
    welcome_message = f"👋 Привет, {user_link(call.from_user)}!\n\n"
    
    # Сбрасываем флаг режима поддержки
    if call.from_user.id in bot.user_data:
        bot.user_data[call.from_user.id]['in_support'] = False
    
    if tg_user:
        sub_link = await get_marzban_sub_url(tg_user_id, tg_user.user.full_name)
        
        # Сохраняем ссылку в сессии пользователя
        bot.user_data[call.from_user.id] = {'sub_link': sub_link}
        
        welcome_message += """🎉 Добро пожаловать в VPN-бот SubVPN!

Я помогу вам настроить VPN на вашем устройстве. У нас есть поддержка следующих платформ:
• 📱 iOS/MacOS
• 🤖 Android
• 💻 Windows

Выберите вашу платформу, и я предоставлю подробные инструкции по установке и настройке VPN.

ℹ️ Если у вас возникнут вопросы, не стесняйтесь обращаться в поддержку."""
        
        # Создаем inline-кнопки для выбора платформы
        markup = types.InlineKeyboardMarkup(row_width=2)
        markup.add(
            types.InlineKeyboardButton("📱 iOS/MacOS", callback_data="platform_ios"),
            types.InlineKeyboardButton("🤖 Android", callback_data="platform_android"),
            types.InlineKeyboardButton("💻 PC", callback_data="platform_pc")
        )
        markup.add(types.InlineKeyboardButton("💬 Поддержка", callback_data="support"))
        
        # Отправляем новое сообщение с главным меню
        await bot.send_message(
            call.message.chat.id,
            welcome_message,
            reply_markup=markup,
            parse_mode='HTML'
        )
        
        # Отвечаем на callback query
        await bot.answer_callback_query(call.id)
    else:
        keyboardmain = types.InlineKeyboardMarkup()
        keyboardmain.add(types.InlineKeyboardButton(text='Подписаться на бусти', url="https://boosty.to/mob5ter"))
        keyboardmain.add(types.InlineKeyboardButton(text='💬 Поддержка', callback_data="support"))
        welcome_message = f"""❌ Упс! Похоже, вы не являетесь подписчиком нашего сервиса.

Для получения доступа к прокси необходимо:
1. Подписаться на наш Boosty
2. Привязать Telegram к аккаунту Boosty
3. Получить доступ к закрытому каналу

Если у вас уже есть подписка, но вы не можете получить доступ:
• Обратитесь за помощью в поддержку"""
        
        # Отправляем новое сообщение с главным меню
        await bot.send_message(
            call.message.chat.id,
            welcome_message,
            reply_markup=keyboardmain,
            parse_mode='HTML'
        )
        
        # Отвечаем на callback query
        await bot.answer_callback_query(call.id)

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


async def send_message_to_all_users(message_text: str):
    """Отправляет сообщение всем активным пользователям бота."""
    try:
        marzban_token = await api.get_token(username=panel_username, password=panel_pass)
        users = await api.get_users(token=marzban_token.access_token)
        
        for user in users.users:
            if user.status == 'active' and "SUB_" in user.username:
                try:
                    # Пробуем получить числовой ID из username
                    tg_user_id = int(user.username.replace("SUB_", ""))
                except ValueError:
                    # Если не удалось преобразовать в число, пропускаем пользователя
                    logger.warning(f"Пропущен пользователь с некорректным ID: {user.username}")
                    continue
                    
                try:
                    await bot.send_message(
                        chat_id=tg_user_id,
                        text=message_text,
                        parse_mode='HTML'
                    )
                    logger.info(f"[BROADCAST] Сообщение отправлено пользователю {tg_user_id}")
                except Exception as e:
                    logger.error(f"[BROADCAST] Ошибка отправки сообщения пользователю {tg_user_id}: {e}")
                    continue
                    
        logger.info("[BROADCAST] Рассылка завершена")
    except Exception as e:
        logger.error(f"[BROADCAST] Ошибка при рассылке: {e}")

@bot.message_handler(commands=['broadcast'])
async def broadcast(message: types.Message):
    """Рассылка сообщения всем пользователям."""
    if str(message.from_user.id) not in admin_ids:
        await bot.reply_to(message, "❌ У вас нет прав для выполнения этой команды.")
        return

    # Получаем текст для рассылки
    broadcast_text = message.text.replace('/broadcast', '').strip()
    if not broadcast_text:
        await bot.reply_to(message, "❌ Пожалуйста, добавьте текст для рассылки после команды /broadcast")
        return

    # Создаем прогресс-бар
    progress_message = await bot.reply_to(message, "📤 Начинаю рассылку...")
    
    # Отправляем сообщение всем пользователям
    await send_message_to_all_users(f"{broadcast_text}")
    
    # Отправляем итоговый отчет
    await bot.edit_message_text(
        "✅ Рассылка завершена!",
        chat_id=message.chat.id,
        message_id=progress_message.message_id
    )

@bot.message_handler(commands=['support'])
async def cmd_support(message: types.Message):
    """Обработчик команды для обращения в поддержку."""
    if message.chat.type != 'private':
        return
        
    logger.info(f"Получена команда /support от пользователя {message.from_user.id}")
    logger.info(f"Текущий SUPPORT_CHAT_ID: {SUPPORT_CHAT_ID}")
    
    # Проверяем существование чата поддержки
    try:
        chat = await bot.get_chat(SUPPORT_CHAT_ID)
        logger.info(f"Чат поддержки найден: {chat.title} (ID: {chat.id})")
        await bot.reply_to(
            message,
            "💬 Напишите ваше сообщение, и я передам его в службу поддержки. Наши специалисты ответят вам в ближайшее время."
        )
    except Exception as e:
        logger.error(f"Ошибка при проверке чата поддержки: {e}")
        logger.error(f"Тип ошибки: {type(e)}")
        logger.error(f"Полный текст ошибки: {str(e)}")
        await bot.reply_to(
            message,
            "❌ К сожалению, служба поддержки временно недоступна. Пожалуйста, попробуйте позже."
        )

@bot.message_handler(func=lambda message: message.chat.type == 'private' and message.chat.id != SUPPORT_CHAT_ID)
async def forward_to_support(message: types.Message):
    """Пересылает сообщения пользователей в чат поддержки."""
    if not message.text and not message.photo and not message.video and not message.document:  # Игнорируем пустые сообщения
        return
        
    # Проверяем, находится ли пользователь в режиме поддержки
    if message.from_user.id not in bot.user_data or not bot.user_data[message.from_user.id].get('in_support'):
        return
            
    logger.info(f"Получено сообщение от пользователя {message.from_user.id}")
    logger.info(f"Тип сообщения: {message.content_type}")
    logger.info(f"Текущий SUPPORT_CHAT_ID: {SUPPORT_CHAT_ID}")
    
    try:
        # Проверяем существование чата поддержки
        chat = await bot.get_chat(SUPPORT_CHAT_ID)
        logger.info(f"Чат поддержки найден: {chat.title} (ID: {chat.id})")
        
        # Пересылаем оригинальное сообщение
        await bot.forward_message(
            chat_id=SUPPORT_CHAT_ID,
            from_chat_id=message.chat.id,
            message_id=message.message_id
        )
        
        # Отправляем подтверждение пользователю
        await bot.reply_to(
            message,
            "✅ Ваше сообщение отправлено в службу поддержки. Мы ответим вам в ближайшее время."
        )
        
        logger.info(f"Сообщение успешно переслано в чат поддержки")
    except Exception as e:
        logger.error(f"Ошибка пересылки сообщения в поддержку: {e}")
        logger.error(f"Тип ошибки: {type(e)}")
        logger.error(f"Полный текст ошибки: {str(e)}")
        logger.error(f"ID чата поддержки: {SUPPORT_CHAT_ID}")
        logger.error(f"ID отправителя: {message.from_user.id}")
        await bot.reply_to(
            message,
            "❌ К сожалению, произошла ошибка при отправке сообщения. Пожалуйста, попробуйте позже."
        )

@bot.message_handler(func=lambda message: message.chat.id == SUPPORT_CHAT_ID)
async def handle_support_message(message: types.Message):
    """Обработчик сообщений в чате поддержки."""
    # Проверяем, является ли сообщение ответом на пересланное сообщение от пользователя
    if message.reply_to_message and message.reply_to_message.forward_from:
        # Если это ответ на пересланное сообщение
        user_id = message.reply_to_message.forward_from.id
        try:
            # Создаем клавиатуру с кнопками
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("💬 Есть еще вопросы", callback_data="support"))
            markup.add(types.InlineKeyboardButton("🏠 В главное меню", callback_data="refresh_menu"))
            
            logger.info(f"Обработка ответа от поддержки для пользователя {user_id}")
            logger.info(f"Тип сообщения: {message.content_type}")
            
            # Если сообщение содержит фото
            if message.photo:
                logger.info("Отправка фото пользователю")
                # Отправляем фото с подписью
                caption = f"💬 Ответ от поддержки:\n\n{message.caption if message.caption else ''}\n\nЕсли у вас остались вопросы, нажмите кнопку ниже."
                await bot.send_photo(
                    chat_id=user_id,
                    photo=message.photo[-1].file_id,
                    caption=caption,
                    reply_markup=markup
                )
            # Если сообщение содержит видео
            elif message.video:
                logger.info("Отправка видео пользователю")
                # Отправляем видео с подписью
                caption = f"💬 Ответ от поддержки:\n\n{message.caption if message.caption else ''}\n\nЕсли у вас остались вопросы, нажмите кнопку ниже."
                await bot.send_video(
                    chat_id=user_id,
                    video=message.video.file_id,
                    caption=caption,
                    reply_markup=markup
                )
            # Если сообщение содержит документ
            elif message.document:
                logger.info("Отправка документа пользователю")
                # Отправляем документ с подписью
                caption = f"💬 Ответ от поддержки:\n\n{message.caption if message.caption else ''}\n\nЕсли у вас остались вопросы, нажмите кнопку ниже."
                await bot.send_document(
                    chat_id=user_id,
                    document=message.document.file_id,
                    caption=caption,
                    reply_markup=markup
                )
            else:
                # Отправляем текстовое сообщение
                await bot.send_message(
                    chat_id=user_id,
                    text=f"💬 Ответ от поддержки:\n\n{message.text}\n\nЕсли у вас остались вопросы, нажмите кнопку ниже.",
                    reply_markup=markup
                )
            await bot.reply_to(message, "✅ Ответ отправлен пользователю")
        except Exception as e:
            logger.error(f"Ошибка отправки ответа пользователю: {e}")
            logger.error(f"Тип ошибки: {type(e)}")
            logger.error(f"Полный текст ошибки: {str(e)}")
            await bot.reply_to(message, "❌ Ошибка отправки ответа. Возможно, пользователь заблокировал бота.")
    # Игнорируем все остальные сообщения в чате поддержки

# Добавляем обработчик для кнопки поддержки
@bot.callback_query_handler(func=lambda call: call.data == "support")
async def handle_support_button(call):
    """Обработчик нажатия кнопки поддержки."""
    if call.message.chat.type != 'private':
        return
        
    logger.info(f"Нажата кнопка поддержки от пользователя {call.from_user.id}")
    logger.info(f"Текущий SUPPORT_CHAT_ID: {SUPPORT_CHAT_ID}")
    
    # Проверяем существование чата поддержки
    try:
        chat = await bot.get_chat(SUPPORT_CHAT_ID)
        logger.info(f"Чат поддержки найден: {chat.title} (ID: {chat.id})")
        await bot.answer_callback_query(call.id)
        
        # Устанавливаем флаг, что пользователь находится в режиме поддержки
        if call.from_user.id not in bot.user_data:
            bot.user_data[call.from_user.id] = {}
        bot.user_data[call.from_user.id]['in_support'] = True
        
        # Создаем клавиатуру с кнопкой возврата в главное меню
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("🏠 В главное меню", callback_data="refresh_menu"))
        
        await bot.send_message(
            call.message.chat.id,
            "💬 Напишите ваше сообщение, и я передам его в службу поддержки. Наши специалисты ответят вам в ближайшее время.",
            reply_markup=markup
        )
    except Exception as e:
        logger.error(f"Ошибка при проверке чата поддержки: {e}")
        logger.error(f"Тип ошибки: {type(e)}")
        logger.error(f"Полный текст ошибки: {str(e)}")
        await bot.answer_callback_query(call.id)
        await bot.send_message(
            call.message.chat.id,
            "❌ К сожалению, служба поддержки временно недоступна. Пожалуйста, попробуйте позже."
        )

asyncio.run(main())
