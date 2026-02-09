# Authored By Certified Coders 2026
# Module: XO Game Ultimate (Bitwise Engine + Original Texts)

import asyncio
import json
import os
import random
from typing import Dict, List, Optional
from dataclasses import dataclass

from pyrogram import filters, Client
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, Message
from pyrogram.errors import MessageNotModified

from AnnieXMedia import app
import config

# ════════════════════ [ 1. CONFIGURATION ] ════════════════════

GAME_IMAGE = "https://files.catbox.moe/gy85j3.jpg"
POINTS_FILE = "xo_points.json"

SYM_X = "❌"
SYM_O = "⭕"
SYM_E = "◻️"

# ════════════════════ [ 2. BITWISE ENGINE (THE BRAIN) ] ════════════════════

class BitBrain:
    # 9-bit Winning Masks (Fastest calculation method known to man)
    WINS = [
        0b111000000, 0b000111000, 0b000000111,
        0b100100100, 0b010010010, 0b001001001,
        0b100010001, 0b001010100
    ]
    FULL = 0b111111111

    @staticmethod
    def is_win(board_int: int) -> bool:
        for w in BitBrain.WINS:
            if (board_int & w) == w: return True
        return False

    @staticmethod
    def get_moves(bx: int, bo: int) -> list:
        occ = bx | bo
        return [i for i in range(9) if not (occ & (1 << (8 - i)))]

    @staticmethod
    def move(b: int, pos: int) -> int:
        return b | (1 << (8 - pos))

    @staticmethod
    def minimax(bx, bo, is_max, depth, alpha, beta):
        if BitBrain.is_win(bo): return 100 - depth
        if BitBrain.is_win(bx): return depth - 100
        if (bx | bo) == BitBrain.FULL: return 0

        moves = BitBrain.get_moves(bx, bo)
        
        if is_max: # AI (O)
            best = -1000
            for m in moves:
                val = BitBrain.minimax(bx, BitBrain.move(bo, m), False, depth+1, alpha, beta)
                best = max(best, val)
                alpha = max(alpha, best)
                if beta <= alpha: break
            return best
        else: # Human (X)
            best = 1000
            for m in moves:
                val = BitBrain.minimax(BitBrain.move(bx, m), bo, True, depth+1, alpha, beta)
                best = min(best, val)
                beta = min(beta, best)
                if beta <= alpha: break
            return best

    @staticmethod
    def best_move(bx, bo, diff):
        moves = BitBrain.get_moves(bx, bo)
        if not moves: return -1

        # Cheat / Easy
        if (hasattr(config, "XO_CHEAT") and config.XO_CHEAT) or diff == "Easy":
            return random.choice(moves)
        
        # Medium
        if diff == "Medium" and random.random() < 0.4:
            return random.choice(moves)

        # Hard (Bitwise Minimax)
        if 4 in moves: return 4 # Optimization
        
        best_sc = -1000
        best_mv = -1
        
        for m in moves:
            sc = BitBrain.minimax(bx, BitBrain.move(bo, m), False, 0, -1000, 1000)
            if sc > best_sc:
                best_sc = sc
                best_mv = m
        return best_mv

# ════════════════════ [ 3. DATA MANAGER ] ════════════════════

class DB:
    @staticmethod
    def _io(w=None):
        if w is None:
            if not os.path.exists(POINTS_FILE): return {}
            try:
                with open(POINTS_FILE, "r", encoding="utf-8") as f: return json.load(f)
            except: return {}
        with open(POINTS_FILE, "w", encoding="utf-8") as f:
            json.dump(w, f, ensure_ascii=False, indent=4)

    @staticmethod
    def update(uid, name, add=0):
        d = DB._io()
        sid = str(uid)
        obj = d.get(sid, {"points": 0, "name": name})
        if isinstance(obj, int): obj = {"points": obj, "name": name}
        
        obj["name"] = name
        obj["points"] += add
        d[sid] = obj
        DB._io(d)
        return obj["points"]

    @staticmethod
    def get_pts(uid):
        d = DB._io()
        v = d.get(str(uid), 0)
        return v["points"] if isinstance(v, dict) else v

    @staticmethod
    def top():
        d = DB._io()
        l = []
        for v in d.values():
            if isinstance(v, dict): l.append((v["name"], v["points"]))
            else: l.append(("Unknown", v))
        return sorted(l, key=lambda x: x[1], reverse=True)[:5]

