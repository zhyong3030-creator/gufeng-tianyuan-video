#!/usr/bin/env python3
"""Offline verification that BOTH run channels reach S7 end-to-end.

v4.0: guided and autopilot must both be executable. autopilot is verified
against all three execution backends (libtv / workbuddy / external), plus the
"libtv unavailable" degradation case.

v5.0: additionally verifies the seven-step beginner-friendly guided delivery.
v5.1: verifies the protagonist / unnamed-background-figure hierarchy plus the
shot-scale distribution as an S0 project parameter.
v5.2: verifies the default ROLE_SHEET_X top/bottom-split board layout and the
byte-exact verbatim prompt.
v5.3: verifies the cross-scene "场景参照 @SCENE_MOOD_0X；" per-shot binding rule,
on top of the eight authoring
rules (v4.1 x4, v4.2 x2, v4.3 x2)
across SKILL.md / references / assets / scripts -- A08 finished color-card
prompt, shared scene body + N scene sentences, optional scene reverse, and
prompt purity -- plus a scan for stale v3.8 wording.

This script is PURE OFFLINE SELF-CHECK:
  * builds a minimal fake project inside a temporary directory;
  * only calls stage_state.py and build_handoff.py (both are text-only);
  * never connects to the network, never calls any generation API,
    never creates images or videos, never touches real user projects.
  * uses TemporaryDirectory and removes it afterwards (--keep to inspect).

Usage:
  python3 scripts/verify_channels.py
  python3 scripts/verify_channels.py --keep
"""
import argparse
import csv
import json
import math
import pathlib
import re
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
STAGE_STATE = HERE / "stage_state.py"
BUILD_HANDOFF = HERE / "build_handoff.py"
MODEL_ADAPTER = HERE / "model_adapter.py"
SKILL_ROOT = HERE.parent
STAGES = [f"S{i}" for i in range(8)]
BACKENDS = ["libtv", "workbuddy", "external"]
HANDOFF_FILES = ["libtv_handoff.md", "libtv_manifest.json", "libtv_assets_manifest.json"]

# 五条硬约束在交接包首段必须可指认的关键句
CONSTRAINT_MARKERS = [
    "不得重写、扩写、翻译",
    "在 A 段场景图取色彩方案、在每条视频提示词的【参考绑定】为第二处使用",
    "PHOTO_MASTER_01` 摄影母版是**中文文字块**",
    "人物参考**只有两类成对**",
    "风格固定",
]
# v3.8 旧口径 + v4.1 单一使用口径（v4.2 起均不允许出现；排除 .backup / __pycache__）
V41_OLD_PATTERNS = [
    r"用 A08 的固定中文 12 色归纳提示词生成",
    r"用固定中文 12 色归纳提示词",
    r"由视觉母版 \+ 全部场景基调图多图归纳成 12 色",
    r"多图归纳成 12 色",
    r"每场景出 A / B 两机位",
    r"6×2 场景正反打",
    r"SCENE_REVERSE_01\.\.06_A/B",
    r"12 色归纳色卡",
    r"12 色归纳提示词",
    r"色卡由场景基调图归纳而来",
    r"色卡（12 色归纳）延后",
    r"固定中文归纳提示词（整段复制",
    r"用「12 色归纳」中文提示词生成",
    r"色卡改为「视觉母版 \+ 全部场景基调图」",
    r"色卡（v3\.8）不是风格参考",
    r"色卡此时还不出",
    r"延后到场景基调图出齐",
    r"用这批基调图多图归纳",
    r"7 张基调图同传",
    # v4.2：色卡「只进视频」的旧口径已废止，场景图同传是新口径
    r"色卡只在 C 段视频",
    r"色卡只在视频生成时用",
    r"色卡唯一使用处",
    r"only_video_reference_binding",
    r"仅 C 段【参考绑定】",
    r"只在【参考绑定】上传",
    r"色卡只在【参考绑定】",
    r"图像生成阶段一律不挂色卡",
    r"色卡不参与任何图像生成",
]

# v4.3 废止：三子块母版 / 逐 beat 单行画面描述 / 旧画质短语
# v5.1 废止：禁止背景人影的旧句 / 放开景别配比、允许大远景的旧判断
V51_OLD_PATTERNS = [
    r"人物只以以上两类资产为准，全片只有 \[出镜角色\]",
    r"不出现额外人物、不新增首饰",
    r"不安排大远景、航拍",
    r"景别配比(?:改判为|是|属) S0 项目参数",
    r"按项目分镜表覆盖默认配比",
    r"大远景只用于交代场所与人流",
    r"「大远景」已从全局负向词移除",
]


# v5.3 废止：@ 在前、带「空间资产」说明的旧跨场景写法
V53_OLD_PATTERNS = [
    r"为本镜空间资产",
]


# v5.2 废止：1:1 四等分 2×2 作为「默认 ROLE_SHEET_X」版式的旧口径
# 注意：「不回退 1:1 四等分」这类否定句与扩展包 ROLE_BOARD_01 / FACE_QUAD_01
# 的四等分描述是合法的，不列入黑名单。
V52_OLD_PATTERNS = [
    r"四格拼板",
    r"四等分格位",
    r"ROLE_SHEET_X 四视图资产",
    r"人物四视图资产",
    r"每人 1 张 `ROLE_SHEET_X` 上下分区定妆板（正面全身 /",
    r"最终人物资产恒为每人 1 张 ROLE_SHEET_X 上下分区定妆板（正面全身",
    r"全身三视图 \+ 面部特写",
    r"用户给过的定妆照 / 四视图长提示词只是\*\*示例\*\*",
    r"用户提供的定妆 / 多视图提示词只是版式与质感要求的来源",
]

V43_OLD_PATTERNS = [
    r"敏感过度稳定",
    r"摄影母版含【摄影机参数】",
    r"摄影母版三个子块",
    r"【摄影机参数】\s*\n",
    r"【画面描述】\s*=\s*本条色场取值",
    r"逐\s*beat\s*单行写法",
]

MANIFEST_KEYS = [
    "schema_version", "run_mode", "execution_backend", "execution_backend_name",
    "platform_status", "requires_fallback", "input_mode", "spec", "models",
    "hard_constraints", "generation_units", "limits", "idempotency_key_prefix",
    "upload_order", "backend_detail", "degradation", "acceptance",
]


class Check:
    def __init__(self):
        self.rows = []

    def ok(self, group, name, detail=""):
        self.rows.append((group, name, True, detail))

    def fail(self, group, name, detail=""):
        self.rows.append((group, name, False, detail))

    def expect(self, group, name, cond, detail=""):
        (self.ok if cond else self.fail)(group, name, detail)

    @property
    def passed(self):
        return all(r[2] for r in self.rows)

    def report(self):
        last = None
        for group, name, ok, detail in self.rows:
            if group != last:
                print(f"\n【{group}】")
                last = group
            mark = "✓" if ok else "✗"
            print(f"  {mark} {name}" + (f"  — {detail}" if detail else ""))
        n_ok = sum(1 for r in self.rows if r[2])
        print(f"\n{'=' * 62}")
        print(f"结果：{n_ok}/{len(self.rows)} 项通过")
        return 0 if self.passed else 1


def run(*args):
    p = subprocess.run([sys.executable, *map(str, args)],
                       capture_output=True, text=True, encoding="utf-8")
    return p.returncode, (p.stdout or "") + (p.stderr or "")


def write_minimal_project(d, theme="自检样例·雪夜药铺", duration=30):
    """Write the smallest package build_handoff.py accepts; no media files.

    `duration` is a PROJECT PARAMETER: the same pipeline must pack any T.
    """
    d.joinpath("提示词全集.md").write_text(
        "# 提示词全集（离线自检用最小样例）\n\n"
        "### A08 · `COLOR_CARD_01` · 成品色卡出图提示词（12 HEX 写死）\n\n"
        "请生成一张简洁的平面色卡：纯色矩形色块，无渐变、无纹理，12 个色块按四行排列，每块下标 HEX 与用途。\n\n"
        "### A10 · `PHOTO_MASTER_01` · 摄影母版文字块\n\n"
        "【摄影机参数】【画面质感】【光影色彩】\n\n"
        "### C01 · U01 生成条\n\n【视频基本参数】【参考绑定】【摄影母版】【禁止项】【画面描述】【收束与音频】\n\n"
        "### C02 · U02 生成条\n\n【视频基本参数】【参考绑定】【摄影母版】【禁止项】【画面描述】【收束与音频】\n",
        encoding="utf-8")
    for name in ["注意点全集.md", "000_先看这个-操作手册.md", "01_色场方案表.md",
                 "master_overview.md"]:
        d.joinpath(name).write_text(f"# {name}（离线自检样例）\n", encoding="utf-8")
    n_units = math.ceil(duration / 15)
    units = []
    for i in range(n_units):
        start, end = i * 15, min((i + 1) * 15, duration)
        refs = ["COLOR_CARD_01", "ROLE_SHEET_A", "FACE_CLOSE_A"]
        refs.insert(0, "STANDARD_FRAME_01" if i == 0 else f"U{i:02d}_LAST")
        units.append({"unit": f"U{i+1:02d}", "start": start, "end": end,
                      "seconds": end - start, "references": refs})
    plan = {
        "theme": theme,
        "target_duration_seconds": duration, "shot_count": n_units * 3,
        "scene_count": 3,
        "aspect": "16:9", "input_mode": "zero",
        "image_model": "Midjourney + Seedream 5 + Nano Banana 2",
        "video_model": "Seedance 2.0",
        "asset_policy": {"upload_counts": {f"U{i+1:02d}": 4 for i in range(n_units)}},
        "units": units,
    }
    d.joinpath("generation_plan.json").write_text(
        json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
    with d.joinpath("shot_list.csv").open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["镜号", "场景", "生成条ID", "提示词ID", "参考图ID", "使用步骤"])
        w.writeheader()
        for i in range(1, n_units * 3 + 1):
            idx = (i - 1) // 3
            w.writerow({"镜号": f"P{i:02d}", "场景": f"场景{(i - 1) // 2 + 1}",
                        "生成条ID": f"U{idx+1:02d}", "提示词ID": f"C{idx+1:02d}",
                        "参考图ID": "ROLE_SHEET_A FACE_CLOSE_A COLOR_CARD_01",
                        "使用步骤": "首帧 STANDARD_FRAME_01" if i == 1 else "不设首帧"})


