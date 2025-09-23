// graph_ui.js - 用户界面、交互和上下文菜单管理

class GraphUI {
    constructor(graphCore) {
        this.graphCore = graphCore; // 注入核心模块
        this._state = {
            contextMenuNode: null,
            contextMenuEdge: null,
            addingNode: false,
            connectingToExisting: false,
            connectionSourceNode: null,
            isConnectingNewNode: false,
            menuShowTimer: null,
            isMenuVisible: false,
            menuScheduledToShow: false,
        };

        this.init();

        window.addEventListener('graphInitialized', (event) => {
        const network = event.detail.network;
        if (network) {
            network.on("click", (params) => this.handleClick(params));
            network.on("doubleClick", (params) => this.handleDoubleClick(params));
            network.on("oncontext", (params) => this.handleContextMenu(params));
            network.on("hold", (params) => this.handleHold(params));
            network.on("release", (params) => this.handleRelease(params));
            console.log('网络图事件绑定成功');
        }
    });
    }

    init() {
        this.bindGlobalEvents();
        this.bindButtonEvents();
        this.bindNetworkVisualEvents();
         this.bindContextMenuEvents();
    }
    bindNetworkVisualEvents() {
        window.addEventListener('graphInitialized', (event) => {
            const network = event.detail.network;
            if (network) {
                // 悬停高亮
                network.on("hoverNode", (params) => {
                    if (!this.graphCore.state.highlightedNode) { // 只有在未手动高亮时才启用悬停
                        this.highlightNodeAndConnections(params.node);
                    }
                });

                network.on("blurNode", () => {
                    if (this.graphCore.state.highlightedNode) {
                        this.resetHighlight();
                    }
                });
            }
        });
    }
    // --- 全局事件绑定 ---
    bindGlobalEvents() {
        document.addEventListener('click', (e) => {
            const menus = document.querySelectorAll('.context-menu, .input-menu');
            let clickedInsideMenu = false;
            menus.forEach(menu => {
                if (menu.contains(e.target)) {
                    clickedInsideMenu = true;
                }
            });
            if (!clickedInsideMenu && this._state.isMenuVisible) {
                this.hideAllContextMenus();
            }
        });

        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape') {
                this.hideAllContextMenus();
                this.cancelMode();
            }
        });
    }
    // graph_ui.js - 在 GraphUI 类中添加
    // --- 高亮功能（移到 GraphUI） ---
    highlightNodeAndConnections(nodeId) {
        if (!this.graphCore.network) return;

        // 获取所有节点和边
        const allNodes = this.graphCore.nodes.get({ returnType: "Object" });
        const allEdges = this.graphCore.edges.get({ returnType: "Object" });

        // 获取直接连接的节点和边
        const connectedEdges = this.graphCore.network.getConnectedEdges(nodeId);
        const connectedNodes = new Set();
        connectedEdges.forEach(edgeId => {
            const edge = allEdges[edgeId];
            if (edge.from === nodeId) connectedNodes.add(edge.to);
            if (edge.to === nodeId) connectedNodes.add(edge.from);
        });
        connectedNodes.add(nodeId); // 包括自己

        // 更新节点透明度
        const updatedNodes = [];
        for (const id in allNodes) {
            const node = allNodes[id];
            updatedNodes.push({
                id: id,
                opacity: connectedNodes.has(id) ? 1.0 : 0.2
            });
        }

        // 更新边透明度
        const updatedEdges = [];
        for (const id in allEdges) {
            const edge = allEdges[id];
            const isRelevant = edge.from === nodeId || edge.to === nodeId;
            updatedEdges.push({
                id: id,
                opacity: isRelevant ? 1.0 : 0.1
            });
        }

        // 批量更新视觉状态（不修改原始数据）
        this.graphCore.nodes.update(updatedNodes);
        this.graphCore.edges.update(updatedEdges);

        // 更新状态
        this.graphCore.state.highlightedNode = nodeId;

        console.log(`UI: 高亮节点 ${nodeId} 及其 ${connectedNodes.size - 1} 个邻居`);
    }

    resetHighlight() {
        if (!this.graphCore.state.highlightedNode) return;

        // 恢复所有节点和边为完全不透明
        const allNodeIds = this.graphCore.nodes.getIds();
        const allEdgeIds = this.graphCore.edges.getIds();

        const resetNodes = allNodeIds.map(id => ({ id, opacity: 1.0 }));
        const resetEdges = allEdgeIds.map(id => ({ id, opacity: 1.0 }));

        this.graphCore.nodes.update(resetNodes);
        this.graphCore.edges.update(resetEdges);

        this.graphCore.state.highlightedNode = null;

        console.log("UI: 已重置高亮状态");
    }
       updateMetadataDisplay() {
    const metadataContainer = document.getElementById('metadata-info');
    if (!metadataContainer) {
        console.warn('未找到 #metadata-info 元素');
        return;
    }

    // 获取节点和边数量
    let nodeCount = 0, edgeCount = 0;
    try {
        if (this.graphCore && this.graphCore.nodes && this.graphCore.edges) {
            nodeCount = this.graphCore.nodes.get().length;
            edgeCount = this.graphCore.edges.get().length;
        }
    } catch (e) {
        console.error('获取图谱数据失败:', e);
    }

    // 获取 metadata
        const metadata = this.graphCore.metadata || {};

        console.log('🔍 当前 metadata 内容:', metadata);
        console.log('🔍 metadata keys:', Object.keys(metadata));

        // ✅ 字段名映射表（英文 key → 中文显示）
        const fieldLabels = {
            novel_name: '📖 小说名称',
            chapter_name: '📑 章节名称',
            model_name: '🤖 模型名称',
            use_local: '💾 使用本地模型',
            num_ctx: '🧠 上下文长度',
            chunk_size: '🧩 分块大小',
            chunk_overlap: '🔗 分块重叠',
            content_size: '📏 内容长度',
            schema_name: '📋 图谱模式',
            cache_version: '🔢 缓存版本',
            created_at: '📅 创建时间',
            saved_at: '💾 保存时间',
            // 可以继续添加其他字段
        };

        // ✅ 新增：跳过列表 —— 这些字段即使存在也不显示
        const skipFields = [
            'cache_version',   // 不显示缓存版本
            'schema_display',   // 不显示分块重叠
            'use_local',       // 不显示是否本地模型
            'saved_at'
            // 你可以按需添加更多字段
        ];

        // 生成 metadata 字段的 HTML
        let metadataHtml = '';

        // 按你希望的顺序显示字段（可选）
        const displayOrder = [
            'novel_name',
            'chapter_name',
            'model_name',
            'use_local',
            'schema_name',
            'num_ctx',
            'chunk_size',
            'chunk_overlap',
            'content_size',
            'saved_at'
        ];

        // 遍历指定顺序的字段
        for (const key of displayOrder) {
            // ✅ 跳过 skipFields 中的字段
            if (skipFields.includes(key)) continue;
            if (!(key in metadata)) continue;
            const value = metadata[key];
            if (value === null || value === undefined) continue;

            const label = fieldLabels[key] || `🔹 ${this.capitalizeFirstLetter(key)}`;
            let displayValue = this.formatMetadataValue(value, key);

            metadataHtml += `
                <p><strong>${this.escapeHtml(label)}：</strong> ${this.escapeHtml(displayValue)}</p>
            `;
        }

        // 如果还有未在 displayOrder 中的字段，也显示出来（兜底）
        for (const [key, value] of Object.entries(metadata)) {
            if (displayOrder.includes(key)) continue; // 已在顺序中处理过
            if (skipFields.includes(key)) continue;   // ✅ 跳过 skipFields 中的字段
            if (value === null || value === undefined) continue;

            const label = fieldLabels[key] || `🔹 ${this.capitalizeFirstLetter(key)}`;
            let displayValue = this.formatMetadataValue(value, key);

            metadataHtml += `
                <p><strong>${this.escapeHtml(label)}：</strong> ${this.escapeHtml(displayValue)}</p>
            `;
        }

        // 如果 metadata 为空
        if (metadataHtml === '') {
            metadataHtml = '<p><em>暂无元数据信息</em></p>';
        }

        // 固定显示节点数、边数、加载时间
        const footerHtml = `
            <p><strong>📊 节点数量：</strong> ${nodeCount}</p>
            <p><strong>🔗 边数量：</strong> ${edgeCount}</p>
            <p><strong>🕒 最后加载：</strong> ${new Date().toLocaleString()}</p>
        `;

        // 更新 DOM
        metadataContainer.innerHTML = `<h5>📋 图谱信息</h5>` + metadataHtml + footerHtml;

        console.log('✅ 图谱元数据已更新:', { metadata, nodeCount, edgeCount });
    }
    // 在 GraphUI 类内添加
    escapeHtml(text) {
        if (typeof text !== 'string') {
            return String(text);
        }
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }
    capitalizeFirstLetter(string) {
        if (typeof string !== 'string') return String(string);
        return string.charAt(0).toUpperCase() + string.slice(1).replace(/_/g, ' ');
    }
    formatMetadataValue(value, key = '') {
        // 处理布尔值
        if (typeof value === 'boolean') {
            return value ? '是' : '否';
        }
        // 处理数字
        else if (typeof value === 'number') {
            return value.toLocaleString(); // 1000 → "1,000"
        }
        // 处理 ISO 日期字符串
        else if (typeof value === 'string' && (key.endsWith('_at') || key.includes('time') || /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}/.test(value))) {
            try {
                const date = new Date(value);
                if (!isNaN(date.getTime())) {
                    return date.toLocaleString('zh-CN'); // "2025/9/15 11:37:46"
                }
            } catch (e) {
                // 如果解析失败，原样返回
            }
        }
        // 处理普通字符串
        else if (typeof value === 'string') {
            return value.trim() === '' ? '(空)' : value;
        }
        // 处理数组或对象
        else if (Array.isArray(value) || (typeof value === 'object' && value !== null)) {
            try {
                return JSON.stringify(value, null, 2);
            } catch (e) {
                return String(value);
            }
        }
        // 其他类型
        return String(value);
    }
    bindContextMenuEvents() {
        // 绑定所有带 data-action 的元素
        const bindActions = (container) => {
            if (!container) return;
            container.addEventListener('click', (e) => {
                const action = e.target.getAttribute('data-action');
                if (action && typeof this[action] === 'function') {
                    e.preventDefault();
                    this[action]();
                }
            });
        };

        bindActions(document.getElementById('nodeContextMenu'));
        bindActions(document.getElementById('edgeContextMenu'));
        bindActions(document.getElementById('createNodeInput'));
        bindActions(document.getElementById('editNodeLabelInput'));
        bindActions(document.getElementById('editEdgeLabelInput'));
    }
    // --- 按钮事件绑定 ---
    bindButtonEvents() {
        setTimeout(() => {
            const buttonConfigs = [
                {id: 'save-graph-btn', handler: () => this.graphCore.saveGraph()},
                {id: 'delete-graph-btn', handler: () => this.graphCore.deleteGraph()},
                {id: 'refresh-graph-btn', handler: () => this.graphCore.refreshGraph()},
                {id: 'export-graph-btn', handler: () => this.graphCore.exportGraph()},
                {id: 'clear-graph-btn', handler: () => this.graphCore.clearGraph()},
                // ✅ 新增：隐藏面板按钮
                {id: 'hide-panel-btn', handler: () => this.toggleControlPanel(false)},
                // ✅ 新增：展开面板按钮
                {id: 'expand-panel-btn', handler: () => this.toggleControlPanel(true)},
            ];

            buttonConfigs.forEach(btnConfig => {
                const element = document.getElementById(btnConfig.id);
                if (element) {
                    this.bindButtonClick(element, btnConfig.handler);
                } else {
                    console.warn(`未找到按钮元素: ${btnConfig.id}`);
                }
            });

            const physicsToggle = document.getElementById('physicsToggle');
            if (physicsToggle) {
                this.bindToggleChange(physicsToggle, () => this.graphCore.togglePhysics());
            }
        }, 100);
    }

    bindButtonClick(element, handler) {
        if (!element) {
            console.warn('尝试绑定点击事件失败：元素不存在');
            return;
        }
        const newElement = element.cloneNode(true);
        element.parentNode.replaceChild(newElement, element);
        newElement.addEventListener('click', (e) => {
            e.preventDefault();
            try {
                handler();
            } catch (error) {
                console.error(`按钮 ${element.id} 点击处理失败:`, error);
            }
        });
    }

    // --- 修改后 ---
    bindToggleChange(element, handler) {
        if (!element) {
            console.warn('尝试绑定变更事件失败：元素不存在');
            return;
        }
        const newElement = element.cloneNode(true);
        element.parentNode.replaceChild(newElement, element);
        newElement.addEventListener('change', () => {
            try {
                handler();
            } catch (error) {
                console.error(`${element.id} 处理失败:`, error);
            }
        });
    }

    // --- 网络图事件处理器 ---
    handleClick(params) {
        this.logDebug(`🖱️ 点击事件 - 节点: ${params.nodes.length}, 边: ${params.edges.length}`);

        // 处理高亮逻辑 —— ✅ 现在调用的是 GraphUI 自己的方法
        if (params.nodes.length > 0) {
            const clickedNodeId = params.nodes[0];
            if (this.graphCore.state.highlightedNode === clickedNodeId) {
                this.resetHighlight(); // ✅ GraphUI 的方法
            } else {
                this.highlightNodeAndConnections(clickedNodeId); // ✅ GraphUI 的方法
            }
        } else if (params.edges.length === 0 && this.graphCore.state.highlightedNode) {
            this.resetHighlight(); // ✅
        }

        // 处理上下文菜单
        if (this._state.isMenuVisible && params.nodes.length === 0 && params.edges.length === 0) {
            this.hideAllContextMenus();
        }

        // 处理"连接到现有节点"模式
        if (this._state.connectingToExisting && params.nodes.length > 0 && this._state.connectionSourceNode) {
            const targetNodeId = params.nodes[0];
            if (targetNodeId !== this._state.connectionSourceNode) {
                const newEdgeId = `edge_${this._state.connectionSourceNode}_${targetNodeId}_${Date.now()}`;
                this.graphCore.edges.add({
                    id: newEdgeId,
                    from: this._state.connectionSourceNode,
                    to: targetNodeId
                });
                this.logDebug(`连接节点: ${this._state.connectionSourceNode} -> ${targetNodeId}`);
            }
            this.cancelMode();
        }
    }

    handleDoubleClick(params) {
        this.logDebug(`👆 双击事件 - 节点: ${params.nodes.length}, 边: ${params.edges.length}`);
        if (params.nodes.length > 0) {
            this._state.contextMenuNode = params.nodes[0];
            this.showEditNodeLabelInput();
        } else if (params.edges.length > 0) {
            this._state.contextMenuEdge = params.edges[0];
            this.showEditEdgeLabelInput();
        }
    }

    handleContextMenu(params) {
        params.event.preventDefault();
        this.showContextMenuAtPosition(params);
    }

    handleHold(params) {
        this.logDebug(`✋ 长按事件 - 节点: ${params.nodes.length}, 边: ${params.edges.length}`);
        if (this._state.menuShowTimer) {
            clearTimeout(this._state.menuShowTimer);
        }
        this._state.menuScheduledToShow = true;
        this._state.menuShowTimer = setTimeout(() => {
            this.showContextMenuAtPosition(params);
            this._state.menuScheduledToShow = false;
        }, 100);
    }

    handleRelease(params) {
        this.logDebug(`放开 release事件`);
    }

    showContextMenuAtPosition(params) {
        if (params.nodes.length > 0) {
            this._state.contextMenuNode = params.nodes[0];
            const node = this.graphCore.nodes.get(params.nodes[0]);
            this.logDebug(`🖱️ 点击节点: ${node.label} (ID: ${node.id})`);
            this.showNodeContextMenu(params.pointer.DOM);
        } else if (params.edges.length > 0) {
            this._state.contextMenuEdge = params.edges[0];
            const edge = this.graphCore.edges.get(params.edges[0]);
            this.logDebug(`🖱️ 点击边: ${edge.from} -> ${edge.to} (ID: ${edge.id})`);
            this.showEdgeContextMenu(params.pointer.DOM);
        } else {
            this.logDebug("🖱️ 点击画布空白处");
            this.hideAllContextMenus();
        }
    }

    // --- 上下文菜单显示 ---
    showNodeContextMenu(domPos) {
        this.hideAllContextMenus();
        const menu = document.getElementById('nodeContextMenu');
        if (this._state.contextMenuNode) {
            const node = this.graphCore.nodes.get(this._state.contextMenuNode);
            const ul = menu.querySelector('ul');
            const titleElement = document.createElement('li');
            titleElement.className = 'menu-title';
            titleElement.textContent = `节点: ${node.label || '未命名'}`;
            titleElement.style.cssText = 'font-weight: bold; background: #555; font-size: 15px; pointer-events: none; padding: 8px 12px;';
            ul.insertBefore(titleElement, ul.firstChild);
        }
        menu.style.display = 'block';
        this.positionContextMenu(menu, domPos);
        this._state.isMenuVisible = true;
    }

    showEdgeContextMenu(domPos) {
        this.hideAllContextMenus();
        const menu = document.getElementById('edgeContextMenu');
        if (this._state.contextMenuEdge) {
            const edge = this.graphCore.edges.get(this._state.contextMenuEdge);
            const fromNode = this.graphCore.nodes.get(edge.from);
            const toNode = this.graphCore.nodes.get(edge.to);
            const ul = menu.querySelector('ul');
            const titleElement = document.createElement('li');
            titleElement.className = 'menu-title';
            titleElement.textContent = `连接: ${fromNode.label || fromNode.id} → ${toNode.label || toNode.id}`;
            titleElement.style.cssText = 'font-weight: bold; background: #555; pointer-events: none; padding: 8px 12px;';
            ul.insertBefore(titleElement, ul.firstChild);
        }
        menu.style.display = 'block';
        this.positionContextMenu(menu, domPos);
        this._state.isMenuVisible = true;
    }

    showCreateNodeInput() {
        this.hideAllContextMenus();
        const menu = document.getElementById('createNodeInput');
        const input = document.getElementById('newNodeLabel');
        input.value = "新节点";
        if (this._state.contextMenuNode) {
            const node = this.graphCore.nodes.get(this._state.contextMenuNode);
            const titleDiv = menu.querySelector('div:first-child');
            if (titleDiv) {
                titleDiv.textContent = `从节点 "${node.label || node.id}" 创建新节点`;
                titleDiv.style.fontWeight = 'bold';
            }
        }
        menu.style.display = 'block';
        this.positionContextMenu(menu, {x: event.clientX, y: event.clientY});
        input.focus();
        this._state.isConnectingNewNode = true;
        this._state.isMenuVisible = true;
    }

    showEditNodeLabelInput() {
        if (this._state.contextMenuNode) {
            this.hideAllContextMenus();
            const menu = document.getElementById('editNodeLabelInput');
            const input = document.getElementById('editNodeLabelText');
            const node = this.graphCore.nodes.get(this._state.contextMenuNode);
            input.value = node.label || "";
            const titleDiv = menu.querySelector('div:first-child');
            if (titleDiv) {
                titleDiv.textContent = `编辑节点: ${node.label || '未命名'}`;
                titleDiv.style.fontWeight = 'bold';
            }
            menu.style.display = 'block';
            this.positionContextMenu(menu, {x: event.clientX, y: event.clientY});
            input.focus();
            this._state.isMenuVisible = true;
        }
    }

    showEditEdgeLabelInput() {
        if (this._state.contextMenuEdge) {
            this.hideAllContextMenus();
            const menu = document.getElementById('editEdgeLabelInput');
            const input = document.getElementById('editEdgeLabelText');
            const edge = this.graphCore.edges.get(this._state.contextMenuEdge);
            input.value = edge.label || "";
            const titleDiv = menu.querySelector('div:first-child');
            if (titleDiv) {
                const fromNode = this.graphCore.nodes.get(edge.from);
                const toNode = this.graphCore.nodes.get(edge.to);
                titleDiv.textContent = `编辑连接: ${fromNode.label || fromNode.id} → ${toNode.label || toNode.id}`;
                titleDiv.style.fontWeight = 'bold';
            }
            menu.style.display = 'block';
            this.positionContextMenu(menu, {x: event.clientX, y: event.clientY});
            input.focus();
            this._state.isMenuVisible = true;
        }
    }

    positionContextMenu(menu, domPos) {
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

    hideAllContextMenus() {
        const menus = document.querySelectorAll('.context-menu, .input-menu');
        menus.forEach(menu => {
            menu.style.display = 'none';
            const titleElements = menu.querySelectorAll('.menu-title');
            titleElements.forEach(el => el.remove());
        });
        if (this._state.menuShowTimer) {
            clearTimeout(this._state.menuShowTimer);
            this._state.menuShowTimer = null;
        }
        this._state.isMenuVisible = false;
    }

    // --- 输入确认函数 ---
    confirmCreateNode() {
        const input = document.getElementById('newNodeLabel');
        const label = input.value || "新节点";
        const newNodeId = 'node_' + Date.now();

        if (this._state.contextMenuNode && this._state.isConnectingNewNode) {
            const nodePos = this.graphCore.network.getPositions([this._state.contextMenuNode])[this._state.contextMenuNode];
            this.graphCore.nodes.add({
                id: newNodeId,
                label: label,
                x: nodePos.x + 100,
                y: nodePos.y + 100
            });
            this.graphCore.edges.add({
                from: this._state.contextMenuNode,
                to: newNodeId
            });
            this.logDebug(`从节点 ${this._state.contextMenuNode} 创建并连接新节点: ${newNodeId}`);
        } else if (this._state.addingNode) {
            const pos = this.graphCore.network.canvasToDOM({x: 0, y: 0});
            this.graphCore.nodes.add({
                id: newNodeId,
                label: label,
                x: pos.x,
                y: pos.y
            });
            this.logDebug(`创建新节点: ${newNodeId}`);
        }

        this._state.isConnectingNewNode = false;
        this.hideAllContextMenus();
    }

    confirmEditNodeLabel() {
        if (this._state.contextMenuNode) {
            const input = document.getElementById('editNodeLabelText');
            const newLabel = input.value || "未命名节点";
            this.graphCore.nodes.update({ id: this._state.contextMenuNode, label: newLabel });
            this.logDebug(`编辑节点标签: ${this._state.contextMenuNode} -> ${newLabel}`);
            this.hideAllContextMenus();
        }
    }

    confirmEditEdgeLabel() {
        if (this._state.contextMenuEdge) {
            const input = document.getElementById('editEdgeLabelText');
            const newLabel = input.value || "";
            this.graphCore.edges.update({ id: this._state.contextMenuEdge, label: newLabel });
            this.logDebug(`编辑边标签: ${this._state.contextMenuEdge} -> "${newLabel}"`);
            this.hideAllContextMenus();
        }
    }

    cancelInput() {
        this.hideAllContextMenus();
    }

    // --- 节点菜单操作 ---
    deleteSelectedNode() {
        if (this._state.contextMenuNode) {
            const connectedEdges = this.graphCore.network.getConnectedEdges(this._state.contextMenuNode);
            this.graphCore.edges.remove(connectedEdges);
            this.graphCore.nodes.remove(this._state.contextMenuNode);
            this.logDebug(`删除节点: ${this._state.contextMenuNode}`);
            this.hideAllContextMenus();
        }
    }

    connectToExistingNodeMode() {
        if (this._state.contextMenuNode) {
            this._state.connectingToExisting = true;
            this._state.connectionSourceNode = this._state.contextMenuNode;
            this.logDebug(`连接模式: 请点击目标节点以连接到 ${this._state.contextMenuNode}`);
            this.hideAllContextMenus();
        }
    }

    // --- 边菜单操作 ---
    deleteSelectedEdge() {
        if (this._state.contextMenuEdge) {
            this.graphCore.edges.remove(this._state.contextMenuEdge);
            this.logDebug(`删除边: ${this._state.contextMenuEdge}`);
            this.hideAllContextMenus();
        }
    }

    reverseEdgeDirection() {
        if (this._state.contextMenuEdge) {
            const edge = this.graphCore.edges.get(this._state.contextMenuEdge);
            this.graphCore.edges.remove(this._state.contextMenuEdge);
            this.graphCore.edges.add({
                id: this._state.contextMenuEdge,
                from: edge.to,
                to: edge.from,
                label: edge.label
            });
            this.logDebug(`反转边方向: ${edge.to} -> ${edge.from}`);
            this.hideAllContextMenus();
        }
    }

    cancelMode() {
        this._state.addingNode = false;
        this._state.connectingToExisting = false;
        this._state.connectionSourceNode = null;
        this.logDebug("已取消所有模式");
        this.hideAllContextMenus();
    }

    addNodeMode() {
        this._state.addingNode = true;
        this.logDebug("进入添加节点模式，请点击画布添加节点");
    }

    logDebug(message) {
        const debugInfo = document.getElementById('debug-info');
        if (debugInfo) {
            debugInfo.textContent = message;
        }
    }

    // --- 公共接口 ---
    get state() {
        return this._state;
    }
    toggleControlPanel(show) {
    const panel = document.getElementById('floating-control-section');
    const expandBtn = document.getElementById('expand-panel-btn');

    if (show) {
        panel?.classList.remove('hidden');
        expandBtn?.classList.remove('shown');
    } else {
        panel?.classList.add('hidden');
        expandBtn?.classList.add('shown');
    }
}
}

