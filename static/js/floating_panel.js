// static/js/floating_panel.js
const FloatingPanel = (function() {
    let isInitialized = false;
    let cacheKey = '';

    // 初始化控制面板
    function init() {
        if (isInitialized) return;

        // 等待 DOM 加载完成
        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', setupPanel);
        } else {
            setupPanel();
        }

        isInitialized = true;
    }

    // 设置面板事件
    function setupPanel() {
        const panel = document.getElementById('floating-control-section');
        const hideBtn = document.getElementById('hide-panel-btn');
        const expandBtn = document.getElementById('expand-panel-btn');
        const physicsToggle = document.getElementById('physicsToggle');
        const saveBtn = document.getElementById('save-graph-btn');
        const clearBtn = document.getElementById('clear-graph-btn');
        const exportBtn = document.getElementById('export-graph-btn');
        const refreshBtn = document.getElementById('refresh-graph-btn');

        // 隐藏面板
        if (hideBtn) {
            hideBtn.addEventListener('click', function(e) {
                e.stopPropagation();
                if (panel) panel.style.display = 'none';
                if (expandBtn) expandBtn.style.display = 'block';
                localStorage.setItem('graphEditorPanelHidden', 'true');
            });
        }

        // 展开面板
        if (expandBtn) {
            expandBtn.addEventListener('click', function() {
                if (panel) panel.style.display = 'block';
                expandBtn.style.display = 'none';
                localStorage.setItem('graphEditorPanelHidden', 'false');
            });
        }

        // 物理效果切换
        if (physicsToggle) {
            physicsToggle.addEventListener('change', function() {
                // 通过全局事件通知 GraphEditor
                window.dispatchEvent(new CustomEvent('physicsToggleChanged', {
                    detail: { enabled: this.checked }
                }));
            });
        }

        // 保存图谱
        if (saveBtn) {
            saveBtn.addEventListener('click', function() {
                window.dispatchEvent(new CustomEvent('saveGraphRequested'));
            });
        }

        // 清空图谱
        if (clearBtn) {
            clearBtn.addEventListener('click', function() {
                if (confirm('确定要清空当前图谱吗？')) {
                    window.dispatchEvent(new CustomEvent('clearGraphRequested'));
                }
            });
        }

        // 导出图谱
        if (exportBtn) {
            exportBtn.addEventListener('click', function() {
                window.dispatchEvent(new CustomEvent('exportGraphRequested'));
            });
        }

        // 刷新图谱
        if (refreshBtn) {
            refreshBtn.addEventListener('click', function() {
                window.dispatchEvent(new CustomEvent('refreshGraphRequested'));
            });
        }

        // 检查本地存储的面板状态
        const isPanelHidden = localStorage.getItem('graphEditorPanelHidden') === 'true';
        if (isPanelHidden) {
            if (panel) panel.style.display = 'none';
            if (expandBtn) expandBtn.style.display = 'block';
        }

        // 初始化物理效果状态显示
        window.dispatchEvent(new CustomEvent('physicsStatusUpdated', {
            detail: { enabled: true } // 默认启用
        }));

        // 从 URL 获取 cache_key 并加载元数据
        const urlParams = new URLSearchParams(window.location.search);
        cacheKey = urlParams.get('cache_key') || '';

        if (cacheKey) {
            loadMetadata();
        }
    }

    // 加载元数据
    async function loadMetadata() {
    // 找到第一个包含"图谱信息"标题的 control-panel
    const controlPanels = document.querySelectorAll('.control-panel');
    let metadataPanel = null;

    // 遍历所有 control-panel，找到包含"图谱信息"的那一个
    for (let panel of controlPanels) {
        const title = panel.querySelector('h5');
        if (title && title.textContent.includes('图谱信息')) {
            metadataPanel = panel;
            break;
        }
    }

    if (!metadataPanel || !cacheKey) {
        console.log('无法加载元数据：缺少 metadataPanel 或 cacheKey');
        return;
    }

    try {
        // 显示加载状态（保留标题）
        const titleElement = metadataPanel.querySelector('h5');
        const titleHTML = titleElement ? titleElement.outerHTML : '<h5>📋 图谱信息</h5>';
        metadataPanel.innerHTML = titleHTML + '<div style="color: #ccc; font-style: italic; padding: 12px;">加载中...</div>';

        const response = await fetch(`/api/graph/${encodeURIComponent(cacheKey)}/metadata`);
        const metadata = await response.json();

        if (!response.ok) {
            throw new Error(metadata.error || '加载元数据失败');
        }

        // 格式化时间
        const formatTime = (timeStr) => {
            if (!timeStr) return '未知';
            try {
                return new Date(timeStr).toLocaleString('zh-CN');
            } catch {
                return timeStr;
            }
        };

        // 预定义的字段映射
        const fieldMapping = {
            'novel_name': '小说',
            'chapter_name': '章节',
            'model_name': '模型',
            'use_local': '本地模型',
            'num_ctx': '上下文长度',
            'chunk_size': '块大小',
            'chunk_overlap': '重叠大小',
            'content_size': '内容大小',
            'schema_name': '模式',
            'created_at': '创建时间',
        };

        // 忽略显示的字段名（label）
        const ignoreLabels = new Set(['cache_version', 'schema_display','saved_at']);

        // 预定义的特殊处理字段
        const specialFields = {
            'use_local': (value) => value !== undefined ? (value ? '是' : '否') : '未知',
            'created_at': (value) => formatTime(value),
            'model_name': (value) => value == 'qwen3:30b-a3b-instruct-2507-q4_K_M' ? 'qwen3:30b-q4_K_M' : value
        };

        // 先处理预定义的字段
        const predefinedItems = [];
        const processedFields = new Set();

        // 按照预定义顺序处理字段
        Object.keys(fieldMapping).forEach(key => {
            if (metadata.hasOwnProperty(key)) {
                let value = metadata[key];

                // 特殊处理某些字段
                if (specialFields[key]) {
                    value = specialFields[key](value);
                } else {
                    value = value || '未知';
                }

                predefinedItems.push({
                    label: fieldMapping[key],
                    value: value
                });
                processedFields.add(key);
            }
        });

        // 处理未预定义的字段
        const additionalItems = [];
        Object.keys(metadata).forEach(key => {
            if (!processedFields.has(key) && key !== 'error') { // 排除已处理的字段和error字段
                let value = metadata[key];

                // 对时间字段进行特殊处理（如果未在预定义中）
                if (key.includes('time') || key.includes('date') || key.includes('created') || key.includes('updated')) {
                    value = formatTime(value);
                } else {
                    value = value !== null && value !== undefined ? value : '未知';
                }

                const label = key; // 使用原始字段名作为标签

                // 如果 label 在忽略列表中，则跳过
                if (ignoreLabels.has(label)) {
                    return;
                }

                additionalItems.push({
                    label: label,
                    value: value
                });
            }
        });
        // 合并所有项目
        const allItems = [...predefinedItems, ...additionalItems];

        // 生成完整的 HTML 内容（包括标题）
        const htmlContent = titleHTML + allItems.map(item => `
            <div class="detail-item">
                <span class="detail-label">${item.label}:</span>
                <span class="detail-value">${item.value}</span>
            </div>
        `).join('');

        // 替换整个面板内容
        metadataPanel.innerHTML = htmlContent;

    } catch (error) {
        const titleElement = metadataPanel.querySelector('h5');
        const titleHTML = titleElement ? titleElement.outerHTML : '<h5>📋 图谱信息</h5>';
        metadataPanel.innerHTML = titleHTML + `<div style="color: #ff6b6b; padding: 12px;">加载失败: ${error.message}</div>`;
    }
}

    // 更新物理效果状态显示
    function updatePhysicsStatus(enabled) {
        const physicsToggle = document.getElementById('physicsToggle');
        if (physicsToggle) {
            physicsToggle.checked = enabled;
        }
    }

    // 刷新图谱和元数据
    function refreshGraph() {
        // 重新加载元数据
        const urlParams = new URLSearchParams(window.location.search);
        cacheKey = urlParams.get('cache_key') || cacheKey;
        if (cacheKey) {
            loadMetadata();
        }
    }

    // 公共接口
    return {
        init,
        updatePhysicsStatus,
        refreshGraph,
        loadMetadata,
        // 添加设置 cacheKey 的方法
        setCacheKey: function(key) {
            cacheKey = key;
        }
    };
})();

// 自动初始化
FloatingPanel.init();

// 监听物理效果状态更新事件
window.addEventListener('physicsStatusUpdated', function(e) {
    FloatingPanel.updatePhysicsStatus(e.detail.enabled);
});

// 监听刷新请求
window.addEventListener('refreshGraphRequested', function() {
    FloatingPanel.refreshGraph();
});

// 监听父页面的消息
window.addEventListener('message', function(event) {
    if (event.data && event.data.type === 'updateCacheKey') {
        // 更新 cacheKey 并重新加载元数据
        if (event.data.cacheKey) {
            FloatingPanel.setCacheKey(event.data.cacheKey);
            FloatingPanel.loadMetadata();
        }
    }
});