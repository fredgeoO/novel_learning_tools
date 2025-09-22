# rag/graph_optimizer.py

import json
import logging
import copy
import uuid
from datetime import datetime
from typing import List, Dict, Tuple, Optional, Any, Set
from langchain_core.messages import AIMessage
from langchain_core.output_parsers import JsonOutputParser
from langchain_core.prompts import PromptTemplate
# --- 导入所需模块 (与 NarrativeGraphExtractor 保持一致) ---
from langchain_openai import ChatOpenAI
from langchain_ollama import OllamaLLM
# --- 导入共享的数据结构和配置 ---
from rag.graph_types import (
    SerializableNode,
    SerializableRelationship,
    SerializableGraphDocument,
    AggregateGroupingResponse, ReconnectionResponse
)
# --- 导入共享配置 ---
from config import (
    DEFAULT_MODEL as CONFIG_DEFAULT_MODEL,
    DEFAULT_BASE_URL as CONFIG_DEFAULT_BASE_URL,
    DEFAULT_TEMPERATURE as CONFIG_DEFAULT_TEMPERATURE,
    DEFAULT_NUM_CTX as CONFIG_DEFAULT_NUM_CTX,
    DEFAULT_CHUNK_SIZE as CONFIG_DEFAULT_CHUNK_SIZE,
    DEFAULT_CHUNK_OVERLAP as CONFIG_DEFAULT_CHUNK_OVERLAP,
)
# --- 导入缓存管理器 ---
from rag.cache_manager import load_cache, GRAPH_CACHE_DIR  # 用于加载测试数据

# --- 配置日志 ---
logger = logging.getLogger(__name__)


