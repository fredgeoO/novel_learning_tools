# inputs/rag/narrative_schema.py
"""
定义用于 LLMGraphTransformer 的叙事元素和关系类型。
这些列表用于约束模型的输出，使其专注于特定的叙事分析任务。
采用分层结构，以平衡计算效率与写作分析深度。
"""
from langchain_ollama import OllamaLLM
from langchain_openai import ChatOpenAI
from openai import OpenAI
import os
from pydantic import BaseModel, Field
from typing import List, Dict, Optional
import hashlib
import json
from pathlib import Path
from rag.config import REMOTE_API_KEY, REMOTE_BASE_URL, REMOTE_MODEL_NAME, DEFAULT_MODEL
from langchain_core.output_parsers import JsonOutputParser
from langchain_core.prompts import PromptTemplate
import math
# --- 导入定义的常量 ---
from rag.schema_definitions import (
    BASIC_ELEMENTS, BASIC_RELATIONSHIPS, BASIC_SCHEMA,
    MINIMAL_ELEMENTS, MINIMAL_RELATIONSHIPS, MINIMAL_SCHEMA,
    PLOT_ELEMENTS, PLOT_RELATIONSHIPS, PLOT_SCHEMA,
    NO_SCHEMA, ALL_NARRATIVE_SCHEMAS, DEFAULT_SCHEMA
)

import logging


