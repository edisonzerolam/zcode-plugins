// ZC_STATS_BAR_PATCH_V1 begin
import _zcsbHttp from "node:http";
import _zcsbPath from "node:path";
import _zcsbFsp from "node:fs/promises";
import { createRequire as _zcsbCreateRequire } from "node:module";
const _zcsbRequire = _zcsbCreateRequire(import.meta.url);
(function () {
  if (globalThis.__ZC_STATS_BAR_PATCHED__) return;
  globalThis.__ZC_STATS_BAR_PATCHED__ = true;
  const SENTINEL = "ZC_STATS_BAR_PATCH_V1";
  const ZC_PORT = parseInt(process.env.ZCODE_STATS_BAR_PORT || "", 10) || 45200;
  (async function init() {
    // ── 共享口径模块 compute.mjs（单一事实源）──
    // 优先 import 插件目录下的 compute.mjs；找不到时回退到内联副本（apply_patch.py 构建时注入）。
    // 这样 UI bar 轮询与 MCP server 用同一份口径逻辑，杜绝两处 SQL 漂移。
    let _zcsbCompute = null;
    async function loadCompute() {
      if (_zcsbCompute) return _zcsbCompute;
      const root = process.env.ZCODE_PLUGIN_ROOT || "";
      const cands = [];
      if (root) cands.push(_zcsbPath.join(root, "compute.mjs"));
      cands.push(_zcsbPath.join(process.env.USERPROFILE || "", "Agent", ".zcode", "plugins", "stats-bar", "compute.mjs"));
      cands.push(_zcsbPath.join(process.env.USERPROFILE || "", ".zcode", "plugins", "stats-bar", "compute.mjs"));
      for (const p of cands) {
        try {
          await _zcsbFsp.access(p, 0);
          _zcsbCompute = await import(p);
          return _zcsbCompute;
        } catch {}
      }
      // 兜底：内联副本（构建时由 apply_patch.py 把 compute.mjs 内容替换进下方占位符）
      _zcsbCompute = /*__ZCSB_COMPUTE_INLINE__*/ null;
      return _zcsbCompute;
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
      return { sessionId: null, title: null, rounds: 0, steps: 0, llmMs: 0, toolMs: 0, toolN: 0, avgTtft: 0, throughput: 0, cacheHit: 0, inputTokens: 0, outputTokens: 0, ttftCovered: 0, ready: false };
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
        const compute = await loadCompute();
        if (!compute || typeof compute.computeStats !== "function") {
          send(res, 500, { error: "compute module unavailable" }, true);
          return;
        }
        const stats = compute.computeStats(sid, ws);
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
