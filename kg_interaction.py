# kg_interaction.py
import requests
import os
import logging
from flask import Flask, render_template, request, jsonify

# --- 配置日志 ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- 导入配置和工具 ---
from config import CACHE_DIR, REMOTE_MODEL_CHOICES, REMOTE_MODEL_NAME

# --- 导入 RAG 相关函数 ---
from rag.graph_generator import (
    extract_graph,
    get_novel_list,
    get_novel_chapters,
    get_ollama_models,
    get_schema_choices
)
from rag.graph_manager import ensure_demo_graph, load_available_graphs_metadata

# --- 创建 Flask 应用 ---
app = Flask(
    __name__,
    template_folder='templates',
    static_folder='static',
    static_url_path='/static'
)

# 确保静态资源目录存在
os.makedirs("./static/css", exist_ok=True)

# --- 初始化演示图谱 ---
demo_cache_key = ensure_demo_graph()
logger.info(f"演示图谱已初始化，cache_key: {demo_cache_key}")

# --- ✅ 在 app.run() 之前注册所有蓝图 ---
try:
    from apis.api_graph import init_graph_api

    init_graph_api(app, demo_cache_key)
    logger.info("✅ 图谱 API 蓝图已注册")
except Exception as e:
    logger.error(f"❌ 图谱 API 蓝图注册失败: {e}")

try:
    from apis.api_llm import init_llm_api

    init_llm_api(app)
    logger.info("✅ LLM API 蓝图已注册")
except Exception as e:
    logger.error(f"❌ LLM API 蓝图注册失败: {e}")

try:
    from apis.api_novels import init_novels_api

    init_novels_api(app)
    logger.info("✅ 小说 API 蓝图已注册")
except Exception as e:
    logger.error(f"❌ 小说 API 蓝图注册失败: {e}")


# ==================== 页面路由 ====================

@app.route("/")
def index():
    cache_key = request.args.get("cache_key", demo_cache_key)
    return render_template("index.html", cache_key=cache_key)


@app.route("/viewer")
def viewer():
    """小说叙事分析浏览器"""
    return render_template("viewer.html")  # 注意：viewer.html 不需要 cache_key


@app.route("/selector")
def selector():
    return render_template("selector.html")


@app.route("/editor")
def editor():
    cache_key = request.args.get("cache_key", demo_cache_key)
    return render_template("graph_editor.html", cache_key=cache_key)


@app.route("/generator")
def generator():
    novels = get_novel_list()
    selected_novel = novels[0] if novels else ""
    chapters = get_novel_chapters(selected_novel) if selected_novel else []
    selected_chapter = chapters[0] if chapters else ""
    schema_choices = get_schema_choices()

    return render_template(
        "generator.html",
        novels=novels,
        selected_novel=selected_novel,
        chapters=chapters,
        selected_chapter=selected_chapter,
        ollama_models=[],
        default_model="",
        remote_models=REMOTE_MODEL_CHOICES,
        default_remote_model=REMOTE_MODEL_NAME,
        schema_choices=schema_choices,
        default_schema="自动生成"
    )


# ==================== 全局 API 接口 ====================

@app.route('/api/ollama_models')
def api_get_ollama_models():
    try:
        models = get_ollama_models()
        logger.info(f"成功获取 Ollama 模型列表: {models}")
        return jsonify({"models": models, "success": True})
    except requests.exceptions.RequestException as e:
        error_msg = f"无法连接到 Ollama 服务: {str(e)}"
        logger.error(error_msg)
        return jsonify({"error": error_msg, "success": False}), 500
    except Exception as e:
        error_msg = f"获取 Ollama 模型时发生未知错误: {str(e)}"
        logger.error(error_msg)
        return jsonify({"error": error_msg, "success": False}), 500


@app.route("/api/novel-chapter-structure")
def get_novel_chapter_structure():
    try:
        available_graphs = load_available_graphs_metadata()
        novel_chapter_map = {}
        for key, graph_info in available_graphs.items():
            filters = graph_info.get("filters", {})
            novel_name = filters.get("novel_name", "未知小说")
            chapter_name = filters.get("chapter_name", "未知章节")
            if novel_name not in novel_chapter_map:
                novel_chapter_map[novel_name] = set()
            novel_chapter_map[novel_name].add(chapter_name)
        structure = {novel: sorted(list(chapters)) for novel, chapters in novel_chapter_map.items()}
        return jsonify(structure)
    except Exception as e:
        logger.error(f"获取小说章节结构失败: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@app.route("/api/chapters")
def get_chapters():
    novel_name = request.args.get("novel", "")
    if not novel_name:
        return jsonify([])
    chapters = get_novel_chapters(novel_name)
    return jsonify(chapters)


@app.route("/api/generate", methods=["POST"])
def api_generate():
    try:
        data = request.get_json()
        result = extract_graph(
            novel_name=data.get("novel_name", ""),
            chapter_file=data.get("chapter_file", ""),
            model_type=data.get("model_type", "local"),
            model_name=data.get("model_name", ""),
            chunk_size=int(data.get("chunk_size", 1024)),
            chunk_overlap=int(data.get("chunk_overlap", 192)),
            num_ctx=int(data.get("num_ctx", 16384)),
            schema_name=data.get("schema_name", "自动生成"),
            use_cache=data.get("use_cache", True)
        )
        return jsonify(result)
    except Exception as e:
        logger.error(f"API生成失败: {e}", exc_info=True)
        return jsonify({"error": f"生成失败: {str(e)}"}), 500


# --- 调试路由（可选）---
@app.route("/api/debug/graphs")
def debug_graphs():
    try:
        available_graphs = load_available_graphs_metadata()
        debug_data = dict(list(available_graphs.items())[:3])
        return jsonify(debug_data)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ==================== 启动应用 ====================

if __name__ == "__main__":
    logger.info("🚀 启动知识图谱交互系统...")
    logger.info(f"访问地址: http://127.0.0.1:5000")
    logger.info(f"小说浏览器: http://127.0.0.1:5000/viewer")

    # ✅ 确保蓝图已在上方注册！
    app.run(host='0.0.0.0', port=5000, debug=True)