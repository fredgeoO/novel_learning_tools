# llm/llm_core.py
"""
LLM交互核心模块 - 处理与大语言模型的通信逻辑
用于知识图谱的智能扩展和编辑
"""

import json
import requests
from typing import Dict, Any, Optional
from config import DEFAULT_MODEL, OLLAMA_URL, REMOTE_API_KEY, REMOTE_BASE_URL
from rag.graph_types import LLMGraphResponse, LLMGraphNode, LLMGraphRelationship
from langchain.prompts import PromptTemplate
from langchain.output_parsers import PydanticOutputParser
import logging

logger = logging.getLogger(__name__)


class LLMInteractionManager:
    """LLM交互管理器"""

    def __init__(
            self,
            default_model: Optional[str] = None,
            ollama_base_url: Optional[str] = None,
            remote_api_key: Optional[str] = None,
            remote_base_url: Optional[str] = None
    ):
        """
        初始化 LLM 交互管理器

        :param default_model: 使用的模型名称（如 'llama3', 'qwen:7b'）
        :param ollama_base_url: Ollama 服务地址（如 'http://localhost:11434'）
        :param remote_api_key: 远程 API 密钥（如 OpenAI）
        :param remote_base_url: 远程 API 基础 URL
        """
        # 使用传入参数，若未提供则回退到 config 中的默认值
        self.default_model = default_model or DEFAULT_MODEL
        self.ollama_base_url = ollama_base_url or OLLAMA_URL
        self.remote_api_key = remote_api_key or REMOTE_API_KEY
        self.remote_base_url = remote_base_url or REMOTE_BASE_URL

    def generate_graph_from_question(self, node: Dict[str, Any], question: str,
                                     context_graph: Optional[Dict[str, Any]] = None) -> LLMGraphResponse:
        """
        通用接口：根据节点信息 + 自然语言问题，生成关联的新节点和关系图谱。

        所有语义化提问方法（如解释、论证、推测）都应基于此方法实现。

        :param node: 当前节点信息
        :param question: 用户提出的具体问题（自然语言）
        :param context_graph: 上下文图谱（可选）
        :return: 生成的知识图谱响应
        """
        try:
            # 创建 Pydantic 输出解析器
            parser = PydanticOutputParser(pydantic_object=LLMGraphResponse)

            # 创建提示词模板
            prompt_template = PromptTemplate(
                template="""
                    你是一个专业的知识图谱构建专家。请根据要求生成知识图谱数据。

                    当前节点信息：
                    节点ID: {node_id}
                    节点标签: {node_label}
                    节点类型: {node_type}
                    节点属性: {node_properties}

                    用户提示词: {user_question}

                    {context_info}

                    输出要求：
                    1. 严格按照指定的JSON格式输出
                    2. 新生成的节点和关系必须与原始节点有逻辑关联
                    3. 节点的properties中必须包含content字段存储相关内容
                    4. 关系的properties中必须包含content字段存储关系说明
                    5. 确保生成的数据语义合理、逻辑清晰

                    请严格按照以下JSON格式输出：
                    {format_instructions}
                    """,
                input_variables=["node_id", "node_label", "node_type", "node_properties", "user_question",
                                 "context_info"],
                partial_variables={"format_instructions": parser.get_format_instructions()}
            )

            # 准备输入变量
            context_info = ""
            if context_graph:
                context_info = f"上下文图谱信息：节点数: {len(context_graph.get('nodes', []))}, 关系数: {len(context_graph.get('relationships', []))}"

            # 生成提示词
            formatted_prompt = prompt_template.format(
                node_id=node.get('id', ''),
                node_label=node.get('label', node.get('id', '')),
                node_type=node.get('type', ''),
                node_properties=json.dumps(node.get('properties', {}), ensure_ascii=False),
                user_question=question,
                context_info=context_info
            )

            # 调用LLM
            llm_response = self._call_ollama(formatted_prompt)

            # 清理响应（处理可能的思考过程）
            think_index = llm_response.find("</think>")
            if think_index != -1:
                llm_response = llm_response[think_index + len("</think>"):]

            # 解析响应
            try:
                parsed_result = parser.invoke(llm_response)
                if isinstance(parsed_result, dict):
                    return LLMGraphResponse(**parsed_result)
                elif isinstance(parsed_result, LLMGraphResponse):
                    return parsed_result
                else:
                    return LLMGraphResponse(**parsed_result.dict())
            except Exception as parse_error:
                logger.warning(f"Pydantic解析失败，尝试手动解析: {parse_error}")
                return self._manual_parse_response(llm_response)

        except Exception as e:
            logger.error(f"生成图谱时出错: {e}")
            return LLMGraphResponse(
                nodes=[],
                relationships=[],
                error=f"处理失败: {str(e)}"
            )

    def expand_node_knowledge(self, node: Dict[str, Any], prompt: str,
                              context_graph: Optional[Dict[str, Any]] = None) -> LLMGraphResponse:
        """
        扩展节点知识 —— 现在基于通用提问接口实现
        """
        return self.generate_graph_from_question(node, prompt, context_graph)

    def explain_meaning(self, node: Dict[str, Any],
                        context_graph: Optional[Dict[str, Any]] = None) -> LLMGraphResponse:
        """
        提问：“X是什么意思？” → 请求定义或解释
        """
        question = "请详细解释这个节点的含义或定义，它代表什么概念？在相关领域中如何被理解？"
        return self.generate_graph_from_question(node, question, context_graph)

    def analyze_justification(self, node: Dict[str, Any],
                              context_graph: Optional[Dict[str, Any]] = None) -> LLMGraphResponse:
        """
        提问：“X有什么理据？” → 请求理由、依据、论证
        """
        question = "请分析这个节点背后的理据、支撑依据或论证逻辑，为什么它成立或被提出？"
        return self.generate_graph_from_question(node, question, context_graph)

    def explore_possibility(self, node: Dict[str, Any],
                            context_graph: Optional[Dict[str, Any]] = None) -> LLMGraphResponse:
        """
        提问：“X有什么可能性？” → 请求推测、推演、潜在发展
        """
        question = "请推测这个节点可能的发展方向、潜在关联或未来可能性，有哪些合理的延伸？"
        return self.generate_graph_from_question(node, question, context_graph)

    def _call_ollama(self, prompt: str) -> str:
        """调用Ollama API"""
        try:
            url = f"{self.ollama_base_url}/api/generate"

            payload = {
                "model": self.default_model,
                "prompt": prompt,
                "stream": False,
                "options": {"temperature": 0.8, "num_ctx": 4096}
            }

            logger.info(f"调用Ollama模型: {self.default_model} @ {self.ollama_base_url}")
            response = requests.post(url, json=payload, timeout=300)
            response.raise_for_status()

            result = response.json()
            return result.get('response', '')

        except Exception as e:
            logger.error(f"调用Ollama失败: {e}")
            raise

    def _manual_parse_response(self, response: str) -> LLMGraphResponse:
        """手动解析LLM响应"""
        try:
            # 提取JSON部分
            clean_response = response.strip()
            start = clean_response.find('{')
            end = clean_response.rfind('}') + 1

            if start != -1 and end > start:
                json_str = clean_response[start:end]
                json_data = json.loads(json_str)
            else:
                raise ValueError("未找到有效的JSON格式")

            # 验证并创建响应对象
            nodes_data = json_data.get('nodes', [])
            relationships_data = json_data.get('relationships', [])

            # 转换节点数据，确保有content字段
            nodes = []
            for node_data in nodes_data:
                properties = node_data.get('properties', {})
                if 'content' not in properties:
                    properties['content'] = f"{node_data.get('type', '')}相关信息"
                nodes.append(LLMGraphNode(
                    id=node_data.get('id', ''),
                    type=node_data.get('type', ''),
                    properties=properties
                ))

            # 转换关系数据，确保有content字段
            relationships = []
            for rel_data in relationships_data:
                properties = rel_data.get('properties', {})
                if 'content' not in properties:
                    properties['content'] = f"{rel_data.get('type', '')}关系说明"
                relationships.append(LLMGraphRelationship(
                    source_id=rel_data.get('source_id', ''),
                    target_id=rel_data.get('target_id', ''),
                    type=rel_data.get('type', ''),
                    properties=properties
                ))

            return LLMGraphResponse(
                nodes=nodes,
                relationships=relationships
            )

        except Exception as e:
            logger.error(f"手动解析响应失败: {e}")
            return LLMGraphResponse(
                nodes=[],
                relationships=[],
                error=f"解析响应失败: {str(e)}"
            )


