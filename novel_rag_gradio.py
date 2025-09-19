# novel_rag_gradio.py
import gradio as gr
import os
import sys
import logging
import time
import hashlib
import tempfile
import requests
from typing import List, Tuple, Any, Dict,Optional

# 添加项目根目录到Python路径
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 导入现有模块
from rag.narrative_graph_extractor import NarrativeGraphExtractor
from utils_chapter import load_chapter_content, get_chapter_list
from rag.cache_manager import get_cache_key, generate_extractor_cache_params, load_cache, generate_cache_metadata, \
    save_cache, get_cache_key_from_config
from rag.narrative_schema import ALL_NARRATIVE_SCHEMAS, DEFAULT_SCHEMA
from rag.config_models import ExtractionConfig

# novel_rag_gradio.py
from rag.config import (
    DEFAULT_MODEL,
    OLLAMA_URL,
    REMOTE_API_KEY,
    REMOTE_BASE_URL,
    REMOTE_MODEL_NAME,
    REMOTE_MODEL_CHOICES,
    CACHE_DIR, DEFAULT_BASE_URL, DEFAULT_TEMPERATURE, DEFAULT_NUM_CTX
)

# 全局 ExtractionConfig 变量
_current_extraction_config: Optional[ExtractionConfig] = None

def set_current_config(config: ExtractionConfig):
    """设置当前全局配置"""
    global _current_extraction_config
    _current_extraction_config = config

def get_current_config() -> Optional[ExtractionConfig]:
    """获取当前全局配置"""
    global _current_extraction_config
    return _current_extraction_config

# Ollama 配置
OLLAMA_URL = "http://localhost:11434"


# --- 模型管理函数 ---
def get_ollama_models():
    """获取 Ollama 本地模型列表"""
    try:
        response = requests.get(f"{OLLAMA_URL}/api/tags")
        response.raise_for_status()
        jsondata = response.json()
        result = []
        for model in jsondata["models"]:
            result.append(model["model"])
        return result
    except Exception as e:
        logger.error(f"获取 Ollama 模型失败: {e}")
        return []


# 获取本地 Ollama 模型列表
ollama_models = get_ollama_models()
default_model = ollama_models[0] if ollama_models else DEFAULT_MODEL

# 公共配置
COMMON_CONFIG = {
    "model_name": default_model,
    "base_url": DEFAULT_BASE_URL,
    "temperature": DEFAULT_TEMPERATURE,
    "default_num_ctx": DEFAULT_NUM_CTX,
    "remote_api_key": REMOTE_API_KEY,
    "remote_base_url": REMOTE_BASE_URL,
    "remote_model_name": REMOTE_MODEL_NAME,
    "remote_model_choices": REMOTE_MODEL_CHOICES,  # 添加这行
}

# 图谱临时存储目录
TEMP_GRAPH_DIR = os.path.join(tempfile.gettempdir(), "novel_rag_graphs")
os.makedirs(TEMP_GRAPH_DIR, exist_ok=True)
logger.info(f"图谱临时存储目录: {TEMP_GRAPH_DIR}")


# --- 数据加载函数 ---
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


def load_text_gradio(novel_name: str, chapter_file: str) -> str:
    """Gradio版本的文本加载"""
    try:
        if not novel_name or not chapter_file:
            logger.warning("小说名称或章节文件名为空")
            return ""
        loaded_result = load_chapter_content(novel_name, chapter_file)
        if isinstance(loaded_result, tuple) and len(loaded_result) > 0:
            original_text = loaded_result[0]
            return original_text if original_text else ""
        return ""
    except Exception as e:
        logger.error(f"加载文本失败: {e}")
        return ""


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

# 修改 create_extractor 函数
def create_extractor_from_config(config: ExtractionConfig) -> NarrativeGraphExtractor:
    """从配置创建提取器"""
    return NarrativeGraphExtractor.from_config(config)
