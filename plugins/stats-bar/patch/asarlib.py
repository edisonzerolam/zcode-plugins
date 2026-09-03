#!/usr/bin/env python3
"""asarlib.py — asar 字节操作库（复用 fetch-models 实现，单一事实源）。"""
import hashlib
import json
import os
import re
import shutil
import struct
import tempfile

BLOCK_SIZE = 4 * 1024 * 1024
TS_DIR_RE = re.compile(r"^\d{8}-\d{6}$")
BACKUP_DIR_NAME = "backups"
BACKUP_KEEP = 2


def ensure_within(base_dir, target):
    base_abs = os.path.realpath(os.path.abspath(base_dir))
    target_abs = os.path.realpath(os.path.abspath(target))
    if os.path.commonpath([base_abs, target_abs]) != base_abs:
        raise ValueError("路径越界: 目标不在允许目录内")
    return target_abs


def read_bytes(path):
    with open(path, "rb") as f:
        return f.read()


def write_bytes(path, data):
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), prefix=".tmp-")
    with os.fdopen(fd, "wb") as f:
        f.write(data)
    os.replace(tmp, path)


def write_text(path, text):
    write_bytes(path, text.encode("utf-8"))


def append_text(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(text)


def parse_header(data):
    a, b, c, d = struct.unpack("<4I", data[:16])
    if a != 4:
        raise ValueError("asar 头部魔数不符: {}".format(a))
    hdr = json.loads(data[16:16 + d].decode("utf-8").rstrip("\x00"))
    return hdr, 8 + b, (a, b, c, d)


def walk_files(node, prefix=""):
    for name, entry in node.get("files", {}).items():
        p = prefix + "/" + name if prefix else name
        if "files" in entry:
            yield from walk_files(entry, p)
        else:
            yield p, entry


def file_bytes(data, content_base, entry):
    off = int(entry["offset"])
    return data[content_base + off: content_base + off + entry["size"]]


def compute_integrity(content, template):
    algo = (template or {}).get("algorithm", "SHA256")
    bs = (template or {}).get("blockSize", BLOCK_SIZE)
    h = hashlib.new(algo.lower().replace("-", ""), content).hexdigest()
    blocks = [hashlib.new(algo.lower().replace("-", ""), content[i:i + bs]).hexdigest()
              for i in range(0, len(content), bs)]
    return {"algorithm": algo, "hash": h, "blockSize": bs, "blocks": blocks}


def build_candidate(data, patches):
    hdr, content_base, sizes = parse_header(data)
    want = dict(patches)
    located = {}
    for p, e in walk_files(hdr):
        if p in want and "unpacked" not in e:
            located[p] = e
    if len(located) != len(want):
        raise RuntimeError("补丁目标定位不全: {} / {}".format(sorted(located), sorted(want)))
    new_by_id = {id(located[p]): want[p] for p in located}
    entries = list(walk_files(hdr))
    order = sorted(entries, key=lambda kv: int(kv[1]["offset"]) if "offset" in kv[1] else -1)
    body_parts = []
    pos = 0
    changed = []
    for _, e in order:
        if "unpacked" in e:
            continue
        new = new_by_id.get(id(e))
        old_off = int(e["offset"])
        if new is not None:
            content = new
        else:
            content = data[content_base + old_off: content_base + old_off + e["size"]]
        body_parts.append(content)
        e["offset"] = str(pos)
        e["size"] = len(content)
        if new is not None and "integrity" in e:
            e["integrity"] = compute_integrity(content, e["integrity"])
            changed.append(e.get("zcPatchPath", ""))
        pos += len(content)
    json_new = json.dumps(hdr, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    d2 = len(json_new)
    b_orig, c_orig = sizes[1], sizes[2]
    pad2 = c_orig - 4 - d2
    if pad2 < 0:
        raise ValueError("新 JSON 超过原始 pickle 载荷容量（无法保留原偏移基址）")
    header_new = struct.pack("<4I", 4, b_orig, c_orig, d2) + json_new + b"\x00" * pad2
    if len(header_new) != 8 + b_orig:
        raise ValueError("头部总长与内容基址不一致")
    out = bytearray(header_new)
    for part in body_parts:
        out += part
    return bytes(out), sorted(located.keys())


def count_entry(cand, entry_path, needle):
    hdr, cb, _ = parse_header(cand)
    for p, e in walk_files(hdr):
        if p == entry_path and "unpacked" not in e:
            blob = cand[cb + int(e["offset"]): cb + int(e["offset"]) + e["size"]]
            return blob.count(needle)
    raise RuntimeError("candidate 中找不到 {}".format(entry_path))


def count_all_files(cand):
    hdr, _, _ = parse_header(cand)
    return sum(1 for _ in walk_files(hdr))


def sentinel_files(cand, needle):
    hdr, cb, _ = parse_header(cand)
    hits = []
    for p, e in walk_files(hdr):
        if "unpacked" in e or e.get("size", 0) > 8 * 1024 * 1024:
            continue
        blob = cand[cb + int(e["offset"]): cb + int(e["offset"]) + e["size"]]
        if needle in blob:
            hits.append(p)
    return hits


def contains(data, needle):
    if isinstance(needle, str):
        needle = needle.encode("utf-8")
    return needle in data


def backup_dir(res_dir, ts, pattern):
    if not re.match(pattern, ts):
        raise ValueError("时间戳异常")
    d = ensure_within(res_dir, os.path.join(res_dir, BACKUP_DIR_NAME, ts))
    os.makedirs(d, exist_ok=True)
    return d


def list_backup_dirs(res_dir, pattern):
    root = os.path.join(res_dir, BACKUP_DIR_NAME)
    if not os.path.isdir(root):
        return []
    names = sorted((n for n in os.listdir(root) if re.match(pattern, n)), reverse=True)
    return [ensure_within(root, os.path.join(root, n)) for n in names]


def prune_backups(res_dir, pattern, keep, backup_name):
    for old in list_backup_dirs(res_dir, pattern)[keep:]:
        shutil.rmtree(old, ignore_errors=True)
    return [os.path.join(d, backup_name) for d in list_backup_dirs(res_dir, pattern)]


def copy_file(src, dst):
    shutil.copy2(src, dst)


def lock_probe(path):
    probe = os.path.join(os.path.dirname(path), "app.asar.zcprobe")
    try:
        os.rename(path, probe)
        os.rename(probe, path)
        return True
    except OSError:
        if os.path.exists(probe) and not os.path.exists(path):
            os.rename(probe, path)
        return False


def newest_backup_file(res_dir, pattern, backup_name):
    dirs = list_backup_dirs(res_dir, pattern)
    if not dirs:
        return None
    cand = os.path.join(dirs[0], backup_name)
    return cand if os.path.isfile(cand) else None
