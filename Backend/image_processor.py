import cv2
import numpy as np
import torch
from PIL import Image
from mobile_sam import sam_model_registry, SamPredictor

class ImageProcessor:
    def __init__(self, sam_checkpoint="./local_models/mobile_sam.pt"):
        self.inpaint_radius = 3 
        # 1. 初始化 MobileSAM 模型
        model_type = "vit_t" # MobileSAM 使用的是最輕量的 Vision Transformer Tiny
        
        # 自動偵測是否可以使用 GPU，否則使用 CPU
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        
        sam = sam_model_registry[model_type](checkpoint=sam_checkpoint)
        sam.to(device=self.device)
        sam.eval() # 設定為推論模式
        
        self.predictor = SamPredictor(sam)

    def get_bubble_mask_with_sam(self, image_cv, box):
        """
        利用 MobileSAM，根據 YOLO 的矩形框 (Prompt) 預測出精準的對話框形狀 Mask。
        """
        # SAM 吃的是 RGB 格式，OpenCV 預設是 BGR，需要轉換
        image_rgb = cv2.cvtColor(image_cv, cv2.COLOR_BGR2RGB)
        
        # 將整張圖片設定進 SAM 的預測器
        self.predictor.set_image(image_rgb)
        
        # 將 YOLO 框轉換為 numpy array 格式作為 prompt
        # box 格式必須是: [x1, y1, x2, y2]
        input_box = np.array(box)
        
        # 進行預測
        masks, _, _ = self.predictor.predict(
            point_coords=None,
            point_labels=None,
            box=input_box[None, :],
            multimask_output=False, # 對話框通常是很明確的單一物件，我們只要一個最好的遮罩
        )
        
        # SAM 回傳的 mask 是 boolean array (True/False)，轉換成 OpenCV 可用的 uint8 (255/0)
        bubble_mask = (masks[0] * 255).astype(np.uint8)
        
        return bubble_mask

    def generate_text_mask(self, image_cv, x1, y1, x2, y2):
        """
        這裡放置我們之前討論過的 OpenCV 影像處理邏輯 (CLAHE + 銳化 + 大津二值化)。
        它會回傳一個粗略的文字遮罩 (可能會不小心吃到一些背景)。
        """
        h, w = image_cv.shape[:2]
        text_mask = np.zeros((h, w), dtype=np.uint8)
        
        cropped = image_cv[y1:y2, x1:x2]
        gray = cv2.cvtColor(cropped, cv2.COLOR_BGR2GRAY)
        
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        enhanced_gray = clahe.apply(gray)
        
        sharpen_kernel = np.array([[-1, -1, -1], [-1, 9, -1], [-1, -1, -1]])
        sharpened = cv2.filter2D(enhanced_gray, -1, sharpen_kernel)
        
        _, binary_mask = cv2.threshold(sharpened, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
        
        kernel = np.ones((3, 3), np.uint8) 
        dilated_mask = cv2.dilate(binary_mask, kernel, iterations=2)
        
        text_mask[y1:y2, x1:x2] = dilated_mask
        return text_mask

    def process_single_box(self, image_cv, box_dict):
        x1, y1, x2, y2 = int(box_dict['x1']), int(box_dict['y1']), int(box_dict['x2']), int(box_dict['y2'])
        box_coords = [x1, y1, x2, y2]
        
        # 1. 取得 SAM 生成的「完美對話框形狀遮罩」
        sam_bubble_mask = self.get_bubble_mask_with_sam(image_cv, box_coords)
        
        # ==========================================
        # 💡 新增：將 SAM 遮罩向內侵蝕 (Erosion)
        # ==========================================
        # 設定一個 5x5 的 kernel，這決定了內縮的厚度
        erode_kernel = np.ones((3, 3), np.uint8)
        # 讓 SAM 遮罩往內縮水，避開對話框邊線
        safe_sam_mask = cv2.erode(sam_bubble_mask, erode_kernel, iterations=2)
        # ==========================================

        # 2. 取得 OpenCV 生成的「文字筆劃遮罩」
        opencv_text_mask = self.generate_text_mask(image_cv, x1, y1, x2, y2)
        
        # 3. 交集操作 (Bitwise AND)：使用「內縮後」的 SAM 遮罩
        final_clean_mask = cv2.bitwise_and(opencv_text_mask, safe_sam_mask)
        
        return final_clean_mask

    def process_all_text_boxes(self, pil_image, boxes):
        cv_img = np.array(pil_image)
        if cv_img.shape[2] == 4:
            cv_img = cv2.cvtColor(cv_img, cv2.COLOR_RGBA2RGB)
            
        h, w = cv_img.shape[:2]
        combined_mask = np.zeros((h, w), dtype=np.uint8)
        
        # 迴圈處理 YOLO 抓到的每一個對話框
        for box in boxes:
            clean_box_mask = self.process_single_box(cv_img, box)
            combined_mask = cv2.bitwise_or(combined_mask, clean_box_mask)
            
        # 最後將乾淨的遮罩送入 Inpainting
        cleaned_cv_img = cv2.inpaint(cv_img, combined_mask, self.inpaint_radius, cv2.INPAINT_TELEA)
        return Image.fromarray(cleaned_cv_img)
    
    def get_safe_text_box_from_mask(self, sam_mask, scale=0.7):
        """
        從 SAM 的精準遮罩中，計算出適合填寫文字的「安全內接矩形」。
        scale: 內縮比例，0.7 是完美橢圓的內接比例。遇到較方正的框可以調高到 0.8，爆炸框可調低至 0.6。
        """
        # 1. 找出 SAM Mask 中所有白色像素 (對話框內部) 的座標
        coords = cv2.findNonZero(sam_mask)
        if coords is None:
            return None
        
        # 2. 取得 Mask 的絕對邊界框 (這會比 YOLO 框更緊密且去除多餘背景)
        x, y, w, h = cv2.boundingRect(coords)
        
        # 3. 計算內接矩形的寬高
        safe_w = int(w * scale)
        safe_h = int(h * scale)
        
        # 4. 計算中心點，並向外推算安全矩形的左上與右下座標
        center_x = x + w // 2
        center_y = y + h // 2
        
        safe_x1 = center_x - safe_w // 2
        safe_y1 = center_y - safe_h // 2
        safe_x2 = center_x + safe_w // 2
        safe_y2 = center_y + safe_h // 2
        
        return [safe_x1, safe_y1, safe_x2, safe_y2]
    
    def get_safe_text_box(self, image_cv, box_dict):
        """
        輸入 YOLO 框 (字典格式)，回傳安全的文字排版框 (字典格式)
        """
        x1, y1, x2, y2 = int(box_dict['x1']), int(box_dict['y1']), int(box_dict['x2']), int(box_dict['y2'])
        
        sam_mask = self.get_bubble_mask_with_sam(image_cv, [x1, y1, x2, y2])
        
        safe_box_list = self.get_safe_text_box_from_mask(sam_mask)
        

        if safe_box_list:
            return {
                "x1": safe_box_list[0], 
                "y1": safe_box_list[1], 
                "x2": safe_box_list[2], 
                "y2": safe_box_list[3]
            }
            
        return box_dict