def load_state(d):
    return json.loads(d.joinpath("stage_state.json").read_text(encoding="utf-8"))


def walk_to_s7(d, chk, group, guided):
    """Advance S0 -> S7 through the state machine, checking gate semantics."""
    rc, out = run(STAGE_STATE, "--project", d, "next")
    chk.expect(group, "S0 引导块可读", rc == 0, "")
    if guided:
        chk.expect(group, "guided 输出人工引导块", "👉 现在请你" in out and "⏸" in out)
        chk.expect(group, "guided 不输出自动门禁", "🤖 自动门禁" not in out)
    else:
        chk.expect(group, "autopilot 输出自动门禁", "🤖 自动门禁" in out)
        chk.expect(group, "autopilot 不等待人工确认", "现在请你" not in out)

    for stage in STAGES[:-1]:
        args = [STAGE_STATE, "--project", d, "advance"]
        if guided:
            args += ["--note", "用户确认通过"]
        rc, out = run(*args)
        if rc != 0:
            chk.fail(group, f"{stage} 闸门放行", out.strip()[:120])
            return
    state = load_state(d)
    return state


def verify_guided(root, chk):
    g = "通道 1 · guided 逐步引导"
    d = root / "guided"
    d.mkdir()
    rc, out = run(STAGE_STATE, "--project", d, "init", "--theme", "自检样例",
                  "--input-mode", "zero", "--run-mode", "guided")
    chk.expect(g, "初始化成功", rc == 0, out.strip().splitlines()[0] if out.strip() else "")
    write_minimal_project(d)
    state = walk_to_s7(d, chk, g, guided=True)
    if not state:
        return
    chk.expect(g, "跑到 S7", state["current"] == "S7", f"current={state['current']}")
    chk.expect(g, "S0–S6 全部已放行", set(state["confirmed"]) == set(STAGES[:-1]),
               ",".join(sorted(state["confirmed"])))
    chk.expect(g, "闸门记录来源均为 user",
               all(v["by"] == "user" for v in state["confirmed"].values()))
    chk.expect(g, "不伪造自动门禁留痕", len(state.get("autopilot_log", [])) == 0)
    chk.expect(g, "run_mode=guided", state["run_mode"] == "guided")
    return state


def verify_autopilot(root, chk, backend, libtv_status="available", duration=30):
    g = f"通道 2 · autopilot / {backend}" + ("（libtv 不可用）" if libtv_status == "unavailable" else "")
    d = root / f"auto_{backend}_{libtv_status}"
    d.mkdir()
    rc, out = run(STAGE_STATE, "--project", d, "init", "--theme", "自检样例",
                  "--input-mode", "zero", "--run-mode", "autopilot", "--backend", backend)
    chk.expect(g, "初始化成功", rc == 0)
    write_minimal_project(d, duration=duration)
    state = walk_to_s7(d, chk, g, guided=False)
    if not state:
        return
    chk.expect(g, "跑到 S7", state["current"] == "S7", f"current={state['current']}")
    chk.expect(g, "S0–S6 全部自动放行", set(state["confirmed"]) == set(STAGES[:-1]),
               ",".join(sorted(state["confirmed"])))
    chk.expect(g, "闸门记录来源均为 autopilot",
               all(v["by"] == "autopilot" for v in state["confirmed"].values()))
    chk.expect(g, "note 一律「自动门禁通过」，不伪造用户确认",
               all(v["note"] == "自动门禁通过" for v in state["confirmed"].values()))
    chk.expect(g, "autopilot_log 留痕 7 条", len(state.get("autopilot_log", [])) == len(STAGES) - 1,
               f"{len(state.get('autopilot_log', []))} 条")
    chk.expect(g, "run_mode=autopilot", state["run_mode"] == "autopilot")
    chk.expect(g, f"execution_backend={backend}", state.get("execution_backend") == backend)
    chk.expect(g, "平台不可用也未误回退 guided", state["run_mode"] == "autopilot")

    # 交接包
    args = [BUILD_HANDOFF, "--project", d, "--backend", backend,
            "--libtv-status", libtv_status, "--no-first-frame", "U02"]
    rc, out = run(*args)
    chk.expect(g, "交接包生成成功", rc == 0, out.strip().splitlines()[0] if out.strip() else "")
    if rc != 0:
        return
    for f in HANDOFF_FILES:
        chk.expect(g, f"产出 {f}", d.joinpath(f).is_file())
    handoff = d.joinpath("libtv_handoff.md").read_text(encoding="utf-8")
    manifest = json.loads(d.joinpath("libtv_manifest.json").read_text(encoding="utf-8"))
    assets = json.loads(d.joinpath("libtv_assets_manifest.json").read_text(encoding="utf-8"))

    missing_markers = [m for m in CONSTRAINT_MARKERS if m not in handoff]
    chk.expect(g, "首段五条硬约束齐全", not missing_markers,
               "缺：" + "、".join(missing_markers) if missing_markers else "")
    chk.expect(g, "有按后端的跑法 §3.5", "## 3.5 执行后端与跑法" in handoff)
    chk.expect(g, "无未替换槽位", "{{" not in handoff)
    chk.expect(g, "标明风格固定", "风格固定" in handoff)
    missing_keys = [k for k in MANIFEST_KEYS if k not in manifest]
    chk.expect(g, "manifest 字段齐全", not missing_keys,
               "缺：" + "、".join(missing_keys) if missing_keys else "")
    chk.expect(g, "manifest execution_backend 正确",
               manifest.get("execution_backend") == backend)
    chk.expect(g, "manifest schema 4.0.0", manifest.get("schema_version") == "4.0.0")
    expected_units = math.ceil(duration / 15)
    chk.expect(g, f"生成条数随 T 重算（T={duration} → {expected_units} 条）",
               len(manifest.get("generation_units", [])) == expected_units,
               f"实得 {len(manifest.get('generation_units', []))} 条")
    chk.expect(g, "数量上限写死", manifest.get("limits", {}).get("stop_on_limit") is True
               and manifest["limits"]["max_total_generations"] == expected_units * 3)
    chk.expect(g, "色卡两处使用（manifest 硬约束）",
               manifest["hard_constraints"].get("color_card_two_usages") is True)
    chk.expect(g, "A 段只取色彩方案（manifest 硬约束）",
               manifest["hard_constraints"].get("color_card_scene_color_scheme_only") is True)
    chk.expect(g, "摄影母版不上传",
               manifest["hard_constraints"]["photography_master_upload"] is False)
    chk.expect(g, "人物两类成对", len(manifest["hard_constraints"]["character_reference_pairs"]) == 2)
    chk.expect(g, "视频六块结构", len(manifest["hard_constraints"]["video_prompt_structure"]) == 6)
    pm = [a for a in assets.get("assets", []) if a["id"] == "PHOTO_MASTER_01"]
    chk.expect(g, "摄影母版登记为不上传文字块", bool(pm) and pm[0]["upload"] is False)

    attribution = {"libtv": "libtv Agent 生成", "workbuddy": "WorkBuddy 生成",
                   "external": "用户平台生成"}[backend]
    chk.expect(g, "产物归属按后端标注", manifest["acceptance"]["attribution"] == attribution,
               manifest["acceptance"]["attribution"])

    if libtv_status == "unavailable" and backend == "libtv":
        chk.expect(g, "libtv 不可用 → requires_fallback=true",
                   manifest.get("requires_fallback") is True)
        chk.expect(g, "头部写明不可直接执行", "不可直接执行" in handoff)
        chk.expect(g, "给出换后端命令", "--backend workbuddy" in handoff and "--backend external" in handoff)
    elif backend != "libtv":
        chk.expect(g, "非 libtv 后端不依赖平台连接",
                   "不依赖 libtv" in handoff or "正常跑通" in handoff)
    return state, manifest


def verify_duration_variability(root, chk):
    """证明总时长 T 不是硬编码：不同 T 都能打包，且硬约束一字不变。"""
    g = "时长不卡死（项目参数）"
    baseline = None
    for duration in (20, 90):
        d = root / f"duration_{duration}"
        d.mkdir()
        rc, _ = run(STAGE_STATE, "--project", d, "init", "--theme", "自检样例",
                    "--run-mode", "autopilot", "--backend", "external")
        if rc != 0:
            chk.fail(g, f"T={duration} 初始化", "init 失败")
            continue
        write_minimal_project(d, duration=duration)
        rc, out = run(BUILD_HANDOFF, "--project", d, "--backend", "external")
        chk.expect(g, f"T={duration} 秒可打包", rc == 0,
                   "" if rc == 0 else out.strip()[:100])
        if rc != 0:
            continue
        m = json.loads(d.joinpath("libtv_manifest.json").read_text(encoding="utf-8"))
        handoff = d.joinpath("libtv_handoff.md").read_text(encoding="utf-8")
        expected = math.ceil(duration / 15)
        chk.expect(g, f"T={duration} 写入 spec", m["spec"]["duration_seconds"] == duration,
                   f"spec={m['spec']['duration_seconds']}")
        chk.expect(g, f"T={duration} 生成条按 T 重算 = {expected}",
                   len(m["generation_units"]) == expected)
        chk.expect(g, f"T={duration} 时间码覆盖到 {duration}s",
                   m["generation_units"][-1]["timecode"].endswith(f"–{duration}s"),
                   m["generation_units"][-1]["timecode"])
        chk.expect(g, f"T={duration} 交接包显示正确秒数", f"{duration} 秒" in handoff)
        if baseline is None:
            baseline = m["hard_constraints"]
        else:
            chk.expect(g, f"T={duration} 硬约束与 20 秒完全一致",
                       m["hard_constraints"] == baseline)
    chk.ok(g, "唯一锁死的是视频类型与风格；T / 镜数 / 段落数 / 生成条数均可改",
           "已在 20 秒与 90 秒两个项目验证")



