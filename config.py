# config.py
"""
RAG 应用共享配置
"""

import os

# 获取当前文件所在目录
CONFIG_DIR = os.path.dirname(os.path.abspath(__file__))
# 项目根目录 = config.py 所在目录（假设 config.py 在项目根目录下）
PROJECT_ROOT = CONFIG_DIR

# 定义所有路径
NOVELS_BASE_DIR = os.path.join(PROJECT_ROOT, "novels")
REPORTS_BASE_DIR = os.path.join(PROJECT_ROOT, "reports", "novels")
PROMPT_ANALYZER_DIR = os.path.join(PROJECT_ROOT, "inputs", "prompts", "analyzer")
METADATA_FILE_PATH = os.path.join(PROMPT_ANALYZER_DIR, "metadata.json")
SCRAPED_DATA_DIR = os.path.join(PROJECT_ROOT, "scraped_data")
BROWSE_HISTORY_FILE = os.path.join(PROJECT_ROOT, "browse_history.json")
RANKING_FILE = os.path.join(PROJECT_ROOT, "scraped_data", "所有分类月票榜汇总.txt")
CACHE_DIR = os.path.join(PROJECT_ROOT, "cache")

# 确保必要的目录存在
os.makedirs(CACHE_DIR, exist_ok=True)
os.makedirs(NOVELS_BASE_DIR, exist_ok=True)
os.makedirs(REPORTS_BASE_DIR, exist_ok=True)
os.makedirs(PROMPT_ANALYZER_DIR, exist_ok=True)
os.makedirs(SCRAPED_DATA_DIR, exist_ok=True)

# 默认模型配置
DEFAULT_MODEL = "qwen3:30b-a3b-instruct-2507-q4_K_M"
DEFAULT_BASE_URL = "http://localhost:11434"
DEFAULT_TEMPERATURE = 0.0
DEFAULT_NUM_CTX = 16384
DEFAULT_CHUNK_SIZE = 1536
DEFAULT_CHUNK_OVERLAP = 160

# Ollama 配置
OLLAMA_URL = "http://localhost:11434"

# 远程 API 配置
REMOTE_API_KEY = os.getenv("ARK_API_KEY")
REMOTE_BASE_URL = "https://ark.cn-beijing.volces.com/api/v3  "
REMOTE_MODEL_NAME = "doubao-seed-1-6-250615"

# 可选的远程模型列表（可以扩展）
REMOTE_MODEL_CHOICES = [
    "doubao-seed-1-6-250615",
    "doubao-seed-1-6-flash-250828",
    # 可以添加更多远程模型
]