// 页面加载完成时初始化
document.addEventListener('DOMContentLoaded', async function() {
    // 初始化核心模块
    const graphCore = GraphCore;

    // 初始化UI模块
    const graphUI = new GraphUI(graphCore);

    // 从 URL 获取 cache_key
    const urlParams = new URLSearchParams(window.location.search);
    const cacheKey = urlParams.get('cache_key');

    if (cacheKey) {
        try {
            await graphCore.loadGraphData(cacheKey);
            console.log('图谱数据加载完成');

            graphUI.updateMetadataDisplay(); // 👈 关键！

            // 绑定网络图的UI事件
            if (graphCore.network) {
                graphCore.network.on("click", (params) => graphUI.handleClick(params));
                graphCore.network.on("doubleClick", (params) => graphUI.handleDoubleClick(params));
                graphCore.network.on("oncontext", (params) => graphUI.handleContextMenu(params));
                graphCore.network.on("hold", (params) => graphUI.handleHold(params));
                graphCore.network.on("release", (params) => graphUI.handleRelease(params));
            }
        } catch (error) {
            console.error('图谱数据加载失败:', error);
        }
    } else {
        const container = document.getElementById('mynetwork');
        if (container) {
            container.innerHTML = `<div style="text-align: center; padding: 50px; color: #aaa; font-family: sans-serif;">
                请在 URL 中提供 cache_key 参数加载图谱，例如：<br>
                ?cache_key=your_cache_key_here
            </div>`;
        }
    }

    // 将UI实例暴露到全局，以便在HTML的内联onclick中调用
    window.GraphUI = graphUI;
});