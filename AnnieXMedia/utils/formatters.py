# Authored By Certified Coders © 2026
# System: Advanced Data Formatters & Time Utils
# Optimized for Python 3.13 | Fixed 'Live' Duration Crash & 'Tuple' Error

import shutil
import math
import asyncio
import subprocess
# 🔥 تم إضافة Tuple هنا
from typing import Union, Optional, Tuple

# ==========================
# 🕒 Time & Duration Utils
# ==========================

def get_readable_time(seconds: int) -> str:
    """Converts seconds to a human-readable string (Day, Hour, Min, Sec)."""
    if not seconds or seconds < 0:
        return "0s"
        
    count = 0
    ping_time = ""
    time_list = []
    time_suffix_list = ["s", "m", "h", "days"]

    while count < 4:
        count += 1
        remainder, result = divmod(seconds, 60) if count < 3 else divmod(seconds, 24)
        if seconds == 0 and remainder == 0:
            break
        time_list.append(int(result))
        seconds = int(remainder)

    for i in range(len(time_list)):
        time_list[i] = str(time_list[i]) + time_suffix_list[i]

    if len(time_list) == 4:
        ping_time += time_list.pop() + ", "

    time_list.reverse()
    ping_time += ":".join(time_list)
    return ping_time


def time_to_seconds(time: Union[str, int]) -> int:
    """
    Safely converts timestamp string (HH:MM:SS) to total seconds.
    🔥 FIX: Handles 'Live' or invalid strings gracefully to prevent crashes.
    """
    stringt = str(time).strip().lower()
    
    # 🛡️ Crash Protection
    if stringt in ["live", "stream", "none", "nan", "unknown"]:
        return 0
        
    try:
        # Check if already int
        if stringt.isdigit():
            return int(stringt)
            
        parts = stringt.split(":")
        # Reverse to process seconds, then minutes, then hours
        return sum(int(float(x)) * 60**i for i, x in enumerate(reversed(parts)))
    except Exception:
        return 0


def seconds_to_min(seconds: Union[int, float, None]) -> str:
    """Converts seconds to MM:SS or HH:MM:SS format."""
    if seconds is None:
        return "00:00"
        
    try:
        seconds = int(seconds)
    except:
        return "00:00"

    d, remainder = divmod(seconds, 86400)
    h, remainder = divmod(remainder, 3600)
    m, s = divmod(remainder, 60)

    if d > 0:
        return f"{d:02d}:{h:02d}:{m:02d}:{s:02d}"
    elif h > 0:
        return f"{h:02d}:{m:02d}:{s:02d}"
    
    return f"{m:02d}:{s:02d}"


def speed_converter(seconds: Union[int, float], speed: Union[int, float]) -> Tuple[str, int]:
    """
    Calculates new duration based on playback speed.
    Optimized: Uses math logic instead of hardcoded strings.
    """
    try:
        speed = float(speed)
        seconds = int(seconds)
    except:
        return "-", seconds

    # Calculate new duration (Physics: Time = Distance / Speed)
    if speed > 0:
        new_seconds = int(seconds / speed)
    else:
        new_seconds = seconds

    return seconds_to_min(new_seconds), new_seconds


# ==========================
# 💾 Size & File Utils
# ==========================

def convert_bytes(size: Union[int, float]) -> str:
    """Humanizes file size (B, KiB, MiB, GiB, TiB)."""
    if not size:
        return "0 B"
        
    power = 1024
    t_n = 0
    power_dict = {0: " ", 1: "Ki", 2: "Mi", 3: "Gi", 4: "Ti"}
    
    while size > power:
        size /= power
        t_n += 1
        
    return "{:.2f} {}B".format(size, power_dict.get(t_n, ""))


def check_duration(file_path: str) -> float:
    """Extracts duration from a media file using ffprobe."""
    if not os.path.exists(file_path):
        return 0.0

    try:
        # Using shutil to find executable ensures cross-platform compatibility
        ffprobe_cmd = shutil.which("ffprobe")
        if not ffprobe_cmd:
            return 0.0

        command = [
            ffprobe_cmd,
            "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            file_path,
        ]

        # Run safely
        output = subprocess.check_output(command, timeout=5).decode().strip()
        return float(output)
    except Exception:
        return 0.0


# ==========================
# 🔠 ID Conversion (Alpha)
# ==========================

async def int_to_alpha(user_id: int) -> str:
    alphabet = ["a", "b", "c", "d", "e", "f", "g", "h", "i", "j"]
    return "".join(alphabet[int(digit)] for digit in str(user_id))


async def alpha_to_int(user_id_alphabet: str) -> int:
    alphabet = ["a", "b", "c", "d", "e", "f", "g", "h", "i", "j"]
    user_id = "".join(str(alphabet.index(char)) for char in user_id_alphabet)
    return int(user_id)


# ==========================
# 📼 Supported Formats
# ==========================
# Optimized as a Set for O(1) Lookup Speed
formats = {
    "webm", "mkv", "flv", "vob", "ogv", "ogg", "rrc", "gifv",
    "mng", "mov", "avi", "qt", "wmv", "yuv", "rm", "asf",
    "amv", "mp4", "m4p", "m4v", "mpg", "mp2", "mpeg", "mpe",
    "mpv", "m4v", "svi", "3gp", "3g2", "mxf", "roq", "nsv",
    "f4v", "f4p", "f4a", "f4b", "mp3", "aac", "opus", "flac"
}
