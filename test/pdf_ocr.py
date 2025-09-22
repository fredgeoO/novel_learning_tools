import pymupdf as fitz
import pytesseract
from PIL import Image
import io
import os
import numpy as np


class TextExtractor:
    def __init__(self):
        self.tesseract_available = False
        self.setup_tesseract()

    def setup_tesseract(self):
        """
        设置并检测Tesseract OCR
        """
        try:
            pytesseract.get_tesseract_version()
            self.tesseract_available = True
            print("✓ Tesseract OCR 可用")
        except Exception as e:
            print(f"✗ Tesseract OCR 不可用: {e}")
            # Windows用户可能需要手动设置路径
            windows_tesseract_paths = [
                r"C:\Program Files\Tesseract-OCR\tesseract.exe",
                r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe"
            ]

            for path in windows_tesseract_paths:
                if os.path.exists(path):
                    try:
                        pytesseract.pytesseract.tesseract_cmd = path
                        pytesseract.get_tesseract_version()
                        self.tesseract_available = True
                        print(f"✓ 找到Tesseract: {path}")
                        break
                    except:
                        continue

            if not self.tesseract_available:
                print("⚠️  将在无OCR模式下运行")

    def get_ocr_languages(self):
        """
        获取OCR语言参数
        """
        if not self.tesseract_available:
            return 'eng'

        try:
            available_langs = pytesseract.get_languages()
            if 'chi_sim' in available_langs:
                return 'chi_sim+eng'
            elif 'chi_tra' in available_langs:
                return 'chi_tra+eng'
            else:
                return 'eng'
        except:
            return 'chi_sim+eng'

    def extract_text_from_pdf(self, input_pdf, output_txt, max_pages=None):
        """
        从PDF中提取纯文本并保存为TXT文件
        """
        print(f"从PDF提取文本: {input_pdf}")
        print(f"输出文件: {output_txt}")

        if not os.path.exists(input_pdf):
            print(f"错误: 文件不存在 {input_pdf}")
            return False

        try:
            doc = fitz.open(input_pdf)
            total_pages = len(doc)

            if max_pages:
                pages_to_process = min(max_pages, total_pages)
                print(f"处理前 {pages_to_process} 页 (总共 {total_pages} 页)")
            else:
                pages_to_process = total_pages
                print(f"处理全部 {total_pages} 页")

            full_text = ""
            chinese_chars_total = 0
            english_chars_total = 0

            for page_num in range(pages_to_process):
                if (page_num + 1) % 10 == 0 or pages_to_process <= 10:
                    print(f"处理第 {page_num + 1}/{pages_to_process} 页...")

                page = doc[page_num]

                if self.tesseract_available:
                    try:
                        # 使用高分辨率进行OCR
                        ocr_zoom = 4.0  # 288 DPI
                        ocr_mat = fitz.Matrix(ocr_zoom, ocr_zoom)
                        ocr_pix = page.get_pixmap(matrix=ocr_mat)
                        ocr_img_data = ocr_pix.tobytes("ppm")
                        ocr_image = Image.open(io.BytesIO(ocr_img_data))

                        # 执行OCR
                        text = pytesseract.image_to_string(ocr_image, lang=self.get_ocr_languages())

                        # 统计字符
                        chinese_chars = len([c for c in text if ord(c) > 127])
                        english_chars = len([c for c in text if c.isalpha() and ord(c) <= 127])
                        chinese_chars_total += chinese_chars
                        english_chars_total += english_chars

                        # 添加页面分隔符
                        full_text += f"\n{'=' * 50}\n"
                        full_text += f"第 {page_num + 1} 页\n"
                        full_text += f"{'=' * 50}\n"
                        full_text += text

                        if (page_num + 1) <= 3:  # 只显示前3页的预览
                            preview_lines = text.split('\n')[:5]
                            preview_text = '\n'.join(preview_lines)
                            print(f"  第 {page_num + 1} 页预览:")
                            print(f"    {preview_text[:100]}...")

                        ocr_pix = None
                        ocr_image = None

                    except Exception as e:
                        print(f"  第 {page_num + 1} 页OCR失败: {e}")
                        full_text += f"\n[第 {page_num + 1} 页OCR失败]\n"
                else:
                    full_text += f"\n[第 {page_num + 1} 页: 无OCR支持]\n"

            doc.close()

            # 保存文本文件
            with open(output_txt, 'w', encoding='utf-8') as f:
                f.write(full_text)

            print(f"\n文本提取完成:")
            print(f"- 处理页数: {pages_to_process}")
            print(f"- 输出文件: {output_txt}")
            print(f"- 中文字符: {chinese_chars_total}")
            print(f"- 英文字符: {english_chars_total}")
            print(f"- 总字符数: {len(full_text)}")

            # 显示文件大小
            file_size = os.path.getsize(output_txt) / 1024
            print(f"- 文件大小: {file_size:.2f} KB")

            return True

        except Exception as e:
            print(f"处理失败: {e}")
            return False

    def extract_first_n_pages_text(self, input_pdf, output_txt, pages=10):
        """
        提取前N页的文本
        """
        return self.extract_text_from_pdf(input_pdf, output_txt, max_pages=pages)

    def extract_all_text(self, input_pdf, output_txt):
        """
        提取全部文本
        """
        return self.extract_text_from_pdf(input_pdf, output_txt, max_pages=None)


# 简单使用函数
def extract_pdf_text(input_pdf, output_txt, pages=None):
    """
    提取PDF文本到TXT文件

    Args:
        input_pdf: 输入PDF文件路径
        output_txt: 输出TXT文件路径
        pages: 要处理的页数 (None表示全部页面)
    """
    extractor = TextExtractor()

    if pages:
        return extractor.extract_first_n_pages_text(input_pdf, output_txt, pages)
    else:
        return extractor.extract_all_text(input_pdf, output_txt)


# 使用示例
if __name__ == "__main__":
    input_file = "scanned_document.pdf"
    output_file = "extracted_text.txt"

    print("开始提取PDF文本...")


    success = extract_pdf_text(input_file, output_file)

    if success:
        print(f"\n✅ 文本提取成功完成！")
        print(f"✅ 文件已保存: {output_file}")

        # 显示文件信息
        if os.path.exists(output_file):
            # 显示前500个字符作为预览
            with open(output_file, 'r', encoding='utf-8') as f:
                content = f.read()
                print(f"\n📄 文件预览 (前500字符):")
                print("-" * 50)
                print(content[:500])
                print("-" * 50)
                if len(content) > 500:
                    print("... (内容省略)")
    else:
        print(f"\n❌ 文本提取失败")