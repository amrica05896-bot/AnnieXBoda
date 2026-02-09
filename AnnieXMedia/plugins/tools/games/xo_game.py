# Authored By Certified Coders 2026
# Architecture: MVC (Model-View-Controller)
# Engine: Pure Python Optimized (Alpha-Beta Pruning)

import asyncio
import json
import os
import random
from dataclasses import dataclass, field
from typing import Dict, Optional, List, Tuple

from pyrogram import filters, Client
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, Message
from pyrogram.errors import MessageNotModified

from AnnieXMedia import app
import config

# ════════════════════ [ 1. CONFIGURATION ] ════════════════════

class Config:
    GAME_IMAGE = "https://files.catbox.moe/gy85j3.jpg"
    POINTS_FILE = "xo_points.json"
    
    # Symbols (Keyboard Only)
    SYM_X = "❌"
    SYM_O = "⭕"
    SYM_E = "◻️"

# ════════════════════ [ 2. LOGIC ENGINE (PURE PYTHON) ] ════════════════════

class AIEngine:
    WINS = [
        (0,1,2), (3,4,5), (6,7,8),
        (0,3,6), (1,4,7), (2,5,8),
        (0,4,8), (2,4,6)
    ]

    @staticmethod
    def check_status(board: List[str]) -> Optional[str]:
        for a, b, c in AIEngine.WINS:
            if board[a] == board[b] == board[c] and board[a] != Config.SYM_E:
                return board[a]
        if Config.SYM_E not in board:
            return "Draw"
        return None

    @staticmethod
    def minimax(board, depth, is_max, alpha, beta):
        res = AIEngine.check_status(board)
        if res == Config.SYM_O: return 100 - depth
        if res == Config.SYM_X: return depth - 100
        if res == "Draw": return 0

        if is_max:
            best = -1000
            for i in range(9):
                if board[i] == Config.SYM_E:
                    board[i] = Config.SYM_O
                    val = AIEngine.minimax(board, depth + 1, False, alpha, beta)
                    board[i] = Config.SYM_E
                    best = max(best, val)
                    alpha = max(alpha, best)
                    if beta <= alpha: break
            return best
        else:
            best = 1000
            for i in range(9):
                if board[i] == Config.SYM_E:
                    board[i] = Config.SYM_X
                    val = AIEngine.minimax(board, depth + 1, True, alpha, beta)
                    board[i] = Config.SYM_E
                    best = min(best, val)
                    beta = min(beta, best)
                    if beta <= alpha: break
            return best

    @staticmethod
    def get_best_move(board: List[str], diff: str) -> int:
        # 1. Cheat / Easy
        if (hasattr(config, "XO_CHEAT") and config.XO_CHEAT) or diff == "Easy":
            empties = [i for i, x in enumerate(board) if x == Config.SYM_E]
            return random.choice(empties) if empties else -1

        # 2. Medium (50% Hard)
        if diff == "Medium" and random.random() < 0.4:
            empties = [i for i, x in enumerate(board) if x == Config.SYM_E]
            return random.choice(empties) if empties else -1

        # 3. Hard (Unbeatable)
        if board[4] == Config.SYM_E: return 4 # Optimization
        
        best_val = -1000
        best_move = -1
        
        for i in range(9):
            if board[i] == Config.SYM_E:
                board[i] = Config.SYM_O
                move_val = AIEngine.minimax(board, 0, False, -1000, 1000)
                board[i] = Config.SYM_E
                
                if move_val > best_val:
                    best_val = move_val
                    best_move = i
                    
        return best_move

# ════════════════════ [ 3. DATA LAYER (STORAGE) ] ════════════════════

class DataManager:
    @staticmethod
    def _rw(data=None):
        if data is None: # Read Mode
            if not os.path.exists(Config.POINTS_FILE): return {}
            try:
                with open(Config.POINTS_FILE, "r", encoding="utf-8") as f: return json.load(f)
            except: return {}
        else: # Write Mode
            with open(Config.POINTS_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=4)

    @classmethod
    def update_player(cls, uid: int, name: str, points_add: int = 0) -> int:
        db = cls._rw()
        sid = str(uid)
        
        entry = db.get(sid, {"points": 0, "name": name})
        if isinstance(entry, int): entry = {"points": entry, "name": name}
        
        entry["name"] = name
        entry["points"] += points_add
        db[sid] = entry
        
        cls._rw(db)
        return entry["points"]

    @classmethod
    def get_points(cls, uid: int) -> int:
        db = cls._rw()
        val = db.get(str(uid), 0)
        return val["points"] if isinstance(val, dict) else val

    @classmethod
    def get_leaderboard(cls) -> List[Tuple[str, int]]:
        db = cls._rw()
        data = []
        for v in db.values():
            if isinstance(v, dict): data.append((v["name"], v["points"]))
            else: data.append(("Unknown", v))
        return sorted(data, key=lambda x: x[1], reverse=True)[:5]

