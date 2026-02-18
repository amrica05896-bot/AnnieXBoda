import flet as ft
import asyncio
import aiohttp
import json
from datetime import datetime

API_BASE = "http://0.0.0.0:8080"

COLORS = {
    "void": "#000000",
    "glass": "#1a1a1a",
    "glass_border": "#333333",
    "primary": "#00f3ff",
    "secondary": "#7000ff",
    "danger": "#ff003c",
    "success": "#00ff9d",
    "text": "#ffffff",
    "text_dim": "#888888",
    "surface": "#0a0a0a"
}

class ObsidianAPI:
    def __init__(self):
        self.session = None

    async def ensure_session(self):
        if not self.session:
            self.session = aiohttp.ClientSession()

    async def get_stats(self):
        await self.ensure_session()
        try:
            async with self.session.get(f"{API_BASE}/api/stats") as resp:
                if resp.status == 200:
                    return await resp.json()
        except:
            pass
        return {"cpu": 0, "ram_percent": 0, "ram_used_gb": 0}

    async def get_status(self):
        await self.ensure_session()
        try:
            async with self.session.get(f"{API_BASE}/status_json") as resp:
                if resp.status == 200:
                    return await resp.json()
        except:
            pass
        return {"count": 0, "chats": []}

    async def get_queue(self, chat_id):
        await self.ensure_session()
        try:
            async with self.session.get(f"{API_BASE}/api/queue/{chat_id}") as resp:
                return await resp.json()
        except:
            return {"queue": []}

    async def send_control(self, chat_id, action):
        await self.ensure_session()
        try:
            payload = {"chat_id": chat_id, "action": action}
            async with self.session.post(f"{API_BASE}/api/control", json=payload) as resp:
                return await resp.json()
        except:
            return {"error": "Connection Failed"}

    async def search(self, query):
        await self.ensure_session()
        try:
            async with self.session.post(f"{API_BASE}/api/search", json={"query": query}) as resp:
                return await resp.json()
        except:
            return {"results": []}

    async def inject(self, target, query, video):
        await self.ensure_session()
        try:
            payload = {"chat_id": target, "query": query, "video": video}
            async with self.session.post(f"{API_BASE}/api/play", json=payload) as resp:
                return await resp.json()
        except:
            return {"error": "Failed"}

api = ObsidianAPI()

class GlassCard(ft.Container):
    def __init__(self, content, width=None, height=None, padding=20, on_click=None):
        super().__init__(
            content=content,
            width=width,
            height=height,
            padding=padding,
            bgcolor=ft.colors.with_opacity(0.6, COLORS["glass"]),
            border=ft.border.all(1, ft.colors.with_opacity(0.2, "white")),
            border_radius=20,
            blur=ft.Blur(20, 20, ft.BlurTileMode.MIRROR),
            shadow=ft.BoxShadow(
                spread_radius=0,
                blur_radius=20,
                color=ft.colors.with_opacity(0.3, "black"),
                offset=ft.Offset(0, 10),
            ),
            on_click=on_click,
            animate=ft.animation.Animation(300, "easeOut"),
        )

class ObsidianButton(ft.Container):
    def __init__(self, text, icon, on_click, color=COLORS["primary"], filled=False):
        content_color = COLORS["void"] if filled else color
        bg_color = color if filled else ft.colors.with_opacity(0.05, color)
        border = None if filled else ft.border.all(1, color)
        
        super().__init__(
            content=ft.Row(
                [
                    ft.Icon(icon, size=16, color=content_color),
                    ft.Text(text, size=12, weight="bold", color=content_color, font_family="Rajdhani")
                ],
                alignment=ft.MainAxisAlignment.CENTER,
                spacing=8
            ),
            padding=ft.padding.symmetric(12, 20),
            bgcolor=bg_color,
            border=border,
            border_radius=12,
            on_click=on_click,
            animate=ft.animation.Animation(200, "easeOut"),
            ink=True
        )

