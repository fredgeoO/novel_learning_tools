import os
import json
import hashlib
import re
from datetime import datetime
from typing import List, Dict, Tuple, Optional, Any, Callable

from langchain_community.document_loaders import TextLoader
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_community.vectorstores import FAISS
from langchain.prompts import ChatPromptTemplate
from langchain_ollama import OllamaLLM

from langchain.schema.runnable import RunnablePassthrough, RunnableParallel, RunnableLambda
from langchain.schema import Document

from tqdm import tqdm
import gradio as gr


# ============================================================================
# 1. 配置 (Configuration)
# ============================================================================
class Config:
    """集中管理所有配置参数"""
    NOVELS_DIR = "novels"
    DB_DIR = "db"
    CHUNK_SIZE = 4000
    CHUNK_OVERLAP = 200
    TOP_K = 10
    EMBEDDING_MODEL_NAME = "BAAI/bge-large-zh-v1.5"
    LLM_MODEL = "qwen3:30b"
    EXCLUDED_KEYWORDS = [
        "上架", "感言", "抽奖", "中奖", "活动", "公告", "通知", "声明",
        "后记", "番外", "病假", "请假", "月票", "更新", "更章", "审核",
        "加更", "盟主", "打赏", "催更", "预告", "说明", "致谢"
    ]
    # 匹配章节标题的正则表达式
    CHAPTER_PATTERN = re.compile(
        r"第\s*([0-9]+|[一二三四五六七八九十百千万亿壹贰叁肆伍陆柒捌玖拾佰仟]+|[IVXLCDMivxlcdm]+)\s*[章回节篇幕集话卷]",
        re.IGNORECASE
    )
    # 查询优化提示词模板
    QUERY_REWRITE_TEMPLATE = """你是一个智能查询优化助手。你的任务是分析用户的原始问题，并将其改写成一个更适合用于语义向量数据库检索的查询语句。

    目标是让这个查询语句能够更精准地匹配到知识库中包含答案的相关文档片段。

    请执行以下操作：
    1.  **识别核心要素**：提取问题中的关键名词、概念、实体（如人名、地名、作品名、专业术语）。
    2.  **理解深层意图**：思考用户提问的真正目的，可能需要查找的信息类型（例如，寻求定义、步骤、原因、描述、列表等）。
    3.  **扩展同义/近义词**：考虑与核心要素意思相近的词或常用表达。
    4.  **构建查询语句**：将以上信息整合成一个或几个关键词/短语的组合，用空格分隔。优先保留原始词汇，适当添加扩展词。

    **重要**：只输出优化后的查询语句，不要包含任何解释或其他文字。

    ---
    示例：
    原始问题：奇幻小说的开头怎么写？
    优化后查询：奇幻小说 开头 写作技巧 方法 第一章 情节引入 世界设定 开场白 引子 序章

    原始问题：赛博朋克世界里V是谁？
    优化后查询：赛博朋克 V 主角 身份 背景 角色介绍 人物设定 主人公

    ---
    现在，请优化以下问题：
    原始问题：{original_question}
    优化后查询：
    """

    # 最终回答提示词模板
    FINAL_ANSWER_TEMPLATE = """你是一个熟悉小说内容的助手。请根据以下上下文回答问题。


    上下文来自小说《{novel}》的章节《{chapter}》：
    {context}

    问题: {question}
    回答:"""


# ============================================================================
# 2. 工具函数 (Utility Functions)
# ============================================================================
def get_file_hash(file_path: str) -> Optional[str]:
    """计算文件内容的 SHA256 哈希值"""
    hash_sha256 = hashlib.sha256()
    try:
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hash_sha256.update(chunk)
    except Exception as e:
        print(f"计算文件哈希时出错 {file_path}: {e}")
        return None
    return hash_sha256.hexdigest()


def is_excluded_file(base_name: str, keywords: List[str]) -> bool:
    """检查文件名是否包含排除关键词"""
    base_name_lower = base_name.lower()
    return any(keyword.lower() in base_name_lower for keyword in keywords)


def is_chapter_file(base_name: str, pattern: re.Pattern) -> bool:
    """检查文件名是否匹配章节模式"""
    return bool(pattern.search(base_name))


def print_log(message: str, prefix: str = ""):
    """统一的日志打印函数"""
    print(f"{prefix}{message}")


