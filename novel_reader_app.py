#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
小说叙事分析浏览器

这是一个基于 Gradio 的 Web 应用程序，用于浏览和分析小说章节内容及其对应的 AI 分析报告。

主要功能：
- 按分类浏览小说（支持月票榜分类）
- 查看小说章节内容（支持智能章节排序，包括中文数字章节）
- 查看章节的 AI 分析报告
- 筛选功能：仅显示有分析报告的小说/章节
- 报告管理：删除不需要的分析报告

目录结构要求：
- novels/ - 存放小说章节文本文件
- reports/novels/ - 存放对应的小说分析报告
- scraped_data/所有分类月票榜汇总.txt - 可选的小说分类榜单文件

作者：FredgeoO
日期：2025
"""

import os
import glob
import gradio as gr
import re

# --- 配置 ---
NOVELS_BASE_DIR = "novels"
REPORTS_BASE_DIR = "reports/novels"

# --- 从 chapter_utils 导入通用功能 ---
# --- 从 chapter_utils 导入通用功能 ---
from chapter_utils import (
    get_chapter_list_with_cache as get_chapter_list,
    get_report_list_with_cache as get_report_list,
    load_chapter_and_initial_report,
    load_report_content,
    novel_cache,
    has_any_reports,
    get_filtered_chapters_with_reports,
    delete_report_file
)

# --- 月票榜解析逻辑 ---
def parse_ranking_file(filepath="scraped_data/所有分类月票榜汇总.txt"):
    if not os.path.exists(filepath):
        print(f"警告: 榜单文件 '{filepath}' 不存在。")
        return {}
    rankings = {}
    current_category = None
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line: continue
                category_match = re.match(r"^====\s*(.*?)\s*====$", line)
                if category_match:
                    current_category = category_match.group(1).strip()
                    rankings[current_category] = []
                    continue
                if current_category and re.match(r"^\d+[.?!]?\s*", line):
                    parts = line.split(' - ', 1)
                    if len(parts) >= 2:
                        title_with_number = parts[0]
                        url = parts[1].strip()
                        title_match = re.search(r'^\d+[.?!]?\s*[《\"](.+?)[》\"]', title_with_number)
                        title = title_match.group(1) if title_match else re.sub(r'^\d+[.?!]?\s*', '',
                                                                                title_with_number).strip('《》"')
                        if title:
                            # 简化存储，只存标题，保持顺序
                            rankings[current_category].append(title)
    except Exception as e:
        print(f"解析榜单文件时出错: {e}")
        import traceback
        traceback.print_exc()
    return rankings

RANKINGS_CACHE = parse_ranking_file()

def get_categories():
    return sorted(RANKINGS_CACHE.keys()) if RANKINGS_CACHE else []

# --- 新增功能函数 ---
def get_novel_list(filter_by_category=None, only_with_reports=False):
    if not os.path.exists(NOVELS_BASE_DIR):
        print(f"警告: 小说根目录 '{NOVELS_BASE_DIR}' 不存在。")
        return []
    try:
        local_novel_names_set = {name for name in os.listdir(NOVELS_BASE_DIR)
                                 if os.path.isdir(os.path.join(NOVELS_BASE_DIR, name))}

        if only_with_reports:
            local_novel_names_set = {name for name in local_novel_names_set if has_any_reports(name)}

        key = filter_by_category or "全部"
        current_list = sorted(local_novel_names_set)
        cached = novel_cache.get(key)

        if cached is None or set(cached) != set(current_list):
            print(f"[刷新] 小说列表发生变化: {key}")
            novel_cache[key] = current_list

        if filter_by_category and filter_by_category != "全部":
            category_novels = RANKINGS_CACHE.get(filter_by_category, [])
            return [name for name in category_novels if name in local_novel_names_set]
        else:
            all_category_novels = RANKINGS_CACHE.get("全部", [])
            sorted_all_novels = [name for name in all_category_novels if name in local_novel_names_set]
            remaining_novels = list(local_novel_names_set - set(sorted_all_novels))
            return sorted_all_novels + sorted(remaining_novels)
    except Exception as e:
        print(f"获取小说列表时出错: {e}")
        import traceback
        traceback.print_exc()
        return []

# --- 更新函数（支持checkbox）---
def update_novels_on_category_change(selected_category, only_with_reports):
    novels = get_novel_list(filter_by_category=selected_category if selected_category != "全部" else None,
                            only_with_reports=only_with_reports)
    default_novel = novels[0] if novels else None

    if default_novel:
        # 获取章节更新信息
        chapters_update, reports_update = update_chapters_and_clear_reports(default_novel, only_with_reports)

        # 安全地获取选中的章节
        if isinstance(chapters_update, dict) and 'value' in chapters_update:
            selected_chapter = chapters_update['value']
            if selected_chapter:
                # 更新报告选择器和内容
                reports_update, chapter_content, report_content = update_reports_and_load_content(
                    default_novel, selected_chapter
                )
                return (
                    gr.update(choices=novels, value=default_novel),
                    chapters_update,
                    reports_update
                )

    # 如果没有小说或出错，返回空状态
    return (
        gr.update(choices=novels, value=default_novel),
        gr.update(choices=[], value=None),
        gr.update(choices=[], value=None)
    )

def update_chapters_and_clear_reports(selected_novel, only_with_reports):
    if not selected_novel:
        return gr.update(choices=[], value=None), gr.update(choices=[], value=None)

    if only_with_reports:
        chapters = get_filtered_chapters_with_reports(selected_novel)
    else:
        chapters = get_chapter_list(selected_novel)

    # 移除 .txt 扩展名用于显示
    chapter_choices = [(chap.replace('.txt', ''), chap) for chap in chapters]
    default_chapter = chapter_choices[0][1] if chapter_choices else None
    return gr.update(choices=chapter_choices, value=default_chapter), gr.update(choices=[], value=None)

def update_reports_and_load_content(novel_name, chapter_filename):
    if not novel_name or not chapter_filename:
        return gr.update(choices=[],
                         value=None), "## 请选择小说和章节\n\n在左侧选择一本小说和一个章节开始阅读。", "## AI 分析报告\n\n选择章节后，AI 分析结果将在此显示。"

    # 使用带缓存的新函数
    reports = get_report_list(novel_name, chapter_filename)

    # 移除 .txt 扩展名用于显示
    report_choices = [(rep.replace('.txt', ''), rep) for rep in reports]
    default_report = report_choices[0][1] if report_choices else None

    # 使用更新后的函数加载内容
    chapter_content, report_content = load_chapter_and_initial_report(novel_name, chapter_filename)
    return gr.update(choices=report_choices, value=default_report), chapter_content, report_content

def fn_load_selected_report(novel_name, chapter_filename, report_filename):
    if not all([novel_name, chapter_filename, report_filename]):
        return "## AI 分析报告\n\n请选择一个报告文件。"
    return load_report_content(novel_name, chapter_filename, report_filename)

# --- 新增：Gradio 删除报告调用函数 ---
def fn_delete_selected_report(novel_name, chapter_filename, report_filename):
    """
    Gradio 接口函数，调用 chapter_utils 中的删除逻辑。
    """
    # 调用 chapter_utils 中的函数
    new_report_content, selector_update_dict = delete_report_file(novel_name, chapter_filename, report_filename)

    # 将字典转换为 gr.update 对象
    updated_report_selector = gr.update(**selector_update_dict) if selector_update_dict else gr.update()

    # 返回用于更新 UI 的值
    return (
        gr.update(visible=True),  # delete_report_button
        gr.update(visible=False),  # delete_confirm_button
        gr.update(visible=False),  # delete_cancel_button
        gr.update(value=f"✅ 报告已删除。", visible=True),  # delete_status
        new_report_content,  # analysis_output
        updated_report_selector  # report_selector
    )

# --- Gradio 界面和逻辑 ---
css_for_app = """
html, body { height: 100%; margin: 0; padding: 0; overflow: hidden; }
gradio-app { height: 100vh !important; overflow: hidden !important; }
div.gradio-container { height: 100vh !important; max-height: 100vh !important; overflow: hidden !important; margin: 0 !important; padding: 0 !important; }
.app-header { text-align: center; padding: 10px !important; background-color: #1f2937; margin: 0 !important; flex-shrink: 0; }
.app-header h1 { margin: 0 !important; color: #f3f4f6; }
.main-container { height: calc(100vh - 60px) !important; overflow: hidden !important; margin: 0 !important; padding: 0 !important; }
.sidebar-container { background-color: #1f2937; height: 100%; overflow: hidden; display: flex !important; flex-direction: column !important; }
.selection-section { padding: 15px; border-bottom: 1px solid #4b5563; flex-shrink: 0; }
.placeholder-section { flex-grow: 1; padding: 15px; overflow-y: auto; }
.placeholder-section h3 { color: #f3f4f6; margin-top: 0; }
.main-content-container { height: 100%; overflow: hidden; display: flex !important; flex-direction: row !important; }
.novel-content-panel { flex: 1; height: 100%; overflow-y: auto; padding: 20px; background-color: #111827; color: #d1d5db; font-family: 'Georgia', serif; font-size: 16px; box-sizing: border-box; }
.novel-content-panel h1, .novel-content-panel h2, .novel-content-panel h3 { color: #ffffff; border-bottom: 1px solid #4b5563; padding-bottom: 5px; }
.ai-analysis-panel { flex: 1; height: 100%; overflow-y: auto; padding: 20px; background-color: #111827; color: #d1d5db; font-size: 15px; box-sizing: border-box; border-left: 1px solid #4b5563; }
.ai-analysis-panel h1, .ai-analysis-panel h2, .ai-analysis-panel h3 { color: #ffffff; }
.sidebar-container .wrap-inner { background-color: #374151; border: 1px solid #4b5563; border-radius: 4px; color: #f3f4f6; }
.sidebar-container label { display: block; margin-bottom: 8px; font-weight: bold; color: #f3f4f6; }
.gradio-column { height: 100%; }
.narrow-dropdown {
    width: 75%;
    max-width: 250px;
}
"""

with gr.Blocks(title="📖 小说叙事分析", theme=gr.themes.Soft(primary_hue="slate", secondary_hue="stone"),
               css=css_for_app) as demo:
    with gr.Row(elem_classes=["main-container"]):
        with gr.Column(elem_classes=["sidebar-container"], scale=1,min_width=250):
            with gr.Column(elem_classes=["selection-section"], scale=1,):
                category_selector = gr.Dropdown(choices=["全部"] + get_categories(), value="全部", label="🏷️ 选择分类",
                                                interactive=True)
                novel_selector = gr.Dropdown(choices=get_novel_list(), label="📚 选择小说", interactive=True)
                chapter_selector = gr.Dropdown(choices=[], label="📄 选择章节", interactive=True)
                report_selector = gr.Dropdown(choices=[], label="📊 选择分析报告", interactive=True)
                only_with_reports_checkbox = gr.Checkbox(label="🔍 仅显示有分析的内容", value=False,
                                                         interactive=True)
            with gr.Column(elem_classes=["placeholder-section"], scale=4):
                # --- 新增：删除报告 UI ---
                gr.Markdown("### ⚠️ 管理工具")
                delete_report_button = gr.Button("🗑️ 删除当前报告", variant="secondary")
                delete_confirm_button = gr.Button("✅ 确认删除", variant="primary", visible=False)
                delete_cancel_button = gr.Button("❌ 取消", variant="stop", visible=False)
                delete_status = gr.Markdown(visible=False)

                # --- 新增：删除逻辑 ---
                def show_delete_confirm():
                    return (
                        gr.update(visible=False),  # delete_report_button
                        gr.update(visible=True),   # delete_confirm_button
                        gr.update(visible=True),   # delete_cancel_button
                        gr.update(value="⚠️ 确定要删除当前选中的报告吗？此操作不可逆。", visible=True) # delete_status
                    )

                def hide_delete_confirm():
                    return (
                        gr.update(visible=True),   # delete_report_button
                        gr.update(visible=False),  # delete_confirm_button
                        gr.update(visible=False),  # delete_cancel_button
                        gr.update(visible=False)   # delete_status
                    )
        with gr.Column(elem_classes=["main-content-container"], scale=8):
            raw_text_output = gr.Markdown(value="## 欢迎使用小说章节浏览器\n\n请在左侧选择小说和章节开始阅读。",
                                          elem_classes=["novel-content-panel"])
            analysis_output = gr.Markdown(value="## 🤖 AI 分析报告\n\n选择章节后，AI 分析结果将在此显示。",
                                          elem_classes=["ai-analysis-panel"])

    # --- 连接事件 ---
    # 更新小说列表时考虑 checkbox
    category_selector.change(
        fn=update_novels_on_category_change,
        inputs=[category_selector, only_with_reports_checkbox],
        outputs=[novel_selector, chapter_selector, report_selector],
        queue=False
    )

    # checkbox 改变时也触发小说列表刷新
    only_with_reports_checkbox.change(
        fn=update_novels_on_category_change,
        inputs=[category_selector, only_with_reports_checkbox],
        outputs=[novel_selector, chapter_selector, report_selector],
        queue=False
    )

    # novel_selector 改变时也考虑 checkbox
    novel_selector.change(
        fn=update_chapters_and_clear_reports,
        inputs=[novel_selector, only_with_reports_checkbox],
        outputs=[chapter_selector, report_selector],
        queue=False
    )

    chapter_selector.change(fn=update_reports_and_load_content, inputs=[novel_selector, chapter_selector],
                            outputs=[report_selector, raw_text_output, analysis_output], queue=True)
    report_selector.change(fn=fn_load_selected_report, inputs=[novel_selector, chapter_selector, report_selector],
                           outputs=analysis_output, queue=True)
    delete_report_button.click(
        fn=show_delete_confirm,
        inputs=None,
        outputs=[delete_report_button, delete_confirm_button, delete_cancel_button, delete_status],
        queue=False
    )

    delete_cancel_button.click(
        fn=hide_delete_confirm,
        inputs=None,
        outputs=[delete_report_button, delete_confirm_button, delete_cancel_button, delete_status],
        queue=False
    )

    delete_confirm_button.click(
        fn=fn_delete_selected_report,
        inputs=[novel_selector, chapter_selector, report_selector],
        outputs=[
            delete_report_button, delete_confirm_button, delete_cancel_button, delete_status,
            analysis_output, report_selector
        ],
        queue=True
    )

# --- 启动应用 ---
if __name__ == "__main__":
    import re  # 确保 re 在需要它的函数作用域内可用

    print("正在启动小说章节浏览器...")
    print(f"请确保你的小说文件位于目录: {os.path.abspath(NOVELS_BASE_DIR)}")
    demo.launch(server_name="127.0.0.1", server_port=7861, share=False, show_error=True)