# plugins/ai/__init__.py
# Authored By Certified Coders (c) 2026
# AI Plugin Package Initializer - Project: AnnieXMedia

"""
AI Plugin Package
-----------------
This package contains:
- prompts.py   : System & behavior prompts
- engine.py    : G4F streaming engine (Turbo Edition)
- handlers.py  : Pyrogram handlers & callbacks
"""

# تحميل البرومبتات
from . import prompts  # noqa: F401

# تحميل محرك الذكاء المطور
from .engine import (
    ENGINE,
    ask_ollama_stream,
    clear_user_memory,
    toggle_model,
)  # noqa: F401

# تحميل الهاندلرز لتسجيل الأوامر
from . import handlers  # noqa: F401

__all__ = [
    "prompts",
    "ENGINE",
    "ask_ollama_stream",
    "clear_user_memory",
    "toggle_model",
    "handlers",
]
