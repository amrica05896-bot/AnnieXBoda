# Authored By Certified Coders © 2025
import time
import asyncio
from pyrogram import filters
from pyrogram.enums import ChatType
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message
from youtubesearchpython.aio import VideosSearch

import config
from AnnieXMedia import app
from AnnieXMedia.misc import _boot_
from AnnieXMedia.plugins.sudo.sudoers import sudoers_list
from AnnieXMedia.utils.database import (
    add_served_chat,
    add_served_user,
    blacklisted_chats,
    get_lang,
    is_banned_user,
    is_on_off,
)
from AnnieXMedia.utils.decorators.language import LanguageStart
from AnnieXMedia.utils.formatters import get_readable_time
from AnnieXMedia.utils.inline.help import first_page as help_pannel
from AnnieXMedia.utils.inline.start import private_panel, start_panel
from config import BANNED_USERS
from strings import get_string

# استخدام getattr لتجنب الأخطاء لو المتغير مش موجود
START_IMG_URL = getattr(config, "START_IMG_URL", "https://files.catbox.moe/ompn1o.jpg")
LOGGER_ID = getattr(config, "LOGGER_ID", config.OWNER_ID) # Fallback to Owner ID if Logger ID is 0

@app.on_message(filters.command(["start"]) & filters.private & ~BANNED_USERS)
@LanguageStart
async def start_pm(client, message: Message, _):
    await add_served_user(message.from_user.id)
    try:
        await message.react("❤")
    except:
        pass
        
    if len(message.text.split()) > 1:
        name = message.text.split(None, 1)[1]
        if name[0:4] == "help":
            keyboard = help_pannel(_)
            try:
                await message.reply_sticker("CAACAgUAAyEFAATXFFgrAAIDymlfzq3ZMbEh_bgdkjEhg2QMBib-AAILFQAC-vEZVMBmWHCQ-sJuHgQ")
            except:
                pass
            return await message.reply_photo(
                photo=START_IMG_URL,
                caption=_["help_1"].format(config.SUPPORT_CHAT),
                reply_markup=keyboard,
            )
        if name[0:3] == "sud":
            await sudoers_list(client=client, message=message, _=_)
            if await is_on_off(2):
                if LOGGER_ID != 0:
                    return await app.send_message(
                        chat_id=LOGGER_ID,
                        text=f"{message.from_user.mention} قــام بـبـدء الـبـوت لـمـعـرفـة <b>قـائـمـة الـمـطـوريـن</b>.\n\n<b>آيــدي الـشـخـص :</b> <code>{message.from_user.id}</code>\n<b>الـيـوزر :</b> @{message.from_user.username}",
                    )
            return
        if name[0:3] == "inf":
            m = await message.reply_text("🔎")
            query = (str(name)).replace("info_", "", 1)
            query = f"https://www.youtube.com/watch?v={query}"
            
            def _search():
                return VideosSearch(query, limit=1).result()

            try:
                results = await asyncio.to_thread(_search)
                result = results["result"][0]
                
                title = result["title"]
                duration = result["duration"]
                views = result["viewCount"]["short"]
                thumbnail = result["thumbnails"][0]["url"].split("?")[0]
                channellink = result["channel"]["link"]
                channel = result["channel"]["name"]
                link = result["link"]
                published = result["publishedTime"]
                
                searched_text = _["start_6"].format(
                    title, duration, views, published, channellink, channel, app.mention
                )
                key = InlineKeyboardMarkup(
                    [
                        [
                            InlineKeyboardButton(text=_["S_B_8"], url=link),
                            InlineKeyboardButton(text=_["S_B_9"], url=config.SUPPORT_CHAT),
                        ],
                    ]
                )
                await m.delete()
                await app.send_photo(
                    chat_id=message.chat.id,
                    photo=thumbnail,
                    caption=searched_text,
                    reply_markup=key,
                )
                if await is_on_off(2):
                    if LOGGER_ID != 0:
                        return await app.send_message(
                            chat_id=LOGGER_ID,
                            text=f"{message.from_user.mention} قــام بـبـدء الـبـوت لـمـعـرفـة <b>مـعـلـومـات الأغـنـيـة</b>.\n\n<b>آيــدي الـشـخـص :</b> <code>{message.from_user.id}</code>\n<b>الـيـوزر :</b> @{message.from_user.username}",
                        )
            except Exception as e:
                await m.edit_text(f"Error: {e}")
                return
    else:
        out = private_panel(_)
        
        # --- 1. الصلاة على النبي ---
        prayers = await message.reply_text("صـلـي عـلـي الـنـبـي وتـبـسـم 🤍🌿.")
        await asyncio.sleep(0.5)
        try:
            await prayers.delete()
        except:
            pass

        # --- 2. الترحيب المتحرك ---
        lol = await message.reply_text("نــورت يـا غــالـي ꨄ︎ {}.. 🤍".format(message.from_user.mention))
        await asyncio.sleep(0.1)
        await lol.edit_text("نــورت يـا غــالـي ꨄ︎ {}.. ☔".format(message.from_user.mention))
        await asyncio.sleep(0.1)
        await lol.edit_text("نــورت يـا غــالـي ꨄ︎ {}.. 🧚".format(message.from_user.mention))
        await asyncio.sleep(0.1)
        await lol.edit_text("نــورت يـا غــالـي ꨄ︎ {}.. 💞".format(message.from_user.mention))
        await asyncio.sleep(0.1)
        await lol.edit_text("نــورت يـا غــالـي ꨄ︎ {}.. 💕".format(message.from_user.mention))
        await asyncio.sleep(0.1)
        await lol.edit_text("نــورت يـا غــالـي ꨄ︎ {}.. 💜".format(message.from_user.mention))
        
        try:
            await lol.delete()
        except:
            pass
        
        # --- 3. جاري التشغيل ---
        lols = await message.reply_text("🤍 جـ")
        await asyncio.sleep(0.1)
        await lols.edit_text("🤍 جــ")        
        await asyncio.sleep(0.1)
        await lols.edit_text("🤍 جــا")
        await asyncio.sleep(0.1)
        await lols.edit_text("🤍 جــار")
        await asyncio.sleep(0.1)
        await lols.edit_text("🤍 جــاري")
        await asyncio.sleep(0.1)
        await lols.edit_text("🤍 جــاري الـ")
        await asyncio.sleep(0.1)
        await lols.edit_text("🤍 جــاري التـ")
        await asyncio.sleep(0.1)
        await lols.edit_text("🤍 جــاري التشـ")
        await asyncio.sleep(0.1)
        await lols.edit_text("🤍 جــاري التشغيـ")
        await asyncio.sleep(0.1)
        await lols.edit_text("🤍 جــاري التشغيل")
        await asyncio.sleep(0.1)
        await lols.edit_text("🤍 جــاري التشغيل .")
        await asyncio.sleep(0.1)
        await lols.edit_text("🤍 جــاري التشغيل . .")
        await asyncio.sleep(0.1)
        await lols.edit_text("🤍 جــاري التشغيل . . .")

        # --- 4. الاستيكر ---
        m = None
        try:
            m = await message.reply_sticker("CAACAgUAAyEFAATXFFgrAAIDymlfzq3ZMbEh_bgdkjEhg2QMBib-AAILFQAC-vEZVMBmWHCQ-sJuHgQ")
        except:
            pass
        
        # --- 5. أولوية الصورة ---
        if client.me.photo:
            chat_photo = client.me.photo.big_file_id
        elif message.from_user.photo:
            chat_photo = message.from_user.photo.big_file_id
        else:
            chat_photo = START_IMG_URL
        
        # --- 6. التنظيف والارسال النهائي ---
        if lols:
            try:
                await lols.delete()
            except:
                pass
        if m:
            try:
                await m.delete()
            except:
                pass
        
        try:
            await message.reply_photo(
                photo=chat_photo,
                caption=_["start_2"].format(message.from_user.mention, app.mention),
                reply_markup=InlineKeyboardMarkup(out),
            )
        except Exception as e:
            await message.reply_photo(
                photo=START_IMG_URL,
                caption=_["start_2"].format(message.from_user.mention, app.mention),
                reply_markup=InlineKeyboardMarkup(out),
            )

        # اللوج (معدل ليتوافق مع الكونفج بتاعك)
        if getattr(config, "LOG", True): 
            if LOGGER_ID != 0:
                sender_id = message.from_user.id
                sender_name = message.from_user.first_name
                try:
                    await app.send_message(
                        LOGGER_ID,
                        f"{message.from_user.mention} قــام بـبـدء الـبـوت .. ⚡\n\n**آيــدي الـشـخـص :** {sender_id}\n**الاســم:** {sender_name}",
                    )
                except:
                    pass