def verify_v43_rules(root, chk):
    """v4.1 四项 + v4.2 两项 + v4.3 两项新口径是否四处同步。"""
    g = "v4.3 新口径同步"
    rd = lambda rel: (SKILL_ROOT / rel).read_text(encoding="utf-8-sig")

    skill = rd("SKILL.md")
    cs = rd("references/color-system.md")
    csp = rd("assets/character-sheet-prompts.md")
    sd = rd("references/staged-delivery.md")
    bh = rd("scripts/build_handoff.py")
    ma = rd("scripts/model_adapter.py")
    pev = rd("references/prompt-examples-video.md")
    ht = rd("assets/libtv-handoff-template.md")
    ss = rd("scripts/stage_state.py")

    chk.expect(g, "SKILL.md 版本 5.8.0", "version: 5.8.0" in skill)
    chk.expect(g, "SKILL.md 规则标题升为三十三条", "## 三十三条升级规则（v5.8）" in skill)
    for n, marker in [
        (15, "成品出图提示词，不是归纳方法本身"),
        (20, "一条通用正文 + N 条场景句"),
        (21, "场景反打是可选项，不是必传出口"),
        (22, "提示词纯净原则"),
        (23, "色卡两处使用，A 段场景图只取色彩方案"),
        (24, "场景图用指令式图像模型 + 固定画质段"),
        (25, "摄影母版 = 一段连续专业摄影描述，可变项下放到逐镜"),
        (26, "画面描述 = 全局设定段 + 逐镜块，并清掉跨块重复"),
    ]:
        chk.expect(g, f"SKILL.md 第 {n} 条就位", marker in skill)
        chk.expect(g, f"SKILL.md 第 {n} 条编号存在", f"\n{n}. **" in skill)

    for k, marker in [
        ("§7.2 归纳 meta 指令", "7.2 归纳 meta 指令（只作方法，不复制到平台）"),
        ("§7.4 成品模板", "7.4 成品出图提示词模板"),
        ("§7.6 可选反打", "7.6 标准首帧与场景反打（v4.1）"),
        ("§7.5 五条硬边界", "五条硬边界（v4.2 修订）"),
        ("§7.8 场景图色彩参考", "### 7.8 场景图怎么参考色卡"),
        ("§7.5 顺序不可倒", "必须先于 A01 完成"),
    ]:
        chk.expect(g, f"color-system.md {k}", marker in cs)
    chk.expect(g, "color-system.md 不再把 meta 指令标为整段复制",
               "固定中文归纳提示词（整段复制" not in cs)

    chk.expect(g, "模板 §15.1 成品色卡不传参考图",
               "不上传任何参考图" in csp and "生成提示词的提示词" in csp)
    chk.expect(g, "模板 §15.4 通用正文 + 场景句", "## 15.4" in csp and "<场景句>" in csp)
    chk.expect(g, "模板 §15.5 可选统一反打", "## 15.5" in csp and "不用（默认）" in csp)
    chk.expect(g, "模板 §15.1 标注两处使用", "A 段取色 + C 段视频" in csp)
    # 通用正文代码块纯净度
    seg = csp[csp.index("## 15.4"):] if "## 15.4" in csp else ""
    blocks = re.findall(r"```(.*?)```", seg, re.S)
    body = blocks[0] if blocks else ""
    dirty = [x for x in ["九分区", "3×3", "上传", "请以", "输出一个机位"] if x in body]
    if re.search(r"\b6[0-8]\s*%", body):
        dirty.append("占比数字")
    chk.expect(g, "§15.4 通用正文代码块无验收口径与元指令", not dirty,
               "脏项：" + "、".join(dirty) if dirty else "")
    chk.expect(g, "§15.4 通用正文含色彩参考限定句",
               "以 @COLOR_CARD_01 为色彩方案参考" in body and "不取色块的版式" in body)
    chk.expect(g, "§15.4 通用正文含固定画质段",
               "严禁噪点" in body and "明暗过渡稳定" in body)
    chk.expect(g, "§15.4 指令式模型不套 MJ 参数行",
               "画幅 16:9。" in body and "--ar" not in body)

    chk.expect(g, "staged-delivery 交付硬口径含可选反打", "场景反打可选（v4.1）" in sd)
    chk.expect(g, "staged-delivery 交付硬口径含纯净原则", "A 段场景提示词纯净（v4.1）" in sd)

    db = json.loads(rd("assets/model_profiles.json"))
    chk.expect(g, "能力档案 schema 5.8.0", db["schema_version"] == "5.8.0")
    chk.expect(g, "能力档案 planning_rules 42 条（v5.8 沿用）", len(db["planning_rules"]) == 42)
    for key in ["scene_prompt_rule", "scene_reverse_optional_rule", "prompt_purity_rule",
                "scene_color_card_reference_rule", "scene_quality_clause_rule",
                "photography_master_rule", "shot_block_rule"]:
        chk.expect(g, f"能力档案含 {key}", key in db["planning_rules"])
    chk.expect(g, "color_card_rule 已是两步走",
               "成品出图提示词" in db["planning_rules"]["color_card_rule"]
               and "meta 指令" in db["planning_rules"]["color_card_rule"])

    chk.expect(g, "build_handoff 硬约束写明成品色卡提示词", "成品色卡出图提示词" in bh)
    chk.expect(g, "build_handoff 写明场景反打可选", "不要凭空补一张不存在的反打图" in bh)
    chk.expect(g, "build_handoff 上传序列标注可选", "〔可选〕SCENE_REVERSE_0X" in bh)
    chk.expect(g, "build_handoff 硬约束改为两处使用",
               "color_card_two_usages" in bh and "color_card_scene_color_scheme_only" in bh
               and "color_card_only_in_reference_binding" not in bh)
    chk.expect(g, "build_handoff 写明必须先于 A01", "必须先于 A01 完成" in bh)
    chk.expect(g, "build_handoff 摄影母版改为一段式 + 焦段下放",
               "一段连续专业摄影描述" in bh and "逐镜块" in bh)
    chk.expect(g, "build_handoff 场景图上传标注改为两处", "A 段取色彩方案 + C 段【参考绑定】" in bh)
    chk.expect(g, "model_adapter 输出字段含新口径",
               all(k in ma for k in ["scene_prompt_format", "scene_reverse",
                                     "color_card_deliverable", "prompt_purity_rule",
                                     "scene_color_card_reference", "scene_image_model",
                                     "scene_quality_clause", "color_card_must_precede_A01"]))

    # 动态：model_adapter 真的把新字段写进 generation_plan.json
    out = root / "v43_adapter"
    out.mkdir(exist_ok=True)
    rc, log = run(MODEL_ADAPTER, "--video-model", "seedance-2.5", "--image-model",
                  "seedream-5", "--duration", "30", "--input-mode", "zero",
                  "--out-dir", out)
    plan_path = out / "generation_plan.json"
    chk.expect(g, "model_adapter 冒烟可执行", rc == 0 and plan_path.exists(), log[-120:])
    if plan_path.exists():
        plan = json.loads(plan_path.read_text(encoding="utf-8"))
        ap = plan.get("asset_policy", {})
        chk.expect(g, "plan.scene_prompt_format 正确",
                   ap.get("scene_prompt_format") == "one_shared_body_plus_N_scene_sentences")
        chk.expect(g, "plan.scene_reverse 为可选", ap.get("scene_reverse") == "optional_user_choice")
        chk.expect(g, "plan.color_card_deliverable 正确",
                   ap.get("color_card_deliverable") == "finished_text_to_image_prompt_with_12_hardcoded_HEX")
        chk.expect(g, "plan 写明跳过反打的处理", "SCENE_MOOD_01" in str(ap.get("scene_reverse_when_skipped", "")))
        chk.expect(g, "首帧第 2 张参考给出两个选项",
                   len(ap.get("standard_frame_second_reference_options", [])) == 2)
        chk.expect(g, "首帧恒 2 参考（锁定项未变）", ap.get("standard_frame_references") == 2)
        chk.expect(g, "六块结构未变", len(ap.get("video_prompt_structure", [])) == 6)
        chk.expect(g, "默认仍为 guided", ap.get("run_mode") == "guided")
        chk.expect(g, "plan.color_card_usage 为两处使用",
                   ap.get("color_card_usage") == "scene_color_scheme_plus_video_reference_binding")
        chk.expect(g, "plan.scene_image_model 为指令式模型",
                   ap.get("scene_image_model") == "gpt-image-2.5")
        chk.expect(g, "plan 写明色卡必须先于 A01", ap.get("color_card_must_precede_A01") is True)
        chk.expect(g, "plan 场景色彩参考限定「只取」且不写 --sref",
                   "只取 12 色色值" in str(ap.get("scene_color_card_reference", ""))
                   and "--sref" in str(ap.get("scene_color_card_reference", "")))
        chk.expect(g, "plan 固定画质段含用户确认短语",
                   "明暗过渡稳定" in str(ap.get("scene_quality_clause", ""))
                   and "严禁噪点" in str(ap.get("scene_quality_clause", "")))
        chk.expect(g, "plan 纯净原则含参考图用法",
                   "reference_usage" in str(ap.get("prompt_purity_rule", "")))
        pm = ap.get("photography_master", {})
        chk.expect(g, "plan 摄影母版为一段式、无子块",
                   pm.get("format") == "one_continuous_professional_photography_paragraph_v4.3"
                   and pm.get("subsections") == [])
        chk.expect(g, "plan 焦段下放到逐镜块",
                   pm.get("focal_length_placement") == "shot_blocks_in_picture_description_only")
        chk.expect(g, "plan 画面描述为全局段 + 逐镜块",
                   ap.get("shot_description_format") == "global_setup_paragraph_plus_numbered_shot_blocks")
        chk.expect(g, "plan 跨块去重规则就位",
                   "只在逐镜块" in str(ap.get("cross_block_dedup", "")))
        chk.expect(g, "plan 画质段短语为用户确认值",
                   ap.get("quality_clause_phrase") == "明暗过渡稳定")

    # ---- v4.3 专项：摄影母版一段式 / 画面描述逐镜块 / 焦段下放 / 跨块去重 ----
    chk.expect(g, "SKILL.md 第 25 条写明三类不进母版",
               "三类内容不进母版" in skill and "具体 `mm` 焦段" in skill)
    chk.expect(g, "SKILL.md 第 26 条写明逐镜块与去重表",
               "【镜头N | 时间码 | 镜头名】" in skill and "去重表" in skill)
    chk.expect(g, "SKILL.md 锁定项含一段式母版与焦段下放",
               "摄影母版一段式" in skill and "焦段下放" in skill)

    s82 = pev[pev.index("### 8.2"):pev.index("### 8.3")]
    b82 = re.findall(r"```(.*?)```", s82, re.S)
    master = b82[0] if b82 else ""
    chk.expect(g, "§8.2 母版代码块存在且为一段式", bool(master.strip()))
    chk.expect(g, "§8.2 母版不含三个子标签",
               not any(x in master for x in ["【摄影机参数】", "【画面质感】", "【光影色彩】"]))
    chk.expect(g, "§8.2 母版不含具体 mm 焦段与 T 光圈",
               not re.search(r"\d+\s*mm", master) and not re.search(r"T\d", master))
    chk.expect(g, "§8.2 母版承载高光不漂 / 暗部留色相原则",
               "高光不能漂" in master and "暗部也必须保留色相" in master)

    s83 = pev[pev.index("### 8.3"):pev.index("### 8.4")]
    b83 = re.findall(r"```(.*?)```", s83, re.S)
    six = b83[0] if b83 else ""
    chk.expect(g, "§8.3 六块模板含全局设定段",
               "统一场景为 [场所与器物连成的一个连续空间]" in six)
    chk.expect(g, "§8.3 六块模板含【镜头1 | 时间码 | 镜头名】逐镜块",
               "【镜头1 | 0.00–3.00s" in six)
    chk.expect(g, "§8.3 逐镜块给单一焦段与 T 光圈",
               "[50mm] 焦段" in six and "[T2.8]" in six)
    chk.expect(g, "§8.3 摄影母版块只放占位、不重复器材参数",
               "[§8.2 全文逐字粘贴" in six and "统一使用数字电影摄影机" not in six)
    chk.expect(g, "§8.3 收束与音频不复述人物一致性", "人物一致性" not in six)
    _hdrs = ["视频基本参数", "参考绑定", "摄影母版", "禁止项", "画面描述", "收束与音频"]
    _pos = [six.find("【" + h + "】") for h in _hdrs]
    chk.expect(g, "§8.3 六块顺序正确且各出现一次",
               all(x >= 0 for x in _pos) and _pos == sorted(_pos))

    s152 = csp[csp.index("## 15.2"):csp.index("## 15.3")]
    chk.expect(g, "模板 §15.2 摄影母版为一段式",
               "一段连续专业摄影描述" in s152 and "不再分三个子标签" in s152)
    chk.expect(g, "模板 §15.3 画面描述为全局段 + 逐镜块",
               "全局设定段" in csp and "逐镜块" in csp)
    chk.expect(g, "staged-delivery 摄影母版改为一段式且焦段在逐镜块",
               "A10 摄影母版 = 一段式文字块（v4.3）" in sd and "逐镜块" in sd)
    chk.expect(g, "交接包模板硬约束写明一段式母版与逐镜块",
               "一段连续专业摄影描述" in ht and "逐镜块" in ht)
    chk.expect(g, "状态机 S5 引导含一段式母版与逐镜块",
               "摄影母版一段式且逐字一致" in ss and "全局段 + 逐镜块" in ss)
    chk.expect(g, "能力档案 photography_master_rule 为一段式",
               "一段连续专业摄影描述" in db["planning_rules"]["photography_master_rule"]
               and "下放" in db["planning_rules"]["photography_master_rule"])
    chk.expect(g, "能力档案 shot_block_rule 含逐镜块",
               "逐镜块" in db["planning_rules"]["shot_block_rule"])
    chk.expect(g, "model_adapter 输出 v4.3 字段",
               all(k in ma for k in ["shot_description_format", "cross_block_dedup",
                                     "one_continuous_professional_photography_paragraph_v4.3",
                                     "focal_length_placement", "quality_clause_phrase"]))

    # 全库旧口径残留扫描（排除 .backup / __pycache__）
    files = [p for p in SKILL_ROOT.rglob("*")
             if p.is_file() and p.suffix in (".md", ".py", ".json", ".csv")
             and ".backup" not in str(p) and "__pycache__" not in str(p)
             and p.name != "verify_channels.py"]  # 扫描器自身持有旧串模式，不参与扫描
    stale = []
    for p in files:
        txt = p.read_text(encoding="utf-8-sig", errors="replace")
        for pat in V41_OLD_PATTERNS + V43_OLD_PATTERNS + V51_OLD_PATTERNS + V52_OLD_PATTERNS + V53_OLD_PATTERNS:
            if re.search(pat, txt):
                stale.append(f"{p.relative_to(SKILL_ROOT)}: {pat}")
    chk.expect(g, "全库 v3.8 / v4.1 / v4.3 / v5.1 / v5.2 / v5.3 旧口径残留 0（不含扫描器自身）",
               not stale, "；".join(stale[:4]))