# --- 提取器创建函数 ---
def create_extractor(model_name=None, use_local=True, chunk_size=1024, chunk_overlap=128, num_ctx=None,
                     schema_name="极简"):
    """创建提取器"""
    config = COMMON_CONFIG.copy()
    effective_num_ctx = num_ctx if num_ctx is not None else config["default_num_ctx"]
    actual_model_name = model_name if model_name else config["model_name"]

    # 获取选定的Schema
    selected_schema = ALL_NARRATIVE_SCHEMAS.get(schema_name, DEFAULT_SCHEMA)

    logger.info(f"Creating extractor with model: {actual_model_name}, use_local: {use_local}, schema: {schema_name}")

    # 根据 use_local 参数决定使用哪个模型配置
    if use_local:
        extractor = NarrativeGraphExtractor(
            model_name=actual_model_name,
            base_url=config["base_url"],
            temperature=config["temperature"],
            default_num_ctx=effective_num_ctx,
            default_chunk_size=chunk_size,
            default_chunk_overlap=chunk_overlap,
            allowed_nodes=selected_schema["elements"],
            allowed_relationships=selected_schema["relationships"]
        )
        logger.info(f"NarrativeGraphExtractor initialized with local model: {actual_model_name}")
    else:
        extractor = NarrativeGraphExtractor(
            remote_api_key=config["remote_api_key"],
            remote_base_url=config["remote_base_url"].strip(),
            remote_model_name=config["remote_model_name"],
            temperature=config["temperature"],
            default_num_ctx=effective_num_ctx,
            default_chunk_size=chunk_size,
            default_chunk_overlap=chunk_overlap,
            allowed_nodes=selected_schema["elements"],
            allowed_relationships=selected_schema["relationships"]
        )
        logger.info(f"NarrativeGraphExtractor initialized with remote API model: {config['remote_model_name']}")

    return extractor


# --- 模型信息处理函数 ---
def determine_model_info(model_type_choice: str, local_model_choice: str, extractor: NarrativeGraphExtractor) -> Tuple[
    str, str, bool]:
    """确定实际模型名称和显示名称"""
    use_local = model_type_choice == "本地模型"
    if use_local:
        actual_model_name = local_model_choice
        model_display = f"本地模型 ({actual_model_name})"
    else:
        actual_model_name = extractor.remote_model_name
        model_display = f"远程模型 ({actual_model_name})"
    logger.info(f"模型选择: {model_type_choice}")
    logger.info(f"使用 {'本地' if use_local else '远程'} 模型: {actual_model_name}")
    return actual_model_name, model_display, use_local


# --- 文本格式化函数 ---
def format_status_text_simple(is_cached: bool = False) -> str:
    """格式化状态文本 - 使用全局配置"""
    config = get_current_config()
    if not config:
        return "❌ 未找到配置信息"

    processing_type = " (缓存)" if is_cached else ""
    model_type = "本地" if config.use_local else "远程"
    model_display_name = f"{model_type}模型 ({config.model_name}){processing_type}"

    # 获取Schema的显示名称
    schema_config = ALL_NARRATIVE_SCHEMAS.get(config.schema_name, DEFAULT_SCHEMA)
    schema_display_name = schema_config.get("name", config.schema_name)
    schema_description = schema_config.get("description", "")

    # 特殊处理无约束模式
    if config.schema_name == "无约束":
        schema_info = f"🎨 图谱模式: {schema_display_name} (无类型限制)\n"
    else:
        schema_info = f"🎨 图谱模式: {schema_display_name}\n"

    return (f"🧠 模型: {model_display_name}\n"
            f"{schema_info}"
            f"ℹ️  {schema_description}\n"
            f"📝 文本长度: {len(config.text)} 字符\n"
            f"🧠 上下文长度: {config.num_ctx}\n"
            f"📊 分块大小: {config.chunk_size}, 重叠: {config.chunk_overlap}")


# 保持向后兼容
def format_status_text(model_display: str, text: str, num_ctx: int, chunk_size: int, chunk_overlap: int,
                       schema_name: str, is_cached: bool = False) -> str:
    return format_status_text_simple(is_cached)


