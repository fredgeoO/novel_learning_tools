# rag/graph_types.py
"""定义图谱相关的数据结构和模型。"""

import json
import logging
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field
from pydantic import BaseModel, Field

# --- 配置日志 (如果需要在这个模块内记录日志) ---
logger = logging.getLogger(__name__)


# ==============================
# 可序列化的 Graph Document 类
# ==============================


class ReconnectionSuggestion(BaseModel):
    target_node_id: str
    relationship_type: str

class ReconnectionResponse(BaseModel):
    suggestions: List[ReconnectionSuggestion]

@dataclass
@dataclass
class SerializableNode:
    """可序列化的图节点。"""
    id: str
    type: str
    properties: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_langchain_node(cls, node):
        """从 LangChain 节点创建可序列化节点"""
        node_id = getattr(node, 'id', '')
        node_type = getattr(node, 'type', '')
        node_properties = getattr(node, 'properties', {})
        return cls(id=node_id, type=node_type, properties=node_properties)

    def to_dict(self) -> Dict[str, Any]:
        """将节点序列化为标准字典（用于内部存储）。"""
        return {
            'id': self.id,
            'type': self.type,
            'properties': self.properties
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'SerializableNode':
        """从标准字典反序列化为节点（用于内部存储）。"""
        node_id = data.get('id', '')
        node_type = data.get('type', '')
        node_properties = data.get('properties', {})
        return cls(id=node_id, type=node_type, properties=node_properties)

    # --- 新增：Vis.js 格式支持 ---

    def to_vis_dict(self) -> Dict[str, Any]:
        """将节点序列化为 Vis.js 兼容的字典。"""
        vis_node = {
            'id': self.id,
            # 使用 id 作为默认 label，如果 properties 中有 label 则优先使用
            'label': self.properties.get('label', self.id),
            # 将原始节点数据保存在自定义属性中，方便后续转换回标准格式
            'originalData': self.to_dict()
        }
        # 将 properties 中的 Vis.js 相关属性复制到顶层
        # 例如 color, size, x, y 等
        vis_props = self.properties
        if 'color' in vis_props:
            vis_node['color'] = vis_props['color']
        if 'size' in vis_props:
            vis_node['size'] = vis_props['size']
        if 'x' in vis_props and vis_props['x'] is not None:
             # 确保是数字
            try:
                vis_node['x'] = float(vis_props['x'])
            except (ValueError, TypeError):
                pass # 如果转换失败，不添加 x
        if 'y' in vis_props and vis_props['y'] is not None:
            try:
                vis_node['y'] = float(vis_props['y'])
            except (ValueError, TypeError):
                pass # 如果转换失败，不添加 y
        # 可以根据需要添加更多 Vis.js 属性
        return vis_node

    @classmethod
    def from_vis_dict(cls, vis_data: Dict[str, Any]) -> 'SerializableNode':
        """从 Vis.js 兼容的字典反序列化为节点。"""
        # 尝试从 originalData 恢复原始格式
        original_data = vis_data.get('originalData')
        if original_data and isinstance(original_data, dict):
            return cls.from_dict(original_data)

        # 如果没有 originalData，则从 Vis.js 数据重建
        node_id = vis_data.get('id', '')
        # 尝试从 label 或 id 推断 type（这可能不准确，最好在 originalData 中）
        node_type = "未知类型"
        # properties 初始化
        node_properties = {}

        # 复制 Vis.js 属性到 properties
        vis_keys_to_copy = ['label', 'color', 'size', 'x', 'y']
        for key in vis_keys_to_copy:
            if key in vis_data:
                node_properties[key] = vis_data[key]

        return cls(id=node_id, type=node_type, properties=node_properties)



@dataclass
class SerializableRelationship:
    """可序列化的图关系。"""
    source_id: str
    target_id: str
    type: str
    properties: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_langchain_relationship(cls, rel):
        """从 LangChain 关系创建可序列化关系"""
        source_node = getattr(rel, 'source', None)
        target_node = getattr(rel, 'target', None)
        source_id = getattr(source_node, 'id', '') if source_node else ''
        target_id = getattr(target_node, 'id', '') if target_node else ''
        rel_type = getattr(rel, 'type', '')
        rel_properties = getattr(rel, 'properties', {})
        return cls(source_id=source_id, target_id=target_id, type=rel_type, properties=rel_properties)

    def to_dict(self) -> Dict[str, Any]:
        """将关系序列化为标准字典（用于内部存储）。"""
        return {
            'source_id': self.source_id,
            'target_id': self.target_id,
            'type': self.type,
            'properties': self.properties
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'SerializableRelationship':
        """从标准字典反序列化为关系（用于内部存储）。"""
        source_id = data.get('source_id', '')
        target_id = data.get('target_id', '')
        rel_type = data.get('type', '')
        rel_properties = data.get('properties', {})
        return cls(source_id=source_id, target_id=target_id, type=rel_type, properties=rel_properties)

    # --- 新增：Vis.js 格式支持 ---

    def to_vis_dict(self) -> Dict[str, Any]:
        """将关系序列化为 Vis.js 兼容的字典。"""
        # 生成一个唯一的边 ID，如果 properties 中没有
        edge_id = self.properties.get('id', f"edge_{self.source_id}_{self.target_id}")
        vis_edge = {
            'id': edge_id,
            'from': self.source_id,
            'to': self.target_id,
            # Vis.js 使用 'label' 显示边的文本
            'label': self.type,
            # 将原始关系数据保存在自定义属性中
            'originalData': self.to_dict()
        }
        # 将 properties 中的 Vis.js 相关属性复制到顶层
        vis_props = self.properties
        if 'color' in vis_props:
            # Vis.js 边颜色结构可能是字符串或对象 {'color': '#...'}
            color_val = vis_props['color']
            if isinstance(color_val, str):
                vis_edge['color'] = {'color': color_val}
            elif isinstance(color_val, dict):
                vis_edge['color'] = color_val
            else:
                vis_edge['color'] = {'color': '#666666'} # 默认颜色
        if 'width' in vis_props:
            vis_edge['width'] = vis_props['width']
        if 'arrows' in vis_props:
            vis_edge['arrows'] = vis_props['arrows']
        # title 通常用于悬停显示，可以使用 type 或 properties 中的 title
        if 'title' in vis_props:
            vis_edge['title'] = vis_props['title']
        else:
            vis_edge['title'] = self.type # 默认使用 type 作为 title

        return vis_edge

    @classmethod
    def from_vis_dict(cls, vis_data: Dict[str, Any]) -> 'SerializableRelationship':
        """从 Vis.js 兼容的字典反序列化为关系。"""
        # 尝试从 originalData 恢复原始格式
        original_data = vis_data.get('originalData')
        if original_data and isinstance(original_data, dict):
            return cls.from_dict(original_data)

        # 如果没有 originalData，则从 Vis.js 数据重建
        source_id = vis_data.get('from', '')
        target_id = vis_data.get('to', '')
        # Vis.js 使用 'label'，我们将其映射回 type
        rel_type = vis_data.get('label', '未知关系')
        rel_properties = {}

        # 复制 Vis.js 属性到 properties
        vis_keys_to_copy = ['id', 'label', 'title', 'width', 'arrows']
        for key in vis_keys_to_copy:
            if key in vis_data:
                rel_properties[key] = vis_data[key]

        # 特殊处理 color
        if 'color' in vis_data:
            color_data = vis_data['color']
            if isinstance(color_data, dict) and 'color' in color_data:
                rel_properties['color'] = color_data['color']
            elif isinstance(color_data, str):
                rel_properties['color'] = color_data

        return cls(source_id=source_id, target_id=target_id, type=rel_type, properties=rel_properties)



@dataclass
class SerializableGraphDocument:
    """可序列化的图文档。"""
    nodes: List[SerializableNode] = field(default_factory=list)
    relationships: List[SerializableRelationship] = field(default_factory=list)

    @classmethod
    def from_langchain_graph_document(cls, graph_doc) -> 'SerializableGraphDocument':
        """从 LangChain GraphDocument 创建可序列化版本"""
        lc_nodes = getattr(graph_doc, 'nodes', [])
        lc_relationships = getattr(graph_doc, 'relationships', [])
        nodes = [SerializableNode.from_langchain_node(n) for n in lc_nodes]
        relationships = [SerializableRelationship.from_langchain_relationship(r) for r in lc_relationships]
        return cls(nodes=nodes, relationships=relationships)

    def to_dict(self) -> Dict[str, Any]:
        """将图文档序列化为标准字典（用于内部存储）。"""
        return {
            'nodes': [node.to_dict() for node in self.nodes],
            'relationships': [rel.to_dict() for rel in self.relationships]
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'SerializableGraphDocument':
        """从标准字典反序列化为图文档（用于内部存储）。"""
        nodes_data = data.get('nodes', [])
        relationships_data = data.get('relationships', [])
        nodes = [SerializableNode.from_dict(node_data) for node_data in nodes_data]
        relationships = [SerializableRelationship.from_dict(rel_data) for rel_data in relationships_data]
        return cls(nodes=nodes, relationships=relationships)

    # --- 新增：Vis.js 格式支持 ---

    def to_vis_dict(self) -> Dict[str, Any]:
        """将图文档序列化为 Vis.js 兼容的字典。"""
        return {
            'nodes': [node.to_vis_dict() for node in self.nodes],
            'edges': [rel.to_vis_dict() for rel in self.relationships] # 注意：这里键名改为 'edges'
        }

    @classmethod
    def from_vis_dict(cls, vis_data: Dict[str, Any]) -> 'SerializableGraphDocument':
        """从 Vis.js 兼容的字典反序列化为图文档。"""
        nodes_data = vis_data.get('nodes', [])
        # 注意：这里键名是 'edges'
        edges_data = vis_data.get('edges', [])
        nodes = [SerializableNode.from_vis_dict(node_data) for node_data in nodes_data]
        relationships = [SerializableRelationship.from_vis_dict(edge_data) for edge_data in edges_data]
        return cls(nodes=nodes, relationships=relationships)

    # 如果你想让 to_dict/from_dict 直接输出/输入 Vis 格式，可以替换它们：
    # def to_dict(self) -> Dict[str, Any]:
    #     return self.to_vis_dict()
    # @classmethod
    # def from_dict(cls, data: Dict[str, Any]) -> 'SerializableGraphDocument':
    #     return cls.from_vis_dict(data)

    @staticmethod
    def display_graph_document(graph_doc: 'SerializableGraphDocument', title: str = "Graph Document"):
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
# Pydantic 模型 (用于 LLM 输出解析)
# ==============================

class GroupingResult(BaseModel):
    """单个语义分组结果，用于优化高连接度节点。"""
    # 聚合节点的名称，将用作新节点的 ID 和 name 属性
    group_name: str = Field(
        description="能概括该组节点共同主题的语义化名称（例如'童年经历'、'职场关系'）。这将用作新聚合节点的 ID 和 name 属性。"
    )
    # 属于该组的成员节点ID
    node_ids: List[str] = Field(
        description="属于该分组的成员节点的ID列表。"
    )
    # 主节点到聚合节点的关系类型
    aggregate_relationship_type: str = Field(
        description="描述原始主节点与这个新聚合概念之间关系的中文词语（如'涉及'、'拥有'、'经历'）。"
    )
    # 聚合节点到成员节点的关系类型
    member_relationship_type: str = Field(
        description="描述新聚合概念与其成员节点之间关系的中文词语（如'包含'、'成员是'、'体现为'）。"
    )
    # 注意：移除了 aggregate_node_id 和 description 字段


class AggregateGroupingResponse(BaseModel):
    """完整的分组响应结构"""
    groups: List[GroupingResult] = Field(description="所有分组结果")

# ==============================
# LLM 核心数据结构（简化版）
# ==============================

class LLMGraphRequest(BaseModel):
    """LLM图谱处理请求 - 输入数据结构"""
    node: Dict[str, Any] = Field(description="当前节点信息")
    prompt: str = Field(description="用户的扩展提示词")
    context_graph: Optional[Dict[str, Any]] = Field(default=None, description="上下文图谱信息（可选）")

class LLMGraphNode(BaseModel):
    """LLM生成的图节点"""
    id: str = Field(description="节点ID")
    type: str = Field(description="节点类型")
    properties: Dict[str, Any] = Field(default_factory=dict, description="节点属性")

class LLMGraphRelationship(BaseModel):
    """LLM生成的图关系"""
    source_id: str = Field(description="源节点ID")
    target_id: str = Field(description="目标节点ID")
    type: str = Field(description="关系类型")
    properties: Dict[str, Any] = Field(default_factory=dict, description="关系属性")

class LLMGraphResponse(BaseModel):
    """LLM图谱处理响应 - 输出数据结构"""
    nodes: List[LLMGraphNode] = Field(description="生成的节点列表")
    relationships: List[LLMGraphRelationship] = Field(description="生成的关系列表")
    error: Optional[str] = Field(default=None, description="错误信息")
