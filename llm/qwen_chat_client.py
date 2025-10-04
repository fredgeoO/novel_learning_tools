# qwen_chat_client.py
import atexit
import glob
import json
import time
import tempfile
import html2text
import re
import os
import shutil
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
import uuid


def cleanup_temp_profiles():
    temp_dir = tempfile.gettempdir()
    pattern = os.path.join(temp_dir, "qwen_selenium_profile_*")
    for folder in glob.glob(pattern):
        try:
            shutil.rmtree(folder)
            # print(f"[清理] 已删除临时目录: {folder}")
        except Exception as e:
            # print(f"[清理警告] 无法删除 {folder}: {e}")
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


class QwenChatClient:
    """
    一个使用 Selenium 自动化与 Qwen 网页版聊天的客户端。
    """
    FIXED_TEMP_DIR_NAME = 'qwen_selenium_profile'
    PROFILE_MAX_AGE_SECONDS = 1  # 10秒

    # --- 常量定义 ---
    CHAT_INPUT_SELECTOR = "#chat-input"
    RESPONSE_CONTAINER_SELECTOR = "#response-message-body > div.text-response-render-container"
    MAIN_CONTENT_CONTAINER_SELECTOR = "#response-content-container.markdown-content-container.markdown-prose"
    DEEP_THINKING_BUTTON_XPATH = "//button[contains(., '深度思考')]"
    SEARCH_BUTTON_XPATH = "//button[contains(., '搜索')]"
    LOGIN_POPUP_BUTTON_XPATH = "//button[contains(text(), '保持注销状态')]"
    THINKING_COMPLETED_INDICATOR = "思考与搜索已完成"
    INTERMEDIATE_INDICATORS = ["正在思考与搜索", "tokens 预算"]
    DEFAULT_MAX_WAIT_TIME = 5
    DEFAULT_GET_RESPONSE_MAX_WAIT_TIME = 300
    DEFAULT_START_MINIMIZED = False
    DEFAULT_HEADLESS = False
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
        self.headless = headless
        self.max_wait_time = max_wait_time
        self.get_response_max_wait_time = get_response_max_wait_time
        self.driver_path = driver_path
        self.start_minimized = start_minimized
        self.driver = None
        self.wait = None
        self.user_data_dir = None
        self._closed = False
        self._create_driver()

    def _setup_user_data_dir(self):
        """为每个实例创建唯一的用户数据目录"""
        system_temp_dir = tempfile.gettempdir()
        unique_dir_name = f"qwen_selenium_profile_{uuid.uuid4().hex[:8]}"
        user_data_dir_path = os.path.join(system_temp_dir, unique_dir_name)

        try:
            os.makedirs(user_data_dir_path, exist_ok=True)
            # print(f"[初始化] 已创建独立用户数据目录: {user_data_dir_path}")
        except Exception as e:
            # print(f"[初始化错误] 创建用户数据目录失败: {e}")
            raise

        self.user_data_dir = user_data_dir_path
        return user_data_dir_path


    def _create_driver(self):
        """创建并配置 WebDriver 实例。"""
        chrome_options = Options()
        if self.headless:
            chrome_options.add_argument("--headless=new")
        chrome_options.add_argument("--disable-blink-features=AutomationControlled")
        chrome_options.add_argument('--disable-application-cache')
        chrome_options.add_argument('--disable-gpu-shader-disk-cache')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument('--disk-cache-size=1')  # 最小化缓存
        chrome_options.add_argument('--media-cache-size=1')
        chrome_options.add_argument("--disable-infobars")
        chrome_options.add_argument("--lang=zh-CN")
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option('useAutomationExtension', False)

        user_data_dir_path = self._setup_user_data_dir()
        chrome_options.add_argument(f"--user-data-dir={user_data_dir_path}")

        try:
            if self.driver_path:
                self.driver = webdriver.Chrome(executable_path=self.driver_path, options=chrome_options)
            else:
                self.driver = webdriver.Chrome(options=chrome_options)
            self.driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
            self.wait = WebDriverWait(self.driver, self.max_wait_time)
            # print("[初始化] 成功创建 Chrome 实例")
        except Exception as e:
            # print(f"[初始化错误] 创建 Chrome 实例失败: {e}")
            raise

    def close(self):
        """关闭浏览器驱动。"""
        if self._closed:
            # print("[关闭] 浏览器和资源已被关闭或正在关闭。")
            return

        self._closed = True
        # print("[关闭] 开始关闭浏览器...")

        if self.driver:
            try:
                self.driver.quit()
                # print("[关闭] 浏览器已关闭")
            except Exception as e:
                # print(f"[关闭] 关闭浏览器时出错: {e}")
                pass
            finally:
                self.driver = None
                self.wait = None

        # print("[关闭] 浏览器资源已释放。")

    def _handle_login_popup(self, wait_instance=None):
        """检查并处理'保持注销状态'弹窗。"""
        if wait_instance is None:
            wait_instance = WebDriverWait(self.driver, self.HANDLE_LOGIN_POPUP_QUICK_TIMEOUT)
        try:
            stay_logged_out_button = wait_instance.until(
                EC.element_to_be_clickable((By.XPATH, self.LOGIN_POPUP_BUTTON_XPATH))
            )
            # print("[弹窗处理] 检测到登录弹窗，正在点击'保持注销状态'按钮...")
            stay_logged_out_button.click()
            # print("[弹窗处理] '保持注销状态'按钮已点击。")
            time.sleep(0.1)
            return True
        except TimeoutException:
            return False

    def load_chat_page(self, url="https://chat.qwen.ai/"):
        """导航到 Qwen 聊天页面并等待加载完成。"""
        url = url.strip()
        try:
            # print(f"[页面加载] 导航到 Qwen 聊天页面: {url}")
            self.driver.get(url)
            initial_wait = WebDriverWait(self.driver, self.INITIAL_PAGE_LOAD_TIMEOUT)
            initial_wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, self.CHAT_INPUT_SELECTOR)))
            # print("[页面加载] Qwen 页面加载完成")
            # print(f"[页面加载] 页面标题: {self.driver.title}")
            self._handle_login_popup(self.wait)
        except TimeoutException as e:
            error_msg = f"[页面加载错误] 等待页面元素超时: {e}"
            # print(error_msg)
            raise TimeoutException(error_msg) from e
        except Exception as e:
            error_msg = f"[页面加载错误] 导航到页面时出错: {e}"
            # print(error_msg)
            raise Exception(error_msg) from e

    # --- send_message 相关辅助方法 ---
    def _click_feature_button(self, locators, button_name):
        """通用方法：尝试点击功能按钮（如深度思考、搜索）"""
        clicked = False
        for by, locator in locators:
            try:
                # print(f"[发送消息] 尝试使用 {by} 定位“{button_name}”按钮: {locator}")
                element = WebDriverWait(self.driver, self.CLICK_FEATURE_BUTTON_TIMEOUT).until(
                    EC.element_to_be_clickable((by, locator))
                )
                self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", element)
                time.sleep(self.CLICK_FEATURE_BUTTON_SCROLL_DELAY)
                if element.is_displayed() and element.is_enabled():
                    element.click()
                    # print(f"[发送消息] 成功点击“{button_name}”按钮")
                    clicked = True
                    time.sleep(self.CLICK_FEATURE_BUTTON_POST_CLICK_DELAY)
                    break
                else:
                    # print(
                    #     f"[发送消息] “{button_name}”元素找到但不可点击 (可见: {element.is_displayed()}, 可用: {element.is_enabled()})")
                    pass
            except (TimeoutException, ElementClickInterceptedException) as e:
                # print(f"[发送消息] 使用 {by} 定位“{button_name}”按钮失败 ({type(e).__name__}): {e}")
                pass
            except Exception as e:
                # print(f"[发送消息] 使用 {by} 定位“{button_name}”按钮时发生未预期错误: {e}")
                pass
        return clicked

    def _send_keys_with_newlines_shift_enter(self, element, text):
        """通过发送 Shift+Enter 来处理文本中的换行符。"""
        lines = text.split('\n')
        total_lines = len(lines)
        for i, line in enumerate(lines):
            element.send_keys(line)
            if i < total_lines - 1:
                element.send_keys(Keys.SHIFT, Keys.ENTER)
        # print("[发送消息_处理换行] 所有行已通过 send_keys (Shift+Enter) 输入")

    # --- send_message 辅助方法结束 ---

    def send_message(self, message, enable_thinking=True, enable_search=True):
        """发送消息到 Qwen。"""
        try:
            message_len = len(message)
            # print(f"[发送消息] 准备发送消息 (长度: {message_len} 字符)")
            if not enable_thinking or not enable_search:
                status_msg = []
                if not enable_thinking:
                    status_msg.append("“深度思考”")
                if not enable_search:
                    status_msg.append("“搜索”")
                # print(f"[发送消息] 注意：已禁用 {', '.join(status_msg)} 功能。")

            self._handle_login_popup(self.wait)

            if enable_thinking:
                deep_thinking_locators = [
                    (By.XPATH, self.DEEP_THINKING_BUTTON_XPATH),
                    (By.CSS_SELECTOR, "#chat-message-input .operationBtn button:nth-child(1)"),
                    (By.CSS_SELECTOR,
                     "#chat-message-input > div.chat-message-input-container.svelte-17xwb8y > div.chat-message-input-container-inner.svelte-17xwb8y > div.flex.items-center.min-h-\\[56px\\].mt-0\\.5.p-3.svelte-17xwb8y > div.scrollbar-none.flex.items-center.left-content.operationBtn.svelte-17xwb8y > div:nth-child(1) > button")
                ]
                if not self._click_feature_button(deep_thinking_locators, "深度思考"):
                    # print("[发送消息] 警告：无法点击“深度思考”按钮，将继续执行。")
                    pass
            else:
                # print("[发送消息] 跳过点击“深度思考”按钮。")
                pass

            if enable_search:
                search_locators = [
                    (By.XPATH, self.SEARCH_BUTTON_XPATH),
                    (By.CSS_SELECTOR, "#chat-message-input .operationBtn button:nth-child(2)"),
                    (By.CSS_SELECTOR,
                     "#chat-message-input > div.chat-message-input-container.svelte-17xwb8y > div.chat-message-input-container-inner.svelte-17xwb8y > div.flex.items-center.min-h-\\[56px\\].mt-0\\.5.p-3.svelte-17xwb8y > div.scrollbar-none.flex.items-center.left-content.operationBtn.svelte-17xwb8y > div:nth-child(2) > button")
                ]
                if not self._click_feature_button(search_locators, "搜索"):
                    # print("[发送消息] 警告：无法点击“搜索”按钮，将继续执行。")
                    pass
            else:
                # print("[发送消息] 跳过点击“搜索”按钮。")
                pass

            # print("[发送消息] 正在等待输入框...")
            resilient_wait = WebDriverWait(
                self.driver,
                self.max_wait_time,
                ignored_exceptions=(ElementClickInterceptedException,)
            )
            input_box = resilient_wait.until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, self.CHAT_INPUT_SELECTOR))
            )
            # print("[发送消息] 找到输入框")
            self.driver.execute_script("arguments[0].scrollIntoView(true);", input_box)
            input_box.click()
            time.sleep(0.2)

            if '\n' in message:
                # print("[发送消息] 检测到多行文本，使用 Shift+Enter 发送换行...")
                self._send_keys_with_newlines_shift_enter(input_box, message)
            else:
                input_box.send_keys(message)
                # print(f"[发送消息] 已输入单行消息: '{message}'")

            input_box.send_keys(Keys.ENTER)
            # print("[发送消息] 已按下 Enter 键提交消息")
            # print("[发送消息] 等待页面状态稳定...")
            time.sleep(self.SEND_MESSAGE_POST_ENTER_DELAY)
            # print("[发送消息] 页面状态稳定等待结束。")
        except TimeoutException as e:
            error_msg = f"[发送消息错误] 等待输入框超时: {e}"
            # print(error_msg)
            raise TimeoutException(error_msg) from e
        except StaleElementReferenceException as e:
            warning_msg = f"[发送消息警告] 发送 Enter 时检测到元素过时 (StaleElementReferenceException)，消息可能已发送: {e}"
            # print(warning_msg)
            # print("[发送消息] 检测到 StaleElementReferenceException，仍将等待页面状态稳定...")
            time.sleep(self.SEND_MESSAGE_POST_ENTER_DELAY)
            # print("[发送消息] 页面状态稳定等待结束 (Stale 后)。")
        except Exception as e:
            error_msg = f"[发送消息错误] 发送消息时出错: {e}"
            # print(error_msg)
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
            container = self.driver.find_element(*locator)
            # print("[获取回复] 重新定位成功。")
            return container
        except Exception as re_find_error:
            return None

    def _extract_container_inner_html(self, reply_container):
        """尝试从 reply_container 提取 innerHTML，并处理可能的 StaleElementReferenceException。"""
        reply_container_locator = (By.CSS_SELECTOR, self.RESPONSE_CONTAINER_SELECTOR)
        inner_html = None
        try:
            inner_html = self.driver.execute_script("return arguments[0].innerHTML;", reply_container)
        except StaleElementReferenceException:
            # print("[HTML提取] 检测到 StaleElementReferenceException，尝试重新定位容器...")
            container = self._relocate_reply_container(reply_container_locator)
            if container:
                reply_container = container
                try:
                    inner_html = self.driver.execute_script("return arguments[0].innerHTML;", reply_container)
                    # print("[HTML提取] 重新定位后成功提取 innerHTML。")
                except StaleElementReferenceException:
                    # print("[HTML提取] 重新定位后再次遇到 StaleElementReferenceException。")
                    inner_html = None
            else:
                # print("[HTML提取] 无法重新定位容器。")
                inner_html = None
        except Exception as e:
            # print(f"[HTML提取] 获取 innerHTML 时发生未预期错误: {e}")
            inner_html = None
        return reply_container, inner_html

    def _extract_and_process_text(self, reply_container):
        """从 reply_container 提取文本，并处理可能的 StaleElementReferenceException。"""
        reply_container_locator = (By.CSS_SELECTOR, self.RESPONSE_CONTAINER_SELECTOR)
        current_text = ""
        try:
            current_text = reply_container.text.strip()
        except StaleElementReferenceException:
            container = self._relocate_reply_container(reply_container_locator)
            if container:
                reply_container = container
                try:
                    current_text = reply_container.text.strip()
                    # print("[文本提取] 重新定位后成功提取文本。")
                except StaleElementReferenceException:
                    # print("[文本提取] 重新定位后再次遇到 StaleElementReferenceException，返回空文本。")
                    current_text = ""
            else:
                current_text = ""
        return reply_container, current_text

    # --- 新增函数结束 ---

    def _wait_for_reply_container(self):
        """等待回复容器元素出现"""
        # print("[获取回复] 开始等待 Qwen 回复...")
        reply_container_locator = (By.CSS_SELECTOR, self.RESPONSE_CONTAINER_SELECTOR)
        # print(f"[获取回复] 正在等待回复容器元素 {self.RESPONSE_CONTAINER_SELECTOR} 出现...")
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
            # print(f"[获取回复] 检测到回复容器元素 (耗时: {end_wait_time - start_wait_time:.2f} 秒)")
            return reply_container
        except TimeoutException as e:
            error_msg = f"[获取回复] 等待回复容器元素超时: {e}"
            # print(error_msg)
            raise TimeoutException(error_msg) from e

    def _wait_for_thinking_completion(self, reply_container, enable_thinking=True):
        """(已简化) 快速通过或可选等待 '思考与搜索已完成' 阶段。"""
        if not enable_thinking:
            # print("[获取回复_阶段一] 未启用深度思考，跳过等待 '思考与搜索已完成' 阶段。")
            pass
        else:
            # print("[获取回复_阶段一] (已简化) 快速通过 '思考与搜索已完成' 等待阶段。")
            pass
        reply_container, current_text = self._extract_and_process_text(reply_container)
        # print("[获取回复_阶段一] (已简化) 直接进入内容稳定等待阶段。")
        return reply_container, current_text

    def _wait_for_content_stabilization(self, reply_container, enable_thinking=True):
        """
        等待回复内容稳定。
        使用改进逻辑：连续 stable_length_count_max 次获取的 innerHTML 长度相同，
        并且能够处理内容被截断后需要拼接的情况。
        """
        stable_length_count_max = 3
        # print(
        #     f"[获取回复_阶段二] 开始等待最终回复内容稳定 (改进逻辑: 连续{stable_length_count_max}次长度相同，支持内容拼接)...")
        check_interval = self.RESPONSE_PHASE_CHECK_INTERVAL
        max_total_reply_wait_time = self.get_response_max_wait_time
        start_reply_wait_time = time.time()

        stable_length_count = 0
        last_html_length = -1
        current_stable_html = None
        cached_partial_html = None
        SIGNIFICANT_LENGTH_DROP_THRESHOLD = 0.5

        while True:
            elapsed_reply_time = time.time() - start_reply_wait_time
            if int(elapsed_reply_time) % 5 == 0 or elapsed_reply_time > max_total_reply_wait_time - 1:
                self._handle_login_popup()

            reply_container, current_html = self._extract_container_inner_html(reply_container)
            if current_html is None:
                # print("[获取回复_阶段二] 本轮 HTML 提取失败，重置计数器并继续等待...")
                stable_length_count = 0
                last_html_length = -1
                time.sleep(check_interval)
                continue
            current_html_length = len(current_html)

            if (last_html_length > 0 and
                    current_html_length < last_html_length * SIGNIFICANT_LENGTH_DROP_THRESHOLD):
                # print(
                #     f"[获取回复_阶段二] 检测到 HTML 长度显著减少 (旧: {last_html_length}, 新: {current_html_length})。")
                if cached_partial_html is None and current_stable_html:
                    cached_partial_html = current_stable_html
                    # print(f"[获取回复_阶段二] 已缓存被截断前的内容 (长度: {len(cached_partial_html)})。")
                stable_length_count = 0
                current_stable_html = None
                # print("[获取回复_阶段二] 重置计数器和当前稳定内容，继续等待后续内容。")
            elif current_html_length == last_html_length:
                stable_length_count += 1
                # print(
                #     f"[获取回复_阶段二] HTML 长度稳定计数: {stable_length_count}/{stable_length_count_max} (长度: {current_html_length})")
            else:
                stable_length_count = 1
                # print(
                #     f"[获取回复_阶段二] HTML 长度发生变化 (旧: {last_html_length}, 新: {current_html_length})，重置计数器至 {stable_length_count}/{stable_length_count_max}")

            last_html_length = current_html_length
            if stable_length_count == 1:
                current_stable_html = current_html

            if stable_length_count >= stable_length_count_max:
                # print(
                #     f"[获取回复_阶段二] 回复 HTML 内容已稳定 (连续{stable_length_count_max}次长度为 {last_html_length})。")

                main_content_container = None
                try:
                    main_content_container = reply_container.find_element(By.CSS_SELECTOR,
                                                                          self.MAIN_CONTENT_CONTAINER_SELECTOR)
                    # print(f"[获取回复_阶段二] 已定位到主内容容器: {self.MAIN_CONTENT_CONTAINER_SELECTOR}")
                except Exception as e:
                    # print(f"[获取回复_阶段二] 警告：无法定位主内容容器 {self.MAIN_CONTENT_CONTAINER_SELECTOR}: {e}")
                    pass

                current_segment_html_content = None
                if main_content_container:
                    _, current_segment_html_content = self._extract_container_inner_html(main_content_container)
                else:
                    current_segment_html_content = current_stable_html

                final_html_content = ""
                if cached_partial_html:
                    final_html_content += cached_partial_html
                    # print(f"[获取回复_阶段二] 已从缓存加载前段内容 (长度: {len(cached_partial_html)})。")
                if current_segment_html_content:
                    final_html_content += current_segment_html_content
                    # print(f"[获取回复_阶段二] 已获取当前段稳定内容 (长度: {len(current_segment_html_content)})。")
                final_html_content = final_html_content.strip()

                if not final_html_content:
                    # print(f"[获取回复_阶段二] 警告：拼接后的最终 HTML 内容为空。继续等待内容增长...")
                    stable_length_count = 0
                    last_html_length = -1
                    current_stable_html = None
                    time.sleep(check_interval)
                    continue
                else:
                    total_length = len(final_html_content)
                    # print(f"[获取回复_阶段二] 成功获取到最终拼接并稳定 HTML (总长度: {total_length} 字符)")
                    self._handle_login_popup()

                    if final_html_content:
                        try:
                            # print("[获取回复_阶段二] 开始预处理 HTML 以移除不需要的元素...")
                            soup = BeautifulSoup(final_html_content, 'html.parser')
                            button_area = soup.find('div', class_='seletected-text-content')
                            if button_area:
                                button_area.decompose()
                                # print("[预处理] 已移除底部按钮区域。")
                            citation_buttons = soup.find_all('span', class_='citation-button-wrap')
                            for btn in citation_buttons:
                                btn.decompose()
                            if citation_buttons:
                                # print(f"[预处理] 已移除 {len(citation_buttons)} 个引用按钮/标记。")
                                pass
                            cleaned_html = str(soup)
                            # print("[获取回复_阶段二] HTML 预处理完成。")
                        except Exception as e:
                            # print(f"[获取回复_阶段二] HTML 预处理失败: {e}")
                            cleaned_html = final_html_content
                        try:
                            # print("[获取回复_阶段二] 开始将预处理后的最终 HTML 转换为 Markdown...")
                            h = html2text.HTML2Text()
                            h.body_width = 0
                            h.ignore_links = True
                            h.ignore_images = True
                            h.ignore_emphasis = False
                            markdown_text = h.handle(cleaned_html)
                            # print("[获取回复_阶段二] HTML 到 Markdown 转换完成。")
                            return markdown_text
                        except Exception as e:
                            # print(f"[获取回复_阶段二] HTML 到 Markdown 转换失败: {e}")
                            return ""
                    else:
                        # print("[获取回复_阶段二] 最终未能获取到有效的 HTML 内容。")
                        return ""

            if elapsed_reply_time > max_total_reply_wait_time:
                # print(f"[获取回复_阶段二] 等待回复稳定超时 ({max_total_reply_wait_time} 秒)。")
                if cached_partial_html or current_stable_html:
                    final_html_content = (cached_partial_html or "") + (current_stable_html or "")
                    if final_html_content.strip():
                        # print("[获取回复_阶段二] 超时但仍尝试处理已获取到的部分 HTML...")
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
                            return final_html_content
                return ""
            time.sleep(check_interval)

    def get_response(self, enable_thinking=True):
        """等待并获取 Qwen 的回复。"""
        try:
            # print(f"[获取回复] 开始等待 Qwen 回复 (深度思考已启用: {enable_thinking})...")
            reply_container = self._wait_for_reply_container()
            reply_container, _ = self._wait_for_thinking_completion(reply_container, enable_thinking)
            final_response = self._wait_for_content_stabilization(reply_container, enable_thinking)

            if isinstance(final_response, str) and final_response:
                # print("[获取回复] 开始后处理过滤...")

                # === 新增：提取第一个合法的 JSON 对象 ===
                cleaned_response = self._extract_json_from_text(final_response)

                # print("[获取回复] 内容已获取并后处理完成。")
                return cleaned_response
            else:
                # 兜底：确保所有路径都有返回值
                return final_response if isinstance(final_response, str) else ""
        except TimeoutException as e:
            error_msg = f"等待回复元素超时: {e}"
            # print(f"[获取回复错误] {error_msg}")
            raise Exception(error_msg) from e
        except StaleElementReferenceException as e:
            error_msg = f"元素失效 (StaleElementReferenceException): {e}"
            # print(f"[获取回复错误] {error_msg}")
            raise Exception(error_msg) from e
        except Exception as e:
            error_msg = f"获取回复时发生未知错误: {e}"
            # print(f"[获取回复错误] {error_msg}")
            import traceback
            # traceback.print_exc()
            raise Exception(error_msg) from e

    def chat(self, message, enable_thinking=True, enable_search=True):
        """发送消息并获取回复的便捷方法。"""
        self.send_message(message, enable_thinking, enable_search)
        return self.get_response(enable_thinking=enable_thinking)

    def _extract_json_from_text(self, text: str) -> str:
        """
        从任意文本中提取第一个合法的 JSON 对象（最外层 {} 匹配）
        """
        # 使用栈匹配最外层花括号，确保提取完整 JSON
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
                        candidate = text[start:i+1]
                        try:
                            # 验证是否为合法 JSON
                            json.loads(candidate)
                            return candidate
                        except json.JSONDecodeError:
                            # 不是合法 JSON，继续找下一个 {
                            start = None
        # 未找到合法 JSON，返回原文（让上层手动解析尝试）
        return text
# --- 示例用法 ---
if __name__ == "__main__":
    client = None
    try:
        client = QwenChatClient(headless=True, max_wait_time=5, get_response_max_wait_time=180, start_minimized=True)
        client.load_chat_page()
        user_message_1 = "请介绍量子物理,用json格式输出。"
        response_1 = client.chat(user_message_1, False, False)
        print(f"[主程序] Qwen 回复 1:\n{response_1}")
    except Exception as e:
        print(f"[主程序错误] 运行出错: {e}")
        import traceback
        traceback.print_exc()
    finally:
        if client:
            # print("[主程序] 正在关闭浏览器...")
            client.close()