def format_result_and_stats_text_simple(is_cached: bool) -> Tuple[str, str]:
    """格式化结果和统计文本 - 使用全局配置"""
    config = get_current_config()
    if not config or not hasattr(config, '_extraction_result'):
        return "❌ 未找到配置或结果信息", "❌ 未找到配置或结果信息"

    result_data = config._extraction_result  # 假设我们将结果存储在配置中

    status_msg = {0: "✅ 全部成功", 1: "⚠️ 部分成功", 2: "❌ 全部失败"}
    final_status = status_msg.get(result_data.get('status', 2), "未知")
    processing_type = " (缓存)" if is_cached else ""
    final_status_display = f"{final_status}{processing_type}"
    cache_info = " (来自缓存)" if is_cached else ""

    # 获取Schema的显示名称
    schema_config = ALL_NARRATIVE_SCHEMAS.get(config.schema_name, DEFAULT_SCHEMA)
    schema_display = schema_config.get("name", config.schema_name)

    result_text = (f"{final_status_display}\n"
                   f"⏱️ 处理耗时: {result_data.get('duration', 0):.2f} 秒{cache_info}\n"
                   f"🧩 分块数量: {result_data.get('chunk_count', 'N/A')}\n"
                   f"🔗 节点数量: {result_data.get('node_count', 0)}\n"
                   f"🔗 关系数量: {result_data.get('relationship_count', 0)}\n"
                   f"🎨 图谱模式: {schema_display}\n"
                   f"💾 缓存Key: {result_data.get('cache_key', 'unknown')}")

    stats_text = (f"📊 处理统计{cache_info}:\n"
                  f"• 总耗时: {result_data.get('duration', 0):.2f} 秒{cache_info}\n"
                  f"• 文本长度: {len(config.text)} 字符\n"
                  f"• 上下文长度: {config.num_ctx}\n"
                  f"• 分块数量: {result_data.get('chunk_count', 'N/A')}\n"
                  f"• 节点数量: {result_data.get('node_count', 0)}\n"
                  f"• 关系数量: {result_data.get('relationship_count', 0)}\n"
                  f"• 图谱模式: {schema_display}\n"
                  f"• 处理状态: {final_status_display}")

    return result_text, stats_text


# 保持向后兼容
def format_result_and_stats_text(
        result: Any,
        duration: float,
        status: int,
        chunks: List[Any],
        text: str,
        num_ctx: int,
        chunk_size: int,
        chunk_overlap: int,
        schema_name: str,
        is_cached: bool,
        graph_cache_key: str
) -> Tuple[str, str]:
    # 将结果存储到全局配置中供简化版本使用
    config = get_current_config()
    if config:
        config._extraction_result = {
            'result': result,
            'duration': duration,
            'status': status,
            'chunks': chunks,
            'chunk_count': len(chunks) if chunks else 'N/A',
            'node_count': len(getattr(result, 'nodes', [])),
            'relationship_count': len(getattr(result, 'relationships', [])),
            'cache_key': graph_cache_key
        }

    status_msg = {0: "✅ 全部成功", 1: "⚠️ 部分成功", 2: "❌ 全部失败"}
    final_status = status_msg.get(status, "未知")
    processing_type = " (缓存)" if is_cached else ""
    final_status_display = f"{final_status}{processing_type}"
    cache_info = " (来自缓存)" if is_cached else ""

    schema_config = ALL_NARRATIVE_SCHEMAS.get(schema_name, DEFAULT_SCHEMA)
    schema_display = schema_config.get("name", schema_name)

    result_text = (f"{final_status_display}\n"
                   f"⏱️ 处理耗时: {duration:.2f} 秒{cache_info}\n"
                   f"🧩 分块数量: {len(chunks) if chunks else 'N/A'}\n"
                   f"🔗 节点数量: {len(getattr(result, 'nodes', []))}\n"
                   f"🔗 关系数量: {len(getattr(result, 'relationships', []))}\n"
                   f"🎨 图谱模式: {schema_display}\n"
                   f"💾 缓存Key: {graph_cache_key}")

    stats_text = (f"📊 处理统计{cache_info}:\n"
                  f"• 总耗时: {duration:.2f} 秒{cache_info}\n"
                  f"• 文本长度: {len(text)} 字符\n"
                  f"• 上下文长度: {num_ctx}\n"
                  f"• 分块数量: {len(chunks) if chunks else 'N/A'}\n"
                  f"• 节点数量: {len(getattr(result, 'nodes', []))}\n"
                  f"• 关系数量: {len(getattr(result, 'relationships', []))}\n"
                  f"• 图谱模式: {schema_display}\n"
                  f"• 处理状态: {final_status_display}")

    return result_text, stats_text


