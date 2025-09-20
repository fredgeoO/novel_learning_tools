const GraphEditor = (function() {
    // 私有变量
    let network, nodes, edges;
    let container;

    // 状态管理
    const state = {
        selectedNode: null,
        contextMenuNode: null,
        contextMenuEdge: null,
        addingNode: false,
        connectingToExisting: false,
        connectionSourceNode: null,
        hoveredNode: null,
        hoveredEdge: null,
        isConnectingNewNode: false,
        menuShowTimer: null,
        isMenuVisible: false,
        menuScheduledToShow: false
    };

    // 初始化
    function init() {
        container = document.getElementById('mynetwork');
        initTestGraph();
        bindGlobalEvents();
    }




    // 保存图谱功能
    function saveGraph() {
        try {
            // 获取当前图谱数据
            const graphData = {
                nodes: nodes.get(),
                edges: edges.get()
            };

            console.log('保存图谱数据:', graphData);
            alert('保存功能待实现');
        } catch (error) {
            console.error('保存图谱失败:', error);
            alert('保存失败：' + error.message);
        }
    }

    // 清空图谱功能
    function clearGraph() {
        if (nodes && edges) {
            nodes.clear();
            edges.clear();
            console.log('图谱已清空');
        }
    }

    // 导出图谱功能
    function exportGraph() {
        try {
            const graphData = {
                nodes: nodes.get(),
                edges: edges.get()
            };

            const dataStr = JSON.stringify(graphData, null, 2);
            const dataBlob = new Blob([dataStr], {type: 'application/json'});

            const link = document.createElement('a');
            link.href = URL.createObjectURL(dataBlob);
            link.download = 'graph-data.json';
            link.click();

            console.log('图谱已导出');
        } catch (error) {
            console.error('导出图谱失败:', error);
            alert('导出失败：' + error.message);
        }
    }

    // 初始化测试图
    function initTestGraph() {
        const testData = {
            nodes: [
                {id: 1, label: '节点1'},
                {id: 2, label: '节点2'},
                {id: 3, label: '节点3'}
            ],
            edges: [
                {id: 'e1', from: 1, to: 2},
                {id: 'e2', from: 2, to: 3}
            ]
        };

        initGraph(testData, true);
    }

    // 初始化图
    function initGraph(graphData, physicsEnabled) {
        try {
            // 处理重复的节点ID
            const uniqueNodes = [];
            const nodeIdSet = new Set();

            if (graphData.nodes) {
                graphData.nodes.forEach(node => {
                    let nodeId = node.id;
                    // 如果ID已存在，生成新的唯一ID
                    while (nodeIdSet.has(nodeId)) {
                        nodeId = `${node.id}_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
                        console.warn(`节点ID冲突，重命名: ${node.id} -> ${nodeId}`);
                    }
                    nodeIdSet.add(nodeId);
                    uniqueNodes.push({...node, id: nodeId});
                });
            }

            // 处理重复的边ID
            const uniqueEdges = [];
            const edgeIdSet = new Set();

            if (graphData.edges) {
                graphData.edges.forEach(edge => {
                    // 生成边的唯一标识（from_to_label）
                    let edgeId = edge.id || `edge_${edge.from}_${edge.to}`;
                    // 如果ID已存在，生成新的唯一ID
                    while (edgeIdSet.has(edgeId)) {
                        edgeId = `${edgeId}_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
                    }
                    edgeIdSet.add(edgeId);
                    uniqueEdges.push({...edge, id: edgeId});
                });
            }

            // 创建数据集
            nodes = new vis.DataSet(uniqueNodes);
            edges = new vis.DataSet(uniqueEdges);

            const data = { nodes, edges };

            const options = {
                physics: {
                    enabled: physicsEnabled !== undefined ? physicsEnabled : true,
                    stabilization: { iterations: 100 }
                },
                interaction: {
                    dragNodes: true,
                    dragView: true,
                    zoomView: true,
                    hover: true,
                    tooltipDelay: 200
                },
                nodes: {
                    shape: 'dot',
                    size: 16,
                    font: {
                        size: 14,
                        color: '#ffffff',
                        face: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Oxygen, Ubuntu, Cantarell, "Open Sans", "Helvetica Neue", sans-serif'
                    }
                },
                edges: {
                    arrows: { to: { enabled: true, scaleFactor: 0.5 } },
                    smooth: { enabled: true },
                    color: { color: '#666666' }
                }
            };

            container = document.getElementById('mynetwork');
            if (container) {
                container.innerHTML = '';
                network = new vis.Network(container, data, options);
                bindNetworkEvents();
                bindGlobalEvents(); // 确保全局事件被绑定

                // 通知浮动面板更新物理效果状态
                setTimeout(() => {
                    if (network) {
                        window.dispatchEvent(new CustomEvent('physicsStatusUpdated', {
                            detail: { enabled: network.physics.options.enabled }
                        }));
                    }
                }, 100);
            }
        } catch (error) {
            console.error('初始化图失败:', error);
            const errorContainer = document.getElementById('mynetwork');
            if (errorContainer) {
                errorContainer.innerHTML = '<div style="text-align: center; padding: 50px; color: red;">初始化图失败: ' + error.message + '</div>';
            }
        }
    }

    // 绑定网络事件
    function bindNetworkEvents() {
        if (!network) return;

        // 清空之前的事件监听器
        const events = [
            "click", "doubleClick", "oncontext", "hold", "release", "select",
            "selectNode", "selectEdge", "deselectNode", "deselectEdge",
            "dragStart", "dragging", "dragEnd", "hoverNode", "blurNode",
            "hoverEdge", "blurEdge", "zoom", "showPopup", "hidePopup"
        ];
        events.forEach(event => network.off(event));

        // 事件处理
        network.on("click", handleClick);
        network.on("doubleClick", handleDoubleClick);
        network.on("oncontext", handleContextMenu); // 右键点击
        network.on("hold", handleHold); // 长按事件
        network.on("release", handleRelease); // 松手事件
        network.on("hoverNode", params => { state.hoveredNode = params.node; });
        network.on("blurNode", () => { state.hoveredNode = null; });
        network.on("hoverEdge", params => { state.hoveredEdge = params.edge; });
        network.on("blurEdge", () => { state.hoveredEdge = null; });
        network.on("selectNode", params => {
            state.selectedNode = params.nodes.length > 0 ? params.nodes[0] : null;
        });
    }

    // 点击事件处理
    function handleClick(params) {
        logDebug(`🖱️ 点击事件 - 节点: ${params.nodes.length}, 边: ${params.edges.length}`);
        state.selectedNode = params.nodes.length > 0 ? params.nodes[0] : null;

        // 如果点击的是空白区域且菜单显示，则隐藏菜单
        if (state.isMenuVisible && params.nodes.length === 0 && params.edges.length === 0) {
            hideAllContextMenus();
        }
    }

    // 双击事件处理
    function handleDoubleClick(params) {
        logDebug(`👆 双击事件 - 节点: ${params.nodes.length}, 边: ${params.edges.length}`);

        if (params.nodes.length > 0) {
            state.contextMenuNode = params.nodes[0];
            showEditNodeLabelInput();
        }
        else if (params.edges.length > 0) {
            state.contextMenuEdge = params.edges[0];
            showEditEdgeLabelInput();
        }
    }

    // 右键菜单事件处理（右键点击）
    function handleContextMenu(params) {
        params.event.preventDefault();
        showContextMenuAtPosition(params);
    }

    // 长按事件处理（hold）
    function handleHold(params) {
        logDebug(`✋ 长按事件 - 节点: ${params.nodes.length}, 边: ${params.edges.length}`);

        // 清除旧的定时器
        if (state.menuShowTimer) {
            clearTimeout(state.menuShowTimer);
        }

        // 标记菜单即将显示
        state.menuScheduledToShow = true;

        state.menuShowTimer = setTimeout(() => {
            showContextMenuAtPosition(params);
            state.menuScheduledToShow = false; // 菜单已显示
        }, 100);
    }

    function handleRelease(params) {
        logDebug(`放开 release事件`);
    }

    // 统一的上下文菜单显示函数
    function showContextMenuAtPosition(params) {
        // 优先级：节点 > 边 > 空白区域
        if (params.nodes.length > 0) {
            state.contextMenuNode = params.nodes[0];
            state.selectedNode = params.nodes[0];
            const node = nodes.get(params.nodes[0]);
            logDebug(`🖱️ 点击节点: ${node.label} (ID: ${node.id})`);
            showNodeContextMenu(params.pointer.DOM);
        } else if (params.edges.length > 0) {
            state.contextMenuEdge = params.edges[0];
            const edge = edges.get(params.edges[0]);
            logDebug(`🖱️ 点击边: ${edge.from} -> ${edge.to} (ID: ${edge.id})`);
            showEdgeContextMenu(params.pointer.DOM);
        } else {
            logDebug("🖱️ 点击画布空白处");
            hideAllContextMenus();
        }
    }

    // 绑定全局事件
    function bindGlobalEvents() {
        document.addEventListener('click', function (e) {
            const menus = document.querySelectorAll('.context-menu, .input-menu');
            let clickedInsideMenu = false;
            menus.forEach(menu => {
                if (menu.contains(e.target)) {
                    clickedInsideMenu = true;
                }
            });
        });

        document.addEventListener('keydown', function (e) {
            if (e.key === 'Escape') {
                hideAllContextMenus();
                cancelMode();
            }
        });
    }

    // 菜单显示函数
    function showNodeContextMenu(domPos) {
        hideAllContextMenus();
        const menu = document.getElementById('nodeContextMenu');

        // 更新菜单标题显示节点信息
        if (state.contextMenuNode) {
            const node = nodes.get(state.contextMenuNode);
            const menuHeader = menu.querySelector('ul li:first-child');
            if (menuHeader) {
                // 在菜单最前面添加标题信息
                const titleElement = document.createElement('li');
                titleElement.className = 'menu-title';
                titleElement.textContent = `节点: ${node.label || '未命名'}`;
                titleElement.style.fontWeight = 'bold';
                titleElement.style.backgroundColor = '#f0f0f0';
                titleElement.style.pointerEvents = 'none';
                menu.querySelector('ul').insertBefore(titleElement, menuHeader);
            }
        }

        menu.style.display = 'block';
        positionContextMenu(menu, domPos);
        state.isMenuVisible = true;
    }

    function showEdgeContextMenu(domPos) {
        hideAllContextMenus();
        const menu = document.getElementById('edgeContextMenu');

        // 更新菜单标题显示边信息
        if (state.contextMenuEdge) {
            const edge = edges.get(state.contextMenuEdge);
            const fromNode = nodes.get(edge.from);
            const toNode = nodes.get(edge.to);

            const menuHeader = menu.querySelector('ul li:first-child');
            if (menuHeader) {
                // 在菜单最前面添加标题信息
                const titleElement = document.createElement('li');
                titleElement.className = 'menu-title';
                titleElement.textContent = `连接: ${fromNode.label || fromNode.id} → ${toNode.label || toNode.id}`;
                titleElement.style.fontWeight = 'bold';
                titleElement.style.backgroundColor = '#f0f0f0';
                titleElement.style.pointerEvents = 'none';
                menu.querySelector('ul').insertBefore(titleElement, menuHeader);
            }
        }

        menu.style.display = 'block';
        positionContextMenu(menu, domPos);
        state.isMenuVisible = true;
    }

    function showCreateNodeInput() {
        hideAllContextMenus();
        const menu = document.getElementById('createNodeInput');
        const input = document.getElementById('newNodeLabel');
        input.value = "新节点";

        // 更新菜单标题显示源节点信息
        const titleDiv = menu.querySelector('div:first-child');
        if (titleDiv && state.contextMenuNode) {
            const node = nodes.get(state.contextMenuNode);
            titleDiv.textContent = `从节点 "${node.label || node.id}" 创建新节点`;
            titleDiv.style.fontWeight = 'bold';
        }

        menu.style.display = 'block';
        positionContextMenu(menu, {x: event.clientX, y: event.clientY});
        input.focus();
        state.isConnectingNewNode = true;
        state.isMenuVisible = true;
    }

    function showEditNodeLabelInput() {
        if (state.contextMenuNode) {
            hideAllContextMenus();
            const menu = document.getElementById('editNodeLabelInput');
            const input = document.getElementById('editNodeLabelText');
            const node = nodes.get(state.contextMenuNode);
            input.value = node.label || "";

            // 更新菜单标题显示节点信息
            const titleDiv = menu.querySelector('div:first-child');
            if (titleDiv) {
                titleDiv.textContent = `编辑节点: ${node.label || '未命名'}`;
                titleDiv.style.fontWeight = 'bold';
            }

            menu.style.display = 'block';
            positionContextMenu(menu, {x: event.clientX, y: event.clientY});
            input.focus();
            state.isMenuVisible = true;
        }
    }

    function showEditEdgeLabelInput() {
        if (state.contextMenuEdge) {
            hideAllContextMenus();
            const menu = document.getElementById('editEdgeLabelInput');
            const input = document.getElementById('editEdgeLabelText');
            const edge = edges.get(state.contextMenuEdge);
            input.value = edge.label || "";

            // 更新菜单标题显示边信息
            const titleDiv = menu.querySelector('div:first-child');
            if (titleDiv) {
                const fromNode = nodes.get(edge.from);
                const toNode = nodes.get(edge.to);
                titleDiv.textContent = `编辑连接: ${fromNode.label || fromNode.id} → ${toNode.label || toNode.id}`;
                titleDiv.style.fontWeight = 'bold';
            }

            menu.style.display = 'block';
            positionContextMenu(menu, {x: event.clientX, y: event.clientY});
            input.focus();
            state.isMenuVisible = true;
        }
    }

    // 定位菜单位置
    function positionContextMenu(menu, domPos) {
        let x = domPos.x;
        let y = domPos.y;
        offset = 0
        x -= offset;
        y -= offset;

        const rect = menu.getBoundingClientRect();
        if (x + rect.width > window.innerWidth) {
            x = window.innerWidth - rect.width - offset;
        }
        if (y + rect.height > window.innerHeight) {
            y = window.innerHeight - rect.height - offset;
        }
        if (x < 0) x = offset;
        if (y < 0) y = offset;

        menu.style.left = x + 'px';
        menu.style.top = y + 'px';
    }

    // 修改 hideAllContextMenus 函数，清理动态添加的标题
    function hideAllContextMenus() {
        const menus = document.querySelectorAll('.context-menu, .input-menu');
        menus.forEach(menu => {
            menu.style.display = 'none';

            // 清理动态添加的标题元素
            if (menu.id === 'nodeContextMenu' || menu.id === 'edgeContextMenu') {
                const titleElements = menu.querySelectorAll('.menu-title');
                titleElements.forEach(el => el.remove());
            }
        });

        // 清除定时器
        if (state.menuShowTimer) {
            clearTimeout(state.menuShowTimer);
            state.menuShowTimer = null;
        }
        state.isMenuVisible = false;
    }

    // 输入确认函数
    function confirmCreateNode() {
        const input = document.getElementById('newNodeLabel');
        const label = input.value || "新节点";
        const newNodeId = 'node_' + Date.now();

        if (state.contextMenuNode && state.isConnectingNewNode) {
            const nodePos = network.getPositions([state.contextMenuNode])[state.contextMenuNode];
            nodes.add({
                id: newNodeId,
                label: label,
                x: nodePos.x + 100,
                y: nodePos.y + 100
            });
            edges.add({
                from: state.contextMenuNode,
                to: newNodeId
            });
            logDebug(`从节点 ${state.contextMenuNode} 创建并连接新节点: ${newNodeId}`);
        } else if (state.addingNode) {
            nodes.add({
                id: newNodeId,
                label: label,
                x: window.addNodeX || 0,
                y: window.addNodeY || 0
            });
            logDebug(`创建新节点: ${newNodeId}`);
        }

        state.isConnectingNewNode = false;
        hideAllContextMenus();
    }

    function confirmEditNodeLabel() {
        if (state.contextMenuNode) {
            const input = document.getElementById('editNodeLabelText');
            const newLabel = input.value || "未命名节点";
            nodes.update({ id: state.contextMenuNode, label: newLabel });
            logDebug(`编辑节点标签: ${state.contextMenuNode} -> ${newLabel}`);
            hideAllContextMenus();
        }
    }

    function confirmEditEdgeLabel() {
        if (state.contextMenuEdge) {
            const input = document.getElementById('editEdgeLabelText');
            const newLabel = input.value || "";
            edges.update({ id: state.contextMenuEdge, label: newLabel });
            logDebug(`编辑边标签: ${state.contextMenuEdge} -> "${newLabel}"`);
            hideAllContextMenus();
        }
    }

    function cancelInput() {
        hideAllContextMenus();
    }

    // 节点菜单操作
    function deleteSelectedNode() {
        if (state.contextMenuNode) {
            const connectedEdges = network.getConnectedEdges(state.contextMenuNode);
            edges.remove(connectedEdges);
            nodes.remove(state.contextMenuNode);
            logDebug(`删除节点: ${state.contextMenuNode}`);
            hideAllContextMenus();
        }
    }

    function connectToExistingNodeMode() {
        if (state.contextMenuNode) {
            state.connectingToExisting = true;
            state.connectionSourceNode = state.contextMenuNode;
            logDebug(`连接模式: 请点击目标节点以连接到 ${state.contextMenuNode}`);
            hideAllContextMenus();
        }
    }

    // 边菜单操作
    function deleteSelectedEdge() {
        if (state.contextMenuEdge) {
            edges.remove(state.contextMenuEdge);
            logDebug(`删除边: ${state.contextMenuEdge}`);
            hideAllContextMenus();
        }
    }

    function reverseEdgeDirection() {
        if (state.contextMenuEdge) {
            const edge = edges.get(state.contextMenuEdge);
            edges.remove(state.contextMenuEdge);
            edges.add({
                id: state.contextMenuEdge,
                from: edge.to,
                to: edge.from,
                label: edge.label
            });
            logDebug(`反转边方向: ${edge.to} -> ${edge.from}`);
            hideAllContextMenus();
        }
    }

    // 模式控制
    function cancelMode() {
        if (network) {
            network.disableEditMode();
        }
        state.addingNode = false;
        state.connectingToExisting = false;
        state.connectionSourceNode = null;
        logDebug("已取消所有模式");
        hideAllContextMenus();
    }

    function addNodeMode() {
        state.addingNode = true;
        logDebug("进入添加节点模式，请点击画布添加节点");
    }

    // 日志函数
    function logDebug(message) {
        const debugInfo = document.getElementById('debug-info');
        if (debugInfo) {
            debugInfo.textContent = message;
        }
    }

    function initWithGraphData(graphData, physicsEnabled) {
        initGraph(graphData, physicsEnabled);
    }

    // 公共接口
    return {
        init,
        cancelMode,
        initWithGraphData,
        addNodeMode,
        deleteSelectedNode,
        showCreateNodeInput,
        connectToExistingNodeMode,
        showEditNodeLabelInput,
        deleteSelectedEdge,
        showEditEdgeLabelInput,
        reverseEdgeDirection,
        confirmCreateNode,
        cancelInput,
        confirmEditNodeLabel,
        confirmEditEdgeLabel,
        saveGraph,
        clearGraph,
        exportGraph,
        // 为了在外部访问 network
        get network() { return network; },
        get nodes() { return nodes; },
        get edges() { return edges; }
    };
})();

