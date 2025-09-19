# inputs/rag/narrative_graph_extractor.py
import hashlib
import logging
import os
import time
import math
from typing import List, Tuple, Any, Optional, Dict
from dataclasses import dataclass

# --- 导入所需模块 ---
from langchain_openai import ChatOpenAI
from langchain_ollama import OllamaLLM
from langchain_experimental.graph_transformers import LLMGraphTransformer
from langchain_core.documents import Document
from langchain.text_splitter import RecursiveCharacterTextSplitter
from litellm import max_tokens

# --- 导入共享配置 ---
# 从共享配置文件导入默认值
from rag.config import (
    DEFAULT_MODEL as CONFIG_DEFAULT_MODEL,
    DEFAULT_BASE_URL as CONFIG_DEFAULT_BASE_URL,
    DEFAULT_TEMPERATURE as CONFIG_DEFAULT_TEMPERATURE,
    DEFAULT_NUM_CTX as CONFIG_DEFAULT_NUM_CTX,
    DEFAULT_CHUNK_SIZE as CONFIG_DEFAULT_CHUNK_SIZE,
    DEFAULT_CHUNK_OVERLAP as CONFIG_DEFAULT_CHUNK_OVERLAP,
)

from rag.config_models import ExtractionConfig
from rag.narrative_schema import MINIMAL_SCHEMA, generate_auto_schema
from rag.cache_manager import get_cache_key, save_cache, load_cache, generate_extractor_cache_params, \
    generate_cache_metadata, get_cache_key_from_config

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




# --- End Schema 拆分配置 ---

# ==============================
# 可序列化的 Graph Document 类
# ==============================

@dataclass
class SerializableNode:
    id: str
    type: str
    properties: Dict[str, Any]

    @classmethod
    def from_langchain_node(cls, node):
        """从 LangChain 节点创建可序列化节点"""
        return cls(
            id=getattr(node, 'id', ''),
            type=getattr(node, 'type', ''),
            properties=getattr(node, 'properties', {})
        )

    def to_dict(self):
        return {
            'id': self.id,
            'type': self.type,
            'properties': self.properties
        }

    @classmethod
    def from_dict(cls, data):
        return cls(
            id=data['id'],
            type=data['type'],
            properties=data['properties']
        )


@dataclass
class SerializableRelationship:
    source_id: str
    target_id: str
    type: str
    properties: Dict[str, Any]

    @classmethod
    def from_langchain_relationship(cls, rel):
        """从 LangChain 关系创建可序列化关系"""
        source = getattr(rel, 'source', None)
        target = getattr(rel, 'target', None)
        return cls(
            source_id=getattr(source, 'id', '') if source else '',
            target_id=getattr(target, 'id', '') if target else '',
            type=getattr(rel, 'type', ''),
            properties=getattr(rel, 'properties', {})
        )

    def to_dict(self):
        return {
            'source_id': self.source_id,
            'target_id': self.target_id,
            'type': self.type,
            'properties': self.properties
        }

    @classmethod
    def from_dict(cls, data):
        return cls(
            source_id=data['source_id'],
            target_id=data['target_id'],
            type=data['type'],
            properties=data['properties']
        )