def generate_graph_link_html(graph_cache_key: str, schema_name: str) -> str:
    """生成指向 Streamlit 图谱查看器的链接 HTML"""
    streamlit_url = f"http://localhost:8501/?cache_key={graph_cache_key}"

    # 获取Schema的显示名称 - 修复访问方式
    schema_config = ALL_NARRATIVE_SCHEMAS.get(schema_name, DEFAULT_SCHEMA)
    schema_display = schema_config.get("name", schema_name)  # ✅ 正确访问

    return f"""
    <div styles="margin-top: 15px; padding: 15px; background-color: #e8f4fd; border-radius: 8px; border-left: 4px solid #4dabf7;">
        <h4 styles="margin: 0 0 10px 0; color: #1c7ed6;">🔗 知识图谱已生成</h4>
        <p styles="margin: 5px 0;">分析完成！点击下方链接在新窗口中查看交互式图谱。</p>
        <p styles="margin: 5px 0; font-size: 0.9em; color: #666;">图谱模式: <strong>{schema_display}</strong></p>
        <a href="{streamlit_url}" target="_blank" 
           styles="display: inline-block; margin-top: 10px; padding: 8px 16px; background-color: #4dabf7; color: white; text-decoration: none; border-radius: 5px; font-weight: bold;">
            📊 在新窗口查看图谱
        </a>
        <p styles="margin-top: 15px; font-size: 0.85em; color: #666;">
           <strong>提示:</strong> 确保 Streamlit 查看器 (<code>novel_graph_viewer.py</code>) 正在运行在 <code>http://localhost:8501</code>。
           缓存键: <code styles="background-color: #d0ebff; padding: 2px 4px; border-radius: 3px;">{graph_cache_key[:16]}...</code>
        </p>
    </div>
    """


def ensure_metadata_exists_simple():
    """确保缓存文件存在对应的元数据文件 - 使用全局配置"""
    config = get_current_config()
    if not config:
        logger.error("未找到全局配置")
        return

    try:
        # 检查缓存数据文件是否存在
        cache_dir = "./cache/graph_docs"
        data_path = os.path.join(cache_dir, f"{config._cache_key}.json")

        if os.path.exists(data_path):
            # 检查元数据文件是否存在
            metadata_path = os.path.join(cache_dir, f"{config._cache_key}_metadata.json")
            if not os.path.exists(metadata_path):
                # 生成元数据 - 直接使用配置对象的参数
                metadata = generate_cache_metadata(**config.to_metadata_params())

                # 添加Schema信息到元数据
                metadata["schema_display"] = ALL_NARRATIVE_SCHEMAS.get(config.schema_name, DEFAULT_SCHEMA)["name"]

                # 保存元数据
                cached_data = load_cache(config._cache_key)
                if cached_data is not None:
                    save_cache(config._cache_key, cached_data, metadata)
                    logger.info(f"为缓存 {config._cache_key} 生成了缺失的元数据")
                else:
                    logger.warning(f"无法为缓存 {config._cache_key} 生成元数据：缓存数据无法加载")
            else:
                logger.info(f"缓存 {config._cache_key} 的元数据已存在")
        else:
            logger.warning(f"缓存数据文件不存在: {data_path}")
    except Exception as e:
        logger.error(f"确保元数据存在时出错: {e}")


