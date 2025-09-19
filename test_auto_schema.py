"""
测试程序：演示generate_auto_schema函数的使用方法
"""

from rag.narrative_schema import generate_auto_schema, MINIMAL_SCHEMA, BASIC_SCHEMA


def main():
    # 测试文本内容
    test_text = """
    第一章 初入

    陆江仙做了一个很长很长的梦，梦见田间种稻，梦见刀光剑影，梦见仙宗、女子、大湖。

    "将《太阴吐纳练气诀》与《月华纪要秘旨》交出，我等可以只废去你修为。"

    一道悦耳又冰冷的女声在耳边响起，陆江仙隐隐约约看见一张朦胧的脸庞，却什么也看不清楚。

    "咣当！"

    剧烈的摇晃感一下子将陆江仙惊醒。

    光怪陆离的色彩在脑海中浮现，陆江仙想睁开眼，想起身，身体如同鬼压床般对他的指挥毫不理睬。

    这时，一道灿烂的白光划破眼前的浓密的黑暗，虽然黑暗如同潮水一般不断涌来，但那道光柱始终矗立着，太阳一般亘古不变。

    密密麻麻的金色咒文从中迸发而出，在黑暗中舒展着身体，像星辰一样撒满天空。

    "好美。"陆江仙呆呆地想着。

    随着咒文越来越多，仿佛到达了某个极限，他听到了如同玻璃破碎的咔嚓声。

    世界，亮了。

    陆江仙看见了蔚然如大海的天空，茂密的无边无际的原始森林，不远处是弯月型的小湖，在那个方向，一道白色的流光滑落在波光粼粼的小湖中。

    下方坐落着一小片秸秆扎成顶的小屋和成片的稻田。

    剧烈翻滚的视角中，他像一只轻飘飘的燕雀飞过褐黄色的小小的村落和烟火，从清澈的小河上空划过。

    惊鸿一瞥中，陆江仙望见了小河中自己的倒影。

    "好像是一个圆形的，闪闪发光的东西......"陆江仙迷茫地想着，一种隐约的预兆浮现在心头：

    "我不做人了？"

    "哗啦！"剧烈的摇晃再次袭来，陆江仙迅速沉入水中，小河太浅不足以化解所有冲击力，于是他轻轻地磕在了小河底的青石之上。
    """



    print("\n=== 测试1: 基于最小化schema扩展 ===")
    auto_schema2 = generate_auto_schema(
        text_content=test_text,
        model_name="doubao-seed-1-6-250615",
        enable_thinking=True,
        use_cache=True,
        reference_schema=MINIMAL_SCHEMA
    )
    print(f"生成的schema名称: {auto_schema2['name']}")
    print(f"描述: {auto_schema2['description']}")
    print(f"元素类型: {auto_schema2['elements']}")
    print(f"关系类型: {auto_schema2['relationships']}")

    print("\n=== 测试2: 基于基本schema扩展 ===")
    auto_schema2 = generate_auto_schema(
        text_content=test_text,
        model_name="doubao-seed-1-6-250615",
        enable_thinking=True,
        use_cache=True,
        reference_schema=BASIC_SCHEMA
    )
    print(f"生成的schema名称: {auto_schema2['name']}")
    print(f"描述: {auto_schema2['description']}")
    print(f"元素类型: {auto_schema2['elements']}")
    print(f"关系类型: {auto_schema2['relationships']}")




if __name__ == "__main__":
    main()