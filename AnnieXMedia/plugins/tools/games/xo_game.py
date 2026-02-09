# Authored By Certified Coders 2026
# Module: XO Game Advanced System (Name Caching Fix + Alpha-Beta AI)

import asyncio
import ctypes
import json
import os
import random
from pyrogram import filters, Client
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, Message
from pyrogram.errors import MessageNotModified, FloodWait

from AnnieXMedia import app
import config

# ─── C++ Engine Link ───
ENGINE_PATH = "./xo_engine.so"
xo_lib = None

if os.path.exists(ENGINE_PATH):
    try:
        xo_lib = ctypes.CDLL(ENGINE_PATH)
        xo_lib.check_winner_engine.argtypes = [ctypes.c_char_p]
        xo_lib.check_winner_engine.restype = ctypes.c_char
        xo_lib.get_hard_move.argtypes = [ctypes.c_char_p]
        xo_lib.get_hard_move.restype = ctypes.c_int
        xo_lib.get_medium_move.argtypes = [ctypes.c_char_p]
        xo_lib.get_medium_move.restype = ctypes.c_int
        xo_lib.get_easy_move.argtypes = [ctypes.c_char_p]
        xo_lib.get_easy_move.restype = ctypes.c_int
    except Exception as e:
        print(f"XO Engine Warning: {e}")

# ─── Settings ───

GAME_IMAGE = "https://files.catbox.moe/gy85j3.jpg"
POINTS_FILE = "xo_points.json"

SYM_X = "❌"
SYM_O = "⭕"
SYM_E = "◻️"

ENGINE_MAP = {SYM_X: b'X', SYM_O: b'O', SYM_E: b'-'}

active_games = {}
waiting_for_input = {}
game_lock = asyncio.Lock()

# ─── Points System (Smart Name Caching) ───

def load_data():
    if not os.path.exists(POINTS_FILE): return {}
    try:
        with open(POINTS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            # Fix old format if exists (migration)
            if data and not isinstance(list(data.values())[0], dict):
                return {k: {"points": v, "name": "Unknown"} for k, v in data.items()}
            return data
    except: return {}

def save_data(data):
    with open(POINTS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

def update_user(user_id, name, points_add=0):
    """تحديث بيانات المستخدم (الاسم والنقاط)"""
    data = load_data()
    uid = str(user_id)
    if uid not in data:
        data[uid] = {"points": 0, "name": name}
    
    data[uid]["points"] += points_add
    data[uid]["name"] = name  # تحديث الاسم دائماً
    save_data(data)
    return data[uid]["points"]

def get_user_points(user_id):
    data = load_data()
    return data.get(str(user_id), {}).get("points", 0)

def get_leaderboard():
    data = load_data()
    # Sort by points
    sorted_users = sorted(data.items(), key=lambda x: x[1]['points'], reverse=True)[:5]
    return sorted_users

# ─── Helpers ───

def get_engine_board(py_board):
    return b"".join([ENGINE_MAP[c] for c in py_board])

def check_winner_py(board):
    wins = [[0,1,2],[3,4,5],[6,7,8],[0,3,6],[1,4,7],[2,5,8],[0,4,8],[2,4,6]]
    for w in wins:
        if board[w[0]] == board[w[1]] == board[w[2]] and board[w[0]] != SYM_E:
            return board[w[0]]
    if SYM_E not in board: return "Draw"
    return None

def build_keyboard(board, game_id):
    buttons = []
    row = []
    for i, cell in enumerate(board):
        row.append(InlineKeyboardButton(cell, callback_data=f"xo_m_{game_id}_{i}"))
        if len(row) == 3:
            buttons.append(row)
            row = []
    return InlineKeyboardMarkup(buttons)

def format_name(user_id, name):
    return f"[{name}](tg://user?id={user_id})"

# ─── Start Command ───

@app.on_message(filters.command(["xo", "اكس او", "لعبة xo"], prefixes=["", "/", "!"]))
async def start_xo_command(client, message):
    if hasattr(config, "XO_ENABLED") and not config.XO_ENABLED:
        return await message.reply_text("اللعبة معطلة حالياً.")

    # تسجيل المستخدم فوراً لحل مشكلة Unknown مستقبلاً
    uid = message.from_user.id
    name = message.from_user.first_name
    update_user(uid, name, 0) 

    pts = get_user_points(uid)
    text = (
        f"**مرحباً بك في لعبة إكس أو**\n"
        f"**نقاطك:** `{pts}`\n"
        f"**المعرف:** `{message.id}`"
    )
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("Play vs AI", callback_data=f"xo_pre_ai_{uid}")],
        [InlineKeyboardButton("Play vs Friend", callback_data=f"xo_pre_pvp_{uid}")],
        [InlineKeyboardButton("Leaderboard", callback_data=f"xo_top_{uid}")]
    ])
    
    await message.reply_photo(GAME_IMAGE, caption=text, reply_markup=keyboard)

