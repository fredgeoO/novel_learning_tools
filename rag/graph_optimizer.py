# rag/graph_optimizer.py

import json
import logging
import copy
import uuid
import os
from datetime import datetime
from typing import List, Dict, Tuple, Optional, Any, Set
from langchain_openai import ChatOpenAI
from langchain_ollama import OllamaLLM
from rag.graph_types import (
    SerializableNode,
    SerializableRelationship,
    SerializableGraphDocument,
    # AggregateGroupingResponse, # 不再需要
    # ReconnectionResponse, # 暂时不使用
    # BatchReconnectionResponse, # 暂时不使用
    # BatchReconnectionSuggestion # 暂时不使用
)
from config import (
    DEFAULT_MODEL as CONFIG_DEFAULT_MODEL,
    DEFAULT_BASE_URL as CONFIG_DEFAULT_BASE_URL,
    DEFAULT_TEMPERATURE as CONFIG_DEFAULT_TEMPERATURE,
    DEFAULT_NUM_CTX as CONFIG_DEFAULT_NUM_CTX,
    DEFAULT_CHUNK_SIZE as CONFIG_DEFAULT_CHUNK_SIZE,
    DEFAULT_CHUNK_OVERLAP as CONFIG_DEFAULT_CHUNK_OVERLAP,
)
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
            # --- LLM 配置参数 (用于聚合节点命名) ---
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

    def _detect_communities(self, graph: SerializableGraphDocument) -> Dict[str, int]:
        """
        使用 NetworkX 和 Louvain 算法检测图的社区。
        Args:
            graph (SerializableGraphDocument): 输入的图文档。
        Returns:
            Dict[str, int]: 节点ID到社区ID的映射。
        """
        import networkx as nx
        try:
            # 尝试导入 python-louvain (community)
            import community as community_louvain
        except ImportError:
            try:
                # 尝试导入 nx_cugraph (如果可用且支持 louvain)
                import nx_cugraph as nxcg
                logger.info("Using nx_cugraph for community detection.")
                networkx_func = nxcg.community.louvain_communities
            except ImportError:
                # 如果都失败，抛出错误
                logger.error("Neither 'community' (python-louvain) nor 'nx_cugraph' is available for community detection.")
                logger.error("Please install one: 'pip install python-louvain' or 'pip install nx-cugraph'")
                raise ImportError("Community detection library not found.")

            # 使用 nx_cugraph
            G_nx = nx.Graph()
            for rel in graph.relationships:
                # Louvain 算法通常处理无向图，我们将其视为无向
                G_nx.add_edge(rel.source_id, rel.target_id)

            # nx_cugraph 的 louvain 返回的是 frozenset 的列表
            communities = networkx_func(G_nx)
            partition = {}
            for community_id, community_nodes in enumerate(communities):
                for node_id in community_nodes:
                    partition[node_id] = community_id
            return partition

        # 使用 python-louvain
        logger.info("Using python-louvain for community detection.")
        G_nx = nx.Graph()
        for rel in graph.relationships:
            # Louvain 算法通常处理无向图，我们将其视为无向
            G_nx.add_edge(rel.source_id, rel.target_id)

        partition = community_louvain.best_partition(G_nx)
        return partition

    def _group_nodes_evenly(self, nodes: List[SerializableNode], max_group_size: int) -> List[List[SerializableNode]]:
        """
        将节点列表均匀地分成多个组，每组不超过指定大小
        Args:
            nodes: 要分组的节点列表
            max_group_size: 每组的最大节点数
        Returns:
            分组后的节点列表的列表
        """
        if not nodes or max_group_size <= 0:
            return []

        # 如果总节点数小于等于最大组大小，直接返回一个组
        if len(nodes) <= max_group_size:
            return [nodes]

        # 均匀分组
        groups = []
        for i in range(0, len(nodes), max_group_size):
            group = nodes[i:i + max_group_size]
            groups.append(group)

        return groups

    def _optimize_single_iteration(
            self,
            graph_doc: SerializableGraphDocument,
            min_hub_degree: int,
            max_aggregate_group_size: int = 5  # 新增参数：聚合组的最大大小
    ) -> Tuple[SerializableGraphDocument, bool]:
        """
        对图文档进行单次优化：处理当前所有度数 >= min_hub_degree 的节点。
        Args:
            graph_doc (SerializableGraphDocument): 输入的图文档。
            min_hub_degree (int): 用于确定高连接度节点的固定的最小度数阈值。
            max_aggregate_group_size (int): 每个聚合组的最大节点数，用于均匀分组。
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

            # 4. 使用均匀分组策略，而不是社区检测
            # 将相关节点均匀分组
            evenly_grouped_nodes = self._group_nodes_evenly(related_nodes, max_aggregate_group_size)

            logger.debug(
                f"  节点 '{node.id}' 的相关节点被均匀分为 {len(evenly_grouped_nodes)} 个组，每组最多 {max_aggregate_group_size} 个节点。")

            if not evenly_grouped_nodes:
                logger.info(f"  节点 '{node.id}' 的相关节点无法分组，跳过聚合。")
                continue

            # 5. 为每个组创建聚合节点和关系，并收集已聚合的节点ID
            groups_created_for_this_node = 0
            aggregated_node_ids = set()  # 记录所有被聚合的节点ID

            for group_idx, nodes_in_group in enumerate(evenly_grouped_nodes):
                # 生成聚合节点ID (使用枢纽节点ID和组索引)
                aggregate_node_id = f"{node.id}_agg_{group_idx:03d}"  # 格式: 原节点ID_agg_000, agg_001, ...

                # 使用原始节点的名称作为聚合节点的名称
                original_name = node.properties.get("name", node.id)  # 优先使用name属性，否则使用id
                aggregate_node_name = f"{original_name}_聚合_{group_idx:03d}"

                aggregate_node = SerializableNode(
                    id=aggregate_node_id,
                    type="聚合节点",
                    properties={
                        "name": aggregate_node_name,
                        "origin_hub_node": node.id,
                        "group_index": group_idx,
                        "member_count": len(nodes_in_group),
                        "max_group_size": max_aggregate_group_size  # 记录参数
                    }
                )
                optimized_graph.nodes.append(aggregate_node)
                logger.debug(
                    f" 创建聚合节点: ID='{aggregate_node_id}', Name='{aggregate_node_name}', Group={group_idx}, Members={len(nodes_in_group)}")

                # 创建枢纽节点到聚合节点的关系
                new_rel_to_aggregate = SerializableRelationship(
                    source_id=node.id,
                    target_id=aggregate_node_id,
                    type="聚合连接",
                    properties={"group_index": group_idx}
                )
                optimized_graph.relationships.append(new_rel_to_aggregate)
                logger.debug(f" 创建关系: '{node.id}' --(聚合连接)--> '{aggregate_node_id}'")

                # 创建聚合节点到其成员节点的关系
                for member_node in nodes_in_group:
                    new_rel_to_member = SerializableRelationship(
                        source_id=aggregate_node_id,
                        target_id=member_node.id,
                        type="包含成员",
                        properties={}
                    )
                    optimized_graph.relationships.append(new_rel_to_member)
                    logger.debug(f" 创建关系: '{aggregate_node_id}' --(包含成员)--> '{member_node.id}'")
                    aggregated_node_ids.add(member_node.id)  # 记录被聚合的节点

                groups_created_for_this_node += 1

            logger.info(f" 为节点 '{node.id}' 创建了 {groups_created_for_this_node} 个均匀聚合组。")

            # 6. 删除原枢纽节点与【已聚合节点】之间的直接关系
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

        logger.info(
            f"单次优化迭代完成。总共处理了 {len(high_degree_nodes)} 个高连接度节点。")
        return optimized_graph, was_modified

    # --- 暂时移除孤立节点处理相关方法 ---
    # _sample_candidate_nodes, _find_connection_targets, _find_connected_component,
    # _find_all_connected_components, _reconnect_orphaned_nodes, _reconnect_isolated_components,
    # _remove_remaining_isolated_nodes, _find_connection_targets_for_component,
    # _reconnect_component_representatives_batch, _find_connection_targets_batch,
    # _sample_candidate_nodes_batch 等方法在此版本中被移除。

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
            min_hub_degree: int = 20,
            max_iterations: int = 3,
            max_aggregate_group_size: int = 5,  # 新增参数
            verbose: bool = True
    ) -> SerializableGraphDocument:
        """
        迭代优化图文档，直到所有节点的度数都小于 min_hub_degree 或达到最大迭代次数。
        Args:
            graph_doc (SerializableGraphDocument): 输入的图文档。
            min_hub_degree (int): 停止优化的度数阈值。
            max_iterations (int): 最大迭代次数。
            max_aggregate_group_size (int): 每个聚合组的最大节点数。
            verbose (bool): 是否打印详细日志。
        Returns:
            SerializableGraphDocument: 优化后的图文档。
        """
        current_graph = copy.deepcopy(graph_doc)
        iteration = 0

        if verbose:
            logger.info(f"开始迭代优化图文档...")
            logger.info(f"停止条件: 所有节点度数 < {min_hub_degree}")
            logger.info(f"最大迭代次数: {max_iterations}")
            logger.info(f"最大聚合组大小: {max_aggregate_group_size}")

        while iteration < max_iterations:
            if verbose:
                logger.info(f"--- 开始第 {iteration + 1} 轮优化 ---")

            # 执行单次优化（传入新的参数）
            optimized_graph, was_modified = self._optimize_single_iteration(
                current_graph,
                min_hub_degree,
                max_aggregate_group_size
            )

            # 更新当前图
            current_graph = optimized_graph

            # --- 停止条件 1: 检查是否没有节点被修改 ---
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

        # --- 清理自我指涉的连接 ---
        if verbose:
            logger.info("开始清理自我指涉的连接...")
        self._remove_self_loops(current_graph)

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
    cache_hash = "1f84331574d494ccd2ac92839548626db371e3f21a480ba4490d601ac06600c6"

    logger.info("=== 开始测试 GraphOptimizer.optimize_graph_document (社区检测版本) ===")

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

    logger.info("开始调用 optimize_graph_document (社区检测版本)...")
    try:
        optimized_docs = optimizer.optimize_graph_document(docs)

        if optimized_docs:
            logger.info("optimize_graph_document (社区检测版本) 调用成功。")
            try:
                opt_nodes_count = len(optimized_docs.nodes) if optimized_docs.nodes else 0
                opt_rels_count = len(optimized_docs.relationships) if optimized_docs.relationships else 0
                logger.info(f"最终优化后的图文档包含 {opt_nodes_count} 个节点和 {opt_rels_count} 条关系。")

                # --- 4. 使用 graph_manager 的逻辑保存优化结果 ---

                # 生成一个唯一的 cache_key (可以基于原始 hash 或生成新的)
                # 方式一：基于原始 hash 和时间戳/UUID 生成新 key
                timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
                unique_suffix = uuid.uuid4().hex[:8]  # 取前8位作为简短唯一标识
                optimized_cache_key = f"optimized_community_{cache_hash}_{timestamp_str}_{unique_suffix}"

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
                        "min_hub_degree": 30, # 使用实际使用的参数
                        "max_iterations": 3,  # 使用实际使用的参数
                        "optimization_method": "community_detection_based_aggregation"
                    },
                    "final_stats": {
                        "nodes_count": opt_nodes_count,
                        "relationships_count": opt_rels_count,
                    },
                    "created_at": datetime.now().isoformat(),
                    "description": f"Optimized version of graph {cache_hash} using community detection.",
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
                        "min_hub_degree_used": 30, # 记录实际使用的参数
                        "method": "community_detection"
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
    logger.info("=== GraphOptimizer.optimize_graph_document (社区检测版本) 测试完成 ===")
