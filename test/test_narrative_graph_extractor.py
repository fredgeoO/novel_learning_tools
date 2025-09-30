from rag.narrative_graph_extractor import NarrativeGraphExtractor


def main():
    """
    主函数：用于测试 NarrativeGraphExtractor 的基本功能
    """
    import json
    from datetime import datetime

    # 示例小说文本
    sample_text = """
    在遥远的艾尔多拉大陆上，有一个名叫林风的年轻剑士。
    他拥有一把传说中的圣剑"破晓"，剑身闪烁着金色的光芒。
    林风的师父是大陆上最强大的法师阿尔萨斯，他教会了林风许多魔法。
    阿尔萨斯告诉林风，黑暗魔王萨格拉斯正在威胁着大陆的和平。
    为了阻止萨格拉斯的阴谋，林风踏上了寻找三件神器的旅程。
    在旅途中，他遇到了精灵公主艾莉娅，她拥有治愈魔法。
    艾莉娅告诉林风，暗影军团正在围攻精灵王国。
    林风决定先去救援精灵王国，与艾莉娅一起对抗暗影军团。
    在战斗中，林风发现暗影军团的首领竟然是他失散多年的哥哥雷恩。
    雷恩被黑暗力量腐蚀，已经忘记了过去的兄弟情谊。
    林风必须在拯救哥哥和保护大陆之间做出艰难的选择。
    """

    print("=" * 60)
    print("NarrativeGraphExtractor 测试")
    print("=" * 60)
    print(f"测试时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()

    # 创建提取器配置
    from rag.config_models import ExtractionConfig

    config = ExtractionConfig(
        novel_name="测试小说",
        chapter_name="第一章",
        text=sample_text,
        model_name="qwen3:30b-a3b-instruct-2507-q4_K_M",  # 根据你的本地模型调整
        base_url="http://localhost:11434",  # 根据你的Ollama地址调整
        temperature=0.1,
        num_ctx=4096,
        use_local=True,  # 使用本地模型
        chunk_size=1000,
        chunk_overlap=200,
        merge_results=True,
        verbose=True,
        schema_name="极简",  # 可以尝试 "基础", "完整", "自动生成", "无约束"
        use_cache=True,
        optimize_graph=True
    )

    print("配置信息:")
    print(f"  - 小说名: {config.novel_name}")
    print(f"  - 章节名: {config.chapter_name}")
    print(f"  - 模型: {config.model_name}")
    print(f"  - 本地模型: {config.use_local}")
    print(f"  - Schema: {config.schema_name}")
    print(f"  - 文本长度: {len(config.text)} 字符")
    print()

    # 创建提取器
    try:
        extractor = NarrativeGraphExtractor.from_config(config)
        print("✅ 提取器创建成功")
    except Exception as e:
        print(f"❌ 提取器创建失败: {e}")
        return

    print()
    print("开始提取...")
    print("-" * 40)

    try:
        # 执行提取
        result, duration, status, chunk_results, cache_key = extractor._extract_main(config)

        print("-" * 40)
        print("提取完成!")
        print(f"状态码: {status} ({'成功' if status == 0 else '部分成功' if status == 1 else '失败'})")
        print(f"总耗时: {duration:.2f} 秒")
        print(f"缓存键: {cache_key}")

        if result:
            print(f"节点数量: {len(result.nodes)}")
            print(f"关系数量: {len(result.relationships)}")
            print()

            # 显示节点信息
            print("提取的节点:")
            for i, node in enumerate(result.nodes[:10]):  # 只显示前10个
                print(f"  {i + 1}. ID: '{node.id}', Type: '{node.type}', Properties: {node.properties}")
            if len(result.nodes) > 10:
                print(f"  ... 还有 {len(result.nodes) - 10} 个节点")

            print()

            # 显示关系信息
            print("提取的关系:")
            for i, rel in enumerate(result.relationships[:10]):  # 只显示前10个
                print(f"  {i + 1}. {rel.source_id} --[{rel.type}]--> {rel.target_id}")
            if len(result.relationships) > 10:
                print(f"  ... 还有 {len(result.relationships) - 10} 个关系")

            print()

            # 显示块处理信息
            print(f"处理的文本块数量: {len(chunk_results)}")
            successful_chunks = sum(1 for r in chunk_results if r and len(r.nodes) > 0)
            print(f"成功处理的块数量: {successful_chunks}")

        else:
            print("❌ 提取结果为空")

    except Exception as e:
        print(f"❌ 提取过程中发生错误: {e}")
        import traceback
        traceback.print_exc()

    print()
    print("=" * 60)
    print("测试完成")
    print("=" * 60)

    # 额外测试：不同Schema模式
    print("\n额外测试：不同Schema模式")
    schemas_to_test = ["极简", "基础", "自动生成"]

    for schema_name in schemas_to_test:
        print(f"\n测试 Schema: {schema_name}")
        try:
            config.schema_name = schema_name
            temp_extractor = NarrativeGraphExtractor.from_config(config)
            result, duration, status, _, _ = temp_extractor._extract_main(config)

            if result:
                print(f"  节点数: {len(result.nodes)}, 关系数: {len(result.relationships)}, 耗时: {duration:.2f}s")
            else:
                print(f"  提取失败")

        except Exception as e:
            print(f"  测试失败: {e}")


if __name__ == "__main__":
    main()