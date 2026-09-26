// stats-bar 共享数据口径模块（单一事实源）
// 被 mcp/server.mjs（stdio 工具）与 patch/host_inject.js（HTTP 壳）共同 import，
// 保证 agent 查数与 UI bar 轮询的口径永远一致，消除原先 queries.json 与 host_inject 两处 SQL 的漂移风险。
// 口径要点（2026-09-07 TC-20260907-1 核验）：
//   - ttft 取 (first_token_at - started_at)，不用 time_to_first_token_ms 派生列
//     （该列对 finish_reason='tool-calls' 的行恒空，全库覆盖仅 ~78.5%）
//   - decode 集合对称：仅统计 first_token_at 非空 且 output_tokens>0 的行
//   - rounds = max(turn_usage.completed distinct turn_id, model_usage.main_turn distinct turn_id)
//     （回合进行中 turn_usage 未落盘时由后者兜底，避免活跃会话显示 0 轮）
//   - 库选择：多库时按 lastActivity 最大者选权威库，不合并（D 盘库是前缀快照，union 会重复计数）

import { DatabaseSync } from "node:sqlite";
import { createRequire } from "node:module";
import { join } from "node:path";

const require = createRequire(import.meta.url);

const QUERIES = {
  mu: "SELECT COUNT(*) AS n, SUM(CASE WHEN first_token_at IS NOT NULL THEN 1 ELSE 0 END) AS n_ttft, CAST(SUM(duration_ms) AS REAL) AS llm_ms, COALESCE(SUM(CASE WHEN output_tokens > 0 AND first_token_at IS NOT NULL THEN duration_ms - (first_token_at - started_at) ELSE 0 END), 0) AS decode_ms, COALESCE(SUM(CASE WHEN first_token_at IS NOT NULL THEN first_token_at - started_at ELSE 0 END), 0) AS ttf_ms, SUM(CASE WHEN output_tokens > 0 THEN output_tokens ELSE 0 END) AS out_tok, SUM(CASE WHEN output_tokens > 0 AND first_token_at IS NOT NULL THEN output_tokens ELSE 0 END) AS out_tok_decode, SUM(COALESCE(input_tokens,0)) AS in_tok, SUM(COALESCE(cache_read_input_tokens,0)) AS cr FROM model_usage WHERE session_id=:q AND query_source='main_turn' AND status='completed'",
  tool: "SELECT COUNT(*) AS n, COALESCE(SUM(COALESCE(duration_ms,0)),0) AS ms FROM tool_usage WHERE session_id=:q",
  rounds: "SELECT COUNT(DISTINCT turn_id) AS n FROM turn_usage WHERE session_id=:q AND status='completed'",
  roundsFallback: "SELECT COUNT(DISTINCT turn_id) AS n FROM model_usage WHERE session_id=:q AND query_source='main_turn' AND turn_id IS NOT NULL",
  lastActivity: "SELECT MAX(m) AS ts FROM (SELECT MAX(started_at) AS m FROM model_usage WHERE session_id=:q UNION ALL SELECT MAX(started_at) AS m FROM turn_usage WHERE session_id=:q)",
  titleById: "SELECT title FROM session WHERE id=:q",
  latestSession: "SELECT id, title, time_updated FROM session WHERE time_compacting IS NULL AND time_archived IS NULL ORDER BY time_updated DESC LIMIT 1"
};

export function resolveDbCandidates(ws) {
  const found = new Set();
  const env = process.env.ZCODE_STATS_DB_PATH;
  if (env) {
    found.add(env);
    return [...found];
  }
  if (ws) {
    found.add(join(ws, ".zcode", "cli", "db", "db.sqlite"));
  }
  const base = process.env.ZCODE_STATS_DATA_BASE_DIR || process.env.USERPROFILE || "";
  if (base) {
    const a = join(base, ".zcode", "cli", "db", "db.sqlite");
    const b = join(base, "Agent", ".zcode", "cli", "db", "db.sqlite");
    found.add(a);
    found.add(b);
  }
  return [...found];
}

