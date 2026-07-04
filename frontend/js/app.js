/**
 * 三星事业部管理平台 - 公共模块
 * 提供：认证检查、侧边栏渲染、API 请求封装、通知系统
 */

// 注册 Service Worker（PWA 支持）
if ('serviceWorker' in navigator) {
    window.addEventListener('load', () => {
        navigator.serviceWorker.register('/sw.js').catch(() => {});
    });
}

const App = {
    user: null,
    token: null,

    init() {
        this.token = localStorage.getItem('token');
        this.user = JSON.parse(localStorage.getItem('user') || 'null');
        if (!this.token) {
            window.location.href = '/login';
            return false;
        }
        return true;
    },

    checkAuth() {
        /* 验证 token 是否有效，无效则跳登录页 */
        if (!this.token) {
            window.location.href = '/login';
            return false;
        }
        // 可选：调 /api/auth/me 验证 token 合法性
        return true;
    },

    api(path, options = {}) {
        const url = '/api/' + path.replace(/^\/+/, '');
        const headers = {'Content-Type': 'application/json', ...options.headers};
        if (this.token) headers['Authorization'] = `Bearer ${this.token}`;

        return fetch(url, {
            ...options,
            headers,
            body: options.body ? JSON.stringify(options.body) : undefined
        }).then(r => {
            if (r.status === 401) {
                localStorage.clear();
                window.location.href = '/login';
                throw new Error('未登录');
            }
            return r.json();
        });
    },

    renderSidebar(activePage) {
        const isAdmin = this.user?.role === 'admin';
        const isManager = this.user?.role === 'manager';
        const canManage = isAdmin || isManager;
        const navItems = [
            { id: 'dashboard', icon: '📊', label: '数据总览', href: '/dashboard' },
            { id: 'sales', icon: '💰', label: '销售进度', href: '/sales' },
            { id: 'inventory', icon: '📦', label: '库存监控', href: '/inventory' },
            { id: 'prices', icon: '💲', label: '价格看板', href: '/prices' },
            { id: 'staff', icon: '💵', label: '店员提成', href: '/staff' },
            { id: 'order-entry', icon: '🧾', label: '快速成交', href: '/order-entry' },
            { id: 'members', icon: '👥', label: '会员管理', href: '/members', requiresAuth: canManage },
            { id: 'knowledge', icon: '📚', label: '店长百事通', href: '/knowledge' },
            { id: 'community', icon: '💬', label: '交流社区', href: '/community' },
            { id: 'ai', icon: '🤖', label: 'AI 助手', href: '/ai' },
            { id: 'attendance', icon: '📅', label: '考勤打卡', href: '/attendance' },
            { id: 'approval', icon: '📝', label: '审批管理', href: '/approval' },
            { id: 'tasks', icon: '✅', label: '任务管理', href: '/tasks' },
        ];
        if (isAdmin) {
            navItems.push({ id: 'admin', icon: '⚙️', label: '后台管理', href: '/admin' });
        }

        const sidebar = document.getElementById('sidebar');
        if (!sidebar) return;

        sidebar.innerHTML = `
            <div class="sidebar-header">
                <h2>三星事业部</h2>
                <small>运营管理平台 v2.1</small>
            </div>
            <nav class="sidebar-nav">
                ${navItems.filter(item => item.requiresAuth !== false).map(item => `
                    <a class="nav-item ${item.id === activePage ? 'active' : ''}" href="${item.href}" onclick="App.closeMobileMenu()">
                        <span class="nav-icon">${item.icon}</span>
                        <span>${item.label}</span>
                    </a>
                `).join('')}
            </nav>
            <div class="sidebar-footer">
                ${this.user?.display_name || ''} · ${isAdmin ? '管理员' : this.user?.store_name || '店长'}
            </div>
        `;
    },

    renderTopbar(title) {
        const topbar = document.getElementById('topbar');
        if (!topbar) return;
        const initial = (this.user?.display_name || 'U').charAt(0);
        topbar.innerHTML = `
            <div style="display:flex;align-items:center;gap:8px;">
                <button class="menu-toggle" onclick="App.toggleMobileMenu()">☰</button>
                <div class="topbar-title">${title}</div>
            </div>
            <div class="topbar-right">
                <button class="topbar-btn" onclick="App.showNotifications()" title="通知" id="notifBtn">
                    🔔<span class="badge" id="notifBadge"></span>
                </button>
                <div class="topbar-user">
                    <div class="avatar">${initial}</div>
                    <span>${this.user?.display_name || ''}</span>
                </div>
                <button class="topbar-btn" onclick="App.logout()" title="退出登录">🚪</button>
            </div>
        `;

        // 添加侧边栏遮罩层
        if (!document.getElementById('sidebarOverlay')) {
            const overlay = document.createElement('div');
            overlay.id = 'sidebarOverlay';
            overlay.className = 'sidebar-overlay';
            overlay.onclick = () => App.closeMobileMenu();
            document.body.appendChild(overlay);
        }

        this.checkUnread();
    },

    toggleMobileMenu() {
        const sidebar = document.getElementById('sidebar');
        const overlay = document.getElementById('sidebarOverlay');
        if (sidebar) {
            sidebar.classList.toggle('open');
            if (overlay) overlay.classList.toggle('show', sidebar.classList.contains('open'));
        }
    },

    closeMobileMenu() {
        const sidebar = document.getElementById('sidebar');
        const overlay = document.getElementById('sidebarOverlay');
        if (sidebar) sidebar.classList.remove('open');
        if (overlay) overlay.classList.remove('show');
    },

    logout() {
        if (confirm('确定要退出登录吗？')) {
            localStorage.clear();
            window.location.href = '/login';
        }
    },

    toast(msg, type = 'info') {
        const el = document.createElement('div');
        el.className = `toast ${type}`;
        el.textContent = msg;
        document.body.appendChild(el);
        setTimeout(() => el.classList.add('show'), 10);
        setTimeout(() => {
            el.classList.remove('show');
            setTimeout(() => el.remove(), 300);
        }, 3000);
    },

    async checkUnread() {
        try {
            // 使用 Authorization: Bearer header，不再把 token 明文暴露在 URL
            const data = await this.api('/notify/unread-count');
            const badge = document.getElementById('notifBadge');
            if (badge) {
                badge.classList.toggle('show', data.count > 0);
            }
        } catch(e) {}
    },

    formatDate(dateStr) {
        if (!dateStr) return '--';
        return dateStr.substring(0, 10);
    },

    formatPrice(price) {
        if (!price || price === 0) return '--';
        return '¥' + Number(price).toLocaleString('zh-CN', {minimumFractionDigits: 0});
    }
};
