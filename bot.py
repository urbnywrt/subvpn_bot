import asyncio
import datetime
import logging
import os
from datetime import timedelta

import aiohttp
import telebot
from marzpy import Marzban
from marzpy.api.user import User
from scheduler.asyncio import Scheduler
from telebot import types
from telebot.async_telebot import AsyncTeleBot
from telebot.util import user_link

LOG_LEVEL = os.environ.get('LOG_LEVEL', 'INFO').upper()

logging.basicConfig(level=LOG_LEVEL)

logger = logging.getLogger(__name__)

target_channel = int(os.environ['TARGET_CHANNEL'])
check_cooldown = int(os.environ['CHECK_COOLDOWN'])
panel_username = os.environ['PANEL_USERNAME']
panel_pass = os.environ['PANEL_PASS']
panel_address = os.environ['PANEL_ADDRESS']
bot_token = os.environ['BOT_TOKEN']

bot = AsyncTeleBot(bot_token)
panel = Marzban(panel_username, panel_pass, panel_address)


@bot.message_handler(commands=['vpn', 'start'])
async def vpn_message(message):
    tg_user_id = message.from_user.id
    tg_user = await check_user_in_channel(tg_user_id)
    welcome_message = f"Ну приветик {user_link(message.from_user)}"
    keyboardmain = types.InlineKeyboardMarkup()
    if tg_user:
        sub_link = await get_marzban_sub_url(tg_user_id, tg_user.user.full_name)
        keyboardmain.add(types.InlineKeyboardButton(text='Открыть инструкцию', url=sub_link))
        welcome_message += f"""\nТвоя персональная ссылка на подробную настройку прокси по кнопке ниже"""
    else:
        keyboardmain.add(types.InlineKeyboardButton(text='Подписаться на бусти', url="https://boosty.to/mob5ter"))
        welcome_message = f"""\nОй, а ты не состоишь в нашем чатике для сабской элиты\nНеобходимо привязать тг к бусти, чтоб в него попасть\n\nЕсли ты состоишь в чатике, но не можешь получить через меня инструкцию по использованию прокси, свяжись по контактам ниже для решения вопроса или попроси помощи в чате.\n\n<b>@YABLADAHA</b> <b>@urbnywrt</b>"""
    await bot.send_message(message.chat.id, text=welcome_message, reply_markup=keyboardmain, parse_mode='HTML')



async def update_listener(messages):
    for message in messages:
        try:
            if (message.content_type == 'new_chat_members' or message.content_type == 'left_chat_member') and int(message.chat.id) == target_channel:
                await bot.delete_message(message.chat.id, message.message_id)
            else:
                print(message)
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
        mytoken = await panel.get_token()
        user = await panel.get_user(f"SUB_{tg_id}", mytoken)
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
        mytoken = await panel.get_token()
        sub_date = datetime.datetime.today() + timedelta(days=31)
        user = await panel.add_user(user=User(username=f"SUB_{tg_id}",
                                              note=f"{tg_name}",
                                              proxies={
                                                  "vless": {
                                                      "flow": "xtls-rprx-vision"
                                                  }
                                              },
                                              data_limit=536870912000,
                                              expire=sub_date.timestamp(),
                                              data_limit_reset_strategy="no_reset",
                                              status="active",
                                              inbounds={
                                                  "vless": [
                                                      "VLESS TCP REALITY",
                                                      "VLESS H2 REALITY"
                                                  ]
                                              }), token=mytoken)
        logging.info(f"[MARZBAN] USER CREATED: SUB_{tg_id}-{user.note}")
        return user
    except Exception as e:
        logging.warning(f"[MARZBAN] ERROR add_marzban_user: {e}")
        return False


async def check_tg_and_recharge():
    logger.debug("CHECK FOR EXPIRED USERS")
    mytoken = await panel.get_token()
    users = await panel.get_all_users(token=mytoken)
    try:
        for item in users:
            if item.status == 'expired' and "SUB_" in item.username:
                # print(item.username + " " + item.status)
                if datetime.datetime.now() - datetime.datetime.fromtimestamp(item.expire) > timedelta(days=30):
                    await panel.delete_user(item.username, token=mytoken)
                    logger.info(f"[MARZBAN] USER EXPIRED FOR 30 DAYS AND DELETED : {item.username}")
                    continue

                tg_user_id = str(item.username).replace("SUB_", "")
                user = await check_user_in_channel(user_id=int(tg_user_id))
                if user:
                    # print(user.user.full_name, user.status
                    sub_date = datetime.datetime.today() + timedelta(days=32)
                    await panel.modify_user(user_username=f"SUB_{tg_user_id}", user=User(username=f"SUB_{tg_user_id}",
                                                                                         note=f"{user.user.full_name}",
                                                                                         proxies={
                                                                                             "vless": {
                                                                                                 "flow": "xtls-rprx-vision"
                                                                                             }
                                                                                         },
                                                                                         data_limit=536870912000,
                                                                                         expire=sub_date.timestamp(),
                                                                                         data_limit_reset_strategy="no_reset",
                                                                                         status="active",
                                                                                         inbounds={
                                                                                             "vless": [
                                                                                                 "VLESS TCP REALITY",
                                                                                                 "VLESS H2 REALITY"
                                                                                             ]
                                                                                         }), token=mytoken)
                    await panel.reset_user_traffic(user_username=f"SUB_{tg_user_id}", token=mytoken)
                    logger.info(f"[MARZBAN] user SUB_{tg_user_id} - {user.user.full_name} has been recharged")
                else:
                    logger.debug(f"[MARZBAN] user SUB_{tg_user_id} not found in channel")
    except Exception as e:
        logger.warning(f"[MARZBAN] ERROR check_tg_and_recharge:\n {e}")


async def main():
    chat = await bot.get_chat(target_channel)
    bot.set_update_listener(update_listener)
    logger.info(f"BOT STARTED for {chat.title}")
    await asyncio.gather(bot.polling(
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
