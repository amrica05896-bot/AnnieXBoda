# Authored By Certified Coders © 2026
# Path: AnnieXMedia/__init__.py

import pyromod.listen
from AnnieXMedia.core.bot import MusicBotClient
from AnnieXMedia.core.dir import StorageManager
from AnnieXMedia.core.git import git
from AnnieXMedia.core.userbot import Userbot
from AnnieXMedia.misc import dbb, heroku
from .logging import LOGGER

# 1. تهيئة المجلدات وقاعدة البيانات
StorageManager()
git()
dbb()
heroku()

# 2. تعريف العملاء (كده دول بقوا جاهزين للاستخدام)
app = MusicBotClient()
userbot = Userbot()

# 3. تعريف منصات التشغيل (لازم قبل الـ API)
from .platforms import *

Apple = AppleAPI()
Carbon = CarbonAPI()
SoundCloud = SoundAPI()
Spotify = SpotifyAPI()
Resso = RessoAPI()
Telegram = TeleAPI()
YouTube = YouTubeAPI()

# 🔥 4. استدعاء الـ API في الأخر خالص عشان نكسر الدائرة المغلقة
from AnnieXMedia.core.api import BotAPI
