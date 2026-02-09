# Authored By Certified Coders © 2026
# Optimized for Pillow 10.x & Arabic Text Support (Real Fix)

import os
import re
import asyncio
import aiofiles
import aiohttp
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont, ImageOps
from youtubesearchpython.aio import VideosSearch
from config import YOUTUBE_IMG_URL
from AnnieXMedia.core.dir import CACHE_DIR 

# ✅ استيراد مكتبات تصحيح العربي
try:
    import arabic_reshaper
    from bidi.algorithm import get_display
except ImportError:
    print("⚠️ Arabic libraries not installed. Install 'arabic-reshaper' and 'python-bidi'")
    arabic_reshaper = None
    get_display = None

# ================= CONSTANTS (Glassmorphism Layout) =================
PANEL_W, PANEL_H = 1100, 600  # Wider Panel
PANEL_X = (1280 - PANEL_W) // 2
PANEL_Y = (720 - PANEL_H) // 2
TRANSPARENCY = 180  # More opaque for readability
INNER_OFFSET = 40

THUMB_W, THUMB_H = 450, 450 # Square Art Style
THUMB_X = PANEL_X + INNER_OFFSET
THUMB_Y = PANEL_Y + (PANEL_H - THUMB_H) // 2

# Text Area Calculation
TEXT_AREA_X = THUMB_X + THUMB_W + 40
TEXT_AREA_W = (PANEL_X + PANEL_W) - TEXT_AREA_X - INNER_OFFSET

TITLE_Y = THUMB_Y + 40
META_Y = TITLE_Y + 120
BAR_Y = META_Y + 100

BAR_TOTAL_LEN = TEXT_AREA_W - 20
BAR_RED_LEN = int(BAR_TOTAL_LEN * 0.6) # 60% Played simulation
ICONS_Y = BAR_Y + 60

# =============================================

def fix_ar(text):
    """دالة سحرية لإصلاح الحروف العربية المقطعة والمشقلبة"""
    if not text: return ""
    if arabic_reshaper and get_display:
        try:
            # 1. إعادة تشكيل الحروف (عشان تشبك في بعض)
            reshaped_text = arabic_reshaper.reshape(text)
            # 2. قلب الاتجاه (عشان تبقى من اليمين للشمال)
            bidi_text = get_display(reshaped_text)
            return bidi_text
        except:
            return text
    return text

def truncate(text, font, max_width):
    """قص النص بذكاء ليتناسب مع العرض"""
    if font.getlength(text) <= max_width:
        return text
    for i in range(len(text), 0, -1):
        if font.getlength(text[:i] + "...") <= max_width:
            return text[:i] + "..."
    return ""

