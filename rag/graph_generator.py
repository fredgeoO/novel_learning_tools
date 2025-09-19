# rag/graph_generator.py
"""
小说叙事图谱生成核心逻辑（Flask 兼容版）
负责从文本中提取图谱并保存到缓存
"""

import os
import logging
import time
import requests
from typing import List, Tuple, Dict, Any, Optional
from datetime import datetime

# 本地导入
from rag.narrative_graph_extractor import NarrativeGraphExtractor
from utils_chapter import load_chapter_content, get_chapter_list
from rag.cache_manager import (
    get_cache_key_from_config,
    load_cache,
    save_cache,
    generate_cache_metadata
)
from rag.narrative_schema import ALL_NARRATIVE_SCHEMAS, DEFAULT_SCHEMA
from rag.config_models import ExtractionConfig
from rag.config import CACHE_DIR

# 配置
logger = logging.getLogger(__name__)


# 获取本地 Ollama 模型列表
def get_ollama_models() -> List[str]:
    """获取 Ollama 本地模型列表"""
    try:
        response = requests.get("http://localhost:11434/api/tags", timeout=5)
        response.raise_for_status()
        models = response.json().get("models", [])
        return [model["model"] for model in models]
    except Exception as e:
        logger.error(f"获取 Ollama 模型失败: {e}")
        return []


# 全局默认配置（从 config.py 导入）
from rag.config import (
    DEFAULT_MODEL,
    DEFAULT_BASE_URL,
    DEFAULT_TEMPERATURE,
    DEFAULT_NUM_CTX,
    REMOTE_API_KEY,
    REMOTE_BASE_URL,
    REMOTE_MODEL_NAME,
    REMOTE_MODEL_CHOICES
)

COMMON_CONFIG = {
    "model_name": DEFAULT_MODEL,
    "base_url": DEFAULT_BASE_URL,
    "temperature": DEFAULT_TEMPERATURE,
    "default_num_ctx": DEFAULT_NUM_CTX,
    "remote_api_key": REMOTE_API_KEY,
    "remote_base_url": REMOTE_BASE_URL.strip(),
    "remote_model_name": REMOTE_MODEL_NAME,
    "remote_model_choices": REMOTE_MODEL_CHOICES,
}


# 获取小说列表
def get_novel_list() -> List[str]:
    """获取 novels 目录下的所有小说文件夹名称"""
    novels_base_path = "novels"
    if not os.path.exists(novels_base_path):
        logger.warning(f"小说根目录 '{novels_base_path}' 不存在。")
        return []
    try:
        novel_dirs = [
            d for d in os.listdir(novels_base_path)
            if os.path.isdir(os.path.join(novels_base_path, d))
        ]
        return sorted(novel_dirs)
    except Exception as e:
        logger.error(f"获取小说列表失败: {e}")
        return []


def get_novel_chapters(novel_name: str) -> List[str]:
    """获取小说章节列表"""
    if not novel_name:
        return []
    try:
        chapters = get_chapter_list(novel_name)
        return chapters
    except Exception as e:
        logger.error(f"获取章节列表失败 ({novel_name}): {e}")
        return []


def load_text(novel_name: str, chapter_file: str) -> str:
    """加载文本内容"""
    try:
        if not novel_name or not chapter_file:
            return ""
        loaded_result = load_chapter_content(novel_name, chapter_file)
        if isinstance(loaded_result, tuple) and len(loaded_result) > 0:
            return loaded_result[0] if loaded_result[0] else ""
        return ""
    except Exception as e:
        logger.error(f"加载文本失败: {e}")
        return ""


