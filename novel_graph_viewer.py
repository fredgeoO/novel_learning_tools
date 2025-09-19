# novel_graph_viewer.py
"""
小说叙事图谱查看器 - 专注UI逻辑
"""

import streamlit as st
import os
import logging
import json
from typing import (Any, Dict, List, Set)
import colorsys
import utils_chapter # 导入章节处理工具
import re

# 本地导入
from rag.graph_renderer import (
    GraphVisualizer,
    format_graph_text,
    load_available_graphs_metadata,
    delete_selected_graph,
    generate_color_from_string,  # 从graph_renderer导入
    simple_hash  # 从graph_renderer导入
)
from rag.cache_manager import get_cache_key, load_cache, get_metadata_from_cache_key, get_cache_key_from_config
from rag.color_schema import NODE_COLOR_MAP, COLOR_LEGEND_CATEGORIES, EDGE_COLOR_MAP  # 导入配色方案

# --- 配置 ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# 确保缓存目录与 Gradio 应用一致
CACHE_DIR = "./cache/graph_docs"
os.makedirs(CACHE_DIR, exist_ok=True)

# 颜色缓存字典 (从graph_renderer导入，这里保留引用)
_color_cache = {}  # 实际使用graph_renderer中的_color_cache


# ==============================
# UI 组件和辅助函数
# ==============================


def display_color_legend_and_controls():
    """在Streamlit中显示颜色图例和控制开关"""
    # 注意：NODE_COLOR_MAP, COLOR_LEGEND_CATEGORIES, EDGE_COLOR_MAP 已从 narrative_schema 导入

    # 添加刷新按钮
    col1, col2 = st.columns([1, 1])
    with col1:
        st.subheader("**显示控制**")
    with col2:
        refresh_button = st.button("🔄 刷新图谱", key="refresh_graph", type="primary", use_container_width=True)

    # 如果点击了刷新按钮，更新session_state并重新运行
    if refresh_button:
        # 收集所有选中的类型
        all_selected_types = set()
        for category, node_types in COLOR_LEGEND_CATEGORIES.items():
            selected_key = f"multiselect_{category}"
            if selected_key in st.session_state:
                all_selected_types.update(st.session_state[selected_key])


        # 计算需要隐藏的类型
        all_node_types = []
        for node_types in COLOR_LEGEND_CATEGORIES.values():
            all_node_types.extend(node_types)
        updated_hidden_types = set(all_node_types) - all_selected_types

        # 更新session_state
        st.session_state["hidden_node_types"] = ",".join(updated_hidden_types)
        st.rerun()

    # 获取当前隐藏的节点类型
    hidden_types_str = st.session_state.get("hidden_node_types", "")
    current_hidden_types = set(hidden_types_str.split(",")) if hidden_types_str else set()

    # 为每个类别创建可折叠的区域
    for category, node_types in COLOR_LEGEND_CATEGORIES.items():
        # 创建唯一的key用于expander
        expander_key = f"expander_{category}"

        # 默认展开第一个类别，其他收起
        is_expanded = category == list(COLOR_LEGEND_CATEGORIES.keys())[0]

        with st.expander(category, expanded=is_expanded):
            # 获取该类别下所有节点类型的可见状态
            category_visible_types = [t for t in node_types if t not in current_hidden_types]

            # 创建该类别的多选框
            selected_types = st.multiselect(
                f"选择要显示的{category}类型:",
                options=node_types,
                default=category_visible_types,
                key=f"multiselect_{category}"
            )

    # 显示颜色图例
    st.markdown("**节点类型颜色说明**")
    for category, node_types in COLOR_LEGEND_CATEGORIES.items():
        st.markdown(f"**{category}**")
        for node_type in node_types:
            color = NODE_COLOR_MAP.get(node_type, "#CCCCCC")
            st.markdown(f"""
            <div style="display: flex; align-items: center; margin: 5px 0; padding-left: 20px;">
                <div style="width: 12px; height: 12px; background-color: {color}; 
                            border-radius: 50%; margin-right: 8px; border: 1px solid #666;"></div>
                <span style="font-size: 0.9em;">{node_type}</span>
            </div>
            """, unsafe_allow_html=True)

    st.markdown("---")

    return refresh_button


