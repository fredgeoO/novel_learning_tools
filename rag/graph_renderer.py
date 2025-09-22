# rag/graph_renderer.py
"""
知识图谱渲染核心逻辑
负责将图谱数据转换为可视化格式
"""

import os
import logging
import json
import glob
import uuid
from typing import Any, Dict, List, Union, Set
from pyvis.network import Network
from datetime import datetime
import colorsys

# 本地导入
from rag.color_schema import NODE_COLOR_MAP, EDGE_COLOR_MAP
from rag.graph_manager import load_available_graphs_metadata

# --- 配置 ---
logger = logging.getLogger(__name__)
_color_cache: Dict[str, str] = {}


def simple_hash(text: str) -> int:
    """简单字符串哈希函数"""
    hash_value = 0
    for char in text:
        hash_value = (hash_value * 31 + ord(char)) & 0x7FFFFFFF
    return hash_value


def generate_color_from_string(text: str) -> str:
    """根据字符串生成稳定的中等亮度颜色"""
    # 检查缓存
    if text in _color_cache:
        return _color_cache[text]

    # 使用哈希值生成RGB值
    hash_value = simple_hash(text)
    r = (hash_value >> 16) & 0xFF
    g = (hash_value >> 8) & 0xFF
    b = hash_value & 0xFF

    # 转换为HSV调整亮度和饱和度
    h, s, v = colorsys.rgb_to_hsv(r / 255.0, g / 255.0, b / 255.0)
    s = 0.6 + (s * 0.4)  # 饱和度范围 0.6-1.0
    v = 0.4 + (v * 0.4)  # 亮度范围 0.4-0.8
    r, g, b = colorsys.hsv_to_rgb(h, s, v)

    # 转换为十六进制颜色
    color = f"#{int(r * 255):02x}{int(g * 255):02x}{int(b * 255):02x}"
    _color_cache[text] = color
    return color


