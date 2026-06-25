import os
import threading
import customtkinter as ctk
from tkinter import filedialog

class PageTranslate(ctk.CTkFrame):
    def __init__(self, master, engine, font_h1, font_main, font_console, **kwargs):
        # 初始化為一個透明的 Frame
        super().__init__(master, fg_color="transparent", **kwargs)
        
        self.engine = engine
        self.font_h1 = font_h1
        self.font_main = font_main
        self.font_console = font_console
        
        self.selected_path = ""
        
        # 設定這個頁面本身的佈局 (左控制 0, 右工作 1)
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self._build_ui()

    def _build_ui(self):
        # ==========================================
        # 左側設定區 (Column 0)
        # ==========================================
        settings_frame = ctk.CTkFrame(self, width=300, corner_radius=10)
        settings_frame.grid(row=0, column=0, padx=20, pady=0, sticky="nsew")
        
        ctk.CTkLabel(settings_frame, text="模型設定", font=self.font_h1).grid(row=0, column=0, columnspan=2, pady=(20, 20))

        # YOLO
        ctk.CTkLabel(settings_frame, text="1. YOLO 權重 (Repo ID):", font=self.font_main).grid(row=1, column=0, columnspan=2, padx=15, pady=(5, 0), sticky="w")
        self.yolo_entry = ctk.CTkEntry(settings_frame, placeholder_text="預設: ogkalu/...", font=self.font_main, width=180)
        self.yolo_entry.grid(row=2, column=0, padx=(15, 5), pady=5, sticky="w")
        self.btn_load_yolo = ctk.CTkButton(settings_frame, text="載入", width=60, font=self.font_main, command=self.load_yolo_thread)
        self.btn_load_yolo.grid(row=2, column=1, padx=(0, 15), pady=5)
        self.yolo_status = ctk.CTkLabel(settings_frame, text="🔴 尚未載入", text_color="#e74c3c", font=self.font_main)
        self.yolo_status.grid(row=3, column=0, columnspan=2, padx=15, sticky="w")

        # MOCR
        ctk.CTkLabel(settings_frame, text="2. MOCR 權重 (Repo ID):", font=self.font_main).grid(row=4, column=0, columnspan=2, padx=15, pady=(15, 0), sticky="w")
        self.mocr_entry = ctk.CTkEntry(settings_frame, placeholder_text="預設: kha-white/...", font=self.font_main, width=180)
        self.mocr_entry.grid(row=5, column=0, padx=(15, 5), pady=5, sticky="w")
        self.btn_load_mocr = ctk.CTkButton(settings_frame, text="載入", width=60, font=self.font_main, command=self.load_mocr_thread)
        self.btn_load_mocr.grid(row=5, column=1, padx=(0, 15), pady=5)
        self.mocr_status = ctk.CTkLabel(settings_frame, text="🔴 尚未載入", text_color="#e74c3c", font=self.font_main)
        self.mocr_status.grid(row=6, column=0, columnspan=2, padx=15, sticky="w")

        # LLM
        ctk.CTkLabel(settings_frame, text="3. 翻譯大腦 (Groq LLM):", font=self.font_main).grid(row=7, column=0, columnspan=2, padx=15, pady=(15, 0), sticky="w")
        self.llm_entry = ctk.CTkEntry(settings_frame, placeholder_text="預設: llama-3.1-8b-instant", font=self.font_main)
        self.llm_entry.grid(row=8, column=0, columnspan=2, padx=15, pady=5, sticky="ew")
        self.api_status = ctk.CTkLabel(settings_frame, text="檢查中...", font=self.font_main)
        self.api_status.grid(row=9, column=0, columnspan=2, padx=15, sticky="w")
        
        self.run_btn = ctk.CTkButton(settings_frame, text="🚀 開始翻譯", height=45, font=ctk.CTkFont(family="Microsoft JhengHei", size=16, weight="bold"), command=self.start_translation)
        self.run_btn.grid(row=10, column=0, columnspan=2, padx=15, pady=(30, 20), sticky="ew")

        # ==========================================
        # 右側工作區 (Column 1)
        # ==========================================
        work_frame = ctk.CTkFrame(self, fg_color="transparent")
        work_frame.grid(row=0, column=1, padx=(0, 20), pady=0, sticky="nsew")
        work_frame.grid_columnconfigure(0, weight=1)
        work_frame.grid_rowconfigure(2, weight=1)

        btn_frame = ctk.CTkFrame(work_frame, fg_color="transparent")
        btn_frame.grid(row=0, column=0, pady=(0, 10), sticky="ew")
        ctk.CTkButton(btn_frame, text="🖼️ 選擇單張", font=self.font_main, command=self.select_file).pack(side="left", padx=(0,10))
        ctk.CTkButton(btn_frame, text="📂 選擇資料夾", font=self.font_main, fg_color="#E67E22", hover_color="#D35400", command=self.select_folder).pack(side="left")

        self.path_display = ctk.CTkEntry(work_frame, font=self.font_main, state="readonly")
        self.path_display.grid(row=1, column=0, pady=(0, 10), sticky="ew")

        self.console = ctk.CTkTextbox(work_frame, font=self.font_console)
        self.console.grid(row=2, column=0, pady=(0, 10), sticky="nsew")
        
        self.progressbar = ctk.CTkProgressBar(work_frame)
        self.progressbar.grid(row=3, column=0, pady=(0, 0), sticky="ew")
        self.progressbar.set(0)

    # ==========================================
    # 邏輯與功能區 (專屬於這個頁面)
    # ==========================================
    def gui_log(self, text):
        self.after(0, lambda: self._insert_log(text))
        
    def _insert_log(self, text):
        self.console.insert("end", str(text) + "\n")
        self.console.see("end")

    def gui_progress(self, value):
        self.after(0, lambda: self.progressbar.set(value))
        
    def set_api_status(self, is_ready):
        if is_ready:
            self.api_status.configure(text="🟢 API Key 就緒", text_color="#2ecc71")
        else:
            self.api_status.configure(text="🔴 找不到 API Key", text_color="#e74c3c")
            self.run_btn.configure(state="disabled")

    def select_file(self):
        path = filedialog.askopenfilename(filetypes=[("圖片檔案", "*.png *.jpg *.jpeg")])
        if path: self._update_path(path)

    def select_folder(self):
        path = filedialog.askdirectory()
        if path: self._update_path(path)

    def _update_path(self, path):
        self.selected_path = path
        self.path_display.configure(state="normal")
        self.path_display.delete(0, "end")
        self.path_display.insert(0, path)
        self.path_display.configure(state="readonly")
        self.gui_log(f"📂 已選擇: {path}")

    # --- 載入與翻譯邏輯 (照搬原本的，但 self 指向這個類別) ---
    def load_yolo_thread(self):
        self.btn_load_yolo.configure(state="disabled")
        self.yolo_status.configure(text="🟡 載入中...", text_color="#f39c12")
        custom_model = self.yolo_entry.get().strip() 
        threading.Thread(target=self._load_yolo_task, args=(custom_model,), daemon=True).start()

    def _load_yolo_task(self, custom_model):
        try:
            self.engine.load_yolo(custom_model_name=custom_model)
            self.after(0, lambda: self.yolo_status.configure(text="🟢 已載入", text_color="#2ecc71"))
        except Exception as e:
            self.gui_log(f"錯誤: {e}")
            self.after(0, lambda: self.yolo_status.configure(text="🔴 失敗", text_color="#e74c3c"))
        finally:
            self.after(0, lambda: self.btn_load_yolo.configure(state="normal", text="重新載入"))

    def load_mocr_thread(self):
        self.btn_load_mocr.configure(state="disabled")
        self.mocr_status.configure(text="🟡 載入中...", text_color="#f39c12")
        custom_model = self.mocr_entry.get().strip()
        threading.Thread(target=self._load_mocr_task, args=(custom_model,), daemon=True).start()

    def _load_mocr_task(self, custom_model):
        try:
            self.engine.load_mocr(custom_model_name=custom_model)
            self.after(0, lambda: self.mocr_status.configure(text="🟢 已載入", text_color="#2ecc71"))
        except Exception as e:
            self.gui_log(f"錯誤: {e}")
            self.after(0, lambda: self.mocr_status.configure(text="🔴 失敗", text_color="#e74c3c"))
        finally:
            self.after(0, lambda: self.btn_load_mocr.configure(state="normal", text="重新載入"))

    def start_translation(self):
        if not self.engine.yolo_model or not self.engine.mocr_model:
            self.gui_log("⚠️ 請先載入模型！")
            return
        if not self.selected_path:
            self.gui_log("⚠️ 請選擇路徑！")
            return

        self.run_btn.configure(state="disabled", text="翻譯中...")
        self.progressbar.set(0)
        threading.Thread(target=self._run_translation_task, daemon=True).start()

    def _run_translation_task(self):
        model_name = self.llm_entry.get() or "llama-3.1-8b-instant"
        if os.path.isdir(self.selected_path):
            files = [os.path.join(self.selected_path, f) for f in os.listdir(self.selected_path) if f.lower().endswith(('.png', '.jpg', '.jpeg'))]
        else:
            files = [self.selected_path]
        try:
            self.engine.run_batch_translation(files, model_name)
        except Exception as e:
            self.gui_log(f"❌ 嚴重錯誤: {e}")
        finally:
            self.after(0, lambda: self.run_btn.configure(state="normal", text="🚀 開始翻譯"))