# ════════════════════ [ 4. STATE & UI ] ════════════════════

@dataclass
class Session:
    bx: int = 0
    bo: int = 0
    turn: int = 0
    p1: int = 0
    p2: int = 0
    n1: str = ""
    n2: str = ""
    mode: str = "ai"
    diff: str = "Easy"

class Manager:
    games: Dict[str, Session] = {}
    waits: Dict[int, dict] = {}
    lock = asyncio.Lock()

    @staticmethod
    def kb(s: Session, key: str):
        btns = []
        row = []
        for i in range(9):
            is_x = (s.bx >> (8-i)) & 1
            is_o = (s.bo >> (8-i)) & 1
            sym = SYM_X if is_x else (SYM_O if is_o else SYM_E)
            
            row.append(InlineKeyboardButton(sym, callback_data=f"xo_m_{key}_{i}"))
            if len(row) == 3: btns.append(row); row = []
        return InlineKeyboardMarkup(btns)

    @staticmethod
    def fmt_name(uid, name): return f"[{name}](tg://user?id={uid})"

# ════════════════════ [ 5. HANDLERS (ORIGINAL TEXTS) ] ════════════════════

@app.on_message(filters.command(["xo", "اكس او", "لعبة xo"], prefixes=["", "/", "!"]))
async def start_cmd(_, m):
    if hasattr(config, "XO_ENABLED") and not config.XO_ENABLED:
        return await m.reply_text("اللعبة معطلة حالياً.")

    uid = m.from_user.id
    pts = DB.update(uid, m.from_user.first_name)
    
    txt = (
        f"**مرحباً بك في لعبة إكس أو**\n"
        f"**نقاطك:** `{pts}`\n"
        f"**المعرف:** `{m.id}`"
    )
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("Play vs AI", callback_data=f"xo_pre_ai_{uid}")],
        [InlineKeyboardButton("Play vs Friend", callback_data=f"xo_pre_pvp_{uid}")],
        [InlineKeyboardButton("Leaderboard", callback_data=f"xo_top_{uid}")]
    ])
    await m.reply_photo(GAME_IMAGE, caption=txt, reply_markup=kb)

