#!/usr/bin/env python3
"""Audit the color field of a finished AI short film.

Requires ffmpeg on PATH; otherwise pure Python standard library.

Usage:
  python3 color_field_audit.py <video.mp4> --start 0 --end 38 --out report.json --csv report.csv

Only measure the finished film segment. Use --start / --end to exclude
presenter interviews, tutorial UI and subtitle pages from the statistics.
"""
import argparse
import colorsys
import csv
import json
import math
import shutil
import subprocess
import sys

WIDTH, HEIGHT = 160, 90
HUE_LABELS = [
    "red", "orange", "yellow", "yellow-green", "green", "spring-green",
    "cyan", "azure", "blue", "violet", "magenta", "rose",
]
FIELDS = [
    "t", "dominant", "family_pct", "warm_pct", "green_pct", "cool_pct",
    "main_family", "main_pct", "second_pct", "chromatic_pct", "neutral_pct",
    "dark_pct", "bright_pct", "mean_saturation", "mean_value",
    "grid_cells_over_10pct",
]
TARGETS = [
    ("main_pct", "主色族平均占比", 55.0, "ge"),
    ("second_pct", "辅色族平均占比", 10.0, "ge"),
    ("grid_cells_over_10pct", "九宫格有色分区数", 8.0, "ge"),
    ("dark_pct", "暗部占比(V<0.22)", 20.0, "le"),
    ("bright_pct", "高光占比(V>0.86)", 12.0, "le"),
]


