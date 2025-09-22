# demo_structured_output_v2.py
import json
from typing import List
from pydantic import BaseModel, Field
from langchain_ollama import OllamaLLM
from langchain_core.output_parsers import JsonOutputParser
from langchain_core.prompts import PromptTemplate

# 1. 定义 Pydantic 模型来表示期望的结构化输出
class Character(BaseModel):
    name: str = Field(description="角色的名字")
    age: int = Field(description="角色的年龄")
    description: str = Field(description="角色的简短描述")

class CharacterList(BaseModel):
    characters: List[Character] = Field(description="角色列表")


# 2. 初始化 OllamaLLM (保持您的原始设置)
llm = OllamaLLM(
    model="qwen3:30b-a3b-instruct-2507-q4_K_M",
    temperature=0.7,
    num_predict=256,
    # base_url="http://localhost:11434",
)

# 3. 创建 JsonOutputParser 实例，基于 Pydantic 模型
parser = JsonOutputParser(pydantic_object=CharacterList)

# 4. 创建 PromptTemplate，在提示词中加入格式化指令
#    这会告诉模型按照特定的 JSON 格式输出
prompt_template = PromptTemplate(
    template="创造三个来自奇幻小说的角色，包括他们的名字、年龄和简短描述。\n{format_instructions}\n请生成角色信息。",
    input_variables=[], # 没有动态输入变量
    partial_variables={"format_instructions": parser.get_format_instructions()} # 插入格式指令
)

# 5. 组合 Chain: Prompt -> LLM -> Parser
chain = prompt_template | llm | parser

# 6. 主程序入口
if __name__ == "__main__":
    print("正在请求结构化输出 (使用 Langchain JsonOutputParser)...")

    try:
        # 调用 chain 获取解析后的 Python 对象 (字典/列表)
        result = chain.invoke({}) # 传递空字典作为输入，因为我们没有动态变量

        # 打印结果
        print("\n--- 结构化输出结果 (已解析为 Python 字典) ---")
        print(json.dumps(result, indent=2, ensure_ascii=False))

        # 手动将字典转换回 Pydantic 模型进行验证和访问 (可选，但推荐)
        # 这一步可以确保输出确实符合你的模型定义
        try:
            validated_result = CharacterList(**result)
            print("\n--- 验证通过，使用 Pydantic 模型访问 ---")
            for character in validated_result.characters:
                print(f"名字: {character.name}, 年龄: {character.age}, 描述: {character.description}")
        except Exception as validation_error:
             print(f"\n--- 警告：模型输出与 Pydantic 模型不完全匹配 ---")
             print(f"验证错误: {validation_error}")
             # 即使验证失败，你仍然可以使用原始的字典结果 `result`


    except Exception as e:
        print(f"程序执行出错: {e}")
