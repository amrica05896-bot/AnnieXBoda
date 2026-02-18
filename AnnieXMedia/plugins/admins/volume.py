# Authored By Certified Coders (c) 2026
# Module: Volume Control
# Description: Controls stream volume (0-200%) via PyTgCalls v3.0
# Specs: No Emojis, Hardcoded Arabic Text

from pyrogram import filters
from pyrogram.types import Message

from AnnieXMedia import app
# تأكد أن هذا السطر صحيح ويستورد StreamController من المكان الصحيح
from AnnieXMedia.core.call import StreamController
from AnnieXMedia.utils.decorators import AdminRightsCheck

# اوامر التشغيل
COMMANDS = [
    "volume", "vol", "changevolume", 
    "علي", "عالي", "ارفع", "زود",
    "وطي", "واطي", "نزل", "خفض",
    "صوت", "الصوت"
]

@app.on_message(
    filters.command(COMMANDS, prefixes=["/", "!", "%", ",", "", ".", "@", "#"])
    & filters.group
)
@AdminRightsCheck
async def change_volume_command(cli, message: Message, _, chat_id):
    # ملاحظة: إذا كان الديكوريتور لا يمرر chat_id كمعامل رابع، سيحدث خطأ.
    # الكود هنا يفترض أن الديكوريتور @AdminRightsCheck يمرر (client, message, _, chat_id)
    
    # التحقق من وجود رقم بجانب الامر
    if len(message.command) < 2:
        return await message.reply_text(
            "يجب كتابة رقم بجانب الامر لتغيير الصوت\nمثال: علي 150"
        )

    query = message.text.split(None, 1)[1].strip()

    # التحقق ان المدخل ارقام فقط
    if not query.isnumeric():
        return await message.reply_text(
            "الرجاء كتابة ارقام فقط"
        )

    volume = int(query)

    # تحديد الحد الاقصى والادنى للصوت
    if volume > 200:
        volume = 200
        await message.reply_text(
            "تم ضبط الصوت على الحد الاقصى 200 بالمئة تلقائيا حفاظا على الجودة"
        )
    elif volume < 0:
        volume = 0

    try:
        # تغيير الصوت عبر ملف الكول
        # ملاحظة: هذا يتطلب أن تكون المحادثة (الجروب) به مكالمة نشطة
        await StreamController.change_volume_call(chat_id, volume)
        
        # رسالة التاكيد
        await message.reply_text(f"تم تغيير مستوى الصوت الى: {volume}%")
        
    except AttributeError:
        await message.reply_text("حدث خطأ: دالة تغيير الصوت غير مدعومة في ملف الكول الحالي.")
    except Exception as e:
        await message.reply_text(f"حدث خطأ اثناء تغيير الصوت: {e}")
