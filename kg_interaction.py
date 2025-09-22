# kg_interaction.py
# --- 导入 ---
import requests
from flask import Flask, render_template, request, jsonify
import os

from apis.api_graph import init_graph_api  # 修改导入路径
from apis.api_llm import init_llm_api

# 在文件顶部导入新增的函数
from rag.graph_generator import (
    extract_graph,
    get_novel_list,
    get_novel_chapters,
    get_ollama_models,
    get_schema_choices
)

from config import CACHE_DIR, REMOTE_MODEL_CHOICES, REMOTE_MODEL_NAME  # ✅ 统一配置

from rag.graph_manager import (
    ensure_demo_graph,  # ✅ 新增导入
    load_available_graphs_metadata
)

# --- 初始化 Flask ---
app = Flask(__name__, template_folder='templates',
            static_folder='static',
            static_url_path='/static')  # 明确指定静态URL路径)

STATIC_DIR = "./static"
CSS_DIR = "./static/css"
os.makedirs(CSS_DIR, exist_ok=True)

# --- 初始化演示数据 ---
demo_cache_key = ensure_demo_graph(CACHE_DIR)

# 初始化图谱API蓝图
init_graph_api(app, demo_cache_key)  # 新增初始化

# ==================== 页面路由 ====================

@app.route("/")
def index():
    """主页 - 图谱查看器"""
    cache_key = request.args.get("cache_key", demo_cache_key)
    return render_template("index.html", cache_key=cache_key)  # 确保使用正确的模板

@app.route("/viewer")  # 添加这个路由
def viewer():
    """图谱查看器页面"""
    cache_key = request.args.get("cache_key", demo_cache_key)
    return render_template("viewer.html", cache_key=cache_key)

@app.route("/selector")
def selector():
    """图谱选择器页面"""
    return render_template("selector.html")

@app.route("/text")
def text_view():
    """文字版图谱页面"""
    cache_key = request.args.get("cache_key", demo_cache_key)  # 默认使用演示数据
    return render_template("text_view.html", cache_key=cache_key)

# ==================== 其他API接口 ====================

@app.route('/api/ollama_models')
def api_get_ollama_models():
    """API 端点，返回 Ollama 本地模型列表"""
    try:
        models = get_ollama_models()
        app.logger.info(f"成功获取 Ollama 模型列表: {models}")
        return jsonify({"models": models, "success": True})
    except requests.exceptions.RequestException as e:
        error_msg = f"无法连接到 Ollama 服务: {str(e)}"
        app.logger.error(error_msg)
        return jsonify({"error": error_msg, "success": False}), 500
    except Exception as e:
        error_msg = f"获取 Ollama 模型时发生未知错误: {str(e)}"
        app.logger.error(error_msg)
        return jsonify({"error": error_msg, "success": False}), 500

@app.route("/api/novel-chapter-structure")
def get_novel_chapter_structure():
    """获取小说-章节结构"""
    try:
        available_graphs = load_available_graphs_metadata()
        app.logger.info(f"加载到 {len(available_graphs)} 个图谱")

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
        app.logger.error(f"获取小说章节结构失败: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500

@app.route("/api/filtered-graphs")
def get_filtered_graphs():
    """根据小说和章节过滤图谱"""
    selected_novel = request.args.get("novel")
    selected_chapter = request.args.get("chapter")

    app.logger.info(f"筛选请求: novel={selected_novel}, chapter={selected_chapter}")

    try:
        available_graphs = load_available_graphs_metadata()
        app.logger.info(f"加载到 {len(available_graphs)} 个图谱用于筛选")

        if not available_graphs:
            return jsonify({})

        filtered = {}
        for key, graph_info in available_graphs.items():
            filters = graph_info.get("filters", {})
            novel_name = filters.get("novel_name")
            chapter_name = filters.get("chapter_name")

            if (novel_name and chapter_name and
                    novel_name == selected_novel and chapter_name == selected_chapter):
                filtered[key] = graph_info

        app.logger.info(f"筛选结果: {len(filtered)} 个图谱")
        return jsonify(filtered)
    except Exception as e:
        app.logger.error(f"筛选图谱失败: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500

@app.route("/api/debug/graphs")
def debug_graphs():
    """调试用：查看所有图谱数据结构"""
    try:
        available_graphs = load_available_graphs_metadata()
        debug_data = dict(list(available_graphs.items())[:3])
        return jsonify(debug_data)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/graph-options")
def get_graph_options():
    """获取图谱选项（模型、模式、参数）"""
    filtered_graphs_json = request.args.get("filtered_graphs")
    try:
        import json
        filtered_graphs = json.loads(filtered_graphs_json) if filtered_graphs_json else {}

        models, schemas, params = set(), {}, {}

        for cache_key, graph_info in filtered_graphs.items():
            f = graph_info.get("filters", {})
            model = str(f.get("model_name", "未知模型"))
            schema = str(f.get("schema_name", "未知模式"))
            cs, co, nc = str(f.get("chunk_size", "未知")), str(f.get("chunk_overlap", "未知")), str(
                f.get("num_ctx", "未知"))

            if not model or not schema:
                continue

            models.add(model)
            schemas[(model, schema)] = schema

            key = (model, schema, cs, co, nc)
            meta = graph_info.get("metadata", {})
            ts = str(meta.get("created_at", "未知时间")) if isinstance(meta, dict) else "未知时间"
            display = f"块:{cs} / 重叠:{co} / 上下文:{nc} ({ts})"

            params[key] = {"display": display, "cache_key": cache_key}

        result = {
            "models": sorted(list(models)),
            "schemas": list(schemas.values()),
            "params": params
        }
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/generator")
def generator():
    """图谱生成器页面"""
    novels = get_novel_list()
    selected_novel = novels[0] if novels else ""
    chapters = get_novel_chapters(selected_novel) if selected_novel else []
    selected_chapter = chapters[0] if chapters else ""

    ollama_models = []
    schema_choices = get_schema_choices()

    return render_template(
        "generator.html",
        novels=novels,
        selected_novel=selected_novel,
        chapters=chapters,
        selected_chapter=selected_chapter,
        ollama_models=ollama_models,
        default_model= "",
        remote_models=REMOTE_MODEL_CHOICES,
        default_remote_model=REMOTE_MODEL_NAME,
        schema_choices=schema_choices,
        default_schema="自动生成"
    )

@app.route("/api/generate", methods=["POST"])
def api_generate():
    """API: 执行图谱生成"""
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

@app.route("/api/chapters")
def get_chapters():
    """获取指定小说的章节列表"""
    novel_name = request.args.get("novel", "")
    if not novel_name:
        return jsonify([])

    chapters = get_novel_chapters(novel_name)
    return jsonify(chapters)

@app.route("/generator-iframe")
def generator_iframe():
    """图谱生成器页面 - 用于 iframe 嵌入"""
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

@app.route("/editor")
def editor():
    """交互式图谱编辑器页面"""
    cache_key = request.args.get("cache_key", demo_cache_key)
    return render_template("graph_editor.html", cache_key=cache_key)


# 在主程序 app.py 或 kg_interaction.py 中






if __name__ == "__main__":
    app.run(host='0.0.0.0',debug=True, port=5000)
    init_graph_api(app, demo_cache_key)
    init_llm_api(app)