class StatWidget(ft.Column):
    def __init__(self, title, color):
        self.val_text = ft.Text("0%", size=24, weight="bold", font_family="Rajdhani")
        self.bar = ft.ProgressBar(value=0, color=color, bgcolor="#222222", height=4)
        super().__init__(
            controls=[
                ft.Text(title, size=10, color=COLORS["text_dim"], weight="bold"),
                self.val_text,
                self.bar
            ],
            spacing=5
        )

    def update_data(self, val, text_val):
        self.bar.value = val / 100
        self.val_text.value = text_val
        self.update()

class CinemaOverlay(ft.Stack):
    def __init__(self, page):
        self.page = page
        self.webview = ft.WebView(
            url="",
            visible=False,
            expand=True
        )
        self.close_btn = ft.IconButton(
            icon=ft.icons.CLOSE,
            icon_color="white",
            bgcolor=COLORS["danger"],
            on_click=self.close
        )
        self.container = ft.Container(
            content=ft.Stack([
                self.webview,
                ft.Container(
                    content=self.close_btn,
                    top=20, right=20
                )
            ]),
            visible=False,
            expand=True,
            bgcolor="black",
            alignment=ft.alignment.center
        )
        super().__init__(controls=[self.container], expand=True)

    def open(self, vidid):
        self.webview.url = f"https://www.youtube.com/embed/{vidid}?autoplay=1&controls=0&modestbranding=1&iv_load_policy=3"
        self.webview.visible = True
        self.container.visible = True
        self.container.update()
        self.webview.update()

    def close(self, e):
        self.webview.url = "about:blank"
        self.webview.visible = False
        self.container.visible = False
        self.container.update()
        self.webview.update()

class DashboardPage(ft.Column):
    def __init__(self, app_root):
        self.app_root = app_root
        self.grid = ft.GridView(
            expand=True,
            runs_count=5,
            max_extent=350,
            child_aspect_ratio=0.9,
            spacing=20,
            run_spacing=20,
        )
        super().__init__(
            controls=[
                ft.Text("CONTROL CENTER", size=24, weight="bold", font_family="Rajdhani", color=COLORS["text"]),
                ft.Divider(color=COLORS["glass_border"]),
                self.grid
            ],
            expand=True,
            spacing=20
        )

    def create_card(self, chat):
        vidid = chat.get("vidid", "")
        title = chat.get("title", "Unknown")
        chat_id = chat.get("chat_id")
        
        return GlassCard(
            content=ft.Column([
                ft.Row([
                    ft.Container(
                        content=ft.Text("LIVE", size=10, weight="bold", color="white"),
                        bgcolor=COLORS["danger"], padding=ft.padding.symmetric(4, 8),
                        border_radius=4
                    ),
                    ft.Text(str(chat_id), size=12, color=COLORS["text_dim"], font_family="JetBrains Mono")
                ], alignment="spaceBetween"),
                
                ft.Container(
                    image_src=f"https://i.ytimg.com/vi/{vidid}/mqdefault.jpg",
                    image_fit=ft.ImageFit.COVER,
                    border_radius=12,
                    height=120,
                    border=ft.border.all(1, COLORS["glass_border"])
                ),
                
                ft.Text(title, size=14, weight="bold", max_lines=1, overflow="ellipsis"),
                
                ft.Row([
                    ft.IconButton(ft.icons.PAUSE, icon_color="white", on_click=lambda e: self.control(chat_id, "pause")),
                    ft.IconButton(ft.icons.PLAY_ARROW, icon_color="white", on_click=lambda e: self.control(chat_id, "resume")),
                    ft.IconButton(ft.icons.SKIP_NEXT, icon_color="white", on_click=lambda e: self.control(chat_id, "skip")),
                    ft.IconButton(ft.icons.STOP, icon_color=COLORS["danger"], on_click=lambda e: self.control(chat_id, "stop")),
                ], alignment="center"),
                
                ObsidianButton("ENTER CINEMA", ft.icons.MOVIE, lambda e: self.app_root.cinema.open(vidid), filled=True)
            ], spacing=15)
        )

    def control(self, chat_id, act):
        asyncio.create_task(api.send_control(chat_id, act))

    async def update_view(self, data):
        self.grid.controls.clear()
        if data["count"] == 0:
            self.grid.controls.append(
                ft.Container(
                    content=ft.Column([
                        ft.Icon(ft.icons.POWER_OFF, size=64, color=COLORS["text_dim"]),
                        ft.Text("SYSTEM IDLE", size=20, weight="bold", color=COLORS["text_dim"])
                    ], alignment="center", horizontal_alignment="center"),
                    alignment=ft.alignment.center,
                    height=400
                )
            )
        else:
            for chat in data["chats"]:
                self.grid.controls.append(self.create_card(chat))
        self.update()

