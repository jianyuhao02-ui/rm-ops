// 三星事业部管理平台 - Service Worker v3 (修复缓存 + 增强离线)
const CACHE_NAME = 'samsung-ops-v3';
const API_CACHE = 'samsung-ops-api-v3';

const STATIC_ASSETS = [
  '/',
  '/login',
  '/css/style.css',
  '/js/app.js',
  '/manifest.json',
  '/icons/icon-192.png',
];

// 安装：预缓存核心资源
self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(CACHE_NAME).then(cache => {
      return Promise.allSettled(STATIC_ASSETS.map(url =>
        cache.add(url).catch(() => console.debug('SW: skip cache miss:', url))
      ));
    })
  );
  self.skipWaiting();
});

// 激活：清理旧缓存
self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys().then(keys => {
      return Promise.all(
        keys.filter(k => k !== CACHE_NAME && k !== API_CACHE).map(k => caches.delete(k))
      );
    })
  );
  self.clients.claim();
});

// 请求策略
self.addEventListener('fetch', event => {
  const url = new URL(event.request.url);

  // API GET 请求 → 网络优先，5秒超时回退缓存
  if (url.pathname.startsWith('/api/') && event.request.method === 'GET') {
    event.respondWith(
      Promise.race([
        fetch(event.request).then(response => {
          const clone = response.clone();
          caches.open(API_CACHE).then(cache => cache.put(event.request, clone));
          return response;
        }),
        new Promise((_, reject) => setTimeout(() => reject(new Error('timeout')), 5000))
      ]).catch(() => {
        return caches.match(event.request).then(r => {
          if (r) return r;
          return new Response(JSON.stringify({detail: '网络不可用'}), {
            status: 503,
            headers: {'Content-Type': 'application/json'}
          });
        });
      })
    );
    return;
  }

  // HTML页面 → 网络优先，离线回退缓存
  if (event.request.destination === 'document' ||
      url.pathname === '/' ||
      ['/login','/dashboard','/sales','/inventory','/prices','/staff',
       '/knowledge','/community','/admin','/members','/ai','/attendance',
       '/approval','/tasks'].some(p => url.pathname.startsWith(p))) {
    event.respondWith(
      fetch(event.request)
        .then(response => {
          const clone = response.clone();
          caches.open(CACHE_NAME).then(cache => cache.put(event.request, clone));
          return response;
        })
        .catch(() => caches.match(event.request).then(r => r || caches.match('/')))
    );
    return;
  }

  // 静态资源（JS/CSS/图片/图标）→ 缓存优先
  event.respondWith(
    caches.match(event.request).then(r => r || fetch(event.request).then(response => {
      const clone = response.clone();
      caches.open(CACHE_NAME).then(cache => cache.put(event.request, clone));
      return response;
    }))
  );
});

// 离线状态通知
self.addEventListener('message', event => {
  if (event.data === 'skipWaiting') {
    self.skipWaiting();
  }
});
