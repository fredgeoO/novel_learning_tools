# novel_analyzer.py
import os
import glob
import asyncio
import ollama  # 用于本地 Ollama 模型
from qwen_chat_client import QwenChatClient  # 导入 Qwen 客户端
import re  # 用于解析月票榜文件
from chapter_utils import get_chapter_list

# --- 配置 ---
NOVELS_BASE_DIR = "novels"
PROMPTS_BASE_DIR = "inputs\\prompts\\analyzer"  # 注意：Windows 路径分隔符
REPORTS_BASE_DIR = "reports\\novels"  # 注意：Windows 路径分隔符

# --- AI 模型配置 ---
OLLAMA_MODEL_NAME = "qwen3:30b"  # 本地 Ollama 模型名称

# Qwen Web 配置
QWEN_HEADLESS = True  # 是否无头模式运行 Qwen 浏览器
QWEN_MAX_WAIT_TIME = 5
QWEN_GET_RESPONSE_MAX_WAIT_TIME = 1000
QWEN_START_MINIMIZED = True


# QWEN_DRIVER_PATH = "path/to/chromedriver.exe" # 如果需要指定 chromedriver 路径


def read_file_content(file_path, description="文件"):
    """安全地读取文件内容"""
    if not os.path.exists(file_path):
        print(f"警告: {description} '{file_path}' 不存在。")
        return None
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return f.read()
    except Exception as e:
        print(f"读取{description} '{file_path}' 时出错: {e}")
        return None


def ensure_directory_exists(dir_path):
    """确保目录存在，如果不存在则创建"""
    if not os.path.exists(dir_path):
        try:
            os.makedirs(dir_path)
            print(f"已创建目录: {dir_path}")
        except Exception as e:
            print(f"创建目录 '{dir_path}' 时出错: {e}")
            return False
    return True


def filter_think_tags(text: str) -> str:
    """过滤掉 <think>...</think> 标签及其内容"""
    # 使用 re.DOTALL 标志使 '.' 匹配换行符
    filtered_text = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL)
    # 清理多余的空行，但保留单个空行
    filtered_text = re.sub(r'\n\s*\n', '\n\n', filtered_text).strip()
    return filtered_text


# --- AI 调用函数 ---

async def call_ollama_model(prompt: str) -> str:
    """调用本地 Ollama 模型"""
    try:
        print(f"[Ollama] 正在调用模型 '{OLLAMA_MODEL_NAME}'...")
        # Ollama 的调用是同步的，但在 async 函数中可以直接调用
        response = ollama.chat(model=OLLAMA_MODEL_NAME, messages=[{'role': 'user', 'content': prompt}])
        reply = response['message']['content']
        print(f"[Ollama] 模型调用成功。")
        return reply
    except Exception as e:
        error_msg = f"[Ollama 错误] 调用模型时出错: {e}"
        print(error_msg)
        return error_msg


async def call_qwen_web_model(prompt: str) -> str:
    """调用网页版 Qwen 模型"""
    client = None
    try:
        print("[Qwen Web] 正在启动浏览器...")
        # 初始化 QwenChatClient
        client = QwenChatClient(
            headless=QWEN_HEADLESS,
            max_wait_time=QWEN_MAX_WAIT_TIME,
            get_response_max_wait_time=QWEN_GET_RESPONSE_MAX_WAIT_TIME,
            start_minimized=QWEN_START_MINIMIZED
            # driver_path=QWEN_DRIVER_PATH # 如果需要指定路径
        )
        client.load_chat_page()
        print("[Qwen Web] 浏览器启动并加载页面完成。")

        print("[Qwen Web] 正在发送消息...")
        # 调用 chat 方法发送消息并获取回复
        # 这里可以根据需要调整 enable_thinking 和 enable_search
        # 例如，如果提示词要求深度思考，可以设为 True
        response = client.chat(prompt,True,False)
        print("[Qwen Web] 消息发送并接收回复完成。")
        return response
    except Exception as e:
        error_msg = f"[Qwen Web 错误] 调用模型时出错: {e}"
        print(error_msg)
        import traceback
        traceback.print_exc()
        return error_msg  # 返回错误信息字符串
    finally:
        # 确保无论如何都关闭浏览器
        if client and client.driver:
            print("[Qwen Web] 正在关闭浏览器...")
            client.close()
            print("[Qwen Web] 浏览器已关闭。")


# --- 主分析函数 ---