class RemotePage(ft.Column):
    def __init__(self):
        self.log_view = ft.ListView(expand=True, auto_scroll=True, spacing=5)
        self.target_in = ft.TextField(
            label="TARGET ID", bgcolor=COLORS["surface"], border_color=COLORS["glass_border"],
            text_style=ft.TextStyle(font_family="JetBrains Mono"), text_size=14
        )
        self.query_in = ft.TextField(
            label="PAYLOAD (LINK / QUERY)", bgcolor=COLORS["surface"], border_color=COLORS["glass_border"],
            text_style=ft.TextStyle(font_family="JetBrains Mono"), text_size=14
        )
        
        super().__init__(
            controls=[
                ft.Text("REMOTE INJECTION", size=24, weight="bold", font_family="Rajdhani"),
                ft.Divider(color=COLORS["glass_border"]),
                GlassCard(
                    content=ft.Column([
                        self.target_in,
                        self.query_in,
                        ft.Row([
                            ft.Container(
                                content=ObsidianButton("INJECT AUDIO", ft.icons.AUDIOTRACK, lambda e: self.inject(False), filled=True),
                                expand=True
                            ),
                            ft.Container(
                                content=ObsidianButton("INJECT VIDEO", ft.icons.VIDEOCAM, lambda e: self.inject(True)),
                                expand=True
                            )
                        ])
                    ], spacing=20),
                    padding=30
                ),
                ft.Container(
                    content=self.log_view,
                    bgcolor=COLORS["surface"], border_radius=12, padding=20,
                    border=ft.border.all(1, COLORS["glass_border"]),
                    expand=True
                )
            ],
            expand=True, spacing=20
        )

    def log(self, msg, color="white"):
        t = datetime.now().strftime("%H:%M:%S")
        self.log_view.controls.append(
            ft.Text(f"[{t}] {msg}", color=color, font_family="JetBrains Mono", size=12)
        )
        self.update()

    def inject(self, video):
        tgt = self.target_in.value
        qry = self.query_in.value
        if not tgt or not qry:
            self.log("ERROR: Missing fields", COLORS["danger"])
            return
        
        self.log(f"Injecting payload to {tgt}...", COLORS["text_dim"])
        
        async def _req():
            res = await api.inject(tgt, qry, video)
            if res.get("error"):
                self.log(f"FAIL: {res['error']}", COLORS["danger"])
            else:
                self.log(f"SUCCESS: {res.get('title')}", COLORS["success"])
        
        asyncio.create_task(_req())