def verify_v50_rules(root, chk):
    """v5.0 七步小白引导交付是否四处同步（只改怎么交付，不改画面口径）。"""
    g = "v5.0 七步引导同步"
    rd = lambda rel: (SKILL_ROOT / rel).read_text(encoding="utf-8-sig")

    skill = rd("SKILL.md")
    sd = rd("references/staged-delivery.md")
    ug = rd("references/usage-guide.md")
    ap = rd("references/agent-autopilot.md")
    tmpl = rd("assets/step-delivery-template.md")
    box = rd("assets/step-prompt-box.md")
    ma = rd("scripts/model_adapter.py")
    bh = rd("scripts/build_handoff.py")
    db = json.loads(rd("assets/model_profiles.json"))

    chk.expect(g, "SKILL.md 版本 5.8.0", "version: 5.8.0" in skill)
    chk.expect(g, "SKILL.md 规则标题升为三十三条", "## 三十三条升级规则（v5.8）" in skill)
    chk.expect(g, "第 27 条规则在位", "27. **默认交付 = 7 大步小白引导" in skill)
    chk.expect(g, "SKILL.md 有七大步章节", "## 默认交付：7 大步小白引导（v5.0）" in skill)
    for name in ["0 准备", "1 视频总规划", "2 视觉美学基调", "3 视频分镜设计及脚本",
                 "4 人物场景资产设计", "5 视频生成设计", "6 自查"]:
        chk.expect(g, "七大步含「%s」" % name, name in skill)
    chk.expect(g, "每小步弹选择框", "每一小步必须弹" in skill)
    chk.expect(g, "每大步三件套", "每一大步只给三件套" in skill)
    chk.expect(g, "每条提示词单独一个可一键复制的框", "每条提示词单独放进一个可一键复制的框" in skill)
    chk.expect(g, "只给生成类提示词", "只给生成类提示词" in skill)
    chk.expect(g, "旧文档先归档再重建", "旧文档先归档再重建" in skill)
    chk.expect(g, "autopilot 跳过引导", "跳过 7 步引导、不弹选择框" in skill)
    chk.expect(g, "锁定项一字不动声明", "一字不动" in skill)
    chk.expect(g, "资源索引含两份新模板",
               "step-delivery-template.md" in skill and "step-prompt-box.md" in skill)
    chk.expect(g, "staged-delivery §9 在位", "## 9. v5.0 七步引导交付规范" in sd)
    chk.expect(g, "staged-delivery 三件套表", "每大步三件套缺一不可" in sd)
    chk.expect(g, "usage-guide 入口说明", "7 大步小白引导" in ug)
    chk.expect(g, "autopilot 协议边界", "跳过 7 步引导" in ap)
    chk.expect(g, "本地一步一文件模板存在", "## 5. 怎么用（一句话）" in tmpl)
    chk.expect(g, "粘贴框规范存在", "一条提示词 = 一个框" in box)
    chk.expect(g, "规范禁止分隔行拼接", "禁止用 `=== 第 N 条 ===` 之类的分隔行" in box)
    chk.expect(g, "能力档案 schema 5.8.0", db["schema_version"] == "5.8.0")
    for k in ["guided_step_delivery_rule", "prompt_box_rule", "legacy_archive_rule"]:
        chk.expect(g, "planning_rules 含 %s" % k, k in db["planning_rules"])
    chk.expect(g, "model_adapter 生成 v5.0 七大步字符串", "v5.0 七大步小白引导" in ma)
    chk.expect(g, "build_handoff 声明 v5.0 边界", "v5.0 说明" in bh)
    chk.expect(g, "画面口径未回退：色卡两处使用仍在", "色卡两处使用" in skill)
    chk.expect(g, "画面口径未回退：一段式摄影母版仍在", "摄影母版 = 一段连续专业摄影描述" in skill)
    chk.expect(g, "画面口径未回退：逐镜块仍在", "画面描述 = 全局设定段 + 逐镜块" in skill)
    chk.expect(g, "跨会话续接读入口文件、不跑旧状态机", "不要去跑 `stage_state.py status`" in skill)
    chk.expect(g, "禁止多条塞进同一框", "不把多条提示词塞进同一个框" in skill)
    chk.expect(g, "能力档案写明一条一个框", "一条提示词 = 一个独立 fenced code block" in db["planning_rules"]["prompt_box_rule"])



