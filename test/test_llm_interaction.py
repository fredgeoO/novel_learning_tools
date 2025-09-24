# text\test_llm.py
"""
测试不同 LLM 后端的输出结果，并直接列出内容供人工查看
- 默认 Ollama 配置
- Selenium Qwen 服务 (http://localhost:5001)
"""

import logging
from llm.llm_core import LLMInteractionManager  # 注意：你可能需要调整导入路径

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def create_sample_data():
    """创建测试用的节点和上下文图谱"""
    sample_node = {
        "id": "concept_001",
        "label": "量子纠缠",
        "type": "物理概念",
        "properties": {
            "definition": "两个或多个粒子在相互作用后，其量子状态必须依据整体系统描述，即使相隔遥远。",
            "field": "量子力学",
            "discovered_by": "爱因斯坦、波多尔斯基、罗森 (EPR悖论)"
        }
    }

    sample_context_graph = {
        "nodes": [
            {"id": "concept_002", "label": "量子力学", "type": "学科"},
            {"id": "person_001", "label": "爱因斯坦", "type": "人物"}
        ],
        "relationships": [
            {
                "source_id": "concept_001",
                "target_id": "concept_002",
                "type": "属于",
                "properties": {"content": "量子纠缠是量子力学中的现象"}
            }
        ]
    }
    return sample_node, sample_context_graph


def run_single_test(llm_manager, node, context_graph, question_type="通用"):
    """运行单个测试并返回结果对象"""
    if question_type == "通用":
        return llm_manager.generate_graph_from_question(node, "量子纠缠在量子计算中有什么作用？", context_graph)
    elif question_type == "解释":
        return llm_manager.explain_meaning(node, context_graph)
    elif question_type == "理据":
        return llm_manager.analyze_justification(node, context_graph)
    elif question_type == "可能性":
        return llm_manager.explore_possibility(node, context_graph)
    else:
        raise ValueError("未知问题类型")


def _print_response_content(response, name="结果"):
    """打印响应的详细内容（节点 + 关系）"""
    print(f"\n📄 [{name}] 详细内容:")
    print("-" * 60)

    if response.error:
        print(f"❌ 错误: {response.error}")
        return

    if not response.nodes and not response.relationships:
        print("（无内容）")
        return

    # 打印节点
    if response.nodes:
        print("🔹 节点:")
        for i, node in enumerate(response.nodes, 1):
            content = node.properties.get("content", "N/A")
            print(f"  {i}. ID: {node.id}")
            print(f"     类型: {node.type}")
            print(f"     内容: {content[:300]}{'...' if len(content) > 300 else ''}")
            print()

    # 打印关系
    if response.relationships:
        print("🔗 关系:")
        for i, rel in enumerate(response.relationships, 1):
            content = rel.properties.get("content", "N/A")
            print(f"  {i}. {rel.source_id} --[{rel.type}]--> {rel.target_id}")
            print(f"     说明: {content[:300]}{'...' if len(content) > 300 else ''}")
            print()


def _print_summary(response, name="结果"):
    """打印简要摘要"""
    if response.error:
        print(f"❌ [{name}] 错误: {response.error}")
        return {"nodes": 0, "rels": 0, "error": True}
    else:
        nodes = len(response.nodes)
        rels = len(response.relationships)
        print(f"✅ [{name}] 节点数: {nodes}, 关系数: {rels}")
        return {"nodes": nodes, "rels": rels, "error": False}


def main():
    sample_node, sample_context_graph = create_sample_data()

    # === 初始化两个 LLM 实例 ===
    default_llm = LLMInteractionManager()
    qwen_llm = LLMInteractionManager(
        default_model="qwen-web",
        ollama_base_url="http://localhost:5001"
    )

    # test_types = ["通用", "解释", "理据", "可能性"]
    test_types = ["通用"]

    for test_type in test_types:
        print("\n" + "=" * 90)
        print(f"🧪 正在测试: {test_type}")
        print("=" * 90)

        # 获取两个后端的结果
        try:
            resp_default = run_single_test(default_llm, sample_node, sample_context_graph, test_type)
        except Exception as e:
            resp_default = type('obj', (), {'error': f"异常: {e}", 'nodes': [], 'relationships': []})()

        try:
            resp_qwen = run_single_test(qwen_llm, sample_node, sample_context_graph, test_type)
        except Exception as e:
            resp_qwen = type('obj', (), {'error': f"异常: {e}", 'nodes': [], 'relationships': []})()

        # 打印摘要
        summary1 = _print_summary(resp_default, "Ollama 默认")
        summary2 = _print_summary(resp_qwen, "Selenium Qwen")

        # 直接列出两组内容（不再对比 diff）
        _print_response_content(resp_default, "Ollama 默认")
        _print_response_content(resp_qwen, "Selenium Qwen")

    print("\n🏁 所有测试完成！")


if __name__ == "__main__":
    main()