def generate_simple_display_name(graph_info: Dict) -> str:
    """
    生成简化的显示名称，只包含技术参数信息

    Args:
        graph_info: 图谱信息字典

    Returns:
        str: 简化的显示名称（只包含技术参数）
    """
    filters = graph_info["filters"]

    # 只显示技术参数信息
    tech_info_parts = []

    # 显示技术参数
    tech_info_parts.append(f"{filters.get('model_name', '未知')}")
    tech_info_parts.append(f"{filters.get('schema_name', '未知')}")
    tech_info_parts.append(f"{filters.get('chunk_size', '未知')}")
    tech_info_parts.append(f"{filters.get('chunk_overlap', '未知')}")
    tech_info_parts.append(f"{filters.get('num_ctx', '未知')}")

    # 组合显示名称
    tech_part = " | ".join(tech_info_parts)

    return f"{tech_part} "


# ==============================
# UI 组件和辅助函数 (续)
# ==============================

# --- 通用辅助函数 ---

def _update_session_and_rerun(session_key: str, new_value: str, reset_keys: list = None):
    """更新 session_state 并根据需要重置其他键，然后重新运行应用"""
    st.session_state[session_key] = new_value
    if reset_keys:
        for key in reset_keys:
            st.session_state.pop(key, None)
    st.rerun()


def _render_selectbox(
        label: str,
        options: list,
        session_key: str,
        reset_keys: list = None
) -> str:
    """
    渲染一个智能的 selectbox，自动处理状态管理。

    Args:
        label: 选择框标签
        options: 选项列表
        session_key: 用于存储状态的 session key
        reset_keys: 当选项改变时需要重置的其他 session keys

    Returns:
        用户当前选择的值
    """
    if not options:
        return None

    # 获取当前存储的值
    current_value = st.session_state.get(session_key)

    # 如果存储的值不在选项中，或者没有存储的值，则使用默认值（第一个选项）
    if current_value not in options:
        current_value = options[0]
        st.session_state[session_key] = current_value  # 同步状态

    # 渲染 selectbox
    displayed_value = st.selectbox(
        label,
        options=options,
        index=options.index(current_value),
        key=session_key + "_input"  # 使用不同的 key 避免冲突
        # --- 已移除 format_func=format_func ---
    )

    # 如果用户做了新的选择
    if displayed_value != current_value:
        _update_session_and_rerun(session_key, displayed_value, reset_keys)

    return displayed_value


def _reset_filter_states():
    """重置分层筛选器的状态"""
    keys_to_clear = ["selected_model", "selected_schema", "selected_params_key"]
    for key in keys_to_clear:
        st.session_state.pop(key, None)


# --- 核心业务逻辑函数 ---

def _get_novel_chapter_structure(cache_dir: str) -> dict:
    """获取小说-章节结构"""
    from rag.graph_renderer import load_available_graphs_metadata

    available_graphs = load_available_graphs_metadata(cache_dir)
    novel_chapter_map = {}
    for key, graph_info in available_graphs.items():
        novel_name = graph_info["filters"].get("novel_name", "未知小说")
        chapter_name = graph_info["filters"].get("chapter_name", "未知章节")

        if novel_name not in novel_chapter_map:
            novel_chapter_map[novel_name] = set()
        novel_chapter_map[novel_name].add(chapter_name)

    return {novel: sorted(list(chapters)) for novel, chapters in novel_chapter_map.items()}


def _get_filtered_graphs(cache_dir: str, selected_novel: str, selected_chapter: str) -> dict:
    """根据选定的小说和章节过滤图谱数据"""
    from rag.graph_renderer import load_available_graphs_metadata

    available_graphs = load_available_graphs_metadata(cache_dir)
    if not available_graphs:
        return {}

    return {
        key: graph_info for key, graph_info in available_graphs.items()
        if graph_info.get("filters", {}).get("novel_name") == selected_novel
           and graph_info.get("filters", {}).get("chapter_name") == selected_chapter
    }


