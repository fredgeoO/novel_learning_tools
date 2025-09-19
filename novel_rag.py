# novel_rag.py

import logging
import sys
import os
import time

# 启用根日志记录
logging.basicConfig(level=logging.INFO)

# --- 导入新类和工具 ---
from rag.narrative_graph_extractor import NarrativeGraphExtractor
from utils_chapter import load_chapter_content
from rag.narrative_schema import ANALYTICAL_SCHEMA

# --- 公共配置 ---
COMMON_CONFIG = {
    "model_name": "qwen3:8b",
    "base_url": "http://localhost:11434",
    "temperature": 0.0,
    "default_num_ctx": 8192,
    "remote_api_key": os.getenv("ARK_API_KEY"),
    "remote_base_url": "https://ark.cn-beijing.volces.com/api/v3",
    "remote_model_name": "doubao-seed-1-6-250615",
    "selected_schema": ANALYTICAL_SCHEMA,
    "schema_name": "分析模式 (Analytical Schema)"
}
def clean_cache():
    """清理损坏的缓存文件"""
    import shutil
    cache_dir = "./cache/graph_docs"
    if os.path.exists(cache_dir):
        shutil.rmtree(cache_dir)
        os.makedirs(cache_dir, exist_ok=True)
        print("✅ 缓存目录已清理")

# 1. 替换原有的 load_text 函数
def load_text(novel_name="东京病恋女友", chapter_file="第一章 借贷少女.txt"):
    """加载章节文本的通用函数 (使用默认小说章节)"""
    print(f"\n正在加载章节内容: {novel_name} - {chapter_file}...")
    loaded_result = load_chapter_content(novel_name, chapter_file)

    if isinstance(loaded_result, tuple) and len(loaded_result) > 0:
        original_text = loaded_result[0]
        load_success = loaded_result[1] if len(loaded_result) > 1 else True
        if not load_success:
            print("警告：章节内容加载可能未完全成功。")
        if original_text:
            print(f"✅ 文本加载成功，长度: {len(original_text)} 字符")
        return original_text
    else:
        print(f"❌ 错误：load_chapter_content 返回了意外的类型 {type(loaded_result)} 或为空。")
        return None


def create_extractor(local_chunk_size=1024, local_chunk_overlap=128,
                     remote_chunk_size=2048, remote_chunk_overlap=256,
                     use_local=True):
    """创建 NarrativeGraphExtractor 实例的通用函数"""
    config = COMMON_CONFIG.copy()
    extractor = NarrativeGraphExtractor(
        model_name=config["model_name"],
        base_url=config["base_url"],
        temperature=config["temperature"],
        default_num_ctx=config["default_num_ctx"],
        default_chunk_size=local_chunk_size if use_local else remote_chunk_size,
        default_chunk_overlap=local_chunk_overlap if use_local else remote_chunk_overlap,
        remote_api_key=config["remote_api_key"],
        remote_base_url=config["remote_base_url"].strip(),  # 去掉空格
        remote_model_name=config["remote_model_name"],
        allowed_nodes=config["selected_schema"]["elements"],
        allowed_relationships=config["selected_schema"]["relationships"],
    )

    if not use_local and not extractor.use_remote_api:
        print("⚠️  警告：远程API配置不完整，无法测试远程模型")
        print(f"   remote_api_key: {'✓' if extractor.remote_api_key else '✗'}")
        print(f"   remote_base_url: {'✓' if extractor.remote_base_url else '✗'}")
        print(f"   remote_model_name: {'✓' if extractor.remote_model_name else '✗'}")
        return None

    print(f"✅ Extractor 初始化完成 ({'本地' if use_local else '远程'}模型配置)")
    return extractor


