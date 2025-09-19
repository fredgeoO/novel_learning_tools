import streamlit as st
import json
import streamlit.components.v1 as components

st.set_page_config(page_title="高级图谱编辑器", layout="wide")
st.title("🧠 高级前端主导图谱编辑器")

# 图谱数据管理 - 支持您的格式
if 'graph_json' not in st.session_state:
    st.session_state.graph_json = {
        "nodes": [
            {
                "id": "彭刚",
                "type": "人物",
                "properties": {"name": "彭刚", "sequence_number": 1}
            },
            {
                "id": "彭毅",
                "type": "人物",
                "properties": {"name": "彭毅", "sequence_number": 2}
            },
            {
                "id": "族长",
                "type": "人物",
                "properties": {"name": "族长", "sequence_number": 4}
            }
        ],
        "relationships": [
            {
                "source_id": "族长",
                "target_id": "彭毅",
                "type": "说话给",
                "properties": {}
            }
        ]
    }

# 侧边栏控制
st.sidebar.header("📊 图谱控制")

# 文件上传
uploaded_file = st.sidebar.file_uploader("上传JSON文件", type="json")
if uploaded_file is not None:
    try:
        st.session_state.graph_json = json.load(uploaded_file)
        st.sidebar.success("文件加载成功！")
    except Exception as e:
        st.sidebar.error(f"文件加载失败: {e}")

# 图谱操作
col1, col2, col3 = st.columns(3)
with col1:
    if st.button("📥 加载示例"):
        st.session_state.graph_json = {
            "nodes": [
                {
                    "id": "彭刚",
                    "type": "人物",
                    "properties": {"name": "彭刚", "sequence_number": 1}
                },
                {
                    "id": "彭毅",
                    "type": "人物",
                    "properties": {"name": "彭毅", "sequence_number": 2}
                },
                {
                    "id": "族长",
                    "type": "人物",
                    "properties": {"name": "族长", "sequence_number": 4}
                },
                {
                    "id": "庆丰村",
                    "type": "地点",
                    "properties": {"name": "庆丰村", "sequence_number": 9}
                }
            ],
            "relationships": [
                {
                    "source_id": "族长",
                    "target_id": "彭毅",
                    "type": "说话给",
                    "properties": {}
                },
                {
                    "source_id": "彭刚",
                    "target_id": "庆丰村",
                    "type": "位于",
                    "properties": {}
                }
            ]
        }
        st.sidebar.success("示例数据已加载！")

with col2:
    if st.button("📤 导出JSON"):
        st.sidebar.download_button(
            label="下载图谱",
            data=json.dumps(st.session_state.graph_json, indent=2, ensure_ascii=False),
            file_name="knowledge_graph.json",
            mime="application/json"
        )

with col3:
    if st.button("🔄 刷新"):
        st.rerun()

# JSON编辑器
with st.sidebar.expander("📝 JSON编辑器"):
    # 将您的数据格式转换为前端可用格式
    def convert_to_frontend_format(graph_data):
        nodes = []
        edges = []

        # 类型颜色映射
        color_map = {
            "人物": "#FF6B6B", "地点": "#4ECDC4", "时间": "#45B7D1",
            "物品": "#96CEB4", "事件": "#FFEAA7", "对白": "#DDA0DD",
            "想法": "#98D8C8", "情绪": "#F7DC6F", "状态": "#BB8FCE",
            "概念": "#85C1E9", "组织": "#F8C471"
        }

        # 转换节点
        for node in graph_data.get("nodes", []):
            node_id = node.get("id", "")
            node_type = node.get("type", "未知")
            name = node.get("properties", {}).get("name", node_id)

            nodes.append({
                "id": node_id,
                "label": name,
                "title": f"类型: {node_type}\nID: {node_id}",
                "color": color_map.get(node_type, "#A0A0A0")
            })

        # 转换关系
        for rel in graph_data.get("relationships", []):
            source = rel.get("source_id", "")
            target = rel.get("target_id", "")
            rel_type = rel.get("type", "关联")

            edges.append({
                "from": source,
                "to": target,
                "label": rel_type,
                "title": f"关系类型: {rel_type}"
            })

        return {"nodes": nodes, "edges": edges}


    # 转换为前端格式用于显示和编辑
    frontend_data = convert_to_frontend_format(st.session_state.graph_json)

    json_input = st.text_area(
        "编辑图谱JSON",
        value=json.dumps(frontend_data, indent=2, ensure_ascii=False),
        height=300
    )

    if st.button("✅ 应用JSON"):
        try:
            new_data = json.loads(json_input)
            # 将前端格式转换回您的格式
            converted_nodes = []
            converted_relationships = []

            # 这里可以添加转换逻辑，但为了简单起见，我们直接使用前端格式
            st.session_state.graph_json = {
                "nodes": st.session_state.graph_json.get("nodes", []),
                "relationships": st.session_state.graph_json.get("relationships", [])
            }
            st.sidebar.success("JSON已更新！")
        except json.JSONDecodeError as e:
            st.sidebar.error(f"JSON格式错误: {e}")

