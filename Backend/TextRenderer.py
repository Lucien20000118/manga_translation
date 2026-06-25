from PIL import Image, ImageDraw, ImageFont

class TextRenderer:
    def __init__(self, font_path="C:/Windows/Fonts/msjh.ttc"):
        # 預設使用微軟正黑體。若是 Mac 用戶，請改為 "/System/Library/Fonts/PingFang.ttc"
        self.font_path = font_path

    def get_text_dimensions(self, text, font):
        """測量文字在特定字體下的寬度與高度"""
        left, top, right, bottom = font.getbbox(text)
        width = right - left
        height = bottom - top
        return width, height

    def wrap_text_chinese(self, text, font, max_width):
        """支援手動換行 (\n) 與中文字元自動換行的演算法"""
        lines = []
        paragraphs = text.split('\n') # 1. 尊重原有的換行符號

        for paragraph in paragraphs:
            current_line = ""
            for char in paragraph:
                # 2. 逐字測試是否會超出最大寬度
                test_line = current_line + char
                w, _ = self.get_text_dimensions(test_line, font)

                if w <= max_width:
                    current_line = test_line
                else:
                    if current_line:
                        lines.append(current_line)
                    current_line = char
            
            # 處理該段落剩下的最後一行
            if current_line:
                lines.append(current_line)
            elif not paragraph:
                # 保留連續換行的空行
                lines.append("") 

        return lines

    def draw_centered_text(self, pil_image, text, safe_box, font_size=20, text_color=(0, 0, 0)):
        """在安全框內繪製並自動置中文字"""
        draw = ImageDraw.Draw(pil_image)

        try:
            font = ImageFont.truetype(self.font_path, font_size)
        except IOError:
            print(f"⚠️ 找不到字體: {self.font_path}，使用預設字體")
            font = ImageFont.load_default()

        # 解析安全框座標
        x1, y1, x2, y2 = safe_box
        box_width = x2 - x1
        box_height = y2 - y1
        
        if box_width <= 0 or box_height <= 0:
            return pil_image # 避免異常極小框報錯

        # 執行斷行計算
        lines = self.wrap_text_chinese(text, font, box_width)

        # 計算高度以進行垂直置中
        line_spacing = int(font_size * 0.3) # 動態行距設定為字體的 30%
        _, single_line_height = self.get_text_dimensions("測", font) 
        total_text_height = (single_line_height * len(lines)) + (line_spacing * (len(lines) - 1))
        
        # 第一行的起始 Y 座標
        start_y = y1 + (box_height - total_text_height) / 2

        # 逐行繪製文字
        current_y = start_y
        for line in lines:
            if line:
                line_width, _ = self.get_text_dimensions(line, font)
                # 每行的起始 X 座標 (水平置中)
                start_x = x1 + (box_width - line_width) / 2
                draw.text((start_x, current_y), line, font=font, fill=text_color)
            
            current_y += single_line_height + line_spacing

        return pil_image
    
    def draw_vertical_text(self, pil_image, text, safe_box, font_size=20, text_color=(0, 0, 0)):
        """垂直排版：由右上到左下 (傳統日漫/繁中排版)"""
        draw = ImageDraw.Draw(pil_image)

        try:
            font = ImageFont.truetype(self.font_path, font_size)
        except IOError:
            print(f"⚠️ 找不到字體: {self.font_path}，使用預設字體")
            font = ImageFont.load_default()

        x1, y1, x2, y2 = safe_box
        box_width, box_height = x2 - x1, y2 - y1
        if box_width <= 0 or box_height <= 0: return pil_image

        # 抓取單一中文字的長寬 (直書排版通常字是正方形的)
        _, _, _, char_h = font.getbbox("測")
        char_w = char_h 
        line_spacing = int(font_size * 0.4) # 行距

        # 1. 垂直自動換行邏輯 (受限於高度 box_height)
        lines = []
        paragraphs = text.split('\n')
        
        for paragraph in paragraphs:
            current_line = ""
            for char in paragraph:
                # 測試加上這個字後，這行的高度會不會超過框的高度
                if (len(current_line) + 1) * char_h <= box_height:
                    current_line += char
                else:
                    if current_line: lines.append(current_line)
                    current_line = char
            
            if current_line: lines.append(current_line)
            elif not paragraph: lines.append("") # 保留手動空行

        # 2. 計算總寬度，準備由右至左繪製
        total_width = (len(lines) * char_w) + (line_spacing * (len(lines) - 1))
        
        # 第一行的 X 座標在最「右邊」
        start_x = x1 + (box_width - total_width) / 2 + (total_width - char_w)
        
        current_x = start_x
        for line in lines:
            # 垂直置中該行文字
            line_height = len(line) * char_h
            start_y = y1 + (box_height - line_height) / 2
            
            current_y = start_y
            for char in line:
                draw.text((current_x, current_y), char, font=font, fill=text_color)
                current_y += char_h # 往下畫下一個字
                
            current_x -= (char_w + line_spacing) # 換行時，X 座標往「左」移

        return pil_image