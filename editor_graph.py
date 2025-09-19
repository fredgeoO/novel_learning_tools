import streamlit as st
from pyvis.network import Network
import streamlit.components.v1 as components


def create_editable_graph():
    net = Network(height="600px", width="100%", directed=True)

    # 添加初始节点
    net.add_node(1, label="角色A", color="#FF6B6B")
    net.add_node(2, label="场景1", color="#4ECDC4")
    net.add_edge(1, 2, label="出现在")

    net.set_options("""
    {
      "interaction": {
        "dragNodes": true,
        "dragView": true,
        "zoomView": true
      },
      "physics": {
        "enabled": true,
        "stabilization": {"iterations": 100}
      }
    }
    """)

    return net


# Streamlit 应用
st.title("🔍 可编辑叙事图谱")
st.markdown("右键添加节点 | 双击删除节点 | 拖拽节点创建关系")

net = create_editable_graph()
html_content = net.generate_html()

# 增强的JavaScript
enhanced_js = """
<script>
window.addEventListener('load', function() {
    if (typeof network !== 'undefined') {
        // 右键添加节点
        network.on("oncontext", function (params) {
            params.event.preventDefault();
            const nodeId = 'node_' + Date.now();
            const { x, y } = params.pointer.canvas;
            network.body.data.nodes.add({
                id: nodeId,
                label: "新节点",
                x: x,
                y: y,
                color: "#CCCCCC"
            });
        });

        // 双击删除节点
        network.on("doubleClick", function (params) {
            if (params.nodes.length > 0) {
                const nodeId = params.nodes[0];
                network.body.data.nodes.remove(nodeId);
                // 同时删除相关边
                const edgesToRemove = network.body.data.edges.get().filter(edge => 
                    edge.from === nodeId || edge.to === nodeId
                ).map(edge => edge.id);
                network.body.data.edges.remove(edgesToRemove);
            }
        });

        // 节点拖拽创建关系
        let dragStartNode = null;
        network.on("dragStart", function (params) {
            if (params.nodes.length > 0) {
                dragStartNode = params.nodes[0];
            }
        });

        network.on("dragEnd", function (params) {
            if (dragStartNode && params.nodes.length > 0) {
                const endNode = params.nodes[0];
                if (dragStartNode !== endNode) {
                    // 检查边是否已存在
                    const existingEdges = network.body.data.edges.get({
                        filter: edge => 
                            (edge.from === dragStartNode && edge.to === endNode) ||
                            (edge.from === endNode && edge.to === dragStartNode)
                    });

                    if (existingEdges.length === 0) {
                        network.body.data.edges.add({
                            from: dragStartNode,
                            to: endNode,
                            label: "关系",
                            arrows: "to"
                        });
                    }
                }
            }
            dragStartNode = null;
        });
    }
});
</script>
"""

# 合并并显示
final_html = html_content.replace("</body>", enhanced_js + "</body>")
components.html(final_html, height=700, scrolling=True)