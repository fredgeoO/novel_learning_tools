# rag/graph_manager.py

import os
import json
import glob
import uuid
import logging
from datetime import datetime
from typing import Dict, Set

from rag.config import CACHE_DIR as DEFAULT_CACHE_DIR

logger = logging.getLogger(__name__)

def load_available_graphs_metadata(cache_dir: str = DEFAULT_CACHE_DIR) -> Dict[str, Dict]:
    """加载所有可用图谱的元数据"""
    available_graphs = {}

    metadata_files = glob.glob(os.path.join(cache_dir, "*_metadata.json"))
    metadata_files.sort(key=os.path.getmtime, reverse=True)

    for meta_file_path in metadata_files:
        try:
            with open(meta_file_path, 'r', encoding='utf-8') as f:
                metadata = json.load(f)

            cache_key = os.path.basename(meta_file_path).replace("_metadata.json", "")

            # 提取元数据
            filters = {
                "novel_name": metadata.get("novel_name", "未知小说"),
                "chapter_name": metadata.get("chapter_name", "未知章节"),
                "schema_name": metadata.get("schema_name", "未知模式"),
                "model_name": metadata.get("model_name", "未知模型"),
                "num_ctx": str(metadata.get("num_ctx", "未知")),
                "chunk_size": str(metadata.get("chunk_size", "未知")),
                "chunk_overlap": str(metadata.get("chunk_overlap", "未知"))
            }

            # 创建显示名称
            mtime = os.path.getmtime(meta_file_path)
            date_str = datetime.fromtimestamp(mtime).strftime('%m-%d %H:%M')
            display_name = f"{filters['novel_name']} - {filters['chapter_name']} [{date_str}]"

            available_graphs[cache_key] = {
                "cache_key": cache_key,
                "display_name": display_name,
                "metadata": metadata,
                "filters": filters
            }
        except Exception as e:
            logger.warning(f"加载元数据文件 {meta_file_path} 时出错: {e}")
            continue

    return available_graphs


def delete_selected_graph(cache_dir: str = DEFAULT_CACHE_DIR, cache_key: str = "") -> bool:
    """删除指定 cache_key 对应的图谱数据文件和元数据文件"""
    if not cache_key:
        return False

    data_file_path = os.path.join(cache_dir, f"{cache_key}.json")
    metadata_file_path = os.path.join(cache_dir, f"{cache_key}_metadata.json")

    files_deleted = []

    # 删除数据文件
    if os.path.exists(data_file_path):
        try:
            os.remove(data_file_path)
            files_deleted.append(f"`{os.path.basename(data_file_path)}`")
            logger.info(f"已删除数据文件: {data_file_path}")
        except Exception as e:
            logger.error(f"❌ 删除数据文件 '{data_file_path}' 时出错: {e}")

    # 删除元数据文件
    if os.path.exists(metadata_file_path):
        try:
            os.remove(metadata_file_path)
            files_deleted.append(f"`{os.path.basename(metadata_file_path)}`")
            logger.info(f"已删除元数据文件: {metadata_file_path}")
        except Exception as e:
            logger.error(f"❌ 删除元数据文件 '{metadata_file_path}' 时出错: {e}")

    return len(files_deleted) > 0
# ==================== 演示数据管理 ====================

def create_demo_data(cache_dir: str = DEFAULT_CACHE_DIR) -> str:
    """创建演示图谱数据和元数据文件"""
    demo_graph_data = {
        "nodes": [
            {
                "id": "1",
                "label": "彭刚",
                "type": "人物",
                "properties": {"name": "彭刚", "sequence_number": 1}
            },
            {
                "id": "2",
                "label": "彭毅",
                "type": "人物",
                "properties": {"name": "彭毅", "sequence_number": 2}
            }
        ],
        "relationships": [
            {
                "source_id": "1",
                "target_id": "2",
                "type": "兄弟",
                "properties": {}
            }
        ]
    }

    demo_cache_key = "demo_" + str(uuid.uuid4())[:8]
    demo_metadata = {
        "novel_name": "演示小说",
        "chapter_name": "演示章节",
        "model_name": "演示模型",
        "schema_name": "演示模式",
        "chunk_size": "512",
        "chunk_overlap": "50",
        "num_ctx": "2048",
        "created_at": datetime.now().isoformat()
    }

    # 确保目录存在
    os.makedirs(cache_dir, exist_ok=True)

    # 写入图谱数据
    with open(os.path.join(cache_dir, f"{demo_cache_key}.json"), "w", encoding="utf-8") as f:
        json.dump(demo_graph_data, f, ensure_ascii=False, indent=2)

    # 写入元数据
    with open(os.path.join(cache_dir, f"{demo_cache_key}_metadata.json"), "w", encoding="utf-8") as f:
        json.dump(demo_metadata, f, ensure_ascii=False, indent=2)

    logger.info(f"✅ 创建演示图谱: {demo_cache_key}")
    return demo_cache_key


def ensure_demo_graph(cache_dir: str = DEFAULT_CACHE_DIR) -> str:
    """确保存在演示图谱，若不存在则创建一个"""
    # 查找已存在的演示数据
    demo_files = [
        f for f in os.listdir(cache_dir)
        if f.startswith('demo_') and f.endswith('.json') and not f.endswith('_metadata.json')
    ]

    if demo_files:
        demo_cache_key = demo_files[0].replace('.json', '')
        logger.info(f"📂 使用现有演示图谱: {demo_cache_key}")
        return demo_cache_key
    else:
        return create_demo_data(cache_dir)