# plugins/ai/__init__.py
# Authored By Certified Coders (c) 2026
# AI Plugin Package Initializer - Project: AnnieXMedia
# Updated for DeepSeek-R1 H200 Engine

"""
AI Plugin Package
-----------------
This package contains:
- prompts.py   : System & behavior prompts
- engine.py    : DeepSeek-R1 (Ollama) Streaming Engine
- handlers.py  : Pyrogram handlers & callbacks
"""

# تحميل البرومبتات (إذا وجدت)
try:
    from . import prompts
except ImportError:
    prompts = None

# تحميل محرك الذكاء المطور (DeepSeek Engine)
# تم إضافة get_engine_status و set_engine_state لدعم لوحة تحكم المطورين
from .engine import (
    ENGINE,              # كائن التوافق للنظام القديم
    ask_ollama_stream,   # دالة المحادثة الرئيسية
    clear_user_memory,   # مسح الذاكرة
    toggle_model,        # دالة التوافق (Dummy)
    get_engine_status,   # حالة المحرك (للوحة الأدمن)
    set_engine_state,    # تشغيل/إيقاف المحرك
)

# تحميل الهاندلرز لتسجيل الأوامر
from . import handlers

__all__ = [
    "prompts",
    "ENGINE",
    "ask_ollama_stream",
    "clear_user_memory",
    "toggle_model",
    "get_engine_status",
    "set_engine_state",
    "handlers",
]
