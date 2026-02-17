# Authored By Certified Coders © 2026
# System: Spotify API (Search & Bridge to Youtube Download)

import re
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials
from youtubesearchpython.aio import VideosSearch

import config
# نستدعي المحرك الرئيسي
from AnnieXMedia.platforms.Youtube import YouTube

class SpotifyAPI:
    def __init__(self):
        self.regex = r"^https:\/\/open\.spotify\.com\/.+"
        self.client_id = config.SPOTIFY_CLIENT_ID
        self.client_secret = config.SPOTIFY_CLIENT_SECRET
        
        if self.client_id and self.client_secret:
            self.client_credentials_manager = SpotifyClientCredentials(
                self.client_id, self.client_secret
            )
            self.spotify = spotipy.Spotify(
                client_credentials_manager=self.client_credentials_manager
            )
        else:
            self.spotify = None

    async def valid(self, link: str) -> bool:
        return bool(re.search(self.regex, link or ""))

    async def track(self, link: str):
        """
        جلب بيانات التراك من سبوتيفاي والبحث عن بديل في يوتيوب
        """
        if not self.spotify:
            raise RuntimeError("Spotify credentials not configured")
        
        try:
            track = self.spotify.track(link)
        except Exception:
            return None, None

        # تكوين جملة البحث: اسم الأغنية + اسم الفنان
        info = track["name"]
        for artist in track["artists"]:
            fetched = f' {artist["name"]}'
            if "Various Artists" not in fetched:
                info += fetched
        
        # البحث في يوتيوب باستخدام مكتبتك المحدثة
        try:
            results = VideosSearch(info, limit=1)
            # بما أننا حدثنا المكتبة لـ Async، نستخدم init() أو next() مباشرة حسب التعديل الأخير
            # الكود هنا متوافق مع نسخة (async next)
            data = await results.next()
            
            if not data.get("result"):
                return None, None

            r = data["result"][0]
            
            track_details = {
                "title": r["title"],
                "link": r["link"], # هذا هو رابط يوتيوب الذي سنحمله
                "vidid": r["id"],
                "duration_min": r["duration"],
                "thumb": r["thumbnails"][0]["url"].split("?")[0],
            }
            return track_details, track_details["vidid"]
        except Exception:
            return None, None

    async def download(self, link: str):
        """
        دالة التحميل:
        1. البحث والحصول على رابط يوتيوب.
        2. تمرير الرابط لـ YouTube.download.
        """
        details, vidid = await self.track(link)
        if not details:
            return False, False

        yt_link = details["link"]
        title = details["title"]

        # التحميل عبر المحرك المركزي (يستفيد من Aria2 وكاش يوتيوب)
        try:
            path, _ = await YouTube.download(
                yt_link,
                mystic=None,
                videoid=vidid,
                songaudio=True, # نريد ملف صوتي
                title=title
            )
        except Exception:
            return False, False

        if path:
            details["filepath"] = path
            return details, path
        
        return False, False

    async def playlist(self, url):
        if not self.spotify:
            raise RuntimeError("Spotify credentials not configured")
        try:
            playlist = self.spotify.playlist(url)
            playlist_id = playlist["id"]
            results = []
            for item in playlist["tracks"]["items"]:
                music_track = item["track"]
                info = music_track["name"]
                for artist in music_track["artists"]:
                    fetched = f' {artist["name"]}'
                    if "Various Artists" not in fetched:
                        info += fetched
                results.append(info)
            return results, playlist_id
        except Exception:
            return [], None

    async def album(self, url):
        if not self.spotify:
            raise RuntimeError("Spotify credentials not configured")
        try:
            album = self.spotify.album(url)
            album_id = album["id"]
            results = []
            for item in album["tracks"]["items"]:
                info = item["name"]
                for artist in item["artists"]:
                    fetched = f' {artist["name"]}'
                    if "Various Artists" not in fetched:
                        info += fetched
                results.append(info)
            return results, album_id
        except Exception:
            return [], None

    async def artist(self, url):
        if not self.spotify:
            raise RuntimeError("Spotify credentials not configured")
        try:
            artistinfo = self.spotify.artist(url)
            artist_id = artistinfo["id"]
            results = []
            artisttoptracks = self.spotify.artist_top_tracks(url)
            for item in artisttoptracks["tracks"]:
                info = item["name"]
                for artist in item["artists"]:
                    fetched = f' {artist["name"]}'
                    if "Various Artists" not in fetched:
                        info += fetched
                results.append(info)
            return results, artist_id
        except Exception:
            return [], None
