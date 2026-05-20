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

// ---- 模态框关闭（点击背景关闭） ----
document.addEventListener('click', function(e) {
    if (e.target.classList.contains('modal')) {
        e.target.style.display = 'none';
    }
});
