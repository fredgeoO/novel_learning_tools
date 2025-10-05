# utils/util_rankings.py
import os
import re
from typing import List, Dict, Optional

# --- 使用 config.py 的路径配置 ---
# 从 config.py 获取项目根目录
try:
    from config import PROJECT_ROOT
except ImportError:
    # 如果 config.py 不在项目根目录，回退到原来的逻辑
    UTIL_DIR = os.path.dirname(os.path.abspath(__file__))
    PROJECT_ROOT = os.path.dirname(UTIL_DIR)

# ✅ 使用 config.py 中定义的项目根目录
from utils.util_chapter import NOVELS_BASE_DIR

RANKING_FILE = os.path.join(PROJECT_ROOT, "scraped_data", "所有分类月票榜汇总.txt")


# --- 原有逻辑保持不变 ---
def parse_ranking_file(filepath=RANKING_FILE):
    if not os.path.exists(filepath):
        print(f"警告: 榜单文件 '{filepath}' 不存在。")
        print(f"当前工作目录: {os.getcwd()}")
        print(f"绝对路径检查: 文件存在 = {os.path.exists(filepath)}")
        return {}
    rankings = {}
    current_category = None
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                category_match = re.match(r"^====\s*(.*?)\s*====$", line)
                if category_match:
                    current_category = category_match.group(1).strip()
                    rankings[current_category] = []
                    continue
                if current_category and re.match(r"^\d+[.?!]?\s*", line):
                    parts = line.split(' - ', 1)
                    if len(parts) >= 2:
                        title_with_number = parts[0]
                        title_match = re.search(r'^\d+[.?!]?\s*[《\"](.+?)[》\"]', title_with_number)
                        title = title_match.group(1) if title_match else re.sub(r'^\d+[.?!]?\s*', '',
                                                                                title_with_number).strip('《》"')
                        if title:
                            rankings[current_category].append(title)
    except Exception as e:
        print(f"解析榜单文件时出错: {e}")
        import traceback
        traceback.print_exc()
    return rankings


RANKINGS_CACHE = parse_ranking_file()


def get_categories():
    return sorted(RANKINGS_CACHE.keys()) if RANKINGS_CACHE else []


def get_novel_list(filter_by_category=None, only_with_reports=False):
    from utils.util_chapter import has_any_reports

    if not os.path.exists(NOVELS_BASE_DIR):
        print(f"警告: 小说根目录 '{NOVELS_BASE_DIR}' 不存在。")
        print(f"当前工作目录: {os.getcwd()}")
        print(f"绝对路径检查: 目录存在 = {os.path.exists(NOVELS_BASE_DIR)}")
        return []

    try:
        local_novels = {
            name for name in os.listdir(NOVELS_BASE_DIR)
            if os.path.isdir(os.path.join(NOVELS_BASE_DIR, name))
        }

        if only_with_reports:
            local_novels = {n for n in local_novels if has_any_reports(n)}

        # 情况1: 明确指定了分类（包括 "全部"）
        if filter_by_category is not None:
            # 直接使用该分类的榜单，仅保留本地存在的
            ranked_novels = RANKINGS_CACHE.get(filter_by_category, [])
            return [n for n in ranked_novels if n in local_novels]

        # 情况2: 未指定分类（filter_by_category is None）
        # 此时才展示："全部"榜单中的本地小说 + 其他本地小说（按字母排序）
        all_ranked = RANKINGS_CACHE.get("全部", [])
        in_rank_and_local = [n for n in all_ranked if n in local_novels]
        remaining_local = sorted(local_novels - set(in_rank_and_local))
        return in_rank_and_local + remaining_local

    except Exception as e:
        print(f"获取小说列表时出错: {e}")
        import traceback
        traceback.print_exc()
        return []


def extract_top_novels_from_ranking(top_n: int = 10) -> List[str]:
    """
    从月票榜文件中提取前N本小说的名称

    Args:
        top_n: 要提取的小说数量，默认10

    Returns:
        List[str]: 提取的小说名称列表
    """
    ranking_file = os.path.join(PROJECT_ROOT, "scraped_data", "所有分类月票榜汇总.txt")

    if not os.path.exists(ranking_file):
        print(f"警告: 月票榜文件不存在: {ranking_file}")
        return []

    ranking_content = ""
    try:
        with open(ranking_file, 'r', encoding='utf-8') as f:
            ranking_content = f.read()
    except Exception as e:
        print(f"读取月票榜文件时出错: {e}")
        return []

    if not ranking_content:
        print("月票榜文件内容为空")
        return []

    novel_names = []
    lines = ranking_content.splitlines()
    in_any_category = False

    for line in lines:
        line = line.strip()
        if line.startswith("====") and line.endswith("===="):
            in_any_category = True
            continue
        if in_any_category:
            match = re.match(r'^\s*\d+\.\s*《(.+?)》\s*-', line)
            if match:
                novel_name = match.group(1).strip()
                if novel_name and novel_name not in novel_names:
                    novel_names.append(novel_name)
                if len(novel_names) >= top_n:
                    break

    return novel_names[:top_n]


def get_selected_chapters_for_novels(novel_names: List[str], chapters_per_novel: int = 3) -> Dict[str, List[str]]:
    """
    为指定的小说列表获取选定的章节

    Args:
        novel_names: 小说名称列表
        chapters_per_novel: 每本小说要分析的章节数量，默认3

    Returns:
        Dict[str, List[str]]: 小说名到章节文件名列表的映射
    """
    from utils.util_chapter import get_chapter_list

    selected_chapters = {}

    for novel_name in novel_names:
        all_chapter_files = get_chapter_list(novel_name)
        if not all_chapter_files:
            print(f"警告: 小说 '{novel_name}' 没有找到或没有可分析的章节文件。")
            continue

        chapter_files = all_chapter_files[:chapters_per_novel]
        selected_chapters[novel_name] = chapter_files

    return selected_chapters


def get_top_novels_and_chapters(top_n: int = 10, chapters_per_novel: int = 3) -> Dict[str, List[str]]:
    """
    获取前N本小说的前M章节

    Args:
        top_n: 要处理的小说数量
        chapters_per_novel: 每本小说要分析的章节数量

    Returns:
        Dict[str, List[str]]: 小说名到章节文件名列表的映射
    """
    # 提取前N本小说
    selected_novels = extract_top_novels_from_ranking(top_n)

    if not selected_novels:
        print("警告: 未从月票榜文件中解析出任何小说名称。")
        return {}

    # 获取选定的章节
    selected_chapters = get_selected_chapters_for_novels(selected_novels, chapters_per_novel)

    return selected_chapters