async def analyze_chapter(novel_name: str, chapter_filename: str, prompt_name: str, model_type: str = "ollama"):
    """
    分析指定小说章节并生成报告。如果报告已存在，则跳过。

    :param novel_name: 小说名称 (目录名)
    :param chapter_filename: 章节文件名 (包含 .txt 扩展名)
    :param prompt_name: 提示词文件名 (不包含 .txt 扩展名)
    :param model_type: 使用的模型类型 ("ollama" 或 "qwen_web")
    """


    # 1. 构建文件路径
    chapter_file_path = os.path.join(NOVELS_BASE_DIR, novel_name, chapter_filename)
    prompt_file_path = os.path.join(PROMPTS_BASE_DIR, f"{prompt_name}.txt")
    chapter_name_without_ext = os.path.splitext(chapter_filename)[0]
    report_dir_path = os.path.join(REPORTS_BASE_DIR, novel_name, chapter_name_without_ext)
    report_file_path = os.path.join(report_dir_path, f"{prompt_name}.txt")

    # 2. 检查报告是否已经存在
    if os.path.exists(report_file_path):
        print(f"[跳过] 报告已存在: {report_file_path}")
        return True

    print(f"--- 开始分析任务 ---")
    print(f"小说: {novel_name}")
    print(f"章节: {chapter_filename}")
    print(f"提示词: {prompt_name}")
    print(f"模型: {model_type}")
    print("-" * 20)

    # 3. 读取章节内容和提示词
    chapter_content = read_file_content(chapter_file_path, "章节文件")
    if chapter_content is None:
        return False

    prompt_template = read_file_content(prompt_file_path, "提示词文件")
    if prompt_template is None:
        return False

    # 4. 合并指令 (注意占位符是 [粘贴文本内容] )
    full_prompt = prompt_template.replace("[粘贴文本内容]", chapter_content)
    print(f"[准备] 指令已生成，总长度: {len(full_prompt)} 字符")

    # 5. 调用 AI 模型
    ai_response = ""
    if model_type.lower() == "ollama":
        ai_response = await call_ollama_model(full_prompt)
    elif model_type.lower() == "qwen_web":
        ai_response = await call_qwen_web_model(full_prompt)
    else:
        print(f"错误: 不支持的模型类型 '{model_type}'")
        return False

    if not ai_response or "错误" in ai_response:  # 简单检查是否有错误
        print("错误: 未能从 AI 模型获取有效回复。")
        return False

    # 6. 过滤 <think> 标签
    filtered_response = filter_think_tags(ai_response)

    # 7. 保存报告
    if not ensure_directory_exists(report_dir_path):
        return False

    try:
        with open(report_file_path, 'w', encoding='utf-8') as f:
            f.write(filtered_response)  # 写入过滤后的内容
        print(f"[完成] 分析报告已保存至: {report_file_path}")
        return True
    except Exception as e:
        print(f"保存报告到 '{report_file_path}' 时出错: {e}")
        return False


# --- 新增的大规模处理函数 ---

