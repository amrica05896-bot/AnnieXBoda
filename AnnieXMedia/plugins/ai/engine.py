# file: AnnieXMedia/plugins/ai/engine.py
# Authored By Certified Coders (c) 2026
# G4F Engine (GPT-4 Optimized) - H200 Optimized
# Fixes: ImportError toggle_model, ENGINE, No Emojis

import os
import logging
import json
import time
import asyncio
from typing import Dict, List, Callable, Any, Optional

# Try importing g4f
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

# Target Model (GPT-4 based on Termux tests)
TARGET_MODEL = "gpt-4"

# RAM Memory
# Structure: {user_id: [{"role": "user", "content": "..."}, ...]}
_MEMORY: Dict[int, List[Dict[str, str]]] = {}

# Engine State
_IS_ENABLED = True

# Initialize G4F Client
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
    Main chat function supporting memory and streaming.
    Uses G4F backend but keeps the original name for compatibility.
    """
    if not _IS_ENABLED:
        return "AI is currently disabled for maintenance."

    if not G4F_AVAILABLE:
        return "G4F library not found. Please install it using pip install g4f"

    # 1. Prepare Memory
    if user_id not in _MEMORY:
        _MEMORY[user_id] = []
        # System Prompt (Strict No-Emoji)
        _MEMORY[user_id].append({
            "role": "system", 
            "content": (
                "You are Annie, an advanced AI assistant. "
                "Answer directly, accurately, and briefly in Arabic. "
                "Do NOT use emojis strictly."
            )
        })
    
    # Add user message
    _MEMORY[user_id].append({"role": "user", "content": prompt})
    
    # Keep only last 12 messages
    if len(_MEMORY[user_id]) > 12:
        sys_msg = _MEMORY[user_id][0]
        recent = _MEMORY[user_id][-11:]
        _MEMORY[user_id] = [sys_msg] + recent

    full_response = ""
    last_update_time = time.time()
    
    try:
        # Request to G4F Provider
        response = await _client.chat.completions.create(
            model=TARGET_MODEL,
            messages=_MEMORY[user_id],
            stream=True
        )

        async for chunk in response:
            if chunk.choices and chunk.choices[0].delta.content:
                content = chunk.choices[0].delta.content
                full_response += content
                
                # Update every 0.8s to avoid FloodWait
                now = time.time()
                if on_update and (now - last_update_time > 0.8):
                    try:
                        await on_update(full_response + " ...")
                        last_update_time = now
                    except:
                        pass
        
        # 3. Save Assistant Response
        if full_response.strip():
            _MEMORY[user_id].append({"role": "assistant", "content": full_response})
            return full_response
        else:
            return "No response received from server."

    except Exception as e:
        logger.error(f"G4F Error: {e}")
        return "An error occurred while connecting to the AI engine."

def clear_user_memory(user_id: int):
    """Clear memory for a specific user"""
    if user_id in _MEMORY:
        del _MEMORY[user_id]

def get_engine_status():
    """Get engine status for stats"""
    return {
        "enabled": _IS_ENABLED,
        "model": TARGET_MODEL,
        "active_users": len(_MEMORY)
    }

def set_engine_state(state: bool):
    """Enable or disable AI"""
    global _IS_ENABLED
    _IS_ENABLED = state

# ------------------------------------------------------------------
# Missing Function Fix (toggle_model)
# ------------------------------------------------------------------
def toggle_model(model_name: str = None) -> str:
    """
    Function to change model dynamically.
    """
    global TARGET_MODEL
    if model_name:
        TARGET_MODEL = model_name
        return f"Model changed to: {TARGET_MODEL}"
    return f"Current model: {TARGET_MODEL}"

# ------------------------------------------------------------------
# COMPATIBILITY LAYER (Fixes ImportError ENGINE)
# ------------------------------------------------------------------
class LegacyEngineWrapper:
    """
    Wrapper class to satisfy legacy imports.
    Prevents error: cannot import name 'ENGINE'
    """
    def __init__(self):
        self.is_running = True
        self.memory = _MEMORY
    
    @property
    def model(self):
        return TARGET_MODEL

# Dummy Engine Object
ENGINE = LegacyEngineWrapper()

# Export all necessary functions
__all__ = [
    "ask_ollama_stream", 
    "clear_user_memory", 
    "get_engine_status", 
    "set_engine_state", 
    "toggle_model", 
    "ENGINE"
]
