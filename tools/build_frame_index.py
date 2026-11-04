#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
框条档案索引生成器（多档案版）
==============================
按下面的 ARCHIVES 配置逐个扫描 NAS 目录，各生成一个索引 json，供看板
「档案检索」工具的各子档案做模糊搜索。

用法：
    python3 build_frame_index.py                  # 按 ARCHIVES 全量建档（跳过未挂载/不存在的根目录）
    python3 build_frame_index.py --archive zlk    # 只建某个档案（用 ARCHIVES 里的 id）
    python3 build_frame_index.py --root /path --out /tmp/x.json   # 临时单目录扫描（调试用）
    python3 build_frame_index.py --dry            # 只统计不写文件

新增子档案：在 ARCHIVES 里加一行（id/name/root/out），再在看板 index.html 的
FS_ARCHIVES 里加对应一行即可；文件夹放入文件后下次运行自动建档。

数据结构（刻意做紧凑，10 万条也能秒开）：
    {
      v, gen, root, total,
      dirs: ["", "0-贴纸库", "0-贴纸库/xxx", ...],   # 目录字典，文件里只存下标
      f: [[dirIdx, "文件名.jpg", 字节数, 天偏移], ...] # 天偏移 = 距 2020-01-01 的天数
    }
"""
import os
import sys
import json
import time
import argparse
from datetime import datetime

BASE = "/Volumes/英科再生2/MARKETING/14.市场部内部文件"

# 档案注册表：id 要和看板 FS_ARCHIVES 里的 id 一致；root 不存在时自动跳过（不报错）
ARCHIVES = [
    {"id": "zlk",  "name": "框条新品资料库", "root": BASE + "/框条新品资料库", "out": "frame-index.json"},
    {"id": "ztk",  "name": "框条总图库",     "root": BASE + "/框条段样总图/框条总图(上海+山东)", "out": "gallery-index.json"},
    {"id": "zhjs", "name": "展会资料检索",       "root": BASE + "/展会检索",       "out": "expo-index.json"},
]

# mtime 用「距 2020-01-01 的天数」存，比 10 位时间戳省一半字节
EPOCH = datetime(2020, 1, 1).timestamp()

# 这些是系统/缩略图垃圾，不进档案
SKIP_NAMES = {".DS_Store", "Thumbs.db", "._.DS_Store", "desktop.ini", "Icon\r"}
SKIP_PREFIX = ("._", "~$")


def scan(root):
    """遍历目录树，返回 (dirs 列表, 文件条目列表, 文件数)"""
    dir_index = {}
    dirs = []
    files = []
    n = 0

    def dir_id(rel):
        if rel in dir_index:
            return dir_index[rel]
        dir_index[rel] = len(dirs)
        dirs.append(rel)
        return dir_index[rel]

    for dirpath, dirnames, filenames in os.walk(root):
        dirnames.sort()
        rel_dir = os.path.relpath(dirpath, root)
        rel_dir = "" if rel_dir == "." else rel_dir.replace(os.sep, "/")
        d_id = dir_id(rel_dir)
        for fn in filenames:
            if fn in SKIP_NAMES or fn.startswith(SKIP_PREFIX):
                continue
            full = os.path.join(dirpath, fn)
            try:
                st = os.stat(full)
                size = st.st_size
                day = int((st.st_mtime - EPOCH) // 86400)
            except OSError:
                size, day = 0, 0
            files.append([d_id, fn, size, day])
            n += 1

    return dirs, files, n


def build_one(arch, out_path, dry=False):
    """扫一个档案并写索引；返回结果 dict（ok/total/...）"""
    root = arch["root"]
    t0 = time.time()
    if not os.path.isdir(root):
        return {"id": arch["id"], "name": arch["name"], "ok": False,
                "skip": "根目录不存在（未挂载或尚未创建）", "root": root}
    dirs, files, total = scan(root)
    secs = round(time.time() - t0, 1)

    payload = {
        "v": 1,
        "gen": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "root": root,
        "epoch": int(EPOCH),   # 天数的基准（2020-01-01 本地时间戳），浏览器靠它还原日期
        "total": total,
        "dirs": dirs,
        "f": files,
    }
    if dry:
        return {"id": arch["id"], "name": arch["name"], "ok": True,
                "total": total, "dirs": len(dirs), "secs": secs, "dry": True}

    tmp = out_path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, separators=(",", ":"))
    os.replace(tmp, out_path)

    mb = os.path.getsize(out_path) / 1048576.0
    return {"id": arch["id"], "name": arch["name"], "ok": True,
            "total": total, "dirs": len(dirs), "secs": secs,
            "mb": round(mb, 2), "out": out_path}


def main():
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    ap = argparse.ArgumentParser()
    ap.add_argument("--archive", default=None, help="只建 ARCHIVES 里某个 id")
    ap.add_argument("--root", default=None, help="临时单目录扫描（覆盖 ARCHIVES）")
    ap.add_argument("--out", default=None)
    ap.add_argument("--dry", action="store_true")
    a = ap.parse_args()

    # 临时单目录模式（保持旧用法兼容）
    if a.root:
        arch = {"id": "tmp", "name": "临时扫描", "root": a.root}
        out = a.out or os.path.join(here, "frame-index.json")
        print(json.dumps(build_one(arch, out, a.dry), ensure_ascii=False))
        return

    targets = ARCHIVES
    if a.archive:
        targets = [x for x in ARCHIVES if x["id"] == a.archive]
        if not targets:
            print(json.dumps({"ok": False, "err": "ARCHIVES 里没有 id=" + a.archive}, ensure_ascii=False))
            sys.exit(2)

    results = []
    for arch in targets:
        out_path = a.out or os.path.join(here, arch["out"])
        r = build_one(arch, out_path, a.dry)
        results.append(r)
        print(json.dumps(r, ensure_ascii=False), flush=True)

    built = [r for r in results if r.get("ok")]
    skipped = [r for r in results if not r.get("ok")]
    print(json.dumps({"done": True, "built": len(built), "skipped": len(skipped),
                      "total_files": sum(r.get("total", 0) for r in built)},
                     ensure_ascii=False))


if __name__ == "__main__":
    main()