@app.on_message(filters.command(["start"]) & filters.group & ~BANNED_USERS)
@LanguageStart
async def start_gp(client, message: Message, _):
    out = start_panel(_)
    uptime = int(time.time() - _boot_)
    await message.reply_photo(
        photo=START_IMG_URL,
        caption=_["start_1"].format(app.mention, get_readable_time(uptime)),
        reply_markup=InlineKeyboardMarkup(out),
    )
    return await add_served_chat(message.chat.id)


@app.on_message(filters.new_chat_members, group=-1)
async def welcome(client, message: Message):
    for member in message.new_chat_members:
        try:
            language = await get_lang(message.chat.id)
            _ = get_string(language)
            if await is_banned_user(member.id):
                try:
                    await message.chat.ban_member(member.id)
                except:
                    pass
            if member.id == app.id:
                if message.chat.type != ChatType.SUPERGROUP:
                    await message.reply_text(_["start_4"])
                    return await app.leave_chat(message.chat.id)
                if message.chat.id in await blacklisted_chats():
                    await message.reply_text(
                        _["start_5"].format(
                            app.mention,
                            f"https://t.me/{app.username}?start=sudolist",
                            config.SUPPORT_CHAT,
                        ),
                        disable_web_page_preview=True,
                    )
                    return await app.leave_chat(message.chat.id)

                out = start_panel(_)
                await message.reply_photo(
                    photo=START_IMG_URL,
                    caption=_["start_3"].format(
                        message.from_user.first_name,
                        app.mention,
                        message.chat.title,
                        app.mention,
                    ),
                    reply_markup=InlineKeyboardMarkup(out),
                )
                await add_served_chat(message.chat.id)
                await message.stop_propagation()
        except Exception as ex:
            print(ex)