# ============================================================================
# 3. 文件处理 (File Processing)
# ============================================================================
class FileManager:
    """处理文件的加载、扫描和过滤"""

    @staticmethod
    def scan_files(novels_dir: str) -> List[str]:
        """扫描 novels 目录下所有 .txt 文件"""
        txt_files = []
        for root, _, files in os.walk(novels_dir):
            for file in files:
                if file.endswith(".txt"):
                    txt_files.append(os.path.join(root, file))
        return txt_files

    @staticmethod
    def filter_files(file_paths: List[str]) -> List[str]:
        """根据优先级规则过滤文件列表"""
        filtered_files = []
        skip_count = 0
        include_count = 0

        for file_path in file_paths:
            base_name, _ = os.path.splitext(os.path.basename(file_path))

            # 1. 最高优先级：检查是否匹配章节模式
            if is_chapter_file(base_name, Config.CHAPTER_PATTERN):
                filtered_files.append(file_path)
                include_count += 1
            else:
                # 2. 次优先级：检查是否包含排除关键词
                if is_excluded_file(base_name, Config.EXCLUDED_KEYWORDS):
                    skip_count += 1
                else:
                    # 3. 默认：包含
                    filtered_files.append(file_path)
                    include_count += 1

        print_log(f"扫描完成: 总共 {len(file_paths)} 个文件, 包含 {include_count} 个, 跳过 {skip_count} 个。")
        return filtered_files

    @staticmethod
    def load_documents(file_paths: List[str], novels_dir: str) -> List[Document]:
        """加载并处理文档列表"""
        documents = []
        loaded_count = 0
        skip_count = 0
        error_count = 0

        for file_path in file_paths:
            base_name, _ = os.path.splitext(os.path.basename(file_path))

            # 应用相同的过滤逻辑于加载阶段（安全检查）
            if is_chapter_file(base_name, Config.CHAPTER_PATTERN):
                pass
            else:
                if is_excluded_file(base_name, Config.EXCLUDED_KEYWORDS):
                    skip_count += 1
                    continue

            if file_path.endswith(".txt"):
                loader = TextLoader(file_path, encoding="utf-8")
                try:
                    docs = loader.load()
                    rel_path = os.path.relpath(file_path, novels_dir)
                    parts = rel_path.split(os.sep)
                    if len(parts) >= 2:
                        novel_name = parts[0]
                        chapter_name = os.path.splitext(parts[1])[0]
                        for doc in docs:
                            doc.metadata.update({
                                "novel": novel_name,
                                "chapter": chapter_name,
                                "source_file": file_path
                            })
                    documents.extend(docs)
                    loaded_count += 1
                except Exception as e:
                    error_count += 1
                    print_log(f"加载文件 {file_path} 时出错: {e}", "加载: ")

        print_log(f"加载完成: 成功加载 {loaded_count} 个文件, 跳过 {skip_count} 个, 出错 {error_count} 个。")
        return documents


# ============================================================================
# 4. 数据库管理 (Database Management)
# ============================================================================
class DatabaseManager:
    """管理 FAISS 向量数据库的加载、保存和更新"""

    @staticmethod
    def load(db_dir: str, embeddings: HuggingFaceEmbeddings) -> Optional[FAISS]:
        """从磁盘加载 FAISS 索引"""
        index_path = os.path.join(db_dir, "faiss_index")
        if os.path.exists(index_path):
            try:
                vectorstore = FAISS.load_local(index_path, embeddings, allow_dangerous_deserialization=True)
                print_log(f"FAISS 数据库已从 {index_path} 加载")
                return vectorstore
            except Exception as e:
                print_log(f"加载 FAISS 数据库时出错: {e}")
                return None
        else:
            print_log("未找到现有数据库，将创建新的。")
            return None

    @staticmethod
    def save(vectorstore: FAISS, db_dir: str):
        """保存 FAISS 索引到磁盘"""
        index_path = os.path.join(db_dir, "faiss_index")
        os.makedirs(db_dir, exist_ok=True)
        try:
            vectorstore.save_local(index_path)
            print_log(f"FAISS 数据库已保存至 {index_path}")
        except Exception as e:
            print_log(f"保存 FAISS 数据库时出错: {e}")

    @staticmethod
    def create(documents: List[Document], embeddings: HuggingFaceEmbeddings) -> FAISS:
        """从文档列表创建新的 FAISS 索引"""
        return FAISS.from_documents(documents, embeddings)

    @staticmethod
    def update_with_progress(splits: List[Document], embeddings: HuggingFaceEmbeddings) -> FAISS:
        """为文档切片创建向量，并显示进度条"""
        print_log("正在为新文本块创建向量...")
        progress_wrapper = EmbeddingProgressWrapper(embeddings, len(splits))  # embeddings 是原始模型
        try:
            new_vectorstore = FAISS.from_documents(splits, progress_wrapper)
            progress_wrapper.pbar.close()

            # --- 修复代码开始 ---
            # 确保 vectorstore 内部引用的是原始的 embeddings 模型，
            # 而不是 EmbeddingProgressWrapper 实例，以避免 'not callable' 错误。
            # 这在 retriever 需要调用 embeddings.embed_query 时很重要。
            if hasattr(new_vectorstore, 'embeddings'):
                # EmbeddingProgressWrapper 在 __init__ 中保存了原始模型为 self.embedding_model
                new_vectorstore.embeddings = progress_wrapper.embedding_model
            # --- 修复代码结束 ---

            return new_vectorstore
        except Exception as e:
            progress_wrapper.pbar.close()
            raise e