function openDb(path) {
  return new DatabaseSync(`file:${path}?mode=ro`, { readOnly: true });
}

function existsSync(p) {
  try {
    require("node:fs").accessSync(p, 0);
    return true;
  } catch {
    return false;
  }
}

function lastActivity(handle, sid) {
  const r = handle.prepare(QUERIES.lastActivity).get({ q: sid });
  return (r && r.ts) || 0;
}

function fillStats(res, handle, sid) {
  const mu = handle.prepare(QUERIES.mu).get({ q: sid });
  const tool = handle.prepare(QUERIES.tool).get({ q: sid });
  const rounds = handle.prepare(QUERIES.rounds).get({ q: sid });
  const roundsFb = handle.prepare(QUERIES.roundsFallback).get({ q: sid });
  const n = mu.n || 0;
  if (n === 0) return false;
  const nTtft = mu.n_ttft || 0;
  const decodeMs = mu.decode_ms || 0;
  const outDec = mu.out_tok_decode || 0;
  const inT = mu.in_tok || 0;
  const cr = mu.cr || 0;
  res.rounds = Math.max(rounds.n || 0, roundsFb.n || 0);
  res.steps = n;
  res.llmMs = Math.round(mu.llm_ms || 0);
  res.toolMs = Math.round(tool.ms || 0);
  res.toolN = tool.n || 0;
  res.avgTtft = nTtft ? Math.round((mu.ttf_ms || 0) / nTtft) : 0;
  res.throughput = decodeMs > 0 ? Math.round((outDec / (decodeMs / 1000)) * 10) / 10 : 0;
  res.cacheHit = inT > 0 ? Math.round((cr / inT) * 100) : 0;
  res.inputTokens = inT;
  res.outputTokens = mu.out_tok || 0;
  res.ttftCovered = nTtft;
  res.ready = true;
  return true;
}

function withDb(path, fn) {
  let handle = null;
  try {
    handle = openDb(path);
    return fn(handle);
  } finally {
    try { if (handle) handle.close(); } catch { /* ignore */ }
  }
}

export function computeStats(sid, ws) {
  const res = {
    sessionId: sid || null, title: null, rounds: 0, steps: 0, llmMs: 0, toolMs: 0,
    toolN: 0, avgTtft: 0, throughput: 0, cacheHit: 0, inputTokens: 0, outputTokens: 0,
    ttftCovered: 0, ready: false
  };
  const candidates = resolveDbCandidates(ws).filter(existsSync);
  if (!candidates.length) return Object.assign(res, { error: "db not found" });

  if (sid) {
    let bestDb = null, bestTs = -1, bestTitle = null;
    for (const p of candidates) {
      const t = withDb(p, (h) => {
        const row = h.prepare(QUERIES.titleById).get({ q: sid });
        return row ? { title: row.title, ts: lastActivity(h, sid) } : null;
      });
      if (!t) continue;
      if (t.ts > bestTs) { bestTs = t.ts; bestDb = p; bestTitle = t.title; }
    }
    if (!bestDb) return Object.assign(res, { error: "session not found" });
    res.title = bestTitle;
    res.db = bestDb;
    withDb(bestDb, (h) => fillStats(res, h, sid));
  } else {
    let bestDb = null, bestTs = -1, bestSid = null, bestTitle = null;
    for (const p of candidates) {
      const t = withDb(p, (h) => {
        const row = h.prepare(QUERIES.latestSession).get();
        return row ? { id: row.id, title: row.title, ts: row.time_updated || 0 } : null;
      });
      if (!t) continue;
      if (t.ts > bestTs) { bestTs = t.ts; bestDb = p; bestSid = t.id; bestTitle = t.title; }
    }
    if (!bestDb || !bestSid) return Object.assign(res, { error: "no session" });
    res.sessionId = bestSid;
    res.title = bestTitle;
    res.db = bestDb;
    withDb(bestDb, (h) => fillStats(res, h, bestSid));
  }
  return res;
}

export { QUERIES };
