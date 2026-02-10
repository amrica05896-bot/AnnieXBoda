# Authored By Certified Coders © 2026
import os
from pyrogram import Client
import config
from ..logging import LOGGER

assistants = []
assistantids = []

GROUPS_TO_JOIN = [
    "CertifiedDiscussion",
    "CertifiedCoders",
    "CertifiedCodes",
    "CertifiedDevs",
    "CertifiedNetwork",
]

class Userbot:
    def __init__(self):
        # 🔥 خطوة التنظيف الذاتي: حذف ملفات الجلسة التالفة قبل البدء
        # هذا يحل مشكلة unpack error نهائياً
        self.clean_session_files()

        self.one = Client(
            "AnnieAssis1",
            api_id=config.API_ID,
            api_hash=config.API_HASH,
            session_string=str(config.STRING1),
            no_updates=False,
            in_memory=True, 
        )
        self.two = Client(
            "AnnieAssis2",
            api_id=config.API_ID,
            api_hash=config.API_HASH,
            session_string=str(config.STRING2),
            no_updates=False,
            in_memory=True, 
        )
        self.three = Client(
            "AnnieAssis3",
            api_id=config.API_ID,
            api_hash=config.API_HASH,
            session_string=str(config.STRING3),
            no_updates=False,
            in_memory=True, 
        )
        self.four = Client(
            "AnnieAssis4",
            api_id=config.API_ID,
            api_hash=config.API_HASH,
            session_string=str(config.STRING4),
            no_updates=False,
            in_memory=True, 
        )
        self.five = Client(
            "AnnieAssis5",
            api_id=config.API_ID,
            api_hash=config.API_HASH,
            session_string=str(config.STRING5),
            no_updates=False,
            in_memory=True, 
        )

    def clean_session_files(self):
        """دالة لحذف ملفات الجلسة القديمة من السيرفر لمنع التعارض"""
        sessions = [
            "AnnieAssis1.session", "AnnieAssis2.session", 
            "AnnieAssis3.session", "AnnieAssis4.session", "AnnieAssis5.session"
        ]
        LOGGER(__name__).info("🧹 جـارٍ تنظيف ملفات الجلسة التالفة من السيرفر...")
        for session in sessions:
            try:
                if os.path.exists(session):
                    os.remove(session)
                    LOGGER(__name__).info(f"✅ تم حذف الملف التالف: {session}")
            except Exception as e:
                LOGGER(__name__).error(f"⚠️ خطأ أثناء حذف {session}: {e}")

    async def start_assistant(self, client: Client, index: int):
        string_attr = [
            config.STRING1,
            config.STRING2,
            config.STRING3,
            config.STRING4,
            config.STRING5,
        ][index - 1]
        
        if not string_attr:
            return

        try:
            await client.start()
            for group in GROUPS_TO_JOIN:
                try:
                    await client.join_chat(group)
                except Exception:
                    pass

            assistants.append(index)

            try:
                await client.send_message(
                    config.LOGGER_ID, f"☔ تـم بـدء تـشـغـيـل الـمـسـاعـد {index} بـنـجـاح"
                )
            except Exception:
                LOGGER(__name__).error(
                    f"💝 الـمـسـاعـد {index} لا يـمـكـنـه الـوصـول لـجـروب الـسـجـل.. تـحـقـق مـن الـأذونـات!"
                )
            
            me = await client.get_me()
            client.id, client.name, client.username = me.id, me.first_name, me.username
            assistantids.append(me.id)

            LOGGER(__name__).info(f"☔ تـم تـشـغـيـل الـمـسـاعـد {index} بـهـويـة: {client.name}")

        except Exception as e:
            LOGGER(__name__).error(f"💝 فـشـل فـي بـدء الـمـسـاعـد {index}.. الـخـطـأ: {e}")

    async def start(self):
        LOGGER(__name__).info("💝 جـارٍ بـدء تـشـغـيـل حـسـابـات الـمـسـاعـد...")
        await self.start_assistant(self.one, 1)
        if config.STRING2: await self.start_assistant(self.two, 2)
        if config.STRING3: await self.start_assistant(self.three, 3)
        if config.STRING4: await self.start_assistant(self.four, 4)
        if config.STRING5: await self.start_assistant(self.five, 5)

    async def stop(self):
        LOGGER(__name__).info("☔ جـارٍ إيـقـاف الـمـسـاعـد...")
        try:
            if config.STRING1: await self.one.stop()
            if config.STRING2: await self.two.stop()
            if config.STRING3: await self.three.stop()
            if config.STRING4: await self.four.stop()
            if config.STRING5: await self.five.stop()
        except Exception as e:
            LOGGER(__name__).error(f"💝 خـطـأ أثـنـاء إيـقـاف الـمـسـاعـد: {e}")
