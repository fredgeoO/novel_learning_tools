# utils_number.py
"""
处理各种数字格式（中文、阿拉伯、罗马）的工具函数。
"""

import re

# --- 中文数字映射 ---
CHINESE_NUMBER_MAP = {
    # 基本数字
    "〇": 0, "零": 0, "一": 1, "二": 2, "三": 3, "四": 4, "五": 5,
    "六": 6, "七": 7, "八": 8, "九": 9,
    # 十位数
    "十": 10, "廿": 20, "卅": 30,
    # 十位组合 (10-19)
    "十一": 11, "十二": 12, "十三": 13, "十四": 14, "十五": 15,
    "十六": 16, "十七": 17, "十八": 18, "十九": 19,
    # 整十 (20-90)
    "二十": 20, "三十": 30, "四十": 40, "五十": 50,
    "六十": 60, "七十": 70, "八十": 80, "九十": 90,
    # 复合十位 (21-99)
    "二十一": 21, "二十二": 22, "二十三": 23, "二十四": 24, "二十五": 25,
    "二十六": 26, "二十七": 27, "二十八": 28, "二十九": 29,
    "三十一": 31, "三十二": 32, "三十三": 33, "三十四": 34, "三十五": 35,
    "三十六": 36, "三十七": 37, "三十八": 38, "三十九": 39,
    "四十一": 41, "四十二": 42, "四十三": 43, "四十四": 44, "四十五": 45,
    "四十六": 46, "四十七": 47, "四十八": 48, "四十九": 49,
    "五十一": 51, "五十二": 52, "五十三": 53, "五十四": 54, "五十五": 55,
    "五十六": 56, "五十七": 57, "五十八": 58, "五十九": 59,
    "六十一": 61, "六十二": 62, "六十三": 63, "六十四": 64, "六十五": 65,
    "六十六": 66, "六十七": 67, "六十八": 68, "六十九": 69,
    "七十一": 71, "七十二": 72, "七十三": 73, "七十四": 74, "七十五": 75,
    "七十六": 76, "七十七": 77, "七十八": 78, "七十九": 79,
    "八十一": 81, "八十二": 82, "八十三": 83, "八十四": 84, "八十五": 85,
    "八十六": 86, "八十七": 87, "八十八": 88, "八十九": 89,
    "九十一": 91, "九十二": 92, "九十三": 93, "九十四": 94, "九十五": 95,
    "九十六": 96, "九十七": 97, "九十八": 98, "九十九": 99,
    # 百位及以上
    "一百": 100, "皕": 200, # 稍微高级一点的字
    # 大写数字 (虽然不常见于章节名，但为完整性加入)
    "壹": 1, "贰": 2, "叁": 3, "肆": 4, "伍": 5, "陆": 6, "柒": 7, "捌": 8, "玖": 9,
    "拾": 10, "佰": 100, "仟": 1000,
    # 更大单位 (通常用于序数，但映射有助于识别)
    "萬": 10000, "亿": 100000000, "兆": 1000000000000
}


def chinese_to_arabic_simple(chinese_str: str) -> int:
    """
    将中文数字字符串转换为整数。
    优先使用 CHINESE_NUMBER_MAP 进行直接查找。
    如果找不到，则尝试简单组合（适用于较复杂的数字，如 "一百零一"）。
    """
    # 1. 直接查找
    if chinese_str in CHINESE_NUMBER_MAP:
        return CHINESE_NUMBER_MAP[chinese_str]

    # 2. 如果直接查找失败，尝试简单组合逻辑 (适用于 "一百零一", "三十五" 等)
    #    注意：这是一个简化版本，可能不处理所有边界情况，但对于章节标题通常足够。
    total = 0
    current_number = 0
    unit = 1
    i = len(chinese_str) - 1

    while i >= 0:
        char = chinese_str[i]
        char_value = CHINESE_NUMBER_MAP.get(char, 0)

        if char in ['零', '〇']:
            # 零通常不改变值，但可能影响单位
            pass
        elif char == '十':
            unit = 10
            if i == 0: # 处理 "十" 开头的情况，如 "十三"
                current_number = 1
        elif char == '百' or char == '佰':
            unit = 100
        elif char == '千' or char == '仟':
            unit = 1000
        elif char == '万' or char == '萬':
            unit = 10000
            total += current_number * unit
            current_number = 0
        elif char == '亿':
            unit = 100000000
            total += current_number * unit
            current_number = 0
        elif char == '兆':
            unit = 1000000000000
            total += current_number * unit
            current_number = 0
        else:
            # 是基本数字字符 (一, 二, 三, ..., 九, 壹, 贰, ...)
            current_number += char_value * unit
            unit = 1 # 重置单位为1，用于下一个基本数字
        i -= 1

    total += current_number
    # 如果解析结果为0（可能输入了无效字符或空字符串），返回无穷大以排在最后
    return total if total > 0 else float('inf')


def roman_to_arabic(roman_str: str) -> int:
    """
    将罗马数字字符串转换为阿拉伯数字整数。
    """
    if not roman_str:
        return float('inf')
    roman_str = roman_str.upper()
    roman_values = {
        'I': 1, 'V': 5, 'X': 10, 'L': 50,
        'C': 100, 'D': 500, 'M': 1000
    }

    total = 0
    prev_value = 0

    for char in reversed(roman_str):
        value = roman_values.get(char, 0)
        if value == 0: # 如果遇到无效字符，解析失败
             return float('inf')
        if value < prev_value:
            total -= value
        else:
            total += value
        prev_value = value

    return total if total > 0 else float('inf')
