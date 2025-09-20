# inputs/rag/config.py
"""
RAG 应用共享配置
"""

import os


CACHE_DIR ="C:\\Users\\zgw31\\PycharmProjects\\AI\\cache"

# 确保缓存目录存在

# 确保缓存目录存在
os.makedirs(CACHE_DIR, exist_ok=True)

# 默认模型配置
DEFAULT_MODEL = "qwen3:30b"
DEFAULT_BASE_URL = "http://localhost:11434"
DEFAULT_TEMPERATURE = 0.0
DEFAULT_NUM_CTX = 8192
DEFAULT_CHUNK_SIZE = 1536
DEFAULT_CHUNK_OVERLAP = 160

# Ollama 配置
OLLAMA_URL = "http://localhost:11434"

# 远程 API 配置
REMOTE_API_KEY = os.getenv("ARK_API_KEY")
REMOTE_BASE_URL = "https://ark.cn-beijing.volces.com/api/v3"
REMOTE_MODEL_NAME = "doubao-seed-1-6-250615"

# 可选的远程模型列表（可以扩展）
REMOTE_MODEL_CHOICES = [
    "doubao-seed-1-6-250615",
    "doubao-seed-1-6-flash-250828",
    # 可以添加更多远程模型
]