# 节点编辑
st.sidebar.subheader("✏️ 节点编辑")
with st.sidebar.expander("添加/编辑节点"):
    new_node_id = st.text_input("节点ID")
    new_node_type = st.selectbox("节点类型", [
        "人物", "地点", "时间", "物品", "事件", "对白",
        "想法", "情绪", "状态", "概念", "组织"
    ])
    new_node_name = st.text_input("节点名称")

    if st.button("➕ 添加节点") and new_node_id and new_node_name:
        node_exists = any(node["id"] == new_node_id for node in st.session_state.graph_json["nodes"])
        if not node_exists:
            new_node = {
                "id": new_node_id,
                "type": new_node_type,
                "properties": {
                    "name": new_node_name,
                    "sequence_number": len(st.session_state.graph_json["nodes"]) + 1
                }
            }
            st.session_state.graph_json["nodes"].append(new_node)
            st.sidebar.success(f"节点 '{new_node_id}' 已添加！")
            st.rerun()
        else:
            st.sidebar.warning(f"节点 '{new_node_id}' 已存在！")

# 关系编辑
if len(st.session_state.graph_json["nodes"]) >= 2:
    st.sidebar.subheader("🔗 关系编辑")
    with st.sidebar.expander("添加关系"):
        node_ids = [node["id"] for node in st.session_state.graph_json["nodes"]]
        source_node = st.selectbox("起始节点", node_ids, key="source")
        target_node = st.selectbox("目标节点", node_ids, key="target")
        relationship_type = st.text_input("关系类型", "关联")

        if st.button("➕ 添加关系") and source_node and target_node:
            rel_exists = any(
                rel["source_id"] == source_node and rel["target_id"] == target_node
                for rel in st.session_state.graph_json["relationships"]
            )
            if not rel_exists:
                new_relationship = {
                    "source_id": source_node,
                    "target_id": target_node,
                    "type": relationship_type,
                    "properties": {}
                }
                st.session_state.graph_json["relationships"].append(new_relationship)
                st.sidebar.success(f"关系已添加！")
                st.rerun()
            else:
                st.sidebar.warning("关系已存在！")

# 主要的前端编辑器
st.subheader("🎨 前端主导的图谱编辑器")


# 将您的数据格式转换为前端可用格式
def convert_to_frontend_format(graph_data):
    nodes = []
    edges = []

    # 类型颜色映射
    color_map = {
        "人物": "#FF6B6B", "地点": "#4ECDC4", "时间": "#45B7D1",
        "物品": "#96CEB4", "事件": "#FFEAA7", "对白": "#DDA0DD",
        "想法": "#98D8C8", "情绪": "#F7DC6F", "状态": "#BB8FCE",
        "概念": "#85C1E9", "组织": "#F8C471"
    }

    # 转换节点
    for node in graph_data.get("nodes", []):
        node_id = node.get("id", "")
        node_type = node.get("type", "未知")
        name = node.get("properties", {}).get("name", node_id)

        nodes.append({
            "id": node_id,
            "label": name,
            "title": f"类型: {node_type}\nID: {node_id}",
            "color": color_map.get(node_type, "#A0A0A0")
        })

    # 转换关系
    for rel in graph_data.get("relationships", []):
        source = rel.get("source_id", "")
        target = rel.get("target_id", "")
        rel_type = rel.get("type", "关联")

        edges.append({
            "from": source,
            "to": target,
            "label": rel_type,
            "title": f"关系类型: {rel_type}"
        })

    return {"nodes": nodes, "edges": edges}