def run_extraction(extractor, text, use_local, test_text_length=None, novel_name="", chapter_name=""):
    """执行图谱提取的通用函数"""
    model_name = "本地模型 (Ollama)" if use_local else "远程模型 (豆包API)"
    print(f"\n" + "=" * 60)
    print(f"开始测试 {model_name}...")
    if test_text_length:
        print(f"测试文本长度: {test_text_length} 字符")
    print("=" * 60)

    try:
        # 使用带缓存的提取方法
        result, duration, status, chunks = extractor.extract_with_cache(
            text=text,
            novel_name=novel_name,
            chapter_name=chapter_name,
            num_ctx=extractor.default_num_ctx,
            chunk_size=extractor.default_chunk_size,
            chunk_overlap=extractor.default_chunk_overlap,
            merge_results=True,
            verbose=True,
            use_cache=True
        )
        print(f"✅ {model_name} 测试完成，耗时: {duration:.2f} 秒")
        return result, duration, status, chunks
    except Exception as e:
        print(f"❌ {model_name} 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return None, 0, 2, []

def display_results(extractor, result, duration, status, chunks, title_suffix=""):
    """显示提取结果的通用函数"""
    if not result:
        print(f"❌ {title_suffix}无结果可显示")
        return

    print(f"\n" + "=" * 70)
    print(f"【{title_suffix}】")
    print("=" * 70)

    status_msg = {0: "全部成功", 1: "部分成功", 2: "全部失败"}
    print(f"总耗时: {duration:.2f} 秒")
    print(f"最终状态: {status_msg.get(status, '未知')}")

    if chunks:
        print(f"\n--- 各分割块结果摘要 ---")
        for i, chunk_res in enumerate(chunks):
            nodes_cnt = len(getattr(chunk_res, 'nodes', []))
            rels_cnt = len(getattr(chunk_res, 'relationships', []))
            print(f"  块 {i + 1}: 节点 {nodes_cnt} 个, 关系 {rels_cnt} 个")

    extractor.display_graph_document(result, f"{title_suffix}结果")

    print("\n" + "=" * 70)


# --- 测试函数 ---
def test_single_model(original_text, novel_name="东京病恋女友", chapter_name="第一章 借贷少女"):
    """原始的单一模型测试"""
    print(f"已选择: {COMMON_CONFIG['schema_name']}")

    # 创建提取器 (默认使用本地配置)
    extractor = create_extractor(use_local=True)
    if not extractor:
        return

    # 执行提取 (使用本地模型)
    result, duration, status, chunks = run_extraction(
        extractor, original_text, use_local=True,
        novel_name=novel_name, chapter_name=chapter_name
    )

    # 显示结果
    display_results(extractor, result, duration, status, chunks, "叙事图谱提取结果")

    print("\n【说明】")
    print(f"1. 使用了 {COMMON_CONFIG['schema_name']}。")
    print("2. 文本已被分割处理，显著提高了处理速度。")
    print("3. 每个块独立处理，结果已尝试合并。")
    print("4. 合并逻辑是基础的：节点按 ID 和 Type 合并，关系直接累加。")


def compare_models_test(original_text, novel_name="东京病恋女友", chapter_name="第一章 借贷少女"):
    """比较本地和远程模型的执行时间和结果差异"""
    print(f"已选择: {COMMON_CONFIG['schema_name']}")

    # 移除了2000字符限制，使用完整文本
    test_text = original_text
    test_chapter_name = f"{chapter_name}_对比测试"
    print(f"\n测试文本长度: {len(test_text)} 字符")

    # 创建提取器 (本地和远程使用不同的分块配置)
    local_extractor = create_extractor(use_local=True)
    remote_extractor = create_extractor(use_local=False)

    if not local_extractor or not remote_extractor:
        print("❌ 提取器初始化失败")
        return

    results = {}

    # 测试本地模型
    local_result, local_duration, local_status, local_chunks = run_extraction(
        local_extractor, test_text, use_local=True,
        test_text_length=len(test_text),
        novel_name=novel_name,
        chapter_name=f"{test_chapter_name}_本地"
    )
    results['local'] = {
        'result': local_result,
        'duration': local_duration,
        'status': local_status,
        'chunks': local_chunks
    }

    # 测试远程模型
    remote_result, remote_duration, remote_status, remote_chunks = run_extraction(
        remote_extractor, test_text, use_local=False,
        test_text_length=len(test_text),
        novel_name=novel_name,
        chapter_name=f"{test_chapter_name}_远程"
    )
    results['remote'] = {
        'result': remote_result,
        'duration': remote_duration,
        'status': remote_status,
        'chunks': remote_chunks
    }

    # --- 对比结果 ---
    print("\n" + "=" * 80)
    print("【模型对比测试结果】")
    print("=" * 80)

    print(f"使用模式: {COMMON_CONFIG['schema_name']}")
    print(f"测试文本长度: {len(test_text)} 字符")

    # 性能对比
    print(f"\n--- 性能对比 ---")
    local_duration = results['local'].get('duration', 0)
    remote_duration = results['remote'].get('duration', 0)

    if local_duration > 0 and remote_duration > 0:
        print(f"  本地模型耗时: {local_duration:.2f} 秒")
        print(f"  远程模型耗时: {remote_duration:.2f} 秒")
        if local_duration < remote_duration:
            speedup = remote_duration / local_duration
            print(f"  💡 本地模型快 {speedup:.1f} 倍")
        else:
            slowdown = local_duration / remote_duration
            print(f"  🌐 远程模型快 {slowdown:.1f} 倍")
    elif local_duration > 0:
        print(f"  本地模型耗时: {local_duration:.2f} 秒")
        print(f"  远程模型测试失败")
    elif remote_duration > 0:
        print(f"  本地模型测试失败")
        print(f"  远程模型耗时: {remote_duration:.2f} 秒")
    else:
        print("  两种模型测试均失败")

    # 结果质量对比
    print(f"\n--- 结果质量对比 ---")
    local_nodes = len(getattr(results['local'].get('result'), 'nodes', [])) if results['local'].get('result') else 0
    local_rels = len(getattr(results['local'].get('result'), 'relationships', [])) if results['local'].get(
        'result') else 0
    remote_nodes = len(getattr(results['remote'].get('result'), 'nodes', [])) if results['remote'].get('result') else 0
    remote_rels = len(getattr(results['remote'].get('result'), 'relationships', [])) if results['remote'].get(
        'result') else 0

    print(f"  本地模型: 节点 {local_nodes} 个, 关系 {local_rels} 个")
    print(f"  远程模型: 节点 {remote_nodes} 个, 关系 {remote_rels} 个")

    # 显示结果详情
    if results['local'].get('result'):
        print(f"\n--- 本地模型结果摘要 ---")
        display_results(local_extractor, results['local']['result'], 0, 0, [], "本地模型")

    if results['remote'].get('result'):
        print(f"\n--- 远程模型结果摘要 ---")
        display_results(remote_extractor, results['remote']['result'], 0, 0, [], "远程模型")

    print("\n" + "=" * 80)
    print("【测试说明】")
    print("1. 本地模型：使用 Ollama 运行的 qwen3:8b")
    print("2. 远程模型：使用火山方舟豆包 API")
    print("3. 使用完整文本进行测试")
    print("4. 性能受网络、模型负载等多种因素影响")
    print("=" * 80)


def test_remote_only(original_text, novel_name="东京病恋女友", chapter_name="第一章 借贷少女"):
    """只测试远程模型"""
    print(f"已选择: {COMMON_CONFIG['schema_name']}")

    # 移除了2000字符限制，使用完整文本
    test_text = original_text
    print(f"\n测试文本长度: {len(test_text)} 字符")

    # 创建提取器 (使用远程配置)
    extractor = create_extractor(use_local=False)
    if not extractor:
        return

    # 执行提取 (强制使用远程模型)
    result, duration, status, chunks = run_extraction(
        extractor, test_text, use_local=False,
        test_text_length=len(test_text),
        novel_name=novel_name,
        chapter_name=f"{chapter_name}_远程_only"
    )

    # 显示结果
    display_results(extractor, result, duration, status, chunks, "远程模型测试结果")

    print("\n【说明】")
    print("1. 使用远程模型：火山方舟豆包 API")
    print("2. 文本已被分割处理")
    print("3. 每个块独立处理，结果已尝试合并")


# 2. 替换原有的 if __name__ == "__main__": 块
if __name__ == "__main__":
    # 1. 直接加载默认文本 (不再需要用户选择)
    novel_name = "东京病恋女友"
    chapter_file = "第一章 借贷少女.txt"
    chapter_name = "第一章 借贷少女"

    print(f"--- 使用默认小说章节: {novel_name} - {chapter_file} ---")
    original_text = load_text(novel_name, chapter_file)  # 使用指定参数

    if not original_text:
        print("❌ 无法加载文本，程序退出。")
        sys.exit(1)

    # 2. 询问用户要运行哪种测试
    print("\n请选择测试模式:")
    print("1. 单一模型测试")
    print("2. 本地vs远程模型对比测试")
    print("3. 仅测试远程模型")

    choice = input("请输入选择 (1、2 或 3): ").strip()

    # 3. 根据选择调用相应的测试函数，并传递已加载的文本
    if choice == "2":
        compare_models_test(original_text, novel_name, chapter_name)
    elif choice == "3":
        test_remote_only(original_text, novel_name, chapter_name)
    else:
        test_single_model(original_text, novel_name, chapter_name)