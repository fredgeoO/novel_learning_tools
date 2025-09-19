# kg_interaction.py
# --- 导入 ---
from flask import Flask, render_template, request, jsonify, url_for
import os
import json
import uuid
from datetime import datetime

# 在文件顶部导入新增的函数
from rag.graph_generator import (
    extract_graph,
    get_novel_list,
    get_novel_chapters,
    get_ollama_models,
    get_schema_choices,
    get_default_model
)

from rag.config import CACHE_DIR, REMOTE_MODEL_CHOICES, REMOTE_MODEL_NAME  # ✅ 统一配置
from rag.graph_renderer import (
    GraphVisualizer,
    format_graph_text,

)

from rag.graph_manager import (
    delete_selected_graph,
    ensure_demo_graph,  # ✅ 新增导入
    load_available_graphs_metadata
)
from rag.cache_manager import load_cache, get_metadata_from_cache_key


# --- 初始化 Flask ---
app = Flask(__name__, template_folder='templates', static_folder='static')

STATIC_DIR = "./static"
CSS_DIR = "./static/css"
os.makedirs(CSS_DIR, exist_ok=True)

# --- 初始化演示数据 ---
demo_cache_key = ensure_demo_graph(CACHE_DIR)

# 创建演示数据
def create_demo_data():
    demo_graph_data = {
        "nodes": [
            {
                "id": "1",
                "label": "彭刚",
                "type": "人物",
                "properties": {"name": "彭刚", "sequence_number": 1}
            },
            {
                "id": "2",
                "label": "彭毅",
                "type": "人物",
                "properties": {"name": "彭毅", "sequence_number": 2}
            }
        ],
        "relationships": [
            {
                "source_id": "1",
                "target_id": "2",
                "type": "兄弟",
                "properties": {}
            }
        ]
    }

    demo_cache_key = "demo_" + str(uuid.uuid4())[:8]
    demo_metadata = {
        "novel_name": "演示小说",
        "chapter_name": "演示章节",
        "model_name": "演示模型",
        "schema_name": "演示模式",
        "chunk_size": "512",
        "chunk_overlap": "50",
        "num_ctx": "2048",
        "created_at": datetime.now().isoformat()
    }

    with open(os.path.join(CACHE_DIR, f"{demo_cache_key}.json"), "w", encoding="utf-8") as f:
        json.dump(demo_graph_data, f)

    with open(os.path.join(CACHE_DIR, f"{demo_cache_key}_metadata.json"), "w", encoding="utf-8") as f:
        json.dump(demo_metadata, f)

    return demo_cache_key




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

# ==================== API 接口 ====================

@app.route("/api/graph")
def get_graph():
    """获取图谱HTML"""
    cache_key = request.args.get("cache_key", demo_cache_key)
    max_nodes = int(request.args.get("max_nodes", 1000))
    max_edges = int(request.args.get("max_edges", 1000))
    physics_enabled = request.args.get("physics", "true").lower() == "true"
    hidden_types = request.args.get("hidden_types", "")
    hidden_node_types = set(hidden_types.split(",")) if hidden_types else set()

    try:
        graph_doc = load_cache(cache_key)
        if graph_doc is None:
            return render_template(
                "error_page.html",
                color="red",
                message="❌ 图谱数据未找到"
            ), 404

        visualizer = GraphVisualizer()
        html_content = visualizer.generate_html(
            graph_doc,
            max_nodes=max_nodes,
            max_edges=max_edges,
            physics_enabled=physics_enabled,
            hidden_node_types=hidden_node_types
        )

        return render_template("full_graph.html", html_content=html_content)

    except Exception as e:
        app.logger.error(f"生成图谱失败: {e}")
        return render_template(
            "error_page.html",
            color="red",
            message=f"❌ 可视化失败: {str(e)}"
        ), 500


@app.route("/api/graphs")
def get_available_graphs():
    """获取所有可用图谱"""
    try:
        available_graphs = load_available_graphs_metadata(CACHE_DIR)
        return jsonify(available_graphs)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/graph/<cache_key>/metadata")
def get_graph_metadata(cache_key):
    """获取图谱元数据"""
    try:
        metadata = get_metadata_from_cache_key(cache_key)
        return jsonify(metadata)
    except Exception as e:
        return jsonify({"error": str(e)}), 404


@app.route("/api/graph/<cache_key>/text")
def get_graph_text(cache_key):
    """获取文字版图谱"""
    try:
        graph_doc = load_cache(cache_key)
        if graph_doc is None:
            return jsonify({"error": "图谱数据未找到"}), 404

        hidden_types = request.args.get("hidden_types", "")
        hidden_node_types = set(hidden_types.split(",")) if hidden_types else set()

        if isinstance(graph_doc, dict):
            nodes = graph_doc.get('nodes', [])
            relationships = graph_doc.get('relationships', [])
        else:
            nodes = getattr(graph_doc, 'nodes', [])
            relationships = getattr(graph_doc, 'relationships', [])

        text_content = format_graph_text(nodes, relationships, hidden_node_types)
        return jsonify({"content": text_content})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/graph/<cache_key>", methods=["DELETE"])