@app.on_callback_query(filters.regex(r"^xo_"))
async def cb_router(c, cb):
    d = cb.data.split("_")
    cmd = d[1]
    uid = cb.from_user.id

    # --- Navigation ---
    if cmd == "main":
        if uid != int(d[2]): return await cb.answer("هذه اللعبة ليست لك.", show_alert=True)
        pts = DB.update(uid, cb.from_user.first_name)
        txt = f"**القائمة الرئيسية**\n**نقاطك:** `{pts}`"
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("Play vs AI", callback_data=f"xo_pre_ai_{uid}")],
            [InlineKeyboardButton("Play vs Friend", callback_data=f"xo_pre_pvp_{uid}")],
            [InlineKeyboardButton("Leaderboard", callback_data=f"xo_top_{uid}")]
        ])
        await cb.edit_message_caption(txt, reply_markup=kb)

    elif cmd == "top":
        top = DB.top()
        txt = "**قائمة أفضل اللاعبين:**\n\n"
        for i, (n, p) in enumerate(top, 1): txt += f"{i}. {n} : `{p}` نقطة\n"
        await cb.edit_message_caption(txt, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Back", callback_data=f"xo_main_{uid}")]]))

    # --- Setup ---
    elif cmd == "pre":
        owner = int(d[3])
        if uid != owner: return await cb.answer("هذه اللعبة ليست لك.", show_alert=True)
        
        mode = d[2]
        if mode == "ai":
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("Easy", callback_data=f"xo_sel_ai_Easy_{owner}")],
                [InlineKeyboardButton("Medium", callback_data=f"xo_sel_ai_Medium_{owner}")],
                [InlineKeyboardButton("Hard", callback_data=f"xo_sel_ai_Hard_{owner}")],
                [InlineKeyboardButton("Back", callback_data=f"xo_main_{owner}")]
            ])
            await cb.edit_message_caption("**اختر مستوى الصعوبة:**", reply_markup=kb)
        else:
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("Open Lobby", callback_data=f"xo_mk_pvp_{owner}")],
                [InlineKeyboardButton("Challenge ID", callback_data=f"xo_req_{owner}")],
                [InlineKeyboardButton("Back", callback_data=f"xo_main_{owner}")]
            ])
            await cb.edit_message_caption("**اختر طريقة اللعب:**", reply_markup=kb)

    # --- Logic ---
    elif cmd == "sel": # AI Start
        diff, oid = d[3], int(d[4])
        key = f"{cb.message.chat.id}_{cb.message.id}"
        async with Manager.lock:
            Manager.games[key] = Session(
                turn=oid, p1=oid, n1=cb.from_user.first_name,
                p2=0, n2=f"Bot ({diff})", mode="ai", diff=diff
            )
        await update_ui(c, cb.message, key)

    elif cmd == "mk": # Open Lobby
        oid = int(d[3])
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("Join Match", callback_data=f"xo_join_{oid}")],
            [InlineKeyboardButton("Cancel", callback_data=f"xo_main_{oid}")]
        ])
        await cb.edit_message_caption(f"**تم إنشاء اللعبة بواسطة {cb.from_user.first_name}**\n**بانتظار الخصم...**", reply_markup=kb)

    elif cmd == "join": # Join
        oid = int(d[2])
        if uid == oid: return await cb.answer("لا يمكنك اللعب ضد نفسك!", show_alert=True)
        try: n1 = (await c.get_users(oid)).first_name
        except: n1 = "Player 1"
        
        key = f"{cb.message.chat.id}_{cb.message.id}"
        DB.update(uid, cb.from_user.first_name)
        async with Manager.lock:
            Manager.games[key] = Session(
                turn=oid, p1=oid, n1=n1,
                p2=uid, n2=cb.from_user.first_name, mode="pvp"
            )
        await update_ui(c, cb.message, key)

    elif cmd == "req": # Req
        Manager.waits[uid] = {"c": cb.message.chat.id, "m": cb.message.id}
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("Cancel", callback_data=f"xo_main_{uid}")]])
        await cb.edit_message_caption("**أرسل الآن يوزر أو آيدي الشخص الذي تريد تحديه:**", reply_markup=kb)

    elif cmd == "cancel":
        if uid == int(d[2]):
            Manager.waits.pop(uid, None)
            await main_entry(c, cb.message)
        else: await cb.answer("ليس لك.")

    # --- Gameplay (Bitwise) ---
    elif cmd == "m":
        key = f"{d[2]}_{d[3]}"
        pos = int(d[4])
        s = Manager.games.get(key)
        
        if not s: return await cb.answer("الجلسة منتهية.", show_alert=True)
        if uid != s.turn: return await cb.answer("ليس دورك!", show_alert=True)
        if ((s.bx | s.bo) >> (8-pos)) & 1: return await cb.answer("خانة مشغولة.", show_alert=True)

        async with Manager.lock:
            # Human
            is_p1 = (uid == s.p1)
            if is_p1: s.bx |= (1 << (8-pos))
            else: s.bo |= (1 << (8-pos))

            chk = s.bx if is_p1 else s.bo
            if BitBrain.is_win(chk):
                await finish(c, cb.message, key, SYM_X if is_p1 else SYM_O)
                return
            
            if (s.bx | s.bo) == BitBrain.FULL:
                await finish(c, cb.message, key, "D")
                return

            # AI
            if s.mode == "ai":
                mv = BitBrain.best_move(s.bx, s.bo, s.diff)
                if mv != -1:
                    s.bo |= (1 << (8-mv))
                    if BitBrain.is_win(s.bo):
                        await finish(c, cb.message, key, SYM_O)
                        return
                    if (s.bx | s.bo) == BitBrain.FULL:
                        await finish(c, cb.message, key, "D")
                        return
                s.turn = s.p1
            else:
                s.turn = s.p2 if s.turn == s.p1 else s.p1
            
            await update_ui(c, cb.message, key)

# --- Challenge ---
@app.on_message(filters.text & filters.group)
async def chal_inp(c, m):
    uid = m.from_user.id
    if uid in Manager.waits:
        ctx = Manager.waits.pop(uid)
        if m.chat.id != ctx["c"]: return
        try:
            tgt = await c.get_users(m.text)
            if tgt.is_bot or tgt.id == uid: raise Exception
            
            DB.update(uid, m.from_user.first_name)
            DB.update(tgt.id, tgt.first_name)
            
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("Accept", callback_data=f"xo_acc_{uid}_{tgt.id}_{ctx['m']}")],
                [InlineKeyboardButton("Reject", callback_data=f"xo_dny_{uid}_{tgt.id}_{ctx['m']}")]
            ])
            await m.reply_text(f"**تحدي جديد!**\n**{m.from_user.mention}** يتحدى **{tgt.mention}**", reply_markup=kb)
        except: await m.reply_text("لم يتم العثور على اللاعب.")

