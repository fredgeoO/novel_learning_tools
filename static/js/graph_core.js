// graph_core.js - 核心图数据、状态管理和网络图初始化

const GraphCore = (function() {
    // 私有变量
    let network, nodes, edges;
    let container;
    let currentCacheKey = null; // 用于保存/刷新

    // 状态管理
    const state = {
        selectedNode: null,
        highlightedNode: null, // 用于跟踪当前高亮的节点ID
        hoveredNode: null,
        hoveredEdge: null,
    };

    // --- 颜色映射表 (与后端保持一致) ---
    const NODE_COLOR_MAP = {
        "人物": "#FF6B6B",
        "地点": "#D2B48C",
        "时间": "#87CEEB",
        "事件": "#4682B4",
        "物件": "#98FB98",
        "物品": "#98FB98",
        "对白": "#F7DC6F",
        "想法": "#AED6F1",
        "情绪": "#F7DC6F",
        "状态": "#98FB98",
        "原因": "#FF6B6B",
        "行动": "#BB8FCE",
        "结果": "#96CEB4",
        "聚合概念": "#00CED1",
        "未知": "#CCCCCC"
    };

    const EDGE_COLOR_MAP = {
        "位于": "#A0522D",
        "发生在": "#1E90FF",
        "参与": "#104E8B",
        "导致": "#FF4500",
        "涉及": "#228B22",
        "说出": "#F5DEB3",
        "产生": "#90EE90",
        "经历": "#FF69B4",
        "处于": "#98FB98",
        "属于": "#FF7F50",
        "拥有": "#DEB887",
        "包含": "#DAA520",
        "执行": "#DEB887",
        "前往": "#1E90FF",
        "持续": "#FFD700",
        "敌人": "#FF0000",
        "朋友": "#00FF00",
        "认识": "#F7DC6F"
    };

    // --- 颜色缓存和生成 ---
    const _colorCache = {};

    function simpleHash(text) {
        let hash = 0;
        for (let i = 0; i < text.length; i++) {
            const char = text.charCodeAt(i);
            hash = ((hash << 5) - hash) + char;
            hash = hash & hash;
        }
        return Math.abs(hash);
    }

    function generateColorFromString(text) {
        if (_colorCache[text]) {
            return _colorCache[text];
        }
        const hashValue = simpleHash(text);
        let r = (hashValue >> 16) & 0xFF;
        let g = (hashValue >> 8) & 0xFF;
        let b = hashValue & 0xFF;

        let rf = r / 255.0;
        let gf = g / 255.0;
        let bf = b / 255.0;
        const max = Math.max(rf, gf, bf);
        const min = Math.min(rf, gf, bf);
        let h, s, l;

        l = (max + min) / 2;
        if (max === min) {
            h = s = 0;
        } else {
            const d = max - min;
            s = l > 0.5 ? d / (2 - max - min) : d / (max + min);
            switch(max) {
                case rf: h = (gf - bf) / d + (gf < bf ? 6 : 0); break;
                case gf: h = (bf - rf) / d + 2; break;
                case bf: h = (rf - gf) / d + 4; break;
            }
            if (h !== undefined) h /= 6;
        }

        s = 0.6 + (s * 0.4);
        l = 0.4 + (l * 0.4);

        const hue2rgb = (p, q, t) => {
            if (t < 0) t += 1;
            if (t > 1) t -= 1;
            if (t < 1/6) return p + (q - p) * 6 * t;
            if (t < 1/2) return q;
            if (t < 2/3) return p + (q - p) * (2/3 - t) * 6;
            return p;
        };

        let r1, g1, b1;
        if (s === 0) {
            r1 = g1 = b1 = l;
        } else {
            const q = l < 0.5 ? l * (1 + s) : l + s - l * s;
            const p = 2 * l - q;
            r1 = hue2rgb(p, q, h + 1/3);
            g1 = hue2rgb(p, q, h);
            b1 = hue2rgb(p, q, h - 1/3);
        }

        const colorHex = `#${Math.round(r1 * 255).toString(16).padStart(2, '0')}${Math.round(g1 * 255).toString(16).padStart(2, '0')}${Math.round(b1 * 255).toString(16).padStart(2, '0')}`;
        _colorCache[text] = colorHex;
        return colorHex;
    }

    // --- 数据格式转换 ---
    function convertOriginalToVisFormat(originalData) {
        console.log('转换前的原始数据:', originalData);
        if (!originalData) {
            console.warn('原始数据为空，返回空结构');
            return { nodes: [], edges: [] };
        }

        const rawNodes = Array.isArray(originalData.nodes) ? originalData.nodes : [];
        const rawEdges = Array.isArray(originalData.edges) ? originalData.edges : [];

        console.log(`处理 ${rawNodes.length} 个节点和 ${rawEdges.length} 条边`);

        const processedNodes = processNodes(rawNodes);
        const processedEdges = processEdges(rawEdges);

        console.log('转换并着色后的 Vis 数据:', { nodes: processedNodes, edges: processedEdges });
        return {
            nodes: processedNodes,
            edges: processedEdges
        };
    }

    function processNodes(rawNodes) {
        return rawNodes
            .map((node, index) => {
                if (!node || !node.id) {
                    console.warn(`节点 ${index} 缺少 ID，跳过`);
                    return null;
                }

                if (node.label === undefined || node.label === null) {
                    node.label = String(node.id);
                }

                if (node.size === undefined || node.size === null) {
                    node.size = 25;
                }

                if (!hasValidNodeColor(node)) {
                    const nodeType = determineNodeType(node);
                    applyNodeColor(node, nodeType);
                } else {
                    console.log(`节点 ${node.id} 已有颜色:`, node.color);
                }

                return node;
            })
            .filter(node => node !== null);
    }

    function hasValidNodeColor(node) {
        if (typeof node.color === 'string' && node.color.startsWith('#')) {
            return true;
        } else if (node.color && typeof node.color === 'object') {
            return Object.values(node.color).some(val => typeof val === 'string' && val.startsWith('#'));
        }
        return false;
    }

    function determineNodeType(node) {
        let nodeType = '未知';

        if (node.originalData && node.originalData.type && typeof node.originalData.type === 'string') {
            nodeType = node.originalData.type.trim();
        }
        else if (node.originalData && node.originalData.properties && node.originalData.properties.type && typeof node.originalData.properties.type === 'string') {
            nodeType = node.originalData.properties.type.trim();
        }
        else if (node.title && typeof node.title === 'string') {
            const titleMatch = node.title.match(/^\s*([^(\s]+)\s*\(/);
            if (titleMatch && titleMatch[1]) {
                nodeType = titleMatch[1].trim();
            }
        }
        else if (node.type && typeof node.type === 'string') {
            nodeType = node.type.trim();
        }

        return nodeType;
    }

    function applyNodeColor(node, nodeType) {
        let mappedColor;

        if (nodeType === '未知类型' || nodeType === '未知') {
            const label = (node.label && typeof node.label === 'string') ? node.label.trim() : String(node.id);
            mappedColor = generateColorFromString(label);
            console.log(`为节点 ${node.id} 使用 label "${label}" 生成稳定颜色: ${mappedColor}`);
        } else {
            mappedColor = NODE_COLOR_MAP[nodeType];
            if (!mappedColor) {
                mappedColor = generateColorFromString(nodeType);
                console.log(`为节点 ${node.id} (${nodeType}) 生成稳定颜色: ${mappedColor}`);
            } else {
                console.log(`为节点 ${node.id} (${nodeType}) 应用预设颜色: ${mappedColor}`);
            }
        }

        node.color = mappedColor;
    }

    function processEdges(rawEdges) {
        return rawEdges
            .map((edge, index) => {
                if (!edge || edge.from === undefined || edge.to === undefined) {
                    console.warn(`边 ${index} 缺少 from 或 to，跳过`);
                    return null;
                }

                if (edge.id === undefined || edge.id === null) {
                    edge.id = `edge_${edge.from}_${edge.to}_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
                }

                if (edge.label === undefined || edge.label === null) {
                    edge.label = (edge.type && typeof edge.type === 'string') ? edge.type : '';
                }

                if (edge.width === undefined || edge.width === null) {
                    edge.width = 2;
                }

                if (!edge.arrows) {
                    edge.arrows = 'to';
                }

                if (!hasValidEdgeColor(edge)) {
                    const edgeType = determineEdgeType(edge);
                    applyEdgeColor(edge, edgeType);
                } else {
                    console.log(`边 ${edge.id} 已有颜色:`, edge.color);
                }

                return edge;
            })
            .filter(edge => edge !== null);
    }

    function hasValidEdgeColor(edge) {
        if (!edge.color) return false;

        if (typeof edge.color === 'string' && edge.color.startsWith('#')) {
            return true;
        } else if (typeof edge.color === 'object') {
            if (edge.color.color && typeof edge.color.color === 'string' && edge.color.color.startsWith('#')) {
                return true;
            }
        }
        return false;
    }

    function determineEdgeType(edge) {
        if (edge.type && typeof edge.type === 'string') {
            return edge.type.trim();
        } else if (edge.label && typeof edge.label === 'string') {
            return edge.label.trim();
        } else if (edge.originalData && edge.originalData.type) {
            return (typeof edge.originalData.type === 'string') ? edge.originalData.type.trim() : String(edge.originalData.type);
        }
        return '未知关系';
    }

    function applyEdgeColor(edge, edgeType) {
        let mappedColor = EDGE_COLOR_MAP[edgeType];
        if (!mappedColor) {
            mappedColor = generateColorFromString(edgeType);
        }

        if (!edge.color || typeof edge.color !== 'object') {
            edge.color = {};
        }
        edge.color.color = mappedColor;

        // console.log(`为边 ${edge.id} (${edgeType}) 应用颜色: ${mappedColor}`);
    }

    function convertVisToOriginalFormat(visNodes, visEdges) {
        const originalNodes = visNodes.map(visNode => {
            return {
                id: visNode.id,
                label: visNode.label,
                color: visNode.color,
                size: visNode.size,
                x: visNode.x,
                y: visNode.y,
                title: visNode.title || `${visNode.originalData?.type || '未知'} (${visNode.id})`
            };
        });

        const originalEdges = visEdges.map(visEdge => {
            return {
                id: visEdge.id,
                from: visEdge.from,
                to: visEdge.to,
                label: visEdge.label,
                title: visEdge.title,
                color: visEdge.color,
                width: visEdge.width,
                arrows: visEdge.arrows
            };
        });

        return {
            nodes: originalNodes,
            edges: originalEdges
        };
    }

    // --- 网络图初始化与配置 ---
    function initGraph(graphData, physicsEnabled = true) {
        try {
            const visFormat = convertOriginalToVisFormat(graphData);
            console.log('Vis Network 格式数据:', visFormat);

            const { uniqueNodes, uniqueEdges } = ensureUniqueIds(visFormat.nodes, visFormat.edges);

            nodes = new vis.DataSet(uniqueNodes);
            edges = new vis.DataSet(uniqueEdges);
            const data = { nodes, edges };

            const options = createVisNetworkOptions(physicsEnabled);

            container = document.getElementById('mynetwork');
            if (container) {
                setupNetworkContainer(container);
                container.innerHTML = '';

                network = new vis.Network(container, data, options);

                setTimeout(() => {
                    if (network) {
                        setupNetworkContainer(container);
                        network.redraw();
                    }
                }, 50);

                bindNetworkEvents();

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
                errorContainer.innerHTML = '<div style="text-align: center; padding: 50px; color: red; background: #1e1e1e;">初始化图失败: ' + error.message + '</div>';
            }
        }
        if (typeof window !== 'undefined') {
            window.dispatchEvent(new CustomEvent('graphInitialized', {
                detail: { network: network }
            }));
        }
    }

    function ensureUniqueIds(nodes, edges) {
        const uniqueNodes = [];
        const nodeIdSet = new Set();

        nodes.forEach(node => {
            let nodeId = node.id;
            let counter = 0;
            while (nodeIdSet.has(nodeId)) {
                nodeId = `${node.id}_${++counter}`;
                console.warn(`节点ID冲突，重命名: ${node.id} -> ${nodeId}`);
            }
            nodeIdSet.add(nodeId);
            uniqueNodes.push({...node, id: nodeId});
        });

        const uniqueEdges = [];
        const edgeIdSet = new Set();

        edges.forEach(edge => {
            let edgeId = edge.id || `edge_${edge.from}_${edge.to}`;
            let counter = 0;
            while (edgeIdSet.has(edgeId)) {
                edgeId = `${edge.id || `edge_${edge.from}_${edge.to}`}_${++counter}`;
            }
            edgeIdSet.add(edgeId);
            uniqueEdges.push({...edge, id: edgeId});
        });

        return { uniqueNodes, uniqueEdges };
    }

    function createVisNetworkOptions(physicsEnabled) {
        // 👇 动态计算 springLength
        const baseLength = 100; // 基础间距
        const nodeCount = nodes.length;
        const densityFactor = Math.sqrt(nodeCount); // 或 Math.log(nodeCount + 1)

        const springLength = baseLength * (1 + densityFactor * 0.1);

        console.log(`节点数量: ${nodeCount}, 自动计算 springLength: ${springLength}`);
        return {
            physics: {
                enabled: physicsEnabled,
                stabilization: { iterations: 100 },
                barnesHut: {
                    gravitationalConstant: -2000,
                    centralGravity: 0.1,
                    springLength: springLength,     // 👈 增大这个值（默认约 95-200），节点间距变大
                    springConstant: 0.04,
                    damping: 0.09
                },
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
                font: {
                    size: 14,
                    color: '#ffffff',
                    face: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Oxygen, Ubuntu, Cantarell, "Open Sans", "Helvetica Neue", sans-serif'
                }
            },
            edges: {
                arrows: { to: { enabled: true, scaleFactor: 0.5 } },
                smooth: { enabled: true },
                font: {
                    size: 12,
                    color: '#CCCCCC',
                    face: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Oxygen, Ubuntu, Cantarell, "Open Sans", "Helvetica Neue", sans-serif',
                    strokeWidth: 0,
                    strokeColor: '#1e1e1e'
                },
                color: {
                    color: '#666666',
                    highlight: '#999999',
                    hover: '#AAAAAA'
                },
                width: 1.5
            }
        };
    }

    function setupNetworkContainer(container) {
        container.style.width = '100vw';
        container.style.height = '100vh';
        container.style.margin = '0';
        container.style.padding = '0';
        container.style.overflow = 'hidden';
    }

    // --- 网络事件绑定 ---
    function bindNetworkEvents() {
        if (!network) return;

        const events = [
            "click", "doubleClick", "oncontext", "hold", "release", "select",
            "selectNode", "selectEdge", "deselectNode", "deselectEdge",
            "dragStart", "dragging", "dragEnd", "hoverNode", "blurNode",
            "hoverEdge", "blurEdge", "zoom", "showPopup", "hidePopup"
        ];
        events.forEach(event => network.off(event));

        network.on("hoverNode", params => { state.hoveredNode = params.node; });
        network.on("blurNode", () => { state.hoveredNode = null; });
        network.on("hoverEdge", params => { state.hoveredEdge = params.edge; });
        network.on("blurEdge", () => { state.hoveredEdge = null; });
        network.on("selectNode", params => {
            state.selectedNode = params.nodes.length > 0 ? params.nodes[0] : null;
        });
    }

    // --- 图谱操作 (CRUD) ---
    async function saveGraph() {
        console.log('当前 cacheKey:', currentCacheKey);
        if (!currentCacheKey) {
            alert('未加载图谱，无法保存');
            return;
        }
        try {
            const visNodes = nodes.get();
            const visEdges = edges.get();
            const originalFormat = convertVisToOriginalFormat(visNodes, visEdges);
            console.log('准备保存的数据:', originalFormat);

            const response = await fetch(`/api/graph/${encodeURIComponent(currentCacheKey)}`, {
                method: 'PUT',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify(originalFormat)
            });
            const result = await response.json();
            console.log('保存响应:', result);
            if (response.ok && result.success) {
                alert('✅ 图谱保存成功');
                console.log('图谱已保存');
            } else {
                throw new Error(result.error?.message || '保存失败');
            }
        } catch (error) {
            console.error('保存图谱失败:', error);
            alert('❌ 保存失败：' + error.message);
        }
    }

    async function deleteGraph() {
        if (!currentCacheKey) {
            alert('未加载图谱，无法删除');
            return;
        }
        if (!confirm(`确定要删除图谱 "${currentCacheKey}" 吗？此操作不可恢复。`)) {
            return;
        }
        try {
            const response = await fetch(`/api/graph/${encodeURIComponent(currentCacheKey)}`, {
                method: 'DELETE'
            });
            const result = await response.json();
            if (response.ok && result.success) {
                alert('✅ 图谱删除成功');
                if (nodes && edges) {
                    nodes.clear();
                    edges.clear();
                }
                currentCacheKey = null;
                console.log('图谱已删除');
            } else {
                throw new Error(result.error?.message || '删除失败');
            }
        } catch (error) {
            console.error('删除图谱失败:', error);
            alert('❌ 删除失败：' + error.message);
        }
    }

    async function refreshGraph() {
        if (!currentCacheKey) {
            alert('未加载图谱，无法刷新');
            return;
        }
        await loadGraphData(currentCacheKey);
    }

    function clearGraph() {
        if (confirm('确定要清空当前画布吗？此操作不会影响已保存的图谱。')) {
            if (nodes && edges) {
                nodes.clear();
                edges.clear();
                console.log('图谱已清空（前端）');
            }
            state.highlightedNode = null;
        }
    }

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
            link.download = `graph_${currentCacheKey || 'untitled'}_${new Date().toISOString().slice(0,10)}.json`;
            link.click();
            console.log('图谱已导出');
        } catch (error) {
            console.error('导出图谱失败:', error);
            alert('导出失败：' + error.message);
        }
    }

    function togglePhysics() {
        if (!network) return;
        const current = network.physics.options.enabled;
        network.physics.options.enabled = !current;
        network.physics.simulationActive = !current;
        if (!current) {
            network.physics.startSimulation();
        } else {
            network.physics.stopSimulation();
        }
        window.dispatchEvent(new CustomEvent('physicsStatusUpdated', {
            detail: { enabled: !current }
        }));
        console.log(`物理引擎已${!current ? '开启' : '关闭'}`);
    }

    // --- 高亮功能 ---
    function highlightNodeAndConnections(nodeId) {
        if (!nodes || !edges || !network) return;
        state.highlightedNode = nodeId;

        const allNodes = nodes.get({ returnType: "Object" });
        const allEdges = edges.get({ returnType: "Object" });

        const connectedNodeIds = new Set();
        const connectedEdgeIds = new Set();

        for (const edgeId in allEdges) {
            const edge = allEdges[edgeId];
            if (edge.from === nodeId || edge.to === nodeId) {
                connectedEdgeIds.add(edgeId);
                connectedNodeIds.add(edge.from);
                connectedNodeIds.add(edge.to);
            }
        }

        updateElementsOpacity(allNodes, true, nodeId, connectedNodeIds, 0.2);
        updateElementsOpacity(allEdges, false, nodeId, connectedEdgeIds, 0.1);
    }

    function updateElementsOpacity(elements, isNode, highlightedId, connectedIds, opacity) {
        const elementsToUpdate = [];

        for (const id in elements) {
            const element = elements[id];
            const isHighlighted = (isNode && id === highlightedId) || (!isNode && (element.from === highlightedId || element.to === highlightedId));
            const isConnected = connectedIds.has(id);

            let newColor;
            if (isHighlighted || isConnected) {
                if (element._originalColor) {
                    newColor = element._originalColor;
                    delete element._originalColor;
                } else {
                    newColor = element.color;
                }
            } else {
                if (!element._originalColor) {
                    element._originalColor = JSON.parse(JSON.stringify(element.color));
                }
                newColor = applyTransparencyToColor(element.color, opacity);
            }

            elementsToUpdate.push({ id: id, color: newColor });
        }

        if (elementsToUpdate.length > 0) {
            if (isNode) {
                nodes.update(elementsToUpdate);
            } else {
                edges.update(elementsToUpdate);
            }
        }
    }

    function applyTransparencyToColor(color, opacity) {
        if (typeof color === 'string' && color.startsWith('#')) {
            return hexToRGBA(color, opacity);
        } else if (typeof color === 'object') {
            const newColorObject = {};
            for (const key in color) {
                if (color.hasOwnProperty(key)) {
                    if (typeof color[key] === 'string' && color[key].startsWith('#')) {
                        newColorObject[key] = hexToRGBA(color[key], opacity);
                    } else {
                        newColorObject[key] = color[key];
                    }
                }
            }
            if (color.color && typeof color.color === 'string' && color.color.startsWith('#')) {
                newColorObject.color = hexToRGBA(color.color, opacity);
            }
            return newColorObject;
        }
        console.warn('无法应用透明度到颜色:', color);
        return `rgba(200, 200, 200, ${opacity})`;
    }

    function hexToRGBA(hex, opacity) {
        let r = 0, g = 0, b = 0;
        if (hex.length === 4) {
          r = "0x" + hex[1] + hex[1];
          g = "0x" + hex[2] + hex[2];
          b = "0x" + hex[3] + hex[3];
        } else if (hex.length === 7) {
          r = "0x" + hex[1] + hex[2];
          g = "0x" + hex[3] + hex[4];
          b = "0x" + hex[5] + hex[6];
        }
        return `rgba(${+r}, ${+g}, ${+b}, ${opacity})`;
    }

    function resetHighlight() {
        if (!nodes || !edges || !state.highlightedNode) return;
        state.highlightedNode = null;

        const allNodes = nodes.get();
        const allEdges = edges.get();

        const nodesToUpdate = allNodes
            .filter(node => node._originalColor !== undefined)
            .map(node => {
                const update = { id: node.id, color: node._originalColor };
                delete node._originalColor;
                return update;
            });

        const edgesToUpdate = allEdges
            .filter(edge => edge._originalColor !== undefined)
            .map(edge => {
                const update = { id: edge.id, color: edge._originalColor };
                delete edge._originalColor;
                return update;
            });

        if (nodesToUpdate.length > 0) nodes.update(nodesToUpdate);
        if (edgesToUpdate.length > 0) edges.update(edgesToUpdate);
    }

    // --- 数据加载 ---
    async function loadGraphData(cacheKey) {
        try {
            const container = document.getElementById('mynetwork');
            if (container) {
                setupNetworkContainer(container);
                container.innerHTML = `<div style="text-align: center; padding: 50px; color: #888;">🔄 正在加载图谱数据...</div>`;
            }

            const url = `/api/graph-data?cache_key=${encodeURIComponent(cacheKey)}`;
            console.log('请求 URL:', url);
            const response = await fetch(url);
            const result = await response.json();
            console.log('后端响应:', response.status, result);

            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${result.error || '未知错误'}`);
            }
            if (!result.success) {
                throw new Error(result.error?.message || '加载图谱数据失败');
            }

            initWithGraphData(result, cacheKey);
        } catch (error) {
            console.error('加载图谱失败:', error);
            const container = document.getElementById('mynetwork');
            if (container) {
                container.innerHTML = `<div style="text-align: center; padding: 50px; color: #ff6b6b; background: #1e1e1e;">❌ 加载图谱失败: ${error.message}</div>`;
            }
            throw error;
        }
    }

    function initWithGraphData(apiResult, cacheKey) {
        console.log('initWithGraphData 接收到的数据:', apiResult);
        console.log('cacheKey:', cacheKey);

        if (!apiResult || !apiResult.data) {
            throw new Error('无效的图谱数据格式：缺少 data 字段');
        }
        const graphData = apiResult.data.data;
        const physicsEnabled = apiResult.data.physics;
        console.log('graphData 结构:', graphData);

        if (!graphData) {
            throw new Error('无效的图谱数据格式：缺少实际数据');
        }

        if (!Array.isArray(graphData.nodes)) {
            console.warn('nodes 不是数组，使用空数组');
            graphData.nodes = [];
        }
        if (!Array.isArray(graphData.edges)) {
            console.warn('edges 不是数组，使用空数组');
            graphData.edges = [];
        }

        currentCacheKey = cacheKey;
        console.log('currentCacheKey 已设置为:', currentCacheKey);

        initGraph(graphData, physicsEnabled);
    }

    // --- 公共接口 ---
    return {
        // 初始化
        initWithGraphData,
        loadGraphData,

        // 数据操作
        saveGraph,
        deleteGraph,
        refreshGraph,
        clearGraph,
        exportGraph,

        // 物理引擎
        togglePhysics,

        // 高亮功能
        highlightNodeAndConnections,
        resetHighlight,

        // 状态和数据访问
        get network() { return network; },
        get nodes() { return nodes; },
        get edges() { return edges; },
        get cacheKey() { return currentCacheKey; },
        get state() { return state; }
    };
})();