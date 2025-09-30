import asyncio
import json
import re
from crawl4ai import AsyncWebCrawler, CrawlerRunConfig
from html2text import HTML2Text


def extract_first_json(text: str) -> str:
    """从文本中提取第一个合法的 JSON 对象（最外层 {} 匹配）"""
    start = None
    brace_count = 0
    for i, char in enumerate(text):
        if char == '{':
            if brace_count == 0:
                start = i
            brace_count += 1
        elif char == '}':
            if brace_count > 0:
                brace_count -= 1
                if brace_count == 0 and start is not None:
                    candidate = text[start:i + 1]
                    try:
                        json.loads(candidate)
                        return candidate
                    except json.JSONDecodeError:
                        start = None
    return text  # 未找到合法 JSON，返回原文


async def send_message_and_get_response(
    message: str,
    enable_thinking: bool = True,
    enable_search: bool = True,
    headless: bool = True,
    max_wait_seconds: int = 180,
) -> str:
    """
    使用 Crawl4AI 与 Qwen 网页版交互，发送消息并获取回复。
    """
    session_id = "qwen_chat_session"

    # Step 1: 加载页面 + 关闭登录弹窗
    init_js = """
    // 自动关闭登录弹窗
    const logoutBtn = document.querySelector('button:contains("保持注销状态")');
    if (logoutBtn) logoutBtn.click();
    """

    # 注意：querySelector 不支持 :contains，需用 JS 查找
    init_js = """
    (() => {
        const buttons = Array.from(document.querySelectorAll('button'));
        const logoutBtn = buttons.find(btn => btn.textContent.trim() === '保持注销状态');
        if (logoutBtn) {
            logoutBtn.click();
            console.log('[Crawl4AI] 已点击“保持注销状态”');
        }
    })();
    """

    config1 = CrawlerRunConfig(
        session_id=session_id,
        js_code=init_js,
        wait_for="css:#chat-input",  # 等待输入框出现
        page_timeout=max_wait_seconds * 1000,
    )

    async with AsyncWebCrawler() as crawler:
        # 初始加载
        result = await crawler.arun(
            url="https://chat.qwen.ai/",
            config=config1
        )

        # Step 2: 准备发送消息的 JS
        js_commands = []

        # 点击“深度思考”按钮（如果启用）
        if enable_thinking:
            js_commands.append("""
            (() => {
                const buttons = Array.from(document.querySelectorAll('button'));
                const thinkBtn = buttons.find(btn => btn.textContent.includes('深度思考'));
                if (thinkBtn && !thinkBtn.disabled) {
                    thinkBtn.click();
                    console.log('[Crawl4AI] 已点击“深度思考”');
                }
            })();
            """)

        # 点击“搜索”按钮（如果启用）
        if enable_search:
            js_commands.append("""
            (() => {
                const buttons = Array.from(document.querySelectorAll('button'));
                const searchBtn = buttons.find(btn => btn.textContent.includes('搜索'));
                if (searchBtn && !searchBtn.disabled) {
                    searchBtn.click();
                    console.log('[Crawl4AI] 已点击“搜索”');
                }
            })();
            """)

        # 输入消息（支持换行）
        # 使用 set value + dispatch input event
        escaped_message = json.dumps(message)  # 自动转义换行和引号
        js_commands.append(f"""
        (() => {{
            const input = document.querySelector('#chat-input');
            if (input) {{
                input.value = {escaped_message};
                input.dispatchEvent(new Event('input', {{ bubbles: true }}));
                console.log('[Crawl4AI] 已输入消息');
            }}
        }})();
        """)

        # 提交消息
        js_commands.append("""
        (() => {
            const input = document.querySelector('#chat-input');
            if (input) {
                const event = new KeyboardEvent('keydown', {
                    key: 'Enter',
                    code: 'Enter',
                    bubbles: true
                });
                input.dispatchEvent(event);
                console.log('[Crawl4AI] 已提交消息');
            }
        })();
        """)

        # Step 3: 执行发送 + 等待回复稳定
        wait_js_condition = f"""
        (() => {{
            const container = document.querySelector('#response-message-body > div.text-response-render-container');
            if (!container) return false;

            const text = container.innerText || '';
            const hasThinkingStart = text.includes('正在思考与搜索') || text.includes('tokens 预算');
            const hasThinkingEnd = text.includes('思考与搜索已完成');

            // 如果处于中间状态，继续等待
            if (hasThinkingStart && !hasThinkingEnd) return false;

            // 回复长度需超过阈值（避免空或加载中）
            if (text.trim().length < 50) return false;

            // 等待内容稳定：检查是否还在变化（简单策略：等待一段时间无变化）
            // Crawl4AI 无法直接检测“稳定”，我们用 delay_before_return_html + 最终判断
            return true;
        }})();
        """

        config2 = CrawlerRunConfig(
            session_id=session_id,
            js_code=js_commands,
            wait_for=f"js:{wait_js_condition}",
            js_only=True,
            page_timeout=max_wait_seconds * 1000,
            delay_before_return_html=5.0,  # 额外等待 5 秒确保稳定

        )

        result2 = await crawler.arun(
            url="https://chat.qwen.ai/",
            config=config2
        )

        # Step 4: 提取并清洗回复
        html_content = result2.cleaned_html or result2.html

        # 使用 html2text 转为 Markdown（类似原逻辑）
        h = HTML2Text()
        h.body_width = 0
        h.ignore_links = True
        h.ignore_images = True
        h.ignore_emphasis = False
        markdown_text = h.handle(html_content)

        # 后处理：移除中间状态文本（保险起见）
        lines = markdown_text.splitlines()
        filtered_lines = []
        skip = False
        for line in lines:
            stripped = line.strip()
            if stripped in ["正在思考与搜索", "思考与搜索已完成"] or "tokens 预算" in stripped:
                skip = True
                continue
            if skip and stripped == "":
                skip = False
                continue
            if not skip:
                filtered_lines.append(line)
        final_text = "\n".join(filtered_lines).strip()

        # Step 5: 尝试提取 JSON
        extracted = extract_first_json(final_text)
        return extracted


# --- 示例用法 ---
async def main():
    try:
        response = await send_message_and_get_response(
            message="请介绍量子物理，用 JSON 格式输出，包含字段：概念、原理、应用。",
            enable_thinking=False,
            enable_search=False,
            headless=True,
            max_wait_seconds=180
        )
        print("Qwen 回复:\n", response)
    except Exception as e:
        print(f"错误: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())