# ════════════════════ [ 4. MODEL LAYER (GAME STATE) ] ════════════════════

@dataclass
class GameSession:
    board: List[str]
    turn: int
    p1: int
    p2: int
    p1_name: str
    p2_name: str
    mode: str
    diff: str = "Easy"

class GameManager:
    sessions: Dict[str, GameSession] = {}
    invites: Dict[int, dict] = {} 
    lock = asyncio.Lock()

    @classmethod
    async def create(cls, key: str, p1: int, n1: str, mode: str, p2: int = 0, n2: str = "AI", diff: str = "Easy"):
        async with cls.lock:
            cls.sessions[key] = GameSession(
                board=[Config.SYM_E] * 9,
                turn=p1,
                p1=p1, p1_name=n1,
                p2=p2, p2_name=n2,
                mode=mode, diff=diff
            )
        return cls.sessions[key]

    @classmethod
    def get(cls, key: str) -> Optional[GameSession]:
        return cls.sessions.get(key)

    @classmethod
    def delete(cls, key: str):
        if key in cls.sessions: del cls.sessions[key]

# ════════════════════ [ 5. UI LAYER (INTERFACE) ] ════════════════════

class UIFactory:
    @staticmethod
    def get_keyboard(board: List[str], game_key: str) -> InlineKeyboardMarkup:
        buttons = []
        row = []
        for i, cell in enumerate(board):
            row.append(InlineKeyboardButton(cell, callback_data=f"xo_m_{game_key}_{i}"))
            if len(row) == 3:
                buttons.append(row)
                row = []
        return InlineKeyboardMarkup(buttons)

    @staticmethod
    def format_name(uid: int, name: str) -> str:
        return f"[{name}](tg://user?id={uid})"

# ════════════════════ [ 6. CONTROLLER (HANDLERS) ] ════════════════════

@app.on_message(filters.command(["xo", "اكس او", "لعبة xo"], prefixes=["", "/", "!"]))
async def start_handler(client, message):
    if hasattr(config, "XO_ENABLED") and not config.XO_ENABLED:
        return await message.reply_text("اللعبة معطلة حالياً.")

    uid = message.from_user.id
    name = message.from_user.first_name
    DataManager.update_player(uid, name)
    pts = DataManager.get_points(uid)

    text = (
        f"**مرحباً بك في لعبة إكس أو**\n"
        f"**نقاطك:** `{pts}`\n"
        f"**المعرف:** `{message.id}`"
    )
    
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("Play vs AI", callback_data=f"xo_pre_ai_{uid}")],
        [InlineKeyboardButton("Play vs Friend", callback_data=f"xo_pre_pvp_{uid}")],
        [InlineKeyboardButton("Leaderboard", callback_data=f"xo_top_{uid}")]
    ])
    
    await message.reply_photo(Config.GAME_IMAGE, caption=text, reply_markup=kb)