def verify_v51_rules(root, chk):
    """v5.1 人物层级（主角 / 不具名背景人影）+ 景别配比是否四处同步。"""
    g = "v5.1 人物层级/景别同步"
    rd = lambda rel: (SKILL_ROOT / rel).read_text(encoding="utf-8-sig")

    skill = rd("SKILL.md")
    vg = rd("references/visual-grammar.md")
    pv = rd("references/prompt-examples-video.md")
    ug = rd("references/usage-guide.md")
    im = rd("references/input-modes.md")
    ms = rd("references/model-selection.md")
    css = rd("references/character-sheet-spec.md")
    sd = rd("references/staged-delivery.md")
    st = rd("references/script-template.md")
    pp = rd("references/prompt-playbook.md")
    ot = rd("assets/overview-template.md")
    csp = rd("assets/character-sheet-prompts.md")
    tmpl = rd("assets/step-delivery-template.md")
    lht = rd("assets/libtv-handoff-template.md")
    ma = rd("scripts/model_adapter.py")
    bh = rd("scripts/build_handoff.py")
    ss = rd("scripts/stage_state.py")
    ap = rd("references/agent-autopilot.md")
    db = json.loads(rd("assets/model_profiles.json"))

    chk.expect(g, "SKILL.md 版本 5.8.0", "version: 5.8.0" in skill)
    chk.expect(g, "规则标题升为三十三条（v5.4）", "## 三十三条升级规则（v5.8）" in skill)
    chk.expect(g, "第 28 条规则在位", "28. **人物层级 = 主角 + 不具名背景人影" in skill)
    chk.expect(g, "主角是唯一被表现的人物", "唯一被表现的人物" in skill)
    chk.expect(g, "背景人影不占参考位", "不占参考位" in skill)
    chk.expect(g, "SKILL.md 写明禁用大远景与远景", "禁用大远景 / 远景 / 大全景" in skill)
    chk.expect(g, "铁律表写明禁用大远景", "禁用大远景 / 远景 / 大全景**（第 28 条" in skill)
    chk.expect(g, "约束新增 v5.1 条目", "- **人物层级与景别配比（v5.1）**" in skill)
    chk.expect(g, "v5.0 交付方式声明不动", "七大步交付方式一字不动" in skill)

    chk.expect(g, "visual-grammar §2.1 人物层级表", "### 2.1 人物层级（v5.1" in vg)
    chk.expect(g, "visual-grammar 标明禁用大远景", "禁用大远景、远景、大全景" in vg)
    chk.expect(g, "visual-grammar 声明不用大远景", "也不会出现大远景 / 远景 / 大全景" in vg)
    chk.expect(g, "prompt-examples-video §8.6 在位", "### 8.6 人物层级与逐镜写法（v5.1" in pv)
    chk.expect(g, "参考绑定改为「主要表现人物只有」", "主要表现人物只有 [出镜角色]" in pv)
    chk.expect(g, "禁止项改为唯一清晰主体正向句", "[出镜角色] 为唯一清晰主体" in pv)
    chk.expect(g, "禁止项不再写「不出现额外人物」", "不出现额外人物" not in pv)
    chk.expect(g, "§8.5 第 20 项检查全片无大远景", "20. 全片是否**没有**大远景 / 远景 / 大全景" in pv)
    chk.expect(g, "逐镜块写明背景人影只写背景层与环境动态", "背景人影只在这里与背景层出现" in pv)

    chk.expect(g, "script-template 禁用大远景",
               "不用大远景、远景、大全景" in st and "不越过全景" in st)
    chk.expect(g, "prompt-playbook 写回大远景负向词", "**大远景、远景、大全景**" in pp)
    chk.expect(g, "overview-template 禁用大远景", "不用大远景 / 远景 / 大全景" in ot)
    chk.expect(g, "character-sheet-prompts 头注含人物层级", "v5.1 人物层级" in csp)
    chk.expect(g, "step-delivery 模板第 3 步含人物层级表", "第 3 步专项（v5.1）" in tmpl)
    chk.expect(g, "libtv 交接包模板含人物层级", "v5.1 人物层级" in lht)
    chk.expect(g, "staged-delivery §9.6 在位", "### 9.6 第 3 步分镜表必须含人物层级（v5.1）" in sd)
    chk.expect(g, "usage-guide 背景人影不传图", "背景人影不传图、不计入张数" in ug)
    chk.expect(g, "input-modes 背景人影不占参考位", "不具名背景人影不占参考位" in im)
    chk.expect(g, "model-selection 背景人影不占参考位", "不占参考位" in ms)
    chk.expect(g, "character-sheet-spec 背景人影不出资产", "不占参考位、不出资产" in css)

    chk.expect(g, "model_adapter 负向清单写回大远景",
               '"大远景", "远景", "大全景"' in ma)
    chk.expect(g, "model_adapter asset_policy 含人物层级", '"character_hierarchy":' in ma)
    chk.expect(g, "model_adapter asset_policy 含背景人影写法", '"background_figure_placement":' in ma)
    chk.expect(g, "model_adapter asset_policy 含景别策略", '"shot_scale_policy":' in ma)
    chk.expect(g, "build_handoff 交接包含人物层级", "v5.1 人物层级" in bh)
    chk.expect(g, "build_handoff manifest 含人物层级字段", '"character_hierarchy":' in bh)
    chk.expect(g, "stage_state S3 引导含人物层级", "v5.1 人物层级" in ss)

    chk.expect(g, "能力档案 schema 5.8.0", db["schema_version"] == "5.8.0")
    chk.expect(g, "能力档案 planning_rules 42 条", len(db["planning_rules"]) == 42)
    chk.expect(g, "能力档案含 character_hierarchy_rule",
               "character_hierarchy_rule" in db["planning_rules"])
    chk.expect(g, "能力档案含 shot_scale_parameter_rule",
               "shot_scale_parameter_rule" in db["planning_rules"])
    chk.expect(g, "人物层级规则写明不占参考位",
               "不占参考位" in db["planning_rules"]["character_hierarchy_rule"])
    chk.expect(g, "景别规则写明不新增风格档位",
               "不新增风格档位" in db["planning_rules"]["shot_scale_parameter_rule"])
    chk.expect(g, "景别规则写明禁用大远景",
               "禁用大远景、远景、大全景" in db["planning_rules"]["shot_scale_parameter_rule"])
    chk.expect(g, "人物层级规则写明后景焦外",
               "后景焦外" in db["planning_rules"]["character_hierarchy_rule"])
    chk.expect(g, "SKILL.md 写明不靠拉远镜头摆人影", "不靠拉远镜头去摆" in skill)
    chk.expect(g, "逐镜模板写明人影在后景焦外", "后景焦外 [N] 个不具名人影" in pv)
    chk.expect(g, "分镜模板禁用大远景景别列", "景别列不得出现大远景" in tmpl)
    chk.expect(g, "交接包模板禁用大远景", "全片禁用大远景" in lht)
    chk.expect(g, "build_handoff 禁用大远景", "全片禁用大远景" in bh)
    chk.expect(g, "stage_state 禁用大远景", "全片禁用大远景" in ss)
    chk.expect(g, "model_adapter asset_policy 禁用大远景", "禁用大远景" in ma)
    chk.expect(g, "staged-delivery 禁用大远景", "全片不用大远景" in sd)
    chk.expect(g, "usage-guide 禁用大远景", "全片不用大远景" in ug)
    chk.expect(g, "autopilot 协议禁用大远景", "全片禁用大远景" in ap)



