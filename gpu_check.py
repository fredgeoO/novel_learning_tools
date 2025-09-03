from langchain_huggingface import HuggingFaceEmbeddings
# --- 新增诊断代码 ---
import torch
print("--- 系统环境诊断 ---")
print(f"PyTorch 版本: {torch.__version__}")
print(f"CUDA 是否可用: {torch.cuda.is_available()}")
if torch.cuda.is_available():
    print(f"GPU 型号: {torch.cuda.get_device_name(0)}")
    print(f"CUDA 版本: {torch.version.cuda}")
else:
    print("CUDA 不可用，将使用 CPU 进行嵌入计算。")
print("-------------------")