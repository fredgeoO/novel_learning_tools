# test_llm.py
import sys
import json
import requests

sys.path.append('..')  # 添加项目根目录到路径

from llm.qwen_chat_client import QwenChatClient  # 导入Qwen客户端


class SeleniumLLMInteractionManager:
    """使用Selenium驱动Qwen网页版的LLM交互管理器"""

    def __init__(self):
        # Selenium模式不需要这些参数，但为了接口兼容性保留
        self.default_model = "qwen-web"
        self.ollama_base_url = "http://localhost:5001"  # Selenium服务端口
        self.remote_api_key = None
        self.remote_base_url = None

    def expand_node_knowledge(self, node: dict, prompt: str,
                              context_graph: dict = None) -> dict:
        """
        使用Selenium驱动Qwen网页版扩展节点知识

        :param node: 当前节点信息
        :param prompt: 用户提示词
        :param context_graph: 上下文图谱（可选）
        :return: 生成的新节点和关系
        """
        try:
            # 构建发送给Qwen的完整提示词
            full_prompt = self._build_prompt(node, prompt, context_graph)

            # 调用Selenium驱动的Qwen服务
            response_text = self._call_qwen_selenium(full_prompt)

            # 解析响应为结构化数据
            result = self._parse_response(response_text)

            return result

        except Exception as e:
            print(f"调用Selenium Qwen失败: {e}")
            return {
                "nodes": [],
                "relationships": [],
                "error": f"处理失败: {str(e)}"
            }

    def _build_prompt(self, node: dict, prompt: str, context_graph: dict = None) -> str:
        """构建发送给Qwen的提示词"""

        prompt_parts = []

        # 添加系统指令
        prompt_parts.append("你是一个专业的知识图谱构建专家。请根据要求生成知识图谱数据。")
        prompt_parts.append("")

        # 当前节点信息
        prompt_parts.append("当前节点信息：")
        prompt_parts.append(f"节点ID: {node.get('id', '')}")
        prompt_parts.append(f"节点标签: {node.get('label', node.get('id', ''))}")
        prompt_parts.append(f"节点类型: {node.get('type', '')}")
        prompt_parts.append(f"节点属性: {json.dumps(node.get('properties', {}), ensure_ascii=False)}")
        prompt_parts.append("")

        # 用户要求
        prompt_parts.append(f"用户要求: {prompt}")
        prompt_parts.append("")

        # 上下文图谱（如果有）
        if context_graph:
            prompt_parts.append("上下文图谱信息：")
            prompt_parts.append(f"节点数: {len(context_graph.get('nodes', []))}")
            prompt_parts.append(f"关系数: {len(context_graph.get('relationships', []))}")
            prompt_parts.append("")

        # 输出格式要求
        prompt_parts.append("请严格按照以下JSON格式输出：")
        prompt_parts.append("""{
    "nodes": [
        {
            "id": "节点名称",
            "type": "节点类型",
            "properties": {
                "content": "节点相关内容说明"
            }
        }
    ],
    "relationships": [
        {
            "source_id": "源节点ID",
            "target_id": "目标节点ID",
            "type": "关系类型",
            "properties": {
                "content": "关系说明内容"
            }
        }
    ]
}""")
        prompt_parts.append("")
        prompt_parts.append("重要：只输出JSON数据，不要包含任何其他文本或解释！")

        return "\n".join(prompt_parts)

    def _call_qwen_selenium(self, prompt: str) -> str:
        """调用Selenium驱动的Qwen服务"""
        try:
            # 方法1: 直接调用Selenium服务的Ollama兼容API
            url = "http://localhost:5001/api/generate"

            payload = {
                "model": "qwen-web",
                "prompt": prompt,
                "stream": False,
                "enable_thinking": True,
                "enable_search": True
            }

            response = requests.post(url, json=payload, timeout=300)
            response.raise_for_status()

            result = response.json()
            return result.get('response', '')

        except Exception as e:
            print(f"通过API调用Selenium Qwen失败: {e}")
            print("尝试直接使用QwenChatClient...")

            # 方法2: 直接使用QwenChatClient（备用方案）
            client = None
            try:
                client = QwenChatClient(
                    headless=True,
                    get_response_max_wait_time=400,
                    max_wait_time=10,
                    start_minimized=True
                )
                client.load_chat_page()
                response_text = client.chat(prompt, enable_thinking=True, enable_search=True)
                return response_text
            finally:
                if client:
                    try:
                        client.close()
                    except:
                        pass

    def _parse_response(self, response_text: str) -> dict:
        """解析Qwen响应为结构化数据"""
        try:
            # 清理响应文本
            clean_response = response_text.strip()

            # 尝试提取JSON部分
            start = clean_response.find('{')
            end = clean_response.rfind('}') + 1

            if start != -1 and end > start:
                json_str = clean_response[start:end]
                json_data = json.loads(json_str)

                # 确保必要字段存在
                if 'nodes' not in json_data:
                    json_data['nodes'] = []
                if 'relationships' not in json_data:
                    json_data['relationships'] = []
                if 'error' not in json_data:
                    json_data['error'] = None

                return json_data
            else:
                raise ValueError("响应中未找到有效的JSON格式")

        except Exception as e:
            print(f"解析响应失败: {e}")
            return {
                "nodes": [],
                "relationships": [],
                "error": f"解析响应失败: {str(e)}"
            }


def test_llm_expansion():
    """测试LLM节点扩展功能"""

    # 创建Selenium LLM管理器实例
    llm_manager = SeleniumLLMInteractionManager()

    # 测试数据
    test_node = {
        "id": "中国",
        "label": "中国",
        "type": "国家",
        "properties": {}
    }

    test_prompt = "给一些有关这个国家的历史事件 3个就好，接着根据这3个节点继续发散思维（创建新节点）下去，展开。"

    print("=== 测试Selenium驱动的LLM节点扩展 ===")
    print(f"输入节点: {test_node}")
    print(f"提示词: {test_prompt}")
    print("正在调用Selenium驱动的Qwen...")

    try:
        # 调用扩展功能
        result = llm_manager.expand_node_knowledge(test_node, test_prompt)

        print("\n=== LLM响应结果 ===")
        print(f"错误信息: {result.get('error', 'None')}")
        print(f"生成节点数: {len(result.get('nodes', []))}")
        print(f"生成关系数: {len(result.get('relationships', []))}")

        print("\n=== 生成的节点 ===")
        for i, node in enumerate(result.get('nodes', [])):
            print(f"{i + 1}. ID: {node.get('id', 'N/A')}, 类型: {node.get('type', 'N/A')}")
            print(f"   内容: {node.get('properties', {}).get('content', 'N/A')}")

        print("\n=== 生成的关系 ===")
        for i, rel in enumerate(result.get('relationships', [])):
            print(
                f"{i + 1}. {rel.get('source_id', 'N/A')} --[{rel.get('type', 'N/A')}]--> {rel.get('target_id', 'N/A')}")
            print(f"   内容: {rel.get('properties', {}).get('content', 'N/A')}")

    except Exception as e:
        print(f"测试失败: {e}")


if __name__ == "__main__":
    test_llm_expansion()