# 保持向后兼容
def ensure_metadata_exists(cache_key: str, novel_name: str, chapter_name: str, model_name: str,
                           use_local: bool, num_ctx: int, chunk_size: int, chunk_overlap: int, content_size: int,
                           schema_name: str):
    # 设置全局配置中的缓存键
    config = get_current_config()
    if config:
        config._cache_key = cache_key

    ensure_metadata_exists_simple()


# --- 主处理函数 ---
def extract_graph_gradio(
        novel_name: str,
        chapter_file: str,
        model_type_choice: str,
        local_model_choice: str,
        remote_model_choice: str,  # 添加这个参数
        chunk_size: int,
        chunk_overlap: int,
        num_ctx: int,
        schema_choice: str,
        use_cache: bool
) -> Tuple[str, str, str, str]:
    """Gradio版本的图谱提取"""


    try:
        # 1. 基本输入检查
        if not novel_name or not chapter_file:
            return "❌ 请选择小说和章节文件", "", "", ""

        # 2. 加载文本
        text = load_text_gradio(novel_name, chapter_file)
        if not text:
            return "❌ 无法加载文本", "", "", ""

        # 3. 确定使用的模型
        use_local = model_type_choice == "本地模型"
        model_name = local_model_choice if use_local else remote_model_choice
        chapter_name = os.path.splitext(chapter_file)[0]

        # 4. 调试信息
        logger.info(f"模型选择 - 类型: {model_type_choice}, 本地: {use_local}")
        logger.info(f"使用模型: {model_name}")
        if not use_local:
            logger.info(f"远程配置 - API Key: {'已设置' if COMMON_CONFIG['remote_api_key'] else '未设置'}")
            logger.info(f"远程配置 - Base URL: {COMMON_CONFIG['remote_base_url']}")
            logger.info(f"远程配置 - Model Name: {remote_model_choice}")

        # 5. 创建配置对象并设置为全局变量
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
            remote_model_name=remote_model_choice,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            merge_results=True,
            schema_name=schema_choice,
            use_cache=use_cache,
            verbose=True
        )

        logger.info(f"用户选择的模型类型: {model_type_choice}")
        logger.info(f"计算得到的 use_local: {use_local}")
        logger.info(f"将要使用的模型名称: {model_name}")

        # 设置全局配置
        set_current_config(config)

        # 6. 创建提取器
        extractor = create_extractor_from_config(config)

        # 7. 模型配置检查 (仅对远程模型)
        if not use_local:
            if not extractor.remote_api_key or not extractor.remote_base_url or not extractor.remote_model_name:
                logger.error("远程API配置不完整")
                logger.error(f"API Key: {bool(extractor.remote_api_key)}")
                logger.error(f"Base URL: {bool(extractor.remote_base_url)}")
                logger.error(f"Model Name: {bool(extractor.remote_model_name)}")
                return "❌ 远程API配置不完整", "", "", ""

        # 7. 生成缓存键
        graph_cache_key = get_cache_key_from_config(config)
        config._cache_key = graph_cache_key  # 存储缓存键到配置中
        logger.info(f"为此分析生成的缓存键: {graph_cache_key}")

        # 8. 格式化初始状态文本
        actual_model_name, model_display, use_local_flag = determine_model_info(
            model_type_choice, local_model_choice, extractor)
        status_text = format_status_text_simple(is_cached=False)

        # 9. 执行提取
        start_time = time.time()
        result, duration, status, chunks = extractor.extract_with_config(config)
        end_time = time.time()
        duration = end_time - start_time

        # 10. 处理结果
        is_cached = getattr(result, '_is_from_cache', False) if result else False

        # 11. 更新状态文本 (带缓存信息)
        status_text = format_status_text_simple(is_cached=is_cached)

        # 12. 格式化结果和统计文本
        result_text, stats_text = format_result_and_stats_text(
            result, duration, status, chunks, text, num_ctx, chunk_size, chunk_overlap, schema_choice, is_cached,
            graph_cache_key
        )

        # 13. 生成图谱链接 HTML
        graph_link_html = generate_graph_link_html(graph_cache_key, schema_choice)

        return status_text, result_text, stats_text, graph_cache_key

    except Exception as e:
        logger.error(f"提取失败: {e}", exc_info=True)
        import traceback
        error_info = traceback.format_exc()
        return f"❌ 提取失败: {str(e)}", "", "", ""

