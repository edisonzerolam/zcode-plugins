#!/usr/bin/env node
// stats-bar MCP server（stdio，JSON-RPC 2.0，LSP Content-Length 帧）
// 只读查询 ZCode 会话用量统计。数据口径单一事实源：../compute.mjs
// 工具：stats_session / stats_latest / stats_schema
import { computeStats } from "../compute.mjs";

const SERVER_INFO = { name: "stats-bar", version: "0.4.0" };
const PROTOCOL_VERSION = "2024-11-05";

const TOOLS = [
  {
    name: "stats_session",
    description: "查询指定 ZCode 会话的用量统计（轮数/步数/LLM 与工具耗时/首 token 延迟/tok/s/缓存命中/token 用量）。不传 sessionId 时返回当前活动库的最新会话。",
    inputSchema: {
      type: "object",
      properties: {
        sessionId: { type: "string", description: "会话 id（sess_ 前缀）。留空则返回最新会话。" },
        workspace: { type: "string", description: "工作区绝对路径，用于优先解析 <ws>/.zcode/cli/db/db.sqlite。" }
      },
      additionalProperties: false
    }
  },
  {
    name: "stats_latest",
    description: "返回当前活动库中最近更新的会话及其用量统计。",
    inputSchema: {
      type: "object",
      properties: {
        workspace: { type: "string", description: "工作区绝对路径，用于库解析。" }
      },
      additionalProperties: false
    }
  },
  {
    name: "stats_schema",
    description: "返回 stats-bar 各统计字段的口径说明（数据字典），用于解释每个数字怎么算的。",
    inputSchema: { type: "object", properties: {}, additionalProperties: false }
  }
];

const SCHEMA_TEXT = [
  "口径单一事实源：compute.mjs（与 UI bar 共用）。全部只读，query_source='main_turn' AND status='completed'。",
  "rounds      = max(turn_usage.completed 的 distinct turn_id, model_usage.main_turn 的 distinct turn_id)。后者兜底进行中回合（turn_usage 回合结束才落盘）。",
  "steps       = model_usage 行数（主回合、completed）。",
  "llmMs       = SUM(duration_ms)，LLM 总耗时（含首 token + decode）。",
  "toolMs/toolN= tool_usage 的总耗时/次数。",
  "avgTtft     = 首 token 平均延迟。取 (first_token_at - started_at)，仅统计 first_token_at 非空行（finish_reason='tool-calls' 的行无首 token，恒空，全库覆盖约 78.5%，故不纳入分母）。",
  "throughput  = decode 速率 tok/s。分子=first_token_at 非空且 output_tokens>0 行的 output_tokens 之和；分母=同行 (duration_ms - ttft) 之和。集合对称，避免高估。",
  "cacheHit    = cache_read_input_tokens / input_tokens * 100（input_tokens 已含缓存段）。",
  "inputTokens = SUM(input_tokens)。outputTokens = SUM(output_tokens where >0)。",
  "库选择      = 多库时按 lastActivity（model_usage∪turn_usage 的 max started_at）最大者选权威库，不合并（D 盘库是前缀快照，union 会重复计数）。",
  "ttftCovered = first_token_at 非空行数 / steps，反映该会话 ttft 覆盖度。",
  "查询入口    = 底部状态条（asar 薄壳）、/stats 命令与本 MCP 工具，三者同口径。薄壳由 patch/elevate-install.cmd 提权安装（一次 UAC），ZCodeStatsBarSelfHeal 登录任务在 ZCode 更新后自动重打。"
].join("\n");

let buffer = "";
let nextId = 1;

function send(obj) {
  const s = JSON.stringify(obj);
  process.stdout.write("Content-Length: " + Buffer.byteLength(s, "utf-8") + "\r\n\r\n" + s);
}
function notify(method, params) {
  send({ jsonrpc: "2.0", method, params });
}
function result(id, result) {
  send({ jsonrpc: "2.0", id, result });
}
function error(id, code, message) {
  send({ jsonrpc: "2.0", id, error: { code, message } });
}

function callStats(args) {
  const out = computeStats(args.sessionId || null, args.workspace || null);
  return { content: [{ type: "text", text: JSON.stringify(out, null, 2) }] };
}

function handleRequest(msg) {
  const { id, method, params } = msg;
  switch (method) {
    case "initialize":
      return result(id, {
        protocolVersion: PROTOCOL_VERSION,
        capabilities: { tools: { listChanged: false } },
        serverInfo: SERVER_INFO
      });
    case "notifications/initialized":
      return null; // 通知，无响应
    case "ping":
      return result(id, {});
    case "tools/list":
      return result(id, { tools: TOOLS });
    case "tools/call": {
      const name = params && params.name;
      const args = (params && params.arguments) || {};
      try {
        let r;
        if (name === "stats_session") r = callStats(args);
        else if (name === "stats_latest") r = callStats({ workspace: args.workspace });
        else if (name === "stats_schema") r = { content: [{ type: "text", text: SCHEMA_TEXT }] };
        else return error(id, -32602, "unknown tool: " + name);
        return result(id, r);
      } catch (e) {
        return result(id, { content: [{ type: "text", text: "error: " + (e && e.message) }], isError: true });
      }
    }
    case "resources/list":
      return result(id, { resources: [] });
    case "prompts/list":
      return result(id, { prompts: [] });
    default:
      // 未知方法：有 id 返回 method not found，无 id 视为通知忽略
      if (id !== undefined && id !== null) return error(id, -32601, "method not found: " + method);
      return null;
  }
}

process.stdin.setEncoding("utf-8");
process.stdin.on("data", (chunk) => {
  buffer += chunk;
  for (;;) {
    const m = buffer.match(/^Content-Length: (\d+)\r\n\r\n/);
    if (!m) {
      // 容错：客户端用单个 \n 或无头时，尝试按裸 JSON 解析
      const bare = buffer.match(/^\s*(\{[\s\S]*\})\s*$/);
      if (bare && buffer.length < 200000) {
        buffer = "";
        try { handleRequest(JSON.parse(bare[1])); } catch { /* ignore */ }
      }
      return;
    }
    const len = +m[1];
    const start = m[0].length;
    if (buffer.length < start + len) return; // 等剩余字节
    const body = buffer.slice(start, start + len);
    buffer = buffer.slice(start + len);
    try {
      handleRequest(JSON.parse(body));
    } catch (e) {
      // 协议错误尽量回报
      send({ jsonrpc: "2.0", id: null, error: { code: -32700, message: "parse error: " + e.message } });
    }
  }
});
process.stdin.on("end", () => process.exit(0));

process.stderr.write("[stats-bar-mcp] ready\n");
