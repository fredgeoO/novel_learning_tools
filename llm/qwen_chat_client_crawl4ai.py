import atexit
import glob
import json
import time
import tempfile
import html2text
import re
import os
import shutil
import asyncio
import uuid  # 需要在此处导入，因为 _setup_user_data_dir 用到了它
# 从主模块导入
from crawl4ai import AsyncWebCrawler, BrowserConfig
# 导入 CrawlerRunConfig 用于 arun 参数
from crawl4ai import CrawlerRunConfig
# 注意：DefaultMarkdownGenerator 和 PruningContentFilter 的导入可能需要根据具体版本调整
# 如果默认策略足够，可以移除此行及后续相关代码
# from crawl4ai import DefaultMarkdownGenerator, PruningContentFilter
from crawl4ai import CacheMode  # 导入 CacheMode 用于 arun


def cleanup_temp_profiles():
    """清理临时配置文件"""
    temp_dir = tempfile.gettempdir()
    pattern = os.path.join(temp_dir, "qwen_crawl4ai_profile_*")
    for folder in glob.glob(pattern):
        try:
            shutil.rmtree(folder)
        except Exception:
            pass


atexit.register(cleanup_temp_profiles)


def filter_qwen_output(text: str, intermediate_indicators, thinking_completed_indicator) -> str:
    """过滤掉 Qwen 输出中的中间状态信息"""
    if not text:
        return text
    lines = text.splitlines()
    filtered_lines = []
    skip_until_empty = False
    for line in lines:
        line_stripped = line.strip()
        if line_stripped in intermediate_indicators or line_stripped == thinking_completed_indicator:
            skip_until_empty = True
            continue
        if skip_until_empty and line_stripped:
            continue
        elif skip_until_empty and not line_stripped:
            skip_until_empty = False
            continue
        is_intermediate = any(indicator in line for indicator in intermediate_indicators)
        is_completed_indicator = thinking_completed_indicator in line
        if is_intermediate or is_completed_indicator:
            continue
        filtered_lines.append(line)
    result = "\n".join(filtered_lines)
    return result.strip()


