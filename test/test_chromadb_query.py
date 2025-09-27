# test/query.py
import chromadb
from sentence_transformers import SentenceTransformer
import torch

def load_embed_model():
    """只在查询时按需加载 embedding 模型（其实也可以缓存，但查询频率低，影响不大）"""
    print("🔍 加载 Qwen3 Embedding 模型用于查询...")
    return SentenceTransformer(
        "Qwen/Qwen3-Embedding-8B",
        tokenizer_kwargs={"padding_side": "left"},
        trust_remote_code=True,
        device="cuda" if torch.cuda.is_available() else "cpu"
    )

def query_chroma(query_text: str, n_results: int = 3):
    # 1. 连接已有数据库（不重新入库！）
    client = chromadb.PersistentClient(path="test/chroma_qwen3")
    collection = client.get_collection("chapters")

    # 2. 仅对查询文本生成 embedding
    embed_model = load_embed_model()
    query_emb = embed_model.encode([query_text], prompt_name="query")

    # 3. 查询并打印结果
    results = collection.query(
        query_embeddings=query_emb.tolist(),
        n_results=n_results
    )

    for i, (doc, _id) in enumerate(zip(results['documents'][0], results['ids'][0])):
        print(f"\n--- 结果 {i+1} (ID: {_id}) ---")
        print(doc[:300] + "..." if len(doc) > 300 else doc)

if __name__ == "__main__":
    query_chroma("男主角是谁")