@app.on_callback_query(filters.regex(r"^xo_"))
async def callback_router(client, cb: CallbackQuery):
    data = cb.data.split("_")
    action = data[1]
    uid = cb.from_user.id
    
    # --- Navigation ---
    if action == "main":
        if uid != int(data[2]): return await cb.answer("هذه اللعبة ليست لك.", show_alert=True)
        pts = DataManager.update_player(uid, cb.from_user.first_name)
        text = f"**مرحباً بك في لعبة إكس أو**\n**نقاطك:** `{pts}`\n**المعرف:** `{cb.message.id}`"
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("Play vs AI", callback_data=f"xo_pre_ai_{uid}")],
            [InlineKeyboardButton("Play vs Friend", callback_data=f"xo_pre_pvp_{uid}")],
            [InlineKeyboardButton("Leaderboard", callback_data=f"xo_top_{uid}")]
        ])
        await cb.edit_message_caption(text, reply_markup=kb)

    # --- Leaderboard ---
    elif action == "top":
        top = DataManager.get_leaderboard()
        txt = "**قائمة أفضل اللاعبين:**\n\n"
        for i, (n, p) in enumerate(top, 1): txt += f"{i}. {n} : `{p}` نقطة\n"
        await cb.edit_message_caption(txt, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Back", callback_data=f"xo_main_{uid}")]]))

    # --- Setup Phase ---
    elif action == "pre":
        owner = int(data[3])
        if uid != owner: return await cb.answer("هذه اللعبة ليست لك.", show_alert=True)
        
        mode = data[2]
        if mode == "ai":
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("Easy", callback_data=f"xo_sel_ai_Easy_{owner}")],
                [InlineKeyboardButton("Medium", callback_data=f"xo_sel_ai_Medium_{owner}")],
                [InlineKeyboardButton("Hard", callback_data=f"xo_sel_ai_Hard_{owner}")],
                [InlineKeyboardButton("Back", callback_data=f"xo_main_{owner}")]
            ])
            await cb.edit_message_caption("**اختر مستوى الصعوبة:**", reply_markup=kb)
        elif mode == "pvp":
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("Open Lobby", callback_data=f"xo_mk_pvp_{owner}")],
                [InlineKeyboardButton("Challenge ID", callback_data=f"xo_req_{owner}")],
                [InlineKeyboardButton("Back", callback_data=f"xo_main_{owner}")]
            ])
            await cb.edit_message_caption("**اختر طريقة اللعب:**", reply_markup=kb)

    # --- Game Initialization ---
    elif action == "sel": # AI Start
        diff, owner = data[3], int(data[4])
        key = f"{cb.message.chat.id}_{cb.message.id}"
        
        await GameManager.create(key, owner, cb.from_user.first_name, "ai", diff=diff, n2=f"Bot ({diff})")
        await update_game_interface(client, cb.message, key)

    elif action == "mk": # Open Lobby
        owner = int(data[3])
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("Join Match", callback_data=f"xo_join_{owner}")],
            [InlineKeyboardButton("Cancel", callback_data=f"xo_main_{owner}")]
        ])
        await cb.edit_message_caption(f"**تم إنشاء اللعبة بواسطة {cb.from_user.first_name}**\n**بانتظار الخصم...**", reply_markup=kb)

    elif action == "join": # Join Lobby
        owner = int(data[2])
        if uid == owner: return await cb.answer("لا يمكنك اللعب ضد نفسك!", show_alert=True)
        
        try: n1 = (await client.get_users(owner)).first_name
        except: n1 = "Player 1"
        
        key = f"{cb.message.chat.id}_{cb.message.id}"
        DataManager.update_player(uid, cb.from_user.first_name)
        
        await GameManager.create(key, owner, n1, "pvp", p2=uid, n2=cb.from_user.first_name)
        await update_game_interface(client, cb.message, key)

    elif action == "req": # Challenge Request
        GameManager.invites[uid] = {"cid": cb.message.chat.id, "mid": cb.message.id}
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("Cancel", callback_data=f"xo_main_{uid}")]])
        await cb.edit_message_caption("**أرسل الآن يوزر أو آيدي الشخص الذي تريد تحديه:**", reply_markup=kb)

    # --- Core Gameplay ---
    elif action == "m":
        key = f"{data[2]}_{data[3]}"
        pos = int(data[4])
        
        game = GameManager.get(key)
        if not game: return await cb.answer("انتهت صلاحية الجلسة.", show_alert=True)
        
        if uid != game.turn:
            if uid in [game.p1, game.p2]: return await cb.answer("ليس دورك!", show_alert=True)
            return await cb.answer("لست مشاركاً في هذه اللعبة.", show_alert=True)
            
        if game.board[pos] != Config.SYM_E: return await cb.answer("هذه الخانة مشغولة.", show_alert=True)

        async with GameManager.lock:
            # 1. Human Move
            sym = Config.SYM_X if uid == game.p1 else Config.SYM_O
            game.board[pos] = sym
            
            winner = AIEngine.check_status(game.board)
            if winner:
                await handle_game_end(client, cb.message, key, winner)
                return

            # 2. Logic Switch
            if game.mode == "pvp":
                game.turn = game.p2 if game.turn == game.p1 else game.p1
                await update_game_interface(client, cb.message, key)
            
            elif game.mode == "ai":
                ai_move = AIEngine.get_best_move(game.board, game.diff)
                if ai_move != -1:
                    game.board[ai_move] = Config.SYM_O
                    winner_ai = AIEngine.check_status(game.board)
                    if winner_ai:
                        await handle_game_end(client, cb.message, key, winner_ai)
                        return
                game.turn = game.p1
                await update_game_interface(client, cb.message, key)