# ============================================================================
# 5. 文件清单管理 (Manifest Management)
# ============================================================================
class ManifestManager:
    """管理文件清单，用于跟踪文件变化"""

    @staticmethod
    def load(db_dir: str) -> Dict[str, Any]:
        """从磁盘加载文件清单"""
        manifest_path = os.path.join(db_dir, "file_manifest.json")
        if os.path.exists(manifest_path):
            try:
                with open(manifest_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                print_log(f"加载文件清单时出错: {e}")
        return {}

    @staticmethod
    def save(manifest: Dict[str, Any], db_dir: str):
        """保存文件清单到磁盘"""
        manifest_path = os.path.join(db_dir, "file_manifest.json")
        os.makedirs(db_dir, exist_ok=True)
        try:
            with open(manifest_path, 'w', encoding='utf-8') as f:
                json.dump(manifest, f, ensure_ascii=False, indent=4)
            print_log(f"文件清单已保存至 {manifest_path}")
        except Exception as e:
            print_log(f"保存文件清单时出错: {e}")

    @staticmethod
    def get_files_to_update(novels_dir: str, db_dir: str) -> Tuple[List[str], Dict[str, Any]]:
        """比较文件系统和记录，找出需要处理的文件"""
        existing_manifest = ManifestManager.load(db_dir)
        all_files = FileManager.scan_files(novels_dir)
        filtered_files = FileManager.filter_files(all_files)

        current_files_manifest = {}
        for file_path in filtered_files:
            try:
                file_hash = get_file_hash(file_path)
                if file_hash:
                    current_files_manifest[file_path] = {"hash": file_hash}
            except OSError as e:
                print_log(f"无法获取文件信息 {file_path}: {e}")

        files_to_process = []
        for file_path, current_info in current_files_manifest.items():
            if file_path not in existing_manifest:
                print_log(f"发现新文件: {file_path}")
                files_to_process.append(file_path)
            else:
                existing_info = existing_manifest[file_path]
                if current_info["hash"] != existing_info["hash"]:
                    print_log(f"发现文件已修改: {file_path}")
                    files_to_process.append(file_path)

        return files_to_process, current_files_manifest


# ============================================================================
# 6. 嵌入进度条包装器 (Embedding Progress Wrapper)
# ============================================================================
class EmbeddingProgressWrapper:
    """为嵌入模型添加进度条"""

    def __init__(self, embedding_model, total_docs):
        self.embedding_model = embedding_model
        self.total_docs = total_docs
        self.pbar = tqdm(total=total_docs, desc="生成向量", ncols=100)

    def embed_documents(self, texts):
        embeddings = self.embedding_model.embed_documents(texts)
        self.pbar.update(len(texts))
        return embeddings

    def embed_query(self, text):
        return self.embedding_model.embed_query(text)

    def __getattr__(self, name):
        return getattr(self.embedding_model, name)


# ============================================================================
# 7. RAG 链构建 (RAG Chain Construction)
# ============================================================================
class RAGChainBuilder:
    """构建和运行 RAG 问答链"""

    @staticmethod
    def format_docs(docs):
        """将检索到的文档列表格式化为包含上下文、小说名和章节名的字典"""
        print(f"[DEBUG] format_docs 接收到的原始文档数量: {len(docs)}")
        if not isinstance(docs, list):
            print(f"[WARNING] format_docs received non-list input: {type(docs)}. Converting to empty list.")
            docs = []

        novel = "未知小说"
        chapter = "未知章节"
        context_parts = []

        for i, doc in enumerate(docs):
            print(f"[DEBUG] 文档 {i + 1} 内容预览: {doc.page_content[:100]}...")
            if not hasattr(doc, 'metadata') or not isinstance(getattr(doc, 'metadata', None), dict):
                doc.metadata = {}
            if not hasattr(doc, 'page_content'):
                doc.page_content = "(无内容)"

            if novel == "未知小说" and "novel" in doc.metadata:
                novel = doc.metadata["novel"]
            if chapter == "未知章节" and "chapter" in doc.metadata:
                chapter = doc.metadata["chapter"]

            novel_part = doc.metadata.get('novel', '未知')
            chapter_part = doc.metadata.get('chapter', '未知')
            context_parts.append(f"[{novel_part}-{chapter_part}]: {doc.page_content}")

        context = "\n\n".join(context_parts) if context_parts else "未找到相关文档。"
        print(f"[DEBUG] 格式化后的上下文:\n{context}")

        result_dict = {
            "context": context,
            "novel": novel,
            "chapter": chapter
        }
        return result_dict

    # --- 新增/修改的辅助函数 ---
    @staticmethod
    def _create_query_optimizer(query_rewrite_llm, query_rewrite_prompt: ChatPromptTemplate) -> RunnableLambda:
        """创建查询优化器组件"""
        def rewrite_query(original_question_dict):
            if not isinstance(original_question_dict, dict):
                print(
                    f"[ERROR] rewrite_query expected dict, got {type(original_question_dict)}: {original_question_dict}")
                return {"rewritten_query": ""}

            original_q = original_question_dict.get("question", "")
            print(f"[DEBUG] 用户输入问题: {original_q}")
            if not original_q:
                return {"rewritten_query": ""}

            try:
                prompt_value = query_rewrite_prompt.invoke({"original_question": original_q})
                rewritten_query = query_rewrite_llm.invoke(prompt_value)
                print(f"[DEBUG] 原始问题: {original_q}")
                print(f"[DEBUG] 优化后查询: {rewritten_query}")
                return {"rewritten_query": rewritten_query.strip()}
            except Exception as e:
                print(f"[ERROR] 查询优化时出错: {e}。将使用原始问题进行检索。")
                return {"rewritten_query": original_q}

        return RunnableLambda(rewrite_query)

    @staticmethod
    def _create_input_wrapper() -> RunnableLambda:
        """创建输入包装器，将字符串转换为字典"""
        def wrap_input(question_str: str) -> Dict[str, Any]:
            if not isinstance(question_str, str):
                question_str = str(question_str) if question_str is not None else ""
            return {"question": question_str}
        return RunnableLambda(wrap_input)

    @staticmethod
    def _create_optimized_query_retrieval_chain(
        query_optimizer: RunnableLambda,
        retriever,
        format_docs_func: Callable
    ):
        """创建优化查询并检索的链条"""
        return (
            query_optimizer |
            (lambda x: x["rewritten_query"]) |
            retriever |
            format_docs_func
        )

    @staticmethod
    def _create_process_retrieved_context() -> Callable:
        """创建处理检索上下文的函数"""
        def process_retrieved_context(input_dict):
            if not isinstance(input_dict, dict):
                print(f"[ERROR] process_retrieved_context expected dict, got {type(input_dict)}: {input_dict}")
                return {
                    "context": "处理错误: 输入不是字典",
                    "novel": "未知小说",
                    "chapter": "未知章节",
                    "question": ""
                }

            cnc = input_dict.get("rewritten_query_result", {})
            print(f"[DEBUG] 检索到的原始结果 (cnc): {cnc}")

            if not isinstance(cnc, dict):
                print(
                    f"[ERROR] process_retrieved_context expected dict for rewritten_query_result, got {type(cnc)}: {cnc}")
                cnc = {"context": "处理错误", "novel": "未知", "chapter": "未知"}

            question = input_dict.get("question", "")
            if not isinstance(question, str):
                question = ""

            return {
                "context": cnc.get("context", "上下文缺失"),
                "novel": cnc.get("novel", "未知小说"),
                "chapter": cnc.get("chapter", "未知章节"),
                "question": question
            }
        return process_retrieved_context

    @staticmethod
    def build_rag_chain(vectorstore: FAISS, llm_model_name: str):
        """构建完整的 RAG 问答链 (包含 LLM 和查询优化)"""
        # 1. 基础组件
        retriever = vectorstore.as_retriever(search_kwargs={"k": Config.TOP_K})
        answer_llm = OllamaLLM(model=llm_model_name)
        query_rewrite_llm = OllamaLLM(model=Config.LLM_MODEL)
        query_rewrite_prompt = ChatPromptTemplate.from_template(Config.QUERY_REWRITE_TEMPLATE)
        final_prompt = ChatPromptTemplate.from_template(Config.FINAL_ANSWER_TEMPLATE)

        # 2. 构建链条组件
        query_optimizer = RAGChainBuilder._create_query_optimizer(query_rewrite_llm, query_rewrite_prompt)
        input_wrapper = RAGChainBuilder._create_input_wrapper()
        optimized_query_retrieval_chain = RAGChainBuilder._create_optimized_query_retrieval_chain(
            query_optimizer, retriever, RAGChainBuilder.format_docs
        )
        process_context_func = RAGChainBuilder._create_process_retrieved_context()

        # 3. 组装最终链条
        rag_chain = (
                input_wrapper |
                RunnableParallel(
                    {
                        "question": lambda x: x["question"],
                        "rewritten_query_result": optimized_query_retrieval_chain
                    }
                ) |
                process_context_func |
                final_prompt |
                answer_llm
        )
        return rag_chain

    @staticmethod
    def _handle_debug_command(retrieval_debug_chain, user_input: str) -> str:
        """处理 debug 命令"""
        colon_index = user_input.find(':')
        if colon_index != -1 and colon_index + 1 < len(user_input):
            question = user_input[colon_index + 1:].strip()
        else:
            question = ""

        if not question:
            return "[DEBUG] 请输入要调试的问题，例如: debug: 谁是主角?"

        try:
            if retrieval_debug_chain:
                debug_result = retrieval_debug_chain.invoke(question)
                novel = debug_result.get("novel", "未知小说")
                chapter = debug_result.get("chapter", "未知章节")
                context_preview = debug_result.get("context", "无内容")[:200] + "..."
                return f"[DEBUG] 检索到相关内容:\n小说: {novel}\n章节: {chapter}\n上下文预览: {context_preview}"
            else:
                return "[DEBUG] 检索调试功能未初始化。"
        except Exception as e:
            return f"[DEBUG] 检索调试时出错: {e}"

    @staticmethod
    def run_interactive_qa(rag_chain, retrieval_debug_chain=None):
        """运行交互式问答循环，可选地包含检索调试功能"""
        print("\n--- RAG 系统已就绪，开始提问 ---")
        while True:
            user_input = input("\n请输入你的问题（输入 '退出' 结束，输入 'debug:你的问题' 查看检索结果）: ").strip()
            if not user_input:
                continue
            if user_input.lower() == "退出":
                break

            if user_input.lower().startswith("debug:"):
                if retrieval_debug_chain is None:
                    print("\n[DEBUG] 检索调试功能未启用。")
                    continue
                response = RAGChainBuilder._handle_debug_command(retrieval_debug_chain, user_input)
                print(f"\n{response}")
                print("\n" + "-" * 40)
                continue

            question = user_input
            print("\n回答:")
            try:
                full_response = ""
                for chunk in rag_chain.stream(question):
                    print(chunk, end="", flush=True)
                    full_response += chunk
                filtered_response = filter_think_tags(full_response)
                if filtered_response != full_response:
                    print(
                        f"\n[DEBUG] 已过滤掉思考内容，原始长度: {len(full_response)}, 过滤后长度: {len(filtered_response)}")
                print("\n" + "-" * 40)
            except Exception as e:
                print(f"\n生成回答时出错: {e}")
            print("\n" + "-" * 40)

    @staticmethod
    def build_retrieval_debug_chain(vectorstore: FAISS):
        """构建一个仅执行检索和格式化，不调用 LLM 的链条"""
        retriever = vectorstore.as_retriever(search_kwargs={"k": Config.TOP_K})

        retrieval_debug_chain = (
                RunnablePassthrough()
                | retriever
                | RAGChainBuilder.format_docs # 复用已有的格式化函数
        )
        return retrieval_debug_chain


# ============================================================================
# 8. 应用主类 (Application Main Class)
# ============================================================================
class RAGNovelQAApp:
    """RAG 小说问答应用的主类"""

    def __init__(self):
        """初始化应用，加载模型"""
        print("--- RAG 小说问答系统启动中 ---")
        print_log("正在加载嵌入模型...")
        self.embedding_model = HuggingFaceEmbeddings(model_name=Config.EMBEDDING_MODEL_NAME)
        self.vectorstore: Optional[FAISS] = None
        self.rag_chain = None
        self.retrieval_debug_chain = None

    def _update_database(self):
        """处理数据库更新逻辑"""
        print_log("正在检查小说文件更新...")
        files_to_process, updated_manifest = ManifestManager.get_files_to_update(Config.NOVELS_DIR, Config.DB_DIR)

        if files_to_process:
            print_log(f"发现 {len(files_to_process)} 个文件需要处理。")
            print_log("正在加载需要更新的小说文件...")
            new_documents = FileManager.load_documents(files_to_process, Config.NOVELS_DIR)

            if new_documents:
                print_log("正在切分新文档...")
                text_splitter = RecursiveCharacterTextSplitter(
                    chunk_size=Config.CHUNK_SIZE,
                    chunk_overlap=Config.CHUNK_OVERLAP
                )
                new_splits = text_splitter.split_documents(new_documents)
                print_log(f"新文件切分为 {len(new_splits)} 个文本块。")

                new_vectorstore = DatabaseManager.update_with_progress(new_splits, self.embedding_model)

                if self.vectorstore is None:
                    self.vectorstore = new_vectorstore
                    print_log("创建了新的向量数据库。")
                else:
                    print_log("正在将新向量合并到现有数据库...")
                    self.vectorstore.merge_from(new_vectorstore)
                    print_log("数据库合并完成。")

                print_log("正在保存更新后的数据库和文件清单...")
                DatabaseManager.save(self.vectorstore, Config.DB_DIR)
                ManifestManager.save(updated_manifest, Config.DB_DIR)
            else:
                print_log("没有加载到新的有效文档。")
        else:
            print_log("没有发现需要更新的文件。数据库已是最新。")
            if self.vectorstore is None:
                print_log("未找到任何文件，创建空数据库。")
                dummy_doc = Document(page_content="初始化数据库", metadata={"source": "system"})
                self.vectorstore = DatabaseManager.create([dummy_doc], self.embedding_model)
                DatabaseManager.save(self.vectorstore, Config.DB_DIR)
                ManifestManager.save(updated_manifest, Config.DB_DIR)

    def _setup_qa(self):
        """设置问答环境"""
        self.vectorstore = DatabaseManager.load(Config.DB_DIR, self.embedding_model)
        self._update_database()

        if self.vectorstore:
            print_log("向量数据库准备就绪。")
        else:
            print_log("未能初始化向量数据库，无法进行检索。")
            return False

        print_log("正在加载语言模型...")
        self.rag_chain = RAGChainBuilder.build_rag_chain(self.vectorstore, Config.LLM_MODEL)
        print_log("语言模型加载完成。")

        print_log("正在构建检索调试链...")
        self.retrieval_debug_chain = RAGChainBuilder.build_retrieval_debug_chain(self.vectorstore)
        print_log("检索调试链构建完成。")

        return True

    def run(self):
        """运行应用主循环"""
        if self._setup_qa():
            RAGChainBuilder.run_interactive_qa(self.rag_chain, self.retrieval_debug_chain)
        else:
            print("应用初始化失败，无法启动问答。")


# ============================================================================
# 10. Gradio 集成 (Gradio Integration)
# ============================================================================
rag_app_instance: RAGNovelQAApp = None


def initialize_app():
    """初始化 RAG 应用实例"""
    global rag_app_instance
    if rag_app_instance is None:
        print("--- 正在通过 Gradio 初始化 RAG 应用 ---")
        rag_app_instance = RAGNovelQAApp()
        success = rag_app_instance._setup_qa()
        if not success:
            print("--- RAG 应用初始化失败 ---")
        else:
            print("--- RAG 应用初始化成功 ---")
    return rag_app_instance

def filter_think_tags(text: str) -> str:
    """过滤掉 <think>...</think> 标签及其内容"""
    import re
    filtered_text = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL)
    filtered_text = re.sub(r'\n\s*\n', '\n\n', filtered_text).strip()
    return filtered_text

