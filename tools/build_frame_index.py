#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
框条档案索引生成器
==================
扫描 NAS 上的「框条新品资料库」，把所有文件名 + 所在目录导出成看板可用的
frame-index.json，供看板里的「框条档案检索」工具做模糊搜索。

用法：
    python3 build_frame_index.py                 # 扫描并写入 ../frame-index.json
    python3 build_frame_index.py --dry           # 只统计不写文件
    python3 build_frame_index.py --root /path    # 换根目录

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

# 资料库在 NAS 上的挂载路径（本机固定）
DEFAULT_ROOT = "/Volumes/英科再生2/MARKETING/14.市场部内部文件/框条新品资料库"
OUT_NAME = "frame-index.json"

# mtime 用「距 2020-01-01 的天数」存，比 10 位时间戳省一半字节
EPOCH = datetime(2020, 1, 1).timestamp()

# 这些是系统/缩略图垃圾，不进档案
SKIP_NAMES = {".DS_Store", "Thumbs.db", "._.DS_Store", "desktop.ini", "Icon\r"}
SKIP_PREFIX = ("._", "~$")


def scan(root):
    """遍历目录树，返回 (dirs 列表, 文件条目列表)"""
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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=DEFAULT_ROOT)
    ap.add_argument("--out", default=None)
    ap.add_argument("--dry", action="store_true")
    a = ap.parse_args()

    root = a.root
    out = a.out or os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), OUT_NAME)

    if not os.path.isdir(root):
        print(json.dumps({"ok": False, "err": "资料库未挂载或路径不存在: " + root}, ensure_ascii=False))
        sys.exit(2)

    t0 = time.time()
    dirs, files, total = scan(root)

    payload = {
        "v": 1,
        "gen": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "root": root,
        "epoch": int(EPOCH),   # 天数的基准（2020-01-01 本地时间戳），浏览器靠它还原日期
        "total": total,
        "dirs": dirs,
        "f": files,
    }

    if a.dry:
        print(json.dumps({"ok": True, "total": total, "dirs": len(dirs),
                          "secs": round(time.time() - t0, 1)}, ensure_ascii=False))
        return

    tmp = out + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, separators=(",", ":"))
    os.replace(tmp, out)

    mb = os.path.getsize(out) / 1048576.0
    print(json.dumps({"ok": True, "total": total, "dirs": len(dirs),
                      "secs": round(time.time() - t0, 1),
                      "mb": round(mb, 2), "out": out}, ensure_ascii=False))


if __name__ == "__main__":
    main()
