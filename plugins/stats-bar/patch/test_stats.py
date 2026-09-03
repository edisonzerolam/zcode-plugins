#!/usr/bin/env python3
"""test_stats.py — 独立验证 stats-bar 数据管线（不依赖 asar 补丁）。

用法:
  python test_stats.py                     # 用最新会话
  python test_stats.py <session_id>         # 指定会话
"""
import sqlite3
import sys
import os
import json


def get_db_path():
    home = os.path.expanduser("~")
    try:
        setting = json.load(open(os.path.join(home, ".zcode", "v2", "setting.json"), encoding="utf-8"))
        base = setting.get("dataBaseDir") or setting.get("dataBasePath")
        if base:
            p = os.path.join(base, ".zcode", "cli", "db", "db.sqlite")
            if os.path.isfile(p):
                return p
    except Exception:
        pass
    candidates = [
        os.path.join(home, ".zcode", "cli", "db", "db.sqlite"),
    ]
    for c in candidates:
        if os.path.isfile(c):
            return c
    return None


DB_PATH = get_db_path()


def compute(sid):
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    c = con.cursor()

    if sid:
        t = c.execute("SELECT id, title FROM session WHERE id=?", [sid]).fetchone()
        if not t:
            return {"error": "session not found"}
        session_id, title = t["id"], t["title"]
    else:
        t = c.execute("SELECT id, title FROM session WHERE time_compacting IS NULL AND time_archived IS NULL ORDER BY time_updated DESC LIMIT 1").fetchone()
        if not t:
            return {"error": "no session"}
        session_id, title = t["id"], t["title"]

    mu = c.execute("""
        SELECT
          COUNT(*) AS n,
          CAST(SUM(duration_ms) AS REAL) AS llm_ms,
          COALESCE(SUM(CASE WHEN output_tokens > 0 AND time_to_first_token_ms IS NOT NULL
                            THEN duration_ms - time_to_first_token_ms ELSE 0 END), 0) AS decode_ms,
          COALESCE(SUM(COALESCE(time_to_first_token_ms,0)),0) AS ttf_ms,
          SUM(CASE WHEN output_tokens > 0 THEN output_tokens ELSE 0 END) AS out_tok,
          SUM(COALESCE(input_tokens,0)) AS in_tok,
          SUM(COALESCE(cache_read_input_tokens,0)) AS cr,
          SUM(COALESCE(cache_creation_input_tokens,0)) AS cw
        FROM model_usage
        WHERE session_id=? AND query_source='main_turn' AND status='completed'
    """, [session_id]).fetchone()

    tool = c.execute("""
        SELECT COUNT(*) AS n, COALESCE(SUM(COALESCE(duration_ms,0)),0) AS ms
        FROM tool_usage WHERE session_id=?
    """, [session_id]).fetchone()

    rounds = c.execute("""
        SELECT COUNT(DISTINCT turn_id) AS n
        FROM turn_usage WHERE session_id=? AND status='completed'
    """, [session_id]).fetchone()

    n = mu["n"] or 0
    llm_ms = mu["llm_ms"] or 0
    decode_ms = mu["decode_ms"] or 0
    ttf_ms = mu["ttf_ms"] or 0
    out_tok = mu["out_tok"] or 0
    in_tok = mu["in_tok"] or 0
    cr = mu["cr"] or 0
    cw = mu["cw"] or 0
    denom = in_tok  # DSH: uncached + cr + cw = in_tok
    cache_hit = round(cr / denom * 100) if denom else 0
    throughput = (out_tok / (decode_ms / 1000)) if decode_ms > 0 else 0
    avg_ttf = (ttf_ms / n) if n else 0

    return {
        "sessionId": session_id,
        "title": title,
        "rounds": rounds["n"] or 0,
        "steps": n,
        "llmMs": llm_ms,
        "decodeMs": decode_ms,
        "toolMs": tool["ms"] or 0,
        "avgTtft": avg_ttf,
        "throughput": throughput,
        "cacheHit": cache_hit,
        "inputTokens": in_tok,
        "outputTokens": out_tok,
        "ready": True,
    }


def fmt_tok(n):
    if n >= 1e6: return f"{n/1e6:.1f}".rstrip("0").rstrip(".") + "M"
    if n >= 1e3: return f"{n/1e3:.1f}".rstrip("0").rstrip(".") + "K"
    return str(n)


def fmt_dur(ms):
    if ms < 1000: return f"{ms/1000:.1f}s"
    m = int(ms // 60000)
    s = int(round((ms % 60000) / 1000))
    return f"{m}m{s}s" if m else f"{s}s"


def fmt_ms(ms):
    if ms < 1000: return f"{ms/1000:.1f}s"
    return f"{round(ms/1000)}s"


def fmt_tps(n):
    if n >= 10: return f"{round(n)} tok/s"
    return f"{n:.1f} tok/s"


def render(s):
    parts = []
    parts.append(f"{s['rounds']} 轮 · {s['steps']} 步")
    t = []
    if s["llmMs"] > 0: t.append(f"LLM {fmt_dur(s['llmMs'])}")
    if s["toolMs"] > 0: t.append(f"工具调用 {fmt_dur(s['toolMs'])}")
    if t: parts.append(" · ".join(t))
    sp = []
    if s["avgTtft"] > 0: sp.append(f"首 token 平均 {fmt_ms(s['avgTtft'])}")
    if s["throughput"] > 0: sp.append(fmt_tps(s["throughput"]))
    if sp: parts.append(" · ".join(sp))
    parts.append(f"缓存命中 {s['cacheHit']}%")
    parts.append(f"输入 {fmt_tok(s['inputTokens'])} tok · 输出 {fmt_tok(s['outputTokens'])} tok")
    return " | ".join(parts)


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if not DB_PATH:
        print("db.sqlite 未找到", file=sys.stderr)
        return 1
    print(f"db: {DB_PATH}")
    sid = sys.argv[1] if len(sys.argv) > 1 else None
    s = compute(sid)
    if s.get("error"):
        print(f"error: {s['error']}")
        return 1
    print(f"session: {s['sessionId']}")
    print(f"title: {s['title']}")
    print()
    print(render(s))
    print()
    print("--- raw metrics ---")
    for k in ("rounds", "steps", "llmMs", "decodeMs", "toolMs", "avgTtft",
              "throughput", "cacheHit", "inputTokens", "outputTokens"):
        v = s[k]
        if isinstance(v, float):
            print(f"  {k} = {v:.2f}")
        else:
            print(f"  {k} = {v}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