def extract_graph(
        novel_name: str,
        chapter_file: str,
        model_type: str,  # "local" or "remote"
        model_name: str,
        chunk_size: int,
        chunk_overlap: int,
        num_ctx: int,
        schema_name: str,
        use_cache: bool = True
) -> Dict[str, Any]:
    """
    执行图谱提取的核心函数
    返回结构化结果字典
    """
    try:
        # 1. 输入验证
        if not novel_name or not chapter_file:
            return {"error": "请选择小说和章节文件"}

        # 2. 加载文本
        text = load_text(novel_name, chapter_file)
        if not text:
            return {"error": "无法加载文本内容"}

        chapter_name = os.path.splitext(chapter_file)[0]
        use_local = model_type == "local"

        # 3. 创建配置对象
        config = ExtractionConfig(
            novel_name=novel_name,
            chapter_name=chapter_name,
            text=text,
            model_name=model_name,
            base_url=COMMON_CONFIG["base_url"],
            temperature=COMMON_CONFIG["temperature"],
            num_ctx=num_ctx,
            use_local=use_local,
            remote_api_key=COMMON_CONFIG["remote_api_key"],
            remote_base_url=COMMON_CONFIG["remote_base_url"],
            remote_model_name=model_name if not use_local else "",
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            merge_results=True,
            schema_name=schema_name,
            use_cache=use_cache,
            verbose=True
        )

        # 4. 创建提取器
        extractor = NarrativeGraphExtractor.from_config(config)

        # 5. 模型配置检查（仅远程模型）
        if not use_local:
            if not extractor.remote_api_key or not extractor.remote_base_url or not extractor.remote_model_name:
                return {"error": "远程API配置不完整"}

        # 6. 生成缓存键
        graph_cache_key = get_cache_key_from_config(config)
        config._cache_key = graph_cache_key

        # 7. 检查缓存
        if use_cache:
            cached_result = load_cache(graph_cache_key)
            if cached_result is not None:
                # 标记为缓存结果
                cached_result._is_from_cache = True
                result, chunks = cached_result, []  # 简化处理
                duration = 0.0
                status = 0  # 成功
                is_cached = True
                logger.info(f"从缓存加载图谱: {graph_cache_key}")
            else:
                is_cached = False
        else:
            is_cached = False

        # 8. 执行提取（如果没用缓存或缓存不存在）
        if not is_cached:
            start_time = time.time()
            result, duration, status, chunks = extractor.extract_with_config(config)
            end_time = time.time()
            duration = end_time - start_time

        # 9. 保存结果到缓存
        if not is_cached and result is not None:
            # 生成元数据
            metadata = generate_cache_metadata(**config.to_metadata_params())
            # 添加Schema显示名称
            schema_config = ALL_NARRATIVE_SCHEMAS.get(schema_name, DEFAULT_SCHEMA)
            metadata["schema_display"] = schema_config.get("name", schema_name)

            # 保存到缓存
            save_cache(graph_cache_key, result, metadata)
            logger.info(f"保存图谱到缓存: {graph_cache_key}")

        # 10. 准备返回结果
        node_count = len(getattr(result, 'nodes', []))
        relationship_count = len(getattr(result, 'relationships', []))
        chunk_count = len(chunks) if chunks else 0

        # 格式化状态信息
        status_msg = {0: "✅ 全部成功", 1: "⚠️ 部分成功", 2: "❌ 全部失败"}
        final_status = status_msg.get(status, "未知")
        final_status_display = f"{final_status} {'(缓存)' if is_cached else ''}"

        # 获取Schema显示名称
        schema_config = ALL_NARRATIVE_SCHEMAS.get(schema_name, DEFAULT_SCHEMA)
        schema_display = schema_config.get("name", schema_name)

        return {
            "success": True,
            "cache_key": graph_cache_key,
            "status_text": f"🧠 模型: {'本地' if use_local else '远程'}模型 ({model_name}){' (缓存)' if is_cached else ''}\n"
                           f"🎨 图谱模式: {schema_display}\n"
                           f"📝 文本长度: {len(text)} 字符\n"
                           f"🧠 上下文长度: {num_ctx}\n"
                           f"📊 分块大小: {chunk_size}, 重叠: {chunk_overlap}",
            "result_text": f"{final_status_display}\n"
                           f"⏱️ 处理耗时: {duration:.2f} 秒{' (来自缓存)' if is_cached else ''}\n"
                           f"🧩 分块数量: {chunk_count}\n"
                           f"🔗 节点数量: {node_count}\n"
                           f"🔗 关系数量: {relationship_count}\n"
                           f"🎨 图谱模式: {schema_display}\n"
                           f"💾 缓存Key: {graph_cache_key[:16]}...",
            "stats_text": f"📊 处理统计{' (来自缓存)' if is_cached else ''}:\n"
                          f"• 总耗时: {duration:.2f} 秒\n"
                          f"• 文本长度: {len(text)} 字符\n"
                          f"• 上下文长度: {num_ctx}\n"
                          f"• 分块数量: {chunk_count}\n"
                          f"• 节点数量: {node_count}\n"
                          f"• 关系数量: {relationship_count}\n"
                          f"• 图谱模式: {schema_display}\n"
                          f"• 处理状态: {final_status_display}",
            "is_cached": is_cached,
            "duration": duration,
            "node_count": node_count,
            "relationship_count": relationship_count,
            "chunk_count": chunk_count,
            "schema_display": schema_display
        }

    except Exception as e:
        logger.error(f"提取失败: {e}", exc_info=True)
        return {"error": f"提取失败: {str(e)}"}


# 获取图谱模式列表
def get_schema_choices() -> Dict[str, str]:
    """获取图谱模式选择列表"""
    return {key: f"{schema['name']} - {schema['description']}"
            for key, schema in ALL_NARRATIVE_SCHEMAS.items()}


# 获取默认模型
def get_default_model() -> str:
    """获取默认模型名称"""
    ollama_models = get_ollama_models()
    return ollama_models[0] if ollama_models else DEFAULT_MODEL