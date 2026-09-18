/**
 * 工作看板服务器
 * - 静态服务：board-site 目录（index.html）
 * - 数据 API：GET/POST /api/data，统一存储到 data.json
 *   这样无论从本地地址还是公网隧道访问，读写的都是同一份数据
 */
const http = require('http');
const fs = require('fs');
const path = require('path');

const ROOT = __dirname;
const DATA_FILE = path.join(ROOT, 'data.json');
const PORT = 8899;

const MIME = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.png': 'image/png',
  '.svg': 'image/svg+xml',
  '.ico': 'image/x-icon',
};

const server = http.createServer((req, res) => {
  const url = new URL(req.url, 'http://' + (req.headers.host || 'localhost'));
  const p = url.pathname;

  // 统计带进度/非待办的任务数（用于冲突检测）
  function countActive(data) {
    if (!Array.isArray(data)) return 0;
    return data.reduce((sum, col) => sum + (col.tasks || []).filter(t => t.progress > 0 || (t.status && t.status !== 'todo')).length, 0);
  }

  // ===== API: GET /api/data =====
  if (p === '/api/data' && req.method === 'GET') {
    fs.readFile(DATA_FILE, 'utf8', (err, content) => {
      res.writeHead(200, {
        'Content-Type': 'application/json; charset=utf-8',
        'Cache-Control': 'no-store',
      });
      if (err || !content) {
        res.end(JSON.stringify({ data: null, updatedAt: 0 }));
      } else {
        res.end(content);
      }
    });
    return;
  }

  // ===== API: POST /api/data =====
  if (p === '/api/data' && req.method === 'POST') {
    let body = '';
    req.on('data', chunk => { body += chunk; if (body.length > 5 * 1024 * 1024) req.destroy(); });
    req.on('end', () => {
      try {
        const parsed = JSON.parse(body);
        const payload = parsed && typeof parsed === 'object' ? parsed : { data: null };
        payload.updatedAt = Date.now(); // 记录本次保存时间，供前端做增量同步

        // 冲突保护：服务器已有较多带进度任务，而提交的数据几乎无进度（本地旧缓存/不完整数据）
        // → 拒绝写入并返回服务器最新数据，防止覆盖用户辛苦更新的进度
        fs.readFile(DATA_FILE, 'utf8', (err, content) => {
          const cur = (err || !content) ? null : JSON.parse(content);
          const curActive = countActive((cur && cur.data) || []);
          const newActive = countActive(payload.data || []);
          if (curActive >= 2 && newActive * 2 < curActive) {
            res.writeHead(409, { 'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'no-store' });
            res.end(JSON.stringify({
              error: 'conflict: payload too incomplete',
              data: (cur && cur.data) || null,
              updatedAt: (cur && cur.updatedAt) || 0
            }));
            return;
          }
          fs.writeFile(DATA_FILE, JSON.stringify(payload, null, 2), err2 => {
            if (err2) {
              res.writeHead(500, { 'Content-Type': 'application/json; charset=utf-8' });
              res.end(JSON.stringify({ error: 'write failed' }));
              return;
            }
            res.writeHead(200, { 'Content-Type': 'application/json; charset=utf-8' });
            res.end(JSON.stringify({ ok: true, updatedAt: payload.updatedAt }));
          });
        });
      } catch (e) {
        res.writeHead(400, { 'Content-Type': 'application/json; charset=utf-8' });
        res.end(JSON.stringify({ error: 'bad json' }));
      }
    });
    return;
  }

  // ===== Static files =====
  let filePath;
  if (p === '/') {
    filePath = path.join(ROOT, 'index.html');
  } else {
    filePath = path.normalize(path.join(ROOT, decodeURIComponent(p)));
  }
  if (!filePath.startsWith(ROOT)) {
    res.writeHead(403);
    res.end('Forbidden');
    return;
  }

  fs.readFile(filePath, (err, content) => {
    if (err) {
      res.writeHead(404);
      res.end('Not Found');
      return;
    }
    const ext = path.extname(filePath).toLowerCase();
    res.writeHead(200, {
      'Content-Type': MIME[ext] || 'application/octet-stream',
      'Cache-Control': 'no-store',
    });
    res.end(content);
  });
});

server.listen(PORT, '0.0.0.0', () => {
  console.log('Board server running at http://0.0.0.0:' + PORT);
});
