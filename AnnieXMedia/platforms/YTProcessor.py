# Authored By Certified Coders © 2026
# System: YTProcessor | Full Indentation & Syntax Fix

import asyncio
import os
import time
import glob
import shutil
import yt_dlp
from concurrent.futures import ThreadPoolExecutor
from pyrogram.types import InputMediaAudio, InputMediaVideo, InlineKeyboardButton
from pyrogram.errors import MessageIdInvalid, MessageNotModified, FloodWait

from config import LOGGER_ID, OWNER_ID
from AnnieXMedia import LOGGER
from AnnieXMedia.utils.formatters import convert_bytes

class Config:
    # استخدام الرامات (RAM Disk) للتخزين المؤقت للسرعة القصوى
    if os.path.exists("/dev/shm"):
        DOWNLOAD_PATH = "/dev/shm/AnnieDownloads"
    else:
        DOWNLOAD_PATH = os.path.abspath("downloads")

    MAX_WORKERS = 16   
    USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"

# ✅ إنشاء المجلد (تمت إضافة # للتصحيح)
if not os.path.exists(Config.DOWNLOAD_PATH):
    os.makedirs(Config.DOWNLOAD_PATH, exist_ok=True)

class YTProcessorAPI:
    def __init__(self): # ✅ تم تصحيح الاسم لـ __init__
        self.pool = ThreadPoolExecutor(max_workers=Config.MAX_WORKERS)
        self._clean_cache()

    def _clean_cache(self):  
        try:  
            for filename in os.listdir(Config.DOWNLOAD_PATH):  
                file_path = os.path.join(Config.DOWNLOAD_PATH, filename)  
                if os.path.isfile(file_path) or os.path.islink(file_path):  
                    os.unlink(file_path)  
                elif os.path.isdir(file_path):  
                    shutil.rmtree(file_path)  
        except Exception:  
            pass  

    def get_cookie_file(self):  
        possible_paths = [  
            "cookies.txt", "AnnieXMedia/cookies.txt",  
            "assets/cookies.txt", "AnnieXMedia/assets/cookies.txt",  
            "platforms/cookies.txt", "/app/cookies.txt"  
        ]  
        for path in possible_paths:  
            if os.path.exists(path) and os.path.getsize(path) > 0:  
                return path  
        return None  

    async def get_quality_buttons(self, vidid, stype):  
        yturl = f"https://www.youtube.com/watch?v={vidid}"  
        cookie_file = self.get_cookie_file()  
          
        ydl_opts = {  
            "quiet": True,  
            "cookiefile": cookie_file,  
            "no_warnings": True,  
            "ignoreerrors": True,  
            "nocheckcertificate": True,  
            "remote_components": ["ejs:github"],  
        }  
          
        loop = asyncio.get_running_loop()  
          
        def _fetch_info():  
            try:  
                opts = ydl_opts.copy()  
                opts['extractor_args'] = {'youtube': {'player_client': ['web']}}  
                with yt_dlp.YoutubeDL(opts) as ydl:  
                    return ydl.extract_info(yturl, download=False)  
            except:  
                return None  

        formats = []  
        try:  
            info = await loop.run_in_executor(self.pool, _fetch_info)  
            if info: formats = info.get("formats", [])  
        except:  
            pass   

        keyboard = []  
        if stype == "audio":  
            keyboard.append([InlineKeyboardButton(text="💎 جـودة الـمـالـك (320)", callback_data=f"song_download audio|high|{vidid}")])  
            keyboard.append([InlineKeyboardButton(text="جـودة مـتـوسـطـة (128)", callback_data=f"song_download audio|mid|{vidid}")])  
            keyboard.append([InlineKeyboardButton(text="جـودة مـنـخـفـضـة", callback_data=f"song_download audio|low|{vidid}")])  
        else:  
            has_high = False  
            if formats:  
                for x in formats:  
                    h = x.get("height")  
                    if h and h >= 1080: has_high = True  

            if has_high:  
                keyboard.append([InlineKeyboardButton(text="💎 جـودة الـمـالـك (4K/1080)", callback_data=f"song_download video|high|{vidid}")])  
            keyboard.append([InlineKeyboardButton(text="جـودة مـتـوسـطـة (720/480)", callback_data=f"song_download video|mid|{vidid}")])  
            keyboard.append([InlineKeyboardButton(text="جـودة مـنـخـفـضـة (360/144)", callback_data=f"song_download video|low|{vidid}")])  
          
        keyboard.append([InlineKeyboardButton(text="إغـلاق", callback_data="close")])  
        return keyboard  

    async def download_file(self, url, quality_arg, is_video, title, vidid=None, is_owner=False):  
        vid_id_str = vidid if vidid else str(int(time.time()))  
        output_template = os.path.join(Config.DOWNLOAD_PATH, f"{vid_id_str}.%(ext)s")  
        cookie_file = self.get_cookie_file()  
        
        if not url.startswith("http") and vidid:   
            url = f"https://www.youtube.com/watch?v={vidid}"  

        aria2_args = [  
            "-x", "16", "-s", "16", "-j", "16", "-k", "1M",  
            "--file-allocation=none", "--disable-ipv6=true",  
            "--max-connection-per-server=16"  
        ]  

        is_hls = "m3u8" in url  

        base_opts = {  
            "outtmpl": output_template,  
            "cookiefile": cookie_file,  
            "geo_bypass": True,  
            "nocheckcertificate": True,  
            "quiet": True,  
            "noplaylist": True,  
            "external_downloader": "aria2c" if not is_hls else None,  
            "external_downloader_args": aria2_args if not is_hls else None,  
            "writethumbnail": True,   
            "socket_timeout": 60,  
            "retries": 10,  
            "remote_components": ["ejs:github"],  
        }  
          
        if is_video:  
            if is_owner:  
                fmt = "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best" if quality_arg == "high" else "bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/best[height<=1080][ext=mp4]/best"  
            else:  
                fmt = "bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/best[height<=720][ext=mp4]/best"  
            base_opts["postprocessors"] = [{'key': 'FFmpegMetadata', 'add_metadata': True}]  
        else:  
            q_rate = '320' if is_owner and quality_arg == "high" else '128'  
            fmt = "bestaudio[ext=m4a]/bestaudio/best"  
            base_opts["postprocessors"] = [  
                {'key': 'FFmpegExtractAudio', 'preferredcodec': 'mp3', 'preferredquality': q_rate},  
                {'key': 'FFmpegMetadata', 'add_metadata': True},  
                {'key': 'EmbedThumbnail'}  
            ]  

        base_opts['format'] = fmt  
        loop = asyncio.get_running_loop()  

        def _run_download():  
            try:  
                opts = base_opts.copy()  
                opts['extractor_args'] = {'youtube': {'player_client': ['web', 'android']}}  
                with yt_dlp.YoutubeDL(opts) as ydl:  
                    ydl.download([url])  
                
                search_pattern = os.path.join(Config.DOWNLOAD_PATH, f"{vid_id_str}.*")  
                found_files = glob.glob(search_pattern)  
                valid_extensions = ('.mp3', '.mp4', '.m4a', '.webm', '.mkv', '.ts')  
                best_file, max_size = None, 0  
                  
                for f in found_files:  
                    if f.endswith(valid_extensions):  
                        size = os.path.getsize(f)  
                        if size > 1024 and size > max_size:  
                            max_size, best_file = size, f  
                return best_file  
            except Exception as e:  
                print(f"Download Error: {e}")  
                return None  

        return await loop.run_in_executor(self.pool, _run_download)  

    async def upload_alexa_style(self, client, mystic_msg, file_path, is_video, title, duration, user_name, vidid=None):  
        if not file_path or not os.path.exists(file_path):  
            return False  

        caption = f"**الـعـنـوان:** {title}\n**طـلـب:** {user_name}"  
        chat_id = mystic_msg.chat.id  
        thumb_path = None  
        base_name = os.path.splitext(file_path)[0]  
          
        for ext in [".webp", ".jpg", ".jpeg", ".png"]:  
            if os.path.exists(f"{base_name}{ext}"):  
                thumb_path = f"{base_name}{ext}"  
                break  
          
        if not thumb_path and vidid:  
             possible_files = glob.glob(os.path.join(Config.DOWNLOAD_PATH, f"*{vidid}*"))  
             for f in possible_files:  
                if f.endswith((".webp", ".jpg", ".jpeg", ".png")) and not f.endswith((".mp3", ".mp4", ".m4a")):  
                    thumb_path = f  
                    break  

        try:  
            if is_video:  
                media = InputMediaVideo(media=file_path, thumb=thumb_path, caption=caption, duration=duration, supports_streaming=True)  
            else:  
                media = InputMediaAudio(media=file_path, thumb=thumb_path, caption=caption, duration=duration, title=title, performer=user_name)  
            await mystic_msg.edit_media(media=media)  
        except (MessageIdInvalid, MessageNotModified):  
            try:  
                try: await mystic_msg.delete()  
                except: pass  
                if is_video:  
                    await client.send_video(chat_id, video=file_path, caption=caption, duration=duration, thumb=thumb_path, supports_streaming=True)  
                else:  
                    await client.send_audio(chat_id, audio=file_path, caption=caption, duration=duration, title=title, performer=user_name, thumb=thumb_path)  
            except:  
                return False  
        except Exception:  
            try:  
                if is_video:  
                    await client.send_video(chat_id, video=file_path, caption=caption, duration=duration)  
                else:  
                    await client.send_audio(chat_id, audio=file_path, caption=caption, duration=duration, title=title, performer=user_name)  
            except:  
                return False  
        return True  

    async def download_playlist(self, client, mystic_msg, playlist_url, is_video, user_name, limit=30):  
        cookie_file = self.get_cookie_file()  
        loop = asyncio.get_running_loop()  
          
        ydl_opts = {  
            "extract_flat": True,   
            "playlistend": limit,  
            "quiet": True,  
            "cookiefile": cookie_file,  
            "user_agent": Config.USER_AGENT,  
            "no_warnings": True,  
            "ignoreerrors": True,  
            "remote_components": ["ejs:github"],  
        }  

        def _fetch_playlist():  
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:  
                return ydl.extract_info(playlist_url, download=False)  

        await mystic_msg.edit_text("**جـارٍ جـلـب الـقـائـمـة...**")  
        try:  
            info = await loop.run_in_executor(self.pool, _fetch_playlist)  
        except:  
            return await mystic_msg.edit_text("**❌ فـشـل الـجـلـب.**")  

        if not info or 'entries' not in info:  
            return await mystic_msg.edit_text("**❌ لا يـوجـد مـحـتـوى.**")  

        entries, total = info['entries'], len(info['entries'])  
        await mystic_msg.edit_text(f"**✅ تـم كـشـف {total} مـلـف.\nجـارٍ الـبـدء...**")  
          
        count = 0  
        for entry in entries:  
            count += 1  
            vid_id = entry.get('id')  
            title = entry.get('title', f"Track {count}")  
            url = f"https://www.youtube.com/watch?v={vid_id}"  
              
            if count % 2 == 0:   
                try: await mystic_msg.edit_text(f"**📥 تـحـمـيـل: {count}/{total}**\n**🎵 {title}**")  
                except: pass  

            file_path = await self.download_file(url, "mid" if is_video else "high", is_video, title, vidid=vid_id, is_owner=True)  
            if file_path:  
                temp_msg = await client.send_message(mystic_msg.chat.id, "**⬆️ رفـع...**")  
                await self.upload_alexa_style(client, temp_msg, file_path, is_video, title, 0, user_name, vidid=vid_id)  
                try:  
                    os.remove(file_path)  
                    base = os.path.splitext(file_path)[0]  
                    for ext in [".jpg", ".webp", ".png"]:   
                        if os.path.exists(base+ext): os.remove(base+ext)  
                except: pass  
            await asyncio.sleep(1)  
        await mystic_msg.edit_text(f"**✅ تـم الانـتـهـاء!**")

Processor = YTProcessorAPI()