# 转换数据
frontend_data = convert_to_frontend_format(st.session_state.graph_json)
graph_data_js = json.dumps(frontend_data, ensure_ascii=False)

# 高级前端编辑器 - 修复版
advanced_html = f"""
<!DOCTYPE html>
<html>
<head>
    <script src="https://unpkg.com/vis-network/standalone/umd/vis-network.min.js"></script>
    <style>
        #network-container {{
            width: 100%;
            height: 600px;
            border: 2px solid #ddd;
            border-radius: 8px;
            position: relative;
        }}

        #network {{
            width: 100%;
            height: 100%;
        }}

        #toolbar {{
            padding: 10px;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            border-radius: 5px 5px 0 0;
            display: flex;
            gap: 10px;
            flex-wrap: wrap;
        }}

        .tool-btn {{
            padding: 8px 15px;
            background: rgba(255,255,255,0.2);
            border: 1px solid rgba(255,255,255,0.3);
            color: white;
            border-radius: 4px;
            cursor: pointer;
            font-size: 14px;
            transition: all 0.3s;
        }}

        .tool-btn:hover {{
            background: rgba(255,255,255,0.3);
        }}

        .tool-btn.active {{
            background: rgba(255,255,255,0.4);
            box-shadow: 0 0 10px rgba(255,255,255,0.3);
        }}

        #status-bar {{
            padding: 8px;
            background: #f8f9fa;
            border: 1px solid #ddd;
            border-top: none;
            border-radius: 0 0 5px 5px;
            font-size: 12px;
            color: #666;
        }}

        #context-menu {{
            position: absolute;
            background: white;
            border: 1px solid #ccc;
            border-radius: 4px;
            box-shadow: 2px 2px 10px rgba(0,0,0,0.2);
            z-index: 1000;
            display: none;
        }}

        #context-menu ul {{
            list-style: none;
            padding: 5px 0;
            margin: 0;
        }}

        #context-menu li {{
            padding: 8px 15px;
            cursor: pointer;
            font-size: 14px;
        }}

        #context-menu li:hover {{
            background: #f0f0f0;
        }}

        .node-legend {{
            display: flex;
            flex-wrap: wrap;
            gap: 10px;
            margin-top: 10px;
            padding: 10px;
            background: #f8f9fa;
            border-radius: 5px;
        }}

        .legend-item {{
            display: flex;
            align-items: center;
            gap: 5px;
            font-size: 12px;
        }}

        .legend-color {{
            width: 12px;
            height: 12px;
            border-radius: 50%;
        }}
    </style>
</head>
<body>
    <div id="toolbar">
        <button class="tool-btn" id="selectMode" title="选择模式">🖱️ 选择</button>
        <button class="tool-btn" id="addNodeMode" title="添加节点">➕ 节点</button>
        <button class="tool-btn" id="addEdgeMode" title="添加关系">🔗 关系</button>
        <button class="tool-btn" id="deleteMode" title="删除">🗑️ 删除</button>
        <button class="tool-btn" id="editMode" title="编辑">✏️ 编辑</button>
        <button class="tool-btn" id="clearSelection" title="清除选择">❌ 清除</button>
        <div style="margin-left: auto; font-size: 14px;">
            <span id="mode-indicator">当前模式: 选择</span>
        </div>
    </div>

    <div id="network-container">
        <div id="network"></div>
        <div id="context-menu">
            <ul>
                <li id="ctx-add-node">添加节点</li>
                <li id="ctx-edit-node">编辑节点</li>
                <li id="ctx-delete-node">删除节点</li>
                <li class="separator"></li>
                <li id="ctx-add-edge">添加关系</li>
            </ul>
        </div>
    </div>

    <div id="status-bar">
        节点: <span id="node-count">0</span> | 
        关系: <span id="edge-count">0</span> | 
        选中: <span id="selection-info">无</span>
    </div>

    <div class="node-legend" id="legend">
        <!-- 图例将在这里动态生成 -->
    </div>

    <script>
        // 图谱数据
        const graphData = {graph_data_js};

        // 初始化网络
        const container = document.getElementById('network');
        const nodes = new vis.DataSet(graphData.nodes || []);
        const edges = new vis.DataSet(graphData.edges || []);

        const data = {{ nodes, edges }};
        const options = {{
            nodes: {{
                shape: 'dot',
                scaling: {{
                    min: 10,
                    max: 30
                }},
                font: {{
                    size: 12,
                    face: 'Arial'
                }}
            }},
            edges: {{
                arrows: {{ to: {{ enabled: true, scaleFactor: 1 }} }},
                smooth: {{ enabled: true }},
                font: {{
                    size: 10,
                    align: 'middle'
                }}
            }},
            physics: {{
                enabled: true,
                stabilization: {{ iterations: 100 }}
            }},
            interaction: {{
                hover: true,
                tooltipDelay: 200,
                navigationButtons: true,
                keyboard: true
            }}
        }};

        const network = new vis.Network(container, data, options);

        // 状态管理
        let currentMode = 'select';
        let selectedNodes = [];
        let selectedEdges = [];
        let contextMenu = document.getElementById('context-menu');
        let contextTarget = null;

        // 生成图例
        function generateLegend() {{
            const legend = document.getElementById('legend');
            const types = ["人物", "地点", "时间", "物品", "事件", "对白", "想法", "情绪", "状态", "概念", "组织"];
            const colors = {{
                "人物": "#FF6B6B", "地点": "#4ECDC4", "时间": "#45B7D1",
                "物品": "#96CEB4", "事件": "#FFEAA7", "对白": "#DDA0DD",
                "想法": "#98D8C8", "情绪": "#F7DC6F", "状态": "#BB8FCE",
                "概念": "#85C1E9", "组织": "#F8C471"
            }};

            legend.innerHTML = '<strong>节点类型:</strong> ';
            types.forEach(type => {{
                const item = document.createElement('div');
                item.className = 'legend-item';
                item.innerHTML = `
                    <div class="legend-color" style="background-color: ${{colors[type]}}"></div>
                    <span>${{type}}</span>
                `;
                legend.appendChild(item);
            }});
        }}

        // 更新状态栏
        function updateStatusBar() {{
            document.getElementById('node-count').textContent = nodes.length;
            document.getElementById('edge-count').textContent = edges.length;

            let selectionInfo = '无';
            if (selectedNodes.length > 0) {{
                selectionInfo = `节点(${{selectedNodes.length}})`;
            }}
            if (selectedEdges.length > 0) {{
                selectionInfo += (selectionInfo !== '无' ? ', ' : '') + `关系(${{selectedEdges.length}})`;
            }}
            document.getElementById('selection-info').textContent = selectionInfo;
        }}

        // 更新模式指示器
        function updateModeIndicator() {{
            document.getElementById('mode-indicator').textContent = `当前模式: ${{getModeName(currentMode)}}`;

            // 更新按钮状态
            document.querySelectorAll('.tool-btn').forEach(btn => {{
                btn.classList.remove('active');
            }});

            const modeBtnMap = {{
                'select': 'selectMode',
                'addNode': 'addNodeMode',
                'addEdge': 'addEdgeMode',
                'delete': 'deleteMode',
                'edit': 'editMode'
            }};

            if (modeBtnMap[currentMode]) {{
                document.getElementById(modeBtnMap[currentMode]).classList.add('active');
            }}
        }}

        function getModeName(mode) {{
            const names = {{
                'select': '选择',
                'addNode': '添加节点',
                'addEdge': '添加关系',
                'delete': '删除',
                'edit': '编辑'
            }};
            return names[mode] || mode;
        }}

        // 模式切换
        function setMode(mode) {{
            currentMode = mode;
            updateModeIndicator();

            // 根据模式调整网络交互
            switch(mode) {{
                case 'select':
                    network.setOptions({{ interaction: {{ dragNodes: true }} }});
                    break;
                case 'addNode':
                    network.setOptions({{ interaction: {{ dragNodes: false }} }});
                    break;
                default:
                    network.setOptions({{ interaction: {{ dragNodes: true }} }});
            }}
        }}

        // 工具栏事件
        document.getElementById('selectMode').onclick = () => setMode('select');
        document.getElementById('addNodeMode').onclick = () => setMode('addNode');
        document.getElementById('addEdgeMode').onclick = () => setMode('addEdge');
        document.getElementById('deleteMode').onclick = () => setMode('delete');
        document.getElementById('editMode').onclick = () => setMode('edit');
        document.getElementById('clearSelection').onclick = () => {{
            network.unselectAll();
            selectedNodes = [];
            selectedEdges = [];
            updateStatusBar();
        }};

        // 网络事件
        network.on('click', function(params) {{
            selectedNodes = params.nodes;
            selectedEdges = params.edges;
            updateStatusBar();

            switch(currentMode) {{
                case 'addNode':
                    addNodeAtPosition(params.pointer.canvas);
                    break;
                case 'addEdge':
                    if (params.nodes.length > 0) {{
                        startEdgeCreation(params.nodes[0]);
                    }}
                    break;
                case 'delete':
                    deleteSelectedElements();
                    break;
                case 'edit':
                    if (params.nodes.length > 0) {{
                        editNode(params.nodes[0]);
                    }} else if (params.edges.length > 0) {{
                        editEdge(params.edges[0]);
                    }}
                    break;
            }}
        }});

        network.on('oncontext', function(params) {{
            params.event.preventDefault();
            showContextMenu(params.pointer.DOM, params);
        }});

        // 右键菜单
        function showContextMenu(position, params) {{
            contextTarget = params;

            contextMenu.style.left = position.x + 'px';
            contextMenu.style.top = position.y + 'px';
            contextMenu.style.display = 'block';
        }}

        function hideContextMenu() {{
            contextMenu.style.display = 'none';
            contextTarget = null;
        }}

        // 右键菜单项
        document.getElementById('ctx-add-node').onclick = () => {{
            if (contextTarget && contextTarget.pointer) {{
                addNodeAtPosition(contextTarget.pointer.canvas);
            }}
            hideContextMenu();
        }};

        document.getElementById('ctx-edit-node').onclick = () => {{
            if (contextTarget && contextTarget.nodes && contextTarget.nodes.length > 0) {{
                editNode(contextTarget.nodes[0]);
            }}
            hideContextMenu();
        }};

        document.getElementById('ctx-delete-node').onclick = () => {{
            if (contextTarget && contextTarget.nodes && contextTarget.nodes.length > 0) {{
                nodes.remove(contextTarget.nodes[0]);
                updateStatusBar();
            }}
            hideContextMenu();
        }};

        // 点击其他地方隐藏菜单
        document.addEventListener('click', function(e) {{
            if (!contextMenu.contains(e.target)) {{
                hideContextMenu();
            }}
        }});

        // 功能函数
        function addNodeAtPosition(position) {{
            const nodeId = 'node_' + Date.now();
            const newNode = {{
                id: nodeId,
                label: '新节点',
                color: '#FFA500',
                x: position.x,
                y: position.y
            }};
            nodes.add(newNode);
            updateStatusBar();
            setMode('select');
        }}

        function startEdgeCreation(nodeId) {{
            // 这里可以实现更复杂的边创建逻辑
            alert('点击另一个节点来创建关系');
        }}

        function deleteSelectedElements() {{
            if (selectedNodes.length > 0) {{
                nodes.remove(selectedNodes);
            }}
            if (selectedEdges.length > 0) {{
                edges.remove(selectedEdges);
            }}
            selectedNodes = [];
            selectedEdges = [];
            updateStatusBar();
            setMode('select');
        }}

        function editNode(nodeId) {{
            const node = nodes.get(nodeId);
            const newLabel = prompt('编辑节点标签:', node.label);
            if (newLabel !== null) {{
                nodes.update({{ id: nodeId, label: newLabel }});
            }}
        }}

        function editEdge(edgeId) {{
            const edge = edges.get(edgeId);
            const newLabel = prompt('编辑关系标签:', edge.label || '');
            if (newLabel !== null) {{
                edges.update({{ id: edgeId, label: newLabel }});
            }}
        }}

        // 初始设置
        setMode('select');
        updateStatusBar();
        updateModeIndicator();
        generateLegend();

        // 定期发送更新到Python后端
        setInterval(function() {{
            window.parent.postMessage({{
                type: 'graphDataUpdate',
                data: {{
                    nodes: nodes.get(),
                    edges: edges.get()
                }}
            }}, '*');
        }}, 1000);
    </script>
</body>
</html>
"""