async def process_top_novels_and_chapters(model_type: str = "qwen_web", top_n: int = 10, chapters_per_novel: int = 3):
    """
    大规模处理小说章节分析任务。

    :param model_type: 使用的模型类型 ("ollama" 或 "qwen_web")
    :param top_n: 处理前 N 本小说（按月票榜）
    :param chapters_per_novel: 每本小说处理前 M 章
    """
    print(f"--- 开始大规模分析任务 ---")
    print(f"模型: {model_type}")
    print(f"处理前 {top_n} 本小说，每本分析前 {chapters_per_novel} 章")
    print("-" * 30)

    # 1. 读取月票榜文件并提取小说名
    ranking_file = "scraped_data/所有分类月票榜汇总.txt"
    ranking_content = read_file_content(ranking_file, "月票榜文件")
    if not ranking_content:
        print("无法读取月票榜文件，终止任务。")
        return

    # 解析月票榜文件，提取"全部"分类下的小说名
    novel_names = []
    in_all_category = False
    current_rank = 0

    for line in ranking_content.splitlines():
        line = line.strip()
        if line.startswith("==== 全部 ===="):
            in_all_category = True
            current_rank = 0
            continue
        if in_all_category:
            if line.startswith("====") and line != "==== 全部 ====":
                # 遇到下一个分类，停止读取
                break
            # 匹配排名行，例如 " 1. 《苟在初圣魔门当人材》 - https://..."
            match = re.match(r'^\s*\d+\.\s*《(.+?)》\s*-', line)
            if match:
                current_rank += 1
                novel_name = match.group(1).strip()
                novel_names.append(novel_name)
                if current_rank >= 100:  # 最多读取100个
                    break

    if not novel_names:
        print("警告: 未从月票榜文件中解析出任何小说名称。")
        return

    selected_novels = novel_names[:top_n]
    print(f"选取的前 {top_n} 本小说: {selected_novels}")

    # 2. 获取所有提示词文件名（不含 .txt）
    if not os.path.exists(PROMPTS_BASE_DIR):
        print(f"警告: 提示词目录不存在: {PROMPTS_BASE_DIR}")
        return

    prompt_files = [f for f in os.listdir(PROMPTS_BASE_DIR) if f.endswith(".txt")]
    prompt_names = [os.path.splitext(f)[0] for f in prompt_files]

    if not prompt_names:
        print("未找到任何提示词文件，终止任务。")
        return

    print(f"加载了 {len(prompt_names)} 个提示词: {prompt_names}")

    # 3. 构建分析任务列表
    tasks_to_run = []

    for novel_name in selected_novels:
        # 使用新导入的函数
        all_chapter_files = get_chapter_list(novel_name)
        if not all_chapter_files:
            print(f"警告: 小说 '{novel_name}' 没有找到或没有可分析的章节文件。")
            continue

        # 选取前 N 章
        chapter_files = all_chapter_files[:chapters_per_novel]

        print(f"小说 '{novel_name}' 选取章节: {chapter_files}")

        for chapter_filename in chapter_files:
            for prompt_name in prompt_names:
                tasks_to_run.append({
                    "novel_name": novel_name,
                    "chapter_filename": chapter_filename,
                    "prompt_name": prompt_name,
                    "model_type": model_type
                })

    print(f"共生成 {len(tasks_to_run)} 个分析任务。")

    # 4. 异步执行所有任务
    semaphore = asyncio.Semaphore(5)  # 控制并发数防止浏览器过多或资源耗尽

    async def limited_analyze(task):
        async with semaphore:
            await analyze_chapter(**task)

    # 创建协程任务列表
    coroutines = [limited_analyze(task) for task in tasks_to_run]

    # 执行所有任务
    await asyncio.gather(*coroutines)

    print("\n--- 所有大规模分析任务执行完毕 ---")


# --- 示例用法 / 批量处理入口 ---
async def main():
    """主函数，可以在这里定义要分析的任务列表"""

    # --- 单个任务示例 ---
    # success = await analyze_chapter(
    #     novel_name="苟在初圣魔门当人材",
    #     chapter_filename="第一章 百世书.txt",
    #     prompt_name="会话与内心独白分析", # 不需要 .txt
    #     model_type="qwen_web" # 使用网页版 Qwen
    # )
    # if success:
    #     print("分析任务成功完成。")
    # else:
    #     print("分析任务失败。")

    # --- 批量任务示例 ---
    # tasks = [
    #     {
    #         "novel_name": "苟在初圣魔门当人材",
    #         "chapter_filename": "第一章 百世书.txt",
    #         "prompt_name": "会话与内心独白分析",
    #         "model_type": "qwen_web" # <-- 改为使用 qwen_web
    #     },
    #     {
    #         "novel_name": "苟在初圣魔门当人材",
    #         "chapter_filename": "第一章 百世书.txt",
    #         "prompt_name": "叙事功能单元分析法",
    #         "model_type": "qwen_web" # <-- 改为使用 qwen_web
    #     },
    #     # 可以添加更多任务，混合使用不同模型
    #     # {
    #     #     "novel_name": "苟在初圣魔门当人材",
    #     #     "chapter_filename": "第一章 百世书.txt",
    #     #     "prompt_name": "全景叙事分析",
    #     #     "model_type": "ollama" # <-- 也可以使用 ollama
    #     # },
    # ]

    # for i, task in enumerate(tasks):
    #     print(f"\n>>> 执行任务 {i+1}/{len(tasks)} <<<")
    #     await analyze_chapter(**task)
    #     # 可选：在任务之间添加短暂延迟，避免过于频繁的请求
    #     # await asyncio.sleep(2) # 例如，等待2秒

    # --- 大规模处理任务 ---
    await process_top_novels_and_chapters(
        model_type="qwen_web",  # 可改为 "ollama"
        top_n=100,  # 处理前100本小说
        chapters_per_novel=10  # 每本处理前3章
    )

    print("\n--- 所有分析任务执行完毕 ---")


if __name__ == "__main__":
    # 运行异步主函数
    asyncio.run(main())
