# rag/graph_manager.py

import os
import json
import glob
import uuid
import logging
from datetime import datetime
from typing import Dict, Set

# --- 修改 1: 从 inputs/rag/config.py 导入 CACHE_DIR ---

from rag.config import CACHE_DIR as DEFAULT_CACHE_DIR

# --- 修改 2: 定义子目录 ---
GRAPH_CACHE_SUBFOLDER = "graph_docs"
# --- 修改 3: 构造实际的图谱缓存目录 ---
GRAPH_CACHE_DIR = os.path.join(DEFAULT_CACHE_DIR, GRAPH_CACHE_SUBFOLDER)
print("GRAPH_CACHE_DIR:" + GRAPH_CACHE_DIR)
# 确保目录存在 (可选，但推荐)
os.makedirs(GRAPH_CACHE_DIR, exist_ok=True)

logger = logging.getLogger(__name__)


def load_available_graphs_metadata() -> Dict[str, Dict]: # 默认值改为 GRAPH_CACHE_DIR
    """加载所有可用图谱的元数据"""
    available_graphs = {}

    path = os.path.join(GRAPH_CACHE_DIR, "*_metadata.json")
    metadata_files = glob.glob(path) # 保持不变，因为它使用了传入的 cache_dir 参数


    metadata_files.sort(key=os.path.getmtime, reverse=True)

    for meta_file_path in metadata_files:
        try:
            with open(meta_file_path, 'r', encoding='utf-8') as f:
                metadata = json.load(f)

            cache_key = os.path.basename(meta_file_path).replace("_metadata.json", "")

            # ⭐️ 重新组织数据结构，匹配前端期望的格式
            # ⭐️ 重新组织数据结构，匹配前端期望的格式
            available_graphs[cache_key] = {
                "filters": {
                    "novel_name": metadata.get("novel_name", ""),
                    "chapter_name": metadata.get("chapter_name", ""),
                    "model_name": metadata.get("model_name", ""),
                    "schema_name": metadata.get("schema_name", ""),
                    "chunk_size": metadata.get("chunk_size", ""),
                    "chunk_overlap": metadata.get("chunk_overlap", ""),
                    "num_ctx": metadata.get("num_ctx", "")
                },
                "metadata": {
                    "created_at": metadata.get("created_at", "")
                }
            }

        except Exception as e:
            logger.warning(f"加载元数据文件 {meta_file_path} 时出错: {e}")
            continue
    return available_graphs


def delete_selected_graph(cache_dir: str = GRAPH_CACHE_DIR, cache_key: str = "") -> bool: # 默认值改为 GRAPH_CACHE_DIR
    """删除指定 cache_key 对应的图谱数据文件和元数据文件"""
    if not cache_key:
        return False

    # data_file_path = os.path.join(cache_dir, f"{cache_key}.json") # 使用传入的或默认的 cache_dir
    # metadata_file_path = os.path.join(cache_dir, f"{cache_key}_metadata.json")
    # 如果要强制在 graph_docs 下操作：
    data_file_path = os.path.join(GRAPH_CACHE_DIR, f"{cache_key}.json") # 强制使用 GRAPH_CACHE_DIR
    metadata_file_path = os.path.join(GRAPH_CACHE_DIR, f"{cache_key}_metadata.json")

    # ... (其余逻辑保持不变，但使用修改后的路径) ...
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

# ==================== 演示数据管理 ====================

def create_demo_data(cache_dir: str = GRAPH_CACHE_DIR) -> str: # 默认值改为 GRAPH_CACHE_DIR
    """创建演示图谱数据和元数据文件"""
    demo_graph_data = {
        # ... (数据保持不变) ...
    }

    demo_cache_key = "demo_" + str(uuid.uuid4())[:8]
    demo_metadata = {
        # ... (元数据保持不变) ...
        "created_at": datetime.now().isoformat()
    }

    # 确保目录存在 (使用 GRAPH_CACHE_DIR)
    os.makedirs(GRAPH_CACHE_DIR, exist_ok=True)

    # 写入图谱数据 (使用 GRAPH_CACHE_DIR)
    # with open(os.path.join(cache_dir, f"{demo_cache_key}.json"), "w", encoding="utf-8") as f: # 原来的
    with open(os.path.join(GRAPH_CACHE_DIR, f"{demo_cache_key}.json"), "w", encoding="utf-8") as f: # 修改后
        json.dump(demo_graph_data, f, ensure_ascii=False, indent=2)

    # 写入元数据 (使用 GRAPH_CACHE_DIR)
    # with open(os.path.join(cache_dir, f"{demo_cache_key}_metadata.json"), "w", encoding="utf-8") as f: # 原来的
    with open(os.path.join(GRAPH_CACHE_DIR, f"{demo_cache_key}_metadata.json"), "w", encoding="utf-8") as f: # 修改后
        json.dump(demo_metadata, f, ensure_ascii=False, indent=2)

    logger.info(f"✅ 创建演示图谱: {demo_cache_key}")
    return demo_cache_key


def ensure_demo_graph(cache_dir: str = GRAPH_CACHE_DIR) -> str: # 默认值改为 GRAPH_CACHE_DIR
    """确保存在演示图谱，若不存在则创建一个"""
    # 查找已存在的演示数据 (在 GRAPH_CACHE_DIR 下查找)
    # demo_files = [
    #     f for f in os.listdir(cache_dir) # 原来的
    #     if f.startswith('demo_') and f.endswith('.json') and not f.endswith('_metadata.json')
    # ]
    # 修改为在 GRAPH_CACHE_DIR 下查找
    demo_files = []
    if os.path.exists(GRAPH_CACHE_DIR): # 先检查目录是否存在
        demo_files = [
            f for f in os.listdir(GRAPH_CACHE_DIR)
            if f.startswith('demo_') and f.endswith('.json') and not f.endswith('_metadata.json')
        ]

    if demo_files:
        # demo_cache_key = demo_files[0].replace('.json', '') # 这个逻辑是对的
        # 但为了清晰，可以明确是从 GRAPH_CACHE_DIR 找到的
        demo_cache_key = os.path.splitext(demo_files[0])[0] # os.path.splitext 更健壮
        logger.info(f"📂 使用现有演示图谱: {demo_cache_key}")
        return demo_cache_key
    else:
        # return create_demo_data(cache_dir) # 原来的，会传递 cache_dir
        return create_demo_data() # 修改后，使用 create_demo_data 的默认值 (GRAPH_CACHE_DIR)
