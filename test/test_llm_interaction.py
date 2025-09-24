# test_llm.py
"""
测试并对比不同 LLM 后端的输出结果
- 默认 Ollama 配置
- Selenium Qwen 服务 (http://localhost:5001)
"""

import logging
from llm.llm_core import LLMInteractionManager
from difflib import unified_diff
import json

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


def serialize_response(response) -> str:
    """将 LLMGraphResponse 转为可比较的 JSON 字符串（用于 diff）"""
    data = {
        "nodes": [
            {
                "id": n.id,
                "type": n.type,
                "content": n.properties.get("content", "")[:200]  # 截断长文本
            }
            for n in response.nodes
        ],
        "relationships": [
            {
                "source": r.source_id,
                "target": r.target_id,
                "type": r.type,
                "content": r.properties.get("content", "")[:200]
            }
            for r in response.relationships
        ],
        "error": response.error
    }
    return json.dumps(data, ensure_ascii=False, indent=2)


def compare_responses(resp1, resp2, name1="配置A", name2="配置B"):
    """对比两个响应的结构化差异"""
    str1 = serialize_response(resp1).splitlines(keepends=True)
    str2 = serialize_response(resp2).splitlines(keepends=True)

    diff = list(unified_diff(str1, str2, fromfile=name1, tofile=name2, lineterm=''))

    if diff:
        print("\n🔍 结果差异对比:")
        print("-" * 60)
        for line in diff:
            print(line.rstrip())
        print("-" * 60)
    else:
        print("✅ 两组结果完全一致！")


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

    test_types = ["通用", "解释", "理据", "可能性"]

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

        # 如果两者都成功，进行详细对比
        if not summary1["error"] and not summary2["error"]:
            compare_responses(resp_default, resp_qwen, "Ollama 默认", "Selenium Qwen")
        else:
            print("⚠️  跳过详细对比（至少一个结果出错）")

    print("\n🏁 所有对比测试完成！")


if __name__ == "__main__":
    main()