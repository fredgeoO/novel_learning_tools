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
- URL路径支持：http://127.0.0.1:7861/?novel=小说名&chapter=章节名&report=报告名

目录结构要求：
- novels/ - 存放小说章节文本文件
- reports/novels/ - 存放对应的小说分析报告
- scraped_data/所有分类月票榜汇总.txt - 可选的小说分类榜单文件

作者：FredgeoO
日期：2025
"""

import os
import glob
import time
from urllib.parse import unquote

import gradio as gr
import re
import json
from datetime import datetime
import random

# --- 配置 ---
NOVELS_BASE_DIR = "novels"
REPORTS_BASE_DIR = "reports/novels"
BROWSE_HISTORY_FILE = "browse_history.json"
MAX_HISTORY_ITEMS = 20  # 最多保存20条浏览记录

# --- 从 chapter_utils 导入通用功能 ---
from utils_chapter import (
    get_chapter_list_with_cache as get_chapter_list,
    get_report_list_with_cache as get_report_list,
    load_chapter_and_initial_report,
    load_report_content,
    novel_cache,
    has_any_reports,
    get_filtered_chapters_with_reports,
    delete_report_file
)

# --- 浏览历史相关函数 ---
browse_history = []


def load_browse_history():
    """加载浏览历史"""
    global browse_history
    try:
        if os.path.exists(BROWSE_HISTORY_FILE):
            with open(BROWSE_HISTORY_FILE, 'r', encoding='utf-8') as f:
                browse_history = json.load(f)
        else:
            browse_history = []
    except Exception as e:
        print(f"加载浏览历史时出错: {e}")
        browse_history = []
    return browse_history


def save_browse_history():
    """保存浏览历史"""
    try:
        # 限制历史记录数量
        global browse_history
        browse_history = browse_history[-MAX_HISTORY_ITEMS:]
        with open(BROWSE_HISTORY_FILE, 'w', encoding='utf-8') as f:
            json.dump(browse_history, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"保存浏览历史时出错: {e}")


def add_to_browse_history(novel_name, chapter_filename):
    """添加到浏览历史"""
    global browse_history
    if not novel_name or not chapter_filename:
        return

    # 创建历史记录项
    history_item = {
        "novel": novel_name,
        "chapter": chapter_filename,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "display": f"{novel_name} - {chapter_filename.replace('.txt', '')}"
    }

    # 检查是否已存在相同的记录（避免重复）
    existing_index = None
    for i, item in enumerate(browse_history):
        if item["novel"] == novel_name and item["chapter"] == chapter_filename:
            existing_index = i
            break

    # 如果存在，移到最前面；如果不存在，添加到最前面
    if existing_index is not None:
        browse_history.pop(existing_index)
    browse_history.insert(0, history_item)

    save_browse_history()


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
    """更新章节选择器，但不清空报告选择器"""
    if not selected_novel:
        return gr.update(choices=[], value=None), gr.update(choices=[], value=None)

    try:
        if only_with_reports:
            chapters = get_filtered_chapters_with_reports(selected_novel)
        else:
            chapters = get_chapter_list(selected_novel)

        # 移除 .txt 扩展名用于显示
        chapter_choices = [(chap.replace('.txt', ''), chap) for chap in chapters]
        default_chapter = chapter_choices[0][1] if chapter_choices else None

        # 只更新章节选择器，报告选择器保持不变
        return gr.update(choices=chapter_choices, value=default_chapter), gr.update()
    except Exception as e:
        print(f"更新章节列表时出错: {e}")
        return gr.update(choices=[], value=None), gr.update(choices=[], value=None)


def update_reports_and_load_content(novel_name, chapter_filename):
    if not novel_name or not chapter_filename:
        return gr.update(choices=[],
                         value=None), "## 请选择小说和章节\n\n在左侧选择一本小说和一个章节开始阅读。", "## AI 分析报告\n\n选择章节后，AI 分析结果将在此显示。"

    # 添加到浏览历史
    add_to_browse_history(novel_name, chapter_filename)

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


def fn_load_random_novel_with_reports():
    """
    页面加载时，随机选择一本有报告的小说，并返回更新值。
    """
    novels_with_reports = get_novel_list(only_with_reports=True)
    if not novels_with_reports:
        # 如果没有小说有报告，返回默认空状态
        return (
            gr.update(),  # novel_selector
            gr.update(choices=[], value=None),  # chapter_selector
            gr.update(choices=[], value=None),  # report_selector
            "## 欢迎使用小说章节浏览器\n\n请在左侧选择小说和章节开始阅读。",  # raw_text_output
            "## 🤖 AI 分析报告\n\n选择章节后，AI 分析结果将在此显示。"  # analysis_output
        )

    # 随机选一本小说
    selected_novel = random.choice(novels_with_reports)

    # 获取该小说的章节列表（仅包含有报告的章节）
    chapters = get_filtered_chapters_with_reports(selected_novel)
    chapter_choices = [(chap.replace('.txt', ''), chap) for chap in chapters]
    default_chapter = chapter_choices[0][1] if chapter_choices else None

    # 获取该章节的报告列表
    reports = get_report_list(selected_novel, default_chapter) if default_chapter else []
    report_choices = [(rep.replace('.txt', ''), rep) for rep in reports]
    default_report = report_choices[0][1] if report_choices else None

    # 加载章节内容和报告内容
    chapter_content, report_content = load_chapter_and_initial_report(selected_novel,
                                                                      default_chapter) if default_chapter else (
        "## 欢迎使用小说章节浏览器\n\n请在左侧选择小说和章节开始阅读。",
        "## 🤖 AI 分析报告\n\n选择章节后，AI 分析结果将在此显示。"
    )

    return (
        gr.update(value=selected_novel),  # novel_selector
        gr.update(choices=chapter_choices, value=default_chapter),  # chapter_selector
        gr.update(choices=report_choices, value=default_report),  # report_selector
        chapter_content,  # raw_text_output
        report_content  # analysis_output
    )


# --- URL处理相关函数 ---
def load_from_query_params():
    """
    从查询参数加载内容（简化版本，实际处理通过JavaScript完成）
    """
    return fn_load_random_novel_with_reports()


def update_url_from_selection(novel_name, chapter_filename, report_filename):
    """
    当用户通过UI选择内容时，返回JavaScript代码来更新URL
    """
    if novel_name and chapter_filename and report_filename:
        chapter_name = chapter_filename.replace('.txt', '')
        report_name = report_filename.replace('.txt', '')
        js_code = f"""
        <script>
        if (typeof updateBrowserUrl === 'function') {{
            updateBrowserUrl('{novel_name}', '{chapter_name}', '{report_name}');
        }}
        </script>
        """
        return js_code
    return ""


# --- 修复的历史记录相关函数 ---
def fn_load_history_item(index):
    """加载历史记录项"""
    print(f"尝试加载历史记录项: {index}")

    # 边界检查
    if not browse_history or index >= len(browse_history) or index < 0:
        print(f"无效的历史记录索引: {index}")
        return (
            gr.update(),  # novel_selector
            gr.update(),  # chapter_selector
            gr.update(),  # report_selector
            "## 欢迎使用小说章节浏览器\n\n历史记录无效。",  # raw_text_output
            "## 🤖 AI 分析报告\n\n选择章节后，AI 分析结果将在此显示。"  # analysis_output
        )

    try:
        item = browse_history[index]
        novel_name = item["novel"]
        chapter_filename = item["chapter"]
        print(f"加载历史: {novel_name} - {chapter_filename}")

        # 获取小说列表
        novel_list = get_novel_list()

        # 验证小说是否存在
        if novel_name not in novel_list:
            return (
                gr.update(choices=novel_list),  # novel_selector
                gr.update(),  # chapter_selector
                gr.update(),  # report_selector
                f"## 错误\n\n小说 '{novel_name}' 不存在。",  # raw_text_output
                "## 🤖 AI 分析报告\n\n小说不存在。"  # analysis_output
            )

        # 获取章节列表
        chapters = get_chapter_list(novel_name)
        chapter_choices = [(chap.replace('.txt', ''), chap) for chap in chapters]

        # 验证章节是否存在
        chapter_filenames = [chap[1] for chap in chapter_choices]
        if chapter_filename not in chapter_filenames:
            # 如果章节不存在，使用第一个可用章节
            if chapter_choices:
                chapter_filename = chapter_choices[0][1]
            else:
                return (
                    gr.update(value=novel_name, choices=novel_list),  # novel_selector
                    gr.update(choices=[]),  # chapter_selector
                    gr.update(choices=[]),  # report_selector
                    f"## 错误\n\n小说 '{novel_name}' 没有可用章节。",  # raw_text_output
                    "## 🤖 AI 分析报告\n\n小说没有章节。"  # analysis_output
                )

        # 重新获取章节列表（确保使用正确的章节）
        chapters = get_chapter_list(novel_name)
        chapter_choices = [(chap.replace('.txt', ''), chap) for chap in chapters]

        # 获取报告列表
        reports = get_report_list(novel_name, chapter_filename)
        report_choices = [(rep.replace('.txt', ''), rep) for rep in reports]

        # 设置默认报告
        default_report = report_choices[0][1] if report_choices else None

        # 加载内容
        chapter_content, report_content = load_chapter_and_initial_report(novel_name, chapter_filename)

        print(f"成功加载历史: {novel_name} - {chapter_filename}")
        return (
            gr.update(value=novel_name, choices=novel_list),  # novel_selector
            gr.update(choices=chapter_choices, value=chapter_filename),  # chapter_selector
            gr.update(choices=report_choices, value=default_report),  # report_selector
            chapter_content,  # raw_text_output
            report_content  # analysis_output
        )
    except Exception as e:
        print(f"加载历史记录时出错: {e}")
        import traceback
        traceback.print_exc()
        return (
            gr.update(),  # novel_selector
            gr.update(),  # chapter_selector
            gr.update(),  # report_selector
            "## 错误\n\n加载历史记录时发生错误。",  # raw_text_output
            "## 错误\n\n加载历史记录时发生错误。"  # analysis_output
        )


# --- 简化的章节切换处理函数 ---
def simple_chapter_change(novel_name, chapter_filename):
    if not novel_name or not chapter_filename:
        return gr.update(choices=[], value=None), "请选择小说和章节", "请选择章节查看分析报告"

    # 更新报告选择器
    reports = get_report_list(novel_name, chapter_filename)
    report_choices = [(rep.replace('.txt', ''), rep) for rep in reports]
    default_report = report_choices[0][1] if report_choices else None

    # 加载内容
    chapter_content, report_content = load_chapter_and_initial_report(novel_name, chapter_filename)

    return gr.update(choices=report_choices, value=default_report), chapter_content, report_content


# --- 事件处理函数 ---
def show_delete_confirm():
    return (
        gr.update(visible=False),
        gr.update(visible=True),
        gr.update(visible=True),
        gr.update(value="⚠️ 确定要删除当前选中的报告吗？此操作不可逆。", visible=True)
    )


def hide_delete_confirm():
    return (
        gr.update(visible=True),
        gr.update(visible=False),
        gr.update(visible=False),
        gr.update(visible=False)
    )


# --- Gradio 界面和逻辑 ---
CSS_STYLES = """
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
.narrow-dropdown { width: 75%; max-width: 250px; }
.history-button { margin: 2px 0; text-align: left; font-size: 12px; padding: 5px 8px; }
"""

JS_URL_SYNC = """
<script>
function updateBrowserUrl(novel, chapter, report) {
    if (novel && chapter && report) {
        try {
            const baseUrl = window.location.origin + window.location.pathname;
            const newUrl = `${baseUrl}?novel=${encodeURIComponent(novel)}&chapter=${encodeURIComponent(chapter)}&report=${encodeURIComponent(report)}`;
            window.history.replaceState({}, '', newUrl);
        } catch (e) {
            console.log('URL更新失败:', e);
        }
    }
}

