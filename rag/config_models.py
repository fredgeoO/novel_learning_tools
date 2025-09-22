# rag/config_models.py
"""
配置模型定义
"""

from dataclasses import dataclass
from typing import List, Optional, Dict, Any
from rag.schema_definitions import ALL_NARRATIVE_SCHEMAS, DEFAULT_SCHEMA,MINIMAL_SCHEMA
from config import *


@dataclass
class ExtractionConfig:
    """图谱提取配置"""
    # 基本信息
    novel_name: str
    chapter_name: str
    text: str = ""

    # 模型配置
    model_name: str = DEFAULT_MODEL
    base_url: str = DEFAULT_BASE_URL
    temperature: float = DEFAULT_TEMPERATURE
    num_ctx: int = DEFAULT_NUM_CTX
    use_local: bool = True

    # 远程API配置
    remote_api_key: Optional[str] = None
    remote_base_url: Optional[str] = None
    remote_model_name: Optional[str] = None

    # 文本处理配置
    chunk_size: int = DEFAULT_CHUNK_SIZE
    chunk_overlap: int = DEFAULT_CHUNK_OVERLAP
    merge_results: bool = True

    # 模式配置
    schema_name: str = MINIMAL_SCHEMA["name"]

    # 运行配置
    use_cache: bool = True
    verbose: bool = True

    optimize_graph: bool = True
    max_connections: int = 20
    aggregate_node_type: str = "类聚"
    aggregate_strategy: str = "语义"  # 可选：semantic/structural



    def get_schema(self) -> Dict[str, Any]:
        """获取当前schema配置"""
        return ALL_NARRATIVE_SCHEMAS.get(self.schema_name, DEFAULT_SCHEMA)

    def get_allowed_nodes(self) -> List[str]:
        """获取允许的节点类型"""
        # 如果是无约束模式，返回空列表（表示无限制）
        if self.schema_name == "无约束":
            return []
        schema = self.get_schema()
        return schema.get("elements", [])

    def get_allowed_relationships(self) -> List[str]:
        """获取允许的关系类型"""
        # 如果是无约束模式，返回空列表（表示无限制）
        if self.schema_name == "无约束":
            return []
        schema = self.get_schema()
        return schema.get("relationships", [])

    def to_cache_params(self) -> Dict[str, Any]:
        """转换为缓存参数字典"""
        from rag.cache_manager import generate_extractor_cache_params

        # 确定实际使用的模型名称
        actual_model_name = self.remote_model_name if not self.use_local and self.remote_model_name else self.model_name

        return generate_extractor_cache_params(
            novel_name=self.novel_name,
            chapter_name=self.chapter_name,
            text=self.text,
            model_name=actual_model_name,
            use_remote_api=not self.use_local and bool(
                self.remote_api_key and self.remote_base_url and self.remote_model_name),
            use_local=self.use_local,
            num_ctx=self.num_ctx,
            chunk_size=self.chunk_size,
            chunk_overlap=self.chunk_overlap,
            merge_results=self.merge_results,
            allowed_nodes=self.get_allowed_nodes(),
            allowed_relationships=self.get_allowed_relationships(),
            schema_name=self.schema_name
        )

    def to_metadata_params(self) -> Dict[str, Any]:
        """转换为元数据参数字典"""
        return {
            "novel_name": self.novel_name,
            "chapter_name": self.chapter_name,
            "model_name": self.remote_model_name if not self.use_local and self.remote_model_name else self.model_name,
            "use_local": self.use_local,
            "num_ctx": self.num_ctx,
            "chunk_size": self.chunk_size,
            "chunk_overlap": self.chunk_overlap,
            "content_size": len(self.text),
            "schema_name": self.schema_name
        }