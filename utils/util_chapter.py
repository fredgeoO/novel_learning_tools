# util_chapter.py
import os
import glob
import re
import json
import logging

import utils.util_number # 假设它们在同一个包内
from utils import util_number

# --- 配置 ---
# 日志配置 (如果主程序已有，可以考虑移除或简化)
logging.basicConfig(level=logging.INFO, format='[%(asctime)s] [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

# 获取当前文件所在目录
UTIL_DIR = os.path.dirname(os.path.abspath(__file__))
# 项目根目录 = utils/ 的父目录
PROJECT_ROOT = os.path.dirname(UTIL_DIR)

# 定义绝对路径
NOVELS_BASE_DIR = os.path.join(PROJECT_ROOT, "novels")
BROWSE_HISTORY_FILE = os.path.join(PROJECT_ROOT, "browse_history.json")

# 同理修正其他路径
REPORTS_BASE_DIR = os.path.join(PROJECT_ROOT, "reports", "novels")
PROMPT_ANALYZER_DIR = os.path.join(PROJECT_ROOT, "inputs", "prompts", "analyzer")
METADATA_FILE_PATH = os.path.join(PROMPT_ANALYZER_DIR, "metadata.json")
SCRAPED_DATA_DIR = os.path.join(PROJECT_ROOT, "scraped_data")

print(f"[util_chapter] Novels dir: {NOVELS_BASE_DIR}")  # 调试用


CHAPTER_STATUS_PENDING = "pending"
CHAPTER_STATUS_DOWNLOADED = "downloaded"
CHAPTER_STATUS_FAILED = "failed"
# --- 新增结束 ---

# --- 缓存变量 ---
chapter_cache = {}
report_cache = {}
novel_cache  = {}


def find_novel_synopsis(novel_name):
    """
    在 scraped_data 目录下的月票榜文件中查找指定小说的简介。
    :param novel_name: 小说名称
    :return: 格式化后的简介字符串，如果未找到则返回 None
    """
    if not novel_name or not os.path.exists(SCRAPED_DATA_DIR):
        return None

    # 遍历所有可能的月票榜文件
    for filename in os.listdir(SCRAPED_DATA_DIR):
        if filename.endswith("_月票榜_top100.txt"):
            filepath = os.path.join(SCRAPED_DATA_DIR, filename)
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    content = f.read()
            except Exception as e:
                logger.warning(f"读取简介文件 {filepath} 时出错: {e}")
                continue

            # 使用正则表达式查找小说信息块
            # 匹配 "  X. 《小说名》" 开头，到下一个 "  X." 或文件结尾的部分
            pattern = rf"^\s*\d+\.\s*《{re.escape(novel_name)}》.*?(?=\n\s*\d+\.|\Z)"
            match = re.search(pattern, content, re.DOTALL | re.MULTILINE)

            if match:
                novel_block = match.group(0).strip()
                # 简单格式化：移除 "  X. " 前缀，将条目分行
                lines = novel_block.splitlines()
                if lines:
                    # 移除第一行的序号前缀
                    formatted_lines = [re.sub(r"^\s*\d+\.\s*", "**书名:** ", lines[0])]
                    # 处理后续行，如作者、分类、简介等
                    for line in lines[1:]:
                        stripped_line = line.strip()
                        if stripped_line.startswith("作者:"):
                            formatted_lines.append(f"**{stripped_line}**")
                        elif stripped_line.startswith("分类:"):
                            formatted_lines.append(f"*{stripped_line}*")
                        elif stripped_line.startswith("链接:"):
                            # 可以选择是否显示链接
                            # formatted_lines.append(f"[链接]({stripped_line.split(':', 1)[1].strip()})")
                            pass  # 暂时不显示链接
                        elif stripped_line.startswith("简介:"):
                            formatted_lines.append(f"**简介:**\n{stripped_line.split(':', 1)[1].strip()}")
                        elif stripped_line.startswith("最新:"):
                            formatted_lines.append(f"**{stripped_line}**")
                        elif stripped_line:  # 其他非空行也加上
                            formatted_lines.append(stripped_line)

                synopsis_md = "\n\n".join(formatted_lines)
                return f"## 📖 《{novel_name}》故事简介\n\n{synopsis_md}"

    return None






chapter_number_cache = {}

def extract_chapter_number(chapter_title):
    """
    从章节标题中提取章节号，并转换为可比较的整数。
    支持 "第X章" 格式，其中 X 可以是阿拉伯数字、中文数字或罗马数字。
    也支持纯数字开头的格式，如 "001.", "1 "。
    """
    # --- 新增：检查缓存 ---
    if chapter_title in chapter_number_cache:
        return chapter_number_cache[chapter_title]
    # --- 新增结束 ---

    result = float('inf')  # 默认值

    # 1. 首先尝试匹配 "第X章/回/节..." 格式
    match = re.search(
        r"第\s*((?:[0-9]+|[一二三四五六七八九十〇零壹贰叁肆伍陆柒捌玖拾佰仟萬亿兆廿卅皕]+|[IVXLCDMivxlcdm]+)+)\s*[章回节篇幕集话卷]",
        chapter_title
    )
    if match:
        number_str = match.group(1).strip()
        # 尝试转换阿拉伯数字
        try:
            result = int(number_str)
        except ValueError:
            pass
        # 尝试转换中文数字 (使用改进的函数)
        if result == float('inf'):
            try:
                # --- 修改：使用从 number_utils 导入的函数 ---
                res = util_number.chinese_to_arabic_simple(number_str)
                # --- 修改结束 ---
                if res != float('inf'):
                    result = res
            except:
                pass
        # 尝试转换罗马数字
        if result == float('inf'):
            try:
                # --- 修改：使用从 number_utils 导入的函数 ---
                res = util_number.roman_to_arabic(number_str)
                # --- 修改结束 ---
                if res != float('inf'):
                    result = res
            except:
                pass

    # 2. 如果第一步失败，尝试匹配纯数字开头的格式 (如 "001.", "1 ")
    if result == float('inf'):
        pure_number_match = re.match(r'^\s*(\d+)\s*[.、 ]', chapter_title)
        if pure_number_match:
            try:
                result = int(pure_number_match.group(1))
            except ValueError:
                pass

    # 3. 如果都失败了，尝试在标题中查找任何阿拉伯数字 (作为后备)
    if result == float('inf'):
        arabic_match = re.search(r'\d+', chapter_title)
        if arabic_match:
            try:
                result = int(arabic_match.group())
            except ValueError:
                pass

    # 4. 最后，如果所有方法都失败，返回无穷大
    if result == float('inf'):
        result = float('inf')

    # --- 新增：存储到缓存 ---
    chapter_number_cache[chapter_title] = result
    # --- 新增结束 ---
    return result


def sort_chapters_by_number(chapter_filenames):
    """
    对章节文件名列表进行智能排序。

    Args:
        chapter_filenames (list): 章节文件名列表 (如 ['第一章.txt', '第二章.txt'])

    Returns:
        list: 排序后的章节文件名列表
    """
    return sorted(chapter_filenames, key=lambda x: extract_chapter_number(os.path.splitext(x)[0]))

def get_chapter_list(novel_name):
    """
    根据小说名获取其章节列表 (txt文件名列表，不含路径)，并按章节号智能排序。
    """
    if not novel_name:
        return []
    novel_path = os.path.join(NOVELS_BASE_DIR, novel_name)
    if not os.path.exists(novel_path):
        logger.warning(f"警告: 小说目录 '{novel_path}' 不存在。")
        return []
    try:
        txt_files = glob.glob(os.path.join(glob.escape(novel_path), "*.txt"))
        chapter_names = [os.path.basename(f) for f in txt_files]

        # 更新后的章节模式匹配正则表达式
        CHAPTER_PATTERN = re.compile(
            r"(?:第\s*([0-9]+|[一二三四五六七八九十〇零壹贰叁肆伍陆柒捌玖拾佰仟萬亿兆廿卅皕IVXLCDMivxlcdm]+)\s*[章回节篇幕集话卷])"
            r"|(?:^\s*\d+\s*[.、 ])",
            re.IGNORECASE
        )

        # 筛选有效的章节文件
        filtered_chapters = []
        for chapter in chapter_names:
            chapter_title = os.path.splitext(chapter)[0]
            matches_chapter_pattern = bool(CHAPTER_PATTERN.search(chapter_title))
            if matches_chapter_pattern:
                filtered_chapters.append(chapter)

        # --- 修改：使用通用排序函数 ---
        if filtered_chapters:
            return sort_chapters_by_number(filtered_chapters)
        else:
            logger.info(f"信息: 小说 '{novel_name}' 没有找到符合章节模式的文件。")
            return []

    except Exception as e:
        logger.error(f"获取章节列表时出错 for '{novel_name}': {e}")
        import traceback
        traceback.print_exc()
        return []


# --- 新增：章节内容清洗逻辑 ---

def clean_chapter_text(raw_text):
    """
    (简化版) 对原始小说文本进行基础排版清洗，使其更适合显示或进一步处理。
    这是一个可以深度定制的函数。
    """
    if not raw_text:
        return ""

    lines = raw_text.splitlines()
    formatted_lines = []

    for line in lines:
        stripped_line = line.strip()
        if not stripped_line:
            # 空行保留，作为段落分隔
            formatted_lines.append("")
        else:
            # 可以尝试识别标题 (例如以 "第" 和 "章" 开头的行，或纯数字行)
            # 注意：这里使用了与筛选时类似的判断
            if (re.match(r"^第\s*.*\s*[章回节篇幕集话卷].*", stripped_line) or
                re.match(r"^\s*\d+\s*[.、 ]", stripped_line)):
                # 看起来像标题
                formatted_lines.append(stripped_line)
            else:
                # 普通行，去除首尾空格
                formatted_lines.append(stripped_line)

    # 将列表重新组合成字符串，用换行符连接
    # 保留段落间的空行
    return "\n".join(formatted_lines)


# --- 新增：加载章节内容 ---
# 这个函数可以供其他模块调用，加载原始文本并可选地进行清洗

def load_chapter_content(novel_name, chapter_filename, clean=True):
    """
    加载指定小说章节的原始内容。
    :param novel_name: 小说目录名
    :param chapter_filename: 章节文件名 (包含 .txt)
    :param clean: 是否对内容进行清洗 (默认 True)
    :return: (章节内容字符串, 是否成功布尔值)
    """
    if not novel_name or not chapter_filename:
        return "错误：小说名或章节名为空。", False

    chapter_file_path = os.path.join(NOVELS_BASE_DIR, novel_name, chapter_filename)

    if not os.path.exists(chapter_file_path):
        error_msg = f"错误：章节文件未找到: {chapter_file_path}"
        logger.error(error_msg)
        return error_msg, False

    try:
        with open(chapter_file_path, 'r', encoding='utf-8') as f:
            raw_content = f.read()

        if clean:
            processed_content = clean_chapter_text(raw_content)
        else:
            processed_content = raw_content

        if not processed_content.strip():
            processed_content = "警告：该章节文件内容为空。"

        return processed_content, True

    except Exception as e:
        error_msg = f"读取章节文件时出错: {e}"
        logger.error(error_msg)
        import traceback
        traceback.print_exc()
        return error_msg, False


# --- 新增：带缓存刷新机制的函数 ---

def get_chapter_list_with_cache(novel_name):
    """
    获取章节列表并检查是否有更新。
    """
    if not novel_name:
        return []

    novel_dir = os.path.join(NOVELS_BASE_DIR, novel_name)
    if not os.path.exists(novel_dir):
        return []

    current_files = sorted([f for f in os.listdir(novel_dir) if f.endswith('.txt')])
    cached = chapter_cache.get(novel_name)

    if cached is None or cached != current_files:
        logger.info(f"[刷新] 章节列表发生变化: {novel_name}")
        chapter_cache[novel_name] = current_files

    # 调用原有逻辑进行排序
    return get_chapter_list(novel_name)


def get_report_list_with_cache(novel_name, chapter_filename):
    """
    获取报告列表并检查是否有更新，并按照 metadata.json 排序。
    """
    if not novel_name or not chapter_filename:
        return []

    chapter_name = os.path.splitext(chapter_filename)[0]
    reports_dir = os.path.join(REPORTS_BASE_DIR, novel_name, chapter_name)

    if not os.path.exists(reports_dir):
        report_cache[(novel_name, chapter_name)] = []
        return []

    try:
        current_files = sorted([os.path.basename(f) for f in glob.glob(os.path.join(glob.escape(reports_dir), "*.txt"))])
        cached = report_cache.get((novel_name, chapter_name))

        if cached is None or set(cached) != set(current_files):
            logger.info(f"[刷新] 报告列表发生变化: {novel_name}/{chapter_name}")
            report_cache[(novel_name, chapter_name)] = current_files

        # 使用排序函数对报告进行排序
        return sort_reports_by_metadata(current_files)

    except Exception as e:
        logger.error(f"获取报告列表时出错: {e}")
        return []


def filter_think_tags(text: str) -> str:
    """
    过滤掉 <think>...</think> 标签及其内容。
    """
    import re
    filtered_text = re.sub(r'<!--.*?-->', '', text, flags=re.DOTALL) # 移除HTML注释
    filtered_text = re.sub(r'<think>.*?</think>', '', filtered_text, flags=re.DOTALL)
    filtered_text = re.sub(r'\n\s*\n', '\n\n', filtered_text).strip()
    return filtered_text


def load_report_content(novel_name, chapter_filename, report_filename):
    """
    加载报告内容，过滤 think 标签及无意义段落，并返回清洗后的内容。
    """
    if not all([novel_name, chapter_filename, report_filename]):
        return "## AI 分析报告\n\n请选择一个报告文件。"

    chapter_name = os.path.splitext(chapter_filename)[0]
    report_path = os.path.join(REPORTS_BASE_DIR, novel_name, chapter_name, report_filename)

    if not os.path.exists(report_path):
        error_msg = f"## 错误\n\n报告文件未找到: `{report_path}`"
        logger.error(error_msg)
        return error_msg

    try:
        with open(report_path, 'r', encoding='utf-8') as f:
            raw_content = f.read()

        # Step 1: 过滤掉 <think> 标签及其内容
        content_without_think = filter_think_tags(raw_content)

        # Step 2: 按行处理，过滤无意义内容
        lines = content_without_think.splitlines()
        cleaned_lines = []

        for line in lines:
            stripped = line.strip()

            # 跳过空行
            if not stripped:
                continue

            # 跳过纯数字行（如 1, 2, 99）
            if re.fullmatch(r'\d+', stripped):
                continue

            # 跳过特殊符号行（如 ___, ›, ⌄）
            if re.fullmatch(r'[‗_\-‒–—―‗‹›⌄<> ]+', stripped):
                continue

            # 跳过无意义短句（如少于3个字符且不是Markdown语法）
            if len(stripped) < 3 and not is_markdown_format_line(stripped):
                continue
            # 跳过该行包含 markdown
            if stripped == "markdown":
                continue

            # 保留有效行
            cleaned_lines.append(line)

        # Step 3: 重新拼接内容
        final_content = '\n'.join(cleaned_lines).strip()

        # 如果内容为空，返回默认提示
        if not final_content:
            final_content = "## AI 分析报告\n\n该报告内容为空或已被过滤。"

        return final_content

    except Exception as e:
        error_msg = f"## 读取错误\n\n读取报告文件时出错: `{e}`"
        logger.error(error_msg, exc_info=True)
        return error_msg


def is_markdown_format_line(line):
    """
    判断一行是否为Markdown格式语法
    """
    if not line:
        return False

    # 常见的Markdown格式语法
    markdown_patterns = [
        r'^#{1,6}\s',  # 标题 #
        r'^\s*[\-\*\+]\s',  # 无序列表
        r'^\s*\d+\.\s',  # 有序列表
        r'^\s*>',  # 引用
        r'^\s*```',  # 代码块
        r'^\s*`[^`]*`',  # 行内代码
        r'^\s*\*\*.*\*\*$',  # 粗体 **
        r'^\s*__.*__$',  # 粗体 __
        r'^\s*\*.*\*$',  # 斜体 *
        r'^\s*_.*_$',  # 斜体 _
        r'^\s*\[.*\]\(.*\)',  # 链接
        r'^\s*!\[.*\]\(.*\)',  # 图片
        r'^\s*\|',  # 表格 |
        r'^\s*---+\s*$',  # 分割线
        r'^\s*\*\*\*\s*$',  # 分割线 ***
        r'^\s*___\s*$',  # 分割线 ___
    ]

    for pattern in markdown_patterns:
        if re.match(pattern, line):
            return True

    return False


def load_chapter_and_initial_report(novel_name, chapter_filename):
    """
    加载章节内容和默认报告（第一个报告）。
    """
    # 使用 chapter_utils 加载并清洗章节内容
    chapter_content, success = load_chapter_content(novel_name, chapter_filename, clean=True)
    if not success:
        chapter_content = f"## 错误\n\n{chapter_content}" # 格式化错误信息

    reports = get_report_list_with_cache(novel_name, chapter_filename)
    report_content = load_report_content(novel_name, chapter_filename, reports[0]) if reports else "## AI 分析报告\n\n该章节暂无可用的分析报告。"
    return chapter_content, report_content


# ========================
# 新增功能函数
# ========================

def has_any_reports(novel_name):
    """判断小说是否有任何章节有分析报告"""
    novel_dir = os.path.join(REPORTS_BASE_DIR, novel_name)
    return os.path.exists(novel_dir) and any(os.scandir(novel_dir))


# 同样修改 get_filtered_chapters_with_reports 函数
def get_filtered_chapters_with_reports(novel_name):
    """
    获取小说中存在分析报告的章节，并按章节号智能排序。
    """
    novel_report_dir = os.path.join(REPORTS_BASE_DIR, novel_name)
    if not os.path.exists(novel_report_dir):
        return []

    try:
        # 1. 获取所有有报告的章节名 (目录名)
        chapter_dirs = [d.name for d in os.scandir(novel_report_dir) if d.is_dir()]

        # 2. 将目录名转换为标准章节文件名并过滤
        novel_dir = os.path.join(NOVELS_BASE_DIR, novel_name)
        if not os.path.exists(novel_dir):
            logger.warning(f"小说目录不存在: {novel_dir}")
            return []

        all_chapter_files = [f for f in os.listdir(novel_dir) if f.endswith('.txt')]
        all_chapter_names_set = {os.path.splitext(f)[0] for f in all_chapter_files}

        filtered_chapter_files = [
            f"{ch}.txt" for ch in chapter_dirs if ch in all_chapter_names_set
        ]

        # --- 修改：使用通用排序函数 ---
        return sort_chapters_by_number(filtered_chapter_files)

    except Exception as e:
        logger.error(f"获取带报告的章节列表时出错: {e}", exc_info=True)
        return []


# --- 新增：通用型预检查逻辑 ---
def should_process_novel_by_name(bookname: str, save_base_dir: str = NOVELS_BASE_DIR) -> bool:
    """
    检查小说是否需要处理（即是否所有章节都已下载）。
    逻辑：根据小说名称检查 novels 目录下对应文件夹中的元数据文件。
    如果所有章节状态都是 'downloaded'，则返回 False（跳过）。
    否则返回 True（需要处理）。

    Args:
        bookname (str): 小说的名称。
        save_base_dir (str): 基础保存目录 (默认为 "novels")。

    Returns:
        bool: True 表示需要处理，False 表示无需处理。
    """
    if not bookname or not save_base_dir:
        logger.warning(f"预检查：书名或保存目录为空。书名='{bookname}', 目录='{save_base_dir}'")
        return True # 保守处理，需要处理

    try:
        # 1. 根据书名构造保存目录路径
        # 注意：这里假设主程序和此工具模块使用相同的文件名清理逻辑
        safe_bookname = re.sub(r'[\\/:*?"<>|]', '_', bookname)
        novel_save_dir = os.path.join(save_base_dir, safe_bookname)
        metadata_file_path = os.path.join(novel_save_dir, "novel_metadata.json")

        # 2. 检查保存目录和元数据文件是否存在
        if not os.path.exists(novel_save_dir) or not os.path.exists(metadata_file_path):
            logger.debug(f"预检查：目录或元数据文件不存在，需要处理。目录: {novel_save_dir}, 文件: {metadata_file_path}")
            return True # 需要处理

        # 3. 尝试加载元数据
        metadata = None
        try:
            with open(metadata_file_path, 'r', encoding='utf-8') as f:
                metadata = json.load(f)
        except (json.JSONDecodeError, Exception) as e:
            logger.warning(f"预检查：加载元数据文件 '{metadata_file_path}' 时出错: {e}。将重新处理。")
            return True # 需要处理

        # 4. 验证元数据结构和章节信息
        if not isinstance(metadata, dict) or "chapters" not in metadata:
            logger.warning(f"预检查：元数据文件 '{metadata_file_path}' 结构不完整。将重新处理。")
            return True # 需要处理

        chapters_data = metadata.get("chapters", [])
        if not chapters_data:
            logger.info(f"预检查：元数据中没有章节信息，需要处理。")
            return True # 需要处理

        # 5. 核心判断：检查是否所有章节都已下载
        # 使用 all() 函数和生成器表达式简化逻辑
        all_downloaded = all(
            chapter.get("status") == CHAPTER_STATUS_DOWNLOADED for chapter in chapters_data
        )

        if all_downloaded:
            logger.info(f"预检查：小说《{bookname}》所有章节均已下载。跳过处理。")
            return False # 无需处理
        else:
            # 可选：统计需要处理的章节数量
            pending_or_failed_count = sum(
                1 for c in chapters_data
                if c.get("status") in [CHAPTER_STATUS_PENDING, CHAPTER_STATUS_FAILED]
            )
            logger.info(f"预检查：小说《{bookname}》有 {pending_or_failed_count} 个章节需要处理。")
            return True # 需要处理

    except Exception as e:
        logger.error(f"预检查：处理小说 '{bookname}' 时发生未预期错误: {e}", exc_info=True)
        return True # 出错则保守处理，需要处理




# --- 新增：删除报告功能 ---


def delete_report_file(novel_name, chapter_filename, report_filename):
    """
    删除指定的报告文件，并清理空目录，刷新缓存。
    返回 (新的报告内容, 报告选择器的更新信息字典)
    """
    if not all([novel_name, chapter_filename, report_filename]):
        error_msg = "## 错误\n\n缺少必要参数，无法删除报告。"
        print(error_msg)
        return error_msg, {"choices": [], "value": None}

    try:
        chapter_name = os.path.splitext(chapter_filename)[0]
        report_path = os.path.join(REPORTS_BASE_DIR, novel_name, chapter_name, report_filename)

        if os.path.exists(report_path):
            os.remove(report_path)
            logger.info(f"已删除报告文件: {report_path}")

            # 清理空目录
            chapter_report_dir = os.path.dirname(report_path)
            if not os.listdir(chapter_report_dir):
                os.rmdir(chapter_report_dir)
                logger.info(f"已删除空的章节报告目录: {chapter_report_dir}")

                novel_report_dir = os.path.dirname(chapter_report_dir)
                if not os.listdir(novel_report_dir):
                    os.rmdir(novel_report_dir)
                    logger.info(f"已删除空的小说报告目录: {novel_report_dir}")

            # 刷新报告缓存
            report_cache.pop((novel_name, chapter_name), None)

            # 重新加载报告列表 (使用本模块内的函数)
            reports = get_report_list_with_cache(novel_name, chapter_filename)
            report_choices = [(rep.replace('.txt', ''), rep) for rep in reports]
            default_report = report_choices[0][1] if report_choices else None

            # 如果没有报告了，清空分析面板
            if not reports:
                new_report_content = "## AI 分析报告\n\n该章节的报告已被删除。"
                return new_report_content, {"choices": [], "value": None}
            else:
                # 加载新的默认报告 (使用本模块内的函数)
                new_report_content = load_report_content(novel_name, chapter_filename, default_report)
                return new_report_content, {"choices": report_choices, "value": default_report}
        else:
            error_msg = f"## 错误\n\n要删除的报告文件不存在: `{report_path}`"
            logger.error(error_msg)
            return error_msg, {}

    except Exception as e:
        error_msg = f"## 删除报告时出错\n\n{e}"
        logger.error(error_msg, exc_info=True)
        return error_msg, {}


# ========================
# 新增：报告排序逻辑
# ========================

def ensure_report_metadata_exists():
    """
    确保 metadata.json 存在。如果不存在，则根据 analyzer 目录下的 .txt 文件生成默认排序。
    """
    os.makedirs(PROMPT_ANALYZER_DIR, exist_ok=True)

    if not os.path.exists(METADATA_FILE_PATH):
        txt_files = []
        if os.path.exists(PROMPT_ANALYZER_DIR):
            txt_files = [f.replace('.txt', '') for f in os.listdir(PROMPT_ANALYZER_DIR) if f.endswith('.txt')]
        default_order = sorted(set(txt_files))  # 去重并排序
        with open(METADATA_FILE_PATH, 'w', encoding='utf-8') as f:
            json.dump({"report_order": default_order}, f, ensure_ascii=False, indent=2)
        logger.info(f"[INFO] 已创建默认报告排序文件: {METADATA_FILE_PATH}")


def get_report_order_from_metadata():
    """
    从 metadata.json 中读取报告排序列表。
    """
    ensure_report_metadata_exists()
    try:
        with open(METADATA_FILE_PATH, 'r', encoding='utf-8') as f:
            data = json.load(f)
        order = data.get("report_order", [])
        return order
    except Exception as e:
        logger.error(f"[ERROR] 读取报告排序元数据失败: {e}")
        return []


def sort_reports_by_metadata(report_filenames):
    """
    根据 metadata.json 中定义的顺序对报告文件名列表进行排序。

    Args:
        report_filenames (list): 包含 .txt 扩展名的报告文件名列表，如 ['角色分析.txt', '情节发展.txt']

    Returns:
        list: 排序后的报告文件名列表
    """
    order = get_report_order_from_metadata()
    order_map = {name: idx for idx, name in enumerate(order)}

    def sort_key(filename):
        base_name = os.path.splitext(filename)[0]
        return (order_map.get(base_name, len(order)), base_name)

    return sorted(report_filenames, key=sort_key)