def analyze_frame(raw, t):
    bins = [0] * 12
    neutral = dark = bright = 0
    sat_sum = val_sum = hx = hy = 0.0
    chromatic = 0
    grid_total = [0] * 9
    grid_chroma = [0] * 9
    px = 0
    for y in range(HEIGHT):
        row = raw[y * WIDTH * 3:(y + 1) * WIDTH * 3]
        gy = min(2, y * 3 // HEIGHT)
        for x in range(WIDTH):
            r, g, b = row[x * 3] / 255.0, row[x * 3 + 1] / 255.0, row[x * 3 + 2] / 255.0
            h, s, v = colorsys.rgb_to_hsv(r, g, b)
            gi = gy * 3 + min(2, x * 3 // WIDTH)
            grid_total[gi] += 1
            if v < 0.22:
                dark += 1
            if v > 0.86:
                bright += 1
            if s < 0.11 or v < 0.08:
                neutral += 1
            else:
                chromatic += 1
                deg = h * 360.0
                bins[int((deg + 15) // 30) % 12] += 1
                grid_chroma[gi] += 1
                sat_sum += s
                val_sum += v
                rad = math.radians(deg)
                hx += math.cos(rad)
                hy += math.sin(rad)
            px += 1
    dominant = max(range(12), key=lambda i: bins[i])
    family = bins[dominant] + bins[(dominant - 1) % 12] + bins[(dominant + 1) % 12]
    grid_cover = [grid_chroma[i] / grid_total[i] * 100 for i in range(9)]
    warm = sum(bins[i] for i in (0, 1, 2, 10, 11)) / px * 100
    green = sum(bins[i] for i in (3, 4, 5)) / px * 100
    cool = sum(bins[i] for i in (6, 7, 8, 9)) / px * 100
    ranked = sorted((warm, green, cool), reverse=True)
    mean_hue = (math.degrees(math.atan2(hy, hx)) + 360) % 360 if chromatic else 0
    return {
        "t": t,
        "dominant": HUE_LABELS[dominant],
        "family_pct": round(family / px * 100, 1),
        "warm_pct": round(warm, 1),
        "green_pct": round(green, 1),
        "cool_pct": round(cool, 1),
        "main_family": ["warm", "green", "cool"][(warm, green, cool).index(ranked[0])],
        "main_pct": round(ranked[0], 1),
        "second_pct": round(ranked[1], 1),
        "chromatic_pct": round(chromatic / px * 100, 1),
        "neutral_pct": round(neutral / px * 100, 1),
        "dark_pct": round(dark / px * 100, 1),
        "bright_pct": round(bright / px * 100, 1),
        "mean_saturation": round(sat_sum / chromatic, 3) if chromatic else 0,
        "mean_value": round(val_sum / chromatic, 3) if chromatic else 0,
        "mean_hue_deg": round(mean_hue, 1),
        "grid_chroma_pct": [round(v, 1) for v in grid_cover],
        "grid_cells_over_10pct": sum(v >= 10 for v in grid_cover),
    }


def average(rows, key):
    return round(sum(r[key] for r in rows) / len(rows), 1)


def summarize(rows):
    checks = []
    for key, label, target, op in TARGETS:
        value = average(rows, key)
        ok = value >= target if op == "ge" else value <= target
        checks.append({
            "item": label, "value": value, "target": target, "op": op,
            "status": "PASS" if ok else "WARN",
        })
    jumps = sum(
        abs(rows[i]["main_pct"] - rows[i - 1]["main_pct"]) > 20
        for i in range(1, len(rows))
    )
    checks.append({
        "item": "相邻秒主色族跳变>20个百分点次数", "value": jumps,
        "target": 1, "op": "le", "status": "PASS" if jumps <= 1 else "WARN",
    })
    return {
        "frames": len(rows),
        "time_range": [rows[0]["t"], rows[-1]["t"]] if rows else [],
        "main_family_most_common": max(
            set(r["main_family"] for r in rows),
            key=lambda f: sum(r["main_family"] == f for r in rows),
        ) if rows else "",
        "checks": checks,
        "hint": "若统计区间包含讲解 UI 或访谈，请用 --start/--end 限定成片段后重跑。",
        "priority_on_failure": ["标准首帧", "提示词", "统一调色", "模型"],
    }


def main():
    ap = argparse.ArgumentParser(description="Color-field audit for AI short films")
    ap.add_argument("video", help="path to the finished film (mp4/mov)")
    ap.add_argument("--start", type=float, default=0.0, help="start second")
    ap.add_argument("--end", type=float, default=0.0, help="end second; 0 means full video")
    ap.add_argument("--fps", type=float, default=1.0, help="sampling rate, default 1 frame/sec")
    ap.add_argument("--out", default="", help="write per-second stats as JSON")
    ap.add_argument("--csv", default="", help="write per-second stats as CSV")
    args = ap.parse_args()

    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise SystemExit("ffmpeg not found on PATH")
    vf = f"fps={args.fps},scale={WIDTH}:{HEIGHT}"
    cmd = [ffmpeg, "-hide_banner", "-loglevel", "error", "-i", args.video]
    if args.start > 0:
        cmd += ["-ss", str(args.start)]
    if args.end > 0:
        cmd += ["-t", str(max(0.0, args.end - args.start))]
    cmd += ["-vf", vf, "-pix_fmt", "rgb24", "-f", "rawvideo", "pipe:1"]

    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    frame_size = WIDTH * HEIGHT * 3
    rows = []
    index = 0
    while True:
        raw = proc.stdout.read(frame_size)
        if len(raw) < frame_size:
            break
        rows.append(analyze_frame(raw, round(args.start + index / args.fps, 2)))
        index += 1
    proc.stdout.close()
    proc.wait()
    if not rows:
        raise SystemExit("no frames decoded; check video path and --start/--end")

    report = summarize(rows)
    print(f"Color field audit: {report['time_range'][0]:.1f}-{report['time_range'][1]:.1f}s, {len(rows)} frames")
    print(f"主色族: {report['main_family_most_common']}")
    print("-" * 62)
    for c in report["checks"]:
        sign = ">=" if c["op"] == "ge" else "<="
        print(f"{c['status']:<5} {c['item']:<28} {c['value']:>7}  (目标 {sign} {c['target']})")
    print("-" * 62)
    print("修正顺序:", " -> ".join(report["priority_on_failure"]))
    print(report["hint"])

    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump({"summary": report, "frames": rows}, f, ensure_ascii=False, indent=2)
        print("JSON:", args.out)
    if args.csv:
        with open(args.csv, "w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=FIELDS, extrasaction="ignore")
            w.writeheader()
            w.writerows(rows)
        print("CSV:", args.csv)
    return 0


if __name__ == "__main__":
    sys.exit(main())
