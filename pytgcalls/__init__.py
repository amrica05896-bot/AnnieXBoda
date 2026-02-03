from .__version__ import __version__
from .custom_api import CustomApi
from .media_devices import MediaDevices
from .pytgcalls import PyTgCalls
# استيراد النسخ غير المتزامنة (Async) مباشرة بدل الـ Sync
from .methods.utilities import compose
from .methods.utilities import idle

__all__ = (
    '__version__',
    'compose',
    'CustomApi',
    'PyTgCalls',
    'MediaDevices',
    'idle',
)
