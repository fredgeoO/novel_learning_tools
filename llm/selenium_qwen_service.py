# selenium_qwen_service.py
from flask import Flask, request, jsonify
from qwen_chat_client import QwenChatClient
import traceback
import json

app = Flask(__name__)

# 使用与你现有代码相同的配置
QWEN_HEADLESS = True
QWEN_MAX_WAIT_TIME = 5
QWEN_GET_RESPONSE_MAX_WAIT_TIME = 1000
QWEN_START_MINIMIZED = True


@app.route('/api/generate', methods=['POST'])
def generate():
    """
    Ollama API格式的接口，但使用Selenium驱动Qwen网页版
    """
    # 1. 从请求中解析参数（匹配Ollama API格式）
    data = request.get_json()
    prompt = data.get('prompt', '')
    model = data.get('model', 'qwen-web')
    stream = data.get('stream', False)

    # 从你的配置中获取参数
    headless = data.get('headless', QWEN_HEADLESS)
    max_wait_time = data.get('max_wait_time', QWEN_MAX_WAIT_TIME)
    get_response_max_wait_time = data.get('get_response_max_wait_time', QWEN_GET_RESPONSE_MAX_WAIT_TIME)
    start_minimized = data.get('start_minimized', QWEN_START_MINIMIZED)

    # Qwen特定参数
    enable_thinking = data.get('enable_thinking', False)
    enable_search = data.get('enable_search', False)  # 默认关闭搜索以提高稳定性

    if not prompt:
        return jsonify({"error": "No prompt provided"}), 400

    client_instance = None
    try:
        # 2. 创建客户端实例（使用与你现有代码相同的配置）
        print("[服务] 收到请求，正在启动浏览器...")
        client_instance = QwenChatClient(
            headless=headless,
            max_wait_time=max_wait_time,
            get_response_max_wait_time=get_response_max_wait_time,
            start_minimized=start_minimized
        )
        print("[服务] 浏览器启动成功，正在加载页面...")
        client_instance.load_chat_page()
        print("[服务] 页面加载完成。")

        # 3. 发送消息并获取回复
        print(f"[服务] 正在发送消息: {prompt[:50]}...")
        reply = client_instance.chat(prompt, enable_thinking, enable_search)
        print(f"[服务] 成功获取回复 (长度: {len(reply)} 字符)。")

        # 4. 构造Ollama API格式的响应
        response_data = {
            "model": model,
            "response": reply,
            "done": True
        }

        status_code = 200

    except Exception as e:
        error_details = traceback.format_exc()
        print(f"[服务错误] 处理请求时发生错误: {e}")
        print(f"[服务错误详情] {error_details}")

        response_data = {
            "error": f"Generation failed: {str(e)}",
            "model": model
        }
        status_code = 500

    finally:
        # 6. 关闭浏览器（确保资源释放）
        if client_instance:
            try:
                print("[服务] 正在关闭浏览器...")
                client_instance.close()
                print("[服务] 浏览器已关闭。")
            except Exception as close_error:
                print(f"[服务警告] 关闭浏览器时出错: {close_error}")
        else:
            print("[服务] 未创建客户端实例，无需关闭浏览器。")

    # 7. 返回Ollama API格式的JSON响应
    return jsonify(response_data), status_code


@app.route('/api/tags', methods=['GET'])
def list_models():
    """返回可用模型列表（匹配Ollama API格式）"""
    return jsonify({
        "models": [
            {
                "name": "qwen-web",
                "model": "qwen-web",
                "modified_at": "2024-01-01T00:00:00Z",
                "size": 0,
                "digest": "web-interface",
                "details": {
                    "format": "web",
                    "family": "qwen",
                    "families": ["qwen"],
                    "parameter_size": "web",
                    "quantization_level": "web"
                }
            }
        ]
    })


@app.route('/', methods=['GET'])
def health_check():
    """健康检查"""
    return jsonify({
        "status": "healthy",
        "service": "Selenium Qwen Service",
        "compatible_with": "Ollama API v0.1"
    })


@app.route('/chat', methods=['POST'])
def chat_legacy():
    """
    保持向后兼容的旧版聊天接口
    """
    data = request.get_json()
    message = data.get('message', '')
    enable_thinking = data.get('enable_thinking', True)
    enable_search = data.get('enable_search', False)

    headless = data.get('headless', QWEN_HEADLESS)
    max_wait_time = data.get('max_wait_time', QWEN_MAX_WAIT_TIME)
    get_response_max_wait_time = data.get('get_response_max_wait_time', QWEN_GET_RESPONSE_MAX_WAIT_TIME)
    start_minimized = data.get('start_minimized', QWEN_START_MINIMIZED)

    if not message:
        return jsonify({"error": "No message provided"}), 400

    client_instance = None
    try:
        print("[服务] 收到请求，正在启动浏览器...")
        client_instance = QwenChatClient(
            headless=headless,
            max_wait_time=max_wait_time,
            get_response_max_wait_time=get_response_max_wait_time,
            start_minimized=start_minimized
        )
        print("[服务] 浏览器启动成功，正在加载页面...")
        client_instance.load_chat_page()
        print("[服务] 页面加载完成。")

        print(f"[服务] 正在发送消息: {message[:50]}...")
        reply = client_instance.chat(message, enable_thinking, enable_search)
        print(f"[服务] 成功获取回复 (长度: {len(reply)} 字符)。")

        response_data = {"reply": reply}
        status_code = 200

    except Exception as e:
        error_details = traceback.format_exc()
        print(f"[服务错误] 处理请求时发生错误: {e}")
        print(f"[服务错误详情] {error_details}")
        response_data = {
            "error": f"Chat failed: {str(e)}",
            "details": error_details
        }
        status_code = 500

    finally:
        if client_instance:
            try:
                print("[服务] 正在关闭浏览器...")
                client_instance.close()
                print("[服务] 浏览器已关闭。")
            except Exception as close_error:
                print(f"[服务警告] 关闭浏览器时出错: {close_error}")
        else:
            print("[服务] 未创建客户端实例，无需关闭浏览器。")

    return jsonify(response_data), status_code


if __name__ == '__main__':
    print("[服务] Selenium Qwen服务启动中...")
    print("接口兼容Ollama API格式:")
    print("  POST /api/generate  - 生成文本 (推荐)")
    print("  POST /chat          - 旧版聊天接口")
    print("  GET  /api/tags      - 模型列表")
    print("  GET  /              - 健康检查")
    print("\n配置参数:")
    print(f"  HEADLESS: {QWEN_HEADLESS}")
    print(f"  MAX_WAIT_TIME: {QWEN_MAX_WAIT_TIME}")
    print(f"  GET_RESPONSE_MAX_WAIT_TIME: {QWEN_GET_RESPONSE_MAX_WAIT_TIME}")
    print(f"  START_MINIMIZED: {QWEN_START_MINIMIZED}")
    app.run(host='0.0.0.0', port=5001, debug=False)