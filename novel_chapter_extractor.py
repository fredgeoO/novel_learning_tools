#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
起点中文网小说章节爬虫

这是一个基于 Selenium 的自动化脚本，用于从起点中文网 (qidian.com) 下载指定小说的免费章节，
并将内容保存为本地 TXT 文件。

主要功能：
- 自动识别并下载小说的免费章节
- 智能解析网页中的 JSON 数据以获取章节正文
- 格式化章节内容并保存为 TXT 文件
- 支持断点续传：通过元数据文件记录已下载章节，避免重复下载
- 使用全局 Chrome 用户数据目录，减少浏览器指纹检测
- 可配置的下载参数（如最大章节数、等待时间等）

使用方法：
1. 在 novel_urls.txt 文件中按指定格式填入小说书名和 URL。
2. 运行脚本：python qidian_chapter_extractor.py
3. 爬取的章节将保存在 novels/小说名/ 目录下。

依赖：
- selenium
- ChromeDriver (需与 Chrome 浏览器版本匹配)

作者： FredgeoO
日期：2025
"""

import os
import re
import time
import tempfile
import atexit
import shutil
import json
import html
from urllib.parse import urljoin, urlparse
from typing import Tuple, Optional, Dict, Any, List

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import TimeoutException, WebDriverException
import logging

# --- 新增：导入工具模块 ---
import chapter_utils
# --- 新增结束 ---

# --- 配置 ---
# 日志配置
logging.basicConfig(level=logging.INFO, format='[%(asctime)s] [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

# 常量
SCRIPT_TAG_ID = "vite-plugin-ssr_pageContext"
SCRIPT_TAG_TYPE = "application/json"
CHAPTER_ITEM_SELECTOR = "li.chapter-item"
CHAPTER_LOCKED_SELECTOR = "em.iconfont.chapter-locked"
CHAPTER_LINK_SELECTOR = "a.chapter-name"
BOOK_NAME_ID = "bookName"
CHAPTER_CONTENT_CONTAINER_SELECTOR = "div.read-content.j_readContent"
CHAPTER_PARAGRAPH_SELECTOR = "p"
CHAPTER_TITLE_KEY_PATH = ["pageContext", "pageProps", "pageData", "chapterInfo", "chapterName"]
CHAPTER_CONTENT_KEY_PATH = ["pageContext", "pageProps", "pageData", "chapterInfo", "content"]

# --- 新增：章节状态常量 ---
# 注意：这些常量在主程序和 chapter_utils 中都需要保持一致。
# 为了简化，我们假设 chapter_utils 中也定义了它们，或者主程序直接使用字符串。
# 如果 chapter_utils 没有导出这些常量，主程序需要自己定义或使用字符串。
# 这里我们保留主程序的定义，确保主程序逻辑完整。
CHAPTER_STATUS_PENDING = "pending"
CHAPTER_STATUS_DOWNLOADED = "downloaded"
CHAPTER_STATUS_FAILED = "failed"
# --- 新增结束 ---


# --- 工具函数 ---
# sanitize_filename, get_nested_value, create_error_marker 函数保持不变
def sanitize_filename(title: str, index: int) -> str:
    """清理章节标题以生成安全的文件名。"""
    filename_safe_title = re.sub(r'[\\/:*?"<>|]', '_', title)
    if not filename_safe_title:
        filename_safe_title = f"未命名章节_{index + 1}"
    return f"{filename_safe_title}.txt"

def get_nested_value(data: Dict[str, Any], key_path: list) -> Any:
    """从嵌套字典中安全地获取值。"""
    for key in key_path:
        if isinstance(data, dict) and key in data:
            data = data[key]
        else:
            return None
    return data

def create_error_marker(filepath: str, error_msg: str, error_type: str = "general"):
    """创建错误标记文件。"""
    try:
        error_filepath = f"{filepath}.error_{error_type}"
        with open(error_filepath, 'w', encoding='utf-8') as ef:
            ef.write(f"[错误类型: {error_type}]\n")
            ef.write(error_msg)
        logger.info(f"  错误信息已保存至: {error_filepath}")
    except Exception as e:
        logger.error(f"  创建错误标记文件 '{error_filepath}' 时出错: {e}")


# --- 核心解析函数 ---
# extract_json_data_from_html, format_chapter_content, extract_and_format_chapter_content 函数保持不变
def extract_json_data_from_html(html_string: str) -> Optional[Dict[str, Any]]:
    """从HTML字符串中提取并解析JSON数据。"""
    try:
        logger.debug("  (预处理) 正在查找 JSON 数据块...")
        start_marker = f'<script id="{SCRIPT_TAG_ID}" type="{SCRIPT_TAG_TYPE}">'
        end_marker = '</script>'

        start_index = html_string.find(start_marker)
        if start_index == -1:
            logger.warning(f"  (预处理) 未找到开始标记 '{start_marker}'")
            return None

        json_start_index = start_index + len(start_marker)
        end_index = html_string.find(end_marker, json_start_index)
        if end_index == -1:
            logger.warning(f"  (预处理) 找到开始标记但未找到结束标记 '{end_marker}'")
            return None

        json_text = html_string[json_start_index:end_index].strip()
        if not json_text:
            logger.warning("  (预处理) 提取到的 JSON 文本块为空。")
            return None

        logger.debug(f"  (预处理) 成功提取 JSON 文本块，长度约 {len(json_text)} 字符。")
        logger.debug("  (预处理) 正在尝试解析提取到的 JSON...")

        data = json.loads(json_text)
        logger.info("  (预处理) JSON 解析成功。")
        return data

    except json.JSONDecodeError as e:
        logger.error(f"  (预处理) 提取的文本块无法解析为 JSON: {e}")
    except Exception as e:
        logger.error(f"  (预处理) 提取或解析 JSON 时发生未知错误: {e}")
        import traceback
        logger.error(traceback.format_exc())
    return None

def format_chapter_content(raw_content: str) -> str:
    """格式化章节内容，处理段落分隔。"""
    try:
        decoded_content = html.unescape(raw_content)
        formatted_content = re.sub(r'</p\s*>\s*<p[^>]*>', '', decoded_content)
        formatted_content = re.sub(r'^\s*<p[^>]*>', '', formatted_content)
        formatted_content = re.sub(r'</p\s*>.*$', '', formatted_content)
        formatted_content = re.sub(r'<[^>]+>', '\n\n', formatted_content)
        formatted_content = re.sub(r'\n{3,}', '\n\n', formatted_content)
        formatted_content = formatted_content.strip()
        # 确保 Windows 风格换行符
        formatted_content = formatted_content.replace('\r\n', '\n').replace('\n', '\r\n')
        logger.info("内容格式化完成。")
        return formatted_content
    except Exception as e:
        logger.error(f"格式化章节内容时发生错误: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return ""

def extract_and_format_chapter_content(json_data: Dict[str, Any]) -> Tuple[str, str]:
    """从JSON数据中提取章节标题和正文并格式化。"""
    if not json_data:
        logger.error("错误：输入的 JSON 数据为空或无效。")
        return "", ""

    try:
        chapter_title = get_nested_value(json_data, CHAPTER_TITLE_KEY_PATH) or ""
        logger.info(f"成功提取章节标题: {chapter_title}")

        raw_content = get_nested_value(json_data, CHAPTER_CONTENT_KEY_PATH) or ""
        logger.debug(f"成功提取原始内容，长度: {len(raw_content)} 字符")

        if not raw_content:
            logger.warning("在JSON中未找到章节内容 (content 字段为空)。")
            return chapter_title, ""

        formatted_content = format_chapter_content(raw_content)
        if not formatted_content:
            logger.warning("章节内容格式化后为空。")
            return chapter_title, ""

        return chapter_title, formatted_content

    except KeyError as e:
        logger.error(f"错误：在 JSON 数据中未找到预期的键 {e}。")
    except Exception as e:
        logger.error(f"处理章节内容时发生未知错误: {e}")
        import traceback
        logger.error(traceback.format_exc())

    return "", ""


# --- 主类 ---
# NovelChapterExtractor 类保持不变
class NovelChapterExtractor:
    """一个用于从起点中文网下载小说免费章节并保存为TXT的类。"""

    # --- 新增：类变量用于存储全局临时目录路径 ---
    _global_temp_dir: Optional[str] = None
    _cleanup_registered = False  # 标记是否已注册清理函数
    # --- 新增结束 ---

    def __init__(self, novel_url: str, save_base_dir: str = "novel", max_free_chapters: int = 100,
                 headless: bool = False, max_wait_time: int = 30, chapter_delay: float = 0.5,
                 fixed_wait_time: float = 2.0):
        # 注意：移除了 global_temp_dir 参数
        self.novel_url = novel_url.strip()
        self.save_base_dir = save_base_dir
        self.max_free_chapters = max_free_chapters
        self.headless = headless
        self.max_wait_time = max_wait_time
        self.chapter_delay = chapter_delay
        self.fixed_wait_time = fixed_wait_time
        # self.global_temp_dir = global_temp_dir # 移除此实例变量

        self.driver: Optional[webdriver.Chrome] = None
        self.wait: Optional[WebDriverWait] = None
        self.novel_id = self._extract_novel_id(self.novel_url)
        self.bookname = "未知小说"
        self.novel_save_dir: Optional[str] = None

        # --- 新增：元数据相关属性 ---
        self.metadata_file_path: Optional[str] = None
        self.metadata: Dict[str, Any] = {}
        # --- 新增结束 ---

    def _extract_novel_id(self, base_url: str) -> Optional[str]:
        """从URL中提取小说ID。"""
        parsed_url = urlparse(base_url)
        path_parts = parsed_url.path.strip('/').split('/')
        if 'book' in path_parts:
            book_index = path_parts.index('book')
            if book_index + 1 < len(path_parts):
                return path_parts[book_index + 1]
        return None

    def setup_driver(self) -> bool:
        """设置并启动Selenium WebDriver，优先使用类变量中的全局临时目录。"""
        if not self.novel_id:
            logger.error("小说URL无效，无法提取小说ID。")
            return False

        # --- 修改点：检查并创建全局临时目录 ---
        if not NovelChapterExtractor._global_temp_dir:
            try:
                # 如果类变量为空，说明是首次调用，需要创建
                NovelChapterExtractor._global_temp_dir = tempfile.mkdtemp(prefix='qidian_global_')
                logger.info(f"创建全局临时用户数据目录: {NovelChapterExtractor._global_temp_dir}")

                # 定义清理函数
                def _cleanup_global_temp_dir():
                    temp_dir = NovelChapterExtractor._global_temp_dir
                    if temp_dir and os.path.exists(temp_dir):
                        try:
                            shutil.rmtree(temp_dir)
                            logger.info(f"全局临时用户数据目录已清理: {temp_dir}")
                        except Exception as e:
                            logger.warning(f"清理全局临时目录 '{temp_dir}' 时出错: {e}")
                    elif temp_dir:
                        logger.debug(f"全局临时目录不存在或已被删除: {temp_dir}")

                # 注册清理函数（只注册一次）
                if not NovelChapterExtractor._cleanup_registered:
                    atexit.register(_cleanup_global_temp_dir)
                    NovelChapterExtractor._cleanup_registered = True
                    logger.debug("全局临时目录清理函数已注册。")

            except Exception as e:
                logger.error(f"创建全局临时用户数据目录失败: {e}")
                return False

        # 使用类变量中的全局临时目录
        temp_user_data_dir_to_use = NovelChapterExtractor._global_temp_dir
        logger.info(f"为所有小说使用全局临时用户数据目录: {temp_user_data_dir_to_use}")
        # --- 修改点结束 ---

        chrome_options = Options()
        if self.headless:
            chrome_options.add_argument("--headless=new")
        else:
            chrome_options.add_argument("--window-size=1024,768")

        chrome_options.add_argument("--disable-blink-features=AutomationControlled")
        chrome_options.add_argument("--disable-infobars")
        chrome_options.add_argument("--lang=zh-CN")
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option('useAutomationExtension', False)
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        # chrome_options.add_argument("--disable-images")

        # --- 修改点：使用确定的全局临时目录 ---
        chrome_options.add_argument(f"--user-data-dir={temp_user_data_dir_to_use}")
        # --- 修改点结束 ---

        chrome_options.add_argument(
            "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36")

        try:
            self.driver = webdriver.Chrome(options=chrome_options)
            logger.info("ChromeDriver 启动成功。")
            self.driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
            self.wait = WebDriverWait(self.driver, self.max_wait_time)

            # --- 修改点：移除实例内的 atexit 注册 ---
            # 清理工作由类静态变量和 atexit 负责
            # --- 修改点结束 ---
            return True
        except Exception as e:
            logger.error(f"启动 ChromeDriver 失败: {e}")
            # 不在此处尝试清理全局目录
            return False

    # --- 新增：元数据管理方法 ---
    def _load_metadata(self) -> bool:
        """尝试加载现有的元数据文件。"""
        if not self.metadata_file_path or not os.path.exists(self.metadata_file_path):
            logger.debug(f"元数据文件不存在: {self.metadata_file_path}")
            return False
        try:
            with open(self.metadata_file_path, 'r', encoding='utf-8') as f:
                self.metadata = json.load(f)
            logger.info(f"已加载元数据文件: {self.metadata_file_path}")
            return True
        except json.JSONDecodeError as e:
            logger.error(f"元数据文件 '{self.metadata_file_path}' JSON 格式错误: {e}")
        except Exception as e:
            logger.error(f"加载元数据文件 '{self.metadata_file_path}' 时出错: {e}")
        return False

    def _save_metadata(self):
        """将当前元数据保存到文件。"""
        if not self.metadata_file_path or not self.metadata:
            logger.debug("没有元数据需要保存或路径未设置。")
            return
        try:
            # 确保目录存在
            os.makedirs(os.path.dirname(self.metadata_file_path), exist_ok=True)
            with open(self.metadata_file_path, 'w', encoding='utf-8') as f:
                json.dump(self.metadata, f, ensure_ascii=False, indent=4)
            logger.debug(f"元数据已保存至: {self.metadata_file_path}")
        except Exception as e:
            logger.error(f"保存元数据文件 '{self.metadata_file_path}' 时出错: {e}")

    def _initialize_metadata(self, bookname: str, titles: List[str], links: List[str]):
        """初始化元数据结构。"""
        self.metadata = {
            "novel_id": self.novel_id,
            "bookname": bookname,
            "save_dir": self.novel_save_dir,
            "chapters": []
        }
        for title, link in zip(titles, links):
            # 如果是从已有的元数据加载的，则保留原有状态，否则初始化为 pending
            existing_chapter = next((c for c in self.metadata.get("chapters", []) if c["title"] == title), None)
            if existing_chapter:
                # 如果已有记录，则保留其状态和链接（以防链接变化）
                # 注意：这里假设标题是唯一的，实际情况可能需要更健壮的匹配（如链接）
                self.metadata["chapters"].append(existing_chapter)
            else:
                self.metadata["chapters"].append({
                    "title": title,
                    "link": link,
                    "status": CHAPTER_STATUS_PENDING # 使用主程序定义的常量
                })
        self._save_metadata() # 初始化后立即保存

    def _update_chapter_status(self, title: str, status: str):
        """更新章节在元数据中的状态。"""
        if "chapters" not in self.metadata:
            logger.warning("元数据中没有章节列表，无法更新状态。")
            return
        for chapter in self.metadata["chapters"]:
            if chapter["title"] == title:
                old_status = chapter.get("status", "unknown")
                chapter["status"] = status
                logger.debug(f"章节 '{title}' 状态从 '{old_status}' 更新为 '{status}'")
                self._save_metadata() # 每次状态更新后保存
                return
        logger.warning(f"在元数据中未找到章节 '{title}' 以更新状态。")
    # --- 新增结束 ---

    def get_novel_info_and_free_chapters(self) -> Tuple[str, list, list]:
        """获取小说名称和免费章节列表，并处理元数据。"""
        if not self.driver or not self.wait:
            logger.error("WebDriver 未初始化。")
            return "未知小说", [], []

        titles, links = [], []
        logger.info(f"正在访问小说主页以获取信息: {self.novel_url}")

        try:
            self.driver.set_page_load_timeout(self.max_wait_time)
            logger.debug(f"已为页面加载设置超时时间: {self.max_wait_time} 秒")

            self.driver.get(self.novel_url)
            logger.debug("driver.get 执行完成，小说主页请求已发送，开始等待页面加载...")

            logger.debug(f"等待 '{CHAPTER_ITEM_SELECTOR}' 元素出现...")
            try:
                self.wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, CHAPTER_ITEM_SELECTOR)))
                logger.debug(f"检测到 '{CHAPTER_ITEM_SELECTOR}' 元素。")
            except TimeoutException:
                logger.warning(f"等待 '{CHAPTER_ITEM_SELECTOR}' 超时。")

            time.sleep(1)
            logger.debug("主页加载等待阶段结束。")

        except Exception as e:
            logger.error(f"访问小说主页或等待加载失败: {e}")
            return self.bookname, titles, links

        try:
            bookname_element = self.driver.find_element(By.ID, BOOK_NAME_ID)
            self.bookname = bookname_element.text.strip()
            logger.info(f"通过 ID 找到书名: {self.bookname}")
        except:
            try:
                bookname_meta = self.driver.find_element(By.XPATH, "//meta[@property='og:novel:book_name']")
                self.bookname = bookname_meta.get_attribute("content").strip()
                logger.info(f"通过 Meta 标签找到书名: {self.bookname}")
            except Exception as e:
                logger.warning(f"获取小说名称失败: {e}")

        if not self.bookname or self.bookname == "未知小说":
            logger.warning("无法获取小说名称，将使用 '未知小说' 作为目录名。")
            self.bookname = f"未知小说_{self.novel_id}"

        try:
            safe_bookname = re.sub(r'[\\/:*?"<>|]', '_', self.bookname)
            self.novel_save_dir = os.path.join(self.save_base_dir, safe_bookname)
            os.makedirs(self.novel_save_dir, exist_ok=True)
            logger.info(f"章节文件将保存在目录: {self.novel_save_dir}")

            # --- 新增：设置元数据文件路径 ---
            self.metadata_file_path = os.path.join(self.novel_save_dir, "novel_metadata.json")
            # --- 新增结束 ---

        except Exception as e:
            logger.error(f"创建保存目录失败: {e}")
            return self.bookname, titles, links

        # --- 新增：尝试加载现有元数据 ---
        metadata_loaded = self._load_metadata()
        # --- 新增结束 ---

        try:
            chapter_items = self.driver.find_elements(By.CSS_SELECTOR, CHAPTER_ITEM_SELECTOR)
            free_count = 0
            all_titles, all_links = [], []
            for item in chapter_items:
                if free_count >= self.max_free_chapters:
                    break
                try:
                    item.find_element(By.CSS_SELECTOR, CHAPTER_LOCKED_SELECTOR)
                    continue
                except:
                    pass

                try:
                    link_element = item.find_element(By.CSS_SELECTOR, CHAPTER_LINK_SELECTOR)
                    title = link_element.text.strip()
                    relative_link = link_element.get_attribute("href")
                    if title and relative_link:
                        all_titles.append(title)
                        all_links.append(relative_link)
                        free_count += 1
                        logger.debug(f"  [免费] {title}")
                except Exception as e:
                    logger.warning(f"  提取章节信息时出错: {e}")

            # --- 新增：根据元数据过滤需要处理的章节 ---
            if metadata_loaded and self.metadata.get("chapters"):
                logger.info("根据现有元数据过滤章节...")
                for title, link in zip(all_titles, all_links):
                    # 查找元数据中对应的章节
                    meta_chapter = next((c for c in self.metadata["chapters"] if c["title"] == title), None)
                    if meta_chapter:
                        # 如果状态是 pending 或 failed，则加入待处理列表
                        if meta_chapter.get("status") in [CHAPTER_STATUS_PENDING, CHAPTER_STATUS_FAILED]: # 使用常量
                             titles.append(title)
                             links.append(link)
                             logger.debug(f"  章节 '{title}' 需要处理 (状态: {meta_chapter.get('status')})")
                        # 如果是 downloaded，则跳过
                        elif meta_chapter.get("status") == CHAPTER_STATUS_DOWNLOADED: # 使用常量
                             logger.debug(f"  章节 '{title}' 已下载，跳过。")
                        else:
                             # 其他未知状态，也加入待处理列表
                             titles.append(title)
                             links.append(link)
                             logger.warning(f"  章节 '{title}' 状态未知 ({meta_chapter.get('status')}), 加入待处理列表。")
                    else:
                        # 元数据中没有此章节，说明是新增的，加入待处理列表
                        titles.append(title)
                        links.append(link)
                        logger.debug(f"  章节 '{title}' 是新增的，加入待处理列表。")

                # 如果元数据中的章节比当前获取到的多（例如网站删除了章节），元数据中多余的章节会被忽略
                # 如果需要处理这种情况，可以在这里添加逻辑

            else:
                # 没有加载到元数据，或者元数据为空，则所有获取到的章节都需要处理
                titles = all_titles
                links = all_links
                # 初始化元数据
                self._initialize_metadata(self.bookname, titles, links)

            # --- 新增结束 ---

        except Exception as e:
            logger.error(f"查找章节列表时发生错误: {e}")

        logger.info(f"成功找到 {len(all_titles)} 个免费章节 (最多提取 {self.max_free_chapters} 个)。")
        logger.info(f"根据元数据筛选后，需要处理 {len(titles)} 个章节。")
        return self.bookname, titles, links

    def _get_txt_filepath(self, title: str, index: int) -> str:
        """获取章节 TXT 文件的完整路径。"""
        if not self.novel_save_dir:
            raise ValueError("保存目录未设置。")
        filename = sanitize_filename(title, index)
        return os.path.join(self.novel_save_dir, filename)

    def _check_txt_file_exists(self, title: str, index: int) -> Tuple[bool, str]:
        """检查章节 TXT 文件是否已存在。"""
        txt_filepath = self._get_txt_filepath(title, index)
        if os.path.exists(txt_filepath):
            logger.info(f"  章节 '{title}' 的TXT文件已存在，跳过下载和解析。")
            # --- 新增：如果文件存在，更新元数据状态 ---
            self._update_chapter_status(title, CHAPTER_STATUS_DOWNLOADED) # 使用常量
            # --- 新增结束 ---
            return True, txt_filepath
        return False, txt_filepath

    def _navigate_and_wait(self, full_url: str, title: str) -> bool:
        """导航到章节页面并等待固定时间。"""
        try:
            logger.debug(f"  准备执行 driver.get('{full_url}') ...")
            self.driver.get(full_url)
            logger.debug(f"  driver.get 执行完成，'{title}' 页面请求已发送。")

            logger.debug(f"  开始固定等待 {self.fixed_wait_time} 秒...")
            time.sleep(self.fixed_wait_time)
            logger.debug(f"  章节 '{title}' 固定等待结束。")
            return True
        except Exception as e:
            logger.error(f"  访问章节 '{title}' 页面时发生错误: {e}")
            return False

    def _process_chapter_content(self, title: str, index: int, total: int) -> bool:
        """处理单个章节的内容（获取、解析、保存）。"""
        is_exist, txt_filepath = self._check_txt_file_exists(title, index)
        if is_exist:
            return True # 已存在，处理成功

        try:
            page_html = self.driver.page_source
            logger.debug(f"  已获取 '{title}' 的页面源码，准备解析...")

            json_data = extract_json_data_from_html(page_html)
            if not json_data:
                error_msg = f"[解析失败] 无法从HTML中提取JSON数据\nURL: {self.driver.current_url}\n"
                create_error_marker(txt_filepath, error_msg, "json_extract")
                # --- 新增：更新元数据状态为失败 ---
                self._update_chapter_status(title, CHAPTER_STATUS_FAILED) # 使用常量
                # --- 新增结束 ---
                return False

            final_title, formatted_content = extract_and_format_chapter_content(json_data)
            if final_title and formatted_content:
                save_title = final_title if final_title else title
                try:
                    with open(txt_filepath, 'w', encoding='utf-8') as f:
                        f.write(save_title + "\n\n")
                        f.write(formatted_content)
                    logger.info(f"  章节 '{save_title}' 内容已解析并保存至: {txt_filepath}")

                    # --- 新增：更新元数据状态为已下载 ---
                    self._update_chapter_status(title, CHAPTER_STATUS_DOWNLOADED) # 使用常量
                    # --- 新增结束 ---

                    # 清理可能存在的旧错误文件
                    for suffix in [".error", ".error_general", ".error_json_extract", ".error_write"]:
                        old_error_file = txt_filepath + suffix
                        if os.path.exists(old_error_file):
                            try:
                                os.remove(old_error_file)
                                logger.debug(f"  已删除旧的错误文件: {old_error_file}")
                            except OSError as e:
                                logger.warning(f"  删除旧错误文件 '{old_error_file}' 时出错: {e}")
                    return True
                except Exception as e:
                    error_msg = f"[写入失败] 保存文件时出错: {e}\n"
                    create_error_marker(txt_filepath, error_msg, "write")
                    # --- 新增：更新元数据状态为失败 ---
                    self._update_chapter_status(title, CHAPTER_STATUS_FAILED) # 使用常量
                    # --- 新增结束 ---
                    return False
            else:
                error_msg = f"[解析失败] 章节内容解析失败或为空\n"
                create_error_marker(txt_filepath, error_msg, "parse")
                # --- 新增：更新元数据状态为失败 ---
                self._update_chapter_status(title, CHAPTER_STATUS_FAILED) # 使用常量
                # --- 新增结束 ---
                return False

        except Exception as e:
            logger.error(f"  处理章节 '{title}' 时发生未知错误: {e}")
            import traceback
            logger.error(traceback.format_exc())
            error_msg = f"[未知错误] {e}\n{traceback.format_exc()}\n"
            create_error_marker(txt_filepath, error_msg, "unexpected")
            # --- 新增：更新元数据状态为失败 ---
            self._update_chapter_status(title, CHAPTER_STATUS_FAILED) # 使用常量
            # --- 新增结束 ---
            return False

    def download_and_parse_chapter(self, title: str, relative_link: str, index: int, total: int) -> bool:
        """下载并解析单个章节。"""
        # 修复 urljoin 的基础 URL
        full_url = relative_link if relative_link.startswith('http') else urljoin("https://www.qidian.com/", relative_link)
        logger.info(f"[{index + 1}/{total}] 正在处理章节: {title} ({full_url})")

        # --- 新增：在开始处理前，先检查元数据状态（可能在其他地方已更新）---
        # 这是一个额外的安全检查，虽然主循环已经筛选过了
        if "chapters" in self.metadata:
            meta_chapter = next((c for c in self.metadata["chapters"] if c["title"] == title), None)
            if meta_chapter and meta_chapter.get("status") == CHAPTER_STATUS_DOWNLOADED: # 使用常量
                 logger.info(f"  检查元数据发现章节 '{title}' 已标记为已下载，跳过。")
                 return True # 假设文件也存在
        # --- 新增结束 ---

        if not self._navigate_and_wait(full_url, title):
            txt_filepath = self._get_txt_filepath(title, index)
            error_msg = f"错误: 无法访问章节页面 {full_url}\n"
            create_error_marker(txt_filepath, error_msg, "navigation")
            # --- 新增：更新元数据状态为失败 ---
            self._update_chapter_status(title, CHAPTER_STATUS_FAILED) # 使用常量
            # --- 新增结束 ---
            return False

        return self._process_chapter_content(title, index, total)

    def _generate_txt_filename(self, title, index):
        """
        根据章节标题生成预期的 TXT 文件名。
        与 _check_and_get_txt_filepath 中生成文件名的逻辑保持一致。
        :param title: 章节标题
        :param index: 章节索引 (主要用于备用命名，实际可能用不到)
        :return: str, 预期的文件名 (不包含路径)
        """
        # 清理标题中的非法字符
        filename_safe_title = re.sub(r'[\\/:*?"<>|]', '_', title)
        # 确保文件名不为空
        if not filename_safe_title:
            filename_safe_title = f"未命名章节_{index + 1}"
        return f"{filename_safe_title}.txt"

    def run(self):
        """
        执行完整的提取流程，优化：预先筛选出需要下载的章节。
        """
        if not self.setup_driver():
            return

        try:
            bookname, titles, links = self.get_novel_info_and_free_chapters()
            if not titles:
                logger.info("根据元数据筛选后，没有需要处理的章节。提前退出。") # 修改日志级别和内容
                # 即使没有新章节，也尝试保存一次元数据（可能是初始化）
                if self.metadata and self.metadata_file_path:
                    self._save_metadata()
                return # 提前返回

            # --- 修改：遍历预先筛选出的待处理列表 ---
            success_count = 0
            total_chapters_to_process = len(titles)

            for i, (title, link) in enumerate(zip(titles, links)):
                logger.info(
                    f"[{i + 1}/{total_chapters_to_process}] 计划下载章节: {title}")

                # 调用下载解析方法，传递原始索引和总章节数用于内部可能的日志或计算
                if self.download_and_parse_chapter(title, link, i, total_chapters_to_process):
                    success_count += 1

                # 章节间延迟
                if i < total_chapters_to_process - 1:
                    logger.debug(f"  章节间延迟 {self.chapter_delay} 秒...")
                    time.sleep(self.chapter_delay)
            # --- 修改结束 ---

            logger.info(f"任务完成。小说 '{bookname}'。")
            logger.info(f"本次计划处理 {total_chapters_to_process} 个章节，成功处理 {success_count} 个。")

        except KeyboardInterrupt:
            logger.info("用户中断程序。")
        except Exception as e:
            logger.exception(f"执行过程中发生未预期的错误: {e}")
        finally:
            if self.driver:
                try:
                    self.driver.quit()
                    logger.info("浏览器已关闭。")
                except Exception as e:
                    logger.warning(f"关闭浏览器时出错: {e}")
            # --- 新增：确保最后保存一次元数据 ---
            if self.metadata and self.metadata_file_path:
                self._save_metadata()
            # --- 新增结束 ---


# --- 文件加载函数 ---
# load_booknames_from_file, load_urls_from_file 函数保持不变
def load_booknames_from_file(filepath: str) -> List[str]:
    """
    从文本文件加载小说名称列表。
    假设每行一个书名。

    Args:
        filepath (str): 包含小说名称的文本文件路径。

    Returns:
        List[str]: 小说名称列表。
    """
    booknames = []
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                # 忽略空行和注释行
                if not line or line.startswith('#'):
                    continue
                # 假设每行就是一个书名
                # 可以根据实际文件格式进行调整，例如提取书名部分
                # 例如，如果格式是 "1. 《书名》 - URL"，可以使用正则提取
                # bookname_match = re.search(r'《([^》]+)》', line)
                # if bookname_match:
                #     booknames.append(bookname_match.group(1).strip())
                # else:
                #     logger.warning(f"  跳过第 {line_num} 行：无法识别书名: '{line}'")

                # 当前简单处理：整行作为书名
                if line:
                    booknames.append(line)
        logger.info(f"从文件 '{filepath}' 成功加载 {len(booknames)} 个书名。")
    except FileNotFoundError:
        logger.error(f"错误：找不到文件 '{filepath}'。")
    except Exception as e:
        logger.error(f"读取文件 '{filepath}' 时发生错误: {e}")
    return booknames

def load_urls_from_file(filepath: str) -> List[Tuple[str, str]]:
    """
    从文本文件加载小说信息列表。
    支持带序号和书名的格式，如 "  1. 《书名》 - URL"。
    忽略空行、注释行（以#开头）。
    返回 [(书名, URL), ...] 的列表。
    """
    novels = []
    novel_pattern = re.compile(r'.*?《([^》]+)》\s*-\s*(https?://[^\s]+)')
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if not line or line.startswith('#'):
                    continue

                match = novel_pattern.search(line)
                if match:
                    bookname = match.group(1).strip()
                    url = match.group(2).rstrip('/') + '/'
                    if "qidian.com/book/" in url:
                         novels.append((bookname, url))
                         logging.debug(f"  从第 {line_num} 行提取到: 书名='{bookname}', URL='{url}'")
                    else:
                         logging.warning(f"  跳过第 {line_num} 行：找到URL但不像是起点书籍链接: {url}")
                else:
                    if line and not line.startswith('#'):
                        logging.warning(f"  跳过第 {line_num} 行：无法识别格式或未找到书名和URL: '{line}'")

        logging.info(f"从文件 '{filepath}' 成功加载 {len(novels)} 个小说信息。")
    except FileNotFoundError:
        logging.error(f"错误：找不到文件 '{filepath}'。")
    except Exception as e:
        logging.error(f"读取文件 '{filepath}' 时发生错误: {e}")
    return novels


# --- 主函数 ---
def main():
    """主函数"""
    # --- 配置区域 ---
    URLS_FILE_PATH = 'novel_urls.txt'
    MAX_FREE_CHAPTERS_PER_NOVEL = 100
    SAVE_BASE_DIR = "novels"
    HEADLESS_MODE = True
    MAX_WAIT_TIME = 30
    CHAPTER_DELAY = 1.0
    FIXED_WAIT_TIME = 2.0
    # --- 配置区域结束 ---

    # 1. 读取 (书名, URL) 列表
    novel_info_list = load_urls_from_file(URLS_FILE_PATH)
    if not novel_info_list:
        logger.error("没有找到有效的书名和URL，程序退出。")
        return

    # 2. 总数基于 (书名, URL) 对
    total_novels = len(novel_info_list)
    successful_novels = 0

    # 3. 遍历 (书名, URL) 对
    for index, (bookname, novel_url) in enumerate(novel_info_list):
        # 4. 日志使用书名
        logger.info(f"=== 开始检查第 {index + 1}/{total_novels} 本小说: {bookname} ===")

        # 5. 执行预检查 (使用工具模块中的函数)
        # 注意：chapter_utils.should_process_novel_by_name 返回布尔值
        need_processing = chapter_utils.should_process_novel_by_name(
            bookname=bookname,
            save_base_dir=SAVE_BASE_DIR
        )

        if not need_processing:
            logger.info(f"=== 跳过第 {index + 1}/{total_novels} 本小说《{bookname}》的处理 ===\n")
            successful_novels += 1
            continue

        logger.info(f"=== 需要处理第 {index + 1}/{total_novels} 本小说《{bookname}》 ===")

        try:
            # 6. 创建提取器实例 (使用解析出的 URL)
            extractor = NovelChapterExtractor(
                novel_url=novel_url,
                save_base_dir=SAVE_BASE_DIR,
                max_free_chapters=MAX_FREE_CHAPTERS_PER_NOVEL,
                headless=HEADLESS_MODE,
                max_wait_time=MAX_WAIT_TIME,
                chapter_delay=CHAPTER_DELAY,
                fixed_wait_time=FIXED_WAIT_TIME
            )
            extractor.run()
            successful_novels += 1
            logger.info(f"=== 第 {index + 1}/{total_novels} 本小说处理完成 ===\n")
        except Exception as e:
            # 7. 日志包含书名和URL
            logger.error(f"=== 处理第 {index + 1}/{total_novels} 本小说 '{bookname}' (URL: {novel_url}) 时发生严重错误: {e} ===\n")

    logger.info(f"所有小说处理完毕。总共 {total_novels} 本，成功处理（包括跳过） {successful_novels} 本。")

if __name__ == "__main__":
    main()