def delete_graph(cache_key):
    """删除图谱"""
    try:
        success = delete_selected_graph(CACHE_DIR, cache_key)
        if success:
            return jsonify({"success": True})
        else:
            return jsonify({"error": "删除失败"}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/novel-chapter-structure")
def get_novel_chapter_structure():
    """获取小说-章节结构"""
    try:
        available_graphs = load_available_graphs_metadata(CACHE_DIR)
        app.logger.info(f"加载到 {len(available_graphs)} 个图谱")

        novel_chapter_map = {}
        for key, graph_info in available_graphs.items():
            # 添加调试日志
            # app.logger.info(f"处理图谱 {key}: {graph_info}")

            filters = graph_info.get("filters", {})
            novel_name = filters.get("novel_name", "未知小说")
            chapter_name = filters.get("chapter_name", "未知章节")

            # app.logger.info(f"  小说: {novel_name}, 章节: {chapter_name}")

            if novel_name not in novel_chapter_map:
                novel_chapter_map[novel_name] = set()
            novel_chapter_map[novel_name].add(chapter_name)

        structure = {novel: sorted(list(chapters)) for novel, chapters in novel_chapter_map.items()}
        # app.logger.info(f"最终结构: {structure}")
        return jsonify(structure)
    except Exception as e:
        app.logger.error(f"获取小说章节结构失败: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500

@app.route("/api/graph-frame")
@app.route("/api/graph-frame")
def graph_frame():
    """返回极简版 PyVis 图谱页面，用于 iframe 嵌入"""
    cache_key = request.args.get("cache_key", demo_cache_key)
    max_nodes = int(request.args.get("max_nodes", 1000))
    max_edges = int(request.args.get("max_edges", 1000))
    physics_enabled = request.args.get("physics", "true").lower() == "true"

    try:
        graph_doc = load_cache(cache_key)
        if graph_doc is None:
            return "<div style='text-align: center; padding: 50px; color: red; font-family: Arial, sans-serif; background-color: #1e1e1e;'>❌ 图谱数据未找到</div>", 404

        # 直接使用 generate_html 方法生成完整的 HTML
        visualizer = GraphVisualizer()
        html_content = visualizer.generate_html(
            graph_doc=graph_doc,
            max_nodes=max_nodes,
            max_edges=max_edges,
            physics_enabled=physics_enabled
        )

        return html_content, 200, {'Content-Type': 'text/html; charset=utf-8'}

    except Exception as e:
        app.logger.error(f"生成图谱失败: {e}", exc_info=True)
        error_html = f"<div style='text-align: center; padding: 50px; color: red; font-family: Arial, sans-serif; background-color: #1e1e1e;'>❌ 可视化失败: {str(e)}</div>"
        return error_html, 500, {'Content-Type': 'text/html; charset=utf-8'}
@app.route("/api/filtered-graphs")
def get_filtered_graphs():
    """根据小说和章节过滤图谱"""
    selected_novel = request.args.get("novel")
    selected_chapter = request.args.get("chapter")

    app.logger.info(f"筛选请求: novel={selected_novel}, chapter={selected_chapter}")

    try:
        available_graphs = load_available_graphs_metadata(CACHE_DIR)
        app.logger.info(f"加载到 {len(available_graphs)} 个图谱用于筛选")

        if not available_graphs:
            return jsonify({})

        filtered = {}
        for key, graph_info in available_graphs.items():
            filters = graph_info.get("filters", {})
            novel_name = filters.get("novel_name")
            chapter_name = filters.get("chapter_name")

            # app.logger.info(f"检查图谱 {key}: novel={novel_name}, chapter={chapter_name}")

            # 修复：确保两个条件都匹配，并且不为 None
            if (novel_name and chapter_name and
                    novel_name == selected_novel and chapter_name == selected_chapter):
                filtered[key] = graph_info
                # app.logger.info(f"  匹配成功: {key}")

        app.logger.info(f"筛选结果: {len(filtered)} 个图谱")
        return jsonify(filtered)
    except Exception as e:
        app.logger.error(f"筛选图谱失败: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500
@app.route("/api/debug/graphs")
def debug_graphs():
    """调试用：查看所有图谱数据结构"""
    try:
        available_graphs = load_available_graphs_metadata(CACHE_DIR)
        # 只返回前3个用于调试
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
    # 获取初始数据
    novels = get_novel_list()
    selected_novel = novels[0] if novels else ""
    chapters = get_novel_chapters(selected_novel) if selected_novel else []
    selected_chapter = chapters[0] if chapters else ""

    # 获取模型列表
    ollama_models = get_ollama_models()
    default_model = ollama_models[0] if ollama_models else "qwen3:30b"

    # 获取图谱模式
    schema_choices = get_schema_choices()

    return render_template(
        "generator.html",
        novels=novels,
        selected_novel=selected_novel,
        chapters=chapters,
        selected_chapter=selected_chapter,
        ollama_models=ollama_models,
        default_model=default_model,
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


if __name__ == "__main__":
    app.run(debug=True, port=5000)