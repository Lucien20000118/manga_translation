import customtkinter as ctk
from tkinter import filedialog
from PIL import Image, ImageTk
import os
import json

# ==========================================
# 🧮 0. 獨立的數學與影像輔助函式 (Helper)
# ==========================================
def calculate_zoom_and_crop(orig_size, current_zoom, zoom_step, mouse_pos, container_size):
    orig_w, orig_h = orig_size
    cont_w, cont_h = container_size
    mouse_x, mouse_y = mouse_pos

    new_zoom = current_zoom + zoom_step
    new_zoom = max(0.1, min(5.0, new_zoom))
    if new_zoom == current_zoom: return current_zoom, None

    scale_ratio_fit = min(cont_w / orig_w, cont_h / orig_h)
    fit_w = int(orig_w * scale_ratio_fit)
    fit_h = int(orig_h * scale_ratio_fit)
    final_w = max(10, int(fit_w * new_zoom))
    final_h = max(10, int(fit_h * new_zoom))

    crop_box = None
    if final_w > cont_w or final_h > cont_h:
        img_x_offset = (cont_w - fit_w * current_zoom) / 2
        img_y_offset = (cont_h - fit_h * current_zoom) / 2
        rel_x = max(0.0, min(1.0, (mouse_x - img_x_offset) / (fit_w * current_zoom)))
        rel_y = max(0.0, min(1.0, (mouse_y - img_y_offset) / (fit_h * current_zoom)))
        left = -(mouse_x - (final_w * rel_x))
        top = -(mouse_y - (final_h * rel_y))
        left = max(0, min(final_w - cont_w, left))
        top = max(0, min(final_h - cont_h, top))
        crop_box = (int(left), int(top), int(left + cont_w), int(top + cont_h))
    return new_zoom, (final_w, final_h), crop_box

def orig_to_canvas_coords(box_coords, pan_x, pan_y, zoom_scale):
    x1 = pan_x + (box_coords["x1"] * zoom_scale)
    y1 = pan_y + (box_coords["y1"] * zoom_scale)
    x2 = pan_x + (box_coords["x2"] * zoom_scale)
    y2 = pan_y + (box_coords["y2"] * zoom_scale)
    return x1, y1, x2, y2

