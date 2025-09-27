import os
import asyncio
import re
from tqdm.asyncio import tqdm  # ← 新增导入，用于 tqdm.write

from llm.qwen_chat_client import QwenChatClient
from utils.util_chapter import get_chapter_list
from utils.util_async_executor import run_limited_async_tasks
import config

# --- 配置 ---
NOVELS_BASE_DIR = "../novels"
PROMPTS_BASE_DIR = "../inputs/prompts/analyzer"
REPORTS_BASE_DIR = "../reports/novels"

OLLAMA_MODEL_NAME = config.DEFAULT_MODEL

QWEN_HEADLESS = True
QWEN_MAX_WAIT_TIME = 5
QWEN_GET_RESPONSE_MAX_WAIT_TIME = 1000
QWEN_START_MINIMIZED = True


def read_file_content(file_path, description="文件"):
    """安全地读取文件内容"""
    if not os.path.exists(file_path):
        tqdm.write(f"警告: {description} '{file_path}' 不存在。")
        return None
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return f.read()
    except Exception as e:
        tqdm.write(f"读取{description} '{file_path}' 时出错: {e}")
        return None


def ensure_directory_exists(dir_path):
    """确保目录存在，如果不存在则创建"""
    if not os.path.exists(dir_path):
        try:
            os.makedirs(dir_path)
            tqdm.write(f"已创建目录: {dir_path}")
        except Exception as e:
            tqdm.write(f"创建目录 '{dir_path}' 时出错: {e}")
            return False
    return True


def filter_think_tags(text: str) -> str:
    """过滤掉 <think>...</think> 标签及其内容"""
    filtered_text = re.sub(r'\<think\>.*?\<\/think\>', '', text, flags=re.DOTALL)
    filtered_text = re.sub(r'\n\s*\n', '\n\n', filtered_text).strip()
    return filtered_text


async def call_qwen_web_model(prompt: str) -> str:
    """调用网页版 Qwen 模型（放入线程池）"""
    def _sync_call():
        client = None
        try:
            #tqdm.write("[Qwen Web] 正在启动浏览器...")
            client = QwenChatClient(
                headless=QWEN_HEADLESS,
                max_wait_time=QWEN_MAX_WAIT_TIME,
                get_response_max_wait_time=QWEN_GET_RESPONSE_MAX_WAIT_TIME,
                start_minimized=QWEN_START_MINIMIZED
            )
            client.load_chat_page()
            #tqdm.write("[Qwen Web] 浏览器启动并加载页面完成。")
            response = client.chat(prompt, True, False)
            #tqdm.write("[Qwen Web] 消息发送并接收回复完成。")
            return response
        except Exception as e:
            error_msg = f"[Qwen Web 错误] 调用模型时出错: {e}"
            #tqdm.write(error_msg)
            import traceback
            #tqdm.write(traceback.format_exc())
            return error_msg
        finally:
            if client and client.driver:
                #tqdm.write("[Qwen Web] 正在关闭浏览器...")
                client.close()
                #tqdm.write("[Qwen Web] 浏览器已关闭。")

    try:
        response = await asyncio.to_thread(_sync_call)
        return response
    except Exception as e:
        error_msg = f"[Qwen Web 异步包装错误]: {e}"
        tqdm.write(error_msg)
        return error_msg


async def analyze_chapter(novel_name: str, chapter_filename: str, prompt_name: str, model_type: str = "ollama"):
    chapter_file_path = os.path.join(NOVELS_BASE_DIR, novel_name, chapter_filename)
    prompt_file_path = os.path.join(PROMPTS_BASE_DIR, f"{prompt_name}.txt")
    chapter_name_without_ext = os.path.splitext(chapter_filename)[0]
    report_dir_path = os.path.join(REPORTS_BASE_DIR, novel_name, chapter_name_without_ext)
    report_file_path = os.path.join(report_dir_path, f"{prompt_name}.txt")

    if os.path.exists(report_file_path):
        #tqdm.write(f"[跳过] 报告已存在: {report_file_path}")
        return True

    #tqdm.write(f"--- 开始分析任务 ---")
    #tqdm.write(f"小说: {novel_name}")
    #tqdm.write(f"章节: {chapter_filename}")
    #tqdm.write(f"提示词: {prompt_name}")
    #tqdm.write(f"模型: {model_type}")
    #tqdm.write("-" * 20)

    chapter_content = read_file_content(chapter_file_path, "章节文件")
    if chapter_content is None:
        return False

    prompt_template = read_file_content(prompt_file_path, "提示词文件")
    if prompt_template is None:
        return False

    full_prompt = prompt_template.replace("[粘贴文本内容]", chapter_content)
    # tqdm.write(f"[准备] 指令已生成，总长度: {len(full_prompt)} 字符")

    ai_response = ""
    if model_type.lower() == "ollama":
        pass
    elif model_type.lower() == "qwen_web":
        ai_response = await call_qwen_web_model(full_prompt)
    else:
        tqdm.write(f"错误: 不支持的模型类型 '{model_type}'")
        return False

    if not ai_response or "错误" in ai_response:
        tqdm.write("错误: 未能从 AI 模型获取有效回复。")
        return False

    filtered_response = filter_think_tags(ai_response)

    if not ensure_directory_exists(report_dir_path):
        return False

    try:
        with open(report_file_path, 'w', encoding='utf-8') as f:
            f.write(filtered_response)
        #tqdm.write(f"[完成] 分析报告已保存至: {report_file_path}")
        return True
    except Exception as e:
        tqdm.write(f"保存报告到 '{report_file_path}' 时出错: {e}")
        return False


