# utils/util_rankings.py
import os
import re

# --- 获取绝对路径 ---
# 获取当前文件所在目录
UTIL_DIR = os.path.dirname(os.path.abspath(__file__))
# 项目根目录 = utils/ 的父目录
PROJECT_ROOT = os.path.dirname(UTIL_DIR)

# ✅ 使用绝对路径
from utils.util_chapter import NOVELS_BASE_DIR
RANKING_FILE = os.path.join(PROJECT_ROOT, "scraped_data", "所有分类月票榜汇总.txt")

print(f"[util_rankings] Novels dir: {NOVELS_BASE_DIR}")
print(f"[util_rankings] Ranking file: {RANKING_FILE}")


# --- 原有逻辑保持不变 ---
def parse_ranking_file(filepath=RANKING_FILE):
    if not os.path.exists(filepath):
        print(f"警告: 榜单文件 '{filepath}' 不存在。")
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
    from utils.util_chapter import has_any_reports  # 保持原有导入

    # ✅ 现在 NOVELS_BASE_DIR 是绝对路径，安全！
    if not os.path.exists(NOVELS_BASE_DIR):
        print(f"警告: 小说根目录 '{NOVELS_BASE_DIR}' 不存在。")
        return []

    try:
        local_novels = {
            name for name in os.listdir(NOVELS_BASE_DIR)
            if os.path.isdir(os.path.join(NOVELS_BASE_DIR, name))
        }

        if only_with_reports:
            local_novels = {n for n in local_novels if has_any_reports(n)}

        if filter_by_category and filter_by_category != "全部":
            category_novels = RANKINGS_CACHE.get(filter_by_category, [])
            return [n for n in category_novels if n in local_novels]
        else:
            all_in_rank = RANKINGS_CACHE.get("全部", [])
            sorted_novels = [n for n in all_in_rank if n in local_novels]
            remaining = sorted(local_novels - set(sorted_novels))
            return sorted_novels + remaining

    except Exception as e:
        print(f"获取小说列表时出错: {e}")
        import traceback
        traceback.print_exc()
        return []