# ─── Menu Handler ───

@app.on_callback_query(filters.regex(r"^xo_(pre_ai|sel_ai|pre_pvp|make_open|req|top|join|cancel)_"))
async def xo_menu_handler(client, cb: CallbackQuery):
    data_parts = cb.data.split("_")
    action = data_parts[1]
    user = cb.from_user
    game_key = f"{cb.message.chat.id}_{cb.message.id}"

    # 1. Join Check (First priority)
    if action == "join":
        owner_id = int(data_parts[-1])
        
        if user.id == owner_id:
            return await cb.answer("لا يمكنك اللعب ضد نفسك!", show_alert=True)
        
        try:
            owner = await client.get_users(owner_id)
            p1_name = owner.first_name
        except: p1_name = "Player 1"

        # تسجيل اللاعب الثاني لحل مشكلة Unknown
        update_user(user.id, user.first_name, 0)

        async with game_lock:
            active_games[game_key] = {
                "board": [SYM_E] * 9,
                "turn": owner_id,
                "p1": owner_id,
                "p2": user.id,
                "p1_name": p1_name,
                "p2_name": user.first_name,
                "mode": "pvp"
            }
        await update_game_ui(client, cb.message, game_key)
        return

    # Determine Owner
    if action == "sel": owner_id = int(data_parts[4])
    else: owner_id = int(data_parts[-1])

    # Ownership Check
    if user.id != owner_id:
        return await cb.answer("هذه اللعبة ليست لك.", show_alert=True)

    # Leaderboard (Fixed Unknown Issue)
    if action == "top":
        top = get_leaderboard()
        txt = "**قائمة أفضل اللاعبين:**\n\n"
        for i, (uid, data) in enumerate(top, 1):
            n = data.get("name", "Unknown")
            p = data.get("points", 0)
            txt += f"{i}. {n} : `{p}` نقطة\n"
        
        await cb.edit_message_caption(txt, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Back", callback_data=f"xo_main_{owner_id}")]]))

    # Difficulty Select
    elif action == "pre" and "ai" in cb.data:
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("Easy", callback_data=f"xo_sel_ai_Easy_{owner_id}")],
            [InlineKeyboardButton("Medium", callback_data=f"xo_sel_ai_Medium_{owner_id}")],
            [InlineKeyboardButton("Hard", callback_data=f"xo_sel_ai_Hard_{owner_id}")],
            [InlineKeyboardButton("Back", callback_data=f"xo_main_{owner_id}")]
        ])
        await cb.edit_message_caption("**اختر مستوى الصعوبة:**", reply_markup=kb)

    # PVP Select
    elif action == "pre" and "pvp" in cb.data:
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("Open Lobby", callback_data=f"xo_make_open_{owner_id}")],
            [InlineKeyboardButton("Challenge ID", callback_data=f"xo_req_{owner_id}")],
            [InlineKeyboardButton("Back", callback_data=f"xo_main_{owner_id}")]
        ])
        await cb.edit_message_caption("**اختر طريقة اللعب:**", reply_markup=kb)

    # Open Lobby
    elif action == "make":
        text = f"**تم إنشاء اللعبة بواسطة {user.first_name}**\n**بانتظار الخصم...**"
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("Join Match", callback_data=f"xo_join_{owner_id}")],
            [InlineKeyboardButton("Cancel", callback_data=f"xo_main_{owner_id}")]
        ])
        await cb.edit_message_caption(text, reply_markup=kb)

    # Start AI
    elif action == "sel":
        diff = data_parts[3]
        async with game_lock:
            active_games[game_key] = {
                "board": [SYM_E] * 9,
                "turn": owner_id,
                "p1": owner_id,
                "p2": "AI",
                "p1_name": user.first_name,
                "p2_name": f"Bot ({diff})",
                "mode": "ai",
                "diff": diff
            }
        await update_game_ui(client, cb.message, game_key)

    # Request ID
    elif action == "req":
        waiting_for_input[user.id] = {"chat_id": cb.message.chat.id, "msg_id": cb.message.id}
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("Cancel", callback_data=f"xo_cancel_{owner_id}")]])
        await cb.edit_message_caption("**أرسل الآن يوزر أو آيدي الشخص الذي تريد تحديه:**", reply_markup=kb)

    # Cancel
    elif action == "cancel":
        waiting_for_input.pop(user.id, None)
        await back_to_main(cb, owner_id)