def _extract_options(filtered_graphs: dict) -> tuple:
    """从过滤后的图谱中提取模型、模式和参数选项"""
    models, schemas, params = set(), {}, {}

    for cache_key, graph_info in filtered_graphs.items():
        f = graph_info.get("filters", {})
        model = str(f.get("model_name", "未知模型"))
        schema = str(f.get("schema_name", "未知模式"))
        cs, co, nc = str(f.get("chunk_size", "未知")), str(f.get("chunk_overlap", "未知")), str(
            f.get("num_ctx", "未知"))

        if not model or not schema: continue

        models.add(model)
        schemas[(model, schema)] = schema

        key = (model, schema, cs, co, nc)
        meta = graph_info.get("metadata", {})
        ts = str(meta.get("created_at", "未知时间")) if isinstance(meta, dict) else "未知时间"
        display = f"块:{cs} / 重叠:{co} / 上下文:{nc} ({ts})"

        params[key] = {"display": display, "cache_key": cache_key}

    return sorted(list(models)), schemas, params


def _get_options_for_model_and_schema(params: dict, model: str, schema: str) -> list:
    """获取特定模型和模式下的参数选项"""
    return sorted([info["display"] for key, info in params.items()
                   if key[0] == model and key[1] == schema])


def _get_selected_info(params: dict, model: str, schema: str, display: str) -> dict:
    """根据显示名称获取选中的图谱完整信息"""
    for key, info in params.items():
        if key[0] == model and key[1] == schema and info["display"] == display:
            return info
    return {}


# --- UI 渲染函数 ---

def _render_novel_chapter_selectors(novel_chapter_structure: dict):
    """渲染小说和章节选择器"""
    novels = sorted(novel_chapter_structure.keys())
    if not novels: return None, None

    # 选择小说
    selected_novel = _render_selectbox("📚 选择小说", novels, "selected_novel",
                                       reset_keys=["selected_chapter", "selected_model", "selected_schema",
                                                   "selected_params_key"])
    if not selected_novel: return None, None

    # 选择章节
    chapters = novel_chapter_structure.get(selected_novel, [])
    if not chapters:
        st.info("该小说没有可用的章节图谱。")
        return selected_novel, None

    selected_chapter = _render_selectbox("📄 选择章节", chapters, "selected_chapter",
                                         reset_keys=["selected_model", "selected_schema", "selected_params_key"])

    return selected_novel, selected_chapter


def _render_final_selection_button(selected_info: dict):
    """渲染最终选择图谱的按钮"""
    if selected_info and "cache_key" in selected_info:
        cache_key = selected_info["cache_key"]
        if cache_key:
            st.markdown("---")
            if st.button("🎯 确认选择此图谱", type="primary", use_container_width=True):
                st.query_params["cache_key"] = cache_key
                st.rerun()
        else:
            st.error("选中的图谱缓存键无效。")
    # 即使信息不全，也允许用户重新选择，不显示警告


# --- 主函数 ---

def render_multi_level_graph_selector(cache_dir: str):
    """渲染多层次图谱选择器 - 使用分层筛选器 (高度简化版)"""

    # 1. 获取结构和数据
    structure = _get_novel_chapter_structure(cache_dir)
    if not structure:
        st.info("缓存目录中未找到可用的知识图谱。")
        return

    # 2. 渲染小说和章节选择器
    novel, chapter = _render_novel_chapter_selectors(structure)
    if not novel or not chapter: return

    # 3. 过滤并提取选项
    filtered = _get_filtered_graphs(cache_dir, novel, chapter)
    if not filtered:
        st.info("没有找到匹配的图谱。")
        return

    models, schemas, params = _extract_options(filtered)

    # 4. 渲染模型选择器
    model = _render_selectbox("🤖 选择模型", models, "selected_model",
                              reset_keys=["selected_schema", "selected_params_key"])
    if not model: return

    # 5. 渲染模式选择器
    schema_opts = sorted(list({s for m, s in schemas if m == model}))
    schema = _render_selectbox("🧠 选择图谱模式", schema_opts, "selected_schema",
                               reset_keys=["selected_params_key"])
    if not schema: return

    # 6. 渲染参数选择器
    param_opts = _get_options_for_model_and_schema(params, model, schema)
    param_display = _render_selectbox("⚙️ 选择技术参数", param_opts, "selected_params_key")
    if not param_display: return

    # 7. 渲染最终选择按钮
    selected_info = _get_selected_info(params, model, schema, param_display)
    _render_final_selection_button(selected_info)


