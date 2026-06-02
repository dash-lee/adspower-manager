/**
 * AdsPower Manager - 通用 JavaScript 工具函数
 * =============================================
 */

// ---- Toast 通知 ----
function showToast(message, type = 'info', duration = 3000) {
    const container = document.getElementById('toast-container');
    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    toast.textContent = message;
    container.appendChild(toast);
    setTimeout(() => {
        toast.style.opacity = '0';
        toast.style.transition = 'opacity 0.3s';
        setTimeout(() => toast.remove(), 300);
    }, duration);
}

// ---- HTML 转义 ----
function escapeHtml(str) {
    if (!str) return '';
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
}

// ---- 时间格式化 ----
function formatTime(isoString) {
    if (!isoString) return '-';
    try {
        const d = new Date(isoString);
        const pad = n => String(n).padStart(2, '0');
        return `${d.getFullYear()}-${pad(d.getMonth()+1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
    } catch(e) {
        return isoString;
    }
}

// ---- API 请求封装 ----
async function apiGet(url) {
    try {
        const resp = await fetch(url);
        return await resp.json();
    } catch(e) {
        return {code: -1, data: null, msg: e.message};
    }
}

async function apiPost(url, body = {}) {
    try {
        const resp = await fetch(url, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(body),
        });
        return await resp.json();
    } catch(e) {
        return {code: -1, data: null, msg: e.message};
    }
}

// ---- 模态框管理 ----
function openModal(id) {
    document.getElementById(id).style.display = 'flex';
}
function closeModal(id) {
    document.getElementById(id).style.display = 'none';
}

// ---- 模态框关闭（点击背景关闭） ----
document.addEventListener('click', function(e) {
    if (e.target.classList.contains('modal')) {
        e.target.style.display = 'none';
    }
});

// ---- API 状态检查（所有页面共用） ----
async function checkApiStatus() {
    try {
        const resp = await fetch('/api/status');
        const data = await resp.json();
        if (data.code === 0) {
            const dot = document.getElementById('status-dot');
            const text = document.getElementById('status-text');
            if (!dot || !text) return;
            if (!data.data.api_key_ok) {
                dot.style.color = '#f97316';
                text.textContent = 'API 未配置';
                text.title = '请到配置管理填写 API Key';
            } else if (data.data.adspower_ok) {
                dot.style.color = '#4ade80';
                text.textContent = 'API 正常';
                text.title = '';
            } else {
                dot.style.color = '#f87171';
                text.textContent = 'API 异常';
                text.title = 'AdsPower 可能未启动，请检查';
            }
        }
    } catch(e) {
        const dot = document.getElementById('status-dot');
        const text = document.getElementById('status-text');
        if (dot) dot.style.color = '#f87171';
        if (text) text.textContent = '连接失败';
    }
}
// 页面加载后立即检查，之后每30秒刷新
document.addEventListener('DOMContentLoaded', checkApiStatus);
setInterval(checkApiStatus, 30000);