@dataclass
class SerializableGraphDocument:
    nodes: List[SerializableNode]
    relationships: List[SerializableRelationship]

    @classmethod
    def from_langchain_graph_document(cls, graph_doc):
        """从 LangChain GraphDocument 创建可序列化版本"""
        nodes = [SerializableNode.from_langchain_node(n) for n in getattr(graph_doc, 'nodes', [])]
        relationships = [SerializableRelationship.from_langchain_relationship(r) for r in
                         getattr(graph_doc, 'relationships', [])]
        return cls(nodes=nodes, relationships=relationships)

    def to_dict(self):
        return {
            'nodes': [node.to_dict() for node in self.nodes],
            'relationships': [rel.to_dict() for rel in self.relationships]
        }

    @classmethod
    def from_dict(cls, data):
        nodes = [SerializableNode.from_dict(node_data) for node_data in data['nodes']]
        relationships = [SerializableRelationship.from_dict(rel_data) for rel_data in data['relationships']]
        return cls(nodes=nodes, relationships=relationships)

    @staticmethod
    def display_graph_document(graph_doc, title: str = "Graph Document"):
        """打印 GraphDocument 的内容"""
        print(f"\n=== {title} ===")
        print(f"节点数量: {len(graph_doc.nodes)}")
        print(f"关系数量: {len(graph_doc.relationships)}")
        print("--- 节点 (Nodes) ---")
        for i, node in enumerate(graph_doc.nodes):
            print(f"  {i + 1}. ID: '{node.id}', Type: '{node.type}', Properties: {node.properties}")
        print("--- 关系 (Relationships) ---")
        for i, rel in enumerate(graph_doc.relationships):
            print(f"  {i + 1}. '{rel.source_id}' --({rel.type})--> '{rel.target_id}' | Properties: {rel.properties}")
        print("-" * 20)


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

    # ==============================
    # 公共接口方法
    # ==============================

    def extract(
            self,
            text: str,
            num_ctx: Optional[int] = None,
            chunk_size: Optional[int] = None,
            chunk_overlap: Optional[int] = None,
            merge_results: bool = True,
            verbose: bool = True,
            local: bool = True
    ) -> Tuple[Any, float, int, List[Any]]:
        """
        执行完整的提取流程：分割 -> 处理 -> 合并。
        """
        # 创建临时配置对象
        config = ExtractionConfig(
            novel_name="",  # 临时值
            chapter_name="",  # 临时值
            text=text,
            num_ctx=num_ctx or self.default_num_ctx,
            chunk_size=chunk_size or self.default_chunk_size,
            chunk_overlap=chunk_overlap or self.default_chunk_overlap,
            merge_results=merge_results,
            verbose=verbose,
            use_local=local
        )

        return self._extract_internal(config)

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
    def _split_schema(self, schema: Dict, verbose: bool = True) -> List[Dict]:
        """
        将一个复杂的 Schema 拆分成多个子 Schema。
        策略：保持所有节点类型(elements)不变，将关系类型(relationships)按组拆分。
        这样可以保证每次提取都覆盖所有节点类型，但只关注部分关系，避免关系过多导致的混乱。
        """
        elements = schema.get("elements", [])
        relationships = schema.get("relationships", [])
        schema_name = schema.get("name", "未知Schema")
        schema_description = schema.get("description", "")

        if not relationships:
            if verbose:
                logger.warning(f"    Schema '{schema_name}' 没有定义关系类型，无需拆分。")
            return [schema]  # 如果没有关系，直接返回原schema

        # --- 修改：只根据关系数量来决定拆分 ---
        rels_per_sub = self.SCHEMA_SPLIT_THRESHOLD_RELATIONSHIPS  # 例如 5
        num_sub_schemas = math.ceil(len(relationships) / rels_per_sub)

        if num_sub_schemas <= 1:
            if verbose:
                logger.debug(
                    f"    Schema '{schema_name}' 关系数 ({len(relationships)}) 未超过阈值 ({rels_per_sub})，无需拆分。")
            return [schema]  # 如果关系数没超过阈值，也不拆分

        if verbose:
            logger.info(
                f"    Schema '{schema_name}' 关系数 ({len(relationships)}) 超过阈值 ({rels_per_sub})，将拆分为 {num_sub_schemas} 个子 Schema (固定节点，拆分关系)。")

        sub_schemas = []

        # --- 修改：保持 elements 不变，只拆分 relationships ---
        for i in range(num_sub_schemas):
            start_rel_idx = i * rels_per_sub
            end_rel_idx = min((i + 1) * rels_per_sub, len(relationships))

            # 核心修改点：所有子 Schema 共享相同的 elements
            sub_elements = elements  # <--- 保持不变
            # 只拆分 relationships
            sub_relationships = relationships[start_rel_idx:end_rel_idx]

            sub_schema = {
                "name": f"{schema_name}_关系组_{i + 1}",
                "description": f"{schema_description} - 关系组 {i + 1}/{num_sub_schemas}: {', '.join(sub_relationships)}",
                "elements": sub_elements,  # <--- 所有节点类型
                "relationships": sub_relationships  # <--- 当前组的关系类型
            }
            sub_schemas.append(sub_schema)

            if verbose:
                logger.debug(
                    f"      子 Schema {i + 1}: {len(sub_elements)} 个节点类型, {len(sub_relationships)} 个关系类型")

        # --- 修改结束 ---
        return sub_schemas
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

    def _extract_internal(self, config: ExtractionConfig) -> Tuple[Any, float, int, List[Any]]:
        """内部提取方法，使用配置对象"""
        if config.verbose:
            logger.info(
                f"开始提取流程 (num_ctx={config.num_ctx}, chunk_size={config.chunk_size}, local={config.use_local})")
            token_estimate = self.estimate_tokens(config.text)
            logger.info(f"输入文本估算 Token 数: ~{token_estimate}")

        start_time = time.time()
        total_nodes = 0
        total_relationships = 0

        # --- 新增：用于存储可能拆分的子 Schema 提取结果 ---
        all_extraction_results = []
        # --- 新增结束 ---

        # 如果schema_name是"自动生成"，则生成自动schema
        if config.schema_name == "自动生成":
            auto_schema = self._generate_auto_schema(config.text, config.use_local, config.verbose)

            # --- 提前定义原始 Schema 变量 ---
            original_allowed_nodes = self.allowed_nodes
            original_allowed_relationships = self.allowed_relationships
            # --- 定义结束 ---

            # --- 修改：只根据关系数量决定是否拆分 ---
            num_relationships = len(auto_schema.get("relationships", []))

            if (num_relationships > self.SCHEMA_SPLIT_THRESHOLD_RELATIONSHIPS):  # 只保留关系数量的判断

                if config.verbose:
                    logger.info(f"检测到复杂 Schema (关系数: {num_relationships})，将进行拆分处理...")

                # 拆分 Schema
                sub_schemas = self._split_schema(auto_schema, config.verbose)

                # 针对每个子 Schema 执行提取
                for i, sub_schema in enumerate(sub_schemas):
                    if config.verbose:
                        logger.info(f"  -> 处理子 Schema {i + 1}/{len(sub_schemas)}: {sub_schema['name']}")

                    # 注意：不再需要保存原始值，因为我们已经在外面保存了
                    # 设置当前子 Schema
                    self.allowed_nodes = sub_schema["elements"]
                    self.allowed_relationships = sub_schema["relationships"]

                    # 执行提取
                    sub_result, sub_duration, sub_status, sub_chunks = self._extract_internal_core(config,
                                                                                                   is_sub_extraction=True)

                    all_extraction_results.append(sub_result)




                if config.verbose:
                    logger.info(f"  -> 所有子 Schema 处理完成。")

                # --- 合并所有子 Schema 的结果 ---
                if config.verbose:
                    logger.info(f"  -> 正在合并 {len(all_extraction_results)} 个子 Schema 的提取结果...")

                merged_final_result = self._merge_graph_documents(all_extraction_results)

                end_time = time.time()
                total_duration = end_time - start_time
                status = 0  # 简化处理

                if config.verbose:
                    final_nodes_count = len(merged_final_result.nodes) if merged_final_result else 0
                    final_relationships_count = len(merged_final_result.relationships) if merged_final_result else 0
                    logger.info(
                        f"  -> 所有子 Schema 结果合并完成。"
                        f"最终节点数: {final_nodes_count}, 最终关系数: {final_relationships_count}。"
                        f"总耗时: {total_duration:.2f} 秒"
                    )

                # --- 关键修改：在拆分逻辑分支返回前，恢复原始 Schema ---
                self.allowed_nodes = original_allowed_nodes
                self.allowed_relationships = original_allowed_relationships
                # --- 恢复结束 ---

                return merged_final_result, total_duration, status, []  # chunks 信息在拆分处理中丢失

            else:
                # Schema 不复杂，按正常流程处理
                # --- 计算 num_elements 用于日志 ---
                num_elements = len(auto_schema.get("elements", []))
                # ---
                if config.verbose:
                    logger.info(f"Schema 复杂度适中 (元素: {num_elements}, 关系: {num_relationships})，按正常流程处理。")

                # 设置自动schema
                self.allowed_nodes = auto_schema["elements"]
                self.allowed_relationships = auto_schema["relationships"]
                if config.verbose:
                    logger.info(f"使用自动生成的schema: {auto_schema['name']}")

                # 执行核心提取流程
                final_result, total_duration, status, all_chunk_results = self._extract_internal_core(config)

                # --- 关键修改：在正常流程分支返回前，恢复原始 Schema ---
                # (这部分代码原本就在，现在逻辑更清晰)
                self.allowed_nodes = original_allowed_nodes
                self.allowed_relationships = original_allowed_relationships
                # --- 恢复结束 ---

                return final_result, total_duration, status, all_chunk_results

        else:  # config.schema_name != "自动生成"
            auto_schema = None

            # 执行核心提取流程
            final_result, total_duration, status, all_chunk_results = self._extract_internal_core(config)
            return final_result, total_duration, status, all_chunk_results

    # --- 新增：核心提取逻辑，不包含 Schema 自动生成和拆分 ---
    def _extract_internal_core(self, config: ExtractionConfig, is_sub_extraction: bool = False) -> Tuple[
        Any, float, int, List[Any]]:
        """
        核心提取逻辑，不包含 Schema 自动生成和拆分处理。
        """
        start_time_core = time.time()
        total_nodes = 0
        total_relationships = 0

        # 1. 分割文本
        split_docs = self._split_text(config.text, config.chunk_size, config.chunk_overlap)

        # 2. 初始化 GraphTransformer
        graph_transformer = self._create_graph_transformer(config)

        # 3. 处理每个块并记录顺序
        all_chunk_results = []
        successful_chunks = 0
        global_mention_counter = 0
        node_id_map = {}
        normalized_nodes = {}

        # --- 修改：使用新的 _process_single_chunk 方法 ---
        for i, doc_chunk in enumerate(split_docs):
            single_doc = Document(page_content=doc_chunk.page_content)

            # 调用新的处理函数
            processed_doc, chunk_nodes, chunk_rels, global_mention_counter = self._process_single_chunk(
                chunk_index=i,
                total_chunks=len(split_docs),
                single_doc=single_doc,
                graph_transformer=graph_transformer,
                node_id_map=node_id_map,
                normalized_nodes=normalized_nodes,
                global_mention_counter=global_mention_counter,
                verbose=config.verbose
            )

            # 处理结果
            if processed_doc is not None:
                all_chunk_results.append(processed_doc)
                successful_chunks += 1
                total_nodes += chunk_nodes
                total_relationships += chunk_rels
            else:
                # 即使失败，也添加一个空的占位符，保持索引一致性（如果需要）
                # 或者不添加，取决于 _merge_graph_documents 的健壮性
                # 这里选择添加空的，与原逻辑一致
                all_chunk_results.append(SerializableGraphDocument(nodes=[], relationships=[]))
        # --- 修改结束 ---

        # 4. 合并结果
        final_result = None
        if config.merge_results and all_chunk_results:
            if config.verbose:
                logger.info(f"  -> 正在合并 {len(all_chunk_results)} 个块的结果...")
            final_result = self._merge_graph_documents(all_chunk_results)
            final_nodes_count = len(final_result.nodes) if final_result else 0
            final_relationships_count = len(final_result.relationships) if final_result else 0
            if config.verbose:
                logger.info(f"  -> 合并完成。最终节点数: {final_nodes_count}, 最终关系数: {final_relationships_count}")
        else:
            final_result = all_chunk_results[0] if all_chunk_results else SerializableGraphDocument(nodes=[],
                                                                                                    relationships=[])
            final_nodes_count = len(final_result.nodes)
            final_relationships_count = len(final_result.relationships)
            if config.verbose:
                logger.info(
                    f"  -> 未启用合并或无结果。最终节点数: {final_nodes_count}, 最终关系数: {final_relationships_count}")

        end_time_core = time.time()
        total_duration_core = end_time_core - start_time_core
        # status: 0=全部成功, 1=部分成功, 2=全部失败
        status = 0 if successful_chunks == len(split_docs) else (1 if successful_chunks > 0 else 2)

        if config.verbose and not is_sub_extraction:  # 避免子提取时重复打印
            logger.info(
                f"  -> 所有块处理完成! "
                f"成功处理 {successful_chunks}/{len(split_docs)} 个块。"
                f"总计节点数: {total_nodes}, 总计关系数: {total_relationships}。"
                f"最终节点数: {final_nodes_count}, 最终关系数: {final_relationships_count}。"
                f"总耗时: {total_duration_core:.2f} 秒"
            )

        return final_result, total_duration_core, status, all_chunk_results
    def _extract_with_cache_internal(self, config: ExtractionConfig) -> Tuple[Any, float, int, List[Any]]:
        """带缓存功能的内部提取方法"""
        # 生成缓存键
        cache_key = get_cache_key_from_config(config)

        if config.use_cache:
            cached_result = load_cache(cache_key)
            if cached_result is not None:
                if config.verbose:
                    logger.info(f"命中缓存: {config.novel_name} - {config.chapter_name}")
                # 如果缓存的是字典格式，转换回对象
                if isinstance(cached_result, dict):
                    cached_result = SerializableGraphDocument.from_dict(cached_result)
                # 添加缓存标记
                if hasattr(cached_result, '__dict__'):
                    cached_result._is_from_cache = True
                return cached_result, 0.0, 0, []

        # 调用原始 extract 方法
        result, duration, status, chunks = self._extract_internal(config)

        # 保存缓存
        if config.use_cache:
            cache_data = result
            if isinstance(result, SerializableGraphDocument):
                cache_data = result.to_dict()

            # 生成元数据
            metadata = generate_cache_metadata(**config.to_metadata_params())

            save_cache(cache_key, cache_data, metadata)
            if config.verbose:
                logger.info(f"结果已缓存: {config.novel_name} - {config.chapter_name} ({cache_key}.json)")

        return result, duration, status, chunks

    # ==============================
    # 兼容性方法
    # ==============================

    def extract_with_cache(
            self,
            text: str,
            novel_name: str,
            chapter_name: str,
            num_ctx: Optional[int] = None,
            chunk_size: Optional[int] = None,
            chunk_overlap: Optional[int] = None,
            merge_results: bool = True,
            verbose: bool = True,
            use_cache: bool = True,
            use_local: bool = True,
            schema_name: str = "基础"
    ) -> Tuple[Any, float, int, List[Any]]:
        """
        带缓存功能的 extract 方法，支持小说名和章节名（兼容性方法）
        """
        # 创建配置对象
        config = ExtractionConfig(
            novel_name=novel_name,
            chapter_name=chapter_name,
            text=text,
            model_name=self.model_name,
            base_url=self.base_url,
            temperature=self.temperature,
            num_ctx=num_ctx or self.default_num_ctx,
            use_local=use_local,
            remote_api_key=self.remote_api_key,
            remote_base_url=self.remote_base_url,
            remote_model_name=self.remote_model_name,
            chunk_size=chunk_size or self.default_chunk_size,
            chunk_overlap=chunk_overlap or self.default_chunk_overlap,
            merge_results=merge_results,
            schema_name=schema_name,
            use_cache=use_cache,
            verbose=verbose
        )

        return self._extract_with_cache_internal(config)

    @staticmethod
    def display_graph_document(graph_doc: Any, title: str = "Graph Document"):
        """打印 GraphDocument 的内容"""
        if isinstance(graph_doc, SerializableGraphDocument):
            SerializableGraphDocument.display_graph_document(graph_doc, title)
        else:
            print(f"\n=== {title} ===")
            if not hasattr(graph_doc, 'nodes') or not hasattr(graph_doc, 'relationships'):
                print("  -> 返回的对象格式不正确，缺少 nodes 或 relationships 属性。")
                return
            print(f"节点数量: {len(graph_doc.nodes)}")
            print(f"关系数量: {len(graph_doc.relationships)}")
            print("--- 节点 (Nodes) ---")
            for i, node in enumerate(graph_doc.nodes):
                node_id = getattr(node, 'id', 'N/A')
                node_type = getattr(node, 'type', 'N/A')
                node_properties = getattr(node, 'properties', {})
                print(f"  {i + 1}. ID: '{node_id}', Type: '{node_type}', Properties: {node_properties}")
            print("--- 关系 (Relationships) ---")
            for i, rel in enumerate(graph_doc.relationships):
                source_id = getattr(getattr(rel, 'source', None), 'id', 'N/A_Source')
                target_id = getattr(getattr(rel, 'target', None), 'id', 'N/A_Target')
                rel_type = getattr(rel, 'type', 'N/A')
                rel_properties = getattr(rel, 'properties', {})
                print(f"  {i + 1}. '{source_id}' --({rel_type})--> '{target_id}' | Properties: {rel_properties}")
            print("-" * 20)