# ==============================
# 侧边栏面板
# ==============================

def render_control_panel(cache_dir: str):
    """渲染控制面板"""
    with st.expander("📊 控制面板", expanded=True):
        cache_key = st.query_params.get("cache_key", "")

        # 渲染多层次图谱选择器
        render_multi_level_graph_selector(cache_dir)

        # --- 删除按钮 ---
        if cache_key:
            data_file_path = os.path.join(cache_dir, f"{cache_key}.json")
            metadata_file_path = os.path.join(cache_dir, f"{cache_key}_metadata.json")

            # 检查文件是否存在
            if os.path.exists(data_file_path) or os.path.exists(metadata_file_path):
                st.markdown("**危险操作**: 删除当前选中的图谱数据")

                # 使用警告确认框来防止误删
                if st.button(f"🗑️ 确认删除 (缓存键: {cache_key[:16]}...)", type="secondary", use_container_width=True):
                    # 调用独立的删除函数
                    deletion_performed = delete_selected_graph(cache_dir, cache_key)

                    if deletion_performed:
                        # 删除成功后，清除 URL 中的 cache_key 参数并刷新
                        st.query_params.pop("cache_key", None)
                        st.rerun()
            else:
                st.info("当前选中的图谱数据文件不存在，可能已被删除。")
        # --- 删除按钮结束 ---

        col_max_nodes, col_max_edges = st.columns([1, 1])
        with col_max_nodes:
            max_nodes = st.number_input(
                "最大节点数",
                min_value=1,
                max_value=2000,
                value=int(st.query_params.get("max_nodes", 1000)),
                step=100,
                key="sb_max_nodes"
            )
        with col_max_edges:
            max_edges = st.number_input(
                "最大边数",
                min_value=1,
                max_value=2000,
                value=int(st.query_params.get("max_edges", 1000)),
                step=100,
                key="sb_max_edges"
            )

        # 物理效果控制
        physics_enabled = st.checkbox(
            "启用物理效果",
            value=st.query_params.get("physics", "true").lower() == "true",
            key="sb_physics"
        )

        if st.button("🔄 应用设置", type="primary", use_container_width=True):
            st.query_params["max_nodes"] = str(max_nodes)
            st.query_params["max_edges"] = str(max_edges)
            st.rerun()


