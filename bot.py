import asyncio
import os
import telebot
from scheduler.asyncio import Scheduler
import datetime
from datetime import timedelta
import aiohttp
from telebot.async_telebot import AsyncTeleBot
from marzpy import Marzban
from marzpy.api.user import User
from telebot import types
from telebot.util import user_link
import logging

# Configure the logger
logger = logging.getLogger(__name__)
logger.addHandler(logging.StreamHandler())

target_channel = int(os.environ['TARGET_CHANNEL'])
check_cooldown = int(os.environ['CHECK_COOLDOWN'])
panel_username = os.environ['PANEL_USERNAME']
panel_pass = os.environ['PANEL_PASS']
panel_address = os.environ['PANEL_ADDRESS']
bot_token = os.environ['BOT_TOKEN']

bot = AsyncTeleBot(bot_token)


@bot.message_handler(commands=['vpn', 'start'])
async def vpn_message(message):
    # user = bot.get_chat_member(chat_id=mob5ter_channel_id, user_id=message.from_user.id)
    # print('check', user)
    tg_user = await check_user_in_channel(message.from_user.id)
    sub_link = ""
    if tg_user:
        marzban_user = await check_user_marzban(message.from_user.id)
        if marzban_user:
            sub_link = marzban_user.subscription_url
        else:
            print(f"CREATING NEW USER\ntg: {tg_user.user.full_name} - Marzban: SUB_{message.from_user.id}")
            marzban_new_user = await add_marzban_user(message.from_user.id, tg_user.user.full_name)
            sub_link = marzban_new_user.subscription_url

    keyboardmain = types.InlineKeyboardMarkup()
    welcome_message = f"Ну приветик {user_link(message.from_user)}"
    if tg_user:
        keyboardmain.add(types.InlineKeyboardButton(text='Открыть инструкцию', url=sub_link))
        welcome_message += f"""\nТвоя персональная ссылка на подробную настройку прокси по кнопке ниже"""
    else:
        keyboardmain.add(types.InlineKeyboardButton(text='Подписаться на бусти', url="https://boosty.to/mob5ter"))
        welcome_message = f"""\nОй, а ты не состоишь в нашем чатике для сабской элиты\nНеобходимо привязать тг к бусти, чтоб в него попасть\n\nЕсли ты состоишь в чатике, но не можешь получить через меня инструкцию по использованию прокси, свяжись по контактам ниже для решения вопроса или попроси помощи в чате.\n\n<b>@YABLADAHA</b> <b>@urbnywrt</b>"""
    #
    # if c_user:
    #     print(message, c_user.__dict__, welcome_message)
    # else:
    #     print(message, welcome_message)
    await bot.send_message(message.chat.id, text=welcome_message, reply_markup=keyboardmain, parse_mode='HTML')


async def check_user_in_channel(user_id):
    try:
        user = await bot.get_chat_member(chat_id=target_channel, user_id=user_id)
        return user
    except telebot.asyncio_helper.ApiTelegramException:
        return False
    except Exception as e:
        logger.warning(e)
        return False


async def check_user_marzban(tg_id):
    try:
        panel = Marzban(panel_username, panel_pass, panel_address)
        mytoken = await panel.get_token()
        user = await panel.get_user(f"SUB_{tg_id}", mytoken)
        return user
    except aiohttp.client_exceptions.ClientResponseError:
        return False


async def add_marzban_user(tg_id, tg_name):
    try:
        panel = Marzban(panel_username, panel_pass, panel_address)
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
                                                      "VLESS TCP REALITY"
                                                  ]
                                              }), token=mytoken)
        return user
    except Exception as e:
        logger.warning(e)
        return False


async def check_tg_and_recharge():
    logger.info("CHECK FOR EXPIRED USERS")
    panel = Marzban(panel_username, panel_pass, panel_address)
    mytoken = await panel.get_token()
    users = await panel.get_all_users(token=mytoken)
    for item in users:
        if item.status == 'expired' and "SUB_" in item.username:
            # print(item.username + " " + item.status)
            tg_user_id = str(item.username).replace("SUB_", "")
            user = await check_user_in_channel(user_id=int(tg_user_id))
            if user:
                # print(user.user.full_name, user.status)
                if user.status in ['member', 'administrator', 'creator']:
                    sub_date = datetime.today() + timedelta(days=32)
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
                                                                                                 "VLESS TCP REALITY"
                                                                                             ]
                                                                                         }), token=mytoken)
                    await panel.reset_user_traffic(user_username=f"SUB_{tg_user_id}", token=mytoken)
                    logger.info(f"recharge {tg_user_id}")
            else:
                logger.info(f"user {tg_user_id} not found on channel")


async def main():
    await asyncio.gather(bot.polling(), schedule_task())


async def schedule_task():
    loop = asyncio.get_running_loop()
    schedule = Scheduler(loop=loop)
    schedule.once(datetime.timedelta(seconds=check_cooldown), check_tg_and_recharge)
    schedule.cyclic(datetime.timedelta(minutes=check_cooldown), check_tg_and_recharge)

    while True:
        await asyncio.sleep(2)


asyncio.run(main())