# --- UI 组件创建函数 ---
def create_input_settings_column():
    """创建输入设置列"""
    with gr.Column(scale=1):
        gr.Markdown("### 🎯 输入设置")

        # —————— 修复重点：只定义一次 novel_name，并放在 Row 里 ——————
        with gr.Row():
            novel_name = gr.Dropdown(
                label="小说名称",
                choices=initial_novels,
                value=initial_novel if initial_novel in initial_novels else (
                    initial_novels[0] if initial_novels else ""),
                info="选择要分析的小说文件夹"
            )
            refresh_btn = gr.Button("🔄 刷新", size="sm", elem_classes=["refresh-btn"])

        # 定义 chapter_file（在 novel_name 之后，确保作用域内）
        chapter_file = gr.Dropdown(
            label="章节文件",
            choices=initial_chapters,
            value=initial_chapter if initial_chapter in initial_chapters else (
                initial_chapters[0] if initial_chapters else ""),
            info="选择要分析的章节"
        )

        # —————— 刷新函数 ——————
        def refresh_novels_and_chapters(current_selected_novel=None):
            novels = get_novel_list()
            if not novels:
                return (
                    gr.update(choices=[], value=""),
                    gr.update(choices=[], value=""),
                    gr.update()
                )
            # 保留当前选中，若无效则选第一个
            target_novel = current_selected_novel if current_selected_novel in novels else novels[0]
            chapters = get_novel_chapters(target_novel)
            first_chapter = chapters[0] if chapters else ""
            return (
                gr.update(choices=novels, value=target_novel),
                gr.update(choices=chapters, value=first_chapter),
                gr.update()
            )

        # 绑定刷新按钮
        refresh_btn.click(
            fn=refresh_novels_and_chapters,
            inputs=[novel_name],
            outputs=[novel_name, chapter_file, gr.State()]
        )

        # —————— 小说变化 → 更新章节 ——————
        def update_chapters(novel):
            if not novel:
                return gr.update(choices=[], value="")
            chapters = get_novel_chapters(novel)
            if not chapters:
                logger.info(f"小说 '{novel}' 没有找到有效的章节文件。")
                return gr.update(choices=[], value="")
            return gr.update(choices=chapters, value=chapters[0])

        novel_name.change(
            fn=update_chapters,
            inputs=[novel_name],
            outputs=[chapter_file]
        )

        # —————— 以下保持不变 ——————
        model_type = gr.Radio(
            choices=["本地模型", "远程模型"],
            value="本地模型",
            label="模型类型"
        )

        local_model_choice = gr.Dropdown(
            label="选择本地模型",
            choices=ollama_models,
            value=default_model,
            visible=True
        )

        remote_model_choice = gr.Dropdown(
            label="选择远程模型",
            choices=COMMON_CONFIG["remote_model_choices"],
            value=COMMON_CONFIG["remote_model_name"],
            visible=False
        )

        remote_model_info = gr.Markdown(
            value=f"远程模型: `{COMMON_CONFIG['remote_model_name']}`",
            visible=False
        )

        schema_choices = {key: f"{schema['name']} - {schema['description']}"
                          for key, schema in ALL_NARRATIVE_SCHEMAS.items()}
        schema_choice = gr.Dropdown(
            label="图谱模式",
            choices=schema_choices,
            value="自动生成",
            info="选择知识图谱提取模式"
        )

        def toggle_model_inputs(model_type_choice):
            is_local = model_type_choice == "本地模型"
            remote_info_text = f"远程模型: `{COMMON_CONFIG['remote_model_name']}`"
            return (
                gr.update(visible=is_local),
                gr.update(visible=not is_local),
                gr.update(visible=not is_local, value=remote_info_text)
            )

        def update_remote_model_info(remote_model_selected):
            remote_info_text = f"远程模型: `{remote_model_selected or COMMON_CONFIG['remote_model_name']}`"
            return gr.update(value=remote_info_text)

        with gr.Accordion("⚙️ 高级设置", open=False):
            chunk_size = gr.Slider(
                minimum=256, maximum=4096, value=1024, step=128,
                label="分块大小"
            )
            chunk_overlap = gr.Slider(
                minimum=64, maximum=512, value=192, step=32,
                label="分块重叠"
            )
            num_ctx = gr.Slider(
                minimum=1024, maximum=16384, value=16384, step=256,
                label="上下文长度",
            )
            use_cache = gr.Checkbox(
                value=True,
                label="使用缓存",
                info="启用缓存可避免重复处理相同参数"
            )

        model_type.change(
            fn=toggle_model_inputs,
            inputs=[model_type],
            outputs=[local_model_choice, remote_model_choice, remote_model_info]
        ).then(
            fn=update_num_ctx_range,
            inputs=[model_type],
            outputs=[num_ctx]
        )

        remote_model_choice.change(
            fn=update_remote_model_info,
            inputs=[remote_model_choice],
            outputs=[remote_model_info]
        )

        extract_btn = gr.Button("🚀 开始分析", variant="primary")
        graph_view_btn = gr.Button("📊 在新窗口查看图谱", variant="secondary", interactive=False)
        graph_cache_key_state = gr.State()

        def open_graph_viewer_simple(cache_key: str):
            if not cache_key:
                return
            try:
                config = get_current_config()
                if config:
                    config._cache_key = cache_key
                    ensure_metadata_exists_simple()
            except Exception as e:
                logger.error(f"检查/生成元数据时出错: {e}")
            streamlit_url = f"http://localhost:8501/?cache_key={cache_key}"
            import webbrowser
            webbrowser.open_new_tab(streamlit_url)

        def open_graph_viewer(cache_key: str, novel_name: str, chapter_file: str, model_type_choice: str,
                              local_model_choice: str, remote_model_choice: str,
                              chunk_size: int, chunk_overlap: int, num_ctx: int,
                              schema_choice: str):
            open_graph_viewer_simple(cache_key)

        graph_view_btn.click(
            fn=open_graph_viewer,
            inputs=[graph_cache_key_state, novel_name, chapter_file, model_type, local_model_choice,
                    remote_model_choice, chunk_size, chunk_overlap, num_ctx, schema_choice],
            outputs=[graph_cache_key_state]
        )

        return (novel_name, chapter_file, model_type, local_model_choice, remote_model_choice, schema_choice,
                chunk_size, chunk_overlap, num_ctx, use_cache,
                extract_btn, graph_view_btn, graph_cache_key_state)


