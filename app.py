import customtkinter as ctk
from Backend.Backend import TranslationEngine
from GUI.page_translate import PageTranslate
from GUI.page_adjust import PageAdjust

ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

class AnimeTranslatorApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Comic translator")
        self.geometry("1100x700")
        
        # 集中管理字體
        self.font_main = ctk.CTkFont(family="Microsoft JhengHei", size=14)
        self.font_h1 = ctk.CTkFont(family="Microsoft JhengHei", size=24, weight="bold")
        self.font_console = ctk.CTkFont(family="Microsoft JhengHei", size=14)
        
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)
        self.sidebar_expanded = False

        # --- 1. 建立背景與容器 ---
        self.main_container = ctk.CTkFrame(self, fg_color="transparent")
        self.main_container.grid(row=0, column=0, sticky="nsew")
        self.main_container.grid_columnconfigure(0, weight=1)
        self.main_container.grid_rowconfigure(1, weight=1)

        self.topbar = ctk.CTkFrame(self.main_container, height=50, corner_radius=0, fg_color="transparent")
        self.topbar.grid(row=0, column=0, sticky="ew")
        self.btn_toggle_open = ctk.CTkButton(self.topbar, text="☰", width=40, font=self.font_h1, fg_color="transparent", hover_color="#333333", command=self.toggle_sidebar)
        self.btn_toggle_open.pack(side="left", padx=10, pady=10)

        self.page_container = ctk.CTkFrame(self.main_container, fg_color="transparent")
        self.page_container.grid(row=1, column=0, sticky="nsew")
        self.page_container.grid_columnconfigure(0, weight=1)
        self.page_container.grid_rowconfigure(0, weight=1)

        # --- 2. 實例化頁面 (Pages) ---
        self.frames = {}
        self.engine = TranslationEngine() 
        
        # 把 Engine 和 字體傳給 PageTranslate
        page_translate = PageTranslate(self.page_container, engine=self.engine, font_h1=self.font_h1, font_main=self.font_main, font_console=self.font_console)
        self.engine.set_callbacks(
            log_callback=page_translate.gui_log, 
            progress_callback=page_translate.gui_progress
            )
        self.frames["translate"] = page_translate
        
        # 補上 Callback 綁定 (讓 Engine 可以呼叫 page_translate 裡的 GUI 方法)
        self.engine.log = page_translate.gui_log
        self.engine.update_progress = page_translate.gui_progress

        # 建立 PageAdjust (它目前不需要 engine，只需字體)
        page_adjust = PageAdjust(self.page_container, font_h1=self.font_h1, font_main=self.font_main)
        self.frames["adjust"] = page_adjust

        # --- 3. 建立側邊欄與初始狀態 ---
        self._build_navigation_sidebar()
        self.show_page("translate")
        
        # 檢查 API 狀態 (透過呼叫 page_translate 提供的方法更新介面)
        is_ready = self.engine.initialize_groq()
        page_translate.set_api_status(is_ready)

    # ==========================================
    # 📍 導覽側邊欄 (Overlay 覆蓋層) (維持不變)
    # ==========================================
    def _build_navigation_sidebar(self):
        self.sidebar = ctk.CTkFrame(self, width=220, corner_radius=0, fg_color="#2b2b2b") 
        self.sidebar.place(x=-250, y=0, relheight=1.0) 
        self.sidebar.grid_propagate(False)

        self.header_frame = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        self.header_frame.pack(fill="x", padx=10, pady=(20, 30))
        
        self.btn_toggle_close = ctk.CTkButton(self.header_frame, text="✕", width=40, font=self.font_h1, fg_color="transparent", hover_color="#444444", command=self.toggle_sidebar)
        self.btn_toggle_close.pack(side="left")
        self.lbl_title = ctk.CTkLabel(self.header_frame, text="導覽選單", font=ctk.CTkFont(family="Microsoft JhengHei", size=20, weight="bold"))
        self.lbl_title.pack(side="left", padx=10)

        self.btn_nav_translate = ctk.CTkButton(self.sidebar, text="翻譯介面", font=self.font_main, fg_color="transparent", hover_color="#444444", anchor="w", command=lambda: self.nav_to_page("translate"))
        self.btn_nav_translate.pack(fill="x", padx=10, pady=5)
        self.btn_nav_adjust = ctk.CTkButton(self.sidebar, text="調整&檢查", font=self.font_main, fg_color="transparent", hover_color="#444444", anchor="w", command=lambda: self.nav_to_page("adjust"))
        self.btn_nav_adjust.pack(fill="x", padx=10, pady=5)

    def toggle_sidebar(self):
        if self.sidebar_expanded:
            self.sidebar.place_configure(x=-250)
            self.sidebar_expanded = False
        else:
            self.sidebar.place_configure(x=0)
            self.sidebar.lift() 
            self.sidebar_expanded = True

    def nav_to_page(self, page_name):
        self.show_page(page_name)
        self.toggle_sidebar()

    def show_page(self, page_name):
        for frame in self.frames.values():
            frame.grid_remove()
        self.frames[page_name].grid(row=0, column=0, sticky="nsew")
        
        active_color = "#1f538d"
        inactive_color = "transparent"
        self.btn_nav_translate.configure(fg_color=active_color if page_name == "translate" else inactive_color)
        self.btn_nav_adjust.configure(fg_color=active_color if page_name == "adjust" else inactive_color)


if __name__ == "__main__":
    app = AnimeTranslatorApp()
    app.mainloop()