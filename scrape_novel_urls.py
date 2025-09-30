import asyncio
import json
import os # 用于创建文件夹和处理路径
from crawl4ai import AsyncWebCrawler
from crawl4ai.extraction_strategy import JsonCssExtractionStrategy
from crawl4ai.async_configs import BrowserConfig, CrawlerRunConfig
from urllib.parse import urljoin

# --- 配置 ---
BASE_URL = "https://www.qidian.com"
TARGET_BOOKS = 100
HEADLESS = True
OUTPUT_DIR = "scraped_data_2025_9_30" # 定义保存文件的主目录

# --- 定义小说分类 ---
# 分类ID参考起点网页源码和常识
CATEGORIES = {
    "全部": {"id": "-1", "name": "全部"}, # -1 通常代表全部
    "玄幻": {"id": "21", "name": "玄幻"},
    "奇幻": {"id": "1", "name": "奇幻"},
    "武侠": {"id": "2", "name": "武侠"},
    "仙侠": {"id": "22", "name": "仙侠"},
    "都市": {"id": "4", "name": "都市"},
    "现实": {"id": "15", "name": "现实"},
    "军事": {"id": "6", "name": "军事"},
    "历史": {"id": "5", "name": "历史"},
    "游戏": {"id": "7", "name": "游戏"},
    "体育": {"id": "8", "name": "体育"},
    "科幻": {"id": "9", "name": "科幻"},
    "悬疑": {"id": "10", "name": "悬疑"},
    "轻小说": {"id": "12", "name": "轻小说"},
    # "短篇": {"id": "20076", "name": "短篇"}, # 可根据需要添加
}

# --- 创建输出目录 ---
os.makedirs(OUTPUT_DIR, exist_ok=True)
print(f"输出目录已创建或已存在: {OUTPUT_DIR}")

async def process_extracted_data(extracted_content_str, page_number):
    """处理已成功爬取并提取的 JSON 字符串内容。"""
    try:
        extracted_data = json.loads(extracted_content_str)
    except json.JSONDecodeError as e:
        return False, f"解析第 {page_number} 页提取内容失败 (JSON Error): {e}"

    if not isinstance(extracted_data, list):
        return False, f"第 {page_number} 页提取结果格式不符合预期 (不是列表)。"

    page_books = []
    for item in extracted_data:
        book_title = item.get('book_title', '').strip()
        raw_url = item.get('book_url', '')
        author = item.get('author', '').strip()
        category = item.get('category', '').strip()
        sub_category = item.get('sub_category', '').strip()
        status = item.get('status', '').strip()
        intro = item.get('intro', '').strip()
        update_info = item.get('update_info', '').strip()
        update_time = item.get('update_time', '').strip()
        month_ticket_count = item.get('month_ticket_count', '').strip()

        if book_title and raw_url:
            full_link = urljoin(BASE_URL, raw_url)
            page_books.append({
                "book_title": book_title,
                "book_url": full_link,
                "author": author,
                "category": category,
                "sub_category": sub_category,
                "status": status,
                "intro": intro,
                "update_info": update_info,
                "update_time": update_time,
                "month_ticket_count": month_ticket_count
            })
    return True, page_books

async def fetch_books_from_page(crawler, page_url, crawler_config, page_number):
    """从指定 URL 页面爬取并提取书籍信息。"""
    print(f"  正在爬取第 {page_number} 页: {page_url}")
    try:
        # 注意：bypass_cache 在 CrawlerRunConfig 中设置更合适
        result = await crawler.arun(url=page_url, config=crawler_config)
    except Exception as e:
        return False, f"爬取第 {page_number} 页时发生网络/浏览器错误: {e}"

    if not result.success:
        error_msg = result.error if result.error else "未知错误"
        return False, f"爬取第 {page_number} 页失败 (Crawler Error): {error_msg}"

    if not result.extracted_content:
        return False, f"爬取第 {page_number} 页成功但提取内容为空。"

    success, data_or_error = await process_extracted_data(
        result.extracted_content, page_number
    )
    return success, data_or_error

async def scrape_books_for_category(crawler, category_id, category_name, crawler_config, target_count, year="2025", month="09"):
    """爬取指定分类的月票榜前N本书。"""
    print(f"\n--- 开始爬取 {category_name} (ID: {category_id}) 的月票榜 ---")
    all_books = []
    current_page = 1

    while len(all_books) < target_count:
        # 构造分页 URL
        # 格式: /rank/yuepiao/chn<ID>/year<YYYY>-month<MM>-page<N>/
        # 首页省略 page1
        if current_page == 1:
            page_url = f"{BASE_URL}/rank/yuepiao/chn{category_id}/year{year}-month{month}/"
        else:
            page_url = f"{BASE_URL}/rank/yuepiao/chn{category_id}/year{year}-month{month}-page{current_page}/"

        success, data_or_error = await fetch_books_from_page(
            crawler, page_url, crawler_config, current_page
        )

        if success:
            page_books = data_or_error
            if not page_books:
                print(f"  第 {current_page} 页未提取到有效的书名和链接，可能已到最后一页。")
                break

            all_books.extend(page_books)
            print(f"  第 {current_page} 页提取到 {len(page_books)} 本书的信息。当前 {category_name} 总计: {len(all_books)}")

            if len(all_books) >= target_count:
                print(f"  已收集到 {category_name} 目标数量 {target_count} 本书的信息。")
                break
        else:
            print(data_or_error)
            if current_page == 1:
                 print(f"  无法获取 {category_name} 第一页数据，跳过此类别。")
                 return []
            break

        current_page += 1
        # await asyncio.sleep(1) # 可选延迟

    final_books = all_books[:target_count]
    print(f"--- 完成爬取 {category_name} 的月票榜，共获取 {len(final_books)} 本书 ---")
    return final_books