def verify_v52_rules(root, chk):
    """v5.2 默认 ROLE_SHEET_X 上下分区定妆板 + 逐字模板是否四处同步。"""
    g = "v5.2 上下分区定妆板同步"
    rd = lambda rel: (SKILL_ROOT / rel).read_text(encoding="utf-8-sig")

    skill = rd("SKILL.md")
    css = rd("references/character-sheet-spec.md")
    im = rd("references/input-modes.md")
    ms = rd("references/model-selection.md")
    sd = rd("references/staged-delivery.md")
    ug = rd("references/usage-guide.md")
    pev = rd("references/prompt-examples-video.md")
    ap = rd("references/agent-autopilot.md")
    csp = rd("assets/character-sheet-prompts.md")
    ot = rd("assets/overview-template.md")
    tbt = rd("assets/theme-brief-template.md")
    lht = rd("assets/libtv-handoff-template.md")
    tmpl = rd("assets/step-delivery-template.md")
    ma = rd("scripts/model_adapter.py")
    bh = rd("scripts/build_handoff.py")
    ss = rd("scripts/stage_state.py")
    db = json.loads(rd("assets/model_profiles.json"))

    # --- SKILL.md
    chk.expect(g, "SKILL.md 升为三十三条（v5.4）", "## 三十三条升级规则（v5.8）" in skill)
    chk.expect(g, "第 29 条规则在位", "29. **默认人物资产版式 = 上下分区定妆板（v5.2" in skill)
    chk.expect(g, "第 29 条写明逐字采用", "一个字不加、不删、不改写" in skill)
    chk.expect(g, "第 29 条写明版式上 1/3 下 2/3", "上 1/3 左正面 + 右侧面面部特写" in skill)
    chk.expect(g, "第 29 条写明 M0 适用性", "M0 零素材" in skill and "不回退成 2×2 四等分" in skill)
    chk.expect(g, "第 29 条写明 FACE_CLOSE 从上方左格裁", "上方左格" in skill)
    chk.expect(g, "第 29 条声明不启用扩展包", "扩展定妆包不被启用" in skill or "扩展定妆包仍只在用户主动要求时启用" in skill)
    chk.expect(g, "第 11 条标注 v5.2 定稿版式", "v5.2 定稿版式" in skill)
    chk.expect(g, "约束新增默认人物资产版式条目", "- **默认人物资产版式（v5.2）**" in skill)
    chk.expect(g, "v5.0 章节头注含 v5.2 补充", "**v5.2 补充**：第 4 步第 1 批" in skill)
    chk.expect(g, "用户提示词例外条款在位", "**例外（v5.2）**" in skill)
    chk.expect(g, "资源索引标注 v5.2 自检", "| `scripts/verify_channels.py` | **v5.3：离线自检" in skill)
    chk.expect(g, "资源索引含 §14.6 逐字模板", "§14.6 v5.2 定稿的上下分区定妆板逐字出图提示词" in skill)

    # --- 逐字模板（byte-exact vs 项目第 4 步 §4.1）
    sec = csp.split("## 14.6 ")[1].split("## 14.7 ")[0]
    block = sec.split("```")[1].strip()
    chk.expect(g, "§14.6 代码块以用户原文开头", block.startswith("生成图中人物的真人形象设定四视图"))
    chk.expect(g, "§14.6 代码块 8 行", len(block.splitlines()) == 8)
    chk.expect(g, "§14.6 逐字模板 1333 字符", len(block) == 1333)
    chk.expect(g, "§14.6 含上 1/3 下 2/3 分区句", "上半部分占画面高度三分之一，下半部分占画面高度三分之二" in block)
    chk.expect(g, "§14.6 含裁头放大格", "头部因画面放大而被完整裁切到画面之外" in block)
    chk.expect(g, "§14.6 含只裁头不许裁手脚", "不能裁掉手、脚或身体主体" in block)
    chk.expect(g, "§14.6 含三点式光位", "正左侧主光，正右侧辅助光，后右侧轮廓光" in block)
    chk.expect(g, "§14.6 含四项禁用", "禁止 AI 油腻感、塑料皮肤感、过度美颜感、廉价 CG 感" in block)
    chk.expect(g, "§14.6 含完整背面全身", "右侧图片为背面全身图" in block)
    chk.expect(g, "§14.6 标注逐字采用不改写", "**v5.2 定稿（用户 2026-11-08 指定「四视图提示词用这个」）**" in csp)
    chk.expect(g, "§14.6 框外写竖版 9:16", "竖版 **9:16**" in sec)
    chk.expect(g, "§14.6 框外写 Nano Banana Pro", "Nano Banana Pro" in sec)
    chk.expect(g, "§14.6 写明 M0 用 ROLE_STILL_X", "把 `ROLE_STILL_X` 作为「参考形象」" in sec)
    chk.expect(g, "§14.6 写明 FACE_CLOSE 从上方左格裁", "从新板**上方左格**" in sec)
    chk.expect(g, "§14.6 含新版 8 项验收", "上下 1/3 : 2/3 分区与四格格位正确" in sec)
    chk.expect(g, "§14.6 旧 2×2 版式已不用", "不再用旧的 `1:1` 四等分 `2×2` 拼板" in sec)
    chk.expect(g, "模板头注改为 v5.2 例外", "**v5.2 例外**" in csp)
    chk.expect(g, "模板头注不再称用户提示词为示例", "只是**示例**" not in csp)

    # --- references
    chk.expect(g, "character-sheet-spec 附录 A.1 写明新版式", "上下分区定妆板（上 1/3 左正面" in css)
    chk.expect(g, "character-sheet-spec 写明逐字采用", "逐字采用用户 2026-11-08 定稿" in css)
    chk.expect(g, "character-sheet-spec A.3 含新版 8 项", "左下放大裁头服装图头部完整出画" in css)
    chk.expect(g, "character-sheet-spec A.7 写明上方左格裁", "上方左格" in css)
    chk.expect(g, "character-sheet-spec 声明扩展包规格另计", "扩展包自身规格" in css)
    chk.expect(g, "input-modes 写明三种模式版式逐字不变", "版式逐字不变" in im)
    chk.expect(g, "input-modes 面部格写明上方左格", "从新版 ROLE_SHEET_X 上方左格裁出（v5.2）" in im)
    chk.expect(g, "model-selection 写明纯净灰影棚三点式", "正左主光 / 正右辅光 / 后右轮廓光" in ms)
    chk.expect(g, "model-selection 用新版 8 项验收", "默认先过上下分区定妆板 8 项" in ms)
    chk.expect(g, "staged-delivery 写明不回退 1:1 四等分", "不回退 1:1 四等分" in sd)
    chk.expect(g, "usage-guide 顶部 v5.2 补充", "**v5.2 人物资产版式补充**" in ug)
    chk.expect(g, "usage-guide 步骤表写明逐字采用", "提示词逐字采用用户定稿" in ug)
    chk.expect(g, "prompt-examples-video 参考绑定同步新版式", "@ROLE_SHEET_X 上下分区定妆板资产" in pev)
    chk.expect(g, "autopilot 协议同步新版式", "ROLE_SHEET_X 上下分区定妆板资产（v5.2 逐字模板）" in ap)

    # --- assets
    chk.expect(g, "overview-template 写明只决定传哪张参考图", "只决定传哪张参考图" in ot)
    chk.expect(g, "theme-brief-template 标注 v5.2", "默认精简 v5.2" in tbt)
    chk.expect(g, "libtv 交接包模板同步新版式", "ROLE_SHEET_X` 上下分区定妆板资产" in lht)
    chk.expect(g, "libtv manifest pairs 同步", '"ROLE_SHEET_X 上下分区定妆板资产"' in lht)
    chk.expect(g, "step-delivery 含第 4 步专项（v5.2）", "第 4 步专项（v5.2）" in tmpl)

    # --- scripts
    chk.expect(g, "model_adapter asset_policy 含 role_sheet_layout", '"role_sheet_layout":' in ma)
    chk.expect(g, "model_adapter asset_policy 含模板来源", '"role_sheet_prompt_source":' in ma)
    chk.expect(g, "model_adapter 含 face_close_source_v52", '"face_close_source_v52":' in ma)
    chk.expect(g, "model_adapter 视频参考同步新版式", '"ROLE_SHEET_X 上下分区定妆板资产"' in ma)
    chk.expect(g, "model_adapter 最终资产写明 v5.2", "**最终人物资产（v5.2）**" in ma)
    chk.expect(g, "build_handoff manifest 含 role_sheet_layout", '"role_sheet_layout":' in bh)
    chk.expect(g, "build_handoff 硬约束同步新版式", "ROLE_SHEET_X` 上下分区定妆板资产（v5.2 逐字模板" in bh)
    chk.expect(g, "build_handoff asset_kind 同步", "人物上下分区定妆板资产" in bh)
    chk.expect(g, "stage_state S3 引导含 v5.2 逐字模板", "v5.2 逐字模板" in ss)
    chk.expect(g, "stage_state M2 写明上方左格", "FACE_CLOSE_X 从新版上方左格裁出" in ss)

    # --- 能力档案
    chk.expect(g, "能力档案 schema 5.8.0", db["schema_version"] == "5.8.0")
    chk.expect(g, "能力档案 planning_rules 42 条", len(db["planning_rules"]) == 42)
    chk.expect(g, "planning_rules 含 role_sheet_layout_rule", "role_sheet_layout_rule" in db["planning_rules"])
    chk.expect(g, "planning_rules 含 role_sheet_acceptance_rule", "role_sheet_acceptance_rule" in db["planning_rules"])
    r = db["planning_rules"]["role_sheet_layout_rule"]
    chk.expect(g, "版式规则写明逐字采用", "逐字采用" in r)
    chk.expect(g, "版式规则写明 M0 不虚构参考图", "不虚构参考图" in r)
    chk.expect(g, "版式规则写明不回退 1:1 四等分", "不回退 1:1 四等分 2×2" in r)
    chk.expect(g, "版式规则写明每人 1 张不变", "每人 1 张" in r)
    chk.expect(g, "版式规则写明扩展包不启用", "扩展定妆包不被启用" in r)
    chk.expect(g, "验收规则写明新版 8 项", "上下分区定妆板 8 项验收" in db["planning_rules"]["role_sheet_acceptance_rule"])
    chk.expect(g, "face_close_video_rule 写明 v5.2 来源", "v5.2 FACE_CLOSE_X 双重身份" in db["planning_rules"]["face_close_video_rule"])
    chk.expect(g, "asset_minimal_rule 写明逐字模板", "逐字采用用户 2026-11-08 定稿" in db["planning_rules"]["asset_minimal_rule"])

    # --- 不回退的锁定口径
    for name, marker in [
        ("人物两类成对", "两类成对"), ("首帧 2 参考", "标准首帧 2 参考"),
        ("色卡两处使用", "色卡两处使用"), ("视频六块结构", "视频六块结构"),
        ("禁用大远景", "禁用大远景 / 远景 / 大全景"), ("风格锁定", "风格锁定"),
    ]:
        chk.expect(g, "锁定口径未回退：%s" % name, marker in skill)


def verify_v53_rules(root, chk):
    """v5.3 跨场景「场景参照 @」规则是否四处同步。"""
    g = "v5.3 跨场景场景参照@同步"
    rd = lambda rel: (SKILL_ROOT / rel).read_text(encoding="utf-8-sig")

    skill = rd("SKILL.md")
    pev = rd("references/prompt-examples-video.md")
    db = json.loads(rd("assets/model_profiles.json"))
    tmpl = rd("assets/step-delivery-template.md")
    ht = rd("assets/libtv-handoff-template.md")
    ma = rd("scripts/model_adapter.py")
    ss = rd("scripts/stage_state.py")
    bh = rd("scripts/build_handoff.py")
    ug = rd("references/usage-guide.md")

    chk.expect(g, "SKILL.md 版本 5.8.0", "version: 5.8.0" in skill)
    chk.expect(g, "SKILL.md 规则标题升为三十三条", "## 三十三条升级规则（v5.8）" in skill)
    chk.expect(g, "第 30 条规则在位", "30. **跨场景「场景参照 @」（v5.3" in skill)
    chk.expect(g, "第 30 条写明逐字句式", "场景参照 @SCENE_MOOD_0X；" in skill)
    chk.expect(g, "第 30 条写明一镜一次", "一镜一次" in skill)
    chk.expect(g, "第 30 条写明单场景不强制", "单场景生成条不强制" in skill)
    chk.expect(g, "第 30 条写明通用性", "适用所有输入模式、运行通道、执行后端" in skill)
    chk.expect(g, "约束新增跨场景条目", "- **跨场景「场景参照 @」（v5.3）**" in skill)
    chk.expect(g, "参数层级锁定项含跨场景绑定", "跨场景「场景参照 @」逐镜绑定" in skill)
    chk.expect(g, "资源索引含 §8.7", "§8.7" in skill)
    chk.expect(g, "工作流 S5 行含跨场景", "跨场景逐镜块按第 30 条" in skill)
    chk.expect(g, "v5.0 章节头注含 v5.3 补充", "**v5.3 补充**：第 5 步" in skill)

    chk.expect(g, "权威章节 §8.7 在位", "### 8.7 跨场景「场景参照 @」规则（v5.3 · 唯一权威）" in pev)
    chk.expect(g, "权威章节写明逐字句式", "场景参照 @SCENE_MOOD_0X；" in pev)
    chk.expect(g, "权威章节写明只进逐镜块", "只进【画面描述】逐镜块" in pev)
    chk.expect(g, "§8.5 自检含第 21 项", "21. 一条生成条含 **≥2 处场景**" in pev)

    chk.expect(g, "能力档案 schema 5.8.0", db["schema_version"] == "5.8.0")
    chk.expect(g, "能力档案 planning_rules 42 条", len(db["planning_rules"]) == 42)
    chk.expect(g, "能力档案含 scene_reference_at_rule", "scene_reference_at_rule" in db["planning_rules"])
    r = db["planning_rules"]["scene_reference_at_rule"]
    chk.expect(g, "规则写明逐字句式", "场景参照 @SCENE_MOOD_0X；" in r)
    chk.expect(g, "规则写明不重复绑定", "两边不重复" in r)
    chk.expect(g, "规则写明通用性", "不是新增上传资产" in r)

    chk.expect(g, "第 5 步模板含 v5.3 专项", "第 5 步专项（v5.3）" in tmpl)
    chk.expect(g, "交接模板含 v5.3 硬约束", "v5.3 跨场景「场景参照 @」" in ht)
    chk.expect(g, "model_adapter 生成字符串含规则", "3c. **跨场景「场景参照 @」（v5.3）**" in ma)
    chk.expect(g, "model_adapter usage 含规则", "v5.3 跨场景「场景参照 @」" in ma)
    chk.expect(g, "stage_state S5 引导含规则", "v5.3 跨场景「场景参照 @」" in ss)
    chk.expect(g, "build_handoff 交接包含规则", "v5.3 跨场景「场景参照 @」" in bh)
    chk.expect(g, "build_handoff manifest 含字段", '"scene_reference_at":' in bh)
    chk.expect(g, "usage-guide 顶部含 v5.3 补充", "v5.3 跨场景「场景参照 @」补充" in ug)

    # 不回退：v5.3 只加一条跨场景写法，其余锁定口径一字不动
    for name, marker in [
        ("六块结构", "【收束与音频】"), ("色卡两处使用", "色卡两处使用"),
        ("一段式母版", "一段连续专业摄影描述"), ("人物两类成对", "两类成对"),
        ("标准首帧 2 参考", "标准首帧 2 参考"), ("禁用大远景", "禁用大远景 / 远景 / 大全景"),
        ("上下分区定妆板", "上下分区定妆板"), ("风格锁定", "风格锁定"),
    ]:
        chk.expect(g, "锁定口径未回退：%s" % name, marker in skill)