# --- 配置 ---
# 日志配置 (如果主程序已有，可以考虑移除或简化)
logging.basicConfig(level=logging.INFO, format='[%(asctime)s] [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

# 初始化OpenAI客户端
client = OpenAI(
    api_key=REMOTE_API_KEY,
    base_url=REMOTE_BASE_URL,
)


# 1. 定义 Pydantic 模型来表示期望的 Schema 结构
class SchemaModel(BaseModel):
    name: str = Field(description="根据文本内容生成的Schema名称")
    description: str = Field(description="Schema 的简要描述")
    elements: List[str] = Field(description="节点类型列表")
    relationships: List[str] = Field(description="关系类型列表")


def _get_text_hash(text_content: str, reference_schema: Optional[Dict] = None) -> str:
    """计算文本内容和参考schema的SHA256哈希值"""
    content = text_content
    if reference_schema:
        content += json.dumps(reference_schema, sort_keys=True)
    return hashlib.sha256(content.encode('utf-8')).hexdigest()


def _get_cache_path(text_hash: str) -> Path:
    """获取缓存文件路径"""
    cache_dir = Path("./cache/schema")
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir / f"{text_hash}.json"


def _load_schema_from_cache(text_hash: str) -> Dict:
    """从缓存加载schema"""
    cache_path = _get_cache_path(text_hash)
    if cache_path.exists():
        try:
            with open(cache_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"加载缓存失败: {e}")
    return None


def _save_schema_to_cache(text_hash: str, schema: Dict) -> None:
    """保存schema到缓存"""
    cache_path = _get_cache_path(text_hash)
    try:
        with open(cache_path, 'w', encoding='utf-8') as f:
            json.dump(schema, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"保存缓存失败: {e}")


def generate_auto_schema(
        text_content: str,
        model_name: str,
        # --- 参数 ---
        is_local: bool = True,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        use_cache: bool = True
) -> Dict:
    """
    根据文本内容生成知识图谱 Schema。

    Args:
        text_content (str): 用于分析的文本内容。
        model_name (str): 要使用的模型名称。
        is_local (bool): 是否使用本地模型 (True) 还是远程 API (False)。
        base_url (Optional[str]): 模型服务的基础 URL。
        api_key (Optional[str]): 远程 API 所需的密钥。
        use_cache (bool): 是否使用缓存。

    Returns:
        Dict: 包含生成的 schema 信息的字典。
    """
    # --- 1. 缓存检查 ---
    # 生成缓存键：使用文本内容和模型名称（因为不同模型可能产生不同结果）
    # 也可以考虑加入 is_local 等参数，如果认为它们会影响结果
    cache_key_text = f"{text_content}_{model_name}_{'local' if is_local else 'remote'}"
    text_hash = _get_text_hash(cache_key_text)  # 使用已定义的函数生成哈希

    if use_cache:
        cached_schema = _load_schema_from_cache(text_hash)  # 使用已定义的函数加载缓存
        if cached_schema:
            logger.info(f"[Schema Gen] 命中缓存: {text_hash}")
            return cached_schema
        else:
            logger.debug(f"[Schema Gen] 未找到缓存: {text_hash}")

    # --- 2. 核心逻辑：根据 is_local 创建 LLM 实例 ---
    llm = None
    try:
        if is_local:

            model_name = DEFAULT_MODEL
            ollama_base_url = base_url or "http://localhost:11434"
            logger.info(f"[Schema Gen] 本地模式使用默认本地模型 Ollama LLM: {model_name} @ {ollama_base_url}")
            llm = OllamaLLM(
                model=model_name,
                base_url=ollama_base_url,
                temperature=0.0
            )
        else:
            if not base_url:
                raise ValueError("使用远程模型时，必须提供 base_url。")
            remote_base_url = base_url.rstrip('/')
            logger.info(f"[Schema Gen] 初始化远程 API LLM: {model_name} @ {remote_base_url}")
            llm = ChatOpenAI(
                model=model_name,
                openai_api_key=api_key,
                openai_api_base=remote_base_url,
                temperature=0.0
            )

        if llm is None:
            raise RuntimeError("未能成功初始化 LLM 实例。")

        # --- 3. 使用 LLM 生成 Schema (使用 Pydantic 和 JsonOutputParser) ---
        # 创建 JsonOutputParser 实例，基于 Pydantic 模型
        parser = JsonOutputParser(pydantic_object=SchemaModel)

        # 创建 PromptTemplate，在提示词中加入格式化指令
        prompt_template = PromptTemplate(
            template="""
            生成知识图谱Schema（基于基础schema扩展）：
            基础节点：{minimal_elements}
            基础关系：{minimal_relationships}

            文本内容:
            {text_content}

            要求：
            - 所有名称使用中文二字词
            - 节点与关系要是简单词汇
            - 保留所有基础元素
            - 节点5-8个，关系5-8个
            - 仅输出JSON格式

            {format_instructions}
            """,
            input_variables=["text_content", "minimal_elements", "minimal_relationships"],
            partial_variables={"format_instructions": parser.get_format_instructions()}
        )

        # 组合 Chain: Prompt -> LLM -> Parser
        chain = prompt_template | llm

        logger.debug("[Schema Gen] 正在调用 LLM 生成 Schema...")

        # 调用 chain 获取 LLM 的原始响应
        llm_response = chain.invoke({
            "text_content": text_content,
            "minimal_elements": MINIMAL_ELEMENTS,
            "minimal_relationships": MINIMAL_RELATIONSHIPS
        })

        logger.debug(f"[Schema Gen] LLM 原始响应: {llm_response[:200]}...")  # 打印前200个字符

        # --- 新增：如果使用本地模型，清理响应内容 ---
        if is_local:
            # 删除 </think> 标签及其前面的内容
            think_index = llm_response.find("</think>")
            if think_index != -1:
                # 找到 <think> 标签，删除它及其前面的所有内容
                cleaned_response = llm_response[think_index + len("</think>"):]
                logger.debug(f"[Schema Gen] 清理后的响应: {cleaned_response[:200]}...")
                llm_response = cleaned_response
            else:
                logger.debug("[Schema Gen] 未找到 </think> 标签，使用原始响应")

        # 将清理后的响应传递给解析器
        schema_dict = parser.invoke(llm_response)

        logger.debug(f"[Schema Gen] LLM 响应已解析为结构化数据")

        # --- 4. 验证和后处理 ---
        # 手动将字典转换回 Pydantic 模型进行验证
        try:
            validated_result = SchemaModel(**schema_dict)
            # 如果验证通过，使用 Pydantic 模型的数据
            schema_dict = {
                "name": validated_result.name,
                "description": validated_result.description,
                "elements": validated_result.elements,
                "relationships": validated_result.relationships
            }
            logger.info(f"[Schema Gen] Schema 验证通过")
        except Exception as validation_error:
            logger.warning(f"[Schema Gen] Schema 验证失败: {validation_error}")
            # 如果验证失败，仍然使用解析后的字典结果
            # 但确保必要的键存在
            required_keys = ["name", "description", "elements", "relationships"]
            for key in required_keys:
                if key not in schema_dict:
                    schema_dict[key] = "未知" if key in ["name", "description"] else []

        # --- 5. 输出生成的 Schema 内容到日志 ---
        schema_name = schema_dict.get('name', 'N/A')
        schema_desc = schema_dict.get('description', 'N/A')
        elements = schema_dict.get('elements', [])
        relationships = schema_dict.get('relationships', [])

        logger.info(f"[Schema Gen] Schema 生成成功: {schema_name}")
        logger.info(f"[Schema Gen] 描述: {schema_desc}")
        logger.info(f"[Schema Gen] 节点类型 ({len(elements)}): {', '.join(elements)}")
        logger.info(f"[Schema Gen] 关系类型 ({len(relationships)}): {', '.join(relationships)}")

        # --- 6. 保存到缓存 ---
        if use_cache:
            _save_schema_to_cache(text_hash, schema_dict)  # 使用已定义的函数保存缓存
            logger.debug(f"[Schema Gen] Schema 已缓存: {text_hash}")

        return schema_dict

    except Exception as e:
        logger.error(f"[Schema Gen] 生成 Schema 时出错: {e}", exc_info=True)  # 添加 exc_info 获取完整堆栈
        # 出错时返回默认 schema
        return MINIMAL_SCHEMA

def split_schema(schema: Dict, threshold: int = 5) -> List[Dict]:
    """
    将一个复杂的 Schema 拆分为多个子 Schema。
    策略：保持所有节点类型不变，将关系类型按组拆分。

    Args:
        schema (Dict): 原始 Schema 字典，包含 'elements' 和 'relationships'
        threshold (int): 每个子 Schema 最多包含的关系数，默认为 5

    Returns:
        List[Dict]: 拆分后的子 Schema 列表
    """
    elements = schema.get("elements", [])
    relationships = schema.get("relationships", [])
    schema_name = schema.get("name", "未知Schema")
    schema_description = schema.get("description", "")

    if not relationships:
        logger.warning(f"Schema '{schema_name}' 没有定义关系类型，无需拆分。")
        return [schema]

    rels_per_sub = threshold
    num_sub_schemas = math.ceil(len(relationships) / rels_per_sub)

    if num_sub_schemas <= 1:
        logger.debug(
            f"Schema '{schema_name}' 关系数 ({len(relationships)}) 未超过阈值 ({rels_per_sub})，无需拆分。"
        )
        return [schema]

    logger.info(
        f"Schema '{schema_name}' 关系数 ({len(relationships)}) 超过阈值 ({rels_per_sub})，将拆分为 {num_sub_schemas} 个子 Schema。"
    )

    sub_schemas = []
    for i in range(num_sub_schemas):
        start_rel_idx = i * rels_per_sub
        end_rel_idx = min((i + 1) * rels_per_sub, len(relationships))
        sub_relationships = relationships[start_rel_idx:end_rel_idx]

        sub_schema = {
            "name": f"{schema_name}_关系组_{i + 1}",
            "description": f"{schema_description} - 关系组 {i + 1}/{num_sub_schemas}: {', '.join(sub_relationships)}",
            "elements": elements,
            "relationships": sub_relationships
        }
        sub_schemas.append(sub_schema)

        logger.debug(
            f"子 Schema {i + 1}: {len(elements)} 个节点类型, {len(sub_relationships)} 个关系类型"
        )

    return sub_schemas