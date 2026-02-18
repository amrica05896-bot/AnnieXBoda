
import shutil
import math
import asyncio
import subprocess
import re
import json
from typing import Union, Optional, Tuple

def get_readable_time(seconds: int) -> str:
    if not seconds or seconds < 0:
        return "0s"
        
    count = 0
    ping_time = ""
    time_list = []
    time_suffix_list = ["s", "ᴍ", "ʜ", "ᴅᴀʏs"]

    while count < 4:
        count += 1
        if count < 3:
            remainder, result = divmod(seconds, 60)
        else:
            remainder, result = divmod(seconds, 24)
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


def convert_bytes(size: Union[int, float]) -> str:
    if not size:
        return "0 B"
    power = 1024
    t_n = 0
    power_dict = {0: " ", 1: "Ki", 2: "Mi", 3: "Gi", 4: "Ti"}
    while size > power:
        size /= power
        t_n += 1
    return "{:.2f} {}B".format(size, power_dict.get(t_n, ""))


async def int_to_alpha(user_id: int) -> str:
    alphabet = ["a", "b", "c", "d", "e", "f", "g", "h", "i", "j"]
    return "".join(alphabet[int(digit)] for digit in str(user_id))


async def alpha_to_int(user_id_alphabet: str) -> int:
    alphabet = ["a", "b", "c", "d", "e", "f", "g", "h", "i", "j"]
    user_id = "".join(str(alphabet.index(char)) for char in user_id_alphabet)
    return int(user_id)


def time_to_seconds(time: Union[str, int]) -> int:
    stringt = str(time).strip().lower()
    
    if stringt in ["live", "stream", "none", "nan", "unknown", "لايف", "مباشر"]:
        return 0
    
    if ":" in stringt:
        try:
            parts = stringt.split(":")
            return sum(int(float(x)) * 60**i for i, x in enumerate(reversed(parts)))
        except:
            return 0

    try:
        nums = re.findall(r'\d+', stringt)
        if not nums: return 0
        val = int(nums[0])
        
        if any(x in stringt for x in ["hour", "hr", "ساعة", "ساعات"]):
            return val * 3600
            
        if any(x in stringt for x in ["min", "mn", "دقيقة", "دقائق"]):
            return val * 60
            
        return val
    except:
        return 0


def seconds_to_min(seconds: Union[int, float, str, None]) -> str:
    if seconds is None:
        return "00:00"
    
    if isinstance(seconds, str):
        seconds = seconds.strip()
        if ":" in seconds:
            return seconds
        seconds = time_to_seconds(seconds)
        
    try:
        seconds = int(seconds)
    except:
        return "00:00"

    d, remainder = divmod(seconds, 86400)
    h, remainder = divmod(remainder, 3600)
    m, s = divmod(remainder, 60)

    if d > 0:
        return "{:02d}:{:02d}:{:02d}:{:02d}".format(d, h, m, s)
    elif h > 0:
        return "{:02d}:{:02d}:{:02d}".format(h, m, s)
    
    return "{:02d}:{:02d}".format(m, s)


def speed_converter(seconds: Union[int, float], speed: Union[int, float]) -> Tuple[str, int]:
    try:
        speed = float(speed)
        seconds = int(seconds)
    except:
        return "-", seconds

    if speed > 0:
        new_seconds = int(seconds / speed)
    else:
        new_seconds = seconds

    return seconds_to_min(new_seconds), new_seconds


def check_duration(file_path: str) -> float:
    if not os.path.exists(file_path):
        return 0.0

    try:
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

        output = subprocess.check_output(command, timeout=5).decode().strip()
        return float(output)
    except Exception:
        return 0.0


formats = {
    "webm", "mkv", "flv", "vob", "ogv", "ogg", "rrc", "gifv",
    "mng", "mov", "avi", "qt", "wmv", "yuv", "rm", "asf",
    "amv", "mp4", "m4p", "m4v", "mpg", "mp2", "mpeg", "mpe",
    "mpv", "m4v", "svi", "3gp", "3g2", "mxf", "roq", "nsv",
    "f4v", "f4p", "f4a", "f4b", "mp3", "aac", "opus", "flac"
}