def respond(message, history):
    """
    Gradio ChatInterface 调用的函数。
    :param message: 用户输入的消息 (问题)
    :param history: 当前的聊天历史
    :return: 助手的回复
    """
    global rag_app_instance

    # 初始化应用（如果尚未初始化）
    if rag_app_instance is None:
        initialize_app()

    if rag_app_instance is None or rag_app_instance.rag_chain is None:
        return "抱歉，系统正在初始化或遇到了问题，请稍后再试。"

    # 处理特殊命令
    if message.lower() == "退出":
        return "再见！感谢使用RAG小说问答系统。"

    # 处理调试命令 - 重用 RAGChainBuilder 的逻辑
    if message.lower().startswith("debug:"):
        debug_query = message[6:].strip()
        if not debug_query:
            return "[DEBUG] 请输入要调试的问题，例如: debug: 谁是主角?"
        try:
            if rag_app_instance.retrieval_debug_chain:
                # 直接调用 debug chain 的 invoke 方法
                debug_result = rag_app_instance.retrieval_debug_chain.invoke(debug_query)
                novel = debug_result.get("novel", "未知小说")
                chapter = debug_result.get("chapter", "未知章节")
                context_preview = debug_result.get("context", "无内容")[:200] + "..."
                return f"[DEBUG] 检索到相关内容:\n小说: {novel}\n章节: {chapter}\n上下文预览: {context_preview}"
            else:
                return "[DEBUG] 检索调试功能未初始化。"
        except Exception as e:
            return f"[DEBUG] 检索调试时出错: {e}"

    # 正常问答
    user_question = message
    print(f"[Gradio] 收到问题: {user_question}")

    try:
        full_response = ""
        if not isinstance(user_question, str):
            user_question = str(user_question)

        for chunk in rag_app_instance.rag_chain.stream(user_question):
            full_response += chunk
        print(f"[Gradio] 生成回答: {full_response[:50]}...")
        full_response = filter_think_tags(full_response)
        return full_response
    except Exception as e:
        error_msg = f"处理请求时发生内部错误: {e}"
        print(f"[Gradio] 内部错误: {error_msg}")
        import traceback
        traceback.print_exc()
        return error_msg


