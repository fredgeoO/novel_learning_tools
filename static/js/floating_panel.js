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

        // 构建显示内容
        const items = [
            { label: '小说', value: metadata.novel_name || '未知' },
            { label: '章节', value: metadata.chapter_name || '未知' },
            { label: '模型', value: metadata.model_name || '未知' },
            { label: '本地模型', value: metadata.use_local !== undefined ? (metadata.use_local ? '是' : '否') : '未知' },
            { label: '上下文长度', value: metadata.num_ctx || '未知' },
            { label: '块大小', value: metadata.chunk_size || '未知' },
            { label: '重叠大小', value: metadata.chunk_overlap || '未知' },
            { label: '内容大小', value: metadata.content_size || '未知' },
            { label: '模式', value: metadata.schema_name || '未知' },
            { label: '创建时间', value: formatTime(metadata.created_at) }
        ];

        // 生成完整的 HTML 内容（包括标题）
        const htmlContent = titleHTML + items.map(item => `
            <div class="detail-item">
                <span class="detail-label">${item.label}:</span>
                <span class="detail-value">${item.value}</span>
            </div>
        `).join('');

        // 替换整个面板内容
        metadataPanel.innerHTML = htmlContent;

    } catch (error) {
        console.error('加载元数据失败:', error);
        // 显示错误信息（包括标题）
        const titleElement = metadataPanel.querySelector('h5');
        const titleHTML = titleElement ? titleElement.outerHTML : '<h5>📋 图谱信息</h5>';
        metadataPanel.innerHTML = titleHTML + `<div style="color: #ff6b6b; font-size: 12px; padding: 12px;">无法加载元数据: ${error.message}</div>`;
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