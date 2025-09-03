# qwen_chat_client.py
import time
import tempfile
import atexit
import html2text # <--- 添加这行
import re # 导入 re 用于过滤函数
# 注意：platform 和 subprocess 在当前代码中未被使用，可以移除
# import platform
# import subprocess

from bs4 import BeautifulSoup

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.keys import Keys
from selenium.common.exceptions import (
    TimeoutException,
    StaleElementReferenceException,
    ElementClickInterceptedException,
)


def filter_qwen_output(text: str, intermediate_indicators, thinking_completed_indicator) -> str:
    """过滤掉 Qwen 输出中的中间状态信息"""
    # 注意：由于 reply_container.text 获取的是纯文本，HTML 标签如 <think>...</think> 已经被移除。
    # 因此，这个函数主要用于过滤掉纯文本形式的中间状态信息。
    if not text:
        return text

    lines = text.splitlines()
    filtered_lines = []
    skip_until_empty = False # 用于处理多行的中间状态信息
    for line in lines:
        line_stripped = line.strip()

        # 检查是否是已知的中间状态指示器行
        if line_stripped in intermediate_indicators or line_stripped == thinking_completed_indicator:
            # print(f"[过滤] 跳过指示器行: {line_stripped}") # 可选：调试信息
            skip_until_empty = True # 跳过当前行
            continue

        # 如果之前遇到了指示器，且当前行非空，继续跳过（处理可能的多行指示器）
        if skip_until_empty and line_stripped:
             # print(f"[过滤] 跳过指示器后内容行: {line_stripped}") # 可选：调试信息
             continue
        elif skip_until_empty and not line_stripped:
             # 如果之前遇到了指示器，且当前行为空，则停止跳过
             # print("[过滤] 指示器段落结束") # 可选：调试信息
             skip_until_empty = False
             continue # 跳过这个空行

        # 检查行内是否包含指示器（更宽松的过滤）
        is_intermediate = any(indicator in line for indicator in intermediate_indicators)
        is_completed_indicator = thinking_completed_indicator in line

        if is_intermediate or is_completed_indicator:
            # print(f"[过滤] 跳过包含指示器的行: {line}") # 可选：调试信息
            continue # 跳过包含指示器的行

        # 如果行不为空或不是纯空格，且未被过滤，则添加
        # 这会保留文本中的空行结构，这对于 Markdown 很重要
        filtered_lines.append(line) # 保留原始行（包括前导空格）

    # 重新组合文本
    result = "\n".join(filtered_lines)
    # 最终 strip 以移除首尾可能因过滤产生的多余空行
    return result.strip()