def render_statistics_panel():
    """渲染统计信息面板 (仅显示元数据和统计数据)"""
    with st.expander("📈 统计信息", expanded=True):
        cache_key = st.query_params.get("cache_key", "")

        # 显示元数据信息
        if cache_key:
            try:
                metadata = get_metadata_from_cache_key(cache_key)

                st.markdown("**📋 分析报告元数据**")
                st.markdown(f"**小说名称:** {metadata.get('novel_name', '未知')}")
                st.markdown(f"**章节名称:** {metadata.get('chapter_name', '未知')}")
                st.markdown(f"**图谱模式:** {metadata.get('schema_name', '未知')}")

                # 创建两列表格样式显示元数据
                col1, col2 = st.columns([1, 1])
                with col1:
                    st.markdown(f"**模型:** {metadata.get('model_name', '未知')}")
                with col2:
                    st.markdown(f"**上下文:** {metadata.get('num_ctx', '未知')}")

                col1, col2 = st.columns([1, 1])
                with col1:
                    st.markdown(f"**分块大小:** {metadata.get('chunk_size', '未知')}")
                with col2:
                    st.markdown(f"**重叠:** {metadata.get('chunk_overlap', '未知')}")

                col1, col2 = st.columns([1, 1])
                with col1:
                    st.markdown(f"**内容大小:** {metadata.get('content_size', '未知')}")
                with col2:
                    st.markdown(f"**创建时间:** {metadata.get('created_at', '未知')}")

            except Exception as e:
                st.warning(f"无法加载元数据: {e}")
        else:
            st.info("暂无元数据信息")

        with st.spinner("加载中..."):
            graph_doc = load_cache(st.query_params.get("cache_key", ""))

        if graph_doc is not None:
            if isinstance(graph_doc, dict):
                nodes: List[Any] = graph_doc.get('nodes', [])
                relationships: List[Any] = graph_doc.get('relationships', [])
            else:
                nodes = getattr(graph_doc, 'nodes', [])
                relationships = getattr(graph_doc, 'relationships', [])

            # 显示统计信息
            st.markdown("**📊 图谱统计**")
            col1, col2 = st.columns([1, 1])
            with col1:
                st.text(f"节点数量:{len(nodes)}")
            with col2:
                st.text(f"关系数量:{len(relationships)}")

            # 注意：这里不再显示 "文字版图谱" 和 "章节原文"
            # 这些将由 sidebar 中的其他函数处理

        else:
            st.error("❌ 未找到数据")

def render_textual_graph_view():
    """渲染文字版图谱视图"""
    cache_key = st.query_params.get("cache_key", "")
    if not cache_key:
        return

    with st.expander("📝 文字版图谱", expanded=False):
        with st.spinner("正在加载图谱数据..."):
            graph_doc = load_cache(cache_key)

        if graph_doc is not None:
            if isinstance(graph_doc, dict):
                nodes: List[Any] = graph_doc.get('nodes', [])
                relationships: List[Any] = graph_doc.get('relationships', [])
            else:
                nodes = getattr(graph_doc, 'nodes', [])
                relationships = getattr(graph_doc, 'relationships', [])

            # 获取隐藏的节点类型
            hidden_types_str = st.session_state.get("hidden_node_types", "")
            hidden_node_types = set(hidden_types_str.split(",")) if hidden_types_str else set()

            graph_text = format_graph_text(nodes, relationships, hidden_node_types)
            st.text_area(
                "图谱内容",
                value=graph_text,
                height=300,
                key="graph_text_display_separate", # 使用不同的 key 避免冲突
                disabled=True
            )
        else:
            st.info("暂无图谱数据可显示。")


