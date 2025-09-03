# generate_articles.py
import os
from qwen_chat_client import QwenChatClient # 确保 qwen_chat_client.py 在同一目录或 PYTHONPATH 中

# --- 配置 ---
INPUT_PROMPTS_DIR = "inputs/prompts"
GROK_PROMPTS_DIR = "outputs/grok_prompts"
OUTPUT_ARTICLES_DIR = "outputs/articles"

# 定义需要读取的三个输入提示词文件名
INPUT_PROMPT_FILES = [
    "提示词：元叙事核心设定.txt",
    "提示词：讨论话题_V02.txt",
    "提示词：输出作家的话.txt"
]
# --- 配置结束 ---


def read_file_content(filepath, encoding='utf-8'):
    """读取文件内容"""
    try:
        with open(filepath, 'r', encoding=encoding) as f:
            return f.read()
    except FileNotFoundError:
        print(f"[错误] 找不到文件: {filepath}")
        return None
    except Exception as e:
        print(f"[错误] 读取文件 '{filepath}' 时出错: {e}")
        return None

def sanitize_filename(text):
    """清理文本，使其可以安全地用作文件名。"""
    invalid_chars = '<>:"/\\|?*'
    for char in invalid_chars:
        text = text.replace(char, '_')
    text = text.strip('. ')
    return text[:150] # 限制长度

def process_grok_prompt_file(grok_file_path, input_prompts_content, qwen_client):
    """
    处理单个 Grok 提示词文件：拼接提示词，调用 Qwen，保存结果。
    :param grok_file_path: Grok 提示词文件的完整路径
    :param input_prompts_content: 三个输入提示词拼接后的字符串
    :param qwen_client: 已初始化的 QwenChatClient 实例
    """
    print(f"\n[处理] 开始处理 Grok 文件: {os.path.basename(grok_file_path)}")

    # 1. 读取 Grok 提示词内容
    grok_content = read_file_content(grok_file_path)
    if grok_content is None:
        print(f"[处理] 跳过文件 {os.path.basename(grok_file_path)} (无法读取)")
        return

    # 2. 拼接最终提示词 (输入提示词 + Grok 提示词)
    # 您可以根据需要调整拼接顺序和分隔符
    final_prompt = f"{input_prompts_content}\n\n--- 以下是 Grok 提示词 ---\n\n{grok_content}"
    print(f"[处理] 已生成最终提示词 (总长度: {len(final_prompt)} 字符)")

    # 3. 生成输出文件名 (基于 Grok 文件名)
    grok_filename = os.path.basename(grok_file_path)
    # 移除 "(grok prompt).txt" 部分，得到章节信息
    if grok_filename.endswith("(grok prompt).txt"):
        base_name = grok_filename[:-len("(grok prompt).txt")]
    else:
        base_name = grok_filename # Fallback

    sanitized_base_name = sanitize_filename(base_name)
    output_filename = f"{sanitized_base_name}(generated_article).txt"
    output_file_path = os.path.join(OUTPUT_ARTICLES_DIR, output_filename)

    # 4. 检查输出文件是否已存在
    if os.path.exists(output_file_path):
        print(f"[处理] 检测到输出文件 '{output_filename}' 已存在，跳过。")
        return

    # 5. 调用 Qwen (修改点1: 禁用深度思考)
    try:
        print("[处理] 正在调用 Qwen (已禁用深度思考)...")
        # --- 修改点1：enable_thinking=False ---
        qwen_response = qwen_client.chat(final_prompt, enable_thinking=False, enable_search=False)
        # --- ---
        print("[处理] 已收到来自 Qwen 的回复。")

        # 6. 保存结果 (修改点2: 只保存回复内容)
        # --- 修改点2：只写入 qwen_response ---
        with open(output_file_path, 'w', encoding='utf-8') as f:
            f.write(qwen_response)
        # --- ---
        print(f"[处理] 已保存文章内容至 '{output_file_path}'")
    except Exception as e:
        print(f"[处理错误] 调用 Qwen 或保存文件时出错 ({grok_file_path}): {e}")
        # 可以选择保存错误信息到文件
        error_output_path = output_file_path.replace(".txt", "_ERROR.txt")
        with open(error_output_path, 'w', encoding='utf-8') as f:
            f.write(f"处理文件时出错: {grok_file_path}\n错误信息: {e}\n")
        print(f"[处理错误] 已保存错误信息至 '{error_output_path}'")


def main():
    """主函数"""
    print("[主程序] 开始生成文章流程...")

    # 1. 确保输出目录存在
    os.makedirs(OUTPUT_ARTICLES_DIR, exist_ok=True)
    print(f"[主程序] 确保输出目录 '{OUTPUT_ARTICLES_DIR}' 存在。")

    # 2. 读取并拼接三个输入提示词
    print("[主程序] 正在读取输入提示词...")
    input_prompts_content_parts = []
    for filename in INPUT_PROMPT_FILES:
        file_path = os.path.join(INPUT_PROMPTS_DIR, filename)
        content = read_file_content(file_path)
        if content is not None:
            input_prompts_content_parts.append(content)
            print(f"[主程序] 已读取 '{filename}'")
        else:
            print(f"[主程序] 警告: 无法读取 '{filename}'，将作为空内容处理。")

    # 使用两个换行符连接各部分
    input_prompts_content = "\n\n".join(input_prompts_content_parts)
    if not input_prompts_content.strip():
        print("[主程序] 错误: 未能成功读取任何输入提示词内容。")
        return
    print(f"[主程序] 输入提示词读取完成 (总长度: {len(input_prompts_content)} 字符)。")

    # 3. 初始化 Qwen 客户端 (根据需要调整参数)
    print("[主程序] 正在初始化 Qwen 客户端...")
    qwen_client = QwenChatClient(
        headless=False,
        max_wait_time=10,
        get_response_max_wait_time=180, # 根据生成文章的复杂度调整
        start_minimized=True
    )
    try:
        qwen_client.load_chat_page()
        print("[主程序] Qwen 客户端初始化完成。")

        # 4. 遍历 Grok 提示词目录中的所有 .txt 文件
        if not os.path.exists(GROK_PROMPTS_DIR):
            print(f"[主程序] 错误: Grok 提示词目录 '{GROK_PROMPTS_DIR}' 不存在。")
            return

        grok_files = [f for f in os.listdir(GROK_PROMPTS_DIR) if f.endswith('.txt')]
        if not grok_files:
             print(f"[主程序] 警告: 在 '{GROK_PROMPTS_DIR}' 目录中未找到 .txt 文件。")
             return

        print(f"[主程序] 找到 {len(grok_files)} 个 Grok 提示词文件待处理。")

        for i, grok_filename in enumerate(grok_files):
            grok_file_path = os.path.join(GROK_PROMPTS_DIR, grok_filename)
            print(f"\n--- 文件 {i+1}/{len(grok_files)} ---")
            process_grok_prompt_file(grok_file_path, input_prompts_content, qwen_client)

        print("\n[主程序] 所有 Grok 文件处理完成。")

    except Exception as e:
        print(f"[主程序错误] 初始化 Qwen 客户端或处理文件时发生错误: {e}")
        import traceback
        traceback.print_exc()
    finally:
        # 5. 确保关闭 Qwen 客户端
        if 'qwen_client' in locals() and qwen_client:
            print("\n[主程序] 正在关闭 Qwen 客户端...")
            qwen_client.close()
            print("[主程序] Qwen 客户端已关闭。")

    print("\n[主程序] 文章生成流程结束。")


if __name__ == "__main__":
    main()