@app.on_callback_query(filters.regex(r"^xo_main_"))
async def back_to_main_handler(client, cb):
    await back_to_main(cb, cb.from_user.id)

async def back_to_main(cb, owner_id):
    pts = get_user_points(owner_id)
    text = f"**القائمة الرئيسية**\n**نقاطك:** `{pts}`"
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("Play vs AI", callback_data=f"xo_pre_ai_{owner_id}")],
        [InlineKeyboardButton("Play vs Friend", callback_data=f"xo_pre_pvp_{owner_id}")],
        [InlineKeyboardButton("Leaderboard", callback_data=f"xo_top_{owner_id}")]
    ])
    await cb.edit_message_caption(text, reply_markup=kb)

# ─── Challenge Handler ───

@app.on_message(filters.text & ~filters.command("xo") & filters.group)
async def handle_challenge_text(client, message):
    uid = message.from_user.id
    if uid in waiting_for_input:
        if message.chat.id != waiting_for_input[uid]["chat_id"]: return
        
        data = waiting_for_input.pop(uid)
        orig_msg_id = data["msg_id"]
        
        try:
            target = await client.get_users(message.text)
        except:
            return await message.reply_text("لم يتم العثور على اللاعب.")

        if target.id == uid or target.is_bot:
            return await message.reply_text("لا يمكنك تحدي نفسك أو البوتات.")

        # Update both users in DB
        update_user(uid, message.from_user.first_name, 0)
        update_user(target.id, target.first_name, 0)

        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("Accept", callback_data=f"xo_acc_{uid}_{target.id}_{orig_msg_id}")],
            [InlineKeyboardButton("Reject", callback_data=f"xo_dny_{uid}_{target.id}_{orig_msg_id}")]
        ])
        await message.reply_text(f"**تحدي جديد!**\n**{message.from_user.mention}** يتحدى **{target.mention}**", reply_markup=kb)

@app.on_callback_query(filters.regex(r"^xo_(acc|dny)_"))
async def challenge_resp(client, cb):
    parts = cb.data.split("_")
    action, p1_id, p2_id, orig_id = parts[1], int(parts[2]), int(parts[3]), int(parts[4])

    if cb.from_user.id != p2_id:
        return await cb.answer("هذا التحدي ليس لك.", show_alert=True)

    if action == "dny":
        await cb.message.edit_text(f"**تم رفض التحدي من قبل {cb.from_user.mention}.**")
    else:
        game_key = f"{cb.message.chat.id}_{orig_id}"
        try:
            p1_name = (await client.get_users(p1_id)).first_name
        except: p1_name = "Player 1"
        
        async with game_lock:
            active_games[game_key] = {
                "board": [SYM_E] * 9,
                "turn": p1_id,
                "p1": p1_id,
                "p2": p2_id,
                "p1_name": p1_name,
                "p2_name": cb.from_user.first_name,
                "mode": "pvp"
            }
        await cb.message.delete()
        orig_msg = await client.get_messages(cb.message.chat.id, orig_id)
        await update_game_ui(client, orig_msg, game_key)

# ─── Gameplay Handler ───