def create_output_display_column():
    """创建输出显示列"""
    with gr.Column(scale=2):
        gr.Markdown("### 📊 处理状态")
        status_output = gr.Textbox(
            label="处理进度",
            interactive=False,
            lines=6
        )

        result_output = gr.Textbox(
            label="处理结果",
            interactive=False,
            lines=12
        )

        stats_output = gr.Textbox(
            label="统计信息",
            interactive=False,
            lines=8
        )

        return status_output, result_output, stats_output


def create_text_processing_tab():
    """创建文本处理标签页"""
    with gr.Tab("📚 文本处理", id="text-tab"):
        with gr.Row():
            # 创建输入设置列
            (novel_name, chapter_file, model_type, local_model_choice, remote_model_choice, schema_choice,
             chunk_size, chunk_overlap, num_ctx, use_cache,
             extract_btn, graph_view_btn, graph_cache_key_state) = create_input_settings_column()

            # 创建输出显示列
            status_output, result_output, stats_output = create_output_display_column()


        return (novel_name, chapter_file, model_type, local_model_choice, remote_model_choice, schema_choice,
                chunk_size, chunk_overlap, num_ctx, use_cache,
                extract_btn, graph_view_btn, graph_cache_key_state,
                status_output, result_output, stats_output)


def create_graph_visualization_tab():
    """创建图谱可视化标签页"""
    with gr.Tab("📊 图谱可视化", id="graph-tab"):
        gr.Markdown("### 📈 交互式知识图谱")
        graph_visualization_output = gr.HTML(
            value="<div styles='text-align: center; padding: 50px; color: #aaaaaa; background-color: #f0f0f0; border-radius: 8px;'>📊 点击“📚 文本处理”标签页中的“🚀 开始分析”按钮处理文本，完成后交互式图谱将在此处显示</div>"
        )
        return graph_visualization_output

