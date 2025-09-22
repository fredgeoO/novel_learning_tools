# graph_api.py
from venv import logger

from flask import Blueprint, request, jsonify, render_template
from rag.graph_manager import (
    delete_selected_graph,
    load_available_graphs_metadata
)
from rag.cache_manager import (
    load_cache,
    get_metadata_from_cache_key,
    save_cache  # <-- 新增导入
)
from rag.graph_renderer import (
    GraphVisualizer,
    format_graph_text
)
from rag.graph_types import SerializableGraphDocument

from utils.util_responses import success_response, error_response

from config import CACHE_DIR

# 创建蓝图
graph_bp = Blueprint('graph_api', __name__, url_prefix='/api')

# 全局变量，将在注册时设置
demo_cache_key = None


def init_graph_api(app, demo_key):
    """初始化图谱API，设置应用上下文和演示数据键"""
    global demo_cache_key
    demo_cache_key = demo_key

    # 注册蓝图
    app.register_blueprint(graph_bp)

    # 注册错误处理器
    @app.errorhandler(404)
    def not_found(error):
        return jsonify({"success": False, "error": "资源未找到"}), 404

    @app.errorhandler(500)
    def internal_error(error):
        app.logger.error(f"服务器内部错误: {error}")
        return jsonify({"success": False, "error": "服务器内部错误"}), 500


# 图谱数据相关接口
@graph_bp.route('/graph')
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
        return render_template(
            "error_page.html",
            color="red",
            message=f"❌ 可视化失败: {str(e)}"
        ), 500


@graph_bp.route('/graphs')
def get_available_graphs():
    """获取所有可用图谱"""
    try:
        available_graphs = load_available_graphs_metadata()
        return success_response(data=available_graphs)
    except Exception as e:
        return error_response("获取可用图谱失败", 500, details=str(e))


@graph_bp.route('/graph/<cache_key>/metadata')
def get_graph_metadata(cache_key):
    """获取图谱元数据"""
    try:
        metadata = get_metadata_from_cache_key(cache_key)
        return success_response(data=metadata)
    except Exception as e:
        return error_response("获取元数据失败", 404, details=str(e))


@graph_bp.route('/graph/<cache_key>/text')
def get_graph_text(cache_key):
    """获取文字版图谱"""
    try:
        graph_doc = load_cache(cache_key)
        if graph_doc is None:
            return error_response("图谱数据未找到", 404)

        hidden_types = request.args.get("hidden_types", "")
        hidden_node_types = set(hidden_types.split(",")) if hidden_types else set()

        if isinstance(graph_doc, dict):
            nodes = graph_doc.get('nodes', [])
            relationships = graph_doc.get('relationships', [])
        else:
            nodes = getattr(graph_doc, 'nodes', [])
            relationships = getattr(graph_doc, 'relationships', [])

        text_content = format_graph_text(nodes, relationships, hidden_node_types)
        return success_response(data={"content": text_content})
    except Exception as e:
        return error_response("获取文字版图谱失败", 500, details=str(e))


@graph_bp.route('/graph/<cache_key>', methods=["DELETE"])
def delete_graph(cache_key):
    """删除图谱"""
    try:
        success = delete_selected_graph(CACHE_DIR, cache_key)
        if success:
            return success_response(message="删除成功")
        else:
            return error_response("删除失败", 404)
    except Exception as e:
        return error_response("删除失败", 500, details=str(e))


