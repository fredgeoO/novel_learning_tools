import requests
import json
import re
import math


class OllamaClient:
    def __init__(self, base_url="http://localhost:11434", model_name="qwen3:30b",
                 remove_think_tags=True, context_length=32768):
        self.base_url = base_url.rstrip('/')
        self.model_name = model_name
        self.remove_think_tags = remove_think_tags
        self.context = []  # 对话上下文
        self.default_context_length = context_length  # 默认上下文窗口大小

    def generate(self, prompt, **kwargs):
        """
        生成文本响应，自动移除<think>标签内容（如果启用）
        支持对话上下文管理和自定义上下文长度

        Args:
            prompt: 输入提示
            **kwargs: 可选参数（options, system, max_tokens等）
        """
        # 初始化data时直接包含options字典
        data = {
            "model": self.model_name,
            "prompt": prompt,
            "stream": False,  # 强制关闭流式响应
            "context": self.context,
            "options": {}  # 确保options始终存在且是字典
        }

        # 处理额外参数
        for key, value in kwargs.items():
            if key == 'options':
                # 确保options是字典
                if value is None:
                    data['options'] = {}
                elif isinstance(value, dict):
                    data['options'] = value
                else:
                    data['options'] = {}
            elif key in ['system', 'format', 'images']:
                data[key] = value
            else:
                data['options'][key] = value

        # 动态计算或使用固定上下文长度
        if self.default_context_length is None:
            # 动态计算上下文长度
            input_tokens = self._estimate_tokens(prompt)
            max_tokens = data['options'].get('max_tokens', 2048)
            total_needed = input_tokens + max_tokens + 512  # 添加缓冲
            num_ctx = max(4096, min(32768, total_needed))

            # 调试信息
            print(f"[调试] 动态上下文配置: 输入={input_tokens} tokens | "
                  f"max_tokens={max_tokens} | 需求={total_needed} | 实际设置={num_ctx}")
        else:
            # 使用固定的上下文长度
            num_ctx = self.default_context_length

        # 确保上下文窗口大小设置
        if 'num_ctx' not in data['options']:
            data['options']['num_ctx'] = num_ctx

        try:
            response = requests.post(f"{self.base_url}/api/generate",
                                     json=data)
            response.raise_for_status()
        except Exception as e:
            error_msg = e.response.text if hasattr(e, 'response') and e.response else str(e)
            raise Exception(f"Ollama请求失败: {error_msg}")

        # 处理响应
        try:
            result = response.json()
            response_text = result.get('response', '')
            # 更新上下文
            self.context = result.get('context', [])

            # 移除<think>标签（如果启用）
            if self.remove_think_tags:
                response_text = re.sub(r'<!--.*?-->', '', response_text, flags=re.DOTALL)  # 移除HTML注释
                response_text = re.sub(r'<think>.*?</think>', '', response_text, flags=re.DOTALL)
                response_text = re.sub(r'\n\s*\n', '\n\n', response_text).strip()

            return response_text
        except json.JSONDecodeError as e:
            raise Exception(f"JSON解析失败: {str(e)}")

    def reset_context(self):
        """重置对话上下文"""
        self.context = []

    def get_context_length(self):
        """获取当前上下文长度"""
        return len(self.context)

    def _estimate_tokens(self, text, is_chinese=True):
        """估算文本的token数量（中文字符≈1.7 tokens）"""
        if is_chinese:
            return math.ceil(len(text) * 1.7)
        return len(text.split())  # 英文按单词估算


# 测试代码
if __name__ == "__main__":
    # 创建客户端（启用动态上下文配置）
    client = OllamaClient(context_length=None)  # 设置为None以启用动态配置

    # 测试1：短文本（约500字）
    print("\n=== 短文本测试（约500字） ===")
    short_prompt = "请解释量子力学中的波粒二象性"
    response = client.generate(short_prompt)
    print("响应内容:", response[:200] + ("..." if len(response) > 200 else ""))

    # 测试2：中等长度文本（约4000字故事分析）
    print("\n=== 中等长度测试（约4000字故事） ===")
    medium_prompt = "请详细分析以下故事章节：\n" + "故事内容" * 1000  # 模拟4000字输入
    response = client.generate(medium_prompt)
    print("响应内容:", response[:200] + ("..." if len(response) > 200 else ""))

    # 测试3：手动指定上下文长度
    print("\n=== 手动指定上下文长度测试 ===")
    client_fixed = OllamaClient(context_length=8192)  # 固定为8192
    response = client_fixed.generate("请解释相对论的基本原理")
    print("响应内容:", response[:200] + ("..." if len(response) > 200 else ""))