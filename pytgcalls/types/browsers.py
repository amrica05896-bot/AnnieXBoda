from .user_agent import AgentInfo
from .user_agent import UserAgent


class Browsers:
    def __init__(self):
        # 🟢 CHROME BASE AGENT (Updated to Stable v122)
        self._chrome_agent = AgentInfo(
            'Chrome',
            '122.0.6261.94',
        )

        # 🟢 MOZILLA BASE AGENTS (Updated OS Versions)
        self._mozilla_android_agent = AgentInfo(
            'Mozilla',
            '5.0',
            'Linux',
            'Android 14; K',  # Updated to Android 14
        )
        self._mozilla_ios_agent = AgentInfo(
            'Mozilla',
            '5.0',
            'iPhone',
            'CPU iPhone OS 17_4 like Mac OS X', # Updated to iOS 17.4
        )
        self._mozilla_linux_agent = AgentInfo(
            'Mozilla',
            '5.0',
            'X11',
            'Linux x86_64',
        )
        self._mozilla_macos_agent = AgentInfo(
            'Mozilla',
            '5.0',
            'Macintosh',
            'Intel Mac OS X 10_15_7', # Most common identifier for modern Mac compatibility
        )
        self._mozilla_windows_agent = AgentInfo(
            'Mozilla',
            '5.0',
            'Windows NT 10.0', # Windows 11 still reports as NT 10.0 in UA
            'Win64',
            'x64',
        )

        # 🟢 APPLE_WEBKIT BASE AGENT
        self._apple_webkit_agent = AgentInfo(
            'AppleWebKit',
            '537.36',
            'KHTML',
            'like Gecko',
        )
        self._apple_webkit_apple_agent = AgentInfo(
            'AppleWebKit',
            '605.1.15',
            'KHTML',
            'like Gecko',
        )

        # 🟢 SAFARI BASE AGENT (Updated)
        self._safari_agent = AgentInfo(
            'Safari',
            '537.36',
        )
        self._safari_mobile_agent = AgentInfo(
            'Mobile Safari',
            '537.36',
        )
        self._safari_macos_agent = AgentInfo(
            'Safari',
            '605.1.15',
        )
        self._safari_ios_agent = AgentInfo(
            'Safari',
            '604.1',
        )

        # 🟢 EDGE BASE AGENT (Updated to v122)
        self._edge_android_agent = AgentInfo(
            'EdgA',
            '122.0.2365.92',
        )
        self._edge_ios_agent = AgentInfo(
            'EdgiOS',
            '122.0.2365.92',
        )
        self._edge_pc_agent = AgentInfo(
            'Edg',
            '122.0.2365.92',
        )
        # Windows Mobile is EOL, keeping purely for legacy code compatibility
        self._edge_windows_mob_agent = AgentInfo(
            'Edge',
            '44.18363.8131',
        )
        self._edge_xbox_agent = AgentInfo(
            'Edge',
            '44.18363.8131',
        )

        # 🟢 FIREFOX BASE AGENT (Updated to v123)
        self._firefox_default_agent = AgentInfo(
            'Firefox',
            '123.0',
        )
        self._firefox_ios_agent = AgentInfo(
            'FxiOS',
            '123.0',
        )

        # 🟢 OPERA BASE AGENT (Updated to v108)
        self._opera_default_agent = AgentInfo(
            'OPR',
            '108.0.5067.29',
        )
        self._opera_mobile_agent = AgentInfo(
            'OPR',
            '81.0.4280.76686',
        )

    # ================= PROPERTIES (NO CHANGES TO LOGIC) =================

    # CHROME
    @property
    def chrome_android(self):
        return str(
            UserAgent([
                self._mozilla_android_agent,
                self._apple_webkit_agent,
                self._chrome_agent,
                self._safari_mobile_agent,
            ]),
        )

    @property
    def chrome_ios(self):
        return str(
            UserAgent([
                self._mozilla_ios_agent,
                self._apple_webkit_agent,
                self._chrome_agent,
                self._safari_agent,
            ]),
        )

    @property
    def chrome_linux(self):
        return str(
            UserAgent([
                self._mozilla_linux_agent,
                self._apple_webkit_agent,
                self._chrome_agent,
                self._safari_agent,
            ]),
        )

    @property
    def chrome_macos(self):
        return str(
            UserAgent([
                self._mozilla_macos_agent,
                self._apple_webkit_agent,
                self._chrome_agent,
                self._safari_agent,
            ]),
        )

    @property
    def chrome_windows(self):
        return str(
            UserAgent([
                self._mozilla_windows_agent,
                self._apple_webkit_agent,
                self._chrome_agent,
                self._safari_agent,
            ]),
        )

    # EDGE
    @property
    def edge_android(self):
        return str(
            UserAgent([
                self._mozilla_android_agent,
                self._apple_webkit_agent,
                self._chrome_agent,
                self._safari_mobile_agent,
                self._edge_android_agent,
            ]),
        )

    @property
    def edge_ios(self):
        return str(
            UserAgent([
                self._mozilla_ios_agent,
                self._apple_webkit_agent,
                self._chrome_agent,
                self._safari_agent,
                self._edge_ios_agent,
            ]),
        )

    @property
    def edge_macos(self):
        return str(
            UserAgent([
                self._mozilla_macos_agent,
                self._apple_webkit_agent,
                self._chrome_agent,
                self._safari_agent,
                self._edge_pc_agent,
            ]),
        )

    @property
    def edge_windows(self):
        return str(
            UserAgent([
                self._mozilla_windows_agent,
                self._apple_webkit_agent,
                self._chrome_agent,
                self._safari_agent,
                self._edge_pc_agent,
            ]),
        )

    @property
    def edge_windows_mobile(self):
        return str(
            UserAgent([
                self._mozilla_windows_agent,
                self._apple_webkit_agent,
                self._chrome_agent,
                self._safari_agent,
                self._edge_windows_mob_agent,
            ]),
        )

    @property
    def edge_xbox_one(self):
        return str(
            UserAgent([
                self._mozilla_windows_agent,
                self._apple_webkit_agent,
                self._chrome_agent,
                self._safari_agent,
                self._edge_xbox_agent,
            ]),
        )

    # FIREFOX
    @property
    def firefox_android(self):
        return str(
            UserAgent([
                self._mozilla_android_agent,
                self._apple_webkit_agent,
                self._chrome_agent,
                self._safari_mobile_agent,
                self._firefox_default_agent,
            ]),
        )

    @property
    def firefox_ios(self):
        return str(
            UserAgent([
                self._mozilla_ios_agent,
                self._apple_webkit_agent,
                self._chrome_agent,
                self._safari_agent,
                self._firefox_ios_agent,
            ]),
        )

    @property
    def firefox_linux(self):
        return str(
            UserAgent([
                self._mozilla_linux_agent,
                self._apple_webkit_agent,
                self._chrome_agent,
                self._safari_agent,
                self._firefox_default_agent,
            ]),
        )

    @property
    def firefox_macos(self):
        return str(
            UserAgent([
                self._mozilla_macos_agent,
                self._apple_webkit_agent,
                self._chrome_agent,
                self._safari_agent,
                self._firefox_default_agent,
            ]),
        )

    @property
    def firefox_windows(self):
        return str(
            UserAgent([
                self._mozilla_windows_agent,
                self._apple_webkit_agent,
                self._chrome_agent,
                self._safari_agent,
                self._firefox_default_agent,
            ]),
        )

    # OPERA
    @property
    def opera_android(self):
        return str(
            UserAgent([
                self._mozilla_android_agent,
                self._apple_webkit_agent,
                self._chrome_agent,
                self._safari_mobile_agent,
                self._opera_mobile_agent,
            ]),
        )

    @property
    def opera_linux(self):
        return str(
            UserAgent([
                self._mozilla_linux_agent,
                self._apple_webkit_agent,
                self._chrome_agent,
                self._safari_agent,
                self._opera_default_agent,
            ]),
        )

    @property
    def opera_macos(self):
        return str(
            UserAgent([
                self._mozilla_macos_agent,
                self._apple_webkit_agent,
                self._chrome_agent,
                self._safari_agent,
                self._opera_default_agent,
            ]),
        )

    @property
    def opera_windows(self):
        return str(
            UserAgent([
                self._mozilla_windows_agent,
                self._apple_webkit_agent,
                self._chrome_agent,
                self._safari_agent,
                self._opera_default_agent,
            ]),
        )

    # SAFARI
    @property
    def safari_ios(self):
        return str(
            UserAgent([
                self._mozilla_ios_agent,
                self._apple_webkit_apple_agent,
                self._chrome_agent,
                self._safari_ios_agent,
            ]),
        )

    @property
    def safari_macos(self):
        return str(
            UserAgent([
                self._mozilla_macos_agent,
                self._apple_webkit_apple_agent,
                self._chrome_agent,
                self._safari_macos_agent,
            ]),
        )
