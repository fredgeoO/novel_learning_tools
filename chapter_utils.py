# chapter_utils.py
import os
import glob
import re
import json
import logging

# --- 配置 ---
# 日志配置 (如果主程序已有，可以考虑移除或简化)
logging.basicConfig(level=logging.INFO, format='[%(asctime)s] [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

NOVELS_BASE_DIR = "novels"  # 与主程序保持一致
REPORTS_BASE_DIR = "reports/novels"  # 对应 reports/novels 结构

# --- 新增：章节状态常量 (与主程序保持一致) ---
CHAPTER_STATUS_PENDING = "pending"
CHAPTER_STATUS_DOWNLOADED = "downloaded"
CHAPTER_STATUS_FAILED = "failed"
# --- 新增结束 ---

# --- 缓存变量 ---
chapter_cache = {}
report_cache = {}
novel_cache  = {}

# --- 章节筛选和排序逻辑 ---

# 扩展中文数字映射，包含更多可能用于章节标题的字
CHINESE_NUMBER_MAP = {
    # 基本数字
    "〇": 0, "零": 0, "一": 1, "二": 2, "三": 3, "四": 4, "五": 5,
    "六": 6, "七": 7, "八": 8, "九": 9,
    # 十位数
    "十": 10, "廿": 20, "卅": 30,
    # 十位组合 (10-19)
    "十一": 11, "十二": 12, "十三": 13, "十四": 14, "十五": 15,
    "十六": 16, "十七": 17, "十八": 18, "十九": 19,
    # 整十 (20-90)
    "二十": 20, "三十": 30, "四十": 40, "五十": 50,
    "六十": 60, "七十": 70, "八十": 80, "九十": 90,
    # 复合十位 (21-99)
    "二十一": 21, "二十二": 22, "二十三": 23, "二十四": 24, "二十五": 25,
    "二十六": 26, "二十七": 27, "二十八": 28, "二十九": 29,
    "三十一": 31, "三十二": 32, "三十三": 33, "三十四": 34, "三十五": 35,
    "三十六": 36, "三十七": 37, "三十八": 38, "三十九": 39,
    "四十一": 41, "四十二": 42, "四十三": 43, "四十四": 44, "四十五": 45,
    "四十六": 46, "四十七": 47, "四十八": 48, "四十九": 49,
    "五十一": 51, "五十二": 52, "五十三": 53, "五十四": 54, "五十五": 55,
    "五十六": 56, "五十七": 57, "五十八": 58, "五十九": 59,
    "六十一": 61, "六十二": 62, "六十三": 63, "六十四": 64, "六十五": 65,
    "六十六": 66, "六十七": 67, "六十八": 68, "六十九": 69,
    "七十一": 71, "七十二": 72, "七十三": 73, "七十四": 74, "七十五": 75,
    "七十六": 76, "七十七": 77, "七十八": 78, "七十九": 79,
    "八十一": 81, "八十二": 82, "八十三": 83, "八十四": 84, "八十五": 85,
    "八十六": 86, "八十七": 87, "八十八": 88, "八十九": 89,
    "九十一": 91, "九十二": 92, "九十三": 93, "九十四": 94, "九十五": 95,
    "九十六": 96, "九十七": 97, "九十八": 98, "九十九": 99,
    # 百位及以上
    "一百": 100, "皕": 200, # 稍微高级一点的字
    # 大写数字 (虽然不常见于章节名，但为完整性加入)
    "壹": 1, "贰": 2, "叁": 3, "肆": 4, "伍": 5, "陆": 6, "柒": 7, "捌": 8, "玖": 9,
    "拾": 10, "佰": 100, "仟": 1000,
    # 更大单位 (通常用于序数，但映射有助于识别)
    "萬": 10000, "亿": 100000000, "兆": 1000000000000
}

def chinese_to_arabic_simple(chinese_str):
    """
    将中文数字字符串转换为整数。
    优先使用 CHINESE_NUMBER_MAP 进行直接查找。
    如果找不到，则尝试简单组合（适用于较复杂的数字，如 "一百零一"）。
    """
    # 1. 直接查找
    if chinese_str in CHINESE_NUMBER_MAP:
        return CHINESE_NUMBER_MAP[chinese_str]

    # 2. 如果直接查找失败，尝试简单组合逻辑 (适用于 "一百零一", "三十五" 等)
    #    注意：这是一个简化版本，可能不处理所有边界情况，但对于章节标题通常足够。
    total = 0
    current_number = 0
    unit = 1
    i = len(chinese_str) - 1

    while i >= 0:
        char = chinese_str[i]
        char_value = CHINESE_NUMBER_MAP.get(char, 0)

        if char in ['零', '〇']:
            # 零通常不改变值，但可能影响单位
            pass
        elif char == '十':
            unit = 10
            if i == 0: # 处理 "十" 开头的情况，如 "十三"
                current_number = 1
        elif char == '百' or char == '佰':
            unit = 100
        elif char == '千' or char == '仟':
            unit = 1000
        elif char == '万' or char == '萬':
            unit = 10000
            total += current_number * unit
            current_number = 0
        elif char == '亿':
            unit = 100000000
            total += current_number * unit
            current_number = 0
        elif char == '兆':
            unit = 1000000000000
            total += current_number * unit
            current_number = 0
        else:
            # 是基本数字字符 (一, 二, 三, ..., 九, 壹, 贰, ...)
            current_number += char_value * unit
            unit = 1 # 重置单位为1，用于下一个基本数字
        i -= 1

    total += current_number
    # 如果解析结果为0（可能输入了无效字符或空字符串），返回无穷大以排在最后
    return total if total > 0 else float('inf')


def roman_to_arabic(roman_str):
    """
    将罗马数字字符串转换为阿拉伯数字整数。
    """
    if not roman_str:
        return float('inf')
    roman_str = roman_str.upper()
    roman_values = {
        'I': 1, 'V': 5, 'X': 10, 'L': 50,
        'C': 100, 'D': 500, 'M': 1000
    }

    total = 0
    prev_value = 0

    for char in reversed(roman_str):
        value = roman_values.get(char, 0)
        if value == 0: # 如果遇到无效字符，解析失败
             return float('inf')
        if value < prev_value:
            total -= value
        else:
            total += value
        prev_value = value

    return total if total > 0 else float('inf')


def extract_chapter_number(chapter_title):
    """
    从章节标题中提取章节号，并转换为可比较的整数。
    支持 "第X章" 格式，其中 X 可以是阿拉伯数字、中文数字或罗马数字。
    也支持纯数字开头的格式，如 "001.", "1 "。
    """
    # 1. 首先尝试匹配 "第X章/回/节..." 格式
    match = re.search(
        r"第\s*((?:[0-9]+|[一二三四五六七八九十〇零壹贰叁肆伍陆柒捌玖拾佰仟萬亿兆廿卅皕]+|[IVXLCDMivxlcdm]+)+)\s*[章回节篇幕集话卷]",
        chapter_title
    )
    if match:
        number_str = match.group(1).strip()
        # 尝试转换阿拉伯数字
        try:
            return int(number_str)
        except ValueError:
            pass
        # 尝试转换中文数字 (使用改进的函数)
        try:
            res = chinese_to_arabic_simple(number_str)
            if res != float('inf'):
                return res
        except:
            pass
        # 尝试转换罗马数字
        try:
            res = roman_to_arabic(number_str)
            if res != float('inf'):
                return res
        except:
            pass

    # 2. 如果第一步失败，尝试匹配纯数字开头的格式 (如 "001.", "1 ")
    pure_number_match = re.match(r'^\s*(\d+)\s*[.、 ]', chapter_title)
    if pure_number_match:
        try:
            return int(pure_number_match.group(1))
        except ValueError:
            pass

    # 3. 如果都失败了，尝试在标题中查找任何阿拉伯数字 (作为后备)
    arabic_match = re.search(r'\d+', chapter_title)
    if arabic_match:
        try:
            return int(arabic_match.group())
        except ValueError:
            pass

    # 4. 最后，如果所有方法都失败，返回无穷大
    return float('inf')


def get_chapter_list(novel_name):
    """
    根据小说名获取其章节列表 (txt文件名列表，不含路径)，并按章节号智能排序。
    筛选符合章节标题模式的文件（包括 "第X章" 和纯数字开头如 "001." 的格式）。
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
        # 1. 匹配 "第X章/回/节..." 格式，X 可以是阿拉伯数字、中文数字或罗马数字
        # 2. 匹配以纯数字开头，后跟 . 、 、或空格 的格式 (如 "001.", "1 ", "10、")
        CHAPTER_PATTERN = re.compile(
            r"(?:第\s*([0-9]+|[一二三四五六七八九十〇零壹贰叁肆伍陆柒捌玖拾佰仟萬亿兆廿卅皕IVXLCDMivxlcdm]+)\s*[章回节篇幕集话卷])"
            r"|(?:^\s*\d+\s*[.、 ])",
            re.IGNORECASE
        )

        # 筛选有效的章节文件
        filtered_chapters = []
        for chapter in chapter_names:
            # 移除文件扩展名
            chapter_title = os.path.splitext(chapter)[0]

            # 检查是否符合章节标题模式
            matches_chapter_pattern = bool(CHAPTER_PATTERN.search(chapter_title))

            # --- 修改后的过滤逻辑 ---
            # 只要符合章节模式，就通过筛选
            if matches_chapter_pattern:
                filtered_chapters.append(chapter)
            # --- 修改结束 ---

        # --- 智能排序 ---
        # 对筛选后的章节进行排序，使用 extract_chapter_number 提取的数值作为 key
        if filtered_chapters:
            return sorted(filtered_chapters, key=lambda x: extract_chapter_number(os.path.splitext(x)[0]))
        else:
            # 如果没有符合模式的章节，返回空列表
            logger.info(f"信息: 小说 '{novel_name}' 没有找到符合章节模式的文件。")
            return []

    except Exception as e:
        logger.error(f"获取章节列表时出错 for '{novel_name}': {e}")
        import traceback
        traceback.print_exc()
        return [] # 发生异常时返回空列表


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
    获取报告列表并检查是否有更新。
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

        return current_files
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
    加载报告内容，过滤 think 标签，并过滤掉少于3个字符的行。
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

        # 1. 过滤掉 <think> 标签及其内容
        content_without_think = filter_think_tags(raw_content)

        # 2. 按行分割，过滤掉少于3个字符的行（去除前后空格后判断）
        lines = content_without_think.splitlines()
        filtered_lines = [line for line in lines if len(line.strip()) >= 3]
        final_content = '\n'.join(filtered_lines)

        return final_content
    except Exception as e:
        error_msg = f"## 读取错误\n\n读取报告文件时出错: `{e}`"
        logger.error(error_msg)
        return error_msg


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


def get_filtered_chapters_with_reports(novel_name):
    """获取小说中存在分析报告的章节"""
    novel_report_dir = os.path.join(REPORTS_BASE_DIR, novel_name)
    if not os.path.exists(novel_report_dir):
        return []
    chapter_dirs = [d.name for d in os.scandir(novel_report_dir) if d.is_dir()]
    # 章节文件名和目录名一致，例如 chapter_1.txt -> chapter_1
    return sorted([f"{ch}.txt" for ch in chapter_dirs])


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
import shutil


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

# --- 新增结束 ---