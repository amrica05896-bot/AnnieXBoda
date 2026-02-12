# Authored By Certified Coders © 2026
from pyrogram import Client
import config
from ..logging import LOGGER

assistants = []
assistantids = []

class Userbot:
    def __init__(self):
        # تم ضبط no_updates=False عشان المساعد يشوف تحديثات الكول كويس
        self.one = Client(
            "AnnieAssis1",
            config.API_ID,
            config.API_HASH,
            session_string=str(config.STRING1),
            no_updates=False,
        )
        self.two = Client(
            "AnnieAssis2",
            config.API_ID,
            config.API_HASH,
            session_string=str(config.STRING2),
            no_updates=False,
        )
        self.three = Client(
            "AnnieAssis3",
            config.API_ID,
            config.API_HASH,
            session_string=str(config.STRING3),
            no_updates=False,
        )
        self.four = Client(
            "AnnieAssis4",
            config.API_ID,
            config.API_HASH,
            session_string=str(config.STRING4),
            no_updates=False,
        )
        self.five = Client(
            "AnnieAssis5",
            config.API_ID,
            config.API_HASH,
            session_string=str(config.STRING5),
            no_updates=False,
        )

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
            
            # ❌ تم حذف كود الانضمام التلقائي للجروبات من هنا

            assistants.append(index)

            # ارسال رسالة تأكيد بدء المساعد
            try:
                await client.send_message(
                    config.LOGGER_ID, f"☔ تم بدء تشغيل المساعد {index} بنجاح"
                )
            except Exception:
                LOGGER(__name__).error(
                    f"💝 المساعد {index} لا يمكنه الوصول لجروب السجل.. تحقق من الأذونات!"
                )
                
            me = await client.get_me()
            client.id, client.name, client.username = me.id, me.first_name, me.username
            assistantids.append(me.id)

            LOGGER(__name__).info(f"☔ تم تشغيل المساعد {index} بهوية: {client.name}")

        except Exception as e:
            LOGGER(__name__).error(f"💝 فشل في بدء المساعد {index}.. الخطأ: {e}")

    async def start(self):
        LOGGER(__name__).info("💝 جارٍ بدء تشغيل حسابات المساعدين...")
        if config.STRING1: await self.start_assistant(self.one, 1)
        if config.STRING2: await self.start_assistant(self.two, 2)
        if config.STRING3: await self.start_assistant(self.three, 3)
        if config.STRING4: await self.start_assistant(self.four, 4)
        if config.STRING5: await self.start_assistant(self.five, 5)

    async def stop(self):
        LOGGER(__name__).info("☔ جارٍ إيقاف المساعدين...")
        try:
            if config.STRING1: await self.one.stop()
            if config.STRING2: await self.two.stop()
            if config.STRING3: await self.three.stop()
            if config.STRING4: await self.four.stop()
            if config.STRING5: await self.five.stop()
        except Exception as e:
            LOGGER(__name__).error(f"💝 خطأ أثناء إيقاف المساعدين: {e}")