class MediaPage(ft.Column):
    def __init__(self, app_root):
        self.app_root = app_root
        self.search_in = ft.TextField(
            hint_text="Search Global Database...", bgcolor=COLORS["surface"], 
            border_color=COLORS["glass_border"], expand=True, on_submit=self.do_search
        )
        self.results = ft.GridView(expand=True, max_extent=300, child_aspect_ratio=1.2, spacing=15, run_spacing=15)
        
        super().__init__(
            controls=[
                ft.Text("MEDIA BROWSER", size=24, weight="bold", font_family="Rajdhani"),
                ft.Row([
                    self.search_in,
                    ObsidianButton("SCAN", ft.icons.SEARCH, self.do_search, filled=True)
                ]),
                self.results
            ],
            expand=True, spacing=20
        )

    def do_search(self, e):
        q = self.search_in.value
        if not q: return
        self.results.controls.clear()
        self.results.controls.append(ft.Text("Scanning Neural Network...", color=COLORS["primary"]))
        self.update()
        
        async def _req():
            res = await api.search(q)
            self.results.controls.clear()
            if not res.get("results"):
                self.results.controls.append(ft.Text("No Results Found.", color=COLORS["text_dim"]))
            else:
                for item in res["results"]:
                    self.results.controls.append(self.build_item(item))
            self.update()
        asyncio.create_task(_req())

    def build_item(self, item):
        return GlassCard(
            content=ft.Column([
                ft.Container(
                    image_src=item["thumb"], image_fit=ft.ImageFit.COVER,
                    height=100, border_radius=8,
                    content=ft.Container(
                        content=ft.Text(item["duration"], size=10, weight="bold", color="white"),
                        bgcolor="black", padding=4, border_radius=4,
                        alignment=ft.alignment.bottom_right
                    )
                ),
                ft.Text(item["title"], size=12, weight="bold", max_lines=2, overflow="ellipsis"),
                ft.Row([
                    ObsidianButton("PLAY", ft.icons.PLAY_ARROW, lambda e: self.fill_remote(item["title"]), filled=True),
                    ObsidianButton("WATCH", ft.icons.MOVIE, lambda e: self.app_root.cinema.open(item["vidid"]))
                ], alignment="spaceBetween")
            ], spacing=10),
            padding=15
        )

    def fill_remote(self, title):
        self.app_root.show_view("remote")
        self.app_root.remote_view.query_in.value = title
        self.app_root.remote_view.update()

class QueuePage(ft.Column):
    def __init__(self):
        self.target_in = ft.TextField(hint_text="Enter Chat ID", bgcolor=COLORS["surface"], expand=True)
        self.q_list = ft.ListView(expand=True, spacing=10)
        
        super().__init__(
            controls=[
                ft.Text("QUEUE MANAGER", size=24, weight="bold", font_family="Rajdhani"),
                ft.Row([
                    self.target_in,
                    ObsidianButton("FETCH", ft.icons.REFRESH, self.fetch, filled=True)
                ]),
                self.q_list
            ],
            expand=True, spacing=20
        )

    def fetch(self, e):
        tid = self.target_in.value
        if not tid: return
        
        async def _req():
            res = await api.get_queue(tid)
            self.q_list.controls.clear()
            if not res.get("queue"):
                self.q_list.controls.append(ft.Text("Queue is empty.", color=COLORS["text_dim"]))
            else:
                for idx, item in enumerate(res["queue"]):
                    self.q_list.controls.append(
                        ft.Container(
                            content=ft.Row([
                                ft.Text(f"#{idx+1}", size=14, weight="bold", color=COLORS["primary"]),
                                ft.Column([
                                    ft.Text(item["title"], size=14, weight="bold"),
                                    ft.Text(item["duration"], size=12, color=COLORS["text_dim"])
                                ], expand=True)
                            ]),
                            bgcolor=COLORS["surface"], padding=15, border_radius=10,
                            border=ft.border.all(1, COLORS["glass_border"])
                        )
                    )
            self.update()
        asyncio.create_task(_req())