@app.on_callback_query(filters.regex(r"^xo_(acc|dny)"))
async def chal_res(c, cb):
    d = cb.data.split("_")
    p1, p2, mid = int(d[2]), int(d[3]), int(d[4])
    
    if cb.from_user.id != p2: return await cb.answer("هذا التحدي ليس لك.", show_alert=True)
    if d[1] == "dny": return await cb.message.edit_text(f"**تم رفض التحدي من قبل {cb.from_user.mention}.**")
    
    key = f"{cb.message.chat.id}_{mid}"
    try: n1 = (await c.get_users(p1)).first_name
    except: n1 = "Player 1"
    
    await cb.message.delete()
    async with Manager.lock:
        Manager.games[key] = Session(
            turn=p1, p1=p1, n1=n1, p2=p2, n2=cb.from_user.first_name, mode="pvp"
        )
    
    try:
        orig = await c.get_messages(cb.message.chat.id, mid)
        await update_ui(c, orig, key)
    except: pass

# --- Core UI ---

async def update_ui(c, m, key):
    s = Manager.games[key]
    tn = s.n1 if s.turn == s.p1 else s.n2
    ts = SYM_X if s.turn == s.p1 else SYM_O
    
    p1 = Manager.fmt_name(s.p1, s.n1)
    p2 = s.n2 if s.mode == "ai" else Manager.fmt_name(s.p2, s.n2)
    
    txt = (
        f"**المباراة جارية:**\n"
        f"**{p1} ({SYM_X})**\n"
        f"**{p2} ({SYM_O})**\n\n"
        f"**الدور الحالي:** {tn} ({ts})"
    )
    try: await m.edit_caption(txt, reply_markup=Manager.kb(s, key))
    except: pass

async def finish(c, m, key, win_sym):
    s = Manager.games.pop(key)
    p1n = Manager.fmt_name(s.p1, s.n1)
    p2n = s.n2 if s.mode == "ai" else Manager.fmt_name(s.p2, s.n2)
    
    res = ""
    if win_sym == "D":
        res = "**انتهت المباراة بالتعادل!**\n(+5 نقاط لكل لاعب)"
        DB.update(s.p1, s.n1, 5)
        if s.mode == "pvp": DB.update(s.p2, s.n2, 5)
    else:
        is_p1 = (win_sym == SYM_X)
        wid = s.p1 if is_p1 else s.p2
        wnm = s.n1 if is_p1 else s.n2
        
        dnm = "Bot" if (s.mode == "ai" and not is_p1) else Manager.fmt_name(wid, wnm)
        res = f"**الفائز هو: {dnm} !**"
        
        if s.mode == "pvp":
            DB.update(wid, wnm, 20)
            res += "\n(+20 نقطة)"
        elif s.mode == "ai" and is_p1:
            pts = {"Easy": 5, "Medium": 10, "Hard": 20}.get(s.diff, 5)
            DB.update(wid, wnm, pts)
            res += f"\n(+{pts} نقطة)"
        elif s.mode == "ai" and not is_p1:
            res += "\n(حظ أوفر المرة القادمة)"

    fin = (
        f"**نتيجة المباراة**\n"
        f"**{p1n} ({SYM_X})**\n"
        f"**{p2n} ({SYM_O})**\n\n"
        f"{res}"
    )
    
    btns = []
    row = []
    # Reconstruct board from bits for dead view
    for i in range(9):
        ix = (s.bx >> (8-i)) & 1
        io = (s.bo >> (8-i)) & 1
        t = SYM_X if ix else (SYM_O if io else SYM_E)
        row.append(InlineKeyboardButton(t, callback_data="none"))
        if len(row)==3: btns.append(row); row=[]
    btns.append([InlineKeyboardButton("Back to Menu", callback_data=f"xo_main_{s.p1}")])
    
    try: await m.edit_caption(fin, reply_markup=InlineKeyboardMarkup(btns))
    except: pass