// 自动初始化
document.addEventListener('DOMContentLoaded', function() {
    // 从 URL 获取 cache_key
    const urlParams = new URLSearchParams(window.location.search);
    const cacheKey = urlParams.get('cache_key') || '';

    // 如果有 cache_key，加载图谱数据
    if (cacheKey) {
        loadGraphData(cacheKey);
    } else {
        // 否则初始化默认图谱
        GraphEditor.init();
    }
});

// 加载图谱数据
async function loadGraphData(cacheKey) {
    try {
        const response = await fetch(`/api/graph-data?cache_key=${encodeURIComponent(cacheKey)}`);
        const result = await response.json();

        if (!response.ok || !result.success) {
            throw new Error(result.error || '加载图谱数据失败');
        }

        // 初始化 GraphEditor
        GraphEditor.initWithGraphData(result.data, result.physics);

    } catch (error) {
        console.error('加载图谱失败:', error);
        // 确保能获取到 container
        const container = document.getElementById('mynetwork');
        if (container) {
            container.innerHTML = `<div style="text-align: center; padding: 50px; color: #ff6b6b;">
                ❌ 加载图谱失败: ${error.message}
            </div>`;
        } else {
            // 如果连 container 都获取不到，在 body 中显示错误
            document.body.innerHTML = `<div style="text-align: center; padding: 50px; color: #ff6b6b; background: #1e1e1e; height: 100vh;">
                ❌ 加载图谱失败: ${error.message}
            </div>`;
        }
    }
}