class GraphOptimizer:
    """
    用于优化知识图谱结构，特别是减少高连接度节点的直接连接数。
    """
    # --- 使用从 config.py 导入的默认值 ---
    DEFAULT_MODEL = CONFIG_DEFAULT_MODEL
    DEFAULT_BASE_URL = CONFIG_DEFAULT_BASE_URL
    DEFAULT_TEMPERATURE = CONFIG_DEFAULT_TEMPERATURE
    DEFAULT_NUM_CTX = CONFIG_DEFAULT_NUM_CTX
    DEFAULT_CHUNK_SIZE = CONFIG_DEFAULT_CHUNK_SIZE
    DEFAULT_CHUNK_OVERLAP = CONFIG_DEFAULT_CHUNK_OVERLAP

    def __init__(
            self,
            # --- LLM 配置参数 ---
            model_name: str = DEFAULT_MODEL,
            base_url: str = DEFAULT_BASE_URL,
            temperature: float = DEFAULT_TEMPERATURE,
            default_num_ctx: int = DEFAULT_NUM_CTX,
            # --- 远程 API 配置 ---
            remote_api_key: Optional[str] = None,
            remote_base_url: Optional[str] = None,
            remote_model_name: Optional[str] = None,
    ):
        """
        初始化 GraphOptimizer。
        Args:
            model_name (str): 本地 Ollama 模型名称。
            base_url (str): 本地 Ollama 服务的 base URL。
            temperature (float): LLM 生成文本的随机性。
            default_num_ctx (int): 默认的上下文长度。
            remote_api_key (str, optional): 远程 API 的密钥。
            remote_base_url (str, optional): 远程 API 的 base URL。
            remote_model_name (str, optional): 远程 API 的模型名称。
        """
        # 基础配置
        self.model_name = model_name
        self.base_url = base_url
        self.temperature = temperature
        self.default_num_ctx = default_num_ctx

        # 远程 API 配置
        self.remote_api_key = remote_api_key or os.getenv("ARK_API_KEY")  # 从环境变量获取
        self.remote_base_url = remote_base_url
        self.remote_model_name = remote_model_name

        # 判断是否使用远程 API
        self.use_remote_api = bool(
            self.remote_api_key and
            self.remote_base_url and
            self.remote_model_name
        )

        logger.info(
            f"GraphOptimizer initialized with {'remote API' if self.use_remote_api else 'local Ollama'} model."
        )

    def _create_llm(self, num_ctx: int, local: bool = True) -> Any:
        """创建并返回配置好的 LLM 实例（本地或远程）。"""
        # 优先使用传入的 local 参数，如果没有指定，则根据 self.use_remote_api 判断
        use_local_effectively = local if local is not None else not self.use_remote_api

        if not use_local_effectively and self.use_remote_api:
            logger.info(f"Using remote OpenAI-compatible API: {self.remote_model_name} at {self.remote_base_url}")
            return ChatOpenAI(
                model=self.remote_model_name,
                openai_api_key=self.remote_api_key,
                openai_api_base=self.remote_base_url.strip(),  # 确保去除尾部空格
                temperature=self.temperature,
                max_tokens=num_ctx,  # 注意：有些 OpenAI API 实现使用 max_tokens 而不是 num_ctx
            )
        else:
            logger.info(f"Using local Ollama model: {self.model_name}")
            return OllamaLLM(
                model=self.model_name,
                base_url=self.base_url,
                temperature=self.temperature,
                num_ctx=num_ctx
            )

    def _calculate_dynamic_threshold(self, node_connections: Dict[str, int], hub_threshold_percentile: float) -> float:
        """
        根据节点连接度计算动态阈值。
        (此方法在新的迭代逻辑中可能不直接使用，但保留以备将来扩展)
        """
        if not node_connections:
            logger.debug("节点连接度字典为空，动态阈值设为0。")
            return 0.0

        all_degrees = list(node_connections.values())
        percentile_q = max(0.0, min(1.0, hub_threshold_percentile))

        dynamic_threshold = 0.0
        if len(all_degrees) > 1:
            sorted_degrees = sorted(all_degrees)
            index = percentile_q * (len(sorted_degrees) - 1)
            if index.is_integer():
                dynamic_threshold = float(sorted_degrees[int(index)])
            else:
                lower_index = int(index)
                upper_index = lower_index + 1
                if upper_index < len(sorted_degrees):
                    dynamic_threshold = sorted_degrees[lower_index] + (index - lower_index) * (
                            sorted_degrees[upper_index] - sorted_degrees[lower_index])
                else:
                    dynamic_threshold = float(sorted_degrees[lower_index])
        else:
            dynamic_threshold = float(max(all_degrees)) if all_degrees else 0.0

        dynamic_threshold = max(1.0, dynamic_threshold)
        logger.debug(
            f"使用百分位数法计算动态阈值: Percentile={percentile_q * 100:.1f}%, Threshold (approx)={dynamic_threshold:.2f}"
        )
        return dynamic_threshold

    def _group_related_nodes(
            self,
            main_node: SerializableNode,
            related_nodes: List[SerializableNode],
    ) -> AggregateGroupingResponse:
        """
        使用LLM对高连接度节点的相关节点进行语义分组，以减少直接连接数。
        """
        llm = self._create_llm(num_ctx=self.default_num_ctx)

        related_nodes_info = "\n".join([
            f"节点{idx + 1}: ID={n.id}, 类型={n.type}, 属性={json.dumps(n.properties, ensure_ascii=False)}"
            for idx, n in enumerate(related_nodes)
        ])
        main_node_props = json.dumps(main_node.properties, ensure_ascii=False)

        prompt_template = PromptTemplate(
            template="""
            你是一个图谱优化专家。图谱中存在一个节点（称为主节点），它与过多的其他节点（相关节点）直接相连，导致图结构复杂。
            你的任务是优化这个结构。
            主节点信息：
            - ID: {main_node_id}
            - 类型: {main_node_type}
            - 属性: {main_node_properties}
            相关节点列表 (这些节点都直接连接到主节点)：
            {related_nodes_info}
            优化任务：
            1.  分析所有“相关节点”的语义、类型和属性。
            2.  将这些“相关节点”分成2-7个语义上内聚的组，分组数量取决于相关节点的数量，平均10个相关节点才增加1个内聚的组。分组的目标是减少主节点的直接连接数。
            3.  每个分组应围绕一个清晰的主题或概念。
            4.  为每个组生成以下信息：
                - **group_name**: 一个能概括该组核心语义的中文词语（例如“背景”、“事件”、“组织”）。**这个名称将直接用作新聚合节点的 ID 和其 `name` 属性的值。**
                - **node_ids**: 属于该组的相关节点的ID列表。
                - **aggregate_relationship_type**: 描述“主节点”与这个新“聚合概念”之间关系的最合适的中文词语（如“涉及”、“拥有”、“经历”）。
                - **member_relationship_type**: 描述新“聚合概念”与其“成员节点”之间关系的最合适的中文词语（如“包含”、“导致”、“体现”）。
            **输出要求**：
            - **严格遵守指令，只输出最终的JSON格式结果，不要添加任何解释、前言或后语。**
            - **确保生成的JSON格式完全正确且有效。**
            - **仔细核对，确保所有要求的信息都已包含在输出中。**
            - **严格遵循以下JSON结构定义：**
            {format_instructions}
            """,
            input_variables=[
                "main_node_id",
                "main_node_type",
                "main_node_properties",
                "related_nodes_info"
            ],
            partial_variables={
                "format_instructions": JsonOutputParser(
                    pydantic_object=AggregateGroupingResponse).get_format_instructions()
            }
        )
        chain = prompt_template | llm
        response = chain.invoke({
            "main_node_id": main_node.id,
            "main_node_type": main_node.type,
            "main_node_properties": main_node_props,
            "related_nodes_info": related_nodes_info
        })

        if isinstance(response, AIMessage):
            response = response.content
        if isinstance(response, str):
            think_index = response.find("</think>")
            if think_index != -1:
                response = response[think_index + len("</think>"):]
            response = response.strip()

        try:
            parser = JsonOutputParser(pydantic_object=AggregateGroupingResponse)
            result = parser.invoke(response)
            if isinstance(result, dict):
                result = AggregateGroupingResponse(**result)
            return result
        except Exception as e:
            error_msg = f"为节点 '{main_node.id}' 调用 LLM 进行分组时失败。原始错误: {e}"
            logger.error(error_msg)
            raise RuntimeError(error_msg) from e

    def _optimize_single_iteration(
            self,
            graph_doc: SerializableGraphDocument,
            min_hub_degree: int,
    ) -> Tuple[SerializableGraphDocument, bool]:
        """
        对图文档进行单次优化：处理当前所有度数 >= min_hub_degree 的节点。
        Args:
            graph_doc (SerializableGraphDocument): 输入的图文档。
            min_hub_degree (int): 用于确定高连接度节点的固定的最小度数阈值。
        Returns:
            Tuple[SerializableGraphDocument, bool]: 优化后的图文档和一个布尔值，
                                                    指示本次调用是否实际处理了任何节点。
        """
        logger.debug("开始单次优化迭代...")
        optimized_graph = copy.deepcopy(graph_doc)
        was_modified = False

        # 1. 计算每个节点的连接数 (度数)
        node_connections = {}
        for rel in optimized_graph.relationships:
            node_connections[rel.source_id] = node_connections.get(rel.source_id, 0) + 1
            node_connections[rel.target_id] = node_connections.get(rel.target_id, 0) + 1

        logger.debug(f"计算出的节点连接度: {node_connections}")

        # 2. 识别当前所有度数 >= min_hub_degree 的节点
        high_degree_nodes = []
        for node in optimized_graph.nodes:
            connection_count = node_connections.get(node.id, 0)
            if connection_count >= min_hub_degree:  # 使用固定的度数阈值
                high_degree_nodes.append((node, connection_count))

        # 按度数降序排列，优先处理度数最高的节点
        high_degree_nodes.sort(key=lambda x: x[1], reverse=True)

        if not high_degree_nodes:
            logger.debug(f"未发现度数 >= {min_hub_degree} 的节点，无需优化。")
            return optimized_graph, was_modified

        logger.info(f"识别出 {len(high_degree_nodes)} 个度数 >= {min_hub_degree} 的节点。")
        was_modified = True  # 标记已修改

        # 3. 处理每个高连接度节点
        for node, degree in high_degree_nodes:
            logger.info(f"正在优化节点: '{node.id}' (连接数: {degree})")

            # 找出所有与该节点相关的连接
            related_relations = [
                rel for rel in optimized_graph.relationships
                if rel.source_id == node.id or rel.target_id == node.id
            ]

            # 获取相关节点的 ID
            related_node_ids = set()
            for rel in related_relations:
                if rel.source_id == node.id:
                    related_node_ids.add(rel.target_id)
                elif rel.target_id == node.id:
                    related_node_ids.add(rel.source_id)

            # 根据 ID 获取完整的相关节点对象
            related_nodes = [
                n for n in optimized_graph.nodes if n.id in related_node_ids
            ]

            logger.debug(f"  节点 '{node.id}' 有 {len(related_nodes)} 个相关节点。")

            if not related_nodes:
                logger.warning(f"  节点 '{node.id}' 被标记为高连接度，但未找到相关节点。跳过。")
                continue

            # 4. 调用分组函数
            try:
                grouping_result = self._group_related_nodes(main_node=node, related_nodes=related_nodes)
            except Exception as e:
                logger.error(f"为节点 '{node.id}' 分组失败: {e}")
                continue  # 跳过这个节点，继续处理下一个

            # 5. 创建中间聚合节点和关系，并收集已聚合的节点ID
            groups_created_for_this_node = 0
            aggregated_node_ids = set()  # <-- 新增：记录所有被聚合的节点ID

            for group in grouping_result.groups:
                aggregate_node_id = group.group_name
                aggregate_node = SerializableNode(
                    id=aggregate_node_id,
                    type="聚合概念",
                    properties={
                        "name": group.group_name,
                        "origin_node": node.id
                    }
                )
                optimized_graph.nodes.append(aggregate_node)
                logger.debug(f" 创建聚合节点: ID='{aggregate_node_id}', Name='{group.group_name}'")

                new_rel_to_aggregate = SerializableRelationship(
                    source_id=node.id,
                    target_id=aggregate_node_id,
                    type=group.aggregate_relationship_type,
                    properties={}
                )
                optimized_graph.relationships.append(new_rel_to_aggregate)
                logger.debug(f" 创建关系: '{node.id}' --({group.aggregate_relationship_type})--> '{aggregate_node_id}'")

                for member_node_id in group.node_ids:
                    new_rel_to_member = SerializableRelationship(
                        source_id=aggregate_node_id,
                        target_id=member_node_id,
                        type=group.member_relationship_type,
                        properties={}
                    )
                    optimized_graph.relationships.append(new_rel_to_member)
                    logger.debug(
                        f" 创建关系: '{aggregate_node_id}' --({group.member_relationship_type})--> '{member_node_id}'")
                    aggregated_node_ids.add(member_node_id)  # <-- 记录被聚合的节点

                groups_created_for_this_node += 1

            logger.info(f" 为节点 '{node.id}' 创建了 {groups_created_for_this_node} 个聚合组。")

            # 6. 删除原主节点与【已聚合节点】之间的直接关系
            if aggregated_node_ids:
                initial_rel_count = len(optimized_graph.relationships)
                optimized_graph.relationships = [
                    rel for rel in optimized_graph.relationships
                    if not (
                            (rel.source_id == node.id and rel.target_id in aggregated_node_ids) or
                            (rel.target_id == node.id and rel.source_id in aggregated_node_ids)
                    )
                ]
                removed_rel_count = initial_rel_count - len(optimized_graph.relationships)
                logger.info(f"  为节点 '{node.id}' 删除了 {removed_rel_count} 条与已聚合节点的旧直接关系。")
            else:
                logger.info(f"  节点 '{node.id}' 没有生成任何聚合组，未删除任何关系。")

            # 7. 识别未被聚合的节点（将成为孤立节点）
            unaggregated_node_ids = related_node_ids - aggregated_node_ids
            if unaggregated_node_ids:
                logger.debug(
                    f"  节点 '{node.id}' 有 {len(unaggregated_node_ids)} 个未被聚合的节点，将由后续步骤处理: {unaggregated_node_ids}")
            else:
                logger.debug(f"  节点 '{node.id}' 的所有相关节点均已聚合。")

            # 8. 调用孤立节点重连逻辑（处理 unaggregated_node_ids）
            self._reconnect_orphaned_nodes(optimized_graph, unaggregated_node_ids)

        logger.info(
            f"单次优化迭代完成。总共处理了 {len(high_degree_nodes)} 个高连接度节点。")
        return optimized_graph, was_modified

    def _sample_candidate_nodes(
            self,
            graph: SerializableGraphDocument,
            exclude_node_id: str,
            max_candidates: int = 30
    ) -> List[SerializableNode]:
        """
        采样候选连接节点，优先选择连接数多的节点。

        Args:
            graph: 当前图文档
            exclude_node_id: 需要排除的节点ID（通常是孤立节点本身）
            max_candidates: 最大候选节点数

        Returns:
            按连接数降序排列的候选节点列表
        """
        # 1. 计算每个节点的连接数
        node_degree = {}
        for rel in graph.relationships:
            node_degree[rel.source_id] = node_degree.get(rel.source_id, 0) + 1
            node_degree[rel.target_id] = node_degree.get(rel.target_id, 0) + 1

        # 2. 过滤并排序候选节点
        candidate_nodes = [
            n for n in graph.nodes
            if n.id != exclude_node_id
        ]

        # 按连接数降序排序
        candidate_nodes.sort(
            key=lambda n: node_degree.get(n.id, 0),
            reverse=True
        )

        # 3. 限制数量
        return candidate_nodes[:max_candidates]

    def _find_connection_targets(
            self,
            graph: SerializableGraphDocument,
            node: SerializableNode
    ) -> List[Tuple[str, str]]:
        """
        使用LLM为孤立节点寻找可能的连接目标。
        返回: [(target_node_id, relationship_type), ...]
        """
        llm = self._create_llm(num_ctx=self.default_num_ctx)

        # 使用新的采样方法
        candidate_nodes = self._sample_candidate_nodes(graph, node.id, max_candidates=30)

        # 构建候选节点信息
        other_nodes_info = "\n".join([
            f"节点ID: {n.id}, 类型: {n.type}, 属性: {json.dumps(n.properties, ensure_ascii=False)}, 连接数: {sum(1 for rel in graph.relationships if rel.source_id == n.id or rel.target_id == n.id)}"
            for n in candidate_nodes
        ])

        node_props = json.dumps(node.properties, ensure_ascii=False)

        prompt_template = PromptTemplate(
            template="""
            你是一个知识图谱专家。图谱中有一个节点意外变成了孤立节点，需要为其重新建立有意义的连接。

            孤立节点信息：
            - ID: {node_id}
            - 类型: {node_type}
            - 属性: {node_properties}

            图中其他可连接的节点列表（按重要性排序）：
            {other_nodes_info}

            任务：
            1. 分析孤立节点的语义和属性
            2. 在其他节点中找出1-3个最有可能与该节点建立连接的节点
            3. 为每对节点建议一个合适的中文关系类型

            输出要求：
            - 严格遵守以下JSON格式
            - 只输出JSON，不要添加任何解释
            - 如果找不到合适的连接，返回空数组
            {format_instructions}
            """,
            input_variables=["node_id", "node_type", "node_properties", "other_nodes_info"],
            partial_variables={
                "format_instructions": JsonOutputParser(
                    pydantic_object=ReconnectionResponse
                ).get_format_instructions()
            }
        )

        chain = prompt_template | llm
        response = chain.invoke({
            "node_id": node.id,
            "node_type": node.type,
            "node_properties": node_props,
            "other_nodes_info": other_nodes_info
        })

        # 解析响应并返回结果
        try:
            if isinstance(response, AIMessage):
                response = response.content
            if isinstance(response, str):
                response = response.strip()

            parser = JsonOutputParser(pydantic_object=ReconnectionResponse)
            result = parser.invoke(response)

            if isinstance(result, dict):
                result = ReconnectionResponse(**result)

            return [(suggestion.target_node_id, suggestion.relationship_type)
                    for suggestion in result.suggestions]
        except Exception as e:
            logger.error(f"为节点 '{node.id}' 寻找连接目标时失败: {e}")
            return []

    def _find_connected_component(self, graph: SerializableGraphDocument, start_node_id: str, visited: Set[str]) -> Set[
        str]:
        """
        使用 BFS 找到包含 start_node_id 的连通分量的所有节点 ID
        """
        from collections import deque

        component = set()
        queue = deque([start_node_id])
        visited.add(start_node_id)
        component.add(start_node_id)

        # 构建邻接表以提高效率
        adjacency = {}
        for rel in graph.relationships:
            adjacency.setdefault(rel.source_id, set()).add(rel.target_id)
            adjacency.setdefault(rel.target_id, set()).add(rel.source_id)

        while queue:
            current = queue.popleft()
            neighbors = adjacency.get(current, set())
            for neighbor in neighbors:
                if neighbor not in visited:
                    visited.add(neighbor)
                    component.add(neighbor)
                    queue.append(neighbor)

        return component

    def _find_all_connected_components(self, graph: SerializableGraphDocument) -> List[Set[str]]:
        """
        找出图中所有的连通分量
        """
        visited = set()
        components = []
        all_node_ids = {node.id for node in graph.nodes}

        for node_id in all_node_ids:
            if node_id not in visited:
                component = self._find_connected_component(graph, node_id, visited)
                components.append(component)

        return components

    def _reconnect_orphaned_nodes(
            self,
            graph: SerializableGraphDocument,
            potentially_orphaned_node_ids: Set[str]  # 可选参数
    ) -> None:
        """
        检查节点是否变成孤立节点或孤立连通分量，如果是，则尝试为其建立新的连接。

        Args:
            graph: 当前图文档
            potentially_orphaned_node_ids:
                - 如果提供非空集合：只检查这些节点是否孤立并处理
                - 如果为空集合：检查全图所有节点，找出并处理所有孤立节点和孤立连通分量
        """

        # 确定要检查的节点范围
        if potentially_orphaned_node_ids:
            # 局部模式：只检查指定的节点
            candidate_node_ids = potentially_orphaned_node_ids
            logger.debug(f"局部模式：检查 {len(candidate_node_ids)} 个候选节点是否孤立")
        else:
            # 全局模式：检查全图所有节点
            candidate_node_ids = {node.id for node in graph.nodes}
            logger.debug("全局模式：检查全图所有节点是否孤立")

        # 找出当前图中所有有连接的节点
        connected_node_ids = set()
        for rel in graph.relationships:
            connected_node_ids.add(rel.source_id)
            connected_node_ids.add(rel.target_id)

        # 找出真正的孤立节点（在候选范围内但没有连接的节点）
        orphaned_node_ids = candidate_node_ids - connected_node_ids

        if orphaned_node_ids:
            logger.info(f"发现 {len(orphaned_node_ids)} 个孤立节点: {orphaned_node_ids}")

            # 为每个孤立节点寻找新的连接
            for node_id in orphaned_node_ids:
                node = next((n for n in graph.nodes if n.id == node_id), None)
                if not node:
                    continue

                # 使用改进的策略寻找连接目标
                connected_targets = self._find_connection_targets(graph, node)

                if connected_targets:
                    for target_id, rel_type in connected_targets:
                        new_rel = SerializableRelationship(
                            source_id=node_id,
                            target_id=target_id,
                            type=rel_type,
                            properties={}
                        )
                        graph.relationships.append(new_rel)
                        logger.debug(
                            f"为孤立节点 '{node_id}' 重新建立了连接: '{node_id}' --({rel_type})--> '{target_id}'")
                else:
                    logger.warning(f"无法为孤立节点 '{node_id}' 找到合适的连接目标。")

        # ✅ 处理孤立的连通分量
        if not potentially_orphaned_node_ids:  # 只在全局模式下处理连通分量
            self._reconnect_isolated_components(graph)

    def _reconnect_isolated_components(self, graph: SerializableGraphDocument) -> None:
        """
        检测并重新连接孤立的连通分量
        """
        components = self._find_all_connected_components(graph)

        if len(components) <= 1:
            logger.debug("图是连通的，无需处理孤立连通分量。")
            return

        logger.info(f"发现 {len(components)} 个连通分量。")

        # 找到最大的连通分量作为"主图"
        components.sort(key=len, reverse=True)
        main_component = components[0]
        isolated_components = components[1:]

        logger.info(f"主连通分量包含 {len(main_component)} 个节点。")
        logger.info(f"发现 {len(isolated_components)} 个孤立连通分量。")

        # 为每个孤立连通分量选择一个代表节点并连接
        for i, component in enumerate(isolated_components):
            # 选择度数最高的节点作为代表（或者可以随机选择）
            node_degree = {}
            for rel in graph.relationships:
                if rel.source_id in component:
                    node_degree[rel.source_id] = node_degree.get(rel.source_id, 0) + 1
                if rel.target_id in component:
                    node_degree[rel.target_id] = node_degree.get(rel.target_id, 0) + 1

            if not node_degree:
                # 如果这个连通分量只有一个节点且无边（理论上不会出现，但做防御性编程）
                representative_node_id = next(iter(component))
            else:
                representative_node_id = max(node_degree.keys(), key=lambda x: node_degree[x])

            logger.info(f"孤立连通分量 {i + 1} (大小: {len(component)}) 选择代表节点: '{representative_node_id}'")

            # 获取代表节点的完整对象
            representative_node = next((n for n in graph.nodes if n.id == representative_node_id), None)
            if not representative_node:
                logger.warning(f"无法找到代表节点 '{representative_node_id}'，跳过该连通分量。")
                continue

            # 使用 LLM 为该代表节点寻找与主图的连接
            connected_targets = self._find_connection_targets_for_component(
                graph, representative_node, main_component
            )

            if connected_targets:
                for target_id, rel_type in connected_targets:
                    new_rel = SerializableRelationship(
                        source_id=representative_node_id,
                        target_id=target_id,
                        type=rel_type,
                        properties={}
                    )
                    graph.relationships.append(new_rel)
                    logger.debug(
                        f"为孤立连通分量的代表节点 '{representative_node_id}' 建立连接: '{representative_node_id}' --({rel_type})--> '{target_id}'")
            else:
                logger.warning(f"无法为孤立连通分量的代表节点 '{representative_node_id}' 找到合适的连接目标。")

    def _remove_remaining_isolated_nodes(self, graph: SerializableGraphDocument) -> None:
        """
        删除经过所有重连尝试后仍然孤立的节点
        """
        # 找出当前图中所有有连接的节点
        connected_node_ids = set()
        for rel in graph.relationships:
                connected_node_ids.add(rel.source_id)
                connected_node_ids.add(rel.target_id)

        # 找出所有孤立节点
        all_node_ids = {node.id for node in graph.nodes}
        isolated_node_ids = all_node_ids - connected_node_ids

        if not isolated_node_ids:
            logger.info("没有发现需要删除的孤立节点。")
            return

        logger.info(f"发现 {len(isolated_node_ids)} 个仍然孤立的节点，将被删除: {isolated_node_ids}")

        # 删除孤立节点
        original_node_count = len(graph.nodes)
        graph.nodes = [node for node in graph.nodes if node.id not in isolated_node_ids]

        # 注意：这些节点已经是孤立的，所以 relationships 中应该没有涉及它们的边
        # 但为了保险起见，还是清理一下（防御性编程）
        graph.relationships = [
            rel for rel in graph.relationships
            if rel.source_id not in isolated_node_ids and rel.target_id not in isolated_node_ids
        ]

        removed_count = original_node_count - len(graph.nodes)
        logger.info(f"成功删除 {removed_count} 个孤立节点。")
    def _find_connection_targets_for_component(
            self,
            graph: SerializableGraphDocument,
            node: SerializableNode,
            main_component: Set[str]
    ) -> List[Tuple[str, str]]:
        """
        为连通分量的代表节点寻找与主图的连接目标
        限制候选节点只能来自主图
        """
        llm = self._create_llm(num_ctx=self.default_num_ctx)

        # 限制候选节点为主图中的节点
        candidate_nodes = [
            n for n in graph.nodes
            if n.id in main_component
        ]

        # 按连接数排序（优先选择连接多的节点）
        node_degree = {}
        for rel in graph.relationships:
            if rel.source_id in main_component:
                node_degree[rel.source_id] = node_degree.get(rel.source_id, 0) + 1
            if rel.target_id in main_component:
                node_degree[rel.target_id] = node_degree.get(rel.target_id, 0) + 1

        candidate_nodes.sort(
            key=lambda n: node_degree.get(n.id, 0),
            reverse=True
        )

        # 取前30个作为候选
        candidate_nodes = candidate_nodes[:30]

        # 构建候选节点信息
        other_nodes_info = "\n".join([
            f"节点ID: {n.id}, 类型: {n.type}, 属性: {json.dumps(n.properties, ensure_ascii=False)}, 连接数: {node_degree.get(n.id, 0)}"
            for n in candidate_nodes
        ])

        node_props = json.dumps(node.properties, ensure_ascii=False)

        prompt_template = PromptTemplate(
            template="""
            你是一个知识图谱专家。图谱中有一个连通分量意外与主图断开连接，需要为其代表节点建立有意义的连接以重新融入主图。

            代表节点信息（来自孤立连通分量）：
            - ID: {node_id}
            - 类型: {node_type}
            - 属性: {node_properties}

            主图中的候选连接节点列表（按重要性排序）：
            {other_nodes_info}

            任务：
            1. 分析代表节点的语义和属性
            2. 在主图节点中找出1-3个最有可能与该节点建立连接的节点
            3. 为每对节点建议一个合适的中文关系类型

            输出要求：
            - 严格遵守以下JSON格式
            - 只输出JSON，不要添加任何解释
            - 如果找不到合适的连接，返回空数组
            {format_instructions}
            """,
            input_variables=["node_id", "node_type", "node_properties", "other_nodes_info"],
            partial_variables={
                "format_instructions": JsonOutputParser(
                    pydantic_object=ReconnectionResponse
                ).get_format_instructions()
            }
        )

        chain = prompt_template | llm
        response = chain.invoke({
            "node_id": node.id,
            "node_type": node.type,
            "node_properties": node_props,
            "other_nodes_info": other_nodes_info
        })

        # 解析响应并返回结果
        try:
            if isinstance(response, AIMessage):
                response = response.content
            if isinstance(response, str):
                response = response.strip()

            parser = JsonOutputParser(pydantic_object=ReconnectionResponse)
            result = parser.invoke(response)

            if isinstance(result, dict):
                result = ReconnectionResponse(**result)

            return [(suggestion.target_node_id, suggestion.relationship_type)
                    for suggestion in result.suggestions]
        except Exception as e:
            logger.error(f"为连通分量代表节点 '{node.id}' 寻找连接目标时失败: {e}")
            return []

    def _remove_self_loops(self, graph: SerializableGraphDocument) -> None:
        """
        删除图中所有自我指涉的连接（source_id == target_id）
        """
        original_rel_count = len(graph.relationships)

        # 过滤掉自我指涉的关系
        graph.relationships = [
            rel for rel in graph.relationships
            if rel.source_id != rel.target_id
        ]

        removed_count = original_rel_count - len(graph.relationships)

        if removed_count > 0:
            logger.info(f"删除了 {removed_count} 个自我指涉的连接。")
        else:
            logger.debug("未发现自我指涉的连接。")
    def optimize_graph_document(
            self,
            graph_doc: SerializableGraphDocument,
            min_hub_degree: int = 50,  # 默认停止条件：所有节点度数 < 20
            max_iterations: int = 3,  # 默认最大迭代次数
            verbose: bool = True
    ) -> SerializableGraphDocument:
        """
        迭代优化图文档，直到所有节点的度数都小于 min_hub_degree 或达到最大迭代次数。
        Args:
            graph_doc (SerializableGraphDocument): 输入的图文档。
            min_hub_degree (int): 停止优化的度数阈值。当所有节点度数都小于此值时停止。
                                  默认为 10。
            max_iterations (int): 最大迭代次数，防止无限循环。默认为 10。
            verbose (bool): 是否打印详细日志。默认为 True。
        Returns:
            SerializableGraphDocument: 优化后的图文档。
        """
        current_graph = copy.deepcopy(graph_doc)
        iteration = 0

        if verbose:
            logger.info(f"开始迭代优化图文档...")
            logger.info(f"停止条件: 所有节点度数 < {min_hub_degree}")
            logger.info(f"最大迭代次数: {max_iterations}")

        while iteration < max_iterations:
            if verbose:
                logger.info(f"--- 开始第 {iteration + 1} 轮优化 ---")

            # 执行单次优化
            optimized_graph, was_modified = self._optimize_single_iteration(
                current_graph,
                min_hub_degree
            )

            # 更新当前图
            current_graph = optimized_graph

            # --- 停止条件 1: 检查是否没有节点被修改 (即没有找到 >= min_hub_degree 的节点) ---
            if not was_modified:
                if verbose:
                    logger.info(f"第 {iteration + 1} 轮优化未发现需要处理的节点 (所有节点度数 < {min_hub_degree})。")
                    logger.info("优化完成，已达到停止条件。")
                break

            if verbose:
                current_nodes = len(current_graph.nodes)
                current_rels = len(current_graph.relationships)
                logger.info(f"第 {iteration + 1} 轮优化完成。当前图: {current_nodes} 节点, {current_rels} 关系。")

            iteration += 1

        if iteration >= max_iterations and verbose:
            logger.info(f"已达到最大迭代次数 {max_iterations}，停止优化。")

        # ✅ 在所有迭代完成后，统一处理全图孤立节点
        if verbose:
            logger.info("开始全局孤立节点检查和处理...")
        self._reconnect_orphaned_nodes(current_graph, set())  # 传空集触发全局模式

        # ✅ 清理自我指涉的连接
        if verbose:
            logger.info("开始清理自我指涉的连接...")
        self._remove_self_loops(current_graph)

        # ✅ 最后一步：删除仍然孤立的节点
        if verbose:
            logger.info("开始清理仍然孤立的节点...")
        self._remove_remaining_isolated_nodes(current_graph)

        if verbose:
            final_nodes_count = len(current_graph.nodes)
            final_rels_count = len(current_graph.relationships)
            logger.info(f"迭代优化流程结束。最终图包含 {final_nodes_count} 个节点和 {final_rels_count} 条关系。")

        return current_graph


