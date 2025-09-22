const GraphEditor = (function() {
    // 私有变量
    let network, nodes, edges;
    let container;
    let currentCacheKey = null; // 用于保存/刷新

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
        menuScheduledToShow: false,
        highlightedNode: null, // 用于跟踪当前高亮的节点ID
    };

    // 初始化
    function init() {
        container = document.getElementById('mynetwork');
        bindGlobalEvents();
    }

    // 保存图谱功能
    async function saveGraph() {
        console.log('当前 cacheKey:', currentCacheKey); // 调试信息

        if (!currentCacheKey) {
            alert('未加载图谱，无法保存');
            return;
        }

        try {
            // 获取当前 Vis Network 数据
            const visNodes = nodes.get();
            const visEdges = edges.get();

            // 转换回原始格式
            const originalFormat = convertVisToOriginalFormat(visNodes, visEdges);

            console.log('准备保存的数据:', originalFormat); // 调试信息

            const response = await fetch(`/api/graph/${encodeURIComponent(currentCacheKey)}`, {
                method: 'PUT',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify(originalFormat)
            });

            const result = await response.json();
            console.log('保存响应:', result); // 调试信息

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

    // 将 Vis Network 格式转换为原始格式
    function convertVisToOriginalFormat(visNodes, visEdges) {
        // 转换节点 - 保持现有的 Vis Network 格式
        const originalNodes = visNodes.map(visNode => {
            // 直接返回 Vis Network 格式的节点，因为我们就是要保存这种格式
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

        // 转换边 - 保持现有的 Vis Network 格式
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
    // --- 颜色映射表 (与后端保持一致) ---
const NODE_COLOR_MAP = {
    "人物": "#FF6B6B",
    "地点": "#D2B48C", // 从土黄色改为更接近原文的土黄 #D2B48C
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
    "聚合概念": "#00CED1", // 深绿松石色
    "未知": "#CCCCCC" // 默认灰色
};

const EDGE_COLOR_MAP = {
    "位于": "#A0522D", // 深褐
    "发生在": "#1E90FF", // 道奇蓝
    "参与": "#104E8B", // 深藏青
    "导致": "#FF4500", // 橙红
    "涉及": "#228B22", // 森林绿
    "说出": "#F5DEB3", // 小麦色
    "产生": "#90EE90", // 浅绿
    "经历": "#FF69B4", // 热粉
    "处于": "#98FB98", // 浅绿
    "属于": "#FF7F50", // 珊瑚色
    "拥有": "#DEB887", // 榛子色
    "包含": "#DAA520", // 金麒麟鱼色
    "执行": "#DEB887", // 榛子色
    "前往": "#1E90FF", // 道奇蓝
    "持续": "#FFD700", // 金色
    "敌人": "#FF0000", // 红色
    "朋友": "#00FF00", // 绿色
    "认识": "#F7DC6F" // 黄色
};

// --- 简单的字符串哈希和颜色生成功能 ---
const _colorCache = {}; // 颜色缓存

function simpleHash(text) {
    let hash = 0;
    for (let i = 0; i < text.length; i++) {
        const char = text.charCodeAt(i);
        hash = ((hash << 5) - hash) + char;
        hash = hash & hash; // 转换为32位整数
    }
    return Math.abs(hash); // 返回正数
}

function generateColorFromString(text) {
    if (_colorCache[text]) {
        return _colorCache[text];
    }

    const hashValue = simpleHash(text);
    // 使用哈希值生成RGB值，模拟 HSV 调整
    let r = (hashValue >> 16) & 0xFF;
    let g = (hashValue >> 8) & 0xFF;
    let b = hashValue & 0xFF;

    // 简化的 HSV 调整：提高饱和度和亮度的感知一致性
    // 将 RGB 转换为 0-1 范围
    let rf = r / 255.0;
    let gf = g / 255.0;
    let bf = b / 255.0;

    // 找到最大值和最小值
    const max = Math.max(rf, gf, bf);
    const min = Math.min(rf, gf, bf);
    let h, s, l;

    // 计算亮度 (Lightness)
    l = (max + min) / 2;

    if (max === min) {
        // 灰色
        h = s = 0;
    } else {
        const d = max - min;
        // 计算饱和度 (Saturation)
        s = l > 0.5 ? d / (2 - max - min) : d / (max + min);
        // 计算色相 (Hue)
        switch(max) {
            case rf: h = (gf - bf) / d + (gf < bf ? 6 : 0); break;
            case gf: h = (bf - rf) / d + 2; break;
            case bf: h = (rf - gf) / d + 4; break;
        }
        if (h !== undefined) h /= 6;
    }

    // 调整饱和度和亮度到中等范围
    s = 0.6 + (s * 0.4); // 饱和度范围 0.6-1.0
    l = 0.4 + (l * 0.4); // 亮度范围 0.4-0.8

    // 将 HSL 转换回 RGB (近似)
    // 这是一个简化的转换，对于可视化足够
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
        r1 = g1 = b1 = l; // 黑白灰
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

/**
 * 将后端返回的原始格式（Vis.js 格式）转换为前端使用的 Vis Network 数据，并应用默认颜色。
 * @param {Object} originalData - 后端返回的包含 nodes 和 edges 数组的对象。
 * @returns {Object} - 包含处理后的 nodes 和 edges 数组的对象。
 */
function convertOriginalToVisFormat(originalData) {
    // 添加调试信息
    console.log('转换前的原始数据:', originalData);

    // 确保数据结构正确 - 数据已经是 Vis Network 格式
    if (!originalData) {
        console.warn('原始数据为空，返回空结构');
        return { nodes: [], edges: [] };
    }

    // 直接使用数据，因为后端已经返回了正确的格式
    // 但我们需要确保 nodes 和 edges 是数组
    const rawNodes = Array.isArray(originalData.nodes) ? originalData.nodes : [];
    const rawEdges = Array.isArray(originalData.edges) ? originalData.edges : [];

    console.log(`处理 ${rawNodes.length} 个节点和 ${rawEdges.length} 条边`);

    // --- 处理节点颜色 ---
    const processedNodes = rawNodes.map((node, index) => {
        // 确保节点有 ID
        if (!node || !node.id) {
            console.warn(`节点 ${index} 缺少 ID，跳过`);
            return null;
        }

        // 确保节点有 label
        if (node.label === undefined || node.label === null) {
            node.label = String(node.id); // 确保 label 是字符串
        }

        // --- 颜色处理逻辑 (针对新结构) ---
        // 检查节点是否已有颜色（字符串或对象）
        let hasValidColor = false;
        if (typeof node.color === 'string' && node.color.startsWith('#')) {
            hasValidColor = true;
        } else if (node.color && typeof node.color === 'object') {
            // 检查对象中是否有有效的颜色值
            hasValidColor = Object.values(node.color).some(val => typeof val === 'string' && val.startsWith('#'));
        } // 如果 node.color 不存在或为 null/undefined，则 hasValidColor 保持 false

        if (!hasValidColor) {
            // 节点没有颜色或颜色无效，需要分配默认颜色
            let nodeType = '未知';

            // --- 修正：从 originalData 中获取类型 ---
            // 1. 首先检查 node.originalData.type (这是最可能的地方)
            if (node.originalData && node.originalData.type && typeof node.originalData.type === 'string') {
                nodeType = node.originalData.type.trim();
            }
            // 2. 如果上面没有，检查 node.originalData.properties.type
            else if (node.originalData && node.originalData.properties && node.originalData.properties.type && typeof node.originalData.properties.type === 'string') {
                nodeType = node.originalData.properties.type.trim();
            }
            // 3. 如果还没有，尝试从 node.originalData.id 推断（不太可能，但以防万一）
            //    或者检查 node.title (如果存在且原始数据中有相关信息)
            else if (node.originalData && node.originalData.id) {
                 // 可以尝试从 ID 推断，但这通常不靠谱
                 // 或者如果 node.title 存在且格式类似 "类型 (ID)"，可以解析
                 if (node.title && typeof node.title === 'string') {
                     const titleMatch = node.title.match(/^\s*([^(\s]+)\s*\(/);
                     if (titleMatch && titleMatch[1]) {
                         nodeType = titleMatch[1].trim();
                     }
                 }
            }
            // 4. 最后回退到检查顶层 node.type (虽然根据新数据结构不太可能有)
            else if (node.type && typeof node.type === 'string') {
                 nodeType = node.type.trim();
            }


            // 1. 首先查找预定义的颜色映射
            let mappedColor = NODE_COLOR_MAP[nodeType];
            if (!mappedColor) {
                // 2. 如果没有预定义颜色，根据类型生成稳定颜色
                mappedColor = generateColorFromString(nodeType);
            }
            // 应用颜色
            node.color = mappedColor; // Vis.js 接受字符串颜色
            console.log(`为节点 ${node.id} (${nodeType}) 应用颜色: ${mappedColor} (来自 originalData.type: ${node.originalData?.type})`);
        } else {
            console.log(`节点 ${node.id} 已有颜色:`, node.color);
        }

        // 确保其他必要属性存在 (如果需要的话可以设置默认值)
        if (node.size === undefined || node.size === null) node.size = 25; // 默认大小

        return node;
    }).filter(node => node !== null); // 过滤掉无效节点

    // --- 处理边颜色 (这部分保持不变，因为你提到边颜色已经生效) ---
    const processedEdges = rawEdges.map((edge, index) => {
        // 确保边有必要的字段
        if (!edge || edge.from === undefined || edge.to === undefined) {
            console.warn(`边 ${index} 缺少 from 或 to，跳过`);
            return null;
        }

        // 确保边有 ID
        if (edge.id === undefined || edge.id === null) {
             edge.id = `edge_${edge.from}_${edge.to}_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
        }

        // 确保边有 label (可选，如果没有则使用 type 或空字符串)
        if (edge.label === undefined || edge.label === null) {
            edge.label = (edge.type && typeof edge.type === 'string') ? edge.type : ''; // 如果有 type 字段，用它作为 label
        }

        // --- 颜色处理逻辑 ---
        // 检查边是否已有颜色（字符串或对象）
        let hasValidEdgeColor = false;
        if (edge.color) {
            if (typeof edge.color === 'string' && edge.color.startsWith('#')) {
                hasValidEdgeColor = true;
            } else if (typeof edge.color === 'object') {
                // 检查 color 对象中 color 字段
                if (edge.color.color && typeof edge.color.color === 'string' && edge.color.color.startsWith('#')) {
                     hasValidEdgeColor = true;
                }
                // 或者 color.color.color ... (处理嵌套，虽然不太可能)
            }
        }

        if (!hasValidEdgeColor) {
            // 边没有颜色或颜色无效，需要分配默认颜色
            // 假设边数据中可能有一个 'type' 或 'label' 字段来确定关系类型
            let edgeType = '未知关系';
            if (edge.type && typeof edge.type === 'string') {
                edgeType = edge.type.trim();
            } else if (edge.label && typeof edge.label === 'string') {
                edgeType = edge.label.trim();
            } else if (edge.originalData && edge.originalData.type) { // 检查 originalData.type
                 edgeType = (typeof edge.originalData.type === 'string') ? edge.originalData.type.trim() : String(edge.originalData.type);
            }
            // 如果边对象中没有 color，或者 color 是空对象/无效值，则应用默认颜色
            // 1. 首先查找预定义的颜色映射
            let mappedColor = EDGE_COLOR_MAP[edgeType];
            if (!mappedColor) {
                // 2. 如果没有预定义颜色，根据类型生成稳定颜色
                mappedColor = generateColorFromString(edgeType);
            }
            // 应用颜色 (Vis.js 边颜色结构通常是 { color: '#...' } )
            // 确保 edge.color 是一个对象并设置 color 字段
            if (!edge.color || typeof edge.color !== 'object') {
                edge.color = {};
            }
            edge.color.color = mappedColor;
            console.log(`为边 ${edge.id} (${edgeType}) 应用颜色: ${mappedColor}`);
        } else {
            console.log(`边 ${edge.id} 已有颜色:`, edge.color);
        }

        // 确保其他必要属性存在
        if (edge.width === undefined || edge.width === null) edge.width = 2; // 默认宽度
        if (!edge.arrows) edge.arrows = 'to'; // 默认箭头

        return edge;
    }).filter(edge => edge !== null); // 过滤掉无效边

    console.log('转换并着色后的 Vis 数据:', { nodes: processedNodes, edges: processedEdges });

    return {
        nodes: processedNodes,
        edges: processedEdges
    };
}
    // 根据节点类型获取颜色
    function getNodeColorByType(type) {
        const colorMap = {
            '人物': '#FF6B6B',
            '地点': '#4ECDC4',
            '事件': '#45B7D1',
            '物件': '#96CEB4',
            '时间': '#FFEAA7',
            '国家': '#DDA0DD',
            '民族': '#98D8C8',
            '制度': '#F7DC6F',
            '成就': '#BB8FCE',
            '聚合概念': '#F8C471'
        };
        return colorMap[type] || '#95A5A6';
    }

    // 根据节点类型获取大小
    function getNodeSizeByType(type) {
        const sizeMap = {
            '人物': 30,
            '地点': 28,
            '事件': 26,
            '物件': 24,
            '时间': 22,
            '国家': 32,
            '民族': 25,
            '制度': 27,
            '成就': 29,
            '聚合概念': 35
        };
        return sizeMap[type] || 25;
    }

    // 删除图谱功能
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
                // 清空画布
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

    // 刷新图谱（重新从后端加载）
    async function refreshGraph() {
        if (!currentCacheKey) {
            alert('未加载图谱，无法刷新');
            return;
        }
        await loadGraphData(currentCacheKey);
    }

    // 清空图谱功能（仅前端清空）
    function clearGraph() {
        if (confirm('确定要清空当前画布吗？此操作不会影响已保存的图谱。')) {
            if (nodes && edges) {
                nodes.clear();
                edges.clear();
                console.log('图谱已清空（前端）');
            }
            state.highlightedNode = null; // 清空高亮状态
        }
    }

    // 导出图谱功能（前端导出 JSON）
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

    // 切换物理引擎
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

        // 通知浮动面板（如果有的话）
        window.dispatchEvent(new CustomEvent('physicsStatusUpdated', {
            detail: { enabled: !current }
        }));

        console.log(`物理引擎已${!current ? '开启' : '关闭'}`);
    }

    // 初始化图
    function initGraph(graphData, physicsEnabled = true) {
        try {
            // 转换原始格式为 Vis Network 格式
            const visFormat = convertOriginalToVisFormat(graphData);

            console.log('Vis Network 格式数据:', visFormat); // 调试信息

            // 处理重复的节点ID
            const uniqueNodes = [];
            const nodeIdSet = new Set();

            if (visFormat.nodes) {
                visFormat.nodes.forEach(node => {
                    let nodeId = node.id;
                    let counter = 0;
                    while (nodeIdSet.has(nodeId)) {
                        nodeId = `${node.id}_${++counter}`;
                        console.warn(`节点ID冲突，重命名: ${node.id} -> ${nodeId}`);
                    }
                    nodeIdSet.add(nodeId);
                    uniqueNodes.push({...node, id: nodeId});
                });
            }

            // 处理重复的边ID
            const uniqueEdges = [];
            const edgeIdSet = new Set();

            if (visFormat.edges) {
                visFormat.edges.forEach(edge => {
                    let edgeId = edge.id || `edge_${edge.from}_${edge.to}`;
                    let counter = 0;
                    while (edgeIdSet.has(edgeId)) {
                        edgeId = `${edge.id || `edge_${edge.from}_${edge.to}`}_${++counter}`;
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
                    enabled: physicsEnabled,
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
                        size: 12,           // 字体大小
                        color: '#CCCCCC',   // 字体颜色（更浅一些）
                        face: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Oxygen, Ubuntu, Cantarell, "Open Sans", "Helvetica Neue", sans-serif',
                        strokeWidth: 0,     // 去掉字体描边
                        strokeColor: '#1e1e1e' // 描边颜色
                    },
                    // 可选：调整边的颜色和宽度
                    color: {
                        color: '#666666',   // 边的颜色
                        highlight: '#999999', // 高亮时的颜色
                        hover: '#AAAAAA'    // 悬停时的颜色
                    },
                    width: 1.5            // 边的宽度
                }
            };

            container = document.getElementById('mynetwork');
            if (container) {
                // 确保容器在创建 Network 前就设置好大小
                container.style.width = '100vw';
                container.style.height = '100vh';
                container.style.margin = '0';
                container.style.padding = '0';
                container.style.overflow = 'hidden';

                // 清空容器
                container.innerHTML = '';

                // 创建 Network
                network = new vis.Network(container, data, options);

                // 可选：在 Network 创建后强制设置大小
                setTimeout(() => {
                    if (network) {
                        container.style.width = '100vw';
                        container.style.height = '100vh';
                        network.redraw();
                    }
                }, 50);

                bindNetworkEvents();
                bindGlobalEvents();

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
                errorContainer.innerHTML = '<div style="text-align: center; padding: 50px; color: red; background: #1e1e1e;">初始化图失败: ' + error.message + '</div>';
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

        network.on("click", handleClick);
        network.on("doubleClick", handleDoubleClick);
        network.on("oncontext", handleContextMenu);
        network.on("hold", handleHold);
        network.on("release", handleRelease);
        network.on("hoverNode", params => { state.hoveredNode = params.node; });
        network.on("blurNode", () => { state.hoveredNode = null; });
        network.on("hoverEdge", params => { state.hoveredEdge = params.edge; });
        network.on("blurEdge", () => { state.hoveredEdge = null; });
        network.on("selectNode", params => {
            state.selectedNode = params.nodes.length > 0 ? params.nodes[0] : null;
        });
    }

    // 点击事件处理
        // 点击事件处理
    function handleClick(params) {
        logDebug(`🖱️ 点击事件 - 节点: ${params.nodes.length}, 边: ${params.edges.length}`);
        state.selectedNode = params.nodes.length > 0 ? params.nodes[0] : null;

        // --- 新增逻辑开始 ---
        if (params.nodes.length > 0) {
            // 点击了节点
            const clickedNodeId = params.nodes[0];
            if (state.highlightedNode === clickedNodeId) {
                // 再次点击已高亮的节点，取消高亮
                resetHighlight();
            } else {
                // 点击了新节点，高亮它
                highlightNodeAndConnections(clickedNodeId);
            }
        } else if (params.edges.length === 0 && state.highlightedNode) {
            // 点击了画布空白处（且当前有高亮节点），取消高亮
             // 注意：需要区分点击空白和点击边。如果点击边，通常不取消高亮。
             // 这里的条件是点击了节点或边之外的地方
            resetHighlight();
        }
        // --- 新增逻辑结束 ---

        // 处理上下文菜单隐藏
        if (state.isMenuVisible && params.nodes.length === 0 && params.edges.length === 0) {
            hideAllContextMenus();
        }

        // 处理"连接到现有节点"模式 (这部分保持不变)
        if (state.connectingToExisting && params.nodes.length > 0 && state.connectionSourceNode) {
            const targetNodeId = params.nodes[0];
            if (targetNodeId !== state.connectionSourceNode) {
                const newEdgeId = `edge_${state.connectionSourceNode}_${targetNodeId}_${Date.now()}`;
                edges.add({
                    id: newEdgeId,
                    from: state.connectionSourceNode,
                    to: targetNodeId
                });
                logDebug(`连接节点: ${state.connectionSourceNode} -> ${targetNodeId}`);
            }
            cancelMode(); // 这个函数里会调用 hideAllContextMenus()
        }
    }

    // 双击事件处理
    function handleDoubleClick(params) {
        logDebug(`👆 双击事件 - 节点: ${params.nodes.length}, 边: ${params.edges.length}`);

        if (params.nodes.length > 0) {
            state.contextMenuNode = params.nodes[0];
            showEditNodeLabelInput();
        } else if (params.edges.length > 0) {
            state.contextMenuEdge = params.edges[0];
            showEditEdgeLabelInput();
        }
    }

    // 右键菜单事件处理
    function handleContextMenu(params) {
        params.event.preventDefault();
        showContextMenuAtPosition(params);
    }

    // 长按事件处理
    function handleHold(params) {
        logDebug(`✋ 长按事件 - 节点: ${params.nodes.length}, 边: ${params.edges.length}`);

        if (state.menuShowTimer) {
            clearTimeout(state.menuShowTimer);
        }

        state.menuScheduledToShow = true;

        state.menuShowTimer = setTimeout(() => {
            showContextMenuAtPosition(params);
            state.menuScheduledToShow = false;
        }, 100);
    }

    function handleRelease(params) {
        logDebug(`放开 release事件`);
    }

    // 统一的上下文菜单显示函数
    function showContextMenuAtPosition(params) {
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
            if (!clickedInsideMenu && state.isMenuVisible) {
                hideAllContextMenus();
            }
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

        if (state.contextMenuNode) {
            const node = nodes.get(state.contextMenuNode);
            const ul = menu.querySelector('ul');
            const titleElement = document.createElement('li');
            titleElement.className = 'menu-title';
            titleElement.textContent = `节点: ${node.label || '未命名'}`;
            titleElement.style.cssText = 'font-weight: bold; background: #555; font-size: 15px; pointer-events: none; padding: 8px 12px;';
            ul.insertBefore(titleElement, ul.firstChild);
        }

        menu.style.display = 'block';
        positionContextMenu(menu, domPos);
        state.isMenuVisible = true;
    }

    function showEdgeContextMenu(domPos) {
        hideAllContextMenus();
        const menu = document.getElementById('edgeContextMenu');

        if (state.contextMenuEdge) {
            const edge = edges.get(state.contextMenuEdge);
            const fromNode = nodes.get(edge.from);
            const toNode = nodes.get(edge.to);
            const ul = menu.querySelector('ul');
            const titleElement = document.createElement('li');
            titleElement.className = 'menu-title';
            titleElement.textContent = `连接: ${fromNode.label || fromNode.id} → ${toNode.label || toNode.id}`;
            titleElement.style.cssText = 'font-weight: bold; background: #f0f0f0; pointer-events: none; padding: 8px 12px;';
            ul.insertBefore(titleElement, ul.firstChild);
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

        if (state.contextMenuNode) {
            const node = nodes.get(state.contextMenuNode);
            const titleDiv = menu.querySelector('div:first-child');
            if (titleDiv) {
                titleDiv.textContent = `从节点 "${node.label || node.id}" 创建新节点`;
                titleDiv.style.fontWeight = 'bold';
            }
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

    function positionContextMenu(menu, domPos) {
        let x = domPos.x;
        let y = domPos.y;
        const offset = 10;

        const rect = menu.getBoundingClientRect();
        if (x + rect.width > window.innerWidth) {
            x = window.innerWidth - rect.width - offset;
        }
        if (y + rect.height > window.innerHeight) {
            y = window.innerHeight - rect.height - offset;
        }
        if (x < offset) x = offset;
        if (y < offset) y = offset;

        menu.style.left = x + 'px';
        menu.style.top = y + 'px';
    }

    function hideAllContextMenus() {
        const menus = document.querySelectorAll('.context-menu, .input-menu');
        menus.forEach(menu => {
            menu.style.display = 'none';
            const titleElements = menu.querySelectorAll('.menu-title');
            titleElements.forEach(el => el.remove());
        });

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
            const pos = network.canvasToDOM({x: 0, y: 0}); // 默认位置，实际应由点击位置决定
            nodes.add({
                id: newNodeId,
                label: label,
                x: pos.x,
                y: pos.y
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

    function cancelMode() {
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

    function logDebug(message) {
        const debugInfo = document.getElementById('debug-info');
        if (debugInfo) {
            debugInfo.textContent = message;
        }
    }
        /**
     * 突出显示指定节点及其直接连接的节点和边，淡化其他元素。
     * @param {string|number} nodeId - 要突出显示的节点ID。
     */
    function highlightNodeAndConnections(nodeId) {
        if (!nodes || !edges || !network) return;

        state.highlightedNode = nodeId; // 设置状态

        const allNodes = nodes.get({ returnType: "Object" }); // 以对象形式获取，方便查找
        const allEdges = edges.get({ returnType: "Object" });

        const connectedNodeIds = new Set(); // 存储与高亮节点直接相连的节点ID
        const connectedEdgeIds = new Set(); // 存储与高亮节点直接相连的边ID

        // 找出连接到 nodeId 的边和节点
        for (const edgeId in allEdges) {
            const edge = allEdges[edgeId];
            if (edge.from === nodeId || edge.to === nodeId) {
                connectedEdgeIds.add(edgeId);
                connectedNodeIds.add(edge.from);
                connectedNodeIds.add(edge.to);
            }
        }

        // 准备更新节点和边的数据
        const nodesToUpdate = [];
        const edgesToUpdate = [];

        // 更新节点透明度
        for (const id in allNodes) {
            const node = allNodes[id];
            const isHighlighted = (id === nodeId);
            const isConnected = connectedNodeIds.has(id);

            let newColor;
            if (isHighlighted || isConnected) {
                // 保持或恢复原始颜色（或确保不透明）
                // 如果原始节点没有自定义 color 对象，直接使用 color 字符串或默认值
                // 这里假设 color 是字符串或简单对象，为了简化，我们直接保留它
                // 更精确的做法是保存原始颜色，但这里先尝试直接使用
                // 如果之前被淡化过，需要恢复
                if (node._originalColor) {
                     // 如果之前保存过原始颜色，则恢复
                     newColor = node._originalColor;
                     delete node._originalColor; // 恢复后删除临时属性
                } else {
                     // 如果没有被淡化过，就用当前颜色
                     newColor = node.color;
                }
            } else {
                // 淡化不相关的节点
                // 保存原始颜色（如果还没保存）
                if (!node._originalColor) {
                    node._originalColor = JSON.parse(JSON.stringify(node.color)); // 深拷贝
                }
                // 应用半透明效果
                newColor = applyTransparencyToColor(node.color, 0.2);
            }
            nodesToUpdate.push({ id: id, color: newColor });
        }

        // 更新边透明度
        for (const id in allEdges) {
            const edge = allEdges[id];
            const isHighlighted = (edge.from === nodeId || edge.to === nodeId); // 边本身连接到高亮节点
            const isConnectedEdge = connectedEdgeIds.has(id); // 是与高亮节点直接相连的边

            let newColor;
            if (isConnectedEdge) { // 只有直接相连的边才保持或恢复
                // 恢复原始颜色
                if (edge._originalColor) {
                     newColor = edge._originalColor;
                     delete edge._originalColor; // 恢复后删除临时属性
                } else {
                     newColor = edge.color; // 保持当前颜色
                }
            } else {
                // 淡化不相关的边
                if (!edge._originalColor) {
                    edge._originalColor = JSON.parse(JSON.stringify(edge.color)); // 深拷贝
                }
                newColor = applyTransparencyToColor(edge.color, 0.1); // 边可以更淡一些
            }
            edgesToUpdate.push({ id: id, color: newColor });
        }

        // 应用更新
        if (nodesToUpdate.length > 0) nodes.update(nodesToUpdate);
        if (edgesToUpdate.length > 0) edges.update(edgesToUpdate);

        logDebug(`突出显示节点: ${nodeId} 及其直接连接`);
    }

    /**
     * 将颜色（字符串或对象）应用透明度。
     * @param {string|Object} color - Vis.js 颜色定义。
     * @param {number} opacity - 透明度 (0-1)。
     * @returns {string|Object} 应用了透明度的新颜色。
     */
    function applyTransparencyToColor(color, opacity) {
        if (typeof color === 'string' && color.startsWith('#')) {
            // 处理十六进制颜色
            return hexToRGBA(color, opacity);
        } else if (typeof color === 'object') {
            // 处理颜色对象 {color: ..., border: ..., highlight: ...}
            const newColorObject = {};
            for (const key in color) {
                if (color.hasOwnProperty(key)) {
                    // 通常 color.color, color.border, color.highlight 都是颜色字符串
                    if (typeof color[key] === 'string' && (color[key].startsWith('#') || color[key].startsWith('rgb'))) {
                        if (color[key].startsWith('#')) {
                             newColorObject[key] = hexToRGBA(color[key], opacity);
                        } else if (color[key].startsWith('rgb')) {
                            // 简单处理 rgb(...)
                            const match = color[key].match(/rgba?\((\d+),\s*(\d+),\s*(\d+)(?:,\s*([\d.]+))?\)/);
                            if (match) {
                                const r = parseInt(match[1], 10);
                                const g = parseInt(match[2], 10);
                                const b = parseInt(match[3], 10);
                                newColorObject[key] = `rgba(${r}, ${g}, ${b}, ${opacity})`;
                            } else {
                                newColorObject[key] = color[key]; // 无法解析则保持原样
                            }
                        }
                    } else {
                        newColorObject[key] = color[key]; // 非颜色字符串保持原样
                    }
                }
            }
            // 特别处理 color.color，因为 Vis.js 边的主要颜色在这里
            if (color.color && typeof color.color === 'string') {
                 if(color.color.startsWith('#')) {
                     newColorObject.color = hexToRGBA(color.color, opacity);
                 } else if (color.color.startsWith('rgb')) {
                      const match = color.color.match(/rgba?\((\d+),\s*(\d+),\s*(\d+)(?:,\s*([\d.]+))?\)/);
                            if (match) {
                                const r = parseInt(match[1], 10);
                                const g = parseInt(match[2], 10);
                                const b = parseInt(match[3], 10);
                                newColorObject.color = `rgba(${r}, ${g}, ${b}, ${opacity})`;
                            } else {
                                newColorObject.color = color.color;
                            }
                 }
            }
            return newColorObject;
        }
        // 如果不是预期的颜色格式，返回原值或一个默认的半透明色
        console.warn('无法应用透明度到颜色:', color);
        return `rgba(200, 200, 200, ${opacity})`;
    }

    /**
     * 将十六进制颜色转换为 RGBA 字符串。
     * @param {string} hex - 十六进制颜色 (#RRGGBB 或 #RGB)。
     * @param {number} opacity - 透明度 (0-1)。
     * @returns {string} RGBA 颜色字符串。
     */
    function hexToRGBA(hex, opacity) {
        let r = 0, g = 0, b = 0;
        // 3 digits
        if (hex.length === 4) {
          r = "0x" + hex[1] + hex[1];
          g = "0x" + hex[2] + hex[2];
          b = "0x" + hex[3] + hex[3];
        // 6 digits
        } else if (hex.length === 7) {
          r = "0x" + hex[1] + hex[2];
          g = "0x" + hex[3] + hex[4];
          b = "0x" + hex[5] + hex[6];
        }
        return `rgba(${+r}, ${+g}, ${+b}, ${opacity})`;
    }


    /**
     * 重置所有节点和边的颜色到原始状态。
     */
    function resetHighlight() {
        if (!nodes || !edges || !state.highlightedNode) return;

        state.highlightedNode = null; // 清除状态

        const allNodes = nodes.get();
        const allEdges = edges.get();

        const nodesToUpdate = [];
        const edgesToUpdate = [];

        // 恢复节点颜色
        allNodes.forEach(node => {
            if (node._originalColor !== undefined) {
                nodesToUpdate.push({ id: node.id, color: node._originalColor });
                delete node._originalColor; // 清理临时属性
            }
        });

        // 恢复边颜色
        allEdges.forEach(edge => {
            if (edge._originalColor !== undefined) {
                // 特别注意 Vis.js 边的颜色结构 { color: ... }
                edgesToUpdate.push({ id: edge.id, color: edge._originalColor });
                delete edge._originalColor; // 清理临时属性
            }
        });

        // 应用更新
        if (nodesToUpdate.length > 0) nodes.update(nodesToUpdate);
        if (edgesToUpdate.length > 0) edges.update(edgesToUpdate);

        logDebug(`重置突出显示`);
    }


    // 公共接口
    return {
        init,
        cancelMode,
        initWithGraphData: function(apiResult, cacheKey) {
            console.log('initWithGraphData 接收到的数据:', apiResult); // 调试信息
            console.log('cacheKey:', cacheKey); // 调试信息

            // 检查数据结构
            if (!apiResult || !apiResult.data) {
                throw new Error('无效的图谱数据格式：缺少 data 字段');
            }

            const graphData = apiResult.data.data; // 注意这里的嵌套
            const physicsEnabled = apiResult.data.physics;

            console.log('graphData 结构:', graphData); // 调试信息

            if (!graphData) {
                throw new Error('无效的图谱数据格式：缺少实际数据');
            }

            // 检查 nodes 和 edges 是否存在
            if (!Array.isArray(graphData.nodes)) {
                console.warn('nodes 不是数组，使用空数组');
                graphData.nodes = [];
            }

            if (!Array.isArray(graphData.edges)) {
                console.warn('edges 不是数组，使用空数组');
                graphData.edges = [];
            }

            currentCacheKey = cacheKey; // 保存当前 cacheKey
            console.log('currentCacheKey 已设置为:', currentCacheKey); // 调试信息
            initGraph(graphData, physicsEnabled);
        },
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
        deleteGraph,
        refreshGraph,
        clearGraph,
        exportGraph,
        togglePhysics,
        get network() { return network; },
        get nodes() { return nodes; },
        get edges() { return edges; },
        get cacheKey() { return currentCacheKey; }
    };
})();

// 页面加载完成
document.addEventListener('DOMContentLoaded', function() {
    GraphEditor.init();

    // 从 URL 获取 cache_key
    const urlParams = new URLSearchParams(window.location.search);
    const cacheKey = urlParams.get('cache_key');

    if (cacheKey) {
        loadGraphData(cacheKey).then(() => {
            console.log('图谱数据加载完成');
            // 绑定按钮事件
            bindButtonEvents();
        }).catch(error => {
            console.error('图谱数据加载失败:', error);
        });
    } else {
        // 可选：显示欢迎界面或空画布
        const container = document.getElementById('mynetwork');
        if (container) {
            container.innerHTML = `<div style="text-align: center; padding: 50px; color: #aaa; font-family: sans-serif;">
                请在 URL 中提供 cache_key 参数加载图谱，例如：<br>
                ?cache_key=your_cache_key_here
            </div>`;
        }
    }
});

// 绑定按钮事件
function bindButtonEvents() {
    // 使用 setTimeout 确保DOM完全加载
    setTimeout(() => {
        const buttonConfigs = [
            {id: 'save-graph-btn', handler: GraphEditor.saveGraph},
            {id: 'delete-graph-btn', handler: GraphEditor.deleteGraph},
            {id: 'refresh-graph-btn', handler: GraphEditor.refreshGraph},
            {id: 'export-graph-btn', handler: GraphEditor.exportGraph},
            {id: 'clear-graph-btn', handler: GraphEditor.clearGraph},
            {id: 'toggle-physics-btn', handler: GraphEditor.togglePhysics}
        ];

        buttonConfigs.forEach(btnConfig => {
            const element = document.getElementById(btnConfig.id);
            if (element) {
                // 移除已存在的事件监听器（防止重复绑定）
                const newElement = element.cloneNode(true);
                element.parentNode.replaceChild(newElement, element);

                // 添加新的事件监听器
                newElement.addEventListener('click', function(e) {
                    e.preventDefault();
                    try {
                        btnConfig.handler.call(GraphEditor);
                    } catch (error) {
                        console.error(`按钮 ${btnConfig.id} 点击处理失败:`, error);
                    }
                });
            } else {
                console.warn(`未找到按钮元素: ${btnConfig.id}`);
            }
        });

        // 单独处理 physicsToggle
        const physicsToggle = document.getElementById('physicsToggle');
        if (physicsToggle) {
            const newToggle = physicsToggle.cloneNode(true);
            physicsToggle.parentNode.replaceChild(newToggle, physicsToggle);

            newToggle.addEventListener('change', function(e) {
                try {
                    GraphEditor.togglePhysics.call(GraphEditor);
                } catch (error) {
                    console.error('physicsToggle 处理失败:', error);
                }
            });
        }
    }, 100);
}

// 加载图谱数据（适配你的后端接口）
async function loadGraphData(cacheKey) {
    try {
        // 显示 loading
        const container = document.getElementById('mynetwork');
        if (container) {
            // 设置容器样式
            container.style.width = '100vw';
            container.style.height = '100vh';
            container.style.margin = '0';
            container.style.padding = '0';
            container.style.overflow = 'hidden';

            container.innerHTML = `<div style="text-align: center; padding: 50px; color: #888;">
                🔄 正在加载图谱数据...
            </div>`;
        }

        // 调试：打印请求 URL
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

        // 初始化 GraphEditor（适配后端返回结构）
        GraphEditor.initWithGraphData(result, cacheKey);



    } catch (error) {
        console.error('加载图谱失败:', error);
        const container = document.getElementById('mynetwork');
        if (container) {
            container.innerHTML = `<div style="text-align: center; padding: 50px; color: #ff6b6b; background: #1e1e1e;">
                ❌ 加载图谱失败: ${error.message}
            </div>`;
        }
        throw error; // 重新抛出错误，让调用者知道
    }
}