@app.on_callback_query(filters.regex(r"^xo_m_"))
async def gameplay_handler(client, cb):
    parts = cb.data.split("_")
    try:
        pos = int(parts[-1])
        game_key = f"{parts[2]}_{parts[3]}"
    except: return await cb.answer("Error")

    game = active_games.get(game_key)
    if not game: return await cb.answer("الجلسة منتهية.", show_alert=True)

    uid = cb.from_user.id
    
    if uid != game["turn"]:
        if uid in [game["p1"], game["p2"]]: return await cb.answer("ليس دورك!", show_alert=True)
        return await cb.answer("لست في هذه اللعبة.", show_alert=True)

    if game["board"][pos] != SYM_E: return await cb.answer("خانة مشغولة.", show_alert=True)

    async with game_lock:
        sym = SYM_X if uid == game["p1"] else SYM_O
        game["board"][pos] = sym
        
        winner = check_game_winner(game["board"])
        if winner:
            await handle_win(client, cb.message, game, winner, game_key)
            return

        if game["mode"] == "pvp":
            game["turn"] = game["p2"] if uid == game["p1"] else game["p1"]
            await update_game_ui(client, cb.message, game_key)
        
        elif game["mode"] == "ai":
            if xo_lib:
                c_board = get_engine_board(game["board"])
                diff = game["diff"]
                
                if hasattr(config, "XO_CHEAT") and config.XO_CHEAT:
                    move = xo_lib.get_easy_move(c_board)
                else:
                    if diff == "Hard": move = xo_lib.get_hard_move(c_board)
                    elif diff == "Medium": move = xo_lib.get_medium_move(c_board)
                    else: move = xo_lib.get_easy_move(c_board)
            else:
                empties = [i for i, x in enumerate(game["board"]) if x == SYM_E]
                move = random.choice(empties) if empties else -1

            if move != -1:
                game["board"][move] = SYM_O
                winner_ai = check_game_winner(game["board"])
                if winner_ai:
                    await handle_win(client, cb.message, game, winner_ai, game_key)
                    return
            
            game["turn"] = game["p1"]
            await update_game_ui(client, cb.message, game_key)

# ─── Core Functions ───

def check_game_winner(board):
    if xo_lib:
        res = xo_lib.check_winner_engine(get_engine_board(board))
        if res == b'X': return SYM_X
        if res == b'O': return SYM_O
        if res == b'D': return "Draw"
        return None
    return check_winner_py(board)

async def update_game_ui(client, message, key):
    game = active_games[key]
    turn_n = game['p1_name'] if game['turn'] == game['p1'] else game['p2_name']
    sym = SYM_X if game['turn'] == game['p1'] else SYM_O
    
    p1 = format_name(game['p1'], game['p1_name'])
    p2 = game['p2_name'] if game['p2'] == "AI" else format_name(game['p2'], game['p2_name'])
    
    txt = (
        f"**المباراة جارية:**\n"
        f"**{p1} ({SYM_X})**\n"
        f"**{p2} ({SYM_O})**\n\n"
        f"**الدور الحالي:** {turn_n} ({sym})"
    )
    try: await message.edit_caption(txt, reply_markup=build_keyboard(game["board"], key))
    except: pass

async def handle_win(client, message, game, winner, key):
    p1_name = game['p1_name']
    p2_name = game['p2_name']
    p1_link = format_name(game['p1'], p1_name)
    p2_link = p2_name if game['p2'] == "AI" else format_name(game['p2'], p2_name)
    
    res_txt = ""
    if winner == "Draw":
        res_txt = "**انتهت المباراة بالتعادل!**\n(+5 نقاط لكل لاعب)"
        # Update Points & Names
        update_user(game['p1'], p1_name, 5)
        if game['mode'] == 'pvp':
            update_user(game['p2'], p2_name, 5)
            
    else:
        is_p1 = (winner == SYM_X)
        win_id = game['p1'] if is_p1 else game['p2']
        win_name = p1_name if is_p1 else p2_name
        
        # Display Name
        if not is_p1 and game['mode'] == 'ai': display_win = "Bot"
        else: display_win = format_name(win_id, win_name)
        
        res_txt = f"**الفائز هو: {display_win} !**"
        
        if game['mode'] == 'pvp':
            update_user(win_id, win_name, 20)
            res_txt += "\n(+20 نقطة)"
        elif game['mode'] == 'ai':
            if is_p1:
                pts = {"Easy": 5, "Medium": 10, "Hard": 20}.get(game['diff'], 5)
                update_user(win_id, win_name, pts)
                res_txt += f"\n(+{pts} نقطة)"
            else:
                res_txt += "\n(حظ أوفر المرة القادمة)"

    final = (
        f"**نتيجة المباراة**\n"
        f"**{p1_link} ({SYM_X})**\n"
        f"**{p2_link} ({SYM_O})**\n\n"
        f"{res_txt}"
    )
    
    dead_kb = []
    row = []
    for c in game["board"]:
        row.append(InlineKeyboardButton(c, callback_data="none"))
        if len(row) == 3: dead_kb.append(row); row = []
    dead_kb.append([InlineKeyboardButton("Back to Menu", callback_data=f"xo_main_{game['p1']}")])
    
    try: await message.edit_caption(final, reply_markup=InlineKeyboardMarkup(dead_kb))
    except: pass
    
    if key in active_games: del active_games[key]