// 页面加载完成后尝试从URL参数加载内容
document.addEventListener('DOMContentLoaded', function() {
    setTimeout(function() {
        const urlParams = new URLSearchParams(window.location.search);
        const novel = urlParams.get('novel');
        const chapter = urlParams.get('chapter');
        const report = urlParams.get('report');

        if (novel && chapter && report) {
            console.log('检测到URL参数:', novel, chapter, report);
            // 这里可以添加自动加载逻辑（需要与Gradio集成）
        }
    }, 1000);
});
</script>
"""

# 主界面构建
with gr.Blocks(
        title="📖 小说叙事分析",
        theme=gr.themes.Soft(primary_hue="slate", secondary_hue="stone"),
        css=CSS_STYLES
) as demo:
    with gr.Row(elem_classes=["main-container"]):
        # 侧边栏
        with gr.Column(elem_classes=["sidebar-container"], scale=1, min_width=250):
            # 选择区域
            category_selector = gr.Dropdown(
                choices=["全部"] + get_categories(),
                value="全部",
                label="🏷️ 选择分类",
                interactive=True
            )
            novel_selector = gr.Dropdown(
                choices=get_novel_list(),
                label="📚 选择小说",
                interactive=True
            )
            chapter_selector = gr.Dropdown(
                choices=[],
                label="📄 选择章节",
                interactive=True
            )
            report_selector = gr.Dropdown(
                choices=[],
                label="📊 选择分析报告",
                interactive=True
            )
            only_with_reports_checkbox = gr.Checkbox(
                label="🔍 仅显示有分析的内容",
                value=False,
                interactive=True
            )

            # 简化的管理区域 - 只保留删除报告功能
            gr.Markdown("### ⚠️ 管理工具")
            delete_report_button = gr.Button("🗑️ 删除当前报告", variant="secondary")
            delete_confirm_button = gr.Button("✅ 确认删除", variant="primary", visible=False)
            delete_cancel_button = gr.Button("❌ 取消", variant="stop", visible=False)
            delete_status = gr.Markdown(visible=False)

            gr.Markdown("### ℹ️ 提示")
            gr.Markdown("如需查看浏览历史，请刷新页面")

        # 内容显示区域
        with gr.Column(elem_classes=["main-content-container"], scale=8):
            raw_text_output = gr.Markdown(
                value="## 欢迎使用小说章节浏览器\n\n请在左侧选择小说和章节开始阅读。",
                elem_classes=["novel-content-panel"]
            )
            analysis_output = gr.Markdown(
                value="## 🤖 AI 分析报告\n\n选择章节后，AI 分析结果将在此显示。",
                elem_classes=["ai-analysis-panel"]
            )

    # 添加JavaScript支持
    url_update_component = gr.HTML(visible=False)
    gr.HTML(JS_URL_SYNC)

    # --- 事件连接 ---
    category_selector.change(
        fn=update_novels_on_category_change,
        inputs=[category_selector, only_with_reports_checkbox],
        outputs=[novel_selector, chapter_selector, report_selector],
        queue=False
    )

    only_with_reports_checkbox.change(
        fn=update_novels_on_category_change,
        inputs=[category_selector, only_with_reports_checkbox],
        outputs=[novel_selector, chapter_selector, report_selector],
        queue=False
    )

    novel_selector.change(
        fn=update_chapters_and_clear_reports,
        inputs=[novel_selector, only_with_reports_checkbox],
        outputs=[chapter_selector, report_selector],
        queue=False
    )

    # 章节选择事件 - 更新URL
    chapter_selector.change(
        fn=simple_chapter_change,
        inputs=[novel_selector, chapter_selector],
        outputs=[report_selector, raw_text_output, analysis_output],
        queue=True
    ).then(
        fn=update_url_from_selection,
        inputs=[novel_selector, chapter_selector, report_selector],
        outputs=url_update_component
    )

    # 报告选择事件 - 更新URL
    report_selector.change(
        fn=fn_load_selected_report,
        inputs=[novel_selector, chapter_selector, report_selector],
        outputs=analysis_output,
        queue=True
    ).then(
        fn=update_url_from_selection,
        inputs=[novel_selector, chapter_selector, report_selector],
        outputs=url_update_component
    )

    # 删除报告事件
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

    # 页面加载事件
    demo.load(
        fn=load_from_query_params,
        inputs=[],
        outputs=[novel_selector, chapter_selector, report_selector, raw_text_output, analysis_output],
        queue=False
    )

# --- 应用启动 ---
load_browse_history()

if __name__ == "__main__":
    print("正在启动小说章节浏览器...")
    print(f"请确保你的小说文件位于目录: {os.path.abspath(NOVELS_BASE_DIR)}")
    print("支持URL访问格式: http://127.0.0.1:7861/?novel=小说名&chapter=章节名&report=报告名")
    demo.launch(
        server_name="127.0.0.1",
        server_port=7861,
        share=False,
        show_error=True,
        allowed_paths=["."]
    )