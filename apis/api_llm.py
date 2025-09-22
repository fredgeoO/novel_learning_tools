# api_llm.py
"""
LLM API模块 - 提供LLM交互的RESTful接口
"""

from flask import Blueprint, request, jsonify
import logging
from llm.llm_core import llm_manager  # 从核心模块导入管理器

logger = logging.getLogger(__name__)

# 创建蓝图
llm_bp = Blueprint('llm', __name__, url_prefix='/api/llm')


def init_llm_api(app):
    """初始化LLM API"""
    app.register_blueprint(llm_bp)
    logger.info("LLM API蓝图已注册")


@llm_bp.route('/expand-node', methods=['POST'])
def expand_node():
    """
    扩展节点知识API
    请求格式:
    {
        "node": {
            "id": "中国",
            "label": "中国",
            "type": "国家",
            "properties": {}
        },
        "prompt": "给一些有关这个国家的历史事件",
        "context_graph": {
            "nodes": [...],
            "relationships": [...]
        }
    }
    """
    try:
        data = request.get_json()

        node = data.get('node')
        prompt = data.get('prompt')
        context_graph = data.get('context_graph')

        if not node or not prompt:
            return jsonify({
                "error": "缺少必要的参数：node或prompt",
                "success": False
            }), 400

        # 调用LLM处理
        result = llm_manager.expand_node_knowledge(node, prompt, context_graph)

        # 返回结果
        response_data = result.dict()
        response_data["success"] = True
        return jsonify(response_data)

    except Exception as e:
        logger.error(f"处理节点扩展请求时出错: {e}")
        return jsonify({
            "error": f"处理请求时出错: {str(e)}",
            "nodes": [],
            "relationships": [],
            "success": False
        }), 500


@llm_bp.route('/health', methods=['GET'])
def health_check():
    """健康检查"""
    return jsonify({
        "status": "healthy",
        "default_model": llm_manager.default_model,
        "success": True
    })


# 响应辅助函数
def success_response(data=None, message="操作成功"):
    return jsonify({
        "success": True,
        "message": message,
        "data": data
    })


def error_response(message, status_code=400, details=None):
    response = {
        "success": False,
        "error": {
            "code": status_code,
            "message": message,
            "details": details
        }
    }
    return jsonify(response), status_code