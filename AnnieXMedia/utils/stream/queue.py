# Authored By Certified Coders © 2026
# System: Queue Manager (Database Handler)
# Updated: Compatible with PyTgCalls v3.0 Data Structure

import asyncio
from typing import Union

from AnnieXMedia.misc import db
from AnnieXMedia.utils.formatters import check_duration, seconds_to_min
from config import autoclean, time_to_seconds

async def put_queue(
    chat_id,
    original_chat_id,
    file,
    title,
    duration,
    user,
    vidid,
    user_id,
    stream,
    forceplay: Union[bool, str] = None,
):
    """
    Standard Queue Insert for YouTube, Telegram Files, etc.
    """
    title = title.title()
    try:
        # Calculate duration in seconds for Seek logic later
        duration_in_seconds = time_to_seconds(duration) - 3
    except:
        duration_in_seconds = 0
        
    put = {
        "title": title,
        "dur": duration,
        "streamtype": stream, # Critical for Call.py (video vs audio)
        "by": user,
        "user_id": user_id,
        "chat_id": original_chat_id,
        "file": file, # The path Call.py will read
        "vidid": vidid,
        "seconds": duration_in_seconds,
        "played": 0,
    }
    
    if forceplay:
        check = db.get(chat_id)
        if check:
            check.insert(0, put)
        else:
            db[chat_id] = []
            db[chat_id].append(put)
    else:
        # Standard append
        db.get(chat_id, []).append(put)
        
    # Add to autoclean list to remove file later
    if file not in autoclean:
        autoclean.append(file)


async def put_queue_index(
    chat_id,
    original_chat_id,
    file,
    title,
    duration,
    user,
    vidid,
    stream,
    forceplay: Union[bool, str] = None,
):
    """
    Queue Insert for M3U8 / Live Streams / Index Links
    """
    # Specific check for known IP streams or direct URLs
    if "20.212.146.162" in vidid:
        try:
            dur = await asyncio.get_event_loop().run_in_executor(
                None, check_duration, vidid
            )
            duration = seconds_to_min(dur)
        except:
            duration = "ᴜʀʟ sᴛʀᴇᴀᴍ"
            dur = 0
    else:
        dur = 0
        
    put = {
        "title": title,
        "dur": duration,
        "streamtype": stream,
        "by": user,
        "chat_id": original_chat_id,
        "file": file,
        "vidid": vidid,
        "seconds": dur,
        "played": 0,
    }
    
    if forceplay:
        check = db.get(chat_id)
        if check:
            check.insert(0, put)
        else:
            db[chat_id] = []
            db[chat_id].append(put)
    else:
        # Create list if not exists, then append
        if chat_id not in db:
            db[chat_id] = []
        db[chat_id].append(put)
