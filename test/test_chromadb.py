# test/test_chromadb.py

import chromadb
from sentence_transformers import SentenceTransformer  # ← 替换 embedding_functions
from pathlib import Path

from sympy.printing.pytorch import torch


def load_novels_simple(
        novels_dir: str = "../novels",
        db_path: str = "test/chroma_qwen3",
        collection_name: str = "chapters",
        max_novels: int = 2,
        max_chapters_per_novel: int = 3,
        skip_list: list = None
):
    if skip_list is None:
        skip_list = []

    novels_path = Path(novels_dir)
    if not novels_path.exists():
        raise FileNotFoundError(f"小说目录不存在: {novels_path.absolute()}")

    db_path = Path(db_path)
    db_path.mkdir(parents=True, exist_ok=True)

    # 初始化 Chroma（持久化）
    client = chromadb.PersistentClient(path=str(db_path))

    # 🔥 加载 Qwen3-Embedding-8B 模型（首次运行自动下载）
    print("🚀 正在加载 Qwen3-Embedding-8B 模型（首次运行需下载 ~15GB）...")
    embed_model = SentenceTransformer(
        "Qwen/Qwen3-Embedding-8B",
        tokenizer_kwargs={"padding_side": "left"},
        trust_remote_code=True,
        device="cuda" if torch.cuda.is_available() else "cpu"
    )
    print("✅ 模型加载完成")

    # 创建集合（不指定 embedding_function，我们手动 encode）
    collection = client.get_or_create_collection(name=collection_name)

    documents = []
    ids = []

    # 获取并过滤小说文件夹
    all_novel_folders = [f for f in novels_path.iterdir() if f.is_dir()]
    filtered_novel_folders = [
        f for f in all_novel_folders
        if not any(skip in f.name for skip in skip_list)
    ][:max_novels]

    for novel_folder in filtered_novel_folders:
        novel_name = novel_folder.name
        print(f"📖 处理小说: {novel_name}")

        # 获取并过滤章节文件
        all_chapter_files = sorted(novel_folder.glob("*.txt"))
        filtered_chapter_files = [
            cf for cf in all_chapter_files
            if not any(skip in cf.name for skip in skip_list)
        ][:max_chapters_per_novel]

        for i, chapter_file in enumerate(filtered_chapter_files):
            try:
                text = chapter_file.read_text(encoding="utf-8").strip()
                if text:
                    doc_id = f"{novel_name}_ch{i + 1}"
                    documents.append(text)
                    ids.append(doc_id)
            except Exception as e:
                print(f"⚠️ 读取失败: {chapter_file} - {e}")

    # 🔥 使用 Qwen3 模型生成 embedding
    if documents:
        print(f"🧠 正在为 {len(documents)} 个章节生成 embedding...")
        # 对文档使用默认编码（无 prompt）
        doc_embeddings = embed_model.encode(
            documents,
            batch_size=8,  # 根据 GPU 调整
            show_progress_bar=True
        )

        collection.add(
            embeddings=doc_embeddings.tolist(),  # 转为 list 供 Chroma 使用
            documents=documents,
            ids=ids
        )
        print(f"✅ 成功导入 {len(documents)} 个章节")
    else:
        print("❌ 未找到有效文本")

    # 保存模型引用，用于后续查询
    collection._embed_model = embed_model  # 临时挂载（非官方做法，仅演示）
    return collection


def simple_query(collection, query_text: str, n_results: int = 3):
    """使用 Qwen3 模型对查询进行 embedding"""
    print(f'\n🔍 搜索: "{query_text}"')

    # 使用 "query" prompt 提升效果（官方推荐）
    query_emb = collection._embed_model.encode(
        [query_text],
        prompt_name="query",  # ← 关键：使用内置 query prompt
        show_progress_bar=False
    )

    results = collection.query(
        query_embeddings=query_emb.tolist(),
        n_results=n_results
    )

    for i, (doc, _id) in enumerate(zip(results['documents'][0], results['ids'][0])):
        print(f"\n--- 结果 {i + 1} (ID: {_id}) ---")
        print(doc[:300] + "..." if len(doc) > 300 else doc)


if __name__ == "__main__":
    SKIP_LIST = ["111.测试文档", "草稿", "temp"]

    coll = load_novels_simple(
        novels_dir="../novels",
        max_novels=2,
        max_chapters_per_novel=3,
        skip_list=SKIP_LIST
    )

    simple_query(coll, "主角假装很弱，其实很强")
    simple_query(coll, "系统突然激活，赐予他无敌功法")