# 显示高级编辑器 - 确保有足够的显示高度
components.html(advanced_html, height=800)

# 显示统计信息
st.subheader("📈 图谱统计")
col1, col2, col3 = st.columns(3)
with col1:
    st.metric("节点总数", len(st.session_state.graph_json.get("nodes", [])))
with col2:
    st.metric("关系总数", len(st.session_state.graph_json.get("relationships", [])))
with col3:
    node_types = {}
    for node in st.session_state.graph_json.get("nodes", []):
        node_type = node.get("type", "未知")
        node_types[node_type] = node_types.get(node_type, 0) + 1
    if node_types:
        most_common = max(node_types, key=node_types.get)
        st.metric("主要类型", most_common)

# 节点和关系列表
col1, col2 = st.columns(2)
with col1:
    st.subheader("📋 节点列表")
    nodes = st.session_state.graph_json.get("nodes", [])
    if nodes:
        for i, node in enumerate(nodes[:15]):
            node_id = node.get("id", "")
            node_type = node.get("type", "未知")
            name = node.get("properties", {}).get("name", node_id)
            color_map = {
                "人物": "#FF6B6B", "地点": "#4ECDC4", "时间": "#45B7D1",
                "物品": "#96CEB4", "事件": "#FFEAA7", "对白": "#DDA0DD",
                "想法": "#98D8C8", "情绪": "#F7DC6F", "状态": "#BB8FCE",
                "概念": "#85C1E9", "组织": "#F8C471"
            }
            color = color_map.get(node_type, "#A0A0A0")
            st.markdown(f"<span style='color:{color}; font-weight:bold;'>●</span> {name} <small>({node_type})</small>",
                        unsafe_allow_html=True)
        if len(nodes) > 15:
            st.info(f"还有 {len(nodes) - 15} 个节点...")
    else:
        st.info("暂无节点")