V56_SENTENCE = ("主要人物只以以上两类资产为准，是画面里唯一被表现、唯一有清晰正脸与明确动作线的人物；"
                "后景背景人物不占参考位、不给正脸与特写、不与主角同一焦平面、不产生独立动作线、"
                "不新增可辨识妆造，只交代生活感。")


def verify_v58_rules(root, chk):
    """v5.8 手持基底运镜与视线 + 8 处增量口径：四处同步。"""
    g = "v5.8 手持运镜与增量口径同步"
    rd = lambda rel: (SKILL_ROOT / rel).read_text(encoding="utf-8-sig")

    skill = rd("SKILL.md")
    pev = rd("references/prompt-examples-video.md")
    db = json.loads(rd("assets/model_profiles.json"))
    ht = rd("assets/libtv-handoff-template.md")
    sd = rd("assets/step-delivery-template.md")
    ug = rd("references/usage-guide.md")
    ma = rd("scripts/model_adapter.py")
    bh = rd("scripts/build_handoff.py")
    ss = rd("scripts/stage_state.py")

    chk.expect(g, "SKILL.md 版本 5.8.0", "version: 5.8.0" in skill)
    chk.expect(g, "规则标题为三十三条（v5.8）", "## 三十三条升级规则（v5.8）" in skill)
    chk.expect(g, "第 33 条在位", "33. **手持基底运镜与视线" in skill)
    chk.expect(g, "工作流 S5 行含第 33 条", "按第 33 条" in skill)
    chk.expect(g, "资源索引含 §8.11", "§8.11 v5.8" in skill)
    chk.expect(g, "约束含 v5.8 运镜条目", "- **手持基底运镜与视线（v5.8）**" in skill)
    chk.expect(g, "参数层级锁定项含运镜", "手持基底运镜与视线（v5.8" in skill)
    chk.expect(g, "v5.8 增量章节在位", "## v5.8 增量口径" in skill)
    chk.expect(g, "第 33 条写明 v5.7 作废", "v5.8 起作废" in skill)
    for k in ["表情写法", "不要字幕，不要 bgm", "generate_audio", "真人人脸",
              "不设 `first_frame`", "vlog", "短暂自然", "A–D", "原样重提"]:
        chk.expect(g, f"增量章节含 {k}", k in skill)

    sec83 = pev.split("### 8.3 六块结构模板")[1].split("### 8.4")[0]
    chk.expect(g, "§8.3 模板写手持基底", "手持基底" in sec83)
    chk.expect(g, "§8.3 模板无固定机位", "摄影机完全固定" not in sec83 and "不推进不摇移" not in sec83)
    chk.expect(g, "权威章节 §8.10 在位", "### 8.10 手持基底运镜与视线（v5.8 · 唯一权威）" in pev)
    chk.expect(g, "§8.5 自检含第 24 项", "24. **手持基底运镜与视线（v5.8）**" in pev)
    chk.expect(g, "§8.11 增量权威在位", "### 8.11 v5.8 增量口径" in pev)
    chk.expect(g, "§8.11 含 2.5 规格", "4–30 秒" in pev and "50" in pev)

    chk.expect(g, "能力档案 schema 5.8.0", db["schema_version"] == "5.8.0")
    chk.expect(g, "能力档案 planning_rules 42 条", len(db["planning_rules"]) == 42)
    chk.expect(g, "能力档案含 camera_motion_rule", "camera_motion_rule" in db["planning_rules"])
    chk.expect(g, "运镜规则写明手持基底", "手持" in db["planning_rules"]["camera_motion_rule"])
    chk.expect(g, "运镜规则写明 vlog 与直视", "vlog" in db["planning_rules"]["camera_motion_rule"])
    sd25 = db["models"]["seedance-2.5"]
    chk.expect(g, "2.5 规格写 10bit mov", "10bit" in json.dumps(sd25, ensure_ascii=False))
    chk.expect(g, "2.5 规格写不支持真人人脸", "真人人脸" in json.dumps(sd25, ensure_ascii=False))
    chk.expect(g, "2.5 规格写不与 2.0 混用", "2.0 混用" in json.dumps(sd25, ensure_ascii=False))
    chk.expect(g, "2.5 规格写 Draft", "Draft" in json.dumps(sd25, ensure_ascii=False))
    chk.expect(g, "交接模板含第 13 条", "13. **v5.8 手持基底运镜与视线**" in ht)
    chk.expect(g, "交接模板含独立 BGM 条目", "16. **v5.8 独立 BGM**" in ht)
    chk.expect(g, "分步交付模板含 v5.8 专项", "第 5 步专项（v5.8）" in sd)
    chk.expect(g, "使用指引含 v5.8 补充", "v5.8 手持基底运镜与视线补充" in ug)
    chk.expect(g, "使用指引含增量补充", "v5.8 增量口径补充" in ug)
    chk.expect(g, "model_adapter manifest 含 camera_motion", '"camera_motion"' in ma)
    chk.expect(g, "build_handoff manifest 含 camera_motion", '"camera_motion"' in bh)
    chk.expect(g, "stage_state 含 v5.8 运镜", "v5.8 手持基底运镜与视线" in ss)


def verify_v56_rules(root, chk):
    """v5.6 人物层级句定稿：主角唯一性半句保留 + 背景半句简化，四处同步。"""
    g = "v5.6 人物层级句定稿同步"
    rd = lambda rel: (SKILL_ROOT / rel).read_text(encoding="utf-8-sig")

    skill = rd("SKILL.md")
    pev = rd("references/prompt-examples-video.md")
    db = json.loads(rd("assets/model_profiles.json"))
    ht = rd("assets/libtv-handoff-template.md")
    ma = rd("scripts/model_adapter.py")
    bh = rd("scripts/build_handoff.py")

    chk.expect(g, "SKILL.md 版本 5.8.0", "version: 5.8.0" in skill)
    chk.expect(g, "规则标题为三十三条（v5.6）", "## 三十三条升级规则（v5.8）" in skill)
    chk.expect(g, "第 32 条规则在位", "32. **人物层级句定稿" in skill)
    chk.expect(g, "第 32 条写明项目逐字句", "三位主角只以以上两类资产为准" in skill)
    chk.expect(g, "第 32 条写明保留主角唯一性半句", "主角唯一性半句必须保留" in skill)
    chk.expect(g, "第 32 条写明 v5.5 中间态作废", "上一轮「除主要人物外" in skill)
    chk.expect(g, "约束含 v5.6 条目", "- **人物层级句（v5.6）**" in skill)
    chk.expect(g, "资源索引含 §8.9", "§8.9" in skill)
    chk.expect(g, "参数层级锁定项含人物层级句", "人物层级句（v5.6：唯一性半句 + 简化背景半句）" in skill)
    chk.expect(g, "工作流 S5 行含第 32 条", "按第 32 条写定稿的人物层级句" in skill)

    chk.expect(g, "权威章节 §8.9 在位", "### 8.9 人物层级句定稿（v5.6 · 唯一权威）" in pev)
    chk.expect(g, "§8.9 写明用户最终原话", "改成" in pev and "后景背景人物" in pev)
    chk.expect(g, "§8.9 写明通用版", V56_SENTENCE in pev)
    chk.expect(g, "§8.9 写明保留唯一性半句", "主角唯一性半句必须保留" in pev)
    sec83 = pev.split("### 8.3 六块结构模板")[1].split("### 8.4")[0]
    chk.expect(g, "§8.3 模板为定稿句", V56_SENTENCE in sec83)
    chk.expect(g, "§8.3 模板无 v5.5 中间态", "除主要人物外，背景人物不占参考位" not in sec83)
    chk.expect(g, "§8.5 自检含第 23 项", "23. **人物层级句（v5.6）**" in pev)

    chk.expect(g, "能力档案 schema 5.8.0", db["schema_version"] == "5.8.0")
    chk.expect(g, "能力档案 planning_rules 42 条（v5.8 沿用）", len(db["planning_rules"]) == 42)
    chk.expect(g, "人物层级规则含定稿句", V56_SENTENCE in db["planning_rules"]["character_hierarchy_rule"])
    chk.expect(g, "人物层级规则仍含后景焦外细则", "后景焦外" in db["planning_rules"]["character_hierarchy_rule"])
    chk.expect(g, "交接模板含第 12 条", "12. **v5.6 人物层级句定稿**" in ht and "§8.9" in ht)
    chk.expect(g, "model_adapter manifest 含定稿句", V56_SENTENCE in ma)
    chk.expect(g, "build_handoff manifest 含定稿句", V56_SENTENCE in bh)