# ==========================================
# 🧠 1. UX 狀態與互動管理器 (Controller / Presenter)
# ==========================================
class AdjustUXManager:
    def __init__(self, page_view):
        self.page = page_view
        self.img_processor = None 
        self.init_ux_state()

    def init_ux_state(self):
        self.page.combo_images.configure(state="disabled")
        self.page.btn_erase.configure(state="disabled")
        self.page.btn_apply.configure(state="disabled")
        self.page.btn_export.configure(state="disabled")
        
        self.set_inspector_state(False) # 💡 初始化時強制鎖定所有編輯器

        self.raw_pil_img = None     
        self.clean_pil_img = None   
        self.tk_bg_cache = None    
        self.tk_text_caches = []
        self.last_zoom_scale = None
        self.last_bg_state = None 
        
        self.zoom_scale = 1.0       
        self.pan_x = 0              
        self.pan_y = 0              
        
        self.current_json_data = None 
        self.box_canvas_ids = {}      
        self.interaction_mode = None  
        self.active_box_idx = None 
        self.last_mouse_x = 0
        self.last_mouse_y = 0
        
        self.is_erased = False            
        self.is_translated_shown = False  
        self.block_style_updates = False  

        self.page.canvas.bind("<MouseWheel>", self.on_mouse_wheel)
        self.page.canvas.bind("<ButtonPress-1>", self.on_mouse_press)
        self.page.canvas.bind("<B1-Motion>", self.on_mouse_drag)
        self.page.canvas.bind("<ButtonRelease-1>", self.on_mouse_release)
        
        self.page.btn_erase.configure(command=self.toggle_erase_mode)
        self.page.btn_apply.configure(command=self.toggle_translation_mode)
        self.page.btn_export.configure(command=self.export_final_image)

    # 💡 核心新增：獨立管理「屬性檢查器」的鎖定與解鎖
    def set_inspector_state(self, is_active):
        """控制左側編輯面板的鎖定狀態"""
        entry_state = "normal" if is_active else "disabled"
        combo_state = "readonly" if is_active else "disabled"

        self.page.combo_size.configure(state=combo_state)
        self.page.combo_direction.configure(state=combo_state)
        self.page.entry_color.configure(state=entry_state)
        self.page.textbox_edit.configure(state=entry_state)

        # 當鎖定時，清空內容以避免幽靈狀態誤導使用者
        if not is_active:
            self.page.textbox_edit.delete("1.0", "end")
            self.page.entry_color.delete(0, "end")
            self.page.combo_size.set("選擇框框解鎖")
            self.page.combo_direction.set("選擇框框解鎖")

    def handle_folder_selected(self, folder_path):
        if not folder_path: return
        valid_ext = ('.png', '.jpg', '.jpeg')
        image_files = [f for f in os.listdir(folder_path) if f.lower().endswith(valid_ext)]
        if image_files:
            self.page.combo_images.configure(state="normal")
            self.page.combo_images.configure(values=image_files)
            self.page.combo_images.set(image_files[0])
            self.page.combo_images.configure(state="readonly")
            self.load_image_preview(os.path.join(folder_path, image_files[0]))
        else:
            self.init_ux_state()
            self.page.combo_images.configure(values=["無圖片"])
            self.page.combo_images.set("無圖片")

    def handle_image_changed(self, selected_filename):
        folder_path = self.page.entry_dataset.get().strip()
        if folder_path and selected_filename:
            self.load_image_preview(os.path.join(folder_path, selected_filename))

    def load_image_preview(self, img_path):
        if not os.path.exists(img_path): return
        
        self.page.canvas.delete("hint_text")
        self.raw_pil_img = Image.open(img_path)
        self.clean_pil_img = None
        self.active_box_idx = None
        self.last_zoom_scale = None 
        
        # 💡 載入新圖片時，強制鎖定面板
        self.set_inspector_state(False)
        
        self.is_erased = False
        self.is_translated_shown = False
        self.page.btn_erase.configure(text="✨ 1. 擦除原文", state="normal")
        self.page.btn_apply.configure(text="📝 2. 填上翻譯文字", state="disabled")
        self.page.btn_export.configure(state="disabled")
        
        base_name = os.path.splitext(os.path.basename(img_path))[0]
        json_path = os.path.join("data", f"{base_name}_result.json")
        if not os.path.exists(json_path):
            json_path = os.path.splitext(img_path)[0] + "_result.json"
            
        self.current_json_path = json_path 
            
        if os.path.exists(json_path):
            with open(json_path, 'r', encoding='utf-8') as f:
                self.current_json_data = json.load(f)
            
            needs_save = False
            cv_img = None
            if "text_boxes" in self.current_json_data:
                for box in self.current_json_data["text_boxes"]:
                    if "safe_box" in box and isinstance(box["safe_box"], list):
                        box["safe_box"] = {
                            "x1": box["safe_box"][0], "y1": box["safe_box"][1],
                            "x2": box["safe_box"][2], "y2": box["safe_box"][3]
                        }
                        needs_save = True

                    if "safe_box" not in box:
                        if cv_img is None:
                            import cv2, numpy as np
                            cv_img = cv2.cvtColor(np.array(self.raw_pil_img), cv2.COLOR_RGB2BGR)
                        if self.img_processor is None:
                            from Backend.image_processor import ImageProcessor
                            self.img_processor = ImageProcessor()
                        box["safe_box"] = self.img_processor.get_safe_text_box(cv_img, box["coordinates"])
                        needs_save = True
            if needs_save: self.save_current_json()
        else:
            self.current_json_data = None
            self.current_json_path = None
        
        self.page.canvas.update_idletasks()
        cw, ch = self.page.canvas.winfo_width(), self.page.canvas.winfo_height()
        if cw <= 1: cw, ch = 700, 500 
        orig_w, orig_h = self.raw_pil_img.size
        self.zoom_scale = min(cw / orig_w, ch / orig_h)
        self.pan_x = (cw - orig_w * self.zoom_scale) / 2
        self.pan_y = (ch - orig_h * self.zoom_scale) / 2
        
        self.render_canvas_all()

    # ----------------------------------------
    # 🖼️ 高效能圖層分離渲染引擎 
    # ----------------------------------------
    def on_text_edited(self, event=None):
        if self.active_box_idx is None: return
        box_idx = self.active_box_idx
        new_text = self.page.textbox_edit.get("1.0", "end-1c")
        self.current_json_data["text_boxes"][box_idx]["translated_text"] = new_text
        self.save_current_json()
        self.render_overlays() 

    def update_text_color_preview(self, event=None):
        if self.block_style_updates or self.active_box_idx is None: return
        
        box_data = self.current_json_data["text_boxes"][self.active_box_idx]
        
        # 💡 安全抓取數值，避免崩潰
        try:
            box_data["font_size"] = int(self.page.combo_size.get())
        except ValueError:
            pass
            
        hex_color = self.page.entry_color.get().strip()
        if len(hex_color) == 7 and hex_color.startswith('#'):
            box_data["font_color"] = hex_color
            
        box_data["direction"] = self.page.combo_direction.get()
        self.save_current_json()
        self.render_overlays()

    def render_background(self):
        if not self.raw_pil_img: return
        base_image = self.clean_pil_img if (self.is_erased and self.clean_pil_img) else self.raw_pil_img
        current_state = "clean" if (self.is_erased and self.clean_pil_img) else "raw"
        orig_w, orig_h = base_image.size
        new_w, new_h = max(10, int(orig_w * self.zoom_scale)), max(10, int(orig_h * self.zoom_scale))
        
        if getattr(self, "last_zoom_scale", None) != self.zoom_scale or getattr(self, "last_bg_state", None) != current_state or not self.tk_bg_cache:
            resized_img = base_image.resize((new_w, new_h), Image.Resampling.LANCZOS)
            self.tk_bg_cache = ImageTk.PhotoImage(resized_img)
            self.last_zoom_scale = self.zoom_scale
            self.last_bg_state = current_state
            
        self.page.canvas.delete("preview_img")
        self.page.canvas.create_image(self.pan_x, self.pan_y, anchor="nw", image=self.tk_bg_cache, tags="preview_img")
        self.page.canvas.tag_lower("preview_img")

    def render_overlays(self):
        self.page.canvas.delete("bbox")
        self.page.canvas.delete("text_preview")
        self.box_canvas_ids.clear()
        self.tk_text_caches = [] 
        
        if not self.current_json_data or "text_boxes" not in self.current_json_data:
            return

        from Backend.TextRenderer import TextRenderer
        renderer = TextRenderer()

        for idx, box_data in enumerate(self.current_json_data["text_boxes"]):
            coords = box_data.get("safe_box", box_data["coordinates"])
            if isinstance(coords, dict):
                x1, y1, x2, y2 = coords["x1"], coords["y1"], coords["x2"], coords["y2"]
            else:
                x1, y1, x2, y2 = coords[0], coords[1], coords[2], coords[3]
            
            cx1, cy1, cx2, cy2 = orig_to_canvas_coords(coords, self.pan_x, self.pan_y, self.zoom_scale)
            
            if self.is_translated_shown or (not self.is_translated_shown and self.active_box_idx == idx):
                text = box_data.get("translated_text", "")
                if text:
                    # 💡 邏輯地雷修復：完全與 UI 狀態脫鉤。預設使用系統安全值 16 / #1A1A1A
                    font_size = box_data.get("font_size", 16)
                    hex_color = box_data.get("font_color", "#1A1A1A")
                    direction = box_data.get("direction", "縱向呈現 (Vertical)")
                    
                    # 💡 型別崩潰防護：加入 try-except，就算 JSON 裡的色碼壞掉也不會當機
                    try:
                        rgb = tuple(int(hex_color.lstrip('#')[i:i+2], 16) for i in (0, 2, 4)) if (len(hex_color) == 7 and hex_color.startswith('#')) else (26, 26, 26)
                    except ValueError:
                        rgb = (26, 26, 26)
                        
                    rgba_text = rgb + (255,)
                    rgba_bg = rgb + (0,) 

                    box_w_orig = max(1, int(x2 - x1))
                    box_h_orig = max(1, int(y2 - y1))
                    
                    txt_layer = Image.new("RGBA", (box_w_orig, box_h_orig), rgba_bg)
                    local_safe_box = [0, 0, box_w_orig, box_h_orig]
                    
                    if "Vertical" in direction:
                        txt_layer = renderer.draw_vertical_text(txt_layer, text, local_safe_box, font_size, rgba_text)
                    else:
                        txt_layer = renderer.draw_centered_text(txt_layer, text, local_safe_box, font_size, rgba_text)
                    
                    canvas_w = max(1, int(box_w_orig * self.zoom_scale))
                    canvas_h = max(1, int(box_h_orig * self.zoom_scale))
                    resized_txt = txt_layer.resize((canvas_w, canvas_h), Image.Resampling.LANCZOS)
                    
                    tk_txt = ImageTk.PhotoImage(resized_txt)
                    self.tk_text_caches.append(tk_txt)
                    self.page.canvas.create_image(cx1, cy1, anchor="nw", image=tk_txt, tags=("text_preview", f"text_group_{idx}"))

            if self.active_box_idx is not None and idx == self.active_box_idx:
                outline_color = "#007AFF"
            else:
                outline_color = "" if self.is_translated_shown else "#FF3b30"
            
            rect_id = self.page.canvas.create_rectangle(
                cx1, cy1, cx2, cy2, outline=outline_color, width=4, fill="", 
                activeoutline="#34C759" if outline_color != "" else "", activewidth=6, tags=("bbox", f"box_{idx}")
            )
            self.box_canvas_ids[rect_id] = idx

    def render_canvas_all(self):
        self.render_background()
        self.render_overlays()

    # ----------------------------------------
    # 🖱️ 滑鼠操作與智慧屬性面板鎖定 (Lock Sync)
    # ----------------------------------------
    def on_mouse_press(self, event):
        if not self.raw_pil_img: return
        self.last_mouse_x, self.last_mouse_y = event.x, event.y

        old_active_idx = self.active_box_idx
        self.active_box_idx = None
        
        if self.current_json_data and "text_boxes" in self.current_json_data:
            for idx in range(len(self.current_json_data["text_boxes"]) - 1, -1, -1):
                box = self.current_json_data["text_boxes"][idx]
                coords = box.get("safe_box", box["coordinates"])
                cx1, cy1, cx2, cy2 = orig_to_canvas_coords(coords, self.pan_x, self.pan_y, self.zoom_scale)
                
                if cx1 - 15 <= event.x <= cx2 + 15 and cy1 - 15 <= event.y <= cy2 + 15:
                    self.active_box_idx = idx
                    break

        if self.active_box_idx is not None:
            box_idx = self.active_box_idx
            box_data = self.current_json_data["text_boxes"][box_idx]
            
            # ==========================================
            # 💡 核心變更：找到框框！解鎖面板並寫入專屬數據
            # ==========================================
            self.set_inspector_state(True) 
            self.block_style_updates = True  # 鎖定寫入事件，避免觸發迴圈
            
            text = box_data.get("translated_text", "")
            self.page.textbox_edit.delete("1.0", "end")
            self.page.textbox_edit.insert("1.0", text)
            
            self.page.combo_size.set(str(box_data.get("font_size", 16)))
            self.page.entry_color.delete(0, "end")
            self.page.entry_color.insert(0, box_data.get("font_color", "#1A1A1A"))
            self.page.combo_direction.set(box_data.get("direction", "縱向呈現 (Vertical)"))
                
            self.block_style_updates = False 
            
            cx1, cy1, cx2, cy2 = orig_to_canvas_coords(box_data.get("safe_box", box_data["coordinates"]), self.pan_x, self.pan_y, self.zoom_scale)
            margin_x = min(15, (cx2 - cx1) / 3)
            margin_y = min(15, (cy2 - cy1) / 3)
            
            on_left = abs(event.x - cx1) <= margin_x
            on_right = abs(event.x - cx2) <= margin_x
            on_top = abs(event.y - cy1) <= margin_y
            on_bottom = abs(event.y - cy2) <= margin_y
            
            if on_left and on_top:
                self.interaction_mode = "resize_nw"
                self.page.canvas.config(cursor="size_nw_se")
            elif on_right and on_bottom:
                self.interaction_mode = "resize_se"
                self.page.canvas.config(cursor="size_nw_se")
            elif on_left and on_bottom:
                self.interaction_mode = "resize_sw"
                self.page.canvas.config(cursor="size_ne_sw")
            elif on_right and on_top:
                self.interaction_mode = "resize_ne"
                self.page.canvas.config(cursor="size_ne_sw")
            elif on_left:
                self.interaction_mode = "resize_w"
                self.page.canvas.config(cursor="sb_h_double_arrow")
            elif on_right:
                self.interaction_mode = "resize_e"
                self.page.canvas.config(cursor="sb_h_double_arrow")
            elif on_top:
                self.interaction_mode = "resize_n"
                self.page.canvas.config(cursor="sb_v_double_arrow")
            elif on_bottom:
                self.interaction_mode = "resize_s"
                self.page.canvas.config(cursor="sb_v_double_arrow")
            else:
                self.interaction_mode = "drag_box"
                self.page.canvas.config(cursor="fleur")
                
            self.render_overlays()
        else:
            # ==========================================
            # 💡 核心變更：點擊空白處！強制鎖定面板並清空數值
            # ==========================================
            self.set_inspector_state(False)
            
            self.interaction_mode = "pan_image"
            self.page.canvas.config(cursor="fleur")
            if old_active_idx is not None:
                self.render_overlays()

    def on_mouse_drag(self, event):
        if not self.interaction_mode: return
        dx, dy = event.x - self.last_mouse_x, event.y - self.last_mouse_y
        self.last_mouse_x, self.last_mouse_y = event.x, event.y

        if self.interaction_mode == "pan_image":
            self.pan_x += dx
            self.pan_y += dy
            self.render_canvas_all()

        elif self.interaction_mode.startswith("drag_") or self.interaction_mode.startswith("resize_"):
            box_idx = self.active_box_idx
            if box_idx is None: return
            
            box_coords = self.current_json_data["text_boxes"][box_idx].get("safe_box", self.current_json_data["text_boxes"][box_idx]["coordinates"])
            min_size = 10 / self.zoom_scale 
            dx_orig = dx / self.zoom_scale
            dy_orig = dy / self.zoom_scale
            
            if self.interaction_mode == "drag_box":
                box_coords["x1"] += dx_orig
                box_coords["x2"] += dx_orig
                box_coords["y1"] += dy_orig
                box_coords["y2"] += dy_orig
            else:
                mode = self.interaction_mode.split('_')[-1]
                if "w" in mode: 
                    if box_coords["x1"] + dx_orig <= box_coords["x2"] - min_size:
                        box_coords["x1"] += dx_orig
                if "e" in mode: 
                    if box_coords["x2"] + dx_orig >= box_coords["x1"] + min_size:
                        box_coords["x2"] += dx_orig
                if "n" in mode: 
                    if box_coords["y1"] + dy_orig <= box_coords["y2"] - min_size:
                        box_coords["y1"] += dy_orig
                if "s" in mode: 
                    if box_coords["y2"] + dy_orig >= box_coords["y1"] + min_size:
                        box_coords["y2"] += dy_orig
                
            self.render_overlays() 

    def on_mouse_release(self, event):
        if self.interaction_mode and (self.interaction_mode.startswith("drag_") or self.interaction_mode.startswith("resize_")):
            self.save_current_json()
            self.render_overlays()
        self.interaction_mode = None
        self.page.canvas.config(cursor="arrow")

    def on_mouse_wheel(self, event):
        if not (event.state & 0x0004) or not self.raw_pil_img: return 
        zoom_step = 0.1 if event.delta > 0 else -0.1
        new_zoom = max(0.05, min(5.0, self.zoom_scale + zoom_step))
        if new_zoom == self.zoom_scale: return
        mouse_x, mouse_y = event.x, event.y
        scale_ratio = new_zoom / self.zoom_scale
        self.pan_x = mouse_x - (mouse_x - self.pan_x) * scale_ratio
        self.pan_y = mouse_y - (mouse_y - self.pan_y) * scale_ratio
        self.zoom_scale = new_zoom
        self.render_canvas_all()

    # ----------------------------------------
    # ⚙️ Pipeline Functions (按鈕狀態與邏輯)
    # ----------------------------------------
    def toggle_erase_mode(self):
        if not self.raw_pil_img or not self.current_json_data: return

        if self.is_erased:
            self.is_erased = False
            self.is_translated_shown = False 
            
            self.page.btn_erase.configure(text="✨ 1. 擦除原文")
            self.page.btn_apply.configure(text="📝 2. 填上翻譯文字", state="disabled")
            self.page.btn_export.configure(state="disabled")
            self.render_canvas_all()
        else:
            self.page.btn_erase.configure(text="⏳ 正在擦除文字...", state="disabled")
            self.page.after(100, self._process_inpainting_task)

    def _process_inpainting_task(self):
        try:
            if not self.clean_pil_img: 
                if self.img_processor is None:
                    self.page.btn_erase.configure(text="⏳ 載入修補模型中...")
                    self.page.update()
                    from Backend.image_processor import ImageProcessor 
                    self.img_processor = ImageProcessor()

                boxes = [box["coordinates"] for box in self.current_json_data["text_boxes"]]
                self.page.btn_erase.configure(text="⏳ 正在處理影像...")
                self.page.update()

                self.clean_pil_img = self.img_processor.process_all_text_boxes(self.raw_pil_img, boxes)

            self.is_erased = True
            self.page.btn_erase.configure(text="✨ 1. 復原原文", state="normal")
            self.page.btn_apply.configure(state="normal")
            self.page.btn_export.configure(state="normal")
            self.render_canvas_all()
        except Exception as e:
            print(f"擦除文字失敗: {e}")
            self.page.btn_erase.configure(text="✨ 1. 擦除原文", state="normal")

    def toggle_translation_mode(self):
        if not self.is_erased: return
            
        if self.is_translated_shown:
            self.is_translated_shown = False
            self.page.btn_apply.configure(text="📝 2. 填上翻譯文字")
        else:
            self.is_translated_shown = True
            self.page.btn_apply.configure(text="📝 2. 消除翻譯文字")
            
        self.render_overlays()

    def export_final_image(self):
        if not self.is_erased or not self.clean_pil_img:
            print("⚠️ 請先進行擦除與翻譯！")
            return

        export_dir = "Export"
        if not os.path.exists(export_dir):
            os.makedirs(export_dir)

        from Backend.TextRenderer import TextRenderer
        renderer = TextRenderer()
        final_image = self.clean_pil_img.copy()

        for box_data in self.current_json_data.get("text_boxes", []):
            text = box_data.get("translated_text", "")
            if not text: continue
            
            # 💡 導出時也脫離對 UI 面板的依賴，絕對安全
            font_size = box_data.get("font_size", 16)
            hex_color = box_data.get("font_color", "#1A1A1A")
            direction = box_data.get("direction", "縱向呈現 (Vertical)")
            
            try:
                rgb = tuple(int(hex_color.lstrip('#')[i:i+2], 16) for i in (0, 2, 4)) if (len(hex_color) == 7 and hex_color.startswith('#')) else (26, 26, 26)
            except ValueError:
                rgb = (26, 26, 26)

            safe_box = box_data.get("safe_box", box_data["coordinates"])
            if isinstance(safe_box, dict):
                safe_box = [safe_box["x1"], safe_box["y1"], safe_box["x2"], safe_box["y2"]]

            if "Vertical" in direction:
                final_image = renderer.draw_vertical_text(final_image, text, safe_box, font_size, rgb)
            else:
                final_image = renderer.draw_centered_text(final_image, text, safe_box, font_size, rgb)

        base_name = os.path.splitext(os.path.basename(self.current_json_path))[0].replace("_result", "")
        export_path = os.path.join(export_dir, f"{base_name}_translated.png")
        final_image.save(export_path)
        print(f"✨ 匯出成功！檔案已儲存至: {export_path}")

    def save_current_json(self):
        if self.current_json_data and hasattr(self, 'current_json_path'):
            try:
                with open(self.current_json_path, 'w', encoding='utf-8') as f:
                    json.dump(self.current_json_data, f, ensure_ascii=False, indent=4)
            except Exception as e:
                print(f"❌ 儲存 JSON 失敗: {e}")