# ==============================
# 测试代码 (独立的 main 函数)
# ==============================

if __name__ == "__main__":
    import logging
    import os
    import config

    logging.basicConfig(level=logging.INFO, format='[%(asctime)s] [%(levelname)s] %(message)s')
    logger = logging.getLogger(__name__)
    logger.info(f"当前配置的缓存目录 CACHE_DIR: {config.CACHE_DIR}")
    logger.info(f"当前工作目录: {os.getcwd()}")

    optimizer = GraphOptimizer(
        model_name="qwen3:30b-a3b-instruct-2507-q4_K_M",
        base_url="http://localhost:11434",
    )

    logger.info("GraphOptimizer 初始化完成。")
    cache_hash = "8a9a86304720a55a06192babf8da86b044ad877ee9ff309926c331e900fb8dc7"

    logger.info("=== 开始测试 GraphOptimizer.optimize_graph_document (迭代版本) ===")



    docs_raw = load_cache(cache_hash)
    docs = None
    if docs_raw:
        if isinstance(docs_raw, dict):
            docs = SerializableGraphDocument.from_dict(docs_raw)
        elif isinstance(docs_raw, SerializableGraphDocument):
            docs = docs_raw

    if docs is None:
        logger.error(f"加载缓存失败：无法找到或加载哈希值为 {cache_hash} 的缓存数据。")
        logger.info("请确保：")
        logger.info("1. 之前确实运行过生成此哈希对应缓存的提取流程。")
        logger.info(f"2. 缓存目录配置正确: {config.CACHE_DIR}")
        logger.info("3. 缓存文件未被意外删除。")
        logger.info("4. 缓存文件没有损坏。")
        logger.info("5. rag/cache_manager.py 已按要求修改，能在 graph_docs 子目录下查找文件。")
        logger.error("未找到指定的缓存文件，程序无法继续。")
        exit(1)

    if not isinstance(docs, SerializableGraphDocument):
        logger.error(f"加载的缓存数据类型错误: {type(docs)}，期望是 SerializableGraphDocument。")
        exit(1)
    else:
        logger.info("成功加载并验证了缓存数据。")

    try:
        nodes_count = len(docs.nodes) if docs.nodes else 0
        rels_count = len(docs.relationships) if docs.relationships else 0
        logger.info(f"加载的图文档包含 {nodes_count} 个节点和 {rels_count} 条关系。")
    except Exception as e:
        logger.warning(f"无法获取加载数据的摘要信息: {e}")

    logger.info("开始调用 optimize_graph_document (迭代版本)...")
    try:
        optimized_docs = optimizer.optimize_graph_document(docs)

        if optimized_docs:
            logger.info("optimize_graph_document (迭代版本) 调用成功。")
            try:
                opt_nodes_count = len(optimized_docs.nodes) if optimized_docs.nodes else 0
                opt_rels_count = len(optimized_docs.relationships) if optimized_docs.relationships else 0
                logger.info(f"最终优化后的图文档包含 {opt_nodes_count} 个节点和 {opt_rels_count} 条关系。")

                # --- 4. 使用 graph_manager 的逻辑保存优化结果 ---

                # 生成一个唯一的 cache_key (可以基于原始 hash 或生成新的)
                # 方式一：基于原始 hash 和时间戳/UUID 生成新 key
                timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
                unique_suffix = uuid.uuid4().hex[:8]  # 取前8位作为简短唯一标识
                optimized_cache_key = f"optimized_iter_{cache_hash}_{timestamp_str}_{unique_suffix}"

                # 方式二：如果希望使用 UUID 作为主要标识
                # optimized_cache_key = f"optimized_{uuid.uuid4().hex}"

                # 构造完整的文件路径 (利用 graph_manager 定义的 GRAPH_CACHE_DIR)
                output_data_path = os.path.join(GRAPH_CACHE_DIR, f"{optimized_cache_key}.json")
                output_metadata_path = os.path.join(GRAPH_CACHE_DIR, f"{optimized_cache_key}_metadata.json")

                # 保存图谱数据 (这部分逻辑与 graph_manager 类似)
                with open(output_data_path, 'w', encoding='utf-8') as f:
                    json.dump(optimized_docs.to_dict(), f, ensure_ascii=False, indent=2)
                logger.info(f"✅ 优化后的图谱数据已保存到: {output_data_path}")

                # (可选) 创建并保存元数据 (复用或参考 graph_manager 的逻辑)
                # 从原始缓存加载元数据（如果存在且需要继承部分信息）
                original_metadata = {}
                original_metadata_path = os.path.join(GRAPH_CACHE_DIR, f"{cache_hash}_metadata.json")
                if os.path.exists(original_metadata_path):
                    try:
                        with open(original_metadata_path, 'r', encoding='utf-8') as f:
                            original_metadata = json.load(f)
                    except Exception as e:
                        logger.warning(f"加载原始元数据 {original_metadata_path} 时出错: {e}")

                # 构造新的元数据，可以继承部分原始信息
                new_metadata = {
                    "source_cache_key": cache_hash,  # 记录来源
                    "optimization_params": {
                        "min_hub_degree": 15,
                        "max_iterations": 2,
                    },
                    "final_stats": {
                        "nodes_count": opt_nodes_count,
                        "relationships_count": opt_rels_count,
                    },
                    "created_at": datetime.now().isoformat(),
                    "description": f"Optimized version of graph {cache_hash}",
                    # 继承原始元数据的部分字段 (可选)
                    "novel_name": original_metadata.get("novel_name", ""),
                    "chapter_name": original_metadata.get("chapter_name", ""),
                    "model_name": original_metadata.get("model_name", ""),
                    "schema_name": original_metadata.get("schema_name", ""),
                    "chunk_size": original_metadata.get("chunk_size", ""),
                    "chunk_overlap": original_metadata.get("chunk_overlap", ""),
                    "num_ctx": original_metadata.get("num_ctx", ""),
                    # 可以添加优化器相关信息
                    "optimizer_info": {
                        "optimizer_type": "GraphOptimizer",
                        "min_hub_degree_used": 15,
                    }
                }
                with open(output_metadata_path, 'w', encoding='utf-8') as f:
                    json.dump(new_metadata, f, ensure_ascii=False, indent=2)
                logger.info(f"✅ 优化后的图谱元数据已保存到: {output_metadata_path}")
                logger.info(f"优化后的图谱 Cache Key: {optimized_cache_key}")

            except Exception as save_error:
                logger.error(f"❌ 保存优化结果时出错: {save_error}", exc_info=True)
        else:
            logger.warning("optimize_graph_document 返回了 None。")
    except Exception as e:
        logger.error(f"调用 optimize_graph_document 时发生错误: {e}", exc_info=True)
        exit(1)
    logger.info("=== GraphOptimizer.optimize_graph_document (迭代版本) 测试完成 ===")
