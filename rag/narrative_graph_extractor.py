# inputs/rag/narrative_graph_extractor.py
import logging
import os
import time
import math
from typing import List, Tuple, Any, Optional, Dict

# --- 导入所需模块 ---
from langchain_openai import ChatOpenAI
from langchain_ollama import OllamaLLM
from langchain_experimental.graph_transformers import LLMGraphTransformer
from langchain_core.documents import Document
from langchain.text_splitter import RecursiveCharacterTextSplitter

# --- 导入共享配置 ---
# 从共享配置文件导入默认值
from config import (
    DEFAULT_MODEL as CONFIG_DEFAULT_MODEL,
    DEFAULT_BASE_URL as CONFIG_DEFAULT_BASE_URL,
    DEFAULT_TEMPERATURE as CONFIG_DEFAULT_TEMPERATURE,
    DEFAULT_NUM_CTX as CONFIG_DEFAULT_NUM_CTX,
    DEFAULT_CHUNK_SIZE as CONFIG_DEFAULT_CHUNK_SIZE,
    DEFAULT_CHUNK_OVERLAP as CONFIG_DEFAULT_CHUNK_OVERLAP,
)

from rag.config_models import ExtractionConfig
from rag.narrative_schema import MINIMAL_SCHEMA, generate_auto_schema
from rag.cache_manager import save_cache, load_cache, generate_cache_metadata, get_cache_key_from_config
from rag.narrative_schema import split_schema
from rag.graph_optimizer import GraphOptimizer

# --- 配置日志 ---
logger = logging.getLogger(__name__)

# --- 默认配置 (使用从 config.py 导入的值) ---
# 删除原来的 DEFAULT_* = ... 定义，改用导入的值并可以（可选地）重命名以避免混淆
# 这样，所有默认配置都统一由 rag.config 管理
DEFAULT_SCHEMA = MINIMAL_SCHEMA
DEFAULT_MODEL = CONFIG_DEFAULT_MODEL
DEFAULT_BASE_URL = CONFIG_DEFAULT_BASE_URL
DEFAULT_TEMPERATURE = CONFIG_DEFAULT_TEMPERATURE
DEFAULT_NUM_CTX = CONFIG_DEFAULT_NUM_CTX
DEFAULT_CHUNK_SIZE = CONFIG_DEFAULT_CHUNK_SIZE
DEFAULT_CHUNK_OVERLAP = CONFIG_DEFAULT_CHUNK_OVERLAP

from rag.graph_types import (
    SerializableNode,
    SerializableGraphDocument,
)


# ==============================
# 核心类：NarrativeGraphExtractor
# ==============================