# ==========================================
# 🖼️ 2. UI 畫面配置器 (View)
# ==========================================
class PageAdjust(ctk.CTkFrame):
    def __init__(self, master, font_h1, font_main, **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)
        self.font_h1 = font_h1
        self.font_main = font_main
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)
        self._build_ui()
        self.ux_manager = AdjustUXManager(self)

    def _build_ui(self):
        control_frame = ctk.CTkScrollableFrame(self, width=320, corner_radius=10)
        control_frame.grid(row=0, column=0, padx=15, pady=10, sticky="nsew")

        ctk.CTkLabel(control_frame, text="調整與檢查", font=self.font_h1).pack(pady=(10, 20))

        ctk.CTkLabel(control_frame, text="1. Dataset (資料夾) 位置:", font=self.font_main).pack(anchor="w", padx=10)
        folder_frame = ctk.CTkFrame(control_frame, fg_color="transparent")
        folder_frame.pack(fill="x", padx=10, pady=(5, 15))
        self.entry_dataset = ctk.CTkEntry(folder_frame, placeholder_text="請選擇資料夾...", font=self.font_main)
        self.entry_dataset.pack(side="left", fill="x", expand=True)
        self.btn_select_folder = ctk.CTkButton(folder_frame, text="📂", width=40, font=self.font_main, command=self._on_folder_btn_click)
        self.btn_select_folder.pack(side="left", padx=(5, 0))

        ctk.CTkLabel(control_frame, text="2. 選擇圖片:", font=self.font_main).pack(anchor="w", padx=10)
        self.combo_images = ctk.CTkComboBox(control_frame, values=["請先選擇 Dataset"], font=self.font_main, command=lambda c: self.ux_manager.handle_image_changed(c))
        self.combo_images.pack(fill="x", padx=10, pady=(5, 15))

        ctk.CTkLabel(control_frame, text="3. 調整字體大小 (6-48px):", font=self.font_main).pack(anchor="w", padx=10)
        self.combo_size = ctk.CTkComboBox(control_frame, values=[str(i) for i in range(6, 49)], font=self.font_main, justify="center")
        self.combo_size.pack(fill="x", padx=10, pady=(5, 15))

        ctk.CTkLabel(control_frame, text="4. 字體顏色 (Hex Code):", font=self.font_main).pack(anchor="w", padx=10)
        self.entry_color = ctk.CTkEntry(control_frame, font=self.font_main)
        self.entry_color.pack(fill="x", padx=10, pady=(5, 15))

        ctk.CTkLabel(control_frame, text="5. 排版方向:", font=self.font_main).pack(anchor="w", padx=10)
        self.combo_direction = ctk.CTkComboBox(control_frame, values=["橫向呈現 (Horizontal)", "縱向呈現 (Vertical)"], font=self.font_main)
        self.combo_direction.pack(fill="x", padx=10, pady=(5, 15))

        ctk.CTkLabel(control_frame, text="6. 編輯翻譯文字 (點擊右側框):", font=self.font_main).pack(anchor="w", padx=10)
        self.textbox_edit = ctk.CTkTextbox(control_frame, height=100, font=self.font_main)
        self.textbox_edit.pack(fill="x", padx=10, pady=(5, 25))
        
        self.textbox_edit.bind("<KeyRelease>", lambda e: self.ux_manager.on_text_edited(e))
        self.entry_color.bind("<KeyRelease>", lambda e: self.ux_manager.update_text_color_preview(e))
        self.combo_direction.configure(command=lambda e: self.ux_manager.update_text_color_preview(e))
        self.combo_size.configure(command=lambda e: self.ux_manager.update_text_color_preview(e))

        self.btn_erase = ctk.CTkButton(control_frame, text="✨ 1. 擦除原文", height=45, font=ctk.CTkFont(family="Microsoft JhengHei", size=16, weight="bold"))
        self.btn_erase.pack(fill="x", padx=10, pady=(0, 10))
        
        self.btn_apply = ctk.CTkButton(control_frame, text="📝 2. 填上翻譯文字", state="disabled", height=45, fg_color="#E67E22", hover_color="#D35400", font=ctk.CTkFont(family="Microsoft JhengHei", size=16, weight="bold"))
        self.btn_apply.pack(fill="x", padx=10, pady=(0, 10))

        self.btn_export = ctk.CTkButton(control_frame, text="📥 3. 匯出成品", state="disabled", height=45, fg_color="#27ae60", hover_color="#2ecc71", font=ctk.CTkFont(family="Microsoft JhengHei", size=16, weight="bold"))
        self.btn_export.pack(fill="x", padx=10, pady=(0, 20))

        preview_frame = ctk.CTkFrame(self, fg_color="#1E1E1E", corner_radius=10)
        preview_frame.grid(row=0, column=1, padx=(0, 15), pady=10, sticky="nsew")
        preview_frame.grid_columnconfigure(0, weight=1)
        preview_frame.grid_rowconfigure(0, weight=1)

        self.canvas = ctk.CTkCanvas(preview_frame, bg="#1E1E1E", highlightthickness=0)
        self.canvas.grid(row=0, column=0, sticky="nsew", padx=2, pady=2)
        self.canvas.create_text(350, 250, text="請從左側選擇 Dataset 並挑選圖片", fill="gray", font=("Microsoft JhengHei", 14), tags="hint_text")

    def _on_folder_btn_click(self):
        folder_path = filedialog.askdirectory()
        if folder_path:
            self.entry_dataset.configure(state="normal")
            self.entry_dataset.delete(0, "end")
            self.entry_dataset.insert(0, folder_path)
            self.ux_manager.handle_folder_selected(folder_path)