# 新增：保存/更新图谱接口
@graph_bp.route('/graph/<cache_key>', methods=["PUT"])
def update_graph(cache_key):
    """更新图谱数据 (从 Vis.js 格式转换回内部格式并保存)"""
    try:
        data = request.get_json()
        if not data:
            return error_response("请求体为空", 400)

        # 验证数据结构 (Vis.js 格式)
        vis_nodes = data.get('nodes', [])
        vis_edges = data.get('edges', []) # 注意是 edges

        if not isinstance(vis_nodes, list) or not isinstance(vis_edges, list):
             return error_response("无效的图谱数据格式，nodes 和 edges 必须是数组", 400)

        # --- 转换 Vis.js 数据回 SerializableGraphDocument ---
        try:
            # 创建一个只有 nodes 和 edges 的临时字典，供 from_vis_dict 使用
            temp_vis_data = {
                'nodes': vis_nodes,
                'edges': vis_edges
            }
            graph_doc_obj = SerializableGraphDocument.from_vis_dict(temp_vis_data)
        except Exception as conv_error:
            logger.error(f"转换 Vis.js 数据到内部格式失败: {conv_error}", exc_info=True)
            return error_response("图谱数据格式转换失败", 400, details=str(conv_error))

        # --- 保存到缓存 ---
        # 你可以选择保存原始 Vis.js 格式，或者转换回标准字典格式保存
        # 这里我们保存标准字典格式，以保持与之前逻辑的一致性
        try:
            save_cache(cache_key, graph_doc_obj.to_dict()) # 保存标准字典格式
            # 或者如果你想保存 Vis.js 格式：
            # save_cache(cache_key, temp_vis_data)
        except Exception as save_error:
            logger.error(f"保存图谱数据失败: {save_error}", exc_info=True)
            return error_response("保存图谱数据失败", 500, details=str(save_error))

        return success_response(message="图谱保存成功")
    except Exception as e:
        logger.error(f"更新图谱失败: {e}", exc_info=True)
        return error_response("更新图谱失败", 500, details=str(e))


# rag/graph_api.py

# ... (其他导入) ...

@graph_bp.route('/graph-data')
def get_graph_data():
    """获取纯图数据（用于前端交互式渲染 - Vis.js 格式）"""
    cache_key = request.args.get("cache_key", demo_cache_key)
    # max_nodes, max_edges, hidden_types 等过滤逻辑可以保留或根据需要调整
    # physics_enabled 也可以保留
    physics_enabled = request.args.get("physics", "true").lower() == "true"

    try:
        graph_doc = load_cache(cache_key)
        if graph_doc is None:
            return error_response("图谱数据未找到", 404)

        # 直接使用缓存中的 SerializableGraphDocument 对象
        # 并调用新的 to_vis_dict 方法转换为 Vis.js 格式
        if isinstance(graph_doc, dict):
            # 如果缓存加载回来的是字典（可能之前保存的就是字典），尝试转换
            temp_graph_doc = SerializableGraphDocument.from_dict(graph_doc)
            vis_graph_data = temp_graph_doc.to_vis_dict()
        elif isinstance(graph_doc, SerializableGraphDocument):
            # 如果是对象，直接转换
            vis_graph_data = graph_doc.to_vis_dict()
        else:
            # 不支持的类型
            logger.error(f"缓存中图谱数据类型不支持: {type(graph_doc)}")
            return error_response("图谱数据格式不支持", 500)

        return success_response(data={
            'data': vis_graph_data, # data.data 包含 nodes 和 edges
            'physics': physics_enabled
        })
    except Exception as e:
        logger.error(f"获取图数据失败: {e}", exc_info=True) # 添加 exc_info=True 以便查看完整堆栈
        return error_response("获取图数据失败", 500, details=str(e))

# ... (其他路由) ...

@graph_bp.route('/graph-frame')
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

        visualizer = GraphVisualizer()
        html_content = visualizer.generate_html(
            graph_doc=graph_doc,
            max_nodes=max_nodes,
            max_edges=max_edges,
            physics_enabled=physics_enabled
        )

        return html_content, 200, {'Content-Type': 'text/html; charset=utf-8'}

    except Exception as e:
        error_html = f"<div style='text-align: center; padding: 50px; color: red; font-family: Arial, sans-serif; background-color: #1e1e1e;'>❌ 可视化失败: {str(e)}</div>"
        return error_html, 500, {'Content-Type': 'text/html; charset=utf-8'}