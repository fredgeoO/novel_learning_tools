# automate_prompts.py
import os
from llm.qwen_chat_client import QwenChatClient

QWEN_PROMPT_TEMPLATE_FILE = os.path.join("inputs", "prompts", "qwen_chapter_prompt_template.txt")

def read_chapters(filename):
    """从文件中读取章节列表"""
    chapters = []
    try:
        with open(filename, 'r', encoding='utf-8') as file:
            for line in file:
                line = line.strip()
                if line:
                    chapters.append(line)
    except FileNotFoundError:
        print(f"错误：找不到文件 {filename}")
        return []
    return chapters


def read_qwen_prompt_template(template_path):
    """
    从文件中读取 Qwen 提示词模板。
    :param template_path: 模板文件的路径。
    :return: 模板内容字符串，如果读取失败则返回 None。
    """
    try:
        with open(template_path, 'r', encoding='utf-8') as f:
            template_content = f.read()
        print(f"[提示词生成] 成功读取 Qwen 提示词模板: {template_path}")
        return template_content
    except FileNotFoundError:
        print(f"[提示词生成错误] 找不到 Qwen 提示词模板文件: {template_path}")
        return None
    except Exception as e:
        print(f"[提示词生成错误] 读取 Qwen 提示词模板文件 '{template_path}' 时出错: {e}")
        return None


def generate_qwen_prompt(chapter_title):
    """
    根据章节标题和预定义的模板文件生成发送给 Qwen 的提示词。
    :param chapter_title: (str) 章节的完整标题 (例如 "第36章：个人飞行装置：个人飞行设备")。
    :return: (str) 格式化后的提示词字符串。
    """
    print(f"[提示词生成] 正在为章节 '{chapter_title}' 生成 Qwen 提示词...")

    # 1. 读取模板内容
    template_content = read_qwen_prompt_template(QWEN_PROMPT_TEMPLATE_FILE)

    # 2. 检查模板是否成功读取
    if template_content is None:
        print("[提示词生成] 警告：无法读取模板文件，将使用硬编码的默认模板。")
        # Fallback 到之前的硬编码模板 (可选)
        template_content = """请你扮演职业轻小说家，完成以下任务
主题 = {chapter_title}

1. 简洁明了介绍这个主题。
2. 请为 该 主题 列举 7个作家可以从中获得参考/灵感的 关键词，每个关键词举一个例子。

3.例子作品要求：可来源自动漫/轻小说/网络小说。

4.纯文本输出，不要用表格，可用点列式。
5.输出一个新人物的名字：这个名字和主题有关，他/她会参与主题讨论。格式为 新角色：名字（如果是外国人名字必须翻译成中文）。"""

    # 3. 使用 str.format() 方法将 chapter_title 填入模板
    try:
        final_prompt = template_content.format(chapter_title=chapter_title)
        print(f"[提示词生成] Qwen 提示词生成成功 (长度: {len(final_prompt)} 字符)。")
        return final_prompt
    except KeyError as e:
        error_msg = f"[提示词生成错误] 模板中包含未提供的占位符: {e}。请检查模板文件 '{QWEN_PROMPT_TEMPLATE_FILE}'。"
        print(error_msg)
        # 可以选择抛出异常或返回错误信息
        raise ValueError(error_msg) from e
    except Exception as e:
        error_msg = f"[提示词生成错误] 格式化提示词模板时发生未知错误: {e}"
        print(error_msg)
        raise e


def find_next_chapter(current_chapter, all_chapters):
    """根据当前章节，在章节列表中找到下一个章节"""
    try:
        current_index = all_chapters.index(current_chapter)
        if current_index + 1 < len(all_chapters):
            return all_chapters[current_index + 1]
    except ValueError:
        pass
    return "下一章：未知"


def sanitize_filename(text):
    """
    清理文本，使其可以安全地用作文件名。
    移除或替换 Windows/Linux 不允许的字符。
    """
    invalid_chars = '<>|"*?[]~`'
    for char in invalid_chars:
        text = text.replace(char, '_')
    text = text.strip('. ')
    return text[:150]


def generate_grok_prompt_from_raw(chapter_title, raw_qwen_response, all_chapters):
    """
    根据章节标题、原始 Qwen 回复和章节列表生成 Grok 提示词。
    直接将原始回复附加到提示词模板后。
    """
    parts = chapter_title.split('：')
    discussion_topic = parts[1] if len(parts) >= 2 else chapter_title

    next_chapter = find_next_chapter(chapter_title, all_chapters)

    grok_prompt_header = (
        f"讨论主题：{discussion_topic}\n\n"
        f"章节名：{chapter_title}\n"
        f"下一个章节：{next_chapter}\n\n"
        f"第1个大段落§用提问介绍这个讨论主题是什么。\n"
        f"第2-7个大段落§用提问介绍以下具体例子。\n"
        f"第2-7个大段落§引用1个以下提到的作品来说明，每个大段落只提一个作品做例子。\n\n"
    )
    return grok_prompt_header + raw_qwen_response


