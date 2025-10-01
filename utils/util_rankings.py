# utils/util_rankings.py
import os
import re

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
        # 此时才展示：“全部”榜单中的本地小说 + 其他本地小说（按字母排序）
        all_ranked = RANKINGS_CACHE.get("全部", [])
        in_rank_and_local = [n for n in all_ranked if n in local_novels]
        remaining_local = sorted(local_novels - set(in_rank_and_local))
        return in_rank_and_local + remaining_local

    except Exception as e:
        print(f"获取小说列表时出错: {e}")
        import traceback
        traceback.print_exc()
        return []