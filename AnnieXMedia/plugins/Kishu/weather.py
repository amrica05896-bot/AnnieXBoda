# Authored By Certified Coders © 2026
import httpx
from pyrogram import Client, filters, enums
from pyrogram.types import Message
from AnnieXMedia import app

timeout = httpx.Timeout(40.0)
http = httpx.AsyncClient(http2=True, timeout=timeout)

weather_apikey = "8de2d8b3a93542c9a2d8b3a935a2c909"
get_coords_url = "https://api.weather.com/v3/location/search"
weather_data_url = "https://api.weather.com/v3/aggcommon/v3-wx-observations-current"

headers = {
    "User-Agent": "Dalvik/2.1.0 (Linux; U; Android 12; M2012K11AG Build/SQ1D.211205.017)"
}


@app.on_message(filters.command(["الطقس"], prefixes=[""]))
async def weather_command(client: Client, message: Message):
    if len(message.command) == 1:
        return await message.reply_text(
            "<b>الاستخدام:</b> <code>الطقس [اسم المدينة]</code>\nمثال: <code>الطقس القاهرة</code>",
            parse_mode=enums.ParseMode.HTML
        )

    query = message.text.split(maxsplit=1)[1]

    try:
        coord_response = await http.get(
            get_coords_url,
            headers=headers,
            params={
                "apiKey": weather_apikey,
                "format": "json",
                "language": "ar",
                "query": query
            },
        )
        coord_data = coord_response.json()

        if not coord_data.get("location"):
            return await message.reply_text(
                "<b>لم يتم العثور على المدينة.</b> يرجى تجربة مدينة أخرى.",
                parse_mode=enums.ParseMode.HTML
            )

        latitude = coord_data["location"]["latitude"][0]
        longitude = coord_data["location"]["longitude"][0]
        location_name = coord_data["location"]["address"][0]

        weather_response = await http.get(
            weather_data_url,
            headers=headers,
            params={
                "apiKey": weather_apikey,
                "format": "json",
                "language": "ar",
                "geocode": f"{latitude},{longitude}",
                "units": "m"
            },
        )
        weather_data = weather_response.json()
        obs = weather_data.get("v3-wx-observations-current", {})

        if not obs:
            return await message.reply_text(
                "<b>بيانات الطقس غير متوفرة</b> في الوقت الحالي.",
                parse_mode=enums.ParseMode.HTML
            )

        weather_text = (
            f"<b>{location_name}</b>\n\n"
            f"<b>درجة الحرارة:</b> <code>{obs.get('temperature', 'N/A')} °C</code>\n"
            f"<b>الإحساس الفعلي:</b> <code>{obs.get('temperatureFeelsLike', 'N/A')} °C</code>\n"
            f"<b>الرطوبة:</b> <code>{obs.get('relativeHumidity', 'N/A')}%</code>\n"
            f"<b>سرعة الرياح:</b> <code>{obs.get('windSpeed', 'N/A')} كم/س</code>\n"
            f"<b>الحالة:</b> <i>{obs.get('wxPhraseLong', 'N/A')}</i>"
        )

        await message.reply_text(weather_text, parse_mode=enums.ParseMode.HTML)

    except Exception as e:
        print(f"Error in weather: {e}")
        await message.reply_text(
            "<b>حدث خطأ</b> أثناء جلب بيانات الطقس. يرجى المحاولة لاحقا.",
            parse_mode=enums.ParseMode.HTML
        )
