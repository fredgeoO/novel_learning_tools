# test_group_related_nodes_integration.py
import unittest
import logging
from typing import List

# 假设你的模块结构如下，请根据实际情况调整导入路径
from rag.narrative_graph_extractor import NarrativeGraphExtractor, SerializableNode, SerializableGraphDocument
from rag.config_models import ExtractionConfig
from rag.narrative_schema import generate_auto_schema
from config import *
# --- 配置日志 (可选，方便调试) ---
logging.basicConfig(level=logging.INFO) # 或 logging.DEBUG
logger = logging.getLogger(__name__)

class TestGroupRelatedNodesIntegration(unittest.TestCase):


    @classmethod
    def setUpClass(cls):
        """在所有测试方法运行前执行一次，用于准备共享资源"""
        # 1. 初始化 NarrativeGraphExtractor
        # 使用一个较小的、快速的本地模型进行测试
        cls.extractor = NarrativeGraphExtractor(
            model_name= DEFAULT_MODEL, # 使用一个小模型进行快速测试
            base_url= DEFAULT_BASE_URL,
            # 可以根据需要调整其他参数，如 temperature
        )
        logger.info("NarrativeGraphExtractor 初始化完成。")

        novel_name= "111.测试文档"
        chapter_filename="04.何鸿燊 (1).txt"
        # 2. 准备示例文本 (用于生成 Schema 和图谱)
        # 使用一段能生成较复杂关系的文本
        cls.sample_text = utils_chapter.load_chapter_content(
            novel_name=novel_name,chapter_filename=chapter_filename)

        # 3. 生成 Schema (使用真实 LLM)
        logger.info("开始调用 LLM 生成 Schema...")
        cls.auto_schema = generate_auto_schema(
            text_content=cls.sample_text,
            model_name=cls.extractor.model_name,
            is_local=True, # 假设使用本地 Ollama
            base_url=cls.extractor.base_url,
            use_cache=False # 测试时禁用缓存以确保调用真实 LLM
        )
        logger.info(f"Schema 生成完成: {cls.auto_schema['name']}")
        logger.info(f"Schema 元素: {cls.auto_schema['elements']}")
        logger.info(f"Schema 关系: {cls.auto_schema['relationships']}")

        # 4. 使用 Schema 和文本提取图谱 (使用真实 LLM)
        # 创建配置对象
        cls.config = ExtractionConfig(
            novel_name=novel_name,
            chapter_name=chapter_filename.replace(".txt", ""),
            text=cls.sample_text,
            model_name=cls.extractor.model_name,
            base_url=cls.extractor.base_url,
            use_local=True,
            # --- 关键：设置较低的 max_connections 以便更容易触发优化 ---
            max_connections=3, # 例如，连接数超过3就优化
            # --- 关键：启用图优化 ---
            optimize_graph=True,
            use_cache=False, # 测试时禁用缓存
            verbose=True # 打开日志看过程
        )

        # 执行提取 (这会调用 _group_related_nodes 如果 optimize_graph=True 且有高连接节点)
        logger.info("开始调用 LLM 提取图谱...")
        # 直接调用 _extract_internal_core 来控制流程，或者使用 extract_with_config
        # 使用 extract_with_config 更接近真实流程
        cls.graph_result, cls.duration, cls.status, cls.chunks = cls.extractor.extract_with_config(cls.config)
        logger.info(f"图谱提取完成。节点数: {len(cls.graph_result.nodes)}, 关系数: {len(cls.graph_result.relationships)}")
        # 可以打印图谱内容查看
        # cls.extractor.display_graph_document(cls.graph_result, "提取的原始图谱")

    def test_find_and_group_high_degree_node(self):
        """测试查找高连接度节点并对其进行分组"""
        # 1. 确保图谱已生成
        self.assertIsNotNone(self.graph_result)
        self.assertIsInstance(self.graph_result, SerializableGraphDocument)

        # 2. 计算节点连接度
        node_connections = {}
        for rel in self.graph_result.relationships:
            node_connections[rel.source_id] = node_connections.get(rel.source_id, 0) + 1
            node_connections[rel.target_id] = node_connections.get(rel.target_id, 0) + 1

        logger.info(f"计算出的节点连接度: {node_connections}")

        # 3. 查找高连接度节点
        high_degree_nodes: List[SerializableNode] = []
        for node in self.graph_result.nodes:
            connection_count = node_connections.get(node.id, 0)
            if connection_count > self.config.max_connections:
                high_degree_nodes.append(node)
                logger.info(f"发现高连接度节点: {node.id} (连接数: {connection_count})")

        # 4. 断言至少找到一个高连接度节点 (确保测试有效)
        # 如果没有找到，可能需要调整 sample_text 或 max_connections
        self.assertGreater(len(high_degree_nodes), 0, "测试文本和配置未能生成高连接度节点，无法测试 _group_related_nodes。")

        # 5. 选择第一个高连接度节点进行测试
        main_node = high_degree_nodes[0]
        logger.info(f"选择主节点进行分组测试: {main_node.id}")

        # 6. 找出与主节点相关的节点
        related_relations = [
            rel for rel in self.graph_result.relationships
            if rel.source_id == main_node.id or rel.target_id == main_node.id
        ]
        related_node_ids = set()
        for rel in related_relations:
            if rel.source_id == main_node.id:
                related_node_ids.add(rel.target_id)
            else:
                related_node_ids.add(rel.source_id)
        related_nodes = [
            n for n in self.graph_result.nodes if n.id in related_node_ids
        ]
        logger.info(f"找到 {len(related_nodes)} 个相关节点: {[n.id for n in related_nodes]}")

        # 7. 调用 _group_related_nodes (使用真实 LLM)
        logger.info(f"调用 _group_related_nodes 对主节点 '{main_node.id}' 的相关节点进行分组...")
        grouping_result = self.extractor._group_related_nodes(
            main_node=main_node,
            related_nodes=related_nodes,
            config=self.config,
            use_cache=False # 测试时禁用缓存以确保调用真实 LLM
        )

        # 8. 验证返回结果
        from rag.narrative_graph_extractor import AggregateGroupingResponse # 确保导入
        self.assertIsInstance(grouping_result, AggregateGroupingResponse)
        logger.info(f"_group_related_nodes 返回结果: {grouping_result}")

        # 9. 验证分组内容 (基本检查)
        self.assertIsNotNone(grouping_result.groups)
        self.assertIsInstance(grouping_result.groups, list)
        self.assertGreater(len(grouping_result.groups), 0, "LLM 应该至少生成一个分组。")

        for i, group in enumerate(grouping_result.groups):
            logger.info(f"  分组 {i+1}: {group.group_name} ({len(group.node_ids)} 个成员)")
            self.assertIsInstance(group.aggregate_node_id, str)
            self.assertTrue(group.aggregate_node_id, "聚合节点 ID 不应为空")
            self.assertIsInstance(group.group_name, str)
            self.assertTrue(group.group_name, "分组名称不应为空")
            self.assertIsInstance(group.description, str)
            self.assertIsInstance(group.node_ids, list)
            self.assertGreater(len(group.node_ids), 0, "每个分组应至少包含一个节点")
            # 检查 node_ids 是否都在 related_nodes 中
            related_node_id_set = {n.id for n in related_nodes}
            for nid in group.node_ids:
                self.assertIn(nid, related_node_id_set, f"分组中的节点ID '{nid}' 不在相关节点列表中")

            # 检查新添加的字段
            self.assertIsInstance(group.aggregate_relationship_type, str)
            self.assertTrue(group.aggregate_relationship_type, "聚合关系类型不应为空")
            self.assertIsInstance(group.member_relationship_type, str)
            self.assertTrue(group.member_relationship_type, "成员关系类型不应为空")

        logger.info("高连接度节点分组测试通过。")


if __name__ == '__main__':
    unittest.main()
