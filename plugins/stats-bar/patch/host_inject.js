// ZC_STATS_BAR_PATCH_V1 begin
import _zcsbHttp from "node:http";
import _zcsbPath from "node:path";
import _zcsbFsp from "node:fs/promises";
(function () {
  if (globalThis.__ZC_STATS_BAR_PATCHED__) return;
  globalThis.__ZC_STATS_BAR_PATCHED__ = true;
  const SENTINEL = "ZC_STATS_BAR_PATCH_V1";
  const ZC_PORT = parseInt(process.env.ZCODE_STATS_BAR_PORT || "", 10) || 45200;
  const ZC_SQL = /*__ZCSB_QUERIES__*/ null;
  (async function init() {
    let _zcsbSqlite = null;
    let fallbackDbs = null;
    async function loadSql() {
      if (_zcsbSqlite) return _zcsbSqlite;
      try { _zcsbSqlite = await import("node:sqlite"); return _zcsbSqlite; }
      catch {}
      return null;
    }
    async function findFallbackDbs() {
      if (fallbackDbs) return fallbackDbs;
      const found = new Set();
      const env = process.env.ZCODE_STATS_DB_PATH;
      if (env) { try { await _zcsbFsp.access(env, 0); found.add(env); } catch {} }
      try {
        const sp = _zcsbPath.join(process.env.USERPROFILE || "", ".zcode", "v2", "setting.json");
        const s = JSON.parse(await _zcsbFsp.readFile(sp, "utf-8"));
        const base = s.dataBaseDir || s.dataBasePath || "";
        if (base) {
          const p = _zcsbPath.join(base, ".zcode", "cli", "db", "db.sqlite");
          try { await _zcsbFsp.access(p, 0); found.add(p); } catch {}
        }
      } catch {}
      try {
        const p = _zcsbPath.join(process.env.USERPROFILE || "", ".zcode", "cli", "db", "db.sqlite");
        try { await _zcsbFsp.access(p, 0); found.add(p); } catch {}
      } catch {}
      fallbackDbs = [...found];
      return fallbackDbs;
    }
    async function resolveDb(ws) {
      if (ws) {
        const p = _zcsbPath.join(ws, ".zcode", "cli", "db", "db.sqlite");
        try { await _zcsbFsp.access(p, 0); return p; } catch {}
      }
      return findFallbackDbs();
    }
    function send(res, code, obj, cors) {
      const h = { "content-type": "application/json; charset=utf-8" };
      if (cors) {
        h["access-control-allow-origin"] = "*";
        h["access-control-allow-headers"] = "x-zc-stats-bar,content-type";
      }
      res.writeHead(code, h);
      res.end(JSON.stringify(obj));
    }
    function guard(req, res) {
      if (req.headers["x-zc-stats-bar"] !== SENTINEL) { send(res, 403, { error: "forbidden" }); return false; }
      return true;
    }
    function empty() {
      return { sessionId: null, title: null, rounds: 0, steps: 0, llmMs: 0, toolMs: 0, avgTtft: 0, throughput: 0, cacheHit: 0, inputTokens: 0, outputTokens: 0, ready: false };
    }
    function fillStats(res, handle, sid) {
      const mu = handle.prepare(ZC_SQL.mu).get({ q: sid });
      const tool = handle.prepare(ZC_SQL.tool).get({ q: sid });
      const rounds = handle.prepare(ZC_SQL.rounds).get({ q: sid });
      const n = mu.n || 0;
      if (n === 0) return false;
      const inT = mu.in_tok || 0;
      const cr = mu.cr || 0;
      const outT = mu.out_tok || 0;
      const llmMs = mu.llm_ms || 0;
      const decodeMs = mu.decode_ms || 0;
      const ttfMs = mu.ttf_ms || 0;
      res.rounds = rounds.n || 0;
      res.steps = n;
      res.llmMs = llmMs;
      res.avgTtft = n ? (ttfMs / n) : 0;
      res.throughput = decodeMs > 0 ? (outT / (decodeMs / 1000)) : 0;
      res.cacheHit = inT > 0 ? Math.round(cr / inT * 100) : 0;
      res.inputTokens = inT;
      res.outputTokens = outT;
      res.toolMs = tool.ms || 0;
      res.ready = true;
      return true;
    }
    async function compute(sid, ws) {
      const sqlite = await loadSql();
      if (!sqlite) return Object.assign({}, empty(), { error: "node:sqlite unavailable" });
      const dbOrPaths = await resolveDb(ws);
      const dbList = typeof dbOrPaths === "string" ? [dbOrPaths] : dbOrPaths;
      if (!dbList.length) return Object.assign({}, empty(), { error: "db not found" });
      const res = empty();
      for (const dbPath of dbList) {
        let handle = null;
        try {
          handle = new sqlite.DatabaseSync(dbPath);
          if (sid) {
            const t = handle.prepare(ZC_SQL.titleById).get({ q: sid });
            if (t) { res.title = t.title; res.sessionId = sid; }
            if (res.sessionId && fillStats(res, handle, sid)) break;
            if (res.sessionId) break;
          } else {
            const t = handle.prepare(ZC_SQL.latestSession).get();
            if (t && fillStats(res, handle, t.id)) {
              res.sessionId = t.id;
              res.title = t.title;
              break;
            }
          }
        } catch (e) {
          console.warn("[stats-bar] db error:", dbPath, e && e.message);
        } finally {
          try { if (handle) handle.close(); } catch {}
        }
      }
      return res;
    }
    async function handler(req, res) {
      if (req.method === "OPTIONS") { res.writeHead(204, { "access-control-allow-origin": "*" }); res.end(); return; }
      const url = (req.url || "").split("?")[0];
      if (url === "/stats/ping") { send(res, 200, { ok: true, sentinel: SENTINEL }); return; }
      if (!guard(req, res)) return;
      const m = /^\/stats\/(sess_[a-f0-9-]+)$/.exec(url);
      const sid = m ? m[1] : null;
      let ws = null;
      try {
        const u = new URL(req.url, "http://localhost");
        ws = u.searchParams.get("ws") || null;
      } catch {}
      try {
        const stats = await compute(sid, ws);
        send(res, 200, stats, true);
      } catch (e) {
        send(res, 500, { error: (e && e.message) || String(e) }, true);
      }
    }
    const srv = _zcsbHttp.createServer(handler);
    srv.on("error", e => console.warn("[stats-bar] server error:", e.message));
    srv.listen(ZC_PORT, "127.0.0.1", () => {
      console.info("[stats-bar] stats routes on :%d (%s)", ZC_PORT, SENTINEL);
    });
  })();
})();
// ZC_STATS_BAR_PATCH_V1 end
