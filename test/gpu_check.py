import torch
from langchain_huggingface import HuggingFaceEmbeddings

print("=== PyTorch GPU 检测 ===")
print(f"PyTorch 版本: {torch.__version__}")
print(f"CUDA 可用: {torch.cuda.is_available()}")
if torch.cuda.is_available():
    print(f"GPU 名称: {torch.cuda.get_device_name(0)}")
    print(f"CUDA 版本 (PyTorch 编译版): {torch.version.cuda}")
    print(f"当前设备: {torch.cuda.current_device()}")

print("\n=== HuggingFaceEmbeddings 设备检测 ===")
embeddings = HuggingFaceEmbeddings(model_name="BAAI/bge-small-zh-v1.5")
print(f"嵌入模型设备: {embeddings.client.device}")