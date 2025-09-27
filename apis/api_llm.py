# apis\api_llm.py
"""
LLM API模块 - 提供LLM交互的RESTful接口
"""

from flask import Blueprint, request
import logging
from llm.llm_core import LLMInteractionManager  # 从核心模块导入管理器
from utils.util_responses import success_response, error_response  # ✅ 导入统一响应工具

logger = logging.getLogger(__name__)

# 创建蓝图
llm_bp = Blueprint('llm', __name__, url_prefix='/api/llm')

llm_manager = LLMInteractionManager()

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
            return error_response("缺少必要的参数：node或prompt", 400)


        # 调用LLM处理
        result = llm_manager.expand_node_knowledge(node, prompt, context_graph)

        # 返回成功响应
        return success_response(data=result.dict(), message="节点知识扩展成功")

    except Exception as e:
        logger.error(f"处理节点扩展请求时出错: {e}")
        return error_response(
            message=f"处理请求时出错: {str(e)}",
            status_code=500,
            details={
                "nodes": [],
                "relationships": []
            }
        )


@llm_bp.route('/health', methods=['GET'])
def health_check():
    """健康检查"""
    health_data = {
        "status": "healthy",
        "default_model": llm_manager.default_model
    }
    return success_response(data=health_data, message="服务健康")