async def get_thumb(videoid: str) -> str:
    if not os.path.isdir(CACHE_DIR):
        os.makedirs(CACHE_DIR)

    cache_path = os.path.join(CACHE_DIR, f"{videoid}_v2026.png")
    if os.path.exists(cache_path):
        return cache_path

    try:
        search = VideosSearch(videoid, limit=1)
        results_data = await search.next()
        result_items = results_data.get("result", [])
        
        if not result_items:
            # Try searching by URL if ID fails
            search = VideosSearch(f"https://www.youtube.com/watch?v={videoid}", limit=1)
            results_data = await search.next()
            result_items = results_data.get("result", [])

        if not result_items:
            raise ValueError("No results found.")
            
        data = result_items[0]
        title = data.get("title", "Unknown Track")
        thumbnail = data.get("thumbnails", [{}])[0].get("url", YOUTUBE_IMG_URL).split("?")[0]
        duration = data.get("duration") or "Live"
        views = data.get("viewCount", {}).get("short", "N/A Views")
        channel = data.get("channel", {}).get("name", "Unknown Artist")

    except Exception as e:
        print(f"Thumbnail Metadata Error: {e}")
        title, thumbnail, duration, views, channel = "Unknown Track", YOUTUBE_IMG_URL, "00:00", "N/A", "Unknown"

    # Download Thumbnail
    thumb_path = os.path.join(CACHE_DIR, f"temp_{videoid}.png")
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(thumbnail) as resp:
                if resp.status == 200:
                    async with aiofiles.open(thumb_path, "wb") as f:
                        await f.write(await resp.read())
                else:
                    return YOUTUBE_IMG_URL
    except:
        return YOUTUBE_IMG_URL

    try:
        # 1. Background (Blurry & Dark)
        base = Image.open(thumb_path).convert("RGBA")
        base = base.resize((1280, 720), Image.Resampling.LANCZOS)
        
        # Darken Background
        enhancer = ImageEnhance.Brightness(base)
        base = enhancer.enhance(0.4) # Darker
        base = base.filter(ImageFilter.GaussianBlur(20)) # Blurry

        # 2. Glass Panel
        # Create a new image for the glass panel
        glass = Image.new("RGBA", (PANEL_W, PANEL_H), (20, 20, 20, 180)) # Semi-transparent Dark Grey
        
        # Draw Panel with Rounded Corners
        mask = Image.new("L", (PANEL_W, PANEL_H), 0)
        ImageDraw.Draw(mask).rounded_rectangle((0, 0, PANEL_W, PANEL_H), radius=40, fill=255)
        
        # Composite Glass on Base
        base.paste(glass, (PANEL_X, PANEL_Y), mask)
        
        # Add Border to Glass
        draw = ImageDraw.Draw(base)
        draw.rounded_rectangle(
            (PANEL_X, PANEL_Y, PANEL_X + PANEL_W, PANEL_Y + PANEL_H),
            radius=40,
            outline=(255, 255, 255, 50), # Subtle white border
            width=2
        )

        # 3. Album Art (Square)
        art = Image.open(thumb_path).convert("RGBA")
        art = art.resize((THUMB_W, THUMB_H), Image.Resampling.LANCZOS)
        
        # Rounded Corners for Art
        art_mask = Image.new("L", (THUMB_W, THUMB_H), 0)
        ImageDraw.Draw(art_mask).rounded_rectangle((0, 0, THUMB_W, THUMB_H), radius=30, fill=255)
        
        base.paste(art, (THUMB_X, THUMB_Y), art_mask)

        # 4. Text & Details
        # Load Fonts (Fallback to default if not found)
        try:
            # Bold for Title
            font_title = ImageFont.truetype("AnnieXMedia/assets/font.ttf", 55)
            # Regular for Metadata
            font_meta = ImageFont.truetype("AnnieXMedia/assets/font2.ttf", 35)
            # Small for Durations
            font_small = ImageFont.truetype("AnnieXMedia/assets/font2.ttf", 25)
        except:
            font_title = font_meta = font_small = ImageFont.load_default()

        # Fix Arabic
        safe_title = fix_ar(truncate(title, font_title, TEXT_AREA_W))
        safe_channel = fix_ar(truncate(f"By: {channel}", font_meta, TEXT_AREA_W))
        safe_views = fix_ar(f"Views: {views}")

        # Draw Title
        draw.text((TEXT_AREA_X, TITLE_Y), safe_title, fill="white", font=font_title, anchor="lm")
        
        # Draw Channel & Views
        draw.text((TEXT_AREA_X, META_Y), safe_channel, fill="#AAAAAA", font=font_meta, anchor="lm")
        draw.text((TEXT_AREA_X, META_Y + 50), safe_views, fill="#AAAAAA", font=font_meta, anchor="lm")

        # 5. Progress Bar
        bar_start_x = TEXT_AREA_X
        bar_end_x = TEXT_AREA_X + BAR_TOTAL_LEN
        bar_y = BAR_Y

        # Grey Background Line
        draw.line([(bar_start_x, bar_y), (bar_end_x, bar_y)], fill="#444444", width=8, joint="curve")
        # Red Progress Line
        draw.line([(bar_start_x, bar_y), (bar_start_x + BAR_RED_LEN, bar_y)], fill="#FF0000", width=8, joint="curve")
        # Dot at end of red line
        draw.ellipse(
            (bar_start_x + BAR_RED_LEN - 10, bar_y - 10, bar_start_x + BAR_RED_LEN + 10, bar_y + 10),
            fill="white"
        )

        # Timestamps
        draw.text((bar_start_x, bar_y + 25), "00:00", fill="white", font=font_small)
        draw.text((bar_end_x, bar_y + 25), duration, fill="white", font=font_small, anchor="ra")

        # 6. Icons (Play/Pause/Skip) - Simulated with Text or Circles if image missing
        # Centralizing icons under the bar
        center_icons_x = TEXT_AREA_X + (TEXT_AREA_W // 2)
        
        # Play Button (Circle)
        draw.ellipse((center_icons_x - 35, ICONS_Y - 35, center_icons_x + 35, ICONS_Y + 35), fill="white")
        # Play Triangle (Black)
        draw.polygon([
            (center_icons_x - 10, ICONS_Y - 15),
            (center_icons_x - 10, ICONS_Y + 15),
            (center_icons_x + 15, ICONS_Y)
        ], fill="black")

        # Previous/Next (Lines)
        # Prev
        draw.polygon([(center_icons_x - 80, ICONS_Y), (center_icons_x - 60, ICONS_Y - 15), (center_icons_x - 60, ICONS_Y + 15)], fill="white")
        draw.rectangle((center_icons_x - 85, ICONS_Y - 15, center_icons_x - 80, ICONS_Y + 15), fill="white")
        
        # Next
        draw.polygon([(center_icons_x + 80, ICONS_Y), (center_icons_x + 60, ICONS_Y - 15), (center_icons_x + 60, ICONS_Y + 15)], fill="white")
        draw.rectangle((center_icons_x + 80, ICONS_Y - 15, center_icons_x + 85, ICONS_Y + 15), fill="white")

        # 7. Final Polish & Save
        base.save(cache_path)
        return cache_path

    except Exception as e:
        print(f"Thumbnail Generation Failed: {e}")
        return YOUTUBE_IMG_URL
    finally:
        if os.path.exists(thumb_path):
            try: os.remove(thumb_path)
            except: pass