def clean_qwen_response(response_text):
    """
    从 Qwen 的回复中移除开头的中间状态信息。
    """
    if not response_text:
        return response_text

    intermediate_indicators = ["正在思考与搜索", "tokens 预算", "思考与搜索已完成"]
    lines = response_text.split('\n')
    cleaned_lines = []
    skip_lines = False

    for line in lines:
        is_intermediate_line = any(indicator in line for indicator in intermediate_indicators)

        if is_intermediate_line:
            print(f"[主程序] 检测到并移除中间状态行: {line}")
            skip_lines = True
            continue

        if skip_lines and line.strip():
            skip_lines = False

        if not skip_lines:
            cleaned_lines.append(line)

    return '\n'.join(cleaned_lines).strip()


def process_single_chapter(chapter, chapters, output_dirs):
    """
    处理单个章节：生成提示词、调用 Qwen、保存回复、生成 Grok 提示词。
    """
    print(f"[主程序] 开始处理章节: {chapter}")

    sanitized_chapter_title = sanitize_filename(chapter)
    qwen_filename = f"{output_dirs['qwen']}/{sanitized_chapter_title}(qwen prompt).txt"
    grok_filename = f"{output_dirs['grok']}/{sanitized_chapter_title}(grok prompt).txt"

    if os.path.exists(grok_filename):
        print(f"[主程序] 检测到文件 '{grok_filename}' 已存在，跳过此章节。")
        return

    client = None
    try:
        client = QwenChatClient(
            headless=False,
            max_wait_time=10,
            get_response_max_wait_time=180,
            start_minimized=True
        )
        client.load_chat_page()
        print("[主程序] Qwen 页面加载完成。")

        qwen_prompt = generate_qwen_prompt(chapter)
        print(f"[主程序] 生成的 Qwen 提示词:\n{qwen_prompt}\n---")

        raw_qwen_response = client.chat(qwen_prompt)
        print(f"[主程序] 收到 Qwen 回复 (前100字符): {raw_qwen_response[:100] if raw_qwen_response else ''}...\n---")

        cleaned_response = clean_qwen_response(raw_qwen_response)

        with open(qwen_filename, 'w', encoding='utf-8') as f:
            f.write(f"章节: {chapter}\n\n")
            f.write(cleaned_response or "Qwen 未返回有效回复或处理超时。")
        print(f"[主程序] 已保存清理后的 Qwen 回复至 '{qwen_filename}'。")

        grok_prompt_content = generate_grok_prompt_from_raw(chapter, cleaned_response, chapters)

        with open(grok_filename, 'w', encoding='utf-8') as f:
            f.write(grok_prompt_content)
        print(f"[主程序] 已保存 Grok 提示词至 '{grok_filename}'。")

    except Exception as e:
        print(f"[主程序错误] 处理章节 '{chapter}' 时出错: {e}")
        # 保存错误信息到文件
        error_msg = f"处理章节 '{chapter}' 时发生错误: {e}\n"
        with open(grok_filename, 'w', encoding='utf-8') as f:
            f.write(error_msg)
        print(f"[主程序] 已保存错误信息至 '{grok_filename}'。")

    finally:
        if client:
            print("[主程序] 正在关闭浏览器实例...")
            client.close()
            print("[主程序] 浏览器实例已关闭。")


def setup_output_directories():
    """创建必要的输出目录。"""
    output_dirs = {
        "qwen": "outputs/qwen_responses",
        "grok": "outputs/grok_prompts"
    }
    for dir_path in output_dirs.values():
        os.makedirs(dir_path, exist_ok=True)
    return output_dirs


def main():
    """主函数"""
    chapters_file = 'chapters.txt'
    chapters = read_chapters(chapters_file)

    if not chapters:
        print("没有章节数据，程序退出。")
        return

    output_dirs = setup_output_directories()

    # test_chapters = [ch for ch in chapters if "第36章" in ch] # 测试用
    test_chapters = chapters  # 处理所有章节

    try:
        for i, chapter in enumerate(test_chapters):
            print(f"\n--- 开始处理章节 {i + 1}/{len(test_chapters)}: {chapter} ---")
            process_single_chapter(chapter, chapters, output_dirs)
            # --- 可选：在每个章节处理完后添加短暂延迟 ---
            # time.sleep(2)

        print("\n[主程序] 所有选定章节处理完成。")

    except KeyboardInterrupt:
        print("\n[主程序] 用户中断程序。")
    except Exception as e:
        print(f"\n[主程序] 发生未预期的严重错误: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()