# --- Challenge Listener ---
@app.on_message(filters.text & filters.group)
async def challenge_input_listener(client, message):
    uid = message.from_user.id
    if uid in GameManager.invites:
        ctx = GameManager.invites.pop(uid)
        if message.chat.id != ctx["cid"]: return
        
        try: target = await client.get_users(message.text)
        except: return await message.reply_text("لم يتم العثور على اللاعب.")
        
        if target.id == uid or target.is_bot: return await message.reply_text("لا يمكنك تحدي نفسك أو البوتات.")
        
        DataManager.update_player(uid, message.from_user.first_name)
        DataManager.update_player(target.id, target.first_name)
        
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("Accept", callback_data=f"xo_acc_{uid}_{target.id}_{ctx['mid']}")],
            [InlineKeyboardButton("Reject", callback_data=f"xo_dny_{uid}_{target.id}_{ctx['mid']}")]
        ])
        await message.reply_text(f"**تحدي جديد!**\n**{message.from_user.mention}** يتحدى **{target.mention}**", reply_markup=kb)

@app.on_callback_query(filters.regex(r"^xo_(acc|dny)"))
async def challenge_response(client, cb):
    data = cb.data.split("_")
    p1, p2, mid = int(data[2]), int(data[3]), int(data[4])
    
    if cb.from_user.id != p2: return await cb.answer("هذا التحدي ليس لك.", show_alert=True)
    if data[1] == "dny": return await cb.message.edit_text("**تم رفض التحدي.**")
    
    key = f"{cb.message.chat.id}_{mid}"
    try: p1n = (await client.get_users(p1)).first_name
    except: p1n = "Player 1"
    
    await cb.message.delete()
    await GameManager.create(key, p1, p1n, "pvp", p2=p2, n2=cb.from_user.first_name)
    
    try:
        orig = await client.get_messages(cb.message.chat.id, mid)
        await update_game_interface(client, orig, key)
    except: await cb.message.reply_text("خطأ في بدء اللعبة.")

# --- UI Updaters ---

async def update_game_interface(client, message, key):
    game = GameManager.get(key)
    
    p1n = UIFactory.format_name(game.p1, game.p1_name)
    p2n = game.p2_name if game.mode == "ai" else UIFactory.format_name(game.p2, game.p2_name)
    
    turn_name = game.p1_name if game.turn == game.p1 else game.p2_name
    sym = Config.SYM_X if game.turn == game.p1 else Config.SYM_O
    
    text = (
        f"**المباراة جارية:**\n"
        f"**{p1n} ({Config.SYM_X})**\n"
        f"**{p2n} ({Config.SYM_O})**\n\n"
        f"**الدور الحالي:** {turn_name} ({sym})"
    )
    
    try: await message.edit_caption(text, reply_markup=UIFactory.get_keyboard(game.board, key))
    except MessageNotModified: pass

async def handle_game_end(client, message, key, winner):
    game = GameManager.get(key)
    p1n = UIFactory.format_name(game.p1, game.p1_name)
    p2n = game.p2_name if game.mode == "ai" else UIFactory.format_name(game.p2, game.p2_name)
    
    res_text = ""
    pts_msg = ""
    
    if winner == "Draw":
        res_text = "**انتهت المباراة بالتعادل!**"
        pts_msg = "(+5 نقاط لكل لاعب)"
        DataManager.update_player(game.p1, game.p1_name, 5)
        if game.mode == "pvp": DataManager.update_player(game.p2, game.p2_name, 5)
    else:
        is_p1 = (winner == Config.SYM_X)
        win_id = game.p1 if is_p1 else game.p2
        win_nm = game.p1_name if is_p1 else game.p2_name
        
        disp_nm = f"البوت" if (game.mode == "ai" and not is_p1) else UIFactory.format_name(win_id, win_nm)
        res_text = f"**الفائز هو: {disp_nm} !**"
        
        if game.mode == "pvp":
            DataManager.update_player(win_id, win_nm, 20)
            pts_msg = "\n(+20 نقطة)"
        elif game.mode == "ai" and is_p1:
            pts = {"Easy": 5, "Medium": 10, "Hard": 20}.get(game.diff, 5)
            DataManager.update_player(win_id, win_nm, pts)
            pts_msg = f"\n(+{pts} نقطة)"
        elif game.mode == "ai" and not is_p1:
            pts_msg = "\n(حظ أوفر المرة القادمة)"

    final_txt = (
        f"**نتيجة المباراة**\n"
        f"**{p1n} ({Config.SYM_X})**\n"
        f"**{p2n} ({Config.SYM_O})**\n\n"
        f"{res_text}{pts_msg}"
    )
    
    btns = []
    row = []
    for c in game.board:
        row.append(InlineKeyboardButton(c, callback_data="none"))
        if len(row) == 3: btns.append(row); row = []
    btns.append([InlineKeyboardButton("Back to Menu", callback_data=f"xo_main_{game.p1}")])
    
    try: await message.edit_caption(final_txt, reply_markup=InlineKeyboardMarkup(btns))
    except: pass
    
    GameManager.delete(key)