class QwenChatClient:
    """
    一个使用 Selenium 自动化与 Qwen 网页版聊天的客户端。
    """

    # --- 常量定义 ---
    # 选择器 - 更新为更精确地定位包含 Markdown 内容的容器
    # 原选择器 CHAT_INPUT_SELECTOR = "#chat-input" 保持不变
    # 原选择器 RESPONSE_CONTAINER_SELECTOR = "#response-message-body" 定位的是外层容器
    # 新选择器定位到直接包含 Markdown 内容的 div
    CHAT_INPUT_SELECTOR = "#chat-input"
    # RESPONSE_CONTAINER_SELECTOR = "#response-message-body" # 旧的，定位外层
    RESPONSE_CONTAINER_SELECTOR = "#response-message-body > div.text-response-render-container" # 新的，定位内层 Markdown 容器
    MAIN_CONTENT_CONTAINER_SELECTOR = "#response-content-container.markdown-content-container.markdown-prose"  # 新增：精确定位主内容


    DEEP_THINKING_BUTTON_XPATH = "//button[contains(., '深度思考')]"
    SEARCH_BUTTON_XPATH = "//button[contains(., '搜索')]"
    LOGIN_POPUP_BUTTON_XPATH = "//button[contains(text(), '保持注销状态')]"

    # 深度思考相关
    THINKING_COMPLETED_INDICATOR = "思考与搜索已完成"
    INTERMEDIATE_INDICATORS = ["正在思考与搜索", "tokens 预算"]

    # 默认参数
    DEFAULT_MAX_WAIT_TIME = 5
    DEFAULT_GET_RESPONSE_MAX_WAIT_TIME = 120
    DEFAULT_START_MINIMIZED = False
    DEFAULT_HEADLESS = False

    # 等待和稳定参数
    INITIAL_PAGE_LOAD_TIMEOUT = 30
    SEND_MESSAGE_POST_ENTER_DELAY = 1.5
    HANDLE_LOGIN_POPUP_QUICK_TIMEOUT = 0.1
    CLICK_FEATURE_BUTTON_TIMEOUT = 3
    CLICK_FEATURE_BUTTON_POST_CLICK_DELAY = 0.3
    CLICK_FEATURE_BUTTON_SCROLL_DELAY = 0.1
    THINKING_PHASE_CHECK_INTERVAL = 1
    RESPONSE_PHASE_CHECK_INTERVAL = 4.0
    RESPONSE_STABILITY_THRESHOLD_SECONDS = 4.0
    RESPONSE_SIGNIFICANT_CHANGE_THRESHOLD = 5
    RESPONSE_FINAL_CONFIRMATION_WAIT_DURATION = 5.0
    RESPONSE_MIN_LENGTH_THRESHOLD = 50
    # --- 常量定义结束 ---


    def __init__(self, headless=DEFAULT_HEADLESS, max_wait_time=DEFAULT_MAX_WAIT_TIME,
                 get_response_max_wait_time=DEFAULT_GET_RESPONSE_MAX_WAIT_TIME,
                 driver_path=None, start_minimized=DEFAULT_START_MINIMIZED):
        """
        初始化 QwenChatClient。
        :param headless: (bool) 是否以无头模式运行浏览器 (默认 False)。
        :param max_wait_time: (int) 查找元素和等待回复的最大超时时间（秒，默认 5）。
        :param get_response_max_wait_time: (int) 等待 Qwen 回复生成和稳定的最大超时时间（秒，默认 60）。
        :param driver_path: (str, optional) ChromeDriver 的路径。如果未指定，需要确保 chromedriver 在 PATH 中。
        :param start_minimized: (bool) 是否启动时最小化浏览器窗口 (默认 False)。
        """
        self.headless = headless
        self.max_wait_time = max_wait_time
        self.get_response_max_wait_time = get_response_max_wait_time
        self.driver_path = driver_path
        self.start_minimized = start_minimized
        self.driver = None
        self.wait = None
        self._create_driver()

    def _create_driver(self):
        """创建并配置 WebDriver 实例。"""
        chrome_options = Options()

        if self.headless:
            chrome_options.add_argument("--headless=new") # 使用新的 headless 模式

        chrome_options.add_argument("--disable-blink-features=AutomationControlled")
        chrome_options.add_argument("--disable-infobars")
        chrome_options.add_argument("--lang=zh-CN")
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option('useAutomationExtension', False)
        # 禁用日志可能会让调试更困难，暂时注释掉
        # chrome_options.add_experimental_option('excludeSwitches', ['enable-logging'])

        temp_user_data_dir = tempfile.mkdtemp(prefix='qwen_selenium_profile_')
        print(f"[初始化] 使用临时用户数据目录: {temp_user_data_dir}")
        chrome_options.add_argument(f"--user-data-dir={temp_user_data_dir}")

        try:
            # 推荐不指定 driver_path，让 Selenium 自动管理
            if self.driver_path:
                self.driver = webdriver.Chrome(executable_path=self.driver_path, options=chrome_options)
            else:
                self.driver = webdriver.Chrome(options=chrome_options)

            # 尝试隐藏 webdriver 特征
            self.driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")

            self.wait = WebDriverWait(self.driver, self.max_wait_time)
            print("[初始化] 成功创建 Chrome 实例")

            # 注册退出处理函数，确保程序结束时关闭浏览器
            atexit.register(self.close)

        except Exception as e:
            print(f"[初始化错误] 创建 Chrome 实例失败: {e}")
            raise # 重新抛出异常，让调用者处理

    def _handle_login_popup(self, wait_instance=None):
        """
        检查并处理'保持注销状态'弹窗。
        :param wait_instance: 可选的 WebDriverWait 实例。
        :return: True 如果处理了弹窗，False 如果没有弹窗。
        """
        if wait_instance is None:
            wait_instance = WebDriverWait(self.driver, self.HANDLE_LOGIN_POPUP_QUICK_TIMEOUT)

        try:
            # 等待并点击"保持注销状态"按钮
            stay_logged_out_button = wait_instance.until(
                EC.element_to_be_clickable((By.XPATH, self.LOGIN_POPUP_BUTTON_XPATH))
            )
            print("[弹窗处理] 检测到登录弹窗，正在点击'保持注销状态'按钮...")
            stay_logged_out_button.click()
            print("[弹窗处理] '保持注销状态'按钮已点击。")
            time.sleep(0.1) # 点击后短暂等待
            return True
        except TimeoutException:
            # 未找到弹窗，这是正常情况
            return False

    def load_chat_page(self, url="https://chat.qwen.ai/"):
        """
        导航到 Qwen 聊天页面并等待加载完成。
        :param url: (str) Qwen 聊天页面的 URL。
        """
        # 移除 url 字符串末尾可能存在的多余空格
        url = url.strip()
        try:
            print(f"[页面加载] 导航到 Qwen 聊天页面: {url}")
            self.driver.get(url)

            # 等待聊天输入框出现，作为页面加载完成的标志
            initial_wait = WebDriverWait(self.driver, self.INITIAL_PAGE_LOAD_TIMEOUT)
            initial_wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, self.CHAT_INPUT_SELECTOR)))
            print("[页面加载] Qwen 页面加载完成")
            print(f"[页面加载] 页面标题: {self.driver.title}")

            # 页面加载后立即检查一次弹窗
            self._handle_login_popup(self.wait)

        except TimeoutException as e:
            error_msg = f"[页面加载错误] 等待页面元素超时: {e}"
            print(error_msg)
            raise TimeoutException(error_msg) from e
        except Exception as e:
            error_msg = f"[页面加载错误] 导航到页面时出错: {e}"
            print(error_msg)
            raise Exception(error_msg) from e

    # --- send_message 相关辅助方法 ---
    def _click_feature_button(self, locators, button_name):
        """通用方法：尝试点击功能按钮（如深度思考、搜索）"""
        clicked = False
        for by, locator in locators:
            try:
                print(f"[发送消息] 尝试使用 {by} 定位“{button_name}”按钮: {locator}")
                # 使用显式等待查找可点击的元素
                element = WebDriverWait(self.driver, self.CLICK_FEATURE_BUTTON_TIMEOUT).until(
                    EC.element_to_be_clickable((by, locator))
                )
                # 滚动元素到视口中央
                self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", element)
                time.sleep(self.CLICK_FEATURE_BUTTON_SCROLL_DELAY) # 滚动后短暂等待
                # 再次检查元素是否可见和可用
                if element.is_displayed() and element.is_enabled():
                    element.click()
                    print(f"[发送消息] 成功点击“{button_name}”按钮")
                    clicked = True
                    time.sleep(self.CLICK_FEATURE_BUTTON_POST_CLICK_DELAY) # 点击后等待
                    break # 成功点击一个就退出循环
                else:
                    print(
                        f"[发送消息] “{button_name}”元素找到但不可点击 (可见: {element.is_displayed()}, 可用: {element.is_enabled()})")
            except (TimeoutException, ElementClickInterceptedException) as e:
                print(f"[发送消息] 使用 {by} 定位“{button_name}”按钮失败 ({type(e).__name__}): {e}")
                # 继续尝试下一个定位器
            except Exception as e:
                print(f"[发送消息] 使用 {by} 定位“{button_name}”按钮时发生未预期错误: {e}")
                # 继续尝试下一个定位器
        return clicked

    def _send_keys_with_newlines_shift_enter(self, element, text):
        """通过发送 Shift+Enter 来处理文本中的换行符。"""
        lines = text.split('\n')
        total_lines = len(lines)
        for i, line in enumerate(lines):
            element.send_keys(line)
            # print(f"[发送消息_处理换行] 已输入第 {i + 1}/{total_lines} 行: '{line}'")
            # 如果不是最后一行，则发送 Shift+Enter
            if i < total_lines - 1:
                element.send_keys(Keys.SHIFT, Keys.ENTER)
                # print(f"[发送消息_处理换行] 已为第 {i + 1} 行发送 Shift+Enter 换行")
        print("[发送消息_处理换行] 所有行已通过 send_keys (Shift+Enter) 输入")
    # --- send_message 辅助方法结束 ---

    def send_message(self, message, enable_thinking=True, enable_search=True):
        """
        发送消息到 Qwen。
        :param message: (str) 要发送的消息。
        :param enable_thinking: (bool) 是否启用“深度思考”功能 (默认: True)。
        :param enable_search: (bool) 是否启用“搜索”功能 (默认: True)。
        """
        try:
            message_len = len(message)
            print(f"[发送消息] 准备发送消息 (长度: {message_len} 字符)")
            # 提前检查功能启用状态并给出提示
            if not enable_thinking or not enable_search:
                status_msg = []
                if not enable_thinking:
                    status_msg.append("“深度思考”")
                if not enable_search:
                    status_msg.append("“搜索”")
                print(f"[发送消息] 注意：已禁用 {', '.join(status_msg)} 功能。")

            # 发送消息前检查弹窗
            self._handle_login_popup(self.wait)

            # --- 根据参数决定是否点击功能按钮 ---
            # 点击“深度思考”按钮
            if enable_thinking:
                deep_thinking_locators = [
                    (By.XPATH, self.DEEP_THINKING_BUTTON_XPATH),
                    (By.CSS_SELECTOR, "#chat-message-input .operationBtn button:nth-child(1)"),
                    # 备用 CSS 选择器，可能因页面结构变化而失效
                    (By.CSS_SELECTOR,
                     "#chat-message-input > div.chat-message-input-container.svelte-17xwb8y > div.chat-message-input-container-inner.svelte-17xwb8y > div.flex.items-center.min-h-\\[56px\\].mt-0\\.5.p-3.svelte-17xwb8y > div.scrollbar-none.flex.items-center.left-content.operationBtn.svelte-17xwb8y > div:nth-child(1) > button")
                ]
                if not self._click_feature_button(deep_thinking_locators, "深度思考"):
                    print("[发送消息] 警告：无法点击“深度思考”按钮，将继续执行。")
            else:
                print("[发送消息] 跳过点击“深度思考”按钮。")

            # 点击“搜索”按钮
            if enable_search:
                search_locators = [
                    (By.XPATH, self.SEARCH_BUTTON_XPATH),
                    (By.CSS_SELECTOR, "#chat-message-input .operationBtn button:nth-child(2)"),
                     # 备用 CSS 选择器
                    (By.CSS_SELECTOR,
                     "#chat-message-input > div.chat-message-input-container.svelte-17xwb8y > div.chat-message-input-container-inner.svelte-17xwb8y > div.flex.items-center.min-h-\\[56px\\].mt-0\\.5.p-3.svelte-17xwb8y > div.scrollbar-none.flex.items-center.left-content.operationBtn.svelte-17xwb8y > div:nth-child(2) > button")
                ]
                if not self._click_feature_button(search_locators, "搜索"):
                    print("[发送消息] 警告：无法点击“搜索”按钮，将继续执行。")
            else:
                print("[发送消息] 跳过点击“搜索”按钮。")
            # --- 功能按钮点击结束 ---

            # --- 定位并操作输入框 ---
            print("[发送消息] 正在等待输入框...")
            # 使用一个更具弹性的等待，忽略 ElementClickInterceptedException
            resilient_wait = WebDriverWait(
                self.driver,
                self.max_wait_time,
                ignored_exceptions=(ElementClickInterceptedException,)
            )
            input_box = resilient_wait.until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, self.CHAT_INPUT_SELECTOR))
            )
            print("[发送消息] 找到输入框")

            # 滚动输入框到视口顶部附近
            self.driver.execute_script("arguments[0].scrollIntoView(true);", input_box)
            # 点击输入框以确保焦点
            input_box.click()
            time.sleep(0.2)  # 点击后短暂等待以确保焦点稳定

            # --- 处理并输入消息 ---
            if '\n' in message:
                print("[发送消息] 检测到多行文本，使用 Shift+Enter 发送换行...")
                self._send_keys_with_newlines_shift_enter(input_box, message)
            else:
                input_box.send_keys(message)
                print(f"[发送消息] 已输入单行消息: '{message}'")

            # --- 发送消息 (按 Enter 键) ---
            input_box.send_keys(Keys.ENTER)
            print("[发送消息] 已按下 Enter 键提交消息")

            print("[发送消息] 等待页面状态稳定...")
            time.sleep(self.SEND_MESSAGE_POST_ENTER_DELAY)
            print("[发送消息] 页面状态稳定等待结束。")

        except TimeoutException as e:
            error_msg = f"[发送消息错误] 等待输入框超时: {e}"
            print(error_msg)
            raise TimeoutException(error_msg) from e
        except StaleElementReferenceException as e:
            warning_msg = f"[发送消息警告] 发送 Enter 时检测到元素过时 (StaleElementReferenceException)，消息可能已发送: {e}"
            print(warning_msg)
            print("[发送消息] 检测到 StaleElementReferenceException，仍将等待页面状态稳定...")
            time.sleep(self.SEND_MESSAGE_POST_ENTER_DELAY)
            print("[发送消息] 页面状态稳定等待结束 (Stale 后)。")
            # 不抛出异常，认为消息可能已发送
        except Exception as e:
            error_msg = f"[发送消息错误] 发送消息时出错: {e}"
            print(error_msg)
            raise Exception(error_msg) from e

        # --- 新增/修改的辅助方法 ---

    def _is_intermediate_state(self, text):
        """判断文本是否为中间状态"""
        contains_thinking_start = any(indicator in text for indicator in self.INTERMEDIATE_INDICATORS)
        contains_thinking_end = self.THINKING_COMPLETED_INDICATOR in text
        return contains_thinking_start and not contains_thinking_end

    def _relocate_reply_container(self, locator):
        """尝试重新定位回复容器"""
        try:
            # print("[获取回复] 回复容器元素变旧，重新定位...")
            container = self.driver.find_element(*locator)
            print("[获取回复] 重新定位成功。")
            return container
        except Exception as re_find_error:
            # print(f"[获取回复] 重新定位元素时出错: {re_find_error}")
            return None

        # --- 新增的核心文本提取函数 ---

    def _extract_container_inner_html(self, reply_container):
        """
        尝试从 reply_container 提取 innerHTML，并处理可能的 StaleElementReferenceException。
        :param reply_container: 当前的回复容器 WebElement。
        :return: (更新后的 reply_container, 提取到的 innerHTML 字符串 或 None 如果失败)
        """
        reply_container_locator = (By.CSS_SELECTOR, self.RESPONSE_CONTAINER_SELECTOR)
        inner_html = None
        try:
            # 使用 JavaScript 执行来获取 innerHTML
            inner_html = self.driver.execute_script(
                "return arguments[0].innerHTML;", reply_container
            )
            # print(f"[调试] 成功获取 innerHTML (长度: {len(inner_html)})") # 可选调试

        except StaleElementReferenceException:
            print("[HTML提取] 检测到 StaleElementReferenceException，尝试重新定位容器...")
            container = self._relocate_reply_container(reply_container_locator)
            if container:
                reply_container = container
                try:
                    inner_html = self.driver.execute_script(
                        "return arguments[0].innerHTML;", reply_container
                    )
                    print("[HTML提取] 重新定位后成功提取 innerHTML。")
                    # print(f"[调试] 重新定位后获取 innerHTML (长度: {len(inner_html)})") # 可选调试
                except StaleElementReferenceException:
                    print("[HTML提取] 重新定位后再次遇到 StaleElementReferenceException。")
                    inner_html = None
            else:
                print("[HTML提取] 无法重新定位容器。")
                inner_html = None
        except Exception as e:
            print(f"[HTML提取] 获取 innerHTML 时发生未预期错误: {e}")
            inner_html = None

        return reply_container, inner_html
    def _extract_and_process_text(self, reply_container):
        """
        从 reply_container 提取文本，并处理可能的 StaleElementReferenceException。
        不包含过滤逻辑，过滤在 get_response 的最后一步完成。
        :param reply_container: 当前的回复容器 WebElement。
        :return: (更新后的 reply_container, 提取到的文本字符串)
        """
        reply_container_locator = (By.CSS_SELECTOR, self.RESPONSE_CONTAINER_SELECTOR)
        current_text = ""
        try:
            current_text = reply_container.text.strip()
        except StaleElementReferenceException:
            # print("[文本提取] 检测到 StaleElementReferenceException，尝试重新定位容器...")
            container = self._relocate_reply_container(reply_container_locator)
            if container:
                reply_container = container
                try:
                    current_text = reply_container.text.strip()
                    print("[文本提取] 重新定位后成功提取文本。")
                except StaleElementReferenceException:
                    print("[文本提取] 重新定位后再次遇到 StaleElementReferenceException，返回空文本。")
                    current_text = ""  # 如果再次 stale，则返回空
            else:
                # print("[文本提取] 无法重新定位容器，返回空文本。")
                current_text = ""  # 重新定位失败，视为空文本
        return reply_container, current_text
        # --- 新增函数结束 ---


    def _wait_for_reply_container(self):
        """等待回复容器元素出现"""
        print("[获取回复] 开始等待 Qwen 回复...")
        reply_container_locator = (By.CSS_SELECTOR, self.RESPONSE_CONTAINER_SELECTOR)
        print(f"[获取回复] 正在等待回复容器元素 {self.RESPONSE_CONTAINER_SELECTOR} 出现...")

        start_wait_time = time.time()
        container_wait = WebDriverWait(
            self.driver,
            self.get_response_max_wait_time,
            ignored_exceptions=(ElementClickInterceptedException,)
        )
        try:
            reply_container = container_wait.until(
                EC.presence_of_element_located(reply_container_locator)
            )
            end_wait_time = time.time()
            print(f"[获取回复] 检测到回复容器元素 (耗时: {end_wait_time - start_wait_time:.2f} 秒)")
            return reply_container
        except TimeoutException as e:
            error_msg = f"[获取回复] 等待回复容器元素超时: {e}"
            print(error_msg)
            raise TimeoutException(error_msg) from e

    def _wait_for_thinking_completion(self, reply_container, enable_thinking=True):
        """
        (已简化) 快速通过或可选等待 '思考与搜索已完成' 阶段。
        现在使用 _extract_and_process_text 来获取文本。
        """
        if not enable_thinking:
            print("[获取回复_阶段一] 未启用深度思考，跳过等待 '思考与搜索已完成' 阶段。")
        else:
            print("[获取回复_阶段一] (已简化) 快速通过 '思考与搜索已完成' 等待阶段。")

        # 使用新的提取函数
        reply_container, current_text = self._extract_and_process_text(reply_container)

        print("[获取回复_阶段一] (已简化) 直接进入内容稳定等待阶段。")
        return reply_container, current_text

    def _wait_for_content_stabilization(self, reply_container, enable_thinking=True):
        """
        等待回复内容稳定。
        使用改进逻辑：连续 stable_length_count_max 次获取的 innerHTML 长度相同，
        并且能够处理内容被截断后需要拼接的情况。
        """
        stable_length_count_max = 3  # 增大稳定次数以提高可靠性

        print(
            f"[获取回复_阶段二] 开始等待最终回复内容稳定 (改进逻辑: 连续{stable_length_count_max}次长度相同，支持内容拼接)...")

        check_interval = self.RESPONSE_PHASE_CHECK_INTERVAL
        max_total_reply_wait_time = self.get_response_max_wait_time
        start_reply_wait_time = time.time()

        # --- 简化逻辑所需变量 ---
        stable_length_count = 0
        last_html_length = -1
        current_stable_html = None  # 当前认为稳定的 HTML 片段

        # --- 新增：用于缓存被截断前的内容 ---
        cached_partial_html = None  # 缓存之前获取到的较长部分

        # --- 定义显著减少的阈值 ---
        SIGNIFICANT_LENGTH_DROP_THRESHOLD = 0.5  # 如果新长度小于旧长度的 50%，则认为是显著减少

        while True:
            elapsed_reply_time = time.time() - start_reply_wait_time
            if int(elapsed_reply_time) % 5 == 0 or elapsed_reply_time > max_total_reply_wait_time - 1:
                self._handle_login_popup()

            # --- 提取 HTML ---
            reply_container, current_html = self._extract_container_inner_html(reply_container)

            if current_html is None:
                print("[获取回复_阶段二] 本轮 HTML 提取失败，重置计数器并继续等待...")
                stable_length_count = 0
                last_html_length = -1
                # 注意：这里不重置 cached_partial_html，因为它缓存的是有效历史数据
                time.sleep(check_interval)
                continue

            current_html_length = len(current_html)

            # --- 改进的稳定判断逻辑 ---

            # --- 修改：处理长度显著减少并缓存 ---
            if (last_html_length > 0 and
                    current_html_length < last_html_length * SIGNIFICANT_LENGTH_DROP_THRESHOLD):

                print(
                    f"[获取回复_阶段二] 检测到 HTML 长度显著减少 (旧: {last_html_length}, 新: {current_html_length})。")

                # 如果这是第一次显著减少，且我们有之前稳定的较长内容，则缓存它
                if cached_partial_html is None and current_stable_html:
                    cached_partial_html = current_stable_html
                    print(f"[获取回复_阶段二] 已缓存被截断前的内容 (长度: {len(cached_partial_html)})。")

                # 重置计数器和当前稳定内容，准备接收后续内容
                stable_length_count = 0
                current_stable_html = None
                print("[获取回复_阶段二] 重置计数器和当前稳定内容，继续等待后续内容。")
                # 注意：这里不立即更新 last_html_length，而是让它在下面的 else 分支中被更新
                # 这样可以确保下一轮比较是基于这次“缩短”后的长度

            # --- 长度变化或稳定计数逻辑 ---
            if current_html_length == last_html_length:
                stable_length_count += 1
                print(
                    f"[获取回复_阶段二] HTML 长度稳定计数: {stable_length_count}/{stable_length_count_max} (长度: {current_html_length})")
            else:  # 长度发生变化（包括显著减少后的情况，或正常增长）
                stable_length_count = 1
                print(
                    f"[获取回复_阶段二] HTML 长度发生变化 (旧: {last_html_length}, 新: {current_html_length})，重置计数器至 {stable_length_count}/{stable_length_count_max}")

            # 更新上一次的长度和当前稳定内容
            last_html_length = current_html_length
            if stable_length_count == 1:  # 长度变化后的第一次，或连续稳定时的最新内容
                current_stable_html = current_html

            # --- 检查是否达到稳定条件 ---
            if stable_length_count >= stable_length_count_max:
                print(
                    f"[获取回复_阶段二] 回复 HTML 内容已稳定 (连续{stable_length_count_max}次长度为 {last_html_length})。")

                # --- 精确定位主内容容器 (推荐) ---
                main_content_container = None
                try:
                    main_content_container = reply_container.find_element(By.CSS_SELECTOR,
                                                                          self.MAIN_CONTENT_CONTAINER_SELECTOR)
                    print(f"[获取回复_阶段二] 已定位到主内容容器: {self.MAIN_CONTENT_CONTAINER_SELECTOR}")
                except Exception as e:
                    print(f"[获取回复_阶段二] 警告：无法定位主内容容器 {self.MAIN_CONTENT_CONTAINER_SELECTOR}: {e}")

                # --- 修改：获取当前稳定的内容 ---
                current_segment_html_content = None
                if main_content_container:
                    _, current_segment_html_content = self._extract_container_inner_html(main_content_container)
                else:
                    current_segment_html_content = current_stable_html

                # --- 修改：拼接缓存内容和当前稳定内容 ---
                final_html_content = ""
                if cached_partial_html:
                    final_html_content += cached_partial_html
                    print(f"[获取回复_阶段二] 已从缓存加载前段内容 (长度: {len(cached_partial_html)})。")
                if current_segment_html_content:
                    final_html_content += current_segment_html_content
                    print(f"[获取回复_阶段二] 已获取当前段稳定内容 (长度: {len(current_segment_html_content)})。")

                final_html_content = final_html_content.strip()  # 清理首尾空白

                if not final_html_content:
                    print(f"[获取回复_阶段二] 警告：拼接后的最终 HTML 内容为空。继续等待内容增长...")
                    stable_length_count = 0
                    last_html_length = -1
                    current_stable_html = None
                    # 注意：这里不重置 cached_partial_html，保留已缓存的部分
                    time.sleep(check_interval)
                    continue
                else:
                    total_length = len(final_html_content)
                    print(f"[获取回复_阶段二] 成功获取到最终拼接并稳定 HTML (总长度: {total_length} 字符)")
                    self._handle_login_popup()

                    # --- 进行 HTML 预处理和 Markdown 转换 ---
                    if final_html_content:
                        try:
                            print("[获取回复_阶段二] 开始预处理 HTML 以移除不需要的元素...")
                            soup = BeautifulSoup(final_html_content, 'html.parser')

                            button_area = soup.find('div', class_='seletected-text-content')
                            if button_area:
                                button_area.decompose()
                                print("[预处理] 已移除底部按钮区域。")

                            citation_buttons = soup.find_all('span', class_='citation-button-wrap')
                            for btn in citation_buttons:
                                btn.decompose()
                            if citation_buttons:
                                print(f"[预处理] 已移除 {len(citation_buttons)} 个引用按钮/标记。")

                            cleaned_html = str(soup)
                            print("[获取回复_阶段二] HTML 预处理完成。")

                        except Exception as e:
                            print(f"[获取回复_阶段二] HTML 预处理失败: {e}")
                            cleaned_html = final_html_content

                        try:
                            print("[获取回复_阶段二] 开始将预处理后的最终 HTML 转换为 Markdown...")
                            h = html2text.HTML2Text()
                            h.body_width = 0
                            h.ignore_links = True
                            h.ignore_images = True
                            h.ignore_emphasis = False
                            markdown_text = h.handle(cleaned_html)
                            print("[获取回复_阶段二] HTML 到 Markdown 转换完成。")
                            return markdown_text

                        except Exception as e:
                            print(f"[获取回复_阶段二] HTML 到 Markdown 转换失败: {e}")
                            return ""
                    else:
                        print("[获取回复_阶段二] 最终未能获取到有效的 HTML 内容。")
                        return ""

            # --- 超时检查 ---
            if elapsed_reply_time > max_total_reply_wait_time:
                print(f"[获取回复_阶段二] 等待回复稳定超时 ({max_total_reply_wait_time} 秒)。")
                # 超时处理可以更复杂，这里简化处理
                if cached_partial_html or current_stable_html:
                    # 尝试拼接已有的内容
                    final_html_content = (cached_partial_html or "") + (current_stable_html or "")
                    if final_html_content.strip():
                        print("[获取回复_阶段二] 超时但仍尝试处理已获取到的部分 HTML...")
                        # ... (可复用上面的预处理和转换逻辑) ...
                        print("[获取回复_阶段二] 超时处理未完全实现，返回已拼接内容的文本表示或空。")
                        # 简化：直接返回文本或空
                        try:
                            soup = BeautifulSoup(final_html_content, 'html.parser')
                            h = html2text.HTML2Text()
                            h.body_width = 0;
                            h.ignore_links = True;
                            h.ignore_images = True;
                            h.ignore_emphasis = False
                            markdown_text = h.handle(str(soup))
                            return markdown_text
                        except:
                            return final_html_content  # 如果转换失败，至少返回原始HTML片段
                return ""

            time.sleep(check_interval)
        """
        等待回复内容稳定。
        使用简化逻辑：连续 stable_length_count_max 次获取的 innerHTML 长度相同即认为稳定。
        """
        stable_length_count_max = 4

        print(f"[获取回复_阶段二] 开始等待最终回复内容稳定 (简化逻辑: 连续{stable_length_count_max}次长度相同)...")

        check_interval = self.RESPONSE_PHASE_CHECK_INTERVAL
        max_total_reply_wait_time = self.get_response_max_wait_time
        start_reply_wait_time = time.time()

        # --- 简化逻辑所需变量 ---
        stable_length_count = 0  # 记录长度相同的次数
        last_html_length = -1  # 上一次获取的 HTML 长度
        current_stable_html = None  # 用于存储当前认为稳定的 HTML 内容

        while True:
            elapsed_reply_time = time.time() - start_reply_wait_time
            if int(elapsed_reply_time) % 5 == 0 or elapsed_reply_time > max_total_reply_wait_time - 1:
                self._handle_login_popup()

            # --- 提取 HTML ---
            reply_container, current_html = self._extract_container_inner_html(reply_container)

            # --- 处理 HTML 提取失败的情况 ---
            if current_html is None:
                print("[获取回复_阶段二] 本轮 HTML 提取失败，重置计数器并继续等待...")
                stable_length_count = 0  # 提取失败，重置计数
                last_html_length = -1
                time.sleep(check_interval)
                continue

            current_html_length = len(current_html)

            # --- 简化稳定判断逻辑 ---

            if current_html_length == last_html_length:
                stable_length_count += 1
                print(f"[获取回复_阶段二] HTML 长度稳定计数: {stable_length_count}/{stable_length_count_max}> (长度: {current_html_length})")
            else:
                # 长度发生变化，重置计数器
                stable_length_count = 1  # 当前这次变化也算作一次“相同”的开始
                print(
                     f"[获取回复_阶段二] HTML 长度发生变化 (旧: {last_html_length}, 新: {current_html_length})，重置计数器至 {stable_length_count}/{stable_length_count_max}]")

            # 更新上一次的长度和内容
            last_html_length = current_html_length
            # 仅在计数为1时更新内容（即长度变化后第一次，或连续相同时的最新内容）
            # 这样可以确保我们拿到的是最后一次长度稳定的那个 HTML 片段
            if stable_length_count == 1:
                current_stable_html = current_html

                # --- 检查是否达到稳定条件 ---
            if stable_length_count >= stable_length_count_max:  # 连续4次长度相同
                # print(f"[获取回复_阶段二] 回复 HTML 内容已稳定 (连续3次长度为 {last_html_length})。")

                # --- 精确定位主内容容器 (推荐) ---
                main_content_container = None
                try:
                    # 在 reply_container 内查找主内容容器
                    # 注意：reply_container 指向的是 RESPONSE_CONTAINER_SELECTOR
                    # 我们需要在它里面找 MAIN_CONTENT_CONTAINER_SELECTOR
                    main_content_container = reply_container.find_element(By.CSS_SELECTOR,
                                                                          self.MAIN_CONTENT_CONTAINER_SELECTOR)
                    print(f"[获取回复_阶段二] 已定位到主内容容器: {self.MAIN_CONTENT_CONTAINER_SELECTOR}")
                except Exception as e:
                    print(f"[获取回复_阶段二] 警告：无法定位主内容容器 {self.MAIN_CONTENT_CONTAINER_SELECTOR}: {e}")
                    # 如果找不到，使用整个 reply_container 的 HTML 作为后备
                    # main_content_container = reply_container # 这行可能不对，因为 reply_container 是 WebElement
                    # 更安全的是直接使用 current_stable_html，但我们已经提取了它的 innerHTML
                    # 或者再次从 reply_container 提取 innerHTML 作为后备

                stable_html_content = None
                if main_content_container:
                    # 从精确定位的主内容容器提取 HTML
                    _, stable_html_content = self._extract_container_inner_html(main_content_container)
                else:
                    # 回退到之前认为稳定的整个容器的 HTML
                    stable_html_content = current_stable_html

                if not stable_html_content or len(stable_html_content.strip()) == 0:
                    print(f"[获取回复_阶段二] 警告：稳定后的 HTML 内容为空。继续等待内容增长...")
                    stable_length_count = 0  # 重置计数器
                    last_html_length = -1
                    time.sleep(check_interval)
                    continue
                else:
                    print(f"[获取回复_阶段二] 成功获取到最终稳定 HTML (长度: {len(stable_html_content)} 字符)")
                    self._handle_login_popup()

                    # --- 进行 HTML 预处理和 Markdown 转换 ---
                    if stable_html_content:
                        try:
                            print("[获取回复_阶段二] 开始预处理 HTML 以移除不需要的元素...")
                            soup = BeautifulSoup(stable_html_content, 'html.parser')

                            # 1. 移除底部按钮区域
                            button_area = soup.find('div', class_='seletected-text-content')
                            if button_area:
                                button_area.decompose()
                                print("[预处理] 已移除底部按钮区域。")

                            # 2. 移除引用按钮/标记
                            citation_buttons = soup.find_all('span', class_='citation-button-wrap')
                            for btn in citation_buttons:
                                btn.decompose()
                            if citation_buttons:
                                print(f"[预处理] 已移除 {len(citation_buttons)} 个引用按钮/标记。")

                            cleaned_html = str(soup)
                            print("[获取回复_阶段二] HTML 预处理完成。")

                        except Exception as e:
                            print(f"[获取回复_阶段二] HTML 预处理失败: {e}")
                            cleaned_html = stable_html_content

                        try:
                            print("[获取回复_阶段二] 开始将预处理后的稳定 HTML 转换为 Markdown...")
                            h = html2text.HTML2Text()
                            h.body_width = 0
                            h.ignore_links = True  # 根据需要调整
                            h.ignore_images = True  # 根据需要调整
                            h.ignore_emphasis = False  # 保留粗斜体
                            # h.single_line_break = True # 可选
                            markdown_text = h.handle(cleaned_html)
                            print("[获取回复_阶段二] HTML 到 Markdown 转换完成。")

                            # 注意：这里应该 return markdown_text
                            # 原代码在循环外还有一次转换，应该移除
                            return markdown_text

                        except Exception as e:
                            print(f"[获取回复_阶段二] HTML 到 Markdown 转换失败: {e}")
                            return ""  # 或者返回 cleaned_html 或 stable_html_content

                    else:
                        print("[获取回复_阶段二] 最终未能获取到有效的 HTML 内容。")
                        return ""

            # --- 超时检查 ---
            if elapsed_reply_time > max_total_reply_wait_time:
                print(f"[获取回复_阶段二] 等待回复稳定超时 ({max_total_reply_wait_time} 秒)。")
                # 即使超时，也尝试使用最后获取到的 HTML 进行转换
                if current_stable_html:  # 使用最后稳定的 HTML
                    print("[获取回复_阶段二] 超时但仍尝试处理最后获取到的 HTML...")
                    # ... (这里可以复用上面的预处理和转换逻辑，或者简化处理) ...
                    # 为了简化，我们直接返回空或最后的内容
                    # 更好的做法是将预处理和转换逻辑提取成一个辅助函数
                    print("[获取回复_阶段二] 超时处理未完全实现，返回空字符串。")
                return ""  # 超时返回空

            time.sleep(check_interval)

    def get_response(self, enable_thinking=True):
        """
        等待并获取 Qwen 的回复。
        """
        try:
            print(f"[获取回复] 开始等待 Qwen 回复 (深度思考已启用: {enable_thinking})...")

            reply_container = self._wait_for_reply_container()
            reply_container, _ = self._wait_for_thinking_completion(reply_container, enable_thinking)
            final_response = self._wait_for_content_stabilization(reply_container, enable_thinking)

            # --- 在最后一步调用过滤函数 ---
            if isinstance(final_response, str) and final_response:
                print("[获取回复] 开始后处理过滤...")
                # 1. 过滤掉已知的中间状态信息
                cleaned_response = filter_qwen_output(
                    final_response,
                    self.INTERMEDIATE_INDICATORS,
                    self.THINKING_COMPLETED_INDICATOR
                )


                # 3. --- 新增：过滤掉字符串开头和结尾的单引号 ---
                if cleaned_response:
                    original_len = len(cleaned_response)
                    # 使用 str.strip() 方法移除首尾指定字符，默认是空格，这里指定为 "'"
                    cleaned_response = cleaned_response.strip("'").strip("'")
                    removed_len = original_len - len(cleaned_response)
                    if removed_len > 0:
                        print(f"[获取回复] 移除了首尾的 {removed_len} 个单引号。")
                    # 如果只有开头或结尾有单引号，strip 也能正确处理
                    # 例如: "'abc'" -> "abc", "'abc" -> "abc", "abc'" -> "abc"

                print("[获取回复] 内容已获取并后处理完成。")
                # 返回清理后的内容
                return cleaned_response
            elif isinstance(final_response, str):
                print("[获取回复] 获取到空的回复内容。")
                return final_response
            else:
                print("[获取回复] 警告：获取到非字符串类型的回复内容。")
                return str(final_response) if final_response is not None else ""

        except TimeoutException as e:
            error_msg = f"等待回复元素超时: {e}"
            print(f"[获取回复错误] {error_msg}")
            raise Exception(error_msg) from e
        except StaleElementReferenceException as e:
            error_msg = f"元素失效 (StaleElementReferenceException): {e}"
            print(f"[获取回复错误] {error_msg}")
            raise Exception(error_msg) from e
        except Exception as e:
            error_msg = f"获取回复时发生未知错误: {e}"
            print(f"[获取回复错误] {error_msg}")
            import traceback
            traceback.print_exc()
            raise Exception(error_msg) from e


    # ... (get_response 方法结束) ...

    def chat(self, message, enable_thinking=True, enable_search=True):
        """
        发送消息并获取回复的便捷方法。
        :param message: (str) 要发送的消息。
        :param enable_thinking: (bool) 是否启用“深度思考”功能 (默认: True)。
        :param enable_search: (bool) 是否启用“搜索”功能 (默认: True)。
        :return: (str) Qwen 的回复文本 (Markdown 格式)。
        """
        # 1. 发送消息
        self.send_message(message, enable_thinking, enable_search)
        # 2. 获取回复 (将 enable_thinking 参数传递给 get_response)
        return self.get_response(enable_thinking=enable_thinking)

    def close(self):
        """关闭浏览器驱动。"""
        if self.driver:
            try:
                print("[关闭] 正在关闭浏览器...")
                self.driver.quit()
                print("[关闭] 浏览器已关闭")
            except Exception as e:
                print(f"[关闭] 关闭浏览器时出错: {e}")
            finally:
                self.driver = None
                self.wait = None


# --- 示例用法 ---
if __name__ == "__main__":
    client = None
    try:
        client = QwenChatClient(headless=True, max_wait_time=5, get_response_max_wait_time=180, start_minimized=True)
        client.load_chat_page()

        user_message_1 = "请介绍苹果,用md格式输出。"

        response_1 = client.chat(user_message_1,True,False)
        print(f"[主程序] Qwen 回复 1:\n{response_1}")

        print("\n[主程序] --- 交互完成 ---")
        # print("\n[主程序] 请按 Enter 键关闭浏览器并退出程序...")
        # input()

    except Exception as e:
        print(f"[主程序错误] 运行出错: {e}")
        import traceback
        traceback.print_exc()
    finally:
        if client and client.driver:
            print("[主程序] 正在关闭浏览器...")
            client.close()