class GraphVisualizer:
    """小说叙事图谱可视化器"""

    def __init__(self):
        self.net = None

    def _ensure_sequence_numbers(self, nodes: List[Any]) -> None:
        """为没有sequence_number的节点分配默认序号"""
        for i, node_data in enumerate(nodes):
            # 统一处理字典和对象格式
            if isinstance(node_data, dict):
                properties = node_data.setdefault('properties', {})
            else:
                if not hasattr(node_data, 'properties') or node_data.properties is None:
                    node_data.properties = {}
                properties = node_data.properties

            # 确保有sequence_number
            if 'sequence_number' not in properties:
                properties['sequence_number'] = i + 1

    def _sort_nodes_by_sequence(self, nodes: List[Any]) -> List[Any]:
        """按sequence_number对节点进行排序"""

        def get_sequence_number(node):
            if isinstance(node, dict):
                properties = node.get('properties', {})
            else:
                properties = getattr(node, 'properties', {})
            return properties.get('sequence_number', float('inf'))

        return sorted(nodes, key=get_sequence_number)

    def _create_network(self, bgcolor: str = "#1e1e1e", font_color: str = "$ffffff") -> Network:
        """创建PyVis网络对象"""
        net =  Network(
            height="100%",
            width="100%",
            bgcolor=bgcolor,
            font_color=font_color,  # ✅ 明确指定白色字体
            directed=True,
            notebook=True,
            cdn_resources='in_line'
        )

        return net

    def _get_node_display_name(self, node_id: str, node_type: str, properties: Dict) -> str:
        """获取节点的显示名称"""
        # 优先使用名称属性
        name_fields = ['name']
        if node_type == "人物":
            name_fields.extend(['姓名', '名字', '角色'])
        elif node_type == "地点":
            name_fields.extend(['地点', '位置', '地址'])

        for field in name_fields:
            if field in properties and properties[field]:
                return str(properties[field])

        # 默认返回节点ID
        return f"{node_id[:20]}{'...' if len(node_id) > 20 else ''}"

    def _add_nodes_to_network(self, net: Network, nodes: List[Any], max_nodes: int,
                              hidden_node_types: Set[str]) -> None:
        """向网络中添加节点"""
        for i, node_data in enumerate(nodes[:max_nodes]):
            # 统一处理节点数据
            if isinstance(node_data, dict):
                node_id = str(node_data.get('id', ''))
                node_type = node_data.get('type', '未知')
                properties = node_data.get('properties', {})
            else:
                node_id = str(getattr(node_data, 'id', ''))
                node_type = getattr(node_data, 'type', '未知')
                properties = getattr(node_data, 'properties', {})

            # 跳过无效或隐藏节点
            if not node_id or node_type in hidden_node_types:
                continue

            # 构造显示标签和悬停信息
            display_name = self._get_node_display_name(node_id, node_type, properties)
            sequence_number = properties.get('sequence_number', i + 1)
            label = f"{sequence_number}:{display_name}"

            title = f"{node_type} ({node_id})"
            if properties:
                title += "\n属性:" + "\n".join([
                    f"{k}: {v}" for k, v in list(properties.items())[:5]
                ])
                if len(properties) > 5:
                    title += "\n..."

            # 获取节点颜色
            node_color = NODE_COLOR_MAP.get(node_type) or generate_color_from_string(node_type)

            # 添加节点
            net.add_node(
                node_id,
                label=label,
                title=title,
                color=node_color,
                size=25,
            )

    def _add_edges_to_network(self, net: Network, relationships: List[Any],
                              nodes: List[Any], max_edges: int,
                              hidden_node_types: Set[str]) -> None:
        """向网络中添加边"""
        # 创建可见节点集合
        visible_node_ids = set()
        for node in nodes:
            if isinstance(node, dict):
                node_type, node_id = node.get('type', '未知'), str(node.get('id', ''))
            else:
                node_type, node_id = getattr(node, 'type', '未知'), str(getattr(node, 'id', ''))

            if node_type not in hidden_node_types:
                visible_node_ids.add(node_id)

        # 添加边
        existing_node_ids = {str(getattr(n, 'id', str(n.get('id', '')))) for n in nodes}

        for rel_data in relationships[:max_edges]:
            # 处理关系数据
            if isinstance(rel_data, dict):
                source_id = str(rel_data.get('source_id', ''))
                target_id = str(rel_data.get('target_id', ''))
                rel_type = rel_data.get('type', '未知关系')
                properties = rel_data.get('properties', {})
            else:
                source_id = str(getattr(rel_data, 'source_id', ''))
                target_id = str(getattr(rel_data, 'target_id', ''))
                rel_type = getattr(rel_data, 'type', '未知关系')
                properties = getattr(rel_data, 'properties', {})

            # 只添加有效且可见的边
            if (source_id and target_id and
                    source_id in existing_node_ids and target_id in existing_node_ids and
                    source_id in visible_node_ids and target_id in visible_node_ids):

                # 构造边悬停信息
                title = rel_type
                if properties:
                    title += "\n属性:" + "\n".join([
                        f"{k}: {v}" for k, v in list(properties.items())[:5]
                    ])
                    if len(properties) > 5:
                        title += "\n..."

                # 获取边颜色
                edge_color = EDGE_COLOR_MAP.get(rel_type) or generate_color_from_string(rel_type)

                # 添加边
                net.add_edge(
                    source_id,
                    target_id,
                    title=title,
                    arrows='to',
                    color=edge_color,
                    width=2
                )

    def _configure_physics(self, net: Network, physics_enabled: bool) -> None:
        """配置网络物理效果（暂时禁用避免问题）"""
        pass

    def generate_html(self, graph_doc: Union[Dict, Any], max_nodes: int = 1000,
                      max_edges: int = 1000, physics_enabled: bool = True,
                      hidden_node_types: Set[str] = None) -> str:
        """从graph_doc对象生成PyVis HTML"""
        if hidden_node_types is None:
            hidden_node_types = set()

        try:
            # 1. 数据加载和检查
            if isinstance(graph_doc, dict):
                nodes = graph_doc.get('nodes', [])
                relationships = graph_doc.get('relationships', [])
            else:
                if not graph_doc or not hasattr(graph_doc, 'nodes') or not hasattr(graph_doc, 'relationships'):
                    logger.error("无效的图谱数据：缺少 nodes 或 relationships")
                    return self._get_error_html("无效的图谱数据 (缺少 nodes 或 relationships 属性)")
                nodes = getattr(graph_doc, 'nodes', [])
                relationships = getattr(graph_doc, 'relationships', [])

            if not nodes:
                logger.info("图谱数据中没有节点")
                return self._get_empty_html()

            logger.info(f"开始可视化，总节点数: {len(nodes)}, 总关系数: {len(relationships)}")

            # 2. 数据预处理
            self._ensure_sequence_numbers(nodes)
            nodes = self._sort_nodes_by_sequence(nodes)
            logger.info("节点已按sequence_number排序")

            # 3. 创建网络并添加元素
            self.net = self._create_network()
            self._add_nodes_to_network(self.net, nodes, max_nodes, hidden_node_types)
            self._add_edges_to_network(self.net, relationships, nodes, max_edges, hidden_node_types)
            self._configure_physics(self.net, physics_enabled)

            # 4. 生成HTML并清理
            logger.info("正在调用 net.generate_html()...")
            html_content = self.net.generate_html()

            # 使用BeautifulSoup清理HTML
            # 简单直接的清理方法
            try:
                from bs4 import BeautifulSoup
                soup = BeautifulSoup(html_content, 'html.parser')

                # 删除h1标签
                for h1 in soup.find_all('h1'):
                    h1.decompose()

                # 移除所有class属性（这样可以彻底消除Bootstrap影响）
                for element in soup.find_all():
                    if element.get('class'):
                        del element['class']

                html_content = str(soup)
            except Exception as e:
                logger.warning(f"HTML清理失败: {e}")

            return html_content

        except Exception as e:
            logger.error(f"PyVis 可视化失败: {e}", exc_info=True)
            return self._get_error_html(f"可视化失败: {e}")

    def _get_error_html(self, message: str) -> str:
        """生成错误信息HTML"""
        return f"<div style='text-align: center; padding: 20px; color: red; font-family: Arial, sans-serif; background-color: #1e1e1e; border-radius: 8px;'>可视化失败：{message}</div>"

    def _get_empty_html(self) -> str:
        """生成空数据HTML"""
        return "<div style='text-align: center; padding: 50px; color: #aaaaaa; font-family: Arial, sans-serif; background-color: #1e1e1e; border-radius: 8px;'>📊 暂无图谱数据可显示</div>"

    def generate_graph_data(self, graph_doc: Union[Dict, Any], max_nodes: int = 1000,
                            max_edges: int = 1000, hidden_node_types: Set[str] = None) -> Dict:
        """新增：只生成图数据结构，用于前端渲染"""
        if hidden_node_types is None:
            hidden_node_types = set()

        try:
            # 数据加载和检查
            if isinstance(graph_doc, dict):
                nodes = graph_doc.get('nodes', [])
                relationships = graph_doc.get('relationships', [])
            else:
                nodes = getattr(graph_doc, 'nodes', [])
                relationships = getattr(graph_doc, 'relationships', [])

            if not nodes:
                return {'nodes': [], 'edges': []}

            # 数据预处理
            self._ensure_sequence_numbers(nodes)
            nodes = self._sort_nodes_by_sequence(nodes)

            # 转换节点数据
            processed_nodes = []
            visible_nodes = set()

            for i, node_data in enumerate(nodes[:max_nodes]):
                if isinstance(node_data, dict):
                    node_id = str(node_data.get('id', ''))
                    node_type = node_data.get('type', '未知')
                    properties = node_data.get('properties', {})
                else:
                    node_id = str(getattr(node_data, 'id', ''))
                    node_type = getattr(node_data, 'type', '未知')
                    properties = getattr(node_data, 'properties', {})

                if not node_id or node_type in hidden_node_types:
                    continue

                display_name = self._get_node_display_name(node_id, node_type, properties)
                sequence_number = properties.get('sequence_number', i + 1)
                label = f"{sequence_number}:{display_name}"

                title = f"{node_type} ({node_id})"
                if properties:
                    title += "\n属性:" + "\n".join([
                        f"{k}: {v}" for k, v in list(properties.items())[:5]
                    ])

                node_color = NODE_COLOR_MAP.get(node_type) or generate_color_from_string(node_type)

                processed_nodes.append({
                    'id': node_id,
                    'label': label,
                    'title': title,
                    'color': node_color,
                    'size': 25
                })
                visible_nodes.add(node_id)

            # 转换边数据 - 关键修复：使用 edges 而不是 relationships
            processed_edges = []  # 这里改为 edges
            existing_node_ids = {str(getattr(n, 'id', str(n.get('id', '')))) for n in nodes}

            for rel_data in relationships[:max_edges]:
                if isinstance(rel_data, dict):
                    source_id = str(rel_data.get('source_id', ''))
                    target_id = str(rel_data.get('target_id', ''))
                    rel_type = rel_data.get('type', '未知关系')
                    properties = rel_data.get('properties', {})
                else:
                    source_id = str(getattr(rel_data, 'source_id', ''))
                    target_id = str(getattr(rel_data, 'target_id', ''))
                    rel_type = getattr(rel_data, 'type', '未知关系')
                    properties = getattr(rel_data, 'properties', {})

                if (source_id and target_id and
                        source_id in existing_node_ids and target_id in existing_node_ids and
                        source_id in visible_nodes and target_id in visible_nodes):

                    title = rel_type
                    if properties:
                        title += "\n属性:" + "\n".join([
                            f"{k}: {v}" for k, v in list(properties.items())[:5]
                        ])

                    edge_color = EDGE_COLOR_MAP.get(rel_type) or generate_color_from_string(rel_type)

                    # 关键修复：使用 label 而不是 title 作为边的显示文本
                    processed_edges.append({
                        'from': source_id,
                        'to': target_id,
                        'label': rel_type,  # 使用 label 字段
                        'title': title,  # 保留 title 作为悬停信息
                        'arrows': 'to',
                        'color': edge_color,
                        'width': 2
                    })

            # 返回正确的数据结构：nodes 和 edges
            return {
                'nodes': processed_nodes,
                'edges': processed_edges  # 这里是 edges，不是 relationships
            }

        except Exception as e:
            logger.error(f"生成图数据失败: {e}", exc_info=True)
            return {'nodes': [], 'edges': []}  # 确保返回 edges