async def process_top_novels_and_chapters(model_type: str = "qwen_web", top_n: int = 10, chapters_per_novel: int = 3):
    tqdm.write(f"--- 开始大规模分析任务 ---")
    tqdm.write(f"模型: {model_type}")
    tqdm.write(f"处理前 {top_n} 本小说，每本分析前 {chapters_per_novel} 章")
    tqdm.write("-" * 30)

    ranking_file = "../scraped_data/所有分类月票榜汇总.txt"
    ranking_content = read_file_content(ranking_file, "月票榜文件")
    if not ranking_content:
        tqdm.write("无法读取月票榜文件，终止任务。")
        return

    novel_names = []
    lines = ranking_content.splitlines()
    in_any_category = False

    for line in lines:
        line = line.strip()
        if line.startswith("====") and line.endswith("===="):
            in_any_category = True
            continue
        if in_any_category:
            match = re.match(r'^\s*\d+\.\s*《(.+?)》\s*-', line)
            if match:
                novel_name = match.group(1).strip()
                if novel_name and novel_name not in novel_names:
                    novel_names.append(novel_name)
                if len(novel_names) >= top_n:
                    break

    selected_novels = novel_names[:top_n]
    if not selected_novels:
        tqdm.write("警告: 未从月票榜文件中解析出任何小说名称。")
        return

    tqdm.write(f"选取的前 {len(selected_novels)} 本小说: {selected_novels}")

    if not os.path.exists(PROMPTS_BASE_DIR):
        tqdm.write(f"警告: 提示词目录不存在: {PROMPTS_BASE_DIR}")
        return

    prompt_files = [f for f in os.listdir(PROMPTS_BASE_DIR) if f.endswith(".txt")]
    prompt_names = [os.path.splitext(f)[0] for f in prompt_files]

    if not prompt_names:
        tqdm.write("未找到任何提示词文件，终止任务。")
        return

    tqdm.write(f"加载了 {len(prompt_names)} 个提示词: {prompt_names}")

    tasks_to_run = []
    for novel_name in selected_novels:
        all_chapter_files = get_chapter_list(novel_name)
        if not all_chapter_files:
            tqdm.write(f"警告: 小说 '{novel_name}' 没有找到或没有可分析的章节文件。")
            continue

        chapter_files = all_chapter_files[:chapters_per_novel]
        tqdm.write(f"小说 '{novel_name}' 选取章节: {chapter_files}")

        for chapter_filename in chapter_files:
            for prompt_name in prompt_names:
                tasks_to_run.append({
                    "novel_name": novel_name,
                    "chapter_filename": chapter_filename,
                    "prompt_name": prompt_name,
                    "model_type": model_type
                })

    tqdm.write(f"共生成 {len(tasks_to_run)} 个分析任务。")

    def should_skip(task):
        novel = task["novel_name"]
        chapter = task["chapter_filename"]
        prompt = task["prompt_name"]
        report_path = os.path.join(
            REPORTS_BASE_DIR,
            novel,
            os.path.splitext(chapter)[0],
            f"{prompt}.txt"
        )
        exists = os.path.exists(report_path)
        if exists:
            tqdm.write(f"[跳过] 报告已存在: {report_path}")
        return exists

    async def run_single_task(task):
        return await analyze_chapter(**task)

    results = await run_limited_async_tasks(
        tasks=tasks_to_run,
        task_func=run_single_task,
        skip_if_exists=should_skip,
        max_concurrent=8,
        min_interval=5.0,
        rate_limit_key="qwen_web"
    )

    success_count = sum(results)
    tqdm.write(f"\n--- 所有大规模分析任务执行完毕: {success_count}/{len(tasks_to_run)} 成功 ---")


async def main():
    await process_top_novels_and_chapters(
        model_type="qwen_web",
        top_n=100,
        chapters_per_novel=100
    )


if __name__ == "__main__":
    asyncio.run(main())