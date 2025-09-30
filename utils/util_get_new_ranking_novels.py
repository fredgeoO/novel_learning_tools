import re

def extract_books_from_line(line):
    """从一行文本中提取所有可能的书籍信息 (编号, 书名, 链接)。"""
    # 使用 finditer 查找一行中所有匹配项
    pattern = r'(\d+)\.\s*《(.+?)》\s*-\s*(https?://[^\s]+)'
    matches = list(re.finditer(pattern, line.strip()))
    # 返回所有匹配到的书籍元组列表
    return [(int(m.group(1)), m.group(2), m.group(3)) for m in matches]

def parse_file_to_books_and_categories(file_path):
    """
    解析文件，返回所有书籍链接的集合和按分类组织的 (编号, 书名, 链接) 列表。
    现在能处理一行包含多个书籍条目的情况。
    """
    print(f"解析文件: {file_path}")
    all_urls = set()
    categorized_books = {}
    current_category = "UNKNOWN" # 处理开头无分类的情况
    categorized_books[current_category] = []

    with open(file_path, 'r', encoding='utf-8') as f:
        for line_num, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue

            category_match = re.match(r'^====\s*(.+?)\s*====', line)
            if category_match:
                current_category = category_match.group(1)
                if current_category not in categorized_books:
                    categorized_books[current_category] = []
                print(f"  - 找到分类: {current_category}")
                continue

            # 尝试从当前行提取所有书籍
            found_books = extract_books_from_line(line)
            if found_books:
                for num, title, url in found_books:
                    all_urls.add(url)
                    categorized_books[current_category].append((num, title, url))
                # print(f"    - 解析书籍 ({len(found_books)} 本): ...") # Debug
            # else:
                # print(f"    - 忽略非书籍行 (L{line_num}): {line[:50]}...") # Debug

    return all_urls, categorized_books

def find_new_books(file1_path, file2_path):
    """
    找出 file2 中相对于 file1 来说是新增的书籍。
    """
    print(f"解析文件1: {file1_path} (获取已有书籍链接)")
    file1_urls, _ = parse_file_to_books_and_categories(file1_path)

    print(f"解析文件2: {file2_path} (获取所有书籍)")
    _, file2_categorized_books = parse_file_to_books_and_categories(file2_path)

    new_books_by_category = {}
    for cat_name, book_list in file2_categorized_books.items():
        new_books_by_category[cat_name] = []
        for num, title, url in book_list:
            if url not in file1_urls:
                new_books_by_category[cat_name].append((num, title, url))
                # print(f"  - 新增: [{cat_name}] {num}. 《{title}》 - {url}") # Debug

    return new_books_by_category

def write_new_books(new_books_data, output_path):
    """
    将新增书籍写入文件，保持其原始分类。
    """
    print(f"写入新增书籍到: {output_path}")
    with open(output_path, 'w', encoding='utf-8') as f:
        for cat_name, book_list in new_books_data.items():
            if not book_list: # 如果这个分类下没有新增书籍，跳过
                continue
            f.write(f"==== {cat_name} ====\n")
            # 重新编号，从1开始
            for i, (orig_num, title, url) in enumerate(book_list, start=1):
                f.write(f"{i}. 《{title}》 - {url}\n")
            f.write("\n") # 分类之间空一行



# --- 主程序 ---
input_file_1 = '所有分类月票榜汇总1.txt'
input_file_2 = '所有分类月票榜汇总2.txt'
output_file = '新增月票榜.txt'

print("开始查找新增书籍...")
newly_added_books = find_new_books(input_file_1, input_file_2)

# 过滤掉没有新增书籍的分类
newly_added_books = {k: v for k, v in newly_added_books.items() if v}

print(f"找到 {len(newly_added_books)} 个包含新增书籍的分类。")
write_new_books(newly_added_books, output_file)

print(f"查找完成！新增书籍已保存到 '{output_file}'")

# --- 验证信息 ---
total_new_books = sum(len(books) for books in newly_added_books.values())
print(f"\n--- 验证信息 ---")
print(f"总计找到新增书籍: {total_new_books} 本")
for cat, books in newly_added_books.items():
    print(f"  - 分类 '{cat}': {len(books)} 本")

# 检查 file1 中的书籍是否真的在结果中被排除
print("\n--- 简单交叉验证 ---")
# 重新解析 file1 获取其 URL 集合
file1_urls, _ = parse_file_to_books_and_categories(input_file_1)
all_new_urls = set()
for book_list in newly_added_books.values():
    for _, _, url in book_list:
        all_new_urls.add(url)

overlap = file1_urls.intersection(all_new_urls)
if overlap:
    print(f"错误: 发现 {len(overlap)} 个书籍链接同时存在于原榜单和新增榜单中！")
    for url in list(overlap)[:5]: # 只打印前5个
        print(f"  - {url}")
else:
    print("验证通过: 新增书籍列表与原榜单无交集。")
