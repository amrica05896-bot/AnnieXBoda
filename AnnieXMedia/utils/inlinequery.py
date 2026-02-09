# Authored By Certified Coders © 2026
# Module: Inline Query Articles (Top 6 Only)

from pyrogram.types import InlineQueryResultArticle, InputTextMessageContent

answer = []

answer.extend(
    [
        # 1. Pause
        InlineQueryResultArticle(
            title="Pᴀᴜsᴇ",
            description="ᴩᴀᴜsᴇ ᴛʜᴇ ᴄᴜʀʀᴇɴᴛ ᴩʟᴀʏɪɴɢ sᴛʀᴇᴀᴍ ᴏɴ ᴠɪᴅᴇᴏᴄʜᴀᴛ.",
            thumb_url="https://files.catbox.moe/exvq3d.jpg",
            input_message_content=InputTextMessageContent("/pause"),
        ),
        # 2. Resume
        InlineQueryResultArticle(
            title="Rᴇsᴜᴍᴇ",
            description="ʀᴇsᴜᴍᴇ ᴛʜᴇ ᴩᴀᴜsᴇᴅ sᴛʀᴇᴀᴍ ᴏɴ ᴠɪᴅᴇᴏᴄʜᴀᴛ.",
            thumb_url="https://files.catbox.moe/kmn0a6.jpg",
            input_message_content=InputTextMessageContent("/resume"),
        ),
        # 3. Skip
        InlineQueryResultArticle(
            title="Sᴋɪᴩ",
            description="sᴋɪᴩ ᴛʜᴇ ᴄᴜʀʀᴇɴᴛ ᴩʟᴀʏɪɴɢ sᴛʀᴇᴀᴍ ᴏɴ ᴠɪᴅᴇᴏᴄʜᴀᴛ ᴀɴᴅ ᴍᴏᴠᴇs ᴛᴏ ᴛʜᴇ ɴᴇxᴛ sᴛʀᴇᴀᴍ.",
            thumb_url="https://files.catbox.moe/zs9g3f.jpg",
            input_message_content=InputTextMessageContent("/skip"),
        ),
        # 4. End
        InlineQueryResultArticle(
            title="Eɴᴅ",
            description="ᴇɴᴅ ᴛʜᴇ ᴄᴜʀʀᴇɴᴛ ᴩʟᴀʏɪɴɢ sᴛʀᴇᴀᴍ ᴏɴ ᴠɪᴅᴇᴏᴄʜᴀᴛ.",
            thumb_url="https://files.catbox.moe/b91yyd.jpg",
            input_message_content=InputTextMessageContent("/end"),
        ),
        # 5. Shuffle
        InlineQueryResultArticle(
            title="Sʜᴜғғʟᴇ",
            description="sʜᴜғғʟᴇ ᴛʜᴇ ǫᴜᴇᴜᴇᴅ sᴏɴɢs ɪɴ ᴩʟᴀʏʟɪsᴛ.",
            thumb_url="https://files.catbox.moe/wqipfn.jpg",
            input_message_content=InputTextMessageContent("/shuffle"),
        ),
        # 6. Loop
        InlineQueryResultArticle(
            title="Lᴏᴏᴩ",
            description="ʟᴏᴏᴩ ᴛʜᴇ ᴄᴜʀʀᴇɴᴛ ᴩʟᴀʏɪɴɢ ᴛʀᴀᴄᴋ ᴏɴ ᴠɪᴅᴇᴏᴄʜᴀᴛ.",
            thumb_url="https://files.catbox.moe/4qhfqw.jpg",
            input_message_content=InputTextMessageContent("/loop 3"),
        ),
    ]
)