class QwenChatClientCrawl4AI:
    """
    使用 Crawl4AI 与 Qwen 网页版聊天的客户端
    """

    # 常量定义
    THINKING_COMPLETED_INDICATOR = "思考与搜索已完成"
    INTERMEDIATE_INDICATORS = ["正在思考与搜索", "tokens 预算"]
    DEFAULT_MAX_WAIT_TIME = 300
    DEFAULT_BROWSER_TYPE = "chromium"  # crawl4ai 支持的浏览器类型

    # CSS 选择器
    CHAT_INPUT_SELECTOR = "#chat-input"
    RESPONSE_CONTAINER_SELECTOR = "#response-message-body > div.text-response-render-container"
    MAIN_CONTENT_CONTAINER_SELECTOR = ".markdown-content-container.markdown-prose"
    DEEP_THINKING_BUTTON_SELECTOR = "button:has-text('深度思考')"
    SEARCH_BUTTON_SELECTOR = "button:has-text('搜索')"
    LOGIN_POPUP_BUTTON_SELECTOR = "button:has-text('保持注销状态')"

    def __init__(self, headless=True, max_wait_time=DEFAULT_MAX_WAIT_TIME,
                 browser_type=DEFAULT_BROWSER_TYPE):
        self.headless = headless
        self.max_wait_time = max_wait_time
        self.browser_type = browser_type
        self.crawler = None
        self._closed = False
        self.user_data_dir = None
        self.session_id = f"qwen_session_{uuid.uuid4().hex[:8]}"  # 创建一个会话 ID

    async def __aenter__(self):
        await self._create_crawler()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()

    def _setup_user_data_dir(self):
        """为每个实例创建唯一的用户数据目录"""
        system_temp_dir = tempfile.gettempdir()
        unique_dir_name = f"qwen_crawl4ai_profile_{uuid.uuid4().hex[:8]}"
        user_data_dir_path = os.path.join(system_temp_dir, unique_dir_name)

        try:
            os.makedirs(user_data_dir_path, exist_ok=True)
        except Exception as e:
            raise

        self.user_data_dir = user_data_dir_path
        return user_data_dir_path

    async def _create_crawler(self):
        """创建 Crawl4AI 爬虫实例"""
        try:
            # 配置浏览器 (BrowserConfig 从主模块导入)
            browser_config = BrowserConfig(
                headless=self.headless,
                browser_type=self.browser_type,
                user_data_dir=self._setup_user_data_dir(),  # 假设 _setup_user_data_dir 已定义或在此前调用
                extra_args=[
                    "--disable-blink-features=AutomationControlled",
                    "--disable-infobars",
                    "--lang=zh-CN"
                ]
            )

            # --- 关键修改 ---
            # 不再使用 CrawlerConfig。
            # BrowserConfig 现在在创建 AsyncWebCrawler 时传递
            # 初始化 AsyncWebCrawler 实例，传入 browser_config
            self.crawler = AsyncWebCrawler(config=browser_config)

            # 启动爬虫，不再需要传递 browser_config
            await self.crawler.start()  # start() 不再接受 browser_config 参数

        except Exception as e:
            print(f"Error creating crawler: {e}")  # 添加错误信息打印
            raise  # 重新抛出异常

    async def close(self):
        """关闭爬虫"""
        if self._closed:
            return

        self._closed = True

        if self.crawler:
            try:
                await self.crawler.close()
            except Exception:
                pass
            finally:
                self.crawler = None

    async def load_chat_page(self, url="https://chat.qwen.ai/"):
        """导航到 Qwen 聊天页面"""
        url = url.strip()
        try:
            # 使用 crawl4ai 访问页面
            # 注意：arun 通常需要一个 URL
            result = await self.crawler.arun(
                url=url,
                session_id=self.session_id,  # 使用会话 ID
                # 将以前 CrawlerConfig 的参数传递给 CrawlerRunConfig
                config=CrawlerRunConfig(
                    # word_count_threshold=10, # CrawlerRunConfig 可能包含此参数
                    # link_density_threshold=0.3, # CrawlerRunConfig 可能包含此参数
                    # timeout=self.max_wait_time * 1000, # CrawlerRunConfig 可能包含此参数，单位为毫秒
                    # markdown_generator=DefaultMarkdownGenerator( # 如果需要特定策略
                    #     content_filter=PruningContentFilter()
                    # ),
                    css_selector=self.CHAT_INPUT_SELECTOR,  # 等待输入框加载
                    wait_for=self.CHAT_INPUT_SELECTOR
                )
            )

            if not result.success:
                raise Exception(f"页面加载失败: {result.error_message}")

            # 处理登录弹窗 - 使用 arun 传递 JS 代码来点击
            await self._handle_login_popup()

        except Exception as e:
            raise Exception(f"页面加载错误: {e}") from e

    async def _handle_login_popup(self):
        """检查并处理'保持注销状态'弹窗 - 使用 JS 代码"""
        try:
            # 尝试点击登录弹窗的保持注销状态按钮
            # 使用 arun 传递 JS 代码
            js_code_to_click_popup = [
                f"""
                (async () => {{
                    const button = document.querySelector('{self.LOGIN_POPUP_BUTTON_SELECTOR}');
                    if (button && button.offsetParent !== null) {{ // 检查按钮是否存在且可见
                        button.scrollIntoView({{block: 'center'}});
                        await new Promise(r => setTimeout(r, 200)); // 短暂延迟
                        button.click();
                        console.log('Clicked login popup button');
                    }} else {{
                        console.log('Login popup button not found or not visible');
                    }}
                }})();
                """
            ]
            # 在当前会话中执行 JS 代码，不重新加载页面
            result = await self.crawler.arun(
                url="https://chat.qwen.ai/",  # URL 可能被忽略，因为我们使用 js_only=True 和 session_id
                session_id=self.session_id,  # 使用同一个会话 ID
                config=CrawlerRunConfig(
                    js_code=js_code_to_click_popup,
                    js_only=True,  # 只执行 JS，不重新爬取
                    cache_mode=CacheMode.BYPASS  # 旁路缓存
                )
            )
            await asyncio.sleep(0.2)  # 点击后稍等
            return result.success
        except Exception as e:
            print(f"Handle login popup failed: {e}")  # 添加调试信息
            return False

    async def _click_feature_button(self, selector, button_name):
        """点击功能按钮（如深度思考、搜索） - 使用 JS 代码"""
        try:
            # 使用 arun 传递 JS 代码来点击按钮
            js_code_to_click_button = [
                f"""
                (async () => {{
                    const button = document.querySelector('{selector}');
                    if (button && button.offsetParent !== null) {{ // 检查按钮是否存在且可见
                        button.scrollIntoView({{block: 'center'}});
                        await new Promise(r => setTimeout(r, 200)); // 短暂延迟
                        button.click();
                        console.log('Clicked {button_name} button');
                    }} else {{
                        console.log('{button_name} button not found or not visible');
                    }}
                }})();
                """
            ]
            # 在当前会话中执行 JS 代码，不重新加载页面
            result = await self.crawler.arun(
                url="https://chat.qwen.ai/",  # URL 可能被忽略，因为我们使用 js_only=True 和 session_id
                session_id=self.session_id,  # 使用同一个会话 ID
                config=CrawlerRunConfig(
                    js_code=js_code_to_click_button,
                    js_only=True,  # 只执行 JS，不重新爬取
                    cache_mode=CacheMode.BYPASS  # 旁路缓存
                )
            )
            await asyncio.sleep(0.3)  # 点击后稍等
            return result.success
        except Exception as e:
            print(f"Click {button_name} button failed: {e}")  # 添加调试信息
            return False

    async def send_message(self, message, enable_thinking=True, enable_search=True):
        """发送消息到 Qwen - 使用 JS 代码"""
        try:
            message_len = len(message)

            # 处理登录弹窗
            await self._handle_login_popup()

            # 点击功能按钮
            if enable_thinking:
                await self._click_feature_button(self.DEEP_THINKING_BUTTON_SELECTOR, "深度思考")

            if enable_search:
                await self._click_feature_button(self.SEARCH_BUTTON_SELECTOR, "搜索")

            # --- 修正部分：预先处理消息内容 ---
            # 转义单引号，避免在 JS 字符串中破坏语法
            escaped_message = message.replace("'", "\\'")
            # 或者，也可以转义反斜杠和双引号，以应对更复杂的情况
            # escaped_message = json.dumps(message)[1:-1] # 使用 json.dumps 然后去掉首尾引号

            # 使用 arun 传递 JS 代码来输入消息并提交
            js_code_to_send_message = [
                f"""
                (async () => {{
                    const input = document.querySelector('{self.CHAT_INPUT_SELECTOR}');
                    if (input) {{
                        input.focus();
                        input.value = '{escaped_message}'; // 使用已转义的消息
                        // 触发 input 事件，某些应用可能需要
                        const event = new Event('input', {{ bubbles: true }});
                        input.dispatchEvent(event);
                        console.log('Message entered into chat input');
                    }} else {{
                        console.log('Chat input not found');
                    }}
                }})();
                """,
                f"""
                (async () => {{
                    const input = document.querySelector('{self.CHAT_INPUT_SELECTOR}');
                    if (input) {{
                         // 模拟按下 Enter 键
                        const event = new KeyboardEvent('keydown', {{
                            key: 'Enter',
                            code: 'Enter',
                            keyCode: 13,
                            which: 13,
                            bubbles: true
                        }});
                        input.dispatchEvent(event);
                        console.log('Enter key pressed');
                    }} else {{
                        console.log('Chat input not found for Enter press');
                    }}
                }})();
                """
            ]

            # 在当前会话中执行 JS 代码，不重新加载页面
            result = await self.crawler.arun(
                url="https://chat.qwen.ai/",  # URL 可能被忽略，因为我们使用 js_only=True 和 session_id
                session_id=self.session_id,  # 使用同一个会话 ID
                config=CrawlerRunConfig(
                    js_code=js_code_to_send_message,
                    js_only=True,  # 只执行 JS，不重新爬取
                    cache_mode=CacheMode.BYPASS  # 旁路缓存
                )
            )

            if not result.success:
                raise Exception("Failed to send message via JS")

            await asyncio.sleep(1.5)  # 等待页面状态稳定

        except Exception as e:
            raise Exception(f"发送消息错误: {e}") from e

    async def _wait_for_response_start(self):
        """等待回复开始 - 使用 JS 代码检查元素"""
        start_time = time.time()

        while time.time() - start_time < self.max_wait_time:
            try:
                # 使用 arun 等待响应容器出现
                result = await self.crawler.arun(
                    url="https://chat.qwen.ai/",  # URL 可能被忽略，因为我们使用 js_only=True 和 session_id
                    session_id=self.session_id,  # 使用同一个会话 ID
                    config=CrawlerRunConfig(
                        wait_for=self.RESPONSE_CONTAINER_SELECTOR,  # 等待选择器出现
                        timeout=self.max_wait_time * 1000,  # 设置等待超时
                        cache_mode=CacheMode.BYPASS  # 旁路缓存
                    )
                )
                if result.success:
                    print("Response container appeared.")
                    return True  # 找到元素，返回
            except Exception as e:
                print(f"Wait for response start error (using wait_for): {e}")  # 添加调试信息
                pass  # 可能 wait_for 超时，继续循环

            await asyncio.sleep(1)

        raise TimeoutError("等待回复开始超时")

    async def _wait_for_response_completion(self):
        """等待回复完成 - 使用 JS 代码检查内容是否稳定"""
        start_time = time.time()
        last_content = ""
        stable_count = 0
        required_stable_time = 4.0  # 内容稳定4秒认为完成

        while time.time() - start_time < self.max_wait_time:
            try:
                # 使用 arun 获取当前回复内容
                result = await self.crawler.arun(
                    url="https://chat.qwen.ai/",  # URL 可能被忽略，因为我们使用 js_only=True 和 session_id
                    session_id=self.session_id,  # 使用同一个会话 ID
                    config=CrawlerRunConfig(
                        js_code=[f"document.querySelector('{self.RESPONSE_CONTAINER_SELECTOR}').innerText || ''"],
                        cache_mode=CacheMode.BYPASS  # 旁路缓存
                    )
                )
                if result.success and result.extracted_content:  # 检查是否有提取内容
                    # extracted_content 是一个列表，包含 js_code 的执行结果
                    current_content = result.extracted_content[0].get('content', '') if result.extracted_content else ''
                else:
                    current_content = ""  # 如果获取失败，设为空

                # 检查内容是否稳定
                if current_content == last_content:
                    stable_count += 1
                else:
                    stable_count = 0
                    last_content = current_content

                print(f"Content length: {len(current_content)}, Stable count: {stable_count}")  # 调试信息

                # 如果内容稳定达到要求时间，认为回复完成
                if stable_count >= required_stable_time:
                    print("Response seems complete.")
                    return True

            except Exception as e:
                print(f"Wait for response completion error: {e}")  # 添加调试信息
                pass

            await asyncio.sleep(1)

        print("Timed out waiting for response completion.")
        return False

    async def get_response(self, enable_thinking=True):
        """等待并获取 Qwen 的回复"""
        try:
            # 等待回复开始
            await self._wait_for_response_start()

            # 等待回复完成
            await self._wait_for_response_completion()

            # 获取最终回复内容
            # 注意：arun 通常需要一个 URL，这里可能需要获取当前页面 URL 或根据实际情况调整
            current_page_url = "https://chat.qwen.ai/"  # 使用当前页面 URL 或之前保存的
            result = await self.crawler.arun(
                url=current_page_url,  # 使用当前页面 URL
                session_id=self.session_id,  # 使用同一个会话 ID
                # 将以前 CrawlerConfig 的参数传递给 CrawlerRunConfig
                config=CrawlerRunConfig(
                    # word_count_threshold=10, # CrawlerRunConfig 可能包含此参数
                    # link_density_threshold=0.3, # CrawlerRunConfig 可能包含此参数
                    # timeout=self.max_wait_time * 1000, # CrawlerRunConfig 可能包含此参数，单位为毫秒
                    # markdown_generator=DefaultMarkdownGenerator( # 如果需要特定策略
                    #     content_filter=PruningContentFilter()
                    # ),
                    css_selector=self.RESPONSE_CONTAINER_SELECTOR,
                    excluded_selectors=[".citation-button-wrap", ".seletected-text-content"],
                    wait_for_timeout=5000  # 额外等待5秒确保内容稳定
                )
            )

            if result.success and result.markdown:
                # 提取第一个合法的 JSON 对象
                cleaned_response = self._extract_json_from_text(result.markdown)
                return cleaned_response
            else:
                print(
                    f"Get response failed or markdown empty. Success: {result.success}, Markdown: {result.markdown[:200]}...")  # 添加调试信息
                return ""

        except Exception as e:
            raise Exception(f"获取回复错误: {e}") from e

    def _extract_json_from_text(self, text: str) -> str:
        """从任意文本中提取第一个合法的 JSON 对象"""
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
        return text

    async def chat(self, message, enable_thinking=True, enable_search=True):
        """发送消息并获取回复的便捷方法"""
        await self.send_message(message, enable_thinking, enable_search)
        return await self.get_response(enable_thinking=enable_thinking)