def verify_v54_rules(root, chk):
    """v5.4 提示词纯净：代码块只写直接告诉 AI 的内容，是否四处同步。"""
    g = "v5.4 提示词纯净同步"
    rd = lambda rel: (SKILL_ROOT / rel).read_text(encoding="utf-8-sig")

    skill = rd("SKILL.md")
    pev = rd("references/prompt-examples-video.md")
    db = json.loads(rd("assets/model_profiles.json"))
    box = rd("assets/step-prompt-box.md")
    tmpl = rd("assets/step-delivery-template.md")
    ht = rd("assets/libtv-handoff-template.md")
    ma = rd("scripts/model_adapter.py")
    ss = rd("scripts/stage_state.py")
    bh = rd("scripts/build_handoff.py")
    ug = rd("references/usage-guide.md")

    chk.expect(g, "SKILL.md 版本 5.8.0", "version: 5.8.0" in skill)
    chk.expect(g, "规则标题升为三十三条", "## 三十三条升级规则（v5.8）" in skill)
    chk.expect(g, "第 31 条规则在位", "31. **提示词纯净" in skill)
    chk.expect(g, "第 31 条写明四类内容", "视频时长 / 视频比例 / 视频类型 / 视频概述" in skill)
    chk.expect(g, "第 31 条写明移出项", "记录种子值" in skill and "生成条编号" in skill)
    chk.expect(g, "第 31 条写明信息不丢", "信息不丢" in skill)
    chk.expect(g, "约束含 v5.4 条目", "- **提示词纯净（v5.4）**" in skill)
    chk.expect(g, "资源索引含 §8.8", "§8.8" in skill)
    chk.expect(g, "参数层级锁定项含提示词纯净", "提示词纯净（v5.4：元信息出代码块）" in skill)
    chk.expect(g, "工作流 S5 行含第 31 条", "按第 31 条只写给 AI 的内容" in skill)

    chk.expect(g, "权威章节 §8.8 在位", "### 8.8 提示词纯净（v5.4 · 唯一权威）" in pev)
    chk.expect(g, "§8.8 写明用户原话", "不是给 ai 看的" in pev)
    chk.expect(g, "§8.8 写明四类内容", "视频时长 / 视频比例 / 视频类型 / 视频概述" in pev)
    chk.expect(g, "§8.8 写明信息不丢", "信息一条不丢" in pev)
    chk.expect(g, "§8.1 表格改为四类", "只写四类直接告诉 AI 的内容" in pev)
    chk.expect(g, "§8.3 模板基本参数以视频时长开头", "【视频基本参数】\n视频时长" in pev)
    chk.expect(g, "§8.2 母版模板不含输出设置", "画幅 [16:9]、成片 [1080p]" not in pev)
    sec83 = pev.split("### 8.3 六块结构模板")[1].split("### 8.4")[0]
    chk.expect(g, "§8.3 模板无旧记录项",
               "本条生成 2–3 条挑 1，记录种子值" not in sec83 and "模型 [模型名]" not in sec83)
    chk.expect(g, "§8.3 模板基本参数以视频时长起句", "视频时长 [X] 秒" in sec83)
    chk.expect(g, "§8.5 自检含第 22 项", "22. **提示词纯净（v5.4）**" in pev)

    chk.expect(g, "能力档案 schema 5.8.0", db["schema_version"] == "5.8.0")
    chk.expect(g, "能力档案 planning_rules 42 条（v5.8 沿用）（就地更新纯净规则）", len(db["planning_rules"]) == 42)
    chk.expect(g, "能力档案含 prompt_purity_rule", "prompt_purity_rule" in db["planning_rules"])
    r = db["planning_rules"]["prompt_purity_rule"]
    chk.expect(g, "规则写明四类", "视频时长" in r and "视频概述" in r)
    chk.expect(g, "规则写明移出平台模型", "平台" in r and "模型" in r)
    chk.expect(g, "规则写明信息不丢", "信息不丢" in r)

    chk.expect(g, "粘贴框规范含 v5.4", "v5.4" in box and "不进代码块" in box)
    chk.expect(g, "第 5 步模板含 v5.4 专项", "第 5 步专项（v5.4）" in tmpl)
    chk.expect(g, "交接模板含 v5.4 硬约束", "v5.4 提示词纯净" in ht)
    chk.expect(g, "model_adapter 生成串含规则", "3d. **提示词纯净（v5.4）**" in ma)
    chk.expect(g, "model_adapter usage 含规则", "v5.4 提示词纯净" in ma)
    chk.expect(g, "stage_state S5 含规则", "v5.4 提示词纯净" in ss)
    chk.expect(g, "build_handoff 交接包含规则", "v5.4 提示词纯净" in bh)
    chk.expect(g, "build_handoff manifest 含字段", '"prompt_purity":' in bh)
    chk.expect(g, "usage-guide 顶部含 v5.4", "v5.4 提示词纯净" in ug)

    for name, marker in [
        ("六块结构", "【收束与音频】"), ("场景参照@", "场景参照 @SCENE_MOOD_0X；"),
        ("色卡两处使用", "色卡两处使用"), ("一段式母版", "一段连续专业摄影描述"),
        ("人物两类成对", "两类成对"), ("禁用大远景", "禁用大远景 / 远景 / 大全景"),
        ("上下分区定妆板", "上下分区定妆板"), ("固定画质段", "明暗过渡稳定"),
        ("风格锁定", "风格锁定"),
    ]:
        chk.expect(g, "锁定口径未回退：%s" % name, marker in skill or marker in pev)


def main():
    ap = argparse.ArgumentParser(description="离线自检 guided / autopilot 两条通道都能跑到 S7")
    ap.add_argument("--keep", action="store_true", help="保留临时自检目录，便于人工检查")
    args = ap.parse_args()

    print("统一色场短片 · 双通道离线自检（v5.8）")
    print("=" * 62)
    print("范围：状态机 S0→S7、自动门禁留痕、三后端交接包、libtv 不可用降级、总时长可变、v4.1/v4.2/v4.3 八项口径 + v5.0 七步引导 + v5.1 人物层级 / 禁用大远景远景 + v5.2 上下分区定妆板默认版式 + v5.3 跨场景「场景参照 @」逐镜绑定 + v5.4 提示词纯净 + v5.6 人物层级句定稿 + v5.8 手持基底运镜与视线")
    print("保证：不联网、不调用任何生成能力、不生成图片视频、不改动真实项目\n")

    chk = Check()
    tmp = tempfile.TemporaryDirectory(prefix="cfaf-verify-")
    root = pathlib.Path(tmp.name)
    try:
        guided_state = verify_guided(root, chk)
        auto_states = {}
        for backend in BACKENDS:
            result = verify_autopilot(root, chk, backend)
            if result:
                auto_states[backend] = result
        verify_autopilot(root, chk, "libtv", libtv_status="unavailable")
        verify_duration_variability(root, chk)
        verify_v43_rules(root, chk)
        verify_v50_rules(root, chk)
        verify_v51_rules(root, chk)
        verify_v52_rules(root, chk)
        verify_v53_rules(root, chk)
        verify_v54_rules(root, chk)
        verify_v56_rules(root, chk)
        verify_v58_rules(root, chk)

        g = "两通道一致性"
        if guided_state and auto_states:
            chk.expect(g, "guided 与 autopilot 放行阶段集合相同",
                       all(set(guided_state["confirmed"]) == set(st[0]["confirmed"])
                           for st in auto_states.values()))
            chk.expect(g, "两条通道都到达 S7",
                       guided_state["current"] == "S7" and
                       all(st[0]["current"] == "S7" for st in auto_states.values()))
            base = auto_states["libtv"][1]
            chk.expect(g, "换后端不改硬约束",
                       all(st[1]["hard_constraints"] == base["hard_constraints"]
                           for st in auto_states.values()))
            # 幂等键含项目目录哈希，不同后端目录天然不同；只比较规划本身
            def planning_units(m):
                return [{k: v for k, v in u.items() if k != "idempotency_key"}
                        for u in m["generation_units"]]
            chk.expect(g, "换后端不改生成条规划（幂等键除外）",
                       all(planning_units(st[1]) == planning_units(base)
                           for st in auto_states.values()))
            chk.expect(g, "三后端交接包都可执行", len(auto_states) == 3)
            for key in ["character_hierarchy", "background_figure_placement", "shot_scale_policy", "scene_reference_at", "prompt_purity"]:
                chk.expect(g, "三后端 manifest 含 %s" % key,
                           all(key in st[1]["hard_constraints"] for st in auto_states.values()))
        code = chk.report()
        if args.keep:
            kept = pathlib.Path.cwd() / "cfaf-verify-output"
            print(f"临时目录已保留：{root}（--keep 已启用，可自行复制 {kept}）")
        else:
            print("临时自检目录已清理；未产生任何图片、视频或网络请求。")
        print("\n结论：" + ("两条通道都能从 S0 跑到 S7，autopilot 三种后端均可用，v4.1/v4.2/v4.3 八项口径、v5.0 七步引导、v5.1 人物层级 / 禁用大远景远景、v5.2 上下分区定妆板默认版式、v5.3 跨场景「场景参照 @」逐镜绑定、v5.4 提示词纯净、v5.6 人物层级句定稿与 v5.8 手持基底运镜与视线已四处同步。" if code == 0
                          else "存在失败项，请先修复再交付。"))
        return code
    finally:
        if not args.keep:
            tmp.cleanup()
        else:
            # keep: detach cleanup so the directory survives
            tmp._finalizer.detach()


if __name__ == "__main__":
    sys.exit(main())
