# selenium_qwen_service.py
from flask import Flask, request, jsonify
# 假设你将原始的 QwenChatClient 类保存在 qwen_chat_client.py 中
# 确保 qwen_chat_client.py 与本文件在同一目录，或在 Python 路径中
from qwen_chat_client import QwenChatClient
import traceback

app = Flask(__name__)

# --- 移除了全局 client_instance 的初始化 ---

@app.route('/chat', methods=['POST'])
def chat():
    """
    接收聊天请求，按需启动浏览器，处理请求，然后关闭浏览器。
    """
    # 1. 从请求中解析参数
    data = request.get_json()
    message = data.get('message', '')
    enable_thinking = data.get('enable_thinking', True)
    enable_search = data.get('enable_search', True)
    # 可以添加更多参数，例如 headless, max_wait_time 等，如果需要动态控制的话
    # headless = data.get('headless', True)
    # max_wait_time = data.get('max_wait_time', 5)

    if not message:
        return jsonify({"error": "No message provided"}), 400

    client_instance = None
    try:
        # 2. 在收到请求后创建客户端实例
        #    可以根据请求参数动态配置客户端
        print("[服务] 收到请求，正在启动浏览器...")
        client_instance = QwenChatClient(
            headless=True,           # 可以设为 True 以节省资源
            get_response_max_wait_time=400,
            max_wait_time=10,        # 可以根据需要调整
            start_minimized=True     # 可以设为 True
        )
        print("[服务] 浏览器启动成功，正在加载页面...")
        client_instance.load_chat_page() # 加载 Qwen 页面
        print("[服务] 页面加载完成。")

        # 3. 发送消息并获取回复
        print(f"[服务] 正在发送消息: {message[:50]}...") # 打印消息摘要
        # 根据您的 QwenChatClient 最新修改，可以选择获取 Markdown 格式
        # reply = client_instance.chat_md(message, enable_thinking, enable_search)
        # 或者获取纯文本格式 (默认)
        reply = client_instance.chat(message, enable_thinking, enable_search)
        print(f"[服务] 成功获取回复 (长度: {len(reply)} 字符)。")

        # 4. 准备成功响应
        response_data = {"reply": reply}
        status_code = 200

    except Exception as e:
        # 5. 处理错误
        error_details = traceback.format_exc()
        print(f"[服务错误] 处理请求时发生错误: {e}")
        print(f"[服务错误详情] {error_details}")
        # 准备错误响应
        response_data = {
            "error": f"Chat failed: {str(e)}",
            "details": error_details # 在生产环境中，可能不希望返回详细错误栈
        }
        status_code = 500

    finally:
        # 6. 无论成功与否，都尝试关闭浏览器
        if client_instance:
            try:
                print("[服务] 正在关闭浏览器...")
                client_instance.close()
                print("[服务] 浏览器已关闭。")
            except Exception as close_error:
                print(f"[服务警告] 关闭浏览器时出错: {close_error}")
                # 不应因关闭错误而覆盖主逻辑的响应
                # 如果需要，可以在 response_data 中添加关闭状态信息
                # 但通常主错误更重要
        else:
             print("[服务] 未创建客户端实例，无需关闭浏览器。")

    # 7. 返回 JSON 响应
    return jsonify(response_data), status_code

if __name__ == '__main__':
    print("[服务] 启动中...")
    # 注意：在按需启动模式下，debug=True 可能会导致问题，
    # 因为它会重启应用，可能干扰浏览器实例的管理。
    # 建议在生产环境中使用 WSGI 服务器 (如 Gunicorn)。
    app.run(host='0.0.0.0', port=5000, debug=False)
