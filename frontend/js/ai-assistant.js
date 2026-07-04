/**
 * 三星事业部 AI 智能助手 - 浮动聊天组件 v3
 * 极简实现，零依赖，纯原生 DOM
 */

(function() {
    'use strict';

    // ── 状态 ──
    var chatOpen = false;
    var sessionId = 'default';
    var abortController = null;
    var chatPanel = null;
    var chatMessages = null;
    var chatInput = null;

    // ── 主题色 ──
    var P = '#1428a0';   // primary
    var PL = '#e8ecff';  // primary light

    // ── 注入样式 ──
    function injectCSS() {
        if (document.getElementById('_ai_css')) return;
        var s = document.createElement('style');
        s.id = '_ai_css';
        s.textContent = [
            '.ai-fbtn{position:fixed;bottom:24px;right:24px;z-index:99999;width:56px;height:56px;border-radius:50%;background:' + P + ';color:#fff;border:none;cursor:pointer;box-shadow:0 8px 32px rgba(0,0,0,.12);display:flex;align-items:center;justify-content:center;font-size:26px;transition:transform .2s,box-shadow .2s;user-select:none;outline:none;}',
            '.ai-fbtn:hover{transform:scale(1.08);}',
            '.ai-fbtn:active{transform:scale(.95);}',
            '.ai-fbdot{position:absolute;top:2px;right:2px;width:10px;height:10px;border-radius:50%;background:#10b981;border:2px solid #fff;}',
            '@keyframes _aiPulse{0%,100%{box-shadow:0 8px 32px rgba(20,40,160,.12);}50%{box-shadow:0 8px 48px rgba(20,40,160,.35);}}',
            '.ai-fbtn.pulse{animation:_aiPulse 2s infinite;}',
            '',
            '.ai-panel{position:fixed;bottom:92px;right:24px;z-index:99999;width:380px;max-width:calc(100vw - 32px);height:520px;max-height:calc(100vh - 120px);background:#fff;border-radius:16px;box-shadow:0 8px 32px rgba(0,0,0,.12);display:flex;flex-direction:column;overflow:hidden;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;transform-origin:bottom right;transition:transform .25s cubic-bezier(.16,1,.3,1),opacity .25s;}',
            '.ai-panel._hide{transform:scale(.85);opacity:0;pointer-events:none;}',
            '',
            '.ai-phd{padding:14px 16px;border-bottom:1px solid #e5e7eb;display:flex;align-items:center;justify-content:space-between;background:' + P + ';color:#fff;}',
            '.ai-phd h3{margin:0;font-size:15px;font-weight:600;}',
            '.ai-phd button{background:rgba(255,255,255,.15);border:none;color:#fff;width:28px;height:28px;border-radius:8px;cursor:pointer;font-size:14px;display:flex;align-items:center;justify-content:center;margin-left:6px;}',
            '.ai-phd button:hover{background:rgba(255,255,255,.25);}',
            '',
            '.ai-msgs{flex:1;overflow-y:auto;padding:12px;display:flex;flex-direction:column;gap:10px;scroll-behavior:smooth;}',
            '.ai-msg{display:flex;gap:8px;animation:_fadeIn .3s ease;}',
            '@keyframes _fadeIn{from{opacity:0;transform:translateY(6px);}to{opacity:1;transform:translateY(0);}}',
            '.ai-msg.user{flex-direction:row-reverse;}',
            '.ai-avatar{width:30px;height:30px;border-radius:50%;flex-shrink:0;display:flex;align-items:center;justify-content:center;font-size:14px;font-weight:600;}',
            '.ai-msg.assistant .ai-avatar{background:' + PL + ';color:' + P + ';}',
            '.ai-msg.user .ai-avatar{background:' + P + ';color:#fff;}',
            '.ai-bbl{max-width:78%;padding:10px 14px;border-radius:14px;font-size:13px;line-height:1.6;word-break:break-word;}',
            '.ai-msg.user .ai-bbl{background:' + P + ';color:#fff;border-bottom-right-radius:4px;}',
            '.ai-msg.assistant .ai-bbl{background:#f3f4f6;color:#1f2937;border-bottom-left-radius:4px;}',
            '.ai-bbl h1,.ai-bbl h2,.ai-bbl h3{font-size:14px;margin:6px 0 4px;}',
            '.ai-bbl ul,.ai-bbl ol{padding-left:18px;margin:4px 0;}',
            '.ai-bbl li{margin:2px 0;}',
            '.ai-bbl code{background:rgba(0,0,0,.08);padding:2px 6px;border-radius:4px;font-size:12px;font-family:monospace;}',
            '.ai-bbl table{width:100%;border-collapse:collapse;margin:6px 0;font-size:12px;}',
            '.ai-bbl th,.ai-bbl td{border:1px solid #d1d5db;padding:4px 8px;text-align:left;}',
            '.ai-bbl th{background:#f9fafb;font-weight:600;}',
            '.ai-bbl strong{color:' + P + ';}.ai-bbl em{color:#6b7280;}',
            '',
            '.ai-quick{display:flex;flex-wrap:wrap;gap:6px;padding:8px 12px;border-top:1px solid #e5e7eb;}',
            '.ai-qi{padding:5px 10px;border-radius:14px;border:1px solid #e5e7eb;background:#fff;cursor:pointer;font-size:12px;color:#1f2937;white-space:nowrap;transition:all .15s;}',
            '.ai-qi:hover{border-color:' + P + ';color:' + P + ';background:' + PL + ';}',
            '',
            '.ai-inpArea{padding:10px 12px;border-top:1px solid #e5e7eb;display:flex;gap:8px;align-items:flex-end;}',
            '.ai-input{flex:1;border:1px solid #e5e7eb;border-radius:12px;padding:8px 12px;font-size:13px;outline:none;resize:none;max-height:80px;line-height:1.5;font-family:inherit;transition:border-color .15s;}',
            '.ai-input:focus{border-color:' + P + ';}',
            '.ai-sendBtn{width:34px;height:34px;border-radius:10px;border:none;background:' + P + ';color:#fff;cursor:pointer;font-size:16px;flex-shrink:0;display:flex;align-items:center;justify-content:center;transition:background .15s;}',
            '.ai-sendBtn:hover{background:#0e1d7a;}.ai-sendBtn:disabled{background:#9ca3af;cursor:not-allowed;}',
            '',
            '.ai-typing{display:flex;gap:3px;padding:4px 8px;}',
            '.ai-typing span{width:6px;height:6px;border-radius:50%;background:#9ca3af;animation:_dotBounce 1.4s infinite;}',
            '.ai-typing span:nth-child(2){animation-delay:.2s;}.ai-typing span:nth-child(3){animation-delay:.4s;}',
            '@keyframes _dotBounce{0%,60%,100%{transform:translateY(0);}30%{transform:translateY(-6px);}}',
            '',
            '@media(max-width:440px){.ai-panel{right:8px;left:8px;width:auto;bottom:80px;}.ai-fbtn{bottom:16px;right:16px;}}'
        ].join('\n');
        (document.head || document.getElementsByTagName('head')[0]).appendChild(s);
    }

    // ── Markdown 渲染 ──
    function md(text) {
        if (!text) return '';
        return text
            .replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')
            .replace(/^### (.+)$/gm,'<h3>$1</h3>')
            .replace(/^## (.+)$/gm,'<h2>$1</h2>')
            .replace(/^# (.+)$/gm,'<h1>$1</h1>')
            .replace(/\*\*(.+?)\*\*/g,'<strong>$1</strong>')
            .replace(/\*(.+?)\*/g,'<em>$1</em>')
            .replace(/`([^`]+)`/g,'<code>$1</code>')
            .replace(/^- (.+)$/gm,'<li>$1</li>')
            .replace(/(<li>.*<\/li>\n?)+/g,'<ul>$&</ul>')
            .replace(/\n/g,'<br>');
    }

    // ── 创建元素辅助 ──
    function el(tag, cls, txt) {
        var d = document.createElement(tag);
        if (cls) d.className = cls;
        if (txt !== undefined) d.textContent = txt;
        return d;
    }

    // ── 获取或创建面板 ──
    function ensurePanel() {
        if (chatPanel) return;

        injectCSS();

        // 头部
        var hd = el('div', 'ai-phd');
        var h3 = document.createElement('h3');
        h3.textContent = 'AI \u667a\u80fd\u52a9\u624b';
        var btnBar = document.createDocumentFragment();

        var clrBtn = el('button', '', '\u21bb');
        clrBtn.title = '\u6e05\u9664\u5bf9\u8bdd';

        var clsBtn = el('button', '', '\u00d7');
        clsBtn.title = '\u5173\u95ed';

        btnBar.appendChild(clrBtn);
        btnBar.appendChild(clsBtn);
        hd.appendChild(h3);
        hd.appendChild(btnBar);

        // 消息区
        chatMessages = el('div', 'ai-msgs');

        // 快捷指令
        var quickBar = el('div', 'ai-quick');
        var prompts = [
            {t: '\ud83d\udcca \u4eca\u5929\u9500\u552e6005\u4e48\u6837'},
            {t: '\ud83c\dfc6 \u672c\u6708\u95e8\u5e97\u6392\u540d'},
            {t: '\ud83d\udce6 \u5e93\u5b58\u9884\u8b66\u6709\u54ea\u4e9b'},
            {t: '\ud83d\udcb2 S25 Ultra \u7ade\u54c1\u4ef7\u683c'},
            {t: '\ud83d\udc65 \u5f85\u8ddf\u8fdb\u7684\u4f1a\u5458'},
            {t: '\ud83d\udca1 \u672c\u6708\u7ecf\u8425\u5206\u6790'}
        ];
        prompts.forEach(function(p) {
            var q = el('div', 'ai-qi', p.t);
            quickBar.appendChild(q);
        });

        // 输入区
        chatInput = el('textarea', 'ai-input');
        chatInput.placeholder = '\u8f93\u5165\u95ee\u9898\uff0c\u5982"\u4eca\u5929\u9500\u552e6005\u4e48\u6837"';
        chatInput.rows = 1;

        var sendBtn = el('button', 'ai-sendBtn', '\u2191');

        var inpArea = el('div', 'ai-inpArea');
        inpArea.appendChild(chatInput);
        inpArea.appendChild(sendBtn);

        // 面板容器
        chatPanel = el('div', 'ai-panel _hide');
        chatPanel.appendChild(hd);
        chatPanel.appendChild(chatMessages);
        chatPanel.appendChild(quickBar);
        chatPanel.appendChild(inpArea);

        document.body.appendChild(chatPanel);

        // ── 绑定事件 ──
        clsBtn.onclick = function(e) {
            e.stopPropagation();
            closePanel();
        };
        clrBtn.onclick = function(e) {
            e.stopPropagation();
            clearChat();
        };
        sendBtn.onclick = function() { sendMessage(); };

        chatInput.onkeydown = function(e) {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                sendMessage();
            }
        };
        chatInput.oninput = function() {
            chatInput.style.height = 'auto';
            chatInput.style.height = Math.min(chatInput.scrollHeight, 80) + 'px';
        };

        // 快捷指令点击
        quickBar.onclick = function(e) {
            if (e.target.classList.contains('ai-qi')) {
                chatInput.value = e.target.textContent.replace(/^.\s*/, '');
                sendMessage();
            }
        };

        // 欢迎消息
        welcomeMsg();
    }

    function welcomeMsg() {
        addMsg('assistant',
            '\u4f60\u597d\uff01\u6211\u662f\u4e09\u661f\u4e8b\u4e1a\u90e8\u7684 AI \u667a\u80fd\u52a9\u624b\u3002\n\n' +
            '\u6211\u53ef\u4ee5\u5e2e\u4f60\uff1a\n' +
            '- \u67e5\u8be2**\u9500\u552e\u6570\u636e\u548c\u95e8\u5e97\u6392\u540d**\n' +
            '- \u76d1\u63a7**\u5e93\u5b58\u9884\u8b66\u548c\u5e93\u9f84**\n' +
            '- \u5bf9\u6bd4**\u4eac\u4e1c/\u4e5d\u673a\u7ade\u54c1\u4ef7\u683c**\n' +
            '- \u67e5\u770b**\u4f1a\u5458\u8ddf\u8fdb\u60c5\u51b5**\n' +
            '- \u641c\u7d22**\u5e97\u9576\u767e\u4e8b\u901a**\n' +
            '- \u63d0\u4f9b**\u7ecf\u8425\u5206\u6790\u5efa\u8bae**\n\n' +
            '\u76f4\u63a5\u8f93\u5165\u95ee\u9898\u6216\u70b9\u51fb\u4e0b\u65b9\u5feb\u6377\u6307\u4ee4\u5f00\u59cb~'
        );
    }

    function addMsg(role, text) {
        var avatarText = role === 'user'
            ? ((window.App && window.App.user && window.App.user.display_name) || 'U').charAt(0)
            : 'AI';

        var bbl = el('div', 'ai-bbl');
        bbl.innerHTML = md(text);

        var av = el('div', 'ai-avatar', avatarText);
        var row = el('div', 'ai-msg ' + role);
        row.appendChild(av);
        row.appendChild(bbl);

        chatMessages.appendChild(row);
        chatMessages.scrollTop = chatMessages.scrollHeight;
        return bbl;
    }

    function openPanel() {
        ensurePanel();
        chatPanel.classList.remove('_hide');
        chatOpen = true;
        setTimeout(function() {
            if (chatInput) chatInput.focus();
        }, 300);
    }

    function closePanel() {
        if (!chatPanel) return;
        chatPanel.classList.add('_hide');
        chatOpen = false;
    }

    function togglePanel() {
        if (chatOpen) {
            closePanel();
        } else {
            openPanel();
        }
    }

    // ── 发送消息 ──
    async function sendMessage() {
        var text = (chatInput.value || '').trim();
        if (!text) return;

        chatInput.value = '';
        chatInput.style.height = 'auto';

        addMsg('user', text);

        // 打字指示器
        var typingRow = el('div', 'ai-msg assistant');
        var typingAv = el('div', 'ai-avatar', 'AI');
        var typingBbl = el('div', 'ai-bbl');
        var dots = el('div', 'ai-typing');
        dots.innerHTML = '<span></span><span></span><span></span>';
        typingBbl.appendChild(dots);
        typingRow.appendChild(typingAv);
        typingRow.appendChild(typingBbl);
        chatMessages.appendChild(typingRow);
        chatMessages.scrollTop = chatMessages.scrollHeight;

        var curBbl = null;
        var fullContent = '';

        if (abortController) abortController.abort();
        abortController = new AbortController();

        try {
            var token = localStorage.getItem('token') || '';
            var resp = await fetch('/api/chat', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': 'Bearer ' + token
                },
                body: JSON.stringify({ message: text, session_id: sessionId }),
                signal: abortController.signal
            });

            if (!resp.ok) {
                var errData = null;
                try { errData = await resp.json(); } catch(ex) {}
                throw new Error((errData && errData.detail) || 'AI \u670d\u52a1\u6682\u65f6\u4e0d\u53ef\u7528');
            }

            var reader = resp.body.getReader();
            var decoder = new TextDecoder();
            var buf = '';

            while (true) {
                var r = await reader.read();
                if (r.done) break;

                buf += decoder.decode(r.value, { stream: true });
                var lines = buf.split('\n');
                buf = lines.pop() || '';

                for (var i = 0; i < lines.length; i++) {
                    if (lines[i].indexOf('data: ') !== 0) continue;
                    try {
                        var data = JSON.parse(lines[i].slice(6));
                        if (data.type === 'text') {
                            if (!curBbl) {
                                // 移除打字指示器
                                if (typingRow.parentNode) typingRow.parentNode.removeChild(typingRow);
                                curBbl = addMsg('assistant', '');
                            }
                            fullContent += data.content;
                            curBbl.innerHTML = md(fullContent);
                            chatMessages.scrollTop = chatMessages.scrollHeight;
                        } else if (data.type === 'error') {
                            if (typingRow.parentNode) typingRow.parentNode.removeChild(typingRow);
                            addMsg('assistant', '\u26a0\ufe0f ' + data.content);
                        }
                    } catch(parseErr) {}
                }
            }

            // 如果没有收到任何文本内容，移除打字指示器
            if (!curBbl && typingRow.parentNode) {
                typingRow.parentNode.removeChild(typingRow);
            }
        } catch (err) {
            if (typingRow.parentNode) typingRow.parentNode.removeChild(typingRow);
            if (err.name !== 'AbortError') {
                addMsg('assistant', '\u26a0\ufe0f \u62b1\u6b49\uff0cAI \u670d\u52a1\u8fde\u63a5\u5931\u8d25\uff1a' + err.message);
            }
        }
    }

    // ── 清除对话 ──
    function clearChat() {
        fetch('/api/chat/session/' + sessionId, {
            method: 'DELETE',
            headers: { 'Authorization': 'Bearer ' + (localStorage.getItem('token') || ''), 'Content-Type': 'application/json' }
        }).catch(function() {});
        if (chatMessages) chatMessages.innerHTML = '';
        welcomeMsg();
    }

    // ── 创建浮动按钮（使用纯 DOM，不用任何 helper）──
    function createButton() {
        var existing = document.getElementById('ai-float-btn');
        if (existing) {
            // 已存在，确保事件绑定
            existing.addEventListener('click', function(e) {
                e.preventDefault();
                e.stopPropagation();
                togglePanel();
            }, true);  // capture 阶段，优先级最高
            return existing;
        }

        injectCSS();  // 先注入样式

        var btn = document.createElement('button');
        btn.id = 'ai-float-btn';
        btn.className = 'ai-fbtn pulse';
        btn.textContent = '\ud83e\udd16';  // 🤖
        btn.setAttribute('aria-label', 'AI \u667a\u80fd\u52a9\u624b');
        btn.style.outline = 'none';

        // 小绿点
        var dot = document.createElement('span');
        dot.className = 'ai-fbdot';
        btn.appendChild(dot);

        // 方式1：onclick 直接绑定（最高兼容性）
        btn.onclick = function(e) {
            e && e.preventDefault && e.preventDefault();
            e && e.stopImmediatePropagation && e.stopImmediatePropagation();
            console.log('[AI] button onclick fired!');
            togglePanel();
        };

        // 方式2：addEventListener 兜底
        btn.addEventListener('click', function(e) {
            console.log('[AI] button addEventListener click!');
            togglePanel();
        }, true);  // capture phase

        // 方式3：mousedown 兜底（防止某些情况 click 不触发）
        btn.addEventListener('mousedown', function(e) {
            console.log('[AI] button mousedown!');
        }, true);

        document.body.appendChild(btn);
        console.log('[AI] button created:', btn.id, 'pos:', btn.style.position);

        return btn;
    }

    // ── 全局文档级点击兜底（终极方案）──
    function setupGlobalFallback() {
        document.addEventListener('click', function(e) {
            var target = e.target;
            // 向上查找最多 3 层
            for (var i = 0; i < 3 && target; i++) {
                if (target.id === 'ai-float-btn' || target.className && typeof target.className === 'string' && target.className.indexOf('ai-fbtn') >= 0) {
                    console.log('[AI] Global fallback catch! target=', target.tagName, target.id, target.className);
                    e.preventDefault();
                    e.stopPropagation();
                    e.stopImmediatePropagation();
                    togglePanel();
                    return false;
                }
                target = target.parentElement;
            }
        }, true);  // capture phase
    }

    // ── 初始化入口 ──
    function init() {
        try {
            console.log('[AI] init start');
            createButton();
            setupGlobalFallback();
            console.log('[AI] init done');
        } catch(err) {
            console.error('[AI] init ERROR:', err.message, err.stack);
        }
    }

    // 启动
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }

})();