def render_chapter_text_view():
    """渲染章节原文视图 (自动执行基础清洁并优化显示)"""
    cache_key = st.query_params.get("cache_key", "")
    if not cache_key:
        return

    # 尝试从缓存元数据获取小说名和章节名
    novel_name = None
    chapter_name = None
    chapter_filename = None

    try:
        metadata = get_metadata_from_cache_key(cache_key)
        novel_name = metadata.get('novel_name')
        chapter_name = metadata.get('chapter_name')

        if not novel_name or not chapter_name:
            logger.info("元数据中缺少小说名或章节名，跳过章节原文加载。")
            return

        # --- 查找章节文件名 ---
        all_chapters_for_novel = utils_chapter.get_chapter_list(novel_name)
        for fname in all_chapters_for_novel:
            fname_no_ext = os.path.splitext(fname)[0]
            if chapter_name == fname_no_ext:
                chapter_filename = fname
                break

        if not chapter_filename:
            for fname in all_chapters_for_novel:
                fname_no_ext = os.path.splitext(fname)[0]
                if chapter_name in fname_no_ext:
                    chapter_filename = fname
                    logger.info(f"使用模糊匹配找到章节文件: {chapter_filename} 匹配 '{chapter_name}'")
                    break

        if not chapter_filename:
            logger.warning(f"未在章节列表中匹配到 '{chapter_name}'。")
            chapter_filename = f"{chapter_name}.txt"

    except Exception as e:
        logger.error(f"获取章节文件名时出错: {e}")
        return

    # --- 新增：优化文本显示的辅助函数 (用于最终显示微调) ---
    def post_process_for_display(text: str) -> str:
        """
        对已清洗的文本进行最终显示优化。
        主要目标是减少视觉上过多的空行。
        """
        if not text:
            return ""
        # 1. 移除文本开头和结尾的多余空行
        text = text.strip()

        # 2. 将多个连续的空行 (\n\s*\n\s*\n...) 替换为单个空行 (\n\n)
        #    这一步是为了应对即使经过 clean_chapter_text 后仍可能存在的情况
        #    例如，原文本中可能有 "\n\n\n段落" 或 "段落\n\n\n段落"
        #    这会变成 "段落\n\n段落"
        text = re.sub(r'\n\s*\n\s*\n+', '\n\n', text)

        # 3. (可选) 如果仍然觉得空行太多，可以进一步减少
        #    例如，将所有双空行变为单空行
        # text = re.sub(r'\n\n', '\n', text)

        return text

    # --- 新增结束 ---

    with st.expander("📄 章节原文", expanded=False):
        with st.spinner("正在加载章节原文..."):
            try:
                # --- 关键修改：调用 chapter_utils 加载并自动清洗内容 ---
                # chapter_utils.load_chapter_content 默认 clean=True
                # 因此，它会自动调用 chapter_utils.clean_chapter_text
                chapter_content, load_success = utils_chapter.load_chapter_content(
                    novel_name, chapter_filename, clean=True  # 明确指定 clean=True (虽然是默认值)
                )
                # --- 关键修改结束 ---

                if load_success:
                    # --- 新增：应用最终显示优化 ---
                    final_chapter_content = post_process_for_display(chapter_content)
                    # --- 新增结束 ---

                    max_chars_to_display = 15000
                    display_text = final_chapter_content
                    truncated = False
                    if len(final_chapter_content) > max_chars_to_display:
                        display_text = final_chapter_content[:max_chars_to_display] + "\n\n... (内容过长，已截断) ..."
                        truncated = True

                    st.text_area(
                        "章节原文内容",
                        value=display_text,
                        height=500,
                        key="chapter_text_display_separate",
                        disabled=True
                    )
                    if truncated:
                        st.info(f"原文内容较长，仅显示前 {max_chars_to_display} 个字符。")

                else:
                    st.error(f"章节内容加载失败: {chapter_content}")

            except Exception as load_e:
                error_msg = f"加载章节原文时发生未知错误: {load_e}"
                logger.error(error_msg, exc_info=True)
                st.error(error_msg)



def render_node_type_control_panel():
    """渲染节点类型控制面板"""
    with st.expander("🎨 节点类型控制", expanded=True):
        # 显示颜色图例和控制开关
        display_color_legend_and_controls()


def render_help_panel():
    """渲染帮助面板"""
    with st.expander("💡 帮助", expanded=False):
        st.markdown("""
        **如何使用:**
        - 通过 Gradio 应用分析文本获取链接。
        - 在侧边栏调整显示参数。
        - 点击"应用设置"刷新图谱。
        - 在图谱中拖拽节点和视图进行交互。
        - 使用"节点类型控制"可以显示/隐藏特定类型的节点。

        **提示:**
        - 关闭物理效果可提高大型图谱的性能。
        - 减少显示的节点和边数可提高加载速度。
        - 节点始终按原文顺序排列展示。
        - 节点标签格式为"序号:节点名称"，便于识别节点顺序。
        - 点击类别名称可以展开/收起该类别的节点类型控制。
        - 在每个展开的类别中选择要显示的节点类型。
        - 更改选择后，点击"刷新图谱"按钮更新显示。
        - 在"统计信息"中可以查看文字版的图谱内容。
        - "📚 可用图谱"按钮显示技术参数：块大小、重叠、内容大小。
        """)