async def save_books_to_file(category_name, books):
    """将特定分类的书籍列表保存到指定文件夹下的文件中。"""
    if not books:
        print(f"  {category_name} 分类无数据可保存。")
        return

    # 创建该分类的文件名，使用分类名并替换可能影响文件系统的字符
    safe_category_name = "".join(c if c.isalnum() or c in " _-" else "_" for c in category_name)
    filename = f"{safe_category_name}_月票榜_top{len(books)}.txt"
    filepath = os.path.join(OUTPUT_DIR, filename) # 构建完整路径

    try:
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(f"==== {category_name} 月票榜 ====\n")
            f.write(f"总计: {len(books)} 本书\n\n")
            for i, book in enumerate(books, 1):
                f.write(f"{i:3d}. 《{book['book_title']}》\n")
                f.write(f"      作者: {book['author']}\n")
                f.write(f"      分类: {book['category']} · {book['sub_category']} | 状态: {book['status']}\n")
                f.write(f"      链接: {book['book_url']}\n")
                if book['intro']:
                    intro_cleaned = book['intro'].replace('\n', ' ').strip()
                    f.write(f"      简介: {intro_cleaned}\n")
                f.write(f"      最新: {book['update_info']} · {book['update_time']}\n")
                f.write("\n")
        print(f"  {category_name} 分类数据已保存至: {filepath}")
    except Exception as e:
        print(f"  保存 {category_name} 分类数据到 {filepath} 时出错: {e}")


async def scrape_qidian_yuepiao_by_category():
    """主函数：遍历定义的分类，爬取每个分类的月票榜前N本书并保存。"""
    browser_config = BrowserConfig(browser_type="chromium", headless=HEADLESS)

    extraction_strategy = JsonCssExtractionStrategy(
        schema={
            "name": "Qidian Monthly Ticket Ranking Books with Details",
            "baseSelector": "#rank-view-list li[data-rid]",
            "fields": [
                {
                    "name": "book_title",
                    "selector": "div.book-mid-info h2 a",
                    "type": "text",
                },
                {
                    "name": "book_url",
                    "selector": "div.book-mid-info h2 a",
                    "type": "attribute",
                    "attribute": "href",
                },
                {
                    "name": "author",
                    "selector": "p.author a.name",
                    "type": "text",
                },
                {
                    "name": "category",
                    "selector": "p.author a:nth-of-type(2)",
                    "type": "text",
                },
                {
                    "name": "sub_category",
                    "selector": "p.author a.go-sub-type",
                    "type": "text",
                },
                {
                    "name": "status",
                    "selector": "p.author span",
                    "type": "text",
                },
                {
                    "name": "intro",
                    "selector": "p.intro",
                    "type": "text",
                },
                {
                     "name": "update_info",
                     "selector": "p.update a",
                     "type": "text",
                },
                {
                     "name": "update_time",
                     "selector": "p.update span",
                     "type": "text",
                },
                {
                     "name": "month_ticket_count",
                     "selector": "div.book-right-info div.total p span span.GYCWTlhh",
                     "type": "text",
                },
            ],
        },
        verbose=False
    )

    crawler_config = CrawlerRunConfig(
        extraction_strategy=extraction_strategy,
        # bypass_cache=True # 如果需要强制刷新缓存，可以取消注释
    )

    all_results = {}

    async with AsyncWebCrawler(config=browser_config) as crawler:
        for cat_name, cat_info in CATEGORIES.items():
            cat_id = cat_info["id"]
            books = await scrape_books_for_category(
                crawler, cat_id, cat_name, crawler_config, TARGET_BOOKS
            )
            all_results[cat_name] = books

            # --- 新增：爬取完一个分类后立即保存 ---
            await save_books_to_file(cat_name, books)
            # --- 新增结束 ---

    print(f"\n--- 爬取所有分类完成 ---")
    total_books_collected = sum(len(books) for books in all_results.values())
    print(f"总共从 {len(all_results)} 个分类中获取到 {total_books_collected} 本书的信息。")

    # --- 可选：保存一个包含所有分类的汇总文件 ---
    summary_filename = os.path.join(OUTPUT_DIR, "所有分类月票榜汇总.txt")
    try:
        with open(summary_filename, "w", encoding="utf-8") as f:
            f.write(f"=== 起点中文网各分类月票榜前 {TARGET_BOOKS} 名 汇总 ===\n")
            f.write(f"--- 爬取完成时间: {asyncio.get_event_loop().time()} ---\n\n")
            for cat_name, books in all_results.items():
                f.write(f"==== {cat_name} ====\n")
                if books:
                    for i, book in enumerate(books, 1):
                        f.write(f"{i:3d}. 《{book['book_title']}》 - {book['book_url']}\n")
                else:
                     f.write("      (未获取到书籍信息)\n")
                f.write("\n")
        print(f"汇总文件已保存至: {summary_filename}")
    except Exception as e:
        print(f"保存汇总文件 {summary_filename} 时出错: {e}")
    # --- 可选结束 ---

    return all_results

if __name__ == "__main__":
    asyncio.run(scrape_qidian_yuepiao_by_category())