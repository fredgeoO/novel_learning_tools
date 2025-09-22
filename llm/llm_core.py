# rag/llm_core.py
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

    def __init__(self):
        self.default_model = DEFAULT_MODEL
        self.ollama_base_url = OLLAMA_URL
        self.remote_api_key = REMOTE_API_KEY
        self.remote_base_url = REMOTE_BASE_URL

    def expand_node_knowledge(self, node: Dict[str, Any], prompt: str,
                              context_graph: Optional[Dict[str, Any]] = None) -> LLMGraphResponse:
        """
        扩展节点知识 - 输入图JSON+提示词，输出图JSON

        :param node: 当前节点信息
        :param prompt: 用户提示词
        :param context_graph: 上下文图谱（可选）
        :return: 生成的新节点和关系
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

用户要求: {user_prompt}

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
                input_variables=["node_id", "node_label", "node_type", "node_properties", "user_prompt",
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
                user_prompt=prompt,
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
                # 确保返回的是LLMGraphResponse对象
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
            logger.error(f"扩展节点知识时出错: {e}")
            return LLMGraphResponse(
                nodes=[],
                relationships=[],
                error=f"处理失败: {str(e)}"
            )

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

            logger.info(f"调用Ollama模型: {self.default_model}")
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


# 全局LLM管理器实例
llm_manager = LLMInteractionManager()