import re


def extract_book_info(line):
    """从一行文本中提取编号、书名和链接。"""
    match = re.match(r'^(\d+)\.\s*《(.+?)》\s*-\s*(https?://[^\s]+)$', line.strip())
    if match:
        return int(match.group(1)), match.group(2), match.group(3)
    else:
        return None, None, None


def parse_file_by_categories(file_path):
    """
    按分类解析文件，返回一个字典，键为分类名，值为 [(原始编号, 书名, 链接)] 列表。
    """
    print(f"  - 解析文件: {file_path}")
    categories = {}
    current_category = "UNKNOWN"  # 用于处理开头无分类的情况
    categories[current_category] = []

    with open(file_path, 'r', encoding='utf-8') as f:
        for line_num, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue

            category_match = re.match(r'^====\s*(.+?)\s*====', line)
            if category_match:
                current_category = category_match.group(1)
                if current_category not in categories:
                    categories[current_category] = []
                print(f"    - 找到分类: {current_category}")
                continue

            book_num, book_title, book_url = extract_book_info(line)
            if book_num is not None:
                # print(f"    - 解析书籍: {book_num}. 《{book_title}》 - {book_url}") # Debug
                categories[current_category].append((book_num, book_title, book_url))
            # else:
            # print(f"    - 忽略非书籍行 (L{line_num}): {line[:50]}...") # Debug

    return categories


def merge_and_dedupe_categories(cat1, cat2):
    """
    合并两个分类字典，并在每个分类内去重。
    """
    print("开始合并和去重...")
    all_category_names = set(cat1.keys()).union(set(cat2.keys()))
    merged_result = {}

    for cat_name in all_category_names:
        print(f"  - 处理分类: {cat_name}")
        books1 = cat1.get(cat_name, [])
        books2 = cat2.get(cat_name, [])

        seen_urls = set()
        unique_books_list = []

        # 按顺序处理 books1 和 books2，确保首次出现的被保留
        for num, title, url in books1 + books2:  # 先file1，后file2
            if url not in seen_urls:
                unique_books_list.append((num, title, url))  # 暂时保留原始编号
                seen_urls.add(url)
            # else:
            #     print(f"    - 发现重复 (来自后续文件): 《{title}》 - {url}")

        # 重新排序（按原始编号）并分配新编号
        unique_books_list.sort(key=lambda x: x[0])
        renumbered_books = []
        for i, (orig_num, title, url) in enumerate(unique_books_list, start=1):
            renumbered_books.append((i, title, url))
        print(f"    - 分类 '{cat_name}' 最终书籍数量: {len(renumbered_books)}")
        merged_result[cat_name] = renumbered_books

    return merged_result


def write_output(merged_data, output_path, original_order_file_path):
    """
    写入输出文件，尝试保持原始分类顺序。
    """
    print(f"开始写入文件: {output_path}")
    # 获取原始顺序（优先使用第一个文件的顺序）
    original_order = []
    seen_cats = set()
    for path in [original_order_file_path]:  # 可以扩展为 [file1, file2] 来混合顺序
        with open(path, 'r', encoding='utf-8') as f:
            for line in f:
                cat_match = re.match(r'^====\s*(.+?)\s*====', line.strip())
                if cat_match:
                    cat_name = cat_match.group(1)
                    if cat_name not in seen_cats:
                        original_order.append(cat_name)
                        seen_cats.add(cat_name)

    with open(output_path, 'w', encoding='utf-8') as f:
        # 按原始顺序写入
        for cat_name in original_order:
            if cat_name in merged_data:
                f.write(f"==== {cat_name} ====\n")
                for num, title, url in merged_data[cat_name]:
                    f.write(f"{num}. 《{title}》 - {url}\n")
                f.write("\n")

        # 写入其他不在原始顺序中的分类 (如 UNKNOWN 或 file2 中独有的分类)
        for cat_name in merged_data:
            if cat_name not in original_order:
                f.write(f"==== {cat_name} ====\n")
                for num, title, url in merged_data[cat_name]:
                    f.write(f"{num}. 《{title}》 - {url}\n")
                f.write("\n")

# --- 使用说明 ---
# 请将 'file1.txt', 'file2.txt', 'merged_output.txt' 替换为你实际的文件名
input_file_1 = '所有分类月票榜汇总1.txt'
input_file_2 = '所有分类月票榜汇总2.txt'
output_file = '整合月票榜.txt'

print("开始解析文件...")
categories1 = parse_file_by_categories(input_file_1)
categories2 = parse_file_by_categories(input_file_2)

print("\n开始合并...")
merged_categories = merge_and_dedupe_categories(categories1, categories2)

print("\n开始写入输出文件...")
write_output(merged_categories, output_file, input_file_1) # 使用 file1 的顺序

print(f"\n合并完成！结果已保存到 '{output_file}'")

# --- 验证输出数量 ---
print("\n--- 验证信息 ---")
total_books = 0
for cat_name, book_list in merged_categories.items():
    count = len(book_list)
    print(f"分类 '{cat_name}': {count} 本")
    total_books += count
print(f"总计书籍数量: {total_books}")

# 检查是否有明显的重复
all_urls = []
for cat_name, book_list in merged_categories.items():
    for _, _, url in book_list:
        all_urls.append(url)

if len(all_urls) != len(set(all_urls)):
    print("警告: 检测到最终结果中存在重复的URL！")
else:
    print("验证通过: 所有书籍链接均唯一。")