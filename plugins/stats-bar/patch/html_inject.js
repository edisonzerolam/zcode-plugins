<script>/*ZC_STATS_BAR_PATCH_V1*/
(function () {
  if (window.__zcsbInited) return;
  window.__zcsbInited = true;
  const SENTINEL = "ZC_STATS_BAR_PATCH_V1";
  let BASE = null;
  let bar = null;
  let hidden = false;
  let lastSid = null;

  function readColor() {
    try {
      const b = getComputedStyle(document.body);
      return [b.backgroundColor, b.color];
    } catch { return null; }
  }
  function createBar() {
    const c = readColor() || ["rgba(20,22,24,0.85)", "rgba(230,235,240,0.9)"];
    bar = document.createElement("div");
    bar.id = "zcsb-stats-bar";
    bar.style.cssText = "position:absolute;display:none;align-items:center;justify-content:center;font:12px/1 system-ui,-apple-system,'Segoe UI',sans-serif;background:" + c[0] + ";color:" + c[1] + ";border:1px solid rgba(255,255,255,0.08);border-radius:8px;z-index:2147483640;padding:0 16px;cursor:pointer;user-select:none;white-space:nowrap;box-sizing:border-box;overflow:hidden;text-overflow:ellipsis";
    bar.title = "会话用量 · 单击刷新 · 双击隐藏";
    bar.innerHTML = '<span class="zcsb-content"></span>';
    bar.addEventListener("click", refresh);
    bar.addEventListener("dblclick", function () { hidden = !hidden; bar.style.display = hidden ? "none" : "flex"; });
    document.body.appendChild(bar);
    attachBar();
  }
  function attachBar() {
    if (!bar) return false;
    try {
      var dockContent = document.querySelector('[data-v4-composer-dock-content]');
      if (dockContent) {
        if (bar.parentElement !== dockContent) {
          dockContent.appendChild(bar);
        }
        bar.style.position = "absolute";
        bar.style.left = "50%";
        bar.style.right = "auto";
        bar.style.top = "auto";
        bar.style.bottom = "calc(100% + 4px)";
        bar.style.transform = "translateX(-50%)";
        bar.style.width = "";
        bar.style.maxWidth = "100%";
        bar.style.margin = "0";
        return true;
      }
    } catch {}
    // 回退：0.16.x 若 composer dock DOM 变化找不到锚点，固定在窗口底部居中，保证 bar 仍可见。
    try {
      if (bar.parentElement !== document.body) document.body.appendChild(bar);
      bar.style.position = "fixed";
      bar.style.left = "50%";
      bar.style.right = "auto";
      bar.style.top = "auto";
      bar.style.bottom = "8px";
      bar.style.transform = "translateX(-50%)";
      bar.style.width = "";
      bar.style.maxWidth = "90%";
      bar.style.margin = "0";
      return true;
    } catch { return false; }
  }
  function repositionBar() {
    attachBar();
  }
  function getActiveSessionId() {
    try {
      var el = document.querySelector("[data-session-id]");
      if (el) {
        var sid = el.getAttribute("data-session-id");
        if (sid && sid !== "draft" && /^sess_[a-f0-9-]+$/.test(sid)) return sid;
        if (sid === "draft") return "__draft__";
        return null;
      }
    } catch {}
    return null;
  }
  function detectWorkspace() {
    try {
      for (var i = 0; i < localStorage.length; i++) {
        var key = localStorage.key(i);
        if (key && key.indexOf("zcode-v4-last-session:v1:") === 0) {
          var ws = key.substring("zcode-v4-last-session:v1:".length);
          if (ws) return ws;
        }
      }
    } catch {}
    return null;
  }
  function fmtTok(n) {
    if (n >= 1e6) return (n / 1e6).toFixed(1).replace(/\.0$/, "") + "M";
    if (n >= 1e3) return (n / 1e3).toFixed(1).replace(/\.0$/, "") + "K";
    return String(n);
  }
  function fmtDur(ms) {
    if (ms < 1000) return (ms / 1000).toFixed(1) + "s";
    const m = Math.floor(ms / 60000);
    const s = Math.round((ms % 60000) / 1000);
    return m > 0 ? m + "m" + s + "s" : s + "s";
  }
  function fmtMs(ms) {
    if (ms < 1000) return (ms / 1000).toFixed(1) + "s";
    return Math.round(ms / 1000) + "s";
  }
  function fmtTps(n) {
    if (n >= 10) return Math.round(n) + " tok/s";
    return n.toFixed(1) + " tok/s";
  }
  function render(s, pinned) {
    if (!bar) createBar();
    attachBar();
    const content = bar.querySelector(".zcsb-content");
    if (!s.ready || s.steps === 0) { bar.style.display = "none"; return; }
    const parts = [];
    parts.push(s.rounds + " \u8f6e \u00b7 " + s.steps + " \u6b65");
    const t = [];
    if (s.llmMs > 0) t.push("LLM " + fmtDur(s.llmMs));
    if (s.toolMs > 0) t.push("\u5de5\u5177\u8c03\u7528 " + fmtDur(s.toolMs));
    if (t.length) parts.push(t.join(" \u00b7 "));
    const sp = [];
    if (s.avgTtft > 0) sp.push("\u9996 token " + fmtMs(s.avgTtft));
    if (s.throughput > 0) sp.push(fmtTps(s.throughput));
    if (sp.length) parts.push(sp.join(" \u00b7 "));
    parts.push("\u7f13\u5b58\u547d\u4e2d " + s.cacheHit + "%");
    parts.push("\u8f93\u5165 " + fmtTok(s.inputTokens) + " \u00b7 \u8f93\u51fa " + fmtTok(s.outputTokens));
    // pinned=false 表示取不到当前会话 id（DOM 变化兜底），显示的是库内最近会话，加前缀如实标注
    content.textContent = (pinned === false ? "\u6700\u8fd1\u00b7" : "") + parts.join(" | ");
    bar.style.display = hidden ? "none" : "flex";
  }
  function candidates() {
    const list = [];
    if (location.protocol === "http:" || location.protocol === "https:") list.push(location.origin);
    for (let p = 45200; p <= 45209; p++) list.push("http://127.0.0.1:" + p);
    return list;
  }
  async function findBase() {
    if (BASE) return BASE;
    for (const b of candidates()) {
      try {
        const r = await fetch(b + "/stats/ping", { headers: { "x-zc-stats-bar": SENTINEL } });
        const j = await r.json();
        if (j && j.sentinel === SENTINEL) { BASE = b; return BASE; }
      } catch {}
    }
    return null;
  }
  async function refresh() {
    if (hidden) { hidden = false; }
    if (!BASE) { BASE = await findBase(); }
    if (!BASE) return;
    var sid = getActiveSessionId();
    if (sid === "__draft__") { if (bar) bar.style.display = "none"; return; }
    var pinned = !!sid;
    var ws = detectWorkspace();
    lastSid = sid;
    let url = pinned ? BASE + "/stats/" + sid : BASE + "/stats/latest";
    if (ws) url += "?ws=" + encodeURIComponent(ws);
    try {
      const r = await fetch(url, { headers: { "x-zc-stats-bar": SENTINEL } });
      if (!r.ok) return;
      const j = await r.json();
      render(j, pinned);
    } catch {}
  }
  createBar();
  refresh().catch(() => {});
  setInterval(refresh, 3000);
  window.addEventListener("resize", repositionBar);
  window.addEventListener("fullscreenchange", repositionBar);
  window.addEventListener("fullscreenerror", repositionBar);
  try {
    var reattachMo = new MutationObserver(function () {
      var dc = document.querySelector('[data-v4-composer-dock-content]');
      if (bar && dc && bar.parentElement !== dc) attachBar();
    });
    var dockObserve = function () {
      var dc = document.querySelector('[data-v4-composer-dock-content]');
      if (dc) reattachMo.observe(dc, { childList: true, subtree: true });
    };
    dockObserve();
    var tryCount = 0;
    var waitForDock = setInterval(function () {
      var dc = document.querySelector('[data-v4-composer-dock-content]');
      if (dc || ++tryCount > 30) {
        clearInterval(waitForDock);
        dockObserve();
        attachBar();
      }
    }, 1000);
  } catch {}
  try {
    var sessionMo = new MutationObserver(function () {
      var el = document.querySelector("[data-session-id]");
      if (el) {
        var sid = el.getAttribute("data-session-id");
        if (sid === "draft") { if (bar) bar.style.display = "none"; return; }
        if (sid && sid !== lastSid) refresh();
      }
    });
    sessionMo.observe(document.body, { attributes: true, subtree: true, attributeFilter: ["data-session-id"] });
  } catch {}
})();
</script>
