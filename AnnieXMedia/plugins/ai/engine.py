# file: AnnieXMedia/plugins/ai/engine.py
# Authored By Certified Coders (c) 2026
# G4F Engine - Architecture Verified (Scan Result: Sync Generator)
# Fixes: 'async_generator can't be used in await'

import logging
import time
import asyncio
from typing import Dict, List, Callable, Any

# Dynamic Import to prevent startup crashes
try:
    import g4f
    from g4f.client import AsyncClient
    G4F_AVAILABLE = True
except ImportError:
    G4F_AVAILABLE = False

# ------------------------------------------------------------------
# CONFIGURATION
# ------------------------------------------------------------------
logger = logging.getLogger("AnnieX_Engine")
logger.setLevel(logging.INFO)

# Default Model (Fallback to gpt-4 as tested)
TARGET_MODEL = "gpt-4"

# Memory Structure: {user_id: [{"role": "user", "content": "..."}, ...]}
_MEMORY: Dict[int, List[Dict[str, str]]] = {}

# Engine State
_IS_ENABLED = True

# Initialize Client
# Note: Providers are auto-selected by g4f
_client = AsyncClient() if G4F_AVAILABLE else None

# ------------------------------------------------------------------
# CORE FUNCTIONS (API)
# ------------------------------------------------------------------

async def ask_ollama_stream(
    user_id: int, 
    prompt: str, 
    on_update: Callable[[str], Any] = None
) -> str:
    """
    Main chat function.
    Architecture Note: Based on scan, 'create' is Sync but returns AsyncGenerator.
    """
    if not _IS_ENABLED:
        return "AI module is currently disabled."
    
    if not G4F_AVAILABLE:
        return "G4F library is missing. Install via pip."

    # 1. Memory Management
    if user_id not in _MEMORY:
        _MEMORY[user_id] = []
        _MEMORY[user_id].append({
            "role": "system", 
            "content": "You are Annie, a helpful assistant. Reply concisely in Arabic."
        })
    
    _MEMORY[user_id].append({"role": "user", "content": prompt})
    
    # Trim Memory (Keep last 8 messages context)
    if len(_MEMORY[user_id]) > 9:
        sys_msg = _MEMORY[user_id][0]
        recent = _MEMORY[user_id][-8:]
        _MEMORY[user_id] = [sys_msg] + recent

    full_response = ""
    last_update_time = time.time()

    try:
        # 2. Request Creation (THE FIX)
        # Based on scan: create() is Sync, returns AsyncGenerator.
        # DO NOT USE 'await' HERE.
        response_generator = _client.chat.completions.create(
            model=TARGET_MODEL,
            messages=_MEMORY[user_id],
            stream=True
        )

        # 3. Stream Consumption
        # Iterate over the generator asynchronously
        async for chunk in response_generator:
            if chunk.choices and chunk.choices[0].delta.content:
                content = chunk.choices[0].delta.content
                full_response += content
                
                # Rate limit updates (prevents FloodWait)
                now = time.time()
                if on_update and (now - last_update_time > 1.2):
                    try:
                        await on_update(full_response + " ◾️")
                        last_update_time = now
                    except Exception:
                        pass

        # 4. Finalize
        if full_response.strip():
            _MEMORY[user_id].append({"role": "assistant", "content": full_response})
            return full_response
        else:
            return "No response received. Try a different model or provider."

    except Exception as e:
        logger.error(f"G4F Logic Error: {e}")
        return f"AI Error: {str(e)[:100]}"

def clear_user_memory(user_id: int):
    if user_id in _MEMORY:
        del _MEMORY[user_id]

def get_engine_status():
    return {
        "enabled": _IS_ENABLED,
        "backend": "G4F (AsyncClient)",
        "model": TARGET_MODEL,
        "active_users": len(_MEMORY)
    }

def set_engine_state(state: bool):
    global _IS_ENABLED
    _IS_ENABLED = state

# ------------------------------------------------------------------
# COMPATIBILITY LAYER
# ------------------------------------------------------------------
def toggle_model(model_name: str = None) -> str:
    global TARGET_MODEL
    if model_name:
        TARGET_MODEL = model_name
        return f"Model switched to: {TARGET_MODEL}"
    return f"Current Model: {TARGET_MODEL}"

class LegacyEngineWrapper:
    def __init__(self):
        self.is_running = True
        self.memory = _MEMORY
    
    @property
    def model(self):
        return TARGET_MODEL

ENGINE = LegacyEngineWrapper()

__all__ = [
    "ask_ollama_stream", 
    "clear_user_memory", 
    "get_engine_status", 
    "set_engine_state", 
    "toggle_model", 
    "ENGINE"
]