# 异步使用示例
async def main():
    client = None
    try:
        # 使用异步上下文管理器
        async with QwenChatClientCrawl4AI(headless=True) as client:
            await client.load_chat_page()

            user_message_1 = "请介绍量子物理,用json格式输出。"
            response_1 = await client.chat(user_message_1, False, False)
            print(f"[主程序] Qwen 回复 1:\n{response_1}")

    except Exception as e:
        print(f"[主程序错误] 运行出错: {e}")
        import traceback
        traceback.print_exc()


# 同步包装器用于向后兼容
class QwenChatClientSync:
    """同步包装器，提供与原始类相似的接口"""

    def __init__(self, headless=True, max_wait_time=300, **kwargs):
        self.headless = headless
        self.max_wait_time = max_wait_time
        self.client = None
        self.loop = None

    def __enter__(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        self.client = self.loop.run_until_complete(
            QwenChatClientCrawl4AI(headless=self.headless, max_wait_time=self.max_wait_time).__aenter__()
        )
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.client:
            self.loop.run_until_complete(self.client.__aexit__(exc_type, exc_val, exc_tb))
        if self.loop:
            self.loop.close()

    def load_chat_page(self, url="https://chat.qwen.ai/"):
        return self.loop.run_until_complete(self.client.load_chat_page(url))

    def send_message(self, message, enable_thinking=True, enable_search=True):
        return self.loop.run_until_complete(
            self.client.send_message(message, enable_thinking, enable_search)
        )

    def get_response(self, enable_thinking=True):
        return self.loop.run_until_complete(self.client.get_response(enable_thinking))

    def chat(self, message, enable_thinking=True, enable_search=True):
        return self.loop.run_until_complete(
            self.client.chat(message, enable_thinking, enable_search)
        )


if __name__ == "__main__":
    # 异步使用
    asyncio.run(main())

    # 或者使用同步接口（与原始代码兼容）
    with QwenChatClientSync(headless=True) as client:
        client.load_chat_page()
        response = client.chat("请介绍量子物理,用json格式输出。", False, False)
        print(f"Qwen 回复:\n{response}")