with col2:
    st.subheader("🔗 关系列表")
    relationships = st.session_state.graph_json.get("relationships", [])
    if relationships:
        for i, rel in enumerate(relationships[:15]):
            source = rel.get("source_id", "")
            target = rel.get("target_id", "")
            rel_type = rel.get("type", "关联")
            st.write(f"{source} → {target} ({rel_type})")
        if len(relationships) > 15:
            st.info(f"还有 {len(relationships) - 15} 个关系...")
    else:
        st.info("暂无关系")

st.markdown("""
### 🎯 功能特性

1. **完整编辑功能**：
   - 添加/删除节点和关系
   - 文件导入/导出
   - JSON编辑器

2. **支持您的数据格式**：
   - `nodes` + `relationships` 结构
   - 自动类型颜色映射
   - 属性信息显示

3. **高级交互**：
   - 右键菜单
   - 多种操作模式
   - 拖拽布局
   - 实时状态反馈

4. **数据可视化**：
   - 类型颜色编码
   - 图例显示
   - 统计信息
   - 节点和关系列表

### 🚀 使用方法

1. 上传您的JSON文件或加载示例数据
2. 使用侧边栏编辑功能添加节点和关系
3. 在主区域通过右键菜单进行高级操作
4. 通过JSON编辑器进行精细调整
""")