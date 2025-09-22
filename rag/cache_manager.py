# rag/cache_manager.py

import os
import json
import hashlib
from typing import Any, Dict, Optional, List
from datetime import datetime
from rag.config_models import ExtractionConfig

# --- 修改 1: 从 inputs/rag/config.py 导入 CACHE_DIR ---

from config import CACHE_DIR

# --- 修改 2: 定义子目录 ---
CACHE_SUBFOLDER = "graph_docs"

# --- 修改 3: 构造实际的图谱缓存目录 ---
GRAPH_CACHE_DIR = os.path.join(CACHE_DIR, CACHE_SUBFOLDER) # <--- 确保这行存在

# --- 修改 4: 确保目录存在 ---
os.makedirs(GRAPH_CACHE_DIR, exist_ok=True) # <--- 确保这行存在



def get_cache_key(params: Dict[str, Any]) -> str:
    """生成参数的哈希签名"""
    param_str = json.dumps(params, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(param_str.encode('utf-8')).hexdigest()

def get_cache_key_from_config(config: ExtractionConfig) -> str:
    """从配置对象生成缓存键"""
    cache_params = config.to_cache_params()
    return get_cache_key(cache_params)


def save_cache(key: str, data: Any, metadata: Optional[Dict[str, Any]] = None) -> None:
    """保存缓存，可选择性地保存元数据"""
    # --- 修改 2: 构造正确的路径 ---
    # 保存主要数据为JSON格式 (在 graph_docs 子目录下)
    data_path = os.path.join(GRAPH_CACHE_DIR, f"{key}.json") # 使用 GRAPH_CACHE_DIR
    # --- 修改结束 ---
    try:
        if hasattr(data, 'to_dict'):
            json_data = data.to_dict()
        else:
            json_data = data

        with open(data_path, "w", encoding='utf-8') as f:
            json.dump(json_data, f, ensure_ascii=False, indent=2, default=str)
    except Exception as e:
        print(f"警告：缓存数据保存失败 {key}: {e}")

    if metadata:
        # --- 修改 3: 构造正确的元数据路径 ---
        metadata_path = os.path.join(GRAPH_CACHE_DIR, f"{key}_metadata.json") # 使用 GRAPH_CACHE_DIR
        # --- 修改结束 ---
        try:
            metadata['saved_at'] = datetime.now().isoformat()
            with open(metadata_path, "w", encoding='utf-8') as f:
                json.dump(metadata, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"警告：缓存元数据保存失败 {key}: {e}")


def load_cache(key: str) -> Optional[Any]:
    """加载缓存"""
    # --- 构造缓存数据文件的完整路径 ---
    # 文件结构: CACHE_DIR/graph_docs/{key}.json
    cache_data_filename = f"{key}.json"
    # 使用 os.path.join 拼接完整路径
    cache_data_path = os.path.join(GRAPH_CACHE_DIR, cache_data_filename)

    # --- 添加调试信息：打印完整路径 ---

    # --- 检查文件是否存在并尝试加载 ---
    if os.path.exists(cache_data_path):
        try:
            with open(cache_data_path, "r", encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"警告：缓存文件损坏或无法加载 {key}: {e}") # 保留原有警告
            # 删除损坏的缓存文件 (原有逻辑)
            try:
                os.remove(cache_data_path)
                # 同时尝试删除可能存在的元数据文件
                metadata_filename = f"{key}_metadata.json"
                metadata_path = os.path.join(GRAPH_CACHE_DIR, metadata_filename)
                if os.path.exists(metadata_path):
                    os.remove(metadata_path)
            except Exception as remove_error:
                print(f"警告：删除损坏的缓存文件或元数据文件时出错: {remove_error}")
            return None
    else:
        # --- 添加调试信息：文件不存在 ---
        print(f"[DEBUG] load_cache: File does not exist at path: '{cache_data_path}'")
        # --- 调试信息结束 ---
        pass # 继续执行到 return None

    return None # 文件不存在或加载失败


def load_cache_metadata(key: str) -> Optional[Dict[str, Any]]:
    """加载缓存的元数据"""
    # --- 修改 5: 构造正确的元数据路径 ---
    metadata_path = os.path.join(GRAPH_CACHE_DIR, f"{key}_metadata.json") # 使用 GRAPH_CACHE_DIR
    # --- 修改结束 ---
    if os.path.exists(metadata_path):
        try:
            with open(metadata_path, "r", encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"警告：元数据文件损坏或无法加载 {key}: {e}")
            return None
    return None


def get_metadata_from_cache_key(key: str) -> Dict[str, str]:
    """从缓存键获取元数据"""
    # 首先尝试加载保存的元数据
    metadata = load_cache_metadata(key)
    if metadata:
        return metadata

    # 如果没有保存的元数据，返回默认值
    return {
        "novel_name": "未知小说",
        "chapter_name": "未知章节",
        "model_name": "未知模型",
        "use_local": "未知",
        "num_ctx": "未知",
        "chunk_size": "未知",
        "chunk_overlap": "未知",
        "content_size": "未知",
        "schema_name": "未知模式"  # 添加schema名称
    }


def generate_extractor_cache_params(
        novel_name: str,
        chapter_name: str,
        text: str,
        model_name: str,
        use_remote_api: bool,
        use_local: bool,
        num_ctx: int,
        chunk_size: int,
        chunk_overlap: int,
        merge_results: bool,
        allowed_nodes: list,
        allowed_relationships: list,
        schema_name: str = "基础"  # 添加schema名称参数
) -> Dict[str, Any]:
    """生成 NarrativeGraphExtractor 缓存键的参数字典"""
    params = {
        "novel_name": novel_name,
        "chapter_name": chapter_name,
        "model_name": model_name,
        "use_remote_api": use_remote_api,
        "use_local": use_local,
        "num_ctx": num_ctx,
        "chunk_size": chunk_size,
        "chunk_overlap": chunk_overlap,
        "merge_results": merge_results,
        "text_hash": hashlib.sha256(text.encode('utf-8')).hexdigest(),
        "allowed_nodes": sorted(allowed_nodes or []),
        "allowed_relationships": sorted(allowed_relationships or []),
        "schema_name": schema_name  # 添加schema名称到缓存参数
    }
    return params


def generate_cache_metadata(
        novel_name: str,
        chapter_name: str,
        model_name: str,
        use_local: bool,
        num_ctx: int,
        chunk_size: int,
        chunk_overlap: int,
        content_size: int,
        schema_name: str = "基础"  # 添加schema名称参数
) -> Dict[str, Any]:
    """生成缓存元数据"""
    return {
        "novel_name": novel_name,
        "chapter_name": chapter_name,
        "model_name": model_name,
        "use_local": use_local,
        "num_ctx": num_ctx,
        "chunk_size": chunk_size,
        "chunk_overlap": chunk_overlap,
        "content_size": content_size,
        "schema_name": schema_name,  # 添加schema名称
        "cache_version": "1.1",  # 更新版本号
        "created_at": datetime.now().isoformat()
    }


def list_cache_entries() -> Dict[str, Dict]:
    """列出所有缓存条目及其元数据"""
    cache_entries = {}
    # --- 修改 6: 遍历正确的目录 ---
    # if os.path.exists(CACHE_DIR): # 旧的，检查的是上级目录
    if os.path.exists(GRAPH_CACHE_DIR): # 新的，检查 graph_docs 子目录
         # for filename in os.listdir(CACHE_DIR): # 旧的
         for filename in os.listdir(GRAPH_CACHE_DIR): # 新的
             if filename.endswith('.json') and not filename.endswith('_metadata.json'):
                 key = filename[:-5]  # 移除 .json 后缀
                 cache_entries[key] = {
                     'data_file': filename,
                     'metadata': get_metadata_from_cache_key(key)
                 }
    # --- 修改结束 ---
    return cache_entries


def clear_cache(key: Optional[str] = None) -> None:
    """清除缓存"""
    if key:
        # --- 修改 7: 构造正确的路径 ---
        files_to_remove = [
            # os.path.join(CACHE_DIR, f"{key}.json"), # 旧的
            # os.path.join(CACHE_DIR, f"{key}_metadata.json")
            os.path.join(GRAPH_CACHE_DIR, f"{key}.json"), # 新的
            os.path.join(GRAPH_CACHE_DIR, f"{key}_metadata.json") # 新的
        ]
        # --- 修改结束 ---
        for file_path in files_to_remove:
            if os.path.exists(file_path):
                try:
                    os.remove(file_path)
                except Exception as e:
                    print(f"警告：无法删除文件 {file_path}: {e}")
    else:
        # --- 修改 8: 清除正确的目录 ---
        # for filename in os.listdir(CACHE_DIR): # 旧的
        if os.path.exists(GRAPH_CACHE_DIR): # 检查目录是否存在
            for filename in os.listdir(GRAPH_CACHE_DIR): # 新的
                if filename.endswith('.json'):
                    try:
                        # os.remove(os.path.join(CACHE_DIR, filename)) # 旧的
                        os.remove(os.path.join(GRAPH_CACHE_DIR, filename)) # 新的
                    except Exception as e:
                        print(f"警告：无法删除文件 {filename}: {e}")


def get_cache_stats() -> Dict[str, Any]:
    """获取缓存统计信息"""
    stats = {
        "total_cache_entries": 0,
        "total_size_mb": 0,
        "schemas_used": set(),
        "models_used": set()
    }

    cache_entries = list_cache_entries()
    stats["total_cache_entries"] = len(cache_entries)

    total_size = 0
    for key, entry in cache_entries.items():
        # 计算数据文件大小
        data_path = os.path.join(CACHE_DIR, f"{key}.json")
        if os.path.exists(data_path):
            total_size += os.path.getsize(data_path)

        # 收集schema和模型信息
        metadata = entry['metadata']
        stats["schemas_used"].add(metadata.get("schema_name", "unknown"))
        stats["models_used"].add(metadata.get("model_name", "unknown"))

    stats["total_size_mb"] = round(total_size / (1024 * 1024), 2)
    stats["schemas_used"] = list(stats["schemas_used"])
    stats["models_used"] = list(stats["models_used"])

    return stats


def find_caches_by_schema(schema_name: str) -> List[str]:
    """根据schema名称查找缓存"""
    matching_caches = []
    cache_entries = list_cache_entries()

    for key, entry in cache_entries.items():
        metadata = entry['metadata']
        if metadata.get("schema_name") == schema_name:
            matching_caches.append(key)

    return matching_caches


def remove_old_caches(days_old: int = 30) -> int:
    """删除指定天数前的缓存"""
    import time
    current_time = time.time()
    removed_count = 0

    cache_entries = list_cache_entries()

    for key, entry in cache_entries.items():
        metadata = load_cache_metadata(key)
        if metadata and 'created_at' in metadata:
            created_time = datetime.fromisoformat(metadata['created_at'].replace('Z', '+00:00')).timestamp()
            if (current_time - created_time) > (days_old * 24 * 60 * 60):
                clear_cache(key)
                removed_count += 1

    return removed_count