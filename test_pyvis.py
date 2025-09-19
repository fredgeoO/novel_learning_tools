import gradio as gr
from pyvis.network import Network
import networkx as nx
import tempfile
import os


def create_and_save_knowledge_graph_file():
    # ... (与之前提供的函数相同，生成HTML文件并返回路径)
    try:
        nodes = [
            ("Python", {"label": "编程语言", "title": "Python"}),
            ("Pyvis", {"label": "可视化库", "title": "Pyvis"}),
            ("Gradio", {"label": "UI框架", "title": "Gradio"}),
            ("Anaconda", {"label": "环境管理", "title": "Anaconda"}),
            ("数据科学", {"label": "领域", "title": "数据科学"}),
            ("可视化", {"label": "概念", "title": "可视化"}),
            ("UI", {"label": "概念", "title": "UI"}),
        ]
        edges = [
            ("Python", "Pyvis", {"label": "支持", "title": "Python支持Pyvis"}),
            ("Python", "Gradio", {"label": "支持", "title": "Python支持Gradio"}),
            ("Python", "Anaconda", {"label": "集成", "title": "Anaconda集成Python"}),
            ("数据科学", "Python", {"label": "使用", "title": "数据科学使用Python"}),
            ("Pyvis", "可视化", {"label": "用于", "title": "Pyvis用于可视化"}),
            ("Gradio", "UI", {"label": "用于", "title": "Gradio用于构建UI"}),
        ]

        nx_graph = nx.DiGraph()
        nx_graph.add_nodes_from(nodes)
        nx_graph.add_edges_from([(u, v, data) for u, v, data in edges])

        net = Network(height="750px", width="100%", bgcolor="#222222", font_color="white",
                      directed=True, notebook=True, cdn_resources='remote')
        net.from_nx(nx_graph)
        net.toggle_physics(True)

        temp_dir = tempfile.mkdtemp()
        temp_file_path = os.path.join(temp_dir, "knowledge_graph.html")

        # 手动以 UTF-8 编码写入文件
        html_content = net.generate_html()
        with open(temp_file_path, "w", encoding="utf-8") as f:
            f.write(html_content)

        # 返回文件路径，gr.File() 会处理如何提供这个文件
        return temp_file_path

    except Exception as e:
        print(f"生成知识图谱时出错: {e}")
        return None


# 创建 Gradio 界面
interface = gr.Interface(
    fn=create_and_save_knowledge_graph_file,
    inputs=None,
    outputs=gr.File(label="网络可视化", file_count="single"),
    title="📡 PyVis + Gradio 网络可视化演示",
    description="展示如何在 Gradio 中显示 PyVis 生成的交互式网络图"
)

if __name__ == '__main__':
    interface.launch()