def update_num_ctx_range(model_type_choice):
    """根据模型类型动态更新上下文长度滑块的最大值和默认值"""
    is_local = model_type_choice == "本地模型"
    if is_local:
        max_ctx = 16384
        default_ctx = 16384
    else:
        max_ctx = 32000
        default_ctx = 32000
    return gr.update(maximum=max_ctx, value=default_ctx)
# --- 初始化小说列表 ---
initial_novels = get_novel_list()
initial_novel = initial_novels[0] if initial_novels else ""

# 获取章节时容错
initial_chapters = []
initial_chapter = ""
if initial_novel:
    initial_chapters = get_novel_chapters(initial_novel)
    initial_chapter = initial_chapters[0] if initial_chapters else ""

# --- 主界面构建 ---
with gr.Blocks(title="📖 小说叙事图谱分析器", theme=gr.themes.Soft()) as demo:
    gr.Markdown("""
    # 📖 小说叙事图谱分析器
    从文本中提取叙事元素并构建知识图谱，支持本地和远程模型
    """)

    # 创建标签页 - 修复这里的解包数量
    (novel_name, chapter_file, model_type, local_model_choice, remote_model_choice, schema_choice,
     chunk_size, chunk_overlap, num_ctx, use_cache,
     extract_btn, graph_view_btn, graph_cache_key_state,
     status_output, result_output, stats_output) = create_text_processing_tab()

    graph_visualization_output = create_graph_visualization_tab()

    # 绑定事件
    extract_btn.click(
        fn=extract_graph_gradio,
        inputs=[novel_name, chapter_file, model_type, local_model_choice, remote_model_choice,
                chunk_size, chunk_overlap, num_ctx, schema_choice, use_cache],
        outputs=[status_output, result_output, stats_output, graph_cache_key_state],
        queue=True
    ).then(
        fn=lambda key: gr.update(interactive=bool(key)),
        inputs=[graph_cache_key_state],
        outputs=[graph_view_btn]
    )

    gr.Markdown("""
    ---
    ### 💡 使用说明
    1. **选择小说和章节** - 从下拉菜单中选择 `novels` 文件夹下的小说及其章节
    2. **选择模型** - 本地模型速度快，远程模型可能更准确
    3. **选择图谱模式** - 不同模式提取不同粒度的叙事元素
    4. **调整参数** - 可以修改分块大小、重叠和上下文长度来优化效果
    5. **开始分析** - 点击按钮开始处理文本
    6. **查看结果** - 分析完成后，切换到“📊 图谱可视化”标签页查看交互式图谱

    ### 🛠️ 技术特点
    - 支持多种图谱模式：基础模式、最小化模式、完整模式
    - 支持缓存机制，避免重复处理
    - 自动分块处理长文本
    - 交互式图谱直接在应用内显示
    - 详细的处理统计信息
    - 可调节模型上下文长度
    """)

if __name__ == "__main__":
    demo.launch(
        server_name="0.0.0.0",
        server_port=7860,
        share=False,
        inbrowser=True
    )