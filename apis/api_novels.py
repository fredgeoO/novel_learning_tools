# apis/api_novels.py
"""
小说叙事分析 API 模块 - 提供小说、章节、报告的 RESTful 接口
"""

import os
import json
from datetime import datetime
from flask import Blueprint, request, jsonify, current_app
import logging

# 导入工具函数（保持你原有的逻辑）
from utils.util_chapter import (
    get_chapter_list_with_cache as get_chapter_list,
    get_report_list_with_cache as get_report_list,
    load_chapter_and_initial_report,
    load_report_content,
    has_any_reports,
    get_filtered_chapters_with_reports
)

# 假设你已将榜单解析逻辑移到 utils/rankings.py
from utils.util_rankings import get_novel_list, get_categories, parse_ranking_file

logger = logging.getLogger(__name__)

# 创建蓝图
novels_bp = Blueprint('novels', __name__, url_prefix='/api/novels')


def init_novels_api(app):
    """初始化小说 API 蓝图"""
    app.register_blueprint(novels_bp)
    logger.info("小说 API 蓝图已注册")


# --- 工具函数（使用 current_app.config 获取路径）---
def get_browse_history_path():
    return current_app.config.get('BROWSE_HISTORY_FILE', 'browse_history.json')


def load_browse_history():
    history_file = get_browse_history_path()
    if os.path.exists(history_file):
        try:
            with open(history_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"加载浏览历史失败: {e}")
    return []


def save_browse_history(history):
    max_items = current_app.config.get('MAX_HISTORY_ITEMS', 20)
    history = history[-max_items:]
    history_file = get_browse_history_path()
    try:
        with open(history_file, 'w', encoding='utf-8') as f:
            json.dump(history, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"保存浏览历史失败: {e}")


def add_to_history(novel, chapter):
    history = load_browse_history()
    item = {
        "novel": novel,
        "chapter": chapter,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "display": f"{novel} - {chapter.replace('.txt', '')}"
    }
    # 去重：移除已有项
    history = [h for h in history if not (h["novel"] == novel and h["chapter"] == chapter)]
    history.insert(0, item)
    save_browse_history(history)


# --- API 路由 ---

@novels_bp.route('/categories', methods=['GET'])
def api_get_categories():
    """获取所有分类（来自月票榜）"""
    try:
        categories = get_categories()
        return jsonify({"categories": categories})
    except Exception as e:
        logger.error(f"获取分类失败: {e}")
        return jsonify({"error": "获取分类失败"}), 500


@novels_bp.route('/list', methods=['GET'])
def api_get_novels():
    """获取小说列表"""
    try:
        category = request.args.get('category', '全部')
        only_with_reports = request.args.get('only_with_reports', 'false').lower() == 'true'

        novels = get_novel_list(
            filter_by_category=None if category == '全部' else category,
            only_with_reports=only_with_reports
        )
        return jsonify({"novels": novels})
    except Exception as e:
        logger.error(f"获取小说列表失败: {e}")
        return jsonify({"error": "获取小说列表失败"}), 500


@novels_bp.route('/<novel_name>/chapters', methods=['GET'])
def api_get_chapters(novel_name):
    """获取某小说的章节列表"""
    try:
        only_with_reports = request.args.get('only_with_reports', 'false').lower() == 'true'
        if only_with_reports:
            chapters = get_filtered_chapters_with_reports(novel_name)
        else:
            chapters = get_chapter_list(novel_name)
        return jsonify({"chapters": chapters})
    except Exception as e:
        logger.error(f"获取章节列表失败 (小说: {novel_name}): {e}")
        return jsonify({"error": "获取章节列表失败"}), 500


@novels_bp.route('/<novel_name>/<chapter>/reports', methods=['GET'])
def api_get_reports(novel_name, chapter):
    """获取某章节的分析报告列表"""
    try:
        reports = get_report_list(novel_name, chapter)
        return jsonify({"reports": reports})
    except Exception as e:
        logger.error(f"获取报告列表失败 ({novel_name}/{chapter}): {e}")
        return jsonify({"error": "获取报告列表失败"}), 500


@novels_bp.route('/<novel_name>/<chapter>/content', methods=['GET'])
def api_get_content(novel_name, chapter):
    """加载章节内容和默认报告"""
    try:
        add_to_history(novel_name, chapter)
        chapter_content, report_content = load_chapter_and_initial_report(novel_name, chapter)
        return jsonify({
            "chapter_content": chapter_content,
            "report_content": report_content
        })
    except Exception as e:
        logger.error(f"加载内容失败 ({novel_name}/{chapter}): {e}")
        return jsonify({"error": "加载内容失败"}), 500


@novels_bp.route('/<novel_name>/<chapter>/report/<report_name>', methods=['GET'])
def api_load_report(novel_name, chapter, report_name):
    """加载指定报告内容"""
    try:
        content = load_report_content(novel_name, chapter, report_name)
        return jsonify({"content": content})
    except Exception as e:
        logger.error(f"加载报告失败 ({novel_name}/{chapter}/{report_name}): {e}")
        return jsonify({"error": "加载报告失败"}), 500


@novels_bp.route('/<novel_name>/<chapter>/report/<report_name>', methods=['DELETE'])
def api_delete_report(novel_name, chapter, report_name):
    """删除指定报告"""
    try:
        reports_base = current_app.config['REPORTS_BASE_DIR']
        report_path = os.path.join(reports_base, novel_name, chapter, report_name)
        if os.path.exists(report_path):
            os.remove(report_path)
            logger.info(f"报告已删除: {report_path}")
            return jsonify({"message": "报告删除成功"})
        else:
            return jsonify({"error": "报告不存在"}), 404
    except Exception as e:
        logger.error(f"删除报告失败 ({novel_name}/{chapter}/{report_name}): {e}")
        return jsonify({"error": "删除报告失败"}), 500


@novels_bp.route('/history', methods=['GET'])
def api_get_history():
    """获取浏览历史"""
    try:
        history = load_browse_history()
        return jsonify({"history": history})
    except Exception as e:
        logger.error(f"获取浏览历史失败: {e}")
        return jsonify({"error": "获取历史失败"}), 500


@novels_bp.route('/history/<int:index>', methods=['GET'])
def api_get_history_item(index):
    """获取指定历史项"""
    try:
        history = load_browse_history()
        if 0 <= index < len(history):
            return jsonify(history[index])
        else:
            return jsonify({"error": "历史索引无效"}), 400
    except Exception as e:
        logger.error(f"获取历史项失败 (index={index}): {e}")
        return jsonify({"error": "获取历史项失败"}), 500