def format_graph_text(nodes: List[Any], relationships: List[Any], hidden_node_types: Set[str]) -> str:
    """格式化图谱为文字版"""
    if not nodes:
        return "暂无图谱数据"

    # 创建可见节点映射
    node_info = {}
    visible_nodes = set()

    for i, node_data in enumerate(nodes):
        if isinstance(node_data, dict):
            node_id = str(node_data.get('id', ''))
            node_type = node_data.get('type', '未知')
            properties = node_data.get('properties', {})
        else:
            node_id = str(getattr(node_data, 'id', ''))
            node_type = getattr(node_data, 'type', '未知')
            properties = getattr(node_data, 'properties', {})

        if node_type not in hidden_node_types:
            node_info[node_id] = {
                'id': node_id,
                'type': node_type,
                'seq': properties.get('sequence_number', i + 1),
                'properties': properties
            }
            visible_nodes.add(node_id)

    if not visible_nodes:
        return "当前筛选条件下无可见节点"

    # 格式化节点列表
    result = ["=== 节点列表 ==="]
    sorted_nodes = sorted(visible_nodes, key=lambda x: node_info[x]['seq'])

    for node_id in sorted_nodes:
        info = node_info[node_id]
        display_name = _get_node_display_name_for_text(info['id'], info['type'], info['properties'])
        line = f"[{info['seq']}] {display_name} ({info['type']})"

        # 添加重要属性
        important_props = []
        for prop in ['description', 'role', 'location']:
            if prop in info['properties']:
                important_props.append(f"{prop}: {info['properties'][prop]}")

        if important_props:
            line += " | " + ", ".join(important_props)
        result.append(line)

    # 格式化关系列表
    result.append(f"\n=== 关系列表 (共{len(relationships)}条) ===")

    visible_relationships = [
        (str(rel.get('source_id') if isinstance(rel, dict) else getattr(rel, 'source_id', '')),
         str(rel.get('target_id') if isinstance(rel, dict) else getattr(rel, 'target_id', '')),
         rel.get('type') if isinstance(rel, dict) else getattr(rel, 'type', '未知关系'),
         rel)
        for rel in relationships
        if (str(rel.get('source_id') if isinstance(rel, dict) else getattr(rel, 'source_id', '')) in visible_nodes and
            str(rel.get('target_id') if isinstance(rel, dict) else getattr(rel, 'target_id', '')) in visible_nodes)
    ]

    for source_id, target_id, rel_type, rel_data in visible_relationships:
        source_name = _get_node_display_name_for_text(
            source_id, node_info[source_id]['type'], node_info[source_id]['properties'])
        target_name = _get_node_display_name_for_text(
            target_id, node_info[target_id]['type'], node_info[target_id]['properties'])
        line = f"{source_name} --({rel_type})--> {target_name}"

        # 添加关系属性
        properties = (rel_data.get('properties', {}) if isinstance(rel_data, dict)
                      else getattr(rel_data, 'properties', {}))
        if properties:
            prop_items = [f"{k}: {v}" for k, v in list(properties.items())[:3]]
            if prop_items:
                line += " | 属性: " + ", ".join(prop_items)
        result.append(line)

    return "\n".join(result)


def _get_node_display_name_for_text(node_id: str, node_type: str, properties: Dict) -> str:
    """获取节点的显示名称（用于文本显示）"""
    # 优先使用名称属性
    name_fields = ['name']
    if node_type == "人物":
        name_fields.extend(['姓名', '名字', '角色'])
    elif node_type == "地点":
        name_fields.extend(['地点', '位置', '地址'])

    for field in name_fields:
        if field in properties and properties[field]:
            return str(properties[field])

    # 默认返回节点ID
    return f"{node_id[:20]}{'...' if len(node_id) > 20 else ''}"


