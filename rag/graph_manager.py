# rag/graph_manager.py (重构后)

import os
import json
import glob
import uuid
import logging
import time
from datetime import datetime
from typing import Dict, Optional, Tuple, Any, List

# --- 从 config.py 导入 CACHE_DIR ---
from config import CACHE_DIR as DEFAULT_CACHE_DIR
# --- 导入缓存相关的工具函数 ---
from rag.cache_manager import save_cache, load_cache, generate_cache_metadata, get_cache_key_from_config
# --- 导入图谱数据类型 ---
from rag.graph_types import SerializableGraphDocument

# --- 定义子目录 ---
GRAPH_CACHE_SUBFOLDER = "graph_docs"
# --- 构造实际的图谱缓存目录 ---
GRAPH_CACHE_DIR = os.path.join(DEFAULT_CACHE_DIR, GRAPH_CACHE_SUBFOLDER)
# 确保目录存在
os.makedirs(GRAPH_CACHE_DIR, exist_ok=True)

logger = logging.getLogger(__name__)


# ==================== 核心缓存管理类 ====================
class GraphCacheManager:
    """
    负责所有与图谱缓存相关的操作：加载、保存、处理和管理。
    这是 NarrativeGraphExtractor 与底层文件系统之间的唯一接口。
    """

    @staticmethod
    def _process_loaded_cache_data(loaded_data: Any, verbose: bool = False, log_context: str = "") -> Optional[
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

    @classmethod
    def load_from_cache_by_hash(cls, cache_hash: str, verbose: bool = True) -> Optional[SerializableGraphDocument]:
        """
        根据给定的 `cache_hash` 直接加载并处理缓存，返回 `SerializableGraphDocument` 对象或 `None`。
        """
        start_time = time.time()
        log_context = f"(Hash: {cache_hash})"
        try:
            cached_result_raw = load_cache(cache_hash)
            if cached_result_raw is None:
                if verbose:
                    logger.info(f"缓存未命中 {log_context}")
                return None
            if verbose:
                logger.info(f"命中缓存 {log_context}")
            processed_result = cls._process_loaded_cache_data(cached_result_raw, verbose, log_context)
            if processed_result is not None and verbose:
                duration = time.time() - start_time
                logger.debug(f"缓存加载与处理耗时: {duration:.4f} 秒 {log_context}")
            return processed_result
        except Exception as e:
            logger.error(f"尝试从缓存加载时发生未预期错误 {log_context}: {e}", exc_info=True)
            return None

    @classmethod
    def load_from_config(cls, config) -> Optional[Tuple[Any, float, int, List[Any]]]:
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
            processed_data = cls._process_loaded_cache_data(cached_data_raw, config.verbose, log_context)
            # 6. 检查处理结果并返回
            if processed_data is not None:
                duration = time.time() - start_time
                return processed_data, duration, 0, []
            else:
                if config.verbose:
                    logger.info(f"缓存命中但处理失败 {log_context}")
                return None
        except Exception as e:
            logger.error(f"加载或处理缓存数据时出错 {log_context}: {e}")
            return None

    @classmethod
    def save_result_to_cache(cls, result: Any, config, start_time: float):
        """
        保存提取结果到缓存。
        """
        if not config.use_cache or result is None:
            return

        cache_key = get_cache_key_from_config(config)
        cache_data = result.to_dict() if isinstance(result, SerializableGraphDocument) else result
        metadata = generate_cache_metadata(**config.to_metadata_params())

        save_cache(cache_key, cache_data, metadata)

        if config.verbose:
            logger.info(f"结果已缓存: {config.novel_name} - {config.chapter_name} ({cache_key}.json)")


# ==================== 图谱管理功能 (保持不变) ====================
def load_available_graphs_metadata() -> Dict[str, Dict]:
    """加载所有可用图谱的元数据"""
    available_graphs = {}
    path = os.path.join(GRAPH_CACHE_DIR, "*_metadata.json")
    metadata_files = glob.glob(path)
    metadata_files.sort(key=os.path.getmtime, reverse=True)
    for meta_file_path in metadata_files:
        try:
            with open(meta_file_path, 'r', encoding='utf-8') as f:
                metadata = json.load(f)
            cache_key = os.path.basename(meta_file_path).replace("_metadata.json", "")
            excluded_fields = {"created_at"}
            filters_data = {}
            for key, value in metadata.items():
                if key not in excluded_fields:
                    filters_data[key] = value
            available_graphs[cache_key] = {
                "filters": filters_data,
                "metadata": {
                    "created_at": metadata.get("created_at", "")
                }
            }
        except Exception as e:
            logger.warning(f"加载元数据文件 {meta_file_path} 时出错: {e}")
            continue
    return available_graphs


def delete_selected_graph(cache_key: str = "") -> bool:
    """删除指定 cache_key 对应的图谱数据文件和元数据文件"""
    if not cache_key:
        return False
    data_file_path = os.path.join(GRAPH_CACHE_DIR, f"{cache_key}.json")
    metadata_file_path = os.path.join(GRAPH_CACHE_DIR, f"{cache_key}_metadata.json")
    files_deleted = []
    if os.path.exists(data_file_path):
        try:
            os.remove(data_file_path)
            files_deleted.append(f"`{os.path.basename(data_file_path)}`")
            logger.info(f"已删除数据文件: {data_file_path}")
        except Exception as e:
            logger.error(f"❌ 删除数据文件 '{data_file_path}' 时出错: {e}")
    if os.path.exists(metadata_file_path):
        try:
            os.remove(metadata_file_path)
            files_deleted.append(f"`{os.path.basename(metadata_file_path)}`")
            logger.info(f"已删除元数据文件: {metadata_file_path}")
        except Exception as e:
            logger.error(f"❌ 删除元数据文件 '{metadata_file_path}' 时出错: {e}")
    return len(files_deleted) > 0


# ==================== 演示数据管理 (保持不变) ====================
def create_demo_data() -> str:
    """创建演示图谱数据和元数据文件"""
    demo_graph_data = {
        "nodes": [
            {"id": "张三", "type": "角色", "properties": {"name": "张三", "sequence_number": 1}},
            {"id": "李四", "type": "角色", "properties": {"name": "李四", "sequence_number": 2}},
            {"id": "愤怒", "type": "情绪", "properties": {"name": "愤怒", "sequence_number": 3}},
            {"id": "宝剑", "type": "物品", "properties": {"name": "宝剑", "sequence_number": 4}}
        ],
        "relationships": [
            {"source_id": "张三", "target_id": "李四", "type": "仇恨", "properties": {}},
            {"source_id": "张三", "target_id": "愤怒", "type": "感受", "properties": {}},
            {"source_id": "张三", "target_id": "宝剑", "type": "持有", "properties": {}}
        ]
    }
    demo_cache_key = "demo_" + str(uuid.uuid4())[:8]
    demo_metadata = {
        "novel_name": "演示小说",
        "chapter_name": "演示章节",
        "schema_name": "演示Schema",
        "model_name": "demo_model",
        "chunk_size": 1000,
        "use_local": True,
        "created_at": datetime.now().isoformat()
    }
    os.makedirs(GRAPH_CACHE_DIR, exist_ok=True)
    with open(os.path.join(GRAPH_CACHE_DIR, f"{demo_cache_key}.json"), "w", encoding="utf-8") as f:
        json.dump(demo_graph_data, f, ensure_ascii=False, indent=2)
    with open(os.path.join(GRAPH_CACHE_DIR, f"{demo_cache_key}_metadata.json"), "w", encoding="utf-8") as f:
        json.dump(demo_metadata, f, ensure_ascii=False, indent=2)
    logger.info(f"✅ 创建演示图谱: {demo_cache_key}")
    return demo_cache_key


def ensure_demo_graph() -> str:
    """确保存在演示图谱，若不存在则创建一个"""
    demo_files = []
    if os.path.exists(GRAPH_CACHE_DIR):
        demo_files = [
            f for f in os.listdir(GRAPH_CACHE_DIR)
            if f.startswith('demo_') and f.endswith('.json') and not f.endswith('_metadata.json')
        ]
    if demo_files:
        demo_cache_key = os.path.splitext(demo_files[0])[0]
        logger.info(f"📂 使用现有演示图谱: {demo_cache_key}")
        return demo_cache_key
    else:
        return create_demo_data()