# ============================================================================
# 11. 主函数 (Main Function) - 修改为 Gradio 启动
# ============================================================================
def main():
    """主程序入口 - 使用 Gradio 启动 Web 界面"""
    initialize_app()

    with gr.Blocks(title="📚 RAG 小说问答系统", css="""
        .gradio-container { max-width: 1200px !important; }
        .message.user { background-color: #e6f7ff !important; }
        .message.bot { background-color: #f6ffed !important; }
        .chatbot { height: 70vh !important; min-height: 500px; }
        .input-box { padding: 20px; background: #f0f2f6; border-radius: 10px; }
    """) as demo:
        gr.Markdown("# 📚 RAG 小说问答系统")
        gr.Markdown("基于你的本地小说知识库进行问答。输入问题，或使用 'debug:你的问题' 查看检索到的上下文。")

        chatbot = gr.Chatbot(
            label="对话历史",
            height=600,
            show_copy_button=True,
            type="messages"
        )

        with gr.Row():
            msg = gr.Textbox(
                label="输入问题",
                placeholder="请输入您的问题...",
                lines=2,
                max_lines=5,
                scale=4
            )
            submit_btn = gr.Button("发送", variant="primary", scale=1)
            clear_btn = gr.Button("清除", variant="secondary", scale=1)

        gr.Examples(
            examples=[
                "赛博朋克世界里V是谁？",
                "奇幻小说的开头怎么写？",
                "debug:谁是主角"
            ],
            inputs=msg,
            label="示例问题"
        )

        def respond_custom(message, chat_history):
            response = respond(message, chat_history)
            chat_history.append({"role": "user", "content": message})
            chat_history.append({"role": "assistant", "content": response})
            return "", chat_history

        msg.submit(respond_custom, [msg, chatbot], [msg, chatbot])
        submit_btn.click(respond_custom, [msg, chatbot], [msg, chatbot])
        clear_btn.click(lambda: None, None, chatbot, queue=False)

    print("--- 启动 Gradio Web 界面 ---")
    demo.launch(
        share=False,
        server_name="127.0.0.1",
        server_port=7860,
        show_error=True
    )


def main_cli():
    """原始的命令行交互入口"""
    app = RAGNovelQAApp()
    app.run()


if __name__ == "__main__":
    # main() # 使用 Gradio 界面
    main_cli() # 或者使用命令行界面