class TitanApp:
    def __init__(self, page: ft.Page):
        self.page = page
        self.setup_page()
        
        # --- UI COMPONENTS ---
        self.cinema = CinemaOverlay(page)
        self.dash_view = DashboardPage(self)
        self.media_view = MediaPage(self)
        self.remote_view = RemotePage()
        self.queue_view = QueuePage()
        
        self.content_area = ft.Container(content=self.dash_view, expand=True, padding=30)
        
        self.cpu_widget = StatWidget("CPU CORE", COLORS["primary"])
        self.ram_widget = StatWidget("RAM ALLOC", COLORS["secondary"])

        self.layout = ft.Row(
            controls=[
                self.build_sidebar(),
                ft.VerticalDivider(width=1, color=COLORS["glass_border"]),
                self.content_area
            ],
            expand=True, spacing=0
        )
        
        self.page.overlay.append(self.cinema)
        self.page.add(self.layout)
        
        # --- BACKGROUND TASKS ---
        self.page.run_task(self.loop)

    def setup_page(self):
        self.page.title = "TitanOS Obsidian"
        self.page.bgcolor = COLORS["void"]
        self.page.theme_mode = ft.ThemeMode.DARK
        self.page.padding = 0
        self.page.fonts = {
            "Rajdhani": "https://fonts.gstatic.com/s/rajdhani/v15/L10xV2Gt2_gTvjZT5Q.ttf",
            "JetBrains Mono": "https://fonts.gstatic.com/s/jetbrainsmono/v18/tDbY2o-flEEny0FZhsfKu5WU4zr3E_BX0Pn5qRS8.ttf"
        }

    def build_sidebar(self):
        return ft.Container(
            width=280,
            bgcolor=ft.colors.with_opacity(0.8, "#050505"),
            blur=ft.Blur(30),
            padding=30,
            content=ft.Column([
                ft.Row([
                    ft.Container(width=10, height=10, bgcolor=COLORS["primary"], border_radius=5, shadow=ft.BoxShadow(blur_radius=10, color=COLORS["primary"])),
                    ft.Column([
                        ft.Text("TITAN OS", size=20, weight="bold", font_family="Rajdhani", height=20),
                        ft.Text("ENTERPRISE", size=10, color=COLORS["primary"], letter_spacing=2)
                    ], spacing=0)
                ], spacing=15),
                ft.Divider(color=COLORS["glass_border"]),
                ft.Column([
                    self.nav_btn("DASHBOARD", ft.icons.DASHBOARD, "dash"),
                    self.nav_btn("MEDIA", ft.icons.LIBRARY_MUSIC, "media"),
                    self.nav_btn("REMOTE", ft.icons.TERMINAL, "remote"),
                    self.nav_btn("QUEUE", ft.icons.QUEUE_MUSIC, "queue"),
                ], spacing=5),
                ft.Container(expand=True),
                self.cpu_widget,
                self.ram_widget
            ])
        )

    def nav_btn(self, text, icon, view):
        return ft.Container(
            content=ft.Row([
                ft.Icon(icon, size=20, color=COLORS["text_dim"]),
                ft.Text(text, size=14, weight="w600", color=COLORS["text_dim"])
            ], spacing=15),
            padding=15,
            border_radius=12,
            on_click=lambda e: self.show_view(view),
            animate=ft.animation.Animation(200, "easeOut"),
            data=view
        )

    def show_view(self, view_name):
        views = {
            "dash": self.dash_view,
            "media": self.media_view,
            "remote": self.remote_view,
            "queue": self.queue_view
        }
        self.content_area.content = views[view_name]
        self.content_area.update()

    async def loop(self):
        while True:
            try:
                # Update Stats
                stats = await api.get_stats()
                self.cpu_widget.update_data(stats.get("cpu", 0), f"{stats.get('cpu', 0)}%")
                self.ram_widget.update_data(stats.get("ram_percent", 0), f"{stats.get('ram_used_gb', 0)} GB")

                # Update Dashboard if active
                if self.content_area.content == self.dash_view:
                    status = await api.get_status()
                    await self.dash_view.update_view(status)
            except Exception as e:
                print(f"Loop Error: {e}")
            
            await asyncio.sleep(2)

async def main(page: ft.Page):
    app = TitanApp(page)

if __name__ == "__main__":
    ft.app(target=main, view=ft.AppView.WEB_BROWSER, port=8550, assets_dir="assets")
