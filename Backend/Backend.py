
import os
import cv2
import json
import re
import numpy as np
from datetime import datetime
from PIL import Image
from dotenv import load_dotenv
from groq import Groq

import torch
from mobile_sam import sam_model_registry, SamPredictor


class TranslationEngine:
    def __init__(self):
        # 預設的回呼函式 (避免前端還沒綁定時，後端執行會報錯)
        self._log_callback = print
        self._progress_callback = lambda x: None
        
        self.yolo_model = None
        self.mocr_model = None
        self.groq_client = None

    def set_callbacks(self, log_callback, progress_callback):
        """
        提供給前端使用的 Setter 方法。
        前端準備好之後，呼叫這個方法把自己的 UI 更新函式綁定過來。
        """
        if log_callback:
            self._log_callback = log_callback
        if progress_callback:
            self._progress_callback = progress_callback

    def initialize_groq(self):
        """初始化 API Key"""
        load_dotenv()
        key = os.getenv("GROQ_API_KEY")
        if key:
            self.groq_client = Groq(api_key=key)
            return True
        return False

    def load_yolo(self, custom_model_name=""):
        from ultralytics import YOLO
        from huggingface_hub import hf_hub_download
        self.log("⏳ [Backend] 正在載入 YOLO 模型...")
        base_dir = "local_models"
        os.makedirs(base_dir, exist_ok=True)
        
        # 決定要使用的模型 ID 和檔名
        repo_id = custom_model_name if custom_model_name else "ogkalu/comic-speech-bubble-detector-yolov8m"
        filename = "comic-speech-bubble-detector.pt" # 這裡假設自訂模型也是這個檔名，如果不同需要另外處理
        
        yolo_path = os.path.join(base_dir, filename)
        
        # 為了支援自訂模型，如果檔名不存在或是自訂模型，就強制去下載
        if not os.path.exists(yolo_path) or custom_model_name:
            self.log(f"☁️ 正在從雲端下載 YOLO 權重: {repo_id} ...")
            try:
                hf_hub_download(repo_id=repo_id, filename=filename, local_dir=base_dir)
            except Exception as e:
                raise Exception(f"下載模型失敗，請確認 Hugging Face Repo ID 是否正確: {e}")
            
        self.yolo_model = YOLO(yolo_path)
        self.log(f"✅ [Backend] YOLO 模型 ({repo_id}) 載入成功！")
        return True

    def load_mocr(self, custom_model_name=""):
        import transformers
        transformers.logging.set_verbosity_error() 
        from manga_ocr import MangaOcr
        from huggingface_hub import snapshot_download
        self.log("⏳ [Backend] 正在載入 Manga-OCR 模型...")
        base_dir = "local_models"
        os.makedirs(base_dir, exist_ok=True)
        
        repo_id = custom_model_name if custom_model_name else "kha-white/manga-ocr-base"
        mocr_path = os.path.join(base_dir, repo_id.replace("/", "_")) # 避免路徑衝突
        
        if not os.path.exists(mocr_path) or custom_model_name:
            self.log(f"☁️ 正在從雲端下載 Manga-OCR 權重: {repo_id} ...")
            try:
                snapshot_download(repo_id=repo_id, local_dir=mocr_path)
            except Exception as e:
                 raise Exception(f"下載模型失敗，請確認 Hugging Face Repo ID 是否正確: {e}")
            
        self.mocr_model = MangaOcr(pretrained_model_name_or_path=mocr_path)
        self.log(f"✅ [Backend] Manga-OCR 模型 ({repo_id}) 載入成功！")
        return True

    def run_batch_translation(self, image_files, model_name):
        """核心批次處理邏輯 (不含任何 GUI 互動)"""
        os.makedirs("data", exist_ok=True)
        total_images = len(image_files)

        for img_idx, img_path in enumerate(image_files):
            self.log(f"\n📁 正在處理 [{img_idx+1}/{total_images}]: {os.path.basename(img_path)}")
            
            image = cv2.imread(img_path)
            image_rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
            img_height, img_width, _ = image.shape
            
            results = self.yolo_model(image_rgb, verbose=False)
            boxes = results[0].boxes.xyxy.cpu().numpy()
            
            if len(boxes) == 0:
                self.log("  ↳ ⚠️ 未偵測到對話框，跳過。")
                continue

            extracted_data = []
            for i, box in enumerate(boxes):
                x1, y1, x2, y2 = map(int, box)
                x1, y1, x2, y2 = max(0, x1), max(0, y1), min(img_width, x2), min(img_height, y2)
                cropped = image_rgb[y1:y2, x1:x2]
                if cropped.size == 0: continue
                
                jp_text = self.mocr_model(Image.fromarray(cropped))
                extracted_data.append({
                    "id": i + 1, "box": {"x1": x1, "y1": y1, "x2": x2, "y2": y2},
                    "jp_text": jp_text, "ch_text": ""
                })

            # LLM 批次翻譯 (每 5 個一組)
            BATCH_SIZE = 5
            for i in range(0, len(extracted_data), BATCH_SIZE):
                chunk = extracted_data[i:i + BATCH_SIZE]
                prompt_text = "\n".join([f"[{item['id']}] {item['jp_text']}" for item in chunk])
                sys_prompt = "你是台灣動漫翻譯家。翻譯以下標有編號的日文台詞。只能保留編號與中文翻譯，如：[1] 中文翻譯"
                
                try:
                    res = self.groq_client.chat.completions.create(
                        messages=[{"role": "system", "content": sys_prompt}, {"role": "user", "content": prompt_text}],
                        model=model_name, temperature=0.3
                    )
                    
                    for line in res.choices[0].message.content.strip().split('\n'):
                        match = re.match(r'\[(\d+)\]\s*(.*)', line.strip())
                        if match:
                            box_id, trans_text = int(match.group(1)), match.group(2)
                            for item in chunk:
                                if item["id"] == box_id:
                                    item["ch_text"] = trans_text
                                    self.log(f"  ↳ [框 #{box_id}] {trans_text}")
                except Exception as e:
                    self.log(f"  ↳ ❌ 批次翻譯失敗: {e}")

            # 存檔
            json_data = {
                "source": os.path.basename(img_path),
                "image_size": {"width": img_width, "height": img_height},
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "models": {"llm": model_name},
                "text_boxes": [{"id": d["id"], "coordinates": d["box"], "original_text": d["jp_text"], "translated_text": d["ch_text"]} for d in extracted_data]
            }
            
            base_name = os.path.splitext(os.path.basename(img_path))[0]
            json_path = os.path.join("data", f"{base_name}_result.json")
            with open(json_path, 'w', encoding='utf-8') as f:
                json.dump(json_data, f, ensure_ascii=False, indent=4)
                
            self.log(f"💾 已儲存至: {json_path}")
            self.update_progress((img_idx + 1) / total_images) # 通知 GUI 更新進度條

        self.log("\n✨ 批次處理完畢！")
        