class NarrativeGraphExtractor:
    """
    用于从小说文本中提取叙事元素和关系，并构建知识图谱的类。
    """
    # --- Schema 拆分配置 ---
    SCHEMA_SPLIT_THRESHOLD_RELATIONSHIPS = 5

    def __init__(
            self,
            model_name: str = DEFAULT_MODEL,
            base_url: str = DEFAULT_BASE_URL,
            temperature: float = DEFAULT_TEMPERATURE,
            default_num_ctx: int = DEFAULT_NUM_CTX,
            default_chunk_size: int = DEFAULT_CHUNK_SIZE,
            default_chunk_overlap: int = DEFAULT_CHUNK_OVERLAP,

            # 远程 API 支持
            remote_api_key: Optional[str] = None,
            remote_base_url: Optional[str] = None,
            remote_model_name: Optional[str] = None,

            allowed_nodes: Optional[List[str]] = None,
            allowed_relationships: Optional[List[str]] = None,

            # Schema 模式
            schema_mode: str = "约束"  # "约束" 或 "无约束"
    ):
        # 基础配置
        self.model_name = model_name
        self.base_url = base_url
        self.temperature = temperature
        self.default_num_ctx = default_num_ctx
        self.default_chunk_size = default_chunk_size
        self.default_chunk_overlap = default_chunk_overlap

        # 远程 API 配置
        self.remote_api_key = remote_api_key or os.getenv("ARK_API_KEY")
        self.remote_base_url = remote_base_url
        self.remote_model_name = remote_model_name

        # 判断是否使用远程 API
        self.use_remote_api = bool(
            self.remote_api_key and
            self.remote_base_url and
            self.remote_model_name
        )

        # Schema 配置
        if schema_mode == "无约束":
            # 无约束模式：允许所有节点和关系类型
            self.allowed_nodes = []
            self.allowed_relationships = []
            logger.info("Using unrestricted mode - no node/relationship constraints")
        else:
            # 约束模式：使用提供的限制或默认schema
            self.allowed_nodes = allowed_nodes or DEFAULT_SCHEMA["elements"]
            self.allowed_relationships = allowed_relationships or DEFAULT_SCHEMA["relationships"]

        logger.info(
            f"NarrativeGraphExtractor initialized with {'remote API' if self.use_remote_api else 'local Ollama'} model."
        )
        if schema_mode == "无约束":
            logger.info("Using unrestricted schema mode")
        else:
            logger.info(
                f"Using schema with {len(self.allowed_nodes)} elements and {len(self.allowed_relationships)} relationships"
            )

    # ==============================
    # 工具方法
    # ==============================

    def _get_entity_name(self, node):
        """获取实体的真实名称 - 通用方法"""
        # LLMGraphTransformer通常将实体名称放在id字段中
        if node.id:
            return node.id

        # 如果id为空，尝试从properties中获取name
        if 'name' in node.properties and node.properties['name']:
            return node.properties['name']

        # 如果都没有找到，返回id或空字符串
        return node.id or ""

    @staticmethod
    def estimate_tokens(text: str, is_chinese: bool = True) -> int:
        """估算文本的 token 数量"""
        if is_chinese:
            return math.ceil(len(text) * 1.5)
        return len(text.split())

    # ==============================
    # 核心组件创建方法
    # ==============================

    def _create_llm(self, num_ctx: int, local: bool = True, enable_thinking: bool = False) -> Any:
        """创建并返回配置好的 LLM 实例（本地或远程）。"""
        if not local and self.use_remote_api:
            logger.info(f"Using remote OpenAI-compatible API: {self.remote_model_name} at {self.remote_base_url}")
            return ChatOpenAI(
                model=self.remote_model_name,
                openai_api_key=self.remote_api_key,
                openai_api_base=self.remote_base_url.strip(),
                temperature=self.temperature,
                max_tokens=num_ctx,

            )
        else:
            logger.info(f"Using local Ollama model: {self.model_name}")
            return OllamaLLM(
                model=self.model_name,
                base_url=self.base_url,
                temperature=self.temperature,
                num_ctx=num_ctx

            )

    def _process_single_chunk(
            self,
            chunk_index: int,  # 块索引 (用于日志)
            total_chunks: int,  # 总块数 (用于日志)
            single_doc: Document,  # 要处理的 Langchain Document 块
            graph_transformer: LLMGraphTransformer,  # 已配置好的 GraphTransformer 实例
            node_id_map: Dict[str, str],  # 节点 ID 映射字典 (会就地修改)
            normalized_nodes: Dict[str, SerializableNode],  # 标准化节点字典 (会就地修改)
            global_mention_counter: int,  # 全局提及计数器 (会就地修改)
            verbose: bool = True  # 是否打印详细日志
    ) -> Tuple[Optional[SerializableGraphDocument], int, int, int]:
        """
        处理单个文本块并提取图谱信息。

        Args:
            chunk_index (int): 当前块的索引 (从0开始)。
            total_chunks (int): 总的块数量。
            single_doc (Document): 要处理的 Langchain Document。
            graph_transformer (LLMGraphTransformer): 配置好的 GraphTransformer 实例。
            node_id_map (Dict[str, str]): 节点 ID 映射字典 (会就地修改)。
            normalized_nodes (Dict[str, SerializableNode]): 标准化节点字典 (会就地修改)。
            global_mention_counter (int): 全局提及计数器 (会就地修改)。
            verbose (bool): 是否打印详细日志。

        Returns:
            Tuple[Optional[SerializableGraphDocument], int, int, int]:
                - 提取的 SerializableGraphDocument (如果失败则为 None)
                - 该块的节点数
                - 该块的关系数
                - 更新后的 global_mention_counter
        """
        chunk_text = single_doc.page_content
        chunk_nodes_count = 0
        chunk_relationships_count = 0
        result_graph_doc = None

        if verbose:
            chunk_tokens = self.estimate_tokens(chunk_text)
            logger.info(f"  -> 处理块 {chunk_index + 1}/{total_chunks} (估算 Token 数: ~{chunk_tokens})")

        try:
            chunk_graph_docs = graph_transformer.convert_to_graph_documents([single_doc])
            if chunk_graph_docs and len(chunk_graph_docs) > 0:
                graph_doc = chunk_graph_docs[0]
                serializable_graph_doc = SerializableGraphDocument.from_langchain_graph_document(graph_doc)

                chunk_nodes_count = len(serializable_graph_doc.nodes)
                chunk_relationships_count = len(serializable_graph_doc.relationships)

                # 处理节点和关系的ID标准化
                global_mention_counter = self._process_nodes_and_relationships(
                    serializable_graph_doc, node_id_map, normalized_nodes, global_mention_counter
                )

                result_graph_doc = serializable_graph_doc

                if verbose:
                    logger.info(
                        f"      -> 块 {chunk_index + 1} 转换成功! 节点数: {chunk_nodes_count}, 关系数: {chunk_relationships_count}")
            else:
                if verbose:
                    logger.warning(f"      -> 块 {chunk_index + 1} 未返回图文档。")
                # 注意：这里不创建空的 SerializableGraphDocument，由调用者决定是否添加空结果
                # 或者可以返回一个空的，取决于主逻辑如何处理

        except Exception as e:
            if verbose:
                logger.error(f"      -> 块 {chunk_index + 1} 转换出错: {e}")

        return result_graph_doc, chunk_nodes_count, chunk_relationships_count, global_mention_counter

    def _create_graph_transformer(self, config: Optional[ExtractionConfig] = None) -> LLMGraphTransformer:
        """创建并返回配置好的 LLMGraphTransformer 实例。"""
        num_ctx = config.num_ctx if config and config.num_ctx else self.default_num_ctx
        local= config.use_local
        llm = self._create_llm(num_ctx, local=local)

        return LLMGraphTransformer(
            llm=llm,
            allowed_nodes=self.allowed_nodes if self.allowed_nodes else [],
            allowed_relationships=self.allowed_relationships if self.allowed_relationships else [],

            strict_mode=False,
            additional_instructions="""
                提取要求：
                1. id和type必须以中文描述
                2. 节点ID必须是内容本身（如对白节点ID就是对白内容）
                3. 连接所有相关实体，避免孤立节点
                4. 保持输出简洁，避免冗长描述
                5. 如遇到复杂内容，优先提取核心实体和关系
            """
        )

    def _split_text(self, text: str, chunk_size: Optional[int] = None, chunk_overlap: Optional[int] = None) -> List[
        Document]:
        """使用 RecursiveCharacterTextSplitter 分割文本。"""
        size = chunk_size or self.default_chunk_size
        overlap = chunk_overlap or self.default_chunk_overlap

        logger.info(f"正在分割文本... (chunk_size={size}, chunk_overlap={overlap})")
        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=size,
            chunk_overlap=overlap,
            length_function=len,
            is_separator_regex=False,
        )
        docs = text_splitter.create_documents([text])
        logger.info(f"文本分割完成，共得到 {len(docs)} 个块。")
        return docs

    # ==============================
    # 数据处理方法
    # ==============================

    def _process_nodes_and_relationships(self, serializable_graph_doc, node_id_map, normalized_nodes,
                                         global_mention_counter):
        """处理节点和关系的ID标准化 - 通用方法"""
        # 处理节点 - 统一ID为实体名称
        for node in serializable_graph_doc.nodes:
            # 获取实体的真实名称作为ID（通用方法）
            entity_name = self._get_entity_name(node)

            # 保存原始ID和实体名称的映射
            original_id = node.id
            new_id = entity_name if entity_name else original_id

            # 更新节点ID
            node.id = new_id

            # 记录映射
            if original_id != new_id:
                node_id_map[original_id] = new_id

            # 保存实体名称到properties中
            if entity_name and ('name' not in node.properties or not node.properties['name']):
                node.properties['name'] = entity_name

            # 如果是新节点，记录sequence_number
            if new_id not in normalized_nodes:
                global_mention_counter += 1
                normalized_nodes[new_id] = node
                node.properties['sequence_number'] = global_mention_counter
            else:
                # 如果是已存在的节点，更新sequence_number（保留第一次出现的序号）
                existing_node = normalized_nodes[new_id]
                node.properties['sequence_number'] = existing_node.properties.get('sequence_number',
                                                                                  global_mention_counter)

        # 处理关系 - 映射ID
        for rel in serializable_graph_doc.relationships:
            # 映射source_id
            if rel.source_id in node_id_map:
                rel.source_id = node_id_map[rel.source_id]
            # 映射target_id
            if rel.target_id in node_id_map:
                rel.target_id = node_id_map[rel.target_id]

        return global_mention_counter

    @staticmethod
    def _merge_graph_documents(graph_docs: List[Any]) -> SerializableGraphDocument:
        """合并多个 GraphDocument 对象为可序列化的版本。"""
        if not graph_docs:
            return SerializableGraphDocument(nodes=[], relationships=[])

        # 转换为可序列化格式
        serializable_docs = []
        for doc in graph_docs:
            if isinstance(doc, SerializableGraphDocument):
                serializable_docs.append(doc)
            else:
                serializable_docs.append(SerializableGraphDocument.from_langchain_graph_document(doc))

        all_nodes = []
        all_relationships = []

        # 收集所有节点和关系
        for doc in serializable_docs:
            all_nodes.extend(doc.nodes)
            all_relationships.extend(doc.relationships)

        # 节点去重 (通过 ID 和 Type)
        unique_nodes_dict = {}
        for node in all_nodes:
            key = (node.id, node.type)
            if key not in unique_nodes_dict:
                unique_nodes_dict[key] = node

        unique_nodes = list(unique_nodes_dict.values())

        # 关系去重 (通过 source_id, target_id, type)
        unique_relationships_dict = {}
        for rel in all_relationships:
            key = (rel.source_id, rel.target_id, rel.type)
            if key not in unique_relationships_dict:
                unique_relationships_dict[key] = rel

        unique_relationships = list(unique_relationships_dict.values())

        return SerializableGraphDocument(
            nodes=unique_nodes,
            relationships=unique_relationships
        )

    def _calculate_dynamic_threshold(self, node_connections: Dict[str, int],
                                     hub_threshold_percentile: float) -> float:
        """
        根据节点连接度计算动态阈值。

        Args:
            node_connections (Dict[str, int]): 一个字典，键是节点ID，值是该节点的连接数（度数）。
            hub_threshold_percentile (float): 用于确定高连接度节点的百分位数阈值 (0.0 - 1.0)。

        Returns:
            float: 计算出的动态阈值。
        """
        if not node_connections:
            logger.debug("节点连接度字典为空，动态阈值设为0。")
            return 0.0

        # 获取所有节点的度数列表
        all_degrees = list(node_connections.values())

        # 确保百分位数在有效范围内 [0, 1]
        percentile_q = max(0.0, min(1.0, hub_threshold_percentile))

        dynamic_threshold = 0.0
        # 计算动态阈值
        if len(all_degrees) > 1:
            # 对列表排序，然后找对应位置的值
            sorted_degrees = sorted(all_degrees)
            # 计算索引 (0-based)
            index = percentile_q * (len(sorted_degrees) - 1)
            # 简单的线性插值近似
            if index.is_integer():
                dynamic_threshold = float(sorted_degrees[int(index)])
            else:
                lower_index = int(index)
                upper_index = lower_index + 1
                if upper_index < len(sorted_degrees):
                    dynamic_threshold = sorted_degrees[lower_index] + (index - lower_index) * (
                            sorted_degrees[upper_index] - sorted_degrees[lower_index])
                else:
                    dynamic_threshold = float(sorted_degrees[lower_index])  # 边界情况
        else:
            # 只有一个度数，阈值设为该度数
            dynamic_threshold = float(max(all_degrees)) if all_degrees else 0.0

        # 确保阈值至少为1，避免将所有节点都标记为高连接度 (除非所有节点度数都<1，这不太可能)
        # 但考虑到是阈值，我们通常希望它是一个实际的连接数
        dynamic_threshold = max(1.0, dynamic_threshold)
        logger.debug(
            f"使用百分位数法计算动态阈值: Percentile={percentile_q * 100:.1f}%, Threshold (approx)={dynamic_threshold:.2f}"
        )
        return dynamic_threshold



    # ==============================
    # 公共接口方法
    # ==============================

    @classmethod
    def from_config(cls, config: ExtractionConfig) -> 'NarrativeGraphExtractor':
        """从配置创建提取器"""
        logger.info(f"配置对象中的 use_local 值: {config.use_local}")
        logger.info(f"{'将创建本地模型提取器' if config.use_local else '将创建远程模型提取器'}")

        # 判断是否为无约束模式
        is_unrestricted = config.schema_name == "无约束"

        if config.use_local:
            return cls(
                model_name=config.model_name,
                base_url=config.base_url,
                temperature=config.temperature,
                default_num_ctx=config.num_ctx,
                default_chunk_size=config.chunk_size,
                default_chunk_overlap=config.chunk_overlap,
                allowed_nodes=[] if is_unrestricted else config.get_allowed_nodes(),
                allowed_relationships=[] if is_unrestricted else config.get_allowed_relationships(),
                schema_mode="无约束" if is_unrestricted else "约束"
            )
        else:
            return cls(
                remote_api_key=config.remote_api_key,
                remote_base_url=config.remote_base_url,
                remote_model_name=config.remote_model_name,
                temperature=config.temperature,
                default_num_ctx=config.num_ctx,
                default_chunk_size=config.chunk_size,
                default_chunk_overlap=config.chunk_overlap,
                allowed_nodes=[] if is_unrestricted else config.get_allowed_nodes(),
                allowed_relationships=[] if is_unrestricted else config.get_allowed_relationships(),
                schema_mode="无约束" if is_unrestricted else "约束"
            )

    def extract_with_config(self, config: ExtractionConfig) -> Tuple[Any, float, int, List[Any]]:
        """
        使用配置对象进行提取的核心方法
        """
        return self._extract_with_cache_internal(config)

    # ==============================
    # 内部核心方法
    # ==============================
    def _generate_auto_schema(self, text: str, is_local: bool, verbose: bool = True) -> Dict:
        """生成自动schema"""
        if verbose:
            logger.info("正在生成自动schema...")

        # 根据 is_local 参数准备调用 generate_auto_schema 所需的信息
        # 直接使用 self 的属性，这些属性在 from_config 时已根据 is_local 设置
        if is_local:
            model_name_to_use = self.model_name
            # 假设 generate_auto_schema 内部知道如何处理本地模型，
            # 或者我们传递 is_local 让它知道
            base_url_to_use = self.base_url
            api_key_to_use = None  # 本地通常不需要
            logger.debug(f"使用本地模型生成Schema: {model_name_to_use} at {base_url_to_use}")
        else:
            # 确保远程模型配置存在 (在 from_config 时已检查，这里再确认一下)
            if not self.remote_model_name or not self.remote_base_url:
                logger.warning("请求使用远程模型生成Schema，但远程配置不完整。将回退到本地模型。")
                model_name_to_use = self.model_name
                is_local = True  # 回退标志
                base_url_to_use = self.base_url
                api_key_to_use = None
            else:
                model_name_to_use = self.remote_model_name
                # 这些信息传递给 generate_auto_schema，它可能需要
                base_url_to_use = self.remote_base_url
                api_key_to_use = self.remote_api_key
                logger.debug(f"使用远程模型生成Schema: {model_name_to_use} at {base_url_to_use}")

        # 调用 rag.narrative_schema.generate_auto_schema
        # 只传递必要的信息，包括指示本地/远程的 is_local 标志
        # 如果 generate_auto_schema 需要 base_url/api_key，它应该能从 self 的属性推断
        # 或者我们在这里传递，但根据你的要求，我们假设它能处理好
        # 我们传递 is_local 让它知道应该使用哪种配置
        auto_schema = generate_auto_schema(
            text_content=text,
            model_name=model_name_to_use,
            # --- 修改/新增的参数传递 ---
            is_local=is_local,  # 关键：传递 is_local 标志
            # 注意：不再显式传递 base_url 和 api_key，假设 generate_auto_schema 能处理

            use_cache=True
        )

        if verbose:
            logger.info(
                f"自动schema生成完成: {auto_schema['name']} - {len(auto_schema['elements'])}元素, {len(auto_schema['relationships'])}关系")

        return auto_schema

    from typing import Optional, Tuple, Any, List
    # ... 其他导入 ...

    def _extract_main(self, config: ExtractionConfig) -> Tuple[Any, float, int, List[Any]]:
        """
        执行完整的提取流程：缓存处理 -> Schema 逻辑 -> 核心提取 -> 后处理 -> 缓存保存。

        Args:
            config (ExtractionConfig): 提取配置对象。

        Returns:
            Tuple[Any, float, int, List[Any]]:
                - 提取结果 (SerializableGraphDocument 或类似对象)
                - 总耗时 (秒)
                - 状态码 (0=全部成功, 1=部分成功, 2=全部失败)
                - 所有块的结果列表
        """
        start_time = time.time()
        # 1. 生成缓存键 (修复：在此处生成)
        cache_key = get_cache_key_from_config(config)

        # 1. 尝试从缓存加载
        cached_result_tuple = self._load_from_cache(config)
        if cached_result_tuple is not None:
            return cached_result_tuple

        # 2. 未命中缓存，准备执行提取
        if config.verbose:
            logger.info(
                f"开始提取流程 (num_ctx={config.num_ctx}, chunk_size={config.chunk_size}, local={config.use_local})")
        token_estimate = self.estimate_tokens(config.text)
        if config.verbose:
            logger.info(f"输入文本估算 Token 数: ~{token_estimate}")

        # 3. 保存原始 Schema 用于恢复
        original_allowed_nodes = self.allowed_nodes
        original_allowed_relationships = self.allowed_relationships

        final_result = None
        status = 2  # 默认全部失败
        all_chunk_results = []
        total_duration_core = 0.0

        try:
            # 4. 根据 Schema 名称处理 Schema 和执行提取
            #    这个函数将负责 Schema 生成、拆分、应用、核心提取、子结果合并
            extraction_result = self._handle_schema_and_extract(config)
            if extraction_result:
                final_result = extraction_result.get('final_result')
                total_duration_core = extraction_result.get('total_duration_core', 0.0)
                status = extraction_result.get('status', 2)
                all_chunk_results = extraction_result.get('all_chunk_results', [])
                # all_extraction_results 如果需要可以在 extraction_result 中传递，或内部处理

            # 5. 对最终结果进行全局优化 (这一步独立于 Schema 处理)
            final_result = self._post_process_result(final_result, config)

            # 6. 计算总耗时
            end_time = time.time()
            total_duration = end_time - start_time

            # 7. 保存缓存
            self._save_result_to_cache(final_result, config, start_time, cache_key)  # cache_key 需要从 config 生成

            # 8. 记录日志
            self._log_extraction_summary(final_result, total_duration, total_duration_core, status, config)

            return final_result, total_duration, status, all_chunk_results

        except Exception as e:
            logger.error(f"提取过程中发生错误: {e}", exc_info=True)
            return None, time.time() - start_time, 2, []
        finally:
            # 9. 确保在任何情况下都恢复原始 Schema
            self._restore_schema(original_allowed_nodes, original_allowed_relationships)

    # ==============================
    # 重构后的缓存加载相关方法 (简化日志)
    # ==============================

    def _process_loaded_cache_data(self, loaded_data: Any, verbose: bool = False, log_context: str = "") -> Optional[
        SerializableGraphDocument]:
        """
        处理已从缓存加载的原始数据，执行类型检查、转换（如果需要）和添加缓存标记。
        """
        try:
            if loaded_data is None:
                return None

            processed_data = loaded_data

            # 1. 如果缓存的是字典格式，转换回对象
            if isinstance(processed_data, dict):
                if verbose:
                    logger.debug(f"正在转换字典格式缓存数据 {log_context}...")
                processed_data = SerializableGraphDocument.from_dict(processed_data)

            # 2. 添加缓存标记
            if isinstance(processed_data, SerializableGraphDocument):
                try:
                    processed_data._is_from_cache = True
                    if verbose:
                        logger.debug(f"已为缓存对象添加 _is_from_cache 标记 {log_context}。")
                except Exception as e:
                    logger.warning(f"无法为缓存对象添加 _is_from_cache 标记 {log_context}: {e}")

                return processed_data
            else:
                logger.warning(f"缓存结果类型不匹配 ({type(processed_data)}) {log_context}。")
                return None

        except Exception as e:
            logger.error(f"处理缓存数据时发生错误 {log_context}: {e}", exc_info=True)
            return None

    def load_from_cache_by_hash(self, cache_hash: str, verbose: bool = True) -> Optional[SerializableGraphDocument]:
        """
        根据给定的 `cache_hash` 直接加载并处理缓存，返回 `SerializableGraphDocument` 对象或 `None`。
        """
        start_time = time.time()
        log_context = f"(Hash: {cache_hash})"

        try:
            # 1. 尝试加载缓存数据
            cached_result_raw = load_cache(cache_hash)

            # 2. 检查是否命中缓存
            if cached_result_raw is None:
                if verbose:
                    logger.info(f"缓存未命中 {log_context}")
                return None

            if verbose:
                logger.info(f"命中缓存 {log_context}")

            # 3. 调用核心处理函数
            processed_result = self._process_loaded_cache_data(cached_result_raw, verbose, log_context)

            # 4. 计算耗时并返回结果
            if processed_result is not None and verbose:
                duration = time.time() - start_time
                logger.debug(f"缓存加载与处理耗时: {duration:.4f} 秒 {log_context}")
            # 如果处理失败，_process_loaded_cache_data 会记录警告或错误日志

            return processed_result

        except Exception as e:  # 捕获 load_cache 或其他操作可能抛出的意外错误
            logger.error(f"尝试从缓存加载时发生未预期错误 {log_context}: {e}", exc_info=True)
            return None

    def _load_from_cache(self, config: ExtractionConfig) -> Optional[Tuple[Any, float, int, List[Any]]]:
        """
        根据 `ExtractionConfig` 生成缓存键，加载缓存，处理数据，并返回格式化的结果元组或 `None`。
        """
        # 1. 检查是否启用缓存
        if not config.use_cache:
            return None

        start_time = time.time()
        # 2. 生成缓存键
        cache_key = get_cache_key_from_config(config)
        log_context = f"(Key: {cache_key})"

        try:
            # 3. 尝试加载缓存
            cached_data_raw = load_cache(cache_key)

            # 4. 检查是否命中缓存
            if cached_data_raw is None:
                if config.verbose:
                    logger.debug(f"缓存未命中 {log_context}")
                return None

            if config.verbose:
                logger.info(f"命中缓存 {log_context}")

            # 5. 调用核心处理函数
            processed_data = self._process_loaded_cache_data(cached_data_raw, config.verbose, log_context)

            # 6. 检查处理结果并返回
            if processed_data is not None:
                duration = time.time() - start_time
                # 返回格式需与 _extract_main 成功时一致
                return processed_data, duration, 0, []
            else:
                # 处理失败（类型不匹配、转换异常等）在 _process_loaded_cache_data 内已记录日志
                if config.verbose:
                    logger.info(f"缓存命中但处理失败 {log_context}")
                return None

        except Exception as e:
            logger.error(f"加载或处理缓存数据时出错 {log_context}: {e}")
            return None

    def _handle_schema_and_extract(self, config: ExtractionConfig) -> Optional[Dict[str, Any]]:
        """
        根据 config.schema_name 处理 Schema 逻辑并执行核心提取。

        Returns:
            Optional[Dict]: 包含提取结果信息的字典，或 None (如果出错)。
                {
                    'final_result': SerializableGraphDocument,
                    'total_duration_core': float,
                    'status': int,
                    'all_chunk_results': List[Any]
                }
        """
        if config.schema_name == "自动生成":
            return self._handle_auto_schema_extraction(config)
        else:  # 使用预定义的 Schema
            return self._handle_predefined_schema_extraction(config)

    def _handle_sub_schema_result(self, sub_result: Any, config: ExtractionConfig, sub_schema_index: int) -> Any:
        """
        对单个子 Schema 的提取结果进行后处理，例如优化。

        Args:
            sub_result (Any): 子 Schema 的提取结果 (通常是 SerializableGraphDocument)。
            config (ExtractionConfig): 提取配置对象。
            sub_schema_index (int): 子 Schema 的索引 (从 0 开始)。

        Returns:
            Any: 优化后的结果，如果优化未执行或失败，则返回原始结果。
        """
        # --- 修复之前的错误：使用 config.schema_name ---
        # 注意：在这个上下文中，即使 config.schema_name 是 "自动生成"，
        # 我们处理的 sub_schema 本身已经是拆分后的，且其 schema_mode 应该是 "约束" 的。
        # 所以优化逻辑的判断依据是 config.optimize_graph 和结果类型。

        # 检查是否需要优化以及结果是否为可处理的类型
        if config.optimize_graph and isinstance(sub_result, SerializableGraphDocument):
            if config.verbose:
                logger.info(f" -> 对子 Schema {sub_schema_index + 1} 的提取结果进行优化...")
            try:
                # --- 实例化并调用 GraphOptimizer ---
                # 传入当前 extractor 实例，以便 optimizer 可以访问模型等配置
                optimizer = GraphOptimizer()
                optimized_sub_result = optimizer.optimize_graph_document(sub_result)

                if optimized_sub_result:
                    # 如果优化成功返回了新对象，则使用它
                    if config.verbose:
                        opt_nodes = len(optimized_sub_result.nodes)
                        opt_rels = len(optimized_sub_result.relationships)
                        logger.info(
                            f" -> 子 Schema {sub_schema_index + 1} 优化完成。优化后节点数: {opt_nodes}, 关系数: {opt_rels}")
                    return optimized_sub_result
                else:
                    # 如果优化返回 None 或等效值，记录日志并返回原始结果
                    if config.verbose:
                        logger.info(f" -> 子 Schema {sub_schema_index + 1} 优化完成，但未返回新结果或无优化。")
                    return sub_result  # 返回原始结果

            except Exception as e:
                # 捕获优化过程中可能出现的任何异常
                logger.error(f" -> 优化子 Schema {sub_schema_index + 1} 的结果时出错: {e}", exc_info=True)
                # 即使优化失败，也返回原始结果以保证流程继续
                return sub_result
        else:
            # 如果未启用优化或结果类型不匹配，则直接返回原始结果
            return sub_result
    def _handle_auto_schema_extraction(self, config: ExtractionConfig) -> Optional[Dict[str, Any]]:
        """处理自动生成 Schema 的提取流程，包括可能的拆分和合并。"""
        # 保存原始 Schema 用于此分支内的恢复
        branch_original_nodes = self.allowed_nodes
        branch_original_rels = self.allowed_relationships

        try:
            auto_schema = self._generate_auto_schema(config.text, config.use_local, config.verbose)
            num_relationships = len(auto_schema.get("relationships", []))

            if num_relationships > self.SCHEMA_SPLIT_THRESHOLD_RELATIONSHIPS and config.schema_name != "无约束":
                # --- 需要拆分处理 ---
                if config.verbose:
                    logger.info(
                        f" -> 自动Schema包含 {num_relationships} 个关系，超过阈值 {self.SCHEMA_SPLIT_THRESHOLD_RELATIONSHIPS}，将进行拆分处理。")
                sub_schemas = split_schema(auto_schema, self.SCHEMA_SPLIT_THRESHOLD_RELATIONSHIPS)
                if config.verbose:
                    logger.info(f" -> Schema 已拆分为 {len(sub_schemas)} 个子 Schema。")
                    logger.info(f" -> Schema: {sub_schemas}")
                all_sub_results = []
                total_duration_core = 0.0
                status = 2  # 默认全部失败

                for i, sub_schema in enumerate(sub_schemas):
                    if config.verbose:
                        logger.info(f" -> 处理子 Schema {i + 1}/{len(sub_schemas)}: {sub_schema['name']}")
                    self.allowed_nodes = sub_schema["elements"]
                    self.allowed_relationships = sub_schema["relationships"]

                    sub_result, sub_duration, sub_status, sub_chunks = self._extract_internal_core_logic(
                        config, is_sub_extraction=True)

                    sub_result = self._handle_sub_schema_result(sub_result, config, i)

                    total_duration_core += sub_duration
                    if sub_status < status:
                        status = sub_status
                    all_sub_results.append(sub_result)

                if config.verbose:
                    logger.info(f" -> 所有子 Schema 处理完成。")
                    logger.info(f" -> 正在合并 {len(all_sub_results)} 个子 Schema 的提取结果...")
                final_result = self._merge_graph_documents(all_sub_results)
                # 注意：优化移到 _post_process_result

                return {
                    'final_result': final_result,
                    'total_duration_core': total_duration_core,
                    'status': status,
                    'all_chunk_results': []  # 合并后通常不保留子块结果
                }

            else:
                # --- 不需要拆分，直接处理 ---
                if config.verbose:
                    logger.info(
                        f" -> 自动Schema包含 {num_relationships} 个关系，未超过阈值 {self.SCHEMA_SPLIT_THRESHOLD_RELATIONSHIPS}，直接使用。")
                self.allowed_nodes = auto_schema["elements"]
                self.allowed_relationships = auto_schema["relationships"]

                final_result, total_duration_core, status, all_chunk_results = self._extract_internal_core_logic(
                    config, is_sub_extraction=False)
                # 注意：优化移到 _post_process_result

                return {
                    'final_result': final_result,
                    'total_duration_core': total_duration_core,
                    'status': status,
                    'all_chunk_results': all_chunk_results
                }

        finally:
            # 恢复此分支开始前的 Schema
            self.allowed_nodes = branch_original_nodes
            self.allowed_relationships = branch_original_rels

    def _handle_predefined_schema_extraction(self, config: ExtractionConfig) -> Optional[Dict[str, Any]]:
        """处理预定义 Schema 的提取流程。"""
        # 注意：Schema 的设置（self.allowed_nodes, self.allowed_relationships）
        # 应该在 from_config 或 __init__ 时已经根据 config.schema_mode 和 config.schema_name 完成
        # 这里直接执行核心提取
        final_result, total_duration_core, status, all_chunk_results = self._extract_internal_core_logic(
            config, is_sub_extraction=False)
        # 注意：优化移到 _post_process_result

        return {
            'final_result': final_result,
            'total_duration_core': total_duration_core,
            'status': status,
            'all_chunk_results': all_chunk_results
        }

    def _post_process_result(self, result: Any, config: ExtractionConfig) -> Any:
        """对提取结果进行后处理，例如全局优化。"""
        if config.optimize_graph and isinstance(result, SerializableGraphDocument):
            if config.verbose:
                logger.info(" -> 正在对提取的图谱进行全局优化...")

                # --- 使用新的 GraphOptimizer 类 ---
                optimizer = GraphOptimizer()  # 将当前 extractor 实例传给 optimizer
                optimized_result = optimizer.optimize_graph_document(result)
                # --- 优化结束 ---

            if config.verbose:
                final_nodes_count_opt = len(optimized_result.nodes) if optimized_result else 0
                final_relationships_count_opt = len(optimized_result.relationships) if optimized_result else 0
                logger.info(
                    f" -> 全局优化完成。节点数: {final_nodes_count_opt}, 关系数: {final_relationships_count_opt}")
            return optimized_result
        return result

    def _save_result_to_cache(self, result: Any, config: ExtractionConfig, start_time: float, cache_key: str):
        """保存提取结果到缓存。"""
        # 注意：cache_key 应该在 _extract_main 开头或这里生成
        # cache_key = get_cache_key_from_config(config) # 如果不在 _extract_main 生成
        if config.use_cache and result is not None:
            cache_data = result
            if isinstance(result, SerializableGraphDocument):
                cache_data = result.to_dict()
            # 生成元数据
            metadata = generate_cache_metadata(**config.to_metadata_params())
            save_cache(cache_key, cache_data, metadata)
            if config.verbose:
                logger.info(f"结果已缓存: {config.novel_name} - {config.chapter_name} ({cache_key}.json)")

    def _log_extraction_summary(self, result: Any, total_duration: float, core_duration: float, status: int,
                                config: ExtractionConfig):
        """记录提取过程的摘要日志。"""
        if config.verbose:
            final_nodes_count = len(result.nodes) if result and hasattr(result, 'nodes') else 0
            final_relationships_count = len(result.relationships) if result and hasattr(result, 'relationships') else 0
            logger.info(f" -> 提取流程完成。"
                        f"最终节点数: {final_nodes_count}, 最终关系数: {final_relationships_count}。"
                        f"总耗时: {total_duration:.2f} 秒 (核心耗时: {core_duration:.2f} 秒)")

    def _restore_schema(self, original_nodes: List, original_rels: List):
        """恢复原始 Schema。"""
        self.allowed_nodes = original_nodes
        self.allowed_relationships = original_rels

    def _extract_internal_core_logic(self, config: ExtractionConfig, is_sub_extraction: bool = False) -> Tuple[
        Any, float, int, List[Any]]:
        """
        核心提取逻辑：分割 -> 处理 -> 合并。

        Args:
            config (ExtractionConfig): 提取配置对象。
            is_sub_extraction (bool): 是否为子 Schema 提取。

        Returns:
            Tuple[Any, float, int, List[Any]]: 提取结果、核心耗时、状态、块结果列表。
        """
        start_time_core = time.time()
        # total_nodes = 0  # 这些计数器可能在其他地方有用，但在此简化
        # total_relationships = 0

        # 1. 分割文本
        split_docs = self._split_text(config.text, config.chunk_size, config.chunk_overlap)

        # 2. 初始化 GraphTransformer
        graph_transformer = self._create_graph_transformer(
            config)  # 注意：这里可能需要重构 _create_graph_transformer 以减少 config 依赖

        # 3. 处理每个块并记录顺序
        all_chunk_results = []
        successful_chunks = 0
        # global_mention_counter = 0 # 如果需要全局计数
        # node_id_map = {} # 如果需要节点映射
        # normalized_nodes = {} # 如果需要节点标准化

        for i, doc_chunk in enumerate(split_docs):
            single_doc = Document(page_content=doc_chunk.page_content)
            try:
                # graph_document = self._process_single_chunk(single_doc, config) # 如果 _process_single_chunk 也被重构
                # 原有逻辑:
                graph_document = graph_transformer.convert_to_graph_documents([single_doc])[0]
                # ... (后续处理逻辑，如节点合并等，如果在 _process_single_chunk 外部) ...
                all_chunk_results.append(graph_document)
                successful_chunks += 1
                # ... (更新计数器等) ...
            except Exception as e:
                logger.error(f"处理块 {i + 1}/{len(split_docs)} 时出错: {e}")
                # 可以选择跳过错误块或添加空结果
                all_chunk_results.append(SerializableGraphDocument(nodes=[], relationships=[]))

        # 4. 合并结果
        final_result = None
        if config.merge_results and all_chunk_results:
            if config.verbose:
                logger.info(f" -> 正在合并 {len(all_chunk_results)} 个块的结果...")
            final_result = self._merge_graph_documents(all_chunk_results)  # <- 在这里合并

            # 注意：全局优化已移至 _extract_main 中

            final_nodes_count = len(final_result.nodes) if final_result else 0
            final_relationships_count = len(final_result.relationships) if final_result else 0
            if config.verbose:
                logger.info(f" -> 合并完成。最终节点数: {final_nodes_count}, 最终关系数: {final_relationships_count}")
        else:
            # ... (处理未合并的情况) ...
            final_result = all_chunk_results[0] if all_chunk_results else SerializableGraphDocument(nodes=[],
                                                                                                    relationships=[])

            # 注意：全局优化已移至 _extract_main 中

            final_nodes_count = len(final_result.nodes)
            final_relationships_count = len(final_result.relationships)
            if config.verbose:
                logger.info(
                    f" -> 未启用合并或无结果。最终节点数: {final_nodes_count}, 最终关系数: {final_relationships_count}")

        end_time_core = time.time()
        total_duration_core = end_time_core - start_time_core

        # status: 0=全部成功, 1=部分成功, 2=全部失败
        status = 0 if successful_chunks == len(split_docs) else (1 if successful_chunks > 0 else 2)
        if config.verbose and not is_sub_extraction:  # 避免子提取时重复打印
            logger.info(f" -> 所有块处理完成! "
                        f"成功处理 {successful_chunks}/{len(split_docs)} 个块。")
            # f"总计节点数: {total_nodes}, 总计关系数: {total_relationships}。") # 如果需要总计数

        return final_result, total_duration_core, status, all_chunk_results

        # ==============================
        # 简化后的公共接口方法
        # ==============================

    def extract(
            self,
            text: str,
            novel_name: str = "",  # 默认空字符串，兼容旧用法
            chapter_name: str = "",  # 默认空字符串，兼容旧用法
            num_ctx: Optional[int] = None,
            chunk_size: Optional[int] = None,
            chunk_overlap: Optional[int] = None,
            merge_results: bool = True,  # 使用默认值常量
            verbose: bool = True,  # 使用默认值常量
            local: bool = True,  # 注意：extract 原来叫 'local', config 里叫 'use_local'
            schema_name: str = "极简",
            use_cache: bool = False,  # 使用默认值常量
            optimize_graph: bool = False,  # 使用默认值常量 (如果有的话)
            # 可以添加更多 config 中的参数...
    ) -> Tuple[Any, float, int, List[Any]]:
        """
        执行完整的提取流程：分割 -> 处理 -> 合并 (统一接口)。

        Args:
            text (str): 要提取的文本。
            novel_name (str, optional): 小说名称（用于缓存）。默认 ""。
            chapter_name (str, optional): 章节名称（用于缓存）。默认 ""。
            num_ctx (int, optional): 上下文长度。默认 None (使用实例默认值)。
            chunk_size (int, optional): 文本块大小。默认 None (使用实例默认值)。
            chunk_overlap (int, optional): 文本块重叠。默认 None (使用实例默认值)。
            merge_results (bool, optional): 是否合并结果。默认 True。
            verbose (bool, optional): 是否打印详细日志。默认 True。
            local (bool, optional): 是否使用本地模型。默认 True。
            schema_name (str, optional): 使用的 Schema 名称。默认 "基础"。
            use_cache (bool, optional): 是否使用缓存。默认 True。
            optimize_graph (bool, optional): 是否优化图结构。默认 True (或根据配置)。

        Returns:
            Tuple[Any, float, int, List[Any]]: 提取结果、总耗时、状态、块结果列表。
        """
        # 创建配置对象，将所有参数传递进去
        config = ExtractionConfig(
            novel_name=novel_name,
            chapter_name=chapter_name,
            text=text,
            model_name=self.model_name,
            base_url=self.base_url,
            temperature=self.temperature,
            num_ctx=num_ctx or self.default_num_ctx,
            use_local=local,  # 注意参数名映射
            remote_api_key=self.remote_api_key,
            remote_base_url=self.remote_base_url,
            remote_model_name=self.remote_model_name,
            chunk_size=chunk_size or self.default_chunk_size,
            chunk_overlap=chunk_overlap or self.default_chunk_overlap,
            merge_results=merge_results,
            verbose=verbose,
            schema_name=schema_name,
            use_cache=use_cache,
            optimize_graph=optimize_graph,
            # allowed_nodes 和 allowed_relationships 通常由 schema_name 决定，这里不直接传
        )
        # 调用新的统一主入口
        return self._extract_main(config)

        # 如果需要保持 `extract_with_cache` 的名字作为别名，可以这样做：
        # extract_with_cache = extract # 简单别名，因为 extract 现在已经包含了缓存逻辑

        # 如果需要保持 `extract_with_config` 的名字，也可以这样做：

    def extract_with_config(self, config: ExtractionConfig) -> Tuple[Any, float, int, List[Any]]:
        """使用配置对象进行提取的核心方法 (别名)"""
        return self._extract_main(config)