def render_sidebar():
    """渲染侧边栏控制面板"""
    with st.sidebar:
        # 1. 控制面板
        render_control_panel(CACHE_DIR)

        # 2. 统计信息 (元数据和统计数据)
        render_statistics_panel()

        # 3. 文字版图谱视图 (新增)
        render_textual_graph_view()

        # 4. 章节原文视图 (新增)
        render_chapter_text_view()

        # 5. 节点类型控制
        render_node_type_control_panel()

        # 6. 帮助
        render_help_panel()


# ==============================
# 主内容区域
# ==============================

def render_main_content():
    """渲染主内容区域"""
    cache_key = st.query_params.get("cache_key", "")

    if not cache_key:
        # 如果没有缓存键，显示引导信息
        st.title("📖 小说叙事图谱查看器")
        st.header("⚠️ 缺少缓存键")
        st.markdown(
            "请通过 Gradio 应用分析文本后，使用生成的链接来查看图谱。"
        )
        st.code("http://localhost:8501/?cache_key=your_cache_key_here")
        return

    # 加载和显示图谱
    try:
        with st.spinner("正在从缓存加载图谱数据..."):
            graph_doc = load_cache(cache_key)

        if graph_doc is None:
            st.markdown("---")
            st.error("❌ 未找到对应的图谱数据")
            st.info("请确保 Gradio 应用和此应用使用相同的缓存目录，并且缓存未过期。")
            return

        # 获取当前参数
        current_max_nodes = int(st.query_params.get("max_nodes", 1000))
        current_max_edges = int(st.query_params.get("max_edges", 1000))
        current_physics_enabled = st.query_params.get("physics", "true").lower() == "true"

        # 获取隐藏的节点类型
        hidden_types_str = st.session_state.get("hidden_node_types", "")
        hidden_node_types = set(hidden_types_str.split(",")) if hidden_types_str else set()

        # 生成图谱 HTML
        visualizer = GraphVisualizer()
        graph_html = visualizer.generate_html(
            graph_doc,
            max_nodes=current_max_nodes,
            max_edges=current_max_edges,
            physics_enabled=current_physics_enabled,
            hidden_node_types=hidden_node_types
        )

        # 显示图谱
        if "可视化失败" not in graph_html:
            st.components.v1.html(graph_html, height=1150, scrolling=False)
        else:
            st.error(graph_html)

    except Exception as e:
        logger.error(f"加载图谱失败: {e}", exc_info=True)
        st.markdown("---")
        st.error("❌ 加载图谱失败")
        st.write(str(e))


# ==============================
# 主函数
# ==============================

def main():
    """Streamlit 应用主函数"""
    # 获取缓存键以设置页面标题
    cache_key = st.query_params.get("cache_key", "")

    # 设置默认页面标题
    page_title = "📖 小说叙事图谱查看器"

    # 如果有缓存键，尝试加载元数据来设置更详细的标题
    if cache_key:
        try:
            metadata = get_metadata_from_cache_key(cache_key)

            novel_name = metadata.get("novel_name", "未知小说")
            chapter_name = metadata.get("chapter_name", "未知章节")
            model_name = metadata.get("model_name", "未知模型")
            chunk_size = metadata.get("chunk_size", "未知")
            chunk_overlap = metadata.get("chunk_overlap", "未知")
            content_size = metadata.get("content_size", "未知")
            schema_name = metadata.get("schema_name", "未知模式")

            # 创建详细的页面标题
            page_title = f"📖 {novel_name} - {chapter_name} ({schema_name})"
        except Exception as e:
            logger.warning(f"获取元数据失败: {e}")
            # 使用简化版本的标题
            page_title = f"{cache_key[:16]}..."

    st.set_page_config(layout="wide", page_title=page_title)

    # 初始化session_state
    if "hidden_node_types" not in st.session_state:
        st.session_state["hidden_node_types"] = ""

    # 初始化小说和章节选择状态
    if "selected_novel" not in st.session_state:
        st.session_state["selected_novel"] = None
    if "selected_chapter" not in st.session_state:
        st.session_state["selected_chapter"] = None

    render_sidebar()
    render_main_content()


if __name__ == "__main__":
    main()