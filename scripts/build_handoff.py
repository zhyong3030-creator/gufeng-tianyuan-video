#!/usr/bin/env python3
"""Build an autopilot handoff package from an S0-S5 color-field production package.

v4.0 (pluggable execution backends; file names kept for compatibility):
  python3 build_handoff.py --project <项目目录> --backend libtv
  python3 build_handoff.py --project <项目目录> --backend workbuddy
  python3 build_handoff.py --project <项目目录> --backend external
  python3 build_handoff.py --project <项目目录> --backend libtv \
      --libtv-status unavailable --picks-per-unit 3 --out-dir <输出目录>

v5.0 说明：七大步小白引导只是交付层（每小步弹选择框、每条提示词各一个粘贴框）；
用户显式授权 autopilot 时跳过引导，本脚本仍按原有硬约束逐字打包，提示词一字不动。

Outputs (text only):
  libtv_handoff.md            给执行后端的中文执行指令 + 全部硬约束 + 按后端的跑法
  libtv_manifest.json          机器可读清单（execution_backend / 生成条 / 上限 / 降级 / 验收）
  libtv_assets_manifest.json   参考资产清单（ID / 路径 / 是否上传）

libtv is PREFERRED but NOT REQUIRED: autopilot must still run end-to-end when
LibTV is not connected, via --backend workbuddy or --backend external.

This script is PURE PACKAGING: it reads project files and writes three text
files. It never calls any generation API, never creates images or videos,
never connects to the network, and never modifies existing project files.
"""
import argparse
import csv
import datetime
import hashlib
import json
import pathlib
import re
import sys

SCHEMA_VERSION = "4.0.0"
VIDEO_BLOCKS = ["视频基本参数", "参考绑定", "摄影母版", "禁止项", "画面描述", "收束与音频"]
UPLOAD_ORDER = ["首帧", "COLOR_CARD_01", "〔可选〕SCENE_REVERSE_0X", "ROLE_SHEET_X + FACE_CLOSE_X 成对"]
BACKENDS = {
    "libtv": {
        "name": "LibTV Agent 托管",
        "actor": "LibTV 后端 Agent（Canvas run_agent 或 agent-im 会话）",
        "attribution": "libtv Agent 生成",
        "completion": "get_agent_status 回读 artifacts + 实际导出成片 + color_field_audit.py 验收",
        "note": "需要平台连接、项目写权限与 confirmSpend；autoGenerate=true 才允许媒体制作。",
    },
    "workbuddy": {
        "name": "WorkBuddy 内生成能力",
        "actor": "当前 WorkBuddy 会话，按交接清单逐条调用生成能力",
        "attribution": "WorkBuddy 生成",
        "completion": "逐条生成结果落盘 + 拼接导出成片 + color_field_audit.py 验收",
        "note": "不依赖 libtv；仍须用户确认本次生成的数量上限，逐条留种子值与挑片结果。",
    },
    "external": {
        "name": "用户自有平台批量",
        "actor": "用户或用户侧脚本，按批处理清单在自己的平台粘贴执行",
        "attribution": "用户平台生成",
        "completion": "用户回传逐条结果与成片 + color_field_audit.py 验收",
        "note": "交接包退化为按序执行的批处理清单 + 使用步骤；不联网、不代用户操作平台。",
    },
}
SOURCE_FILES = [
    "提示词全集.md", "注意点全集.md", "000_先看这个-操作手册.md", "01_色场方案表.md",
    "shot_list.csv", "generation_plan.json", "stage_state.json", "master_overview.md",
]
ASSET_PREFIXES = (
    "ROLE_SHEET_", "FACE_CLOSE_", "COLOR_CARD_", "SCENE_REVERSE_", "SCENE_MOOD_",
    "SCENE_REF_", "STANDARD_FRAME_", "VISUAL_MASTER_", "FABRIC_DETAIL_",
    "CHARACTER_MOOD_", "OUTFIT_", "ROLE_STILL_", "PHOTO_MASTER_",
)
ASSET_RE = re.compile(r"\b(?:ROLE_SHEET|FACE_CLOSE|COLOR_CARD|SCENE_REVERSE|SCENE_MOOD|SCENE_REF|STANDARD_FRAME|VISUAL_MASTER|FABRIC_DETAIL|CHARACTER_MOOD|OUTFIT|ROLE_STILL|PHOTO_MASTER)_[A-Z0-9]+\b")
PAIR_RE = re.compile(r"\bROLE_SHEET_([A-Z])\b")
CLOSE_RE = re.compile(r"\bFACE_CLOSE_([A-Z])\b")
A_HEAD_RE = re.compile(r"^###\s+(A\d+)\s*·\s*`?([A-Z0-9_]+)`?\s*·\s*(.+)$", re.M)
C_HEAD_RE = re.compile(r"^###\s+(C\d+)\s*·\s*(U\d+)", re.M)
IMAGE_EXT = (".png", ".jpg", ".jpeg", ".webp")


def read_json(path, default=None):
    if not path.exists():
        return {} if default is None else default
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        print(f"[警告] 无法解析 {path.name}: {exc}", file=sys.stderr)
        return {} if default is None else default


def read_text(path):
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8-sig", errors="replace")


def read_shots(path):
    if not path.exists():
        return []
    try:
        with path.open(encoding="utf-8-sig", newline="") as fh:
            return list(csv.DictReader(fh))
    except (UnicodeDecodeError, csv.Error) as exc:
        print(f"[警告] 无法解析 {path.name}: {exc}", file=sys.stderr)
        return []


def stable_prefix(project):
    """Stable, regex-safe idempotency key prefix (letters/digits only)."""
    digest = hashlib.sha1(str(project.resolve()).encode("utf-8")).hexdigest()[:8]
    return f"cfaf-{digest}-v1"


def find_asset_file(project, asset_id):
    """Return a relative path if a real image exists; never invent one."""
    candidates = [project / "assets" / f"{asset_id}{ext}" for ext in IMAGE_EXT]
    candidates += [project / f"{asset_id}{ext}" for ext in IMAGE_EXT]
    for c in candidates:
        if c.is_file():
            return str(c.relative_to(project))
    # 用户原始素材可能用了中文命名：只标注目录存在，不猜测文件名
    return None


def asset_kind(asset_id):
    if asset_id.startswith("ROLE_SHEET_"):
        return "人物上下分区定妆板资产（唯一最终人物资产，v5.2 逐字模板）"
    if asset_id.startswith("FACE_CLOSE_"):
        return "人脸特写（唯一允许进视频的过程件）"
    if asset_id.startswith("COLOR_CARD_"):
        return "成品色卡出图提示词生成的 12 色色卡（A 段场景图取色彩方案 + C 段【参考绑定】上传）"
    if asset_id.startswith("PHOTO_MASTER_"):
        return "摄影母版文字块（不是图片）"
    if asset_id.startswith("STANDARD_FRAME_"):
        return "标准首帧（U01 画面起点）"
    if asset_id.startswith(("SCENE_REVERSE_", "SCENE_REF_", "SCENE_MOOD_")):
        return "场景参考"
    if asset_id.startswith("VISUAL_MASTER_"):
        return "全片视觉母版（定基调，不挂色卡、不上传）"
    if asset_id.startswith("FABRIC_DETAIL_"):
        return "服装材质特写（仅按需）"
    return "过程资产（不上传）"


def should_upload(asset_id):
    if asset_id.startswith("PHOTO_MASTER_"):
        return False
    if asset_id.startswith(("CHARACTER_MOOD_", "OUTFIT_", "ROLE_STILL_", "VISUAL_MASTER_", "SCENE_MOOD_")):
        return False
    if asset_id.startswith("FABRIC_DETAIL_"):
        return False  # 仅材质画错时按需
    return True


def build_units(plan, shots, cid_map, prefix, picks, max_retries, no_first_frame_units=()):
    """Normalize generation units from either the project plan or model_adapter output."""
    raw_units = plan.get("units") or plan.get("generation_units") or []
    if not raw_units:
        return [], ["generation_plan.json 里没有 units，无法打包生成条"]

    by_unit = {}
    for row in shots:
        uid = (row.get("生成条ID") or "").strip()
        if uid:
            by_unit.setdefault(uid, []).append(row)

    units, warns = [], []
    for idx, u in enumerate(raw_units, 1):
        uid = str(u.get("unit") or u.get("id") or f"U{idx:02d}")
        start = u.get("start", 0)
        end = u.get("end", start + (u.get("seconds") or 0))
        seconds = u.get("seconds") or u.get("duration_seconds") or (end - start)
        rows = by_unit.get(uid, [])

        ref_text = " ".join([str(r.get("参考图ID") or "") for r in rows])
        for beat in u.get("beats", []) or []:
            ref_text += " " + str(beat.get("refs") or "")
        if not ref_text.strip():
            ref_text = " ".join(str(x) for x in (u.get("references") or []))
        found = ASSET_RE.findall(ref_text)

        scene_refs, char_refs, other_refs = [], [], []
        for a in dict.fromkeys(found):
            if a.startswith("SCENE_"):
                scene_refs.append(a)
            elif a.startswith(("ROLE_SHEET_", "FACE_CLOSE_")):
                char_refs.append(a)
            elif a.startswith("COLOR_CARD_"):
                other_refs.append(a)
            elif a.startswith(("STANDARD_FRAME_", "FABRIC_DETAIL_")):
                other_refs.append(a)

        # 自动补齐两类成对：只有拼板没有人脸时补 FACE_CLOSE_<同字母>
        auto_paired = []
        sheets = set(PAIR_RE.findall(" ".join(char_refs)))
        closes = set(CLOSE_RE.findall(" ".join(char_refs)))
        for letter in sorted(sheets - closes):
            auto_paired.append(f"FACE_CLOSE_{letter}")
            char_refs.append(f"FACE_CLOSE_{letter}")
        if auto_paired:
            warns.append(f"{uid} 自动补齐人脸特写 {', '.join(auto_paired)}（两类成对口径）")
        char_refs = list(dict.fromkeys(char_refs))

        prompt_id = cid_map.get(uid) or f"C{idx:02d}"
        if rows:
            prompt_from_csv = (rows[0].get("提示词ID") or "").strip()
            # 分镜表的 Pxx 是镜头级 ID，Cxx 才是生成条提示词 ID
            if prompt_from_csv.startswith("C"):
                prompt_id = prompt_from_csv

        step = (rows[0].get("使用步骤") or "") if rows else ""
        explicit = u.get("first_frame") or u.get("start_frame")
        m = re.search(r"首帧\s*`?([A-Z][A-Z0-9_]*)`?", step)
        if uid in no_first_frame_units or "不设首帧" in step or explicit in ("none", "不设首帧"):
            first_frame = "不设首帧"
        elif isinstance(explicit, str) and explicit:
            first_frame = explicit
        elif m and (m.group(1).startswith("STANDARD_FRAME") or m.group(1).endswith("_LAST")):
            first_frame = m.group(1)
        elif idx == 1:
            first_frame = "STANDARD_FRAME_01"
        else:
            first_frame = f"U{idx-1:02d}_LAST.png（上一条末帧）"

        units.append({
            "id": uid,
            "prompt_id": prompt_id,
            "duration_seconds": seconds,
            "timecode": f"{start:g}–{end:g}s",
            "shot_ids": u.get("shot_ids") or [r.get("镜号") for r in rows if r.get("镜号")],
            "beat_count": len(u.get("beats") or []) or len(rows),
            "first_frame": first_frame,
            "scene_references": scene_refs,
            "character_references": char_refs,
            "other_references": other_refs,
            "picks": picks,
            "max_retries": max_retries,
            "idempotency_key": f"{prefix}-{uid}",
        })
    return units, warns


def a_asset_rows(prompt_text):
    rows = []
    for idx, (aid, asset_id, title) in enumerate(A_HEAD_RE.findall(prompt_text), 1):
        if asset_id.startswith("PHOTO_MASTER_"):
            up = "否（文字块，不生成图、不上传）"
        elif asset_id.startswith("COLOR_CARD_"):
            up = "A 段取色彩方案 + C 段【参考绑定】"
        elif asset_id.startswith(("VISUAL_MASTER_", "SCENE_MOOD_")):
            up = "否（定基调 / 场景基调来源，不进视频上传）"
        elif asset_id.startswith(("STANDARD_FRAME_", "SCENE_REVERSE_", "SCENE_REF_")):
            up = "是（首帧 / 场景一致性版）"
        else:
            up = "按 A 段说明"
        rows.append(f"| {idx} | `{aid}` | `{asset_id}` · {title.strip()} | {up} |")
    return rows


def render_handoff(ctx):
    a_rows = "\n".join(ctx["a_rows"]) or "| — | — | 未找到 A 段标题，请检查 `提示词全集.md` | — |"
    unit_rows = "\n".join(ctx["unit_rows"])
    upload_lines = "\n".join(f"{i+1}. {x}" for i, x in enumerate(UPLOAD_ORDER))
    missing = "\n".join(f"- `{x}`" for x in ctx["missing"]) or "- 无，生产包文件齐全"
    return f"""# {ctx['theme']} · 统一色场短片生产包（已定稿，请逐字执行）

> 本文件由 `build_handoff.py` 生成于 {ctx['generated_at']}；项目当前运行通道 `{ctx['run_mode']}`，**执行后端 `{ctx['backend']}`（{ctx['backend_name']}）**，libtv 接法 {ctx['platform']}。
> 唯一生效提示词源是 `提示词全集.md`；本文件只负责说明「怎么按包执行」，不重写任何提示词。
> **风格固定**：本片为「中式古装田园 / 暖调统一色场」类短片，任何后端都不得把色场、光位、肤色与质感换成别的风格。
{ctx['auth_note']}
{ctx['status_note']}

## 0. 执行约束（最高优先级，先读这一段）

1. 本包为**已定稿生产包**。所有提示词必须逐字执行，**不得重写、扩写、翻译、精简或自行重新拆分镜与写 prompt**；不得把六块结构压成一段自然语言描述。
2. `COLOR_CARD_01` 由 **A08 成品色卡出图提示词**（12 个 HEX 写死、纯文字出图、不传参考图）生成；「12 色归纳」中文只是生成它的 meta 指令，**不进包、不复制**。色卡**两处使用**：`A01–A0N` 场景基调图与可选反打同传只取色彩方案（12 色色值 / 主辅结构 / 五级明度，不取色块版式与标注文字）、`C01–C03`【参考绑定】上传；`A00` 母版 / 标准首帧 / 人物资产仍不挂色卡，全阶段不写 `--sref`。色卡必须先于 A01 完成。即：在 A 段场景图取色彩方案、在每条视频提示词的【参考绑定】为第二处使用。
3. `PHOTO_MASTER_01` 摄影母版是**中文文字块**，v4.3 起为**一段连续专业摄影描述**（只写跨镜头统一项、不含具体焦段；焦段与 T 光圈下放到逐镜块）；它**不是图片，不生成、不上传、不占参考位**，每条生成条逐字复用同一份。C 段【画面描述】= 全局设定段 +【镜头N | 时间码 | 镜头名】逐镜块，焦段与 T 光圈只在逐镜块给。
4. 人物参考**只有两类成对**：`ROLE_SHEET_X` 上下分区定妆板资产（v5.2 逐字模板：上 1/3 正侧面头肩特写 / 下 2/3 放大裁头正面服装图与背面全身）+ `FACE_CLOSE_X` 人脸特写（从新版上方左格裁出），每位出镜角色一组；不挂四宫格、定妆基准、四格板、单独三视图与服装放大图。**v5.1 人物层级**：主角是唯一被表现、唯一有身份资产的人物；后景焦外可有 1–3 个不具名背景人影，不占参考位、不给正脸与特写、不与主角同焦平面、不产生独立动作线，只写进逐镜块的背景层与环境动态。
5. 主辅色占比、九宫格覆盖、五级明度由色场方案表与摄影母版写死，**不从色卡取**；柔光与光晕全片统一加一次，不逐镜叠加。
6. 提示词正文一律简体中文；仅平台参数、资产 ID、器材型号与色值、模型专有名保留原文。
7. 若平台模型、参考位或时长不支持，按 `libtv_manifest.json` 的 `degradation` 表降级并**记录偏差**，不得悄悄改色场规则。
8. 生成次数上限为 **{ctx['max_total']} 次**（{ctx['unit_count']} 条 × 每条 {ctx['picks']} 次，单条最多重跑 {ctx['max_retries']} 次）；**超限即停并汇报，不静默重跑**。
9. **风格固定**：本 skill 只做「中式古装田园 / 暖调统一色场」这一类。暖调色场、斜后侧主光、暖象牙—蜜桃肤色、奶油金高光与柔焦质感是风格常量；换主题只换主题、人物、物件与剧情，**不得换成别的视觉风格，不得放宽三条铁律**。**全片禁用大远景 / 远景 / 大全景**（用户 2026-11-08 二次纠偏）：景别只在全景及更近档位之间拉开，背景人影只作后景焦外虚化层，不做纪念碑式空镜头。
10. **v5.3 跨场景「场景参照 @」**：一条生成条装了不止一处场景时，【画面描述】每个逐镜块正文开头逐字写 `场景参照 @SCENE_MOOD_0X；` 再接三层空间句，一镜一次、只 @ 本镜那一处；只写进逐镜块，【参考绑定】不重复绑定说明；句式不得改写，单场景条不强制。这不是新增上传资产，参考张数不因此变化。
11. **v5.4 提示词纯净**：C 段代码块只写直接告诉 AI 的内容，【视频基本参数】只写视频时长 / 视频比例 / 视频类型 / 视频概述；平台 / 模型 / 档位 / 生成条编号 / 成片时间码 / 挑片 / 记录种子 / 剪辑台衔接 / 跨步骤说明 / 按需补图一律移到说明层，不得写进提示词；被删信息必须在说明层找得到。A 段出图提示词不受影响。
12. **v5.8 手持基底运镜与视线**：**手持是基底、幅度清晰可辨**：画面随步伐与动作有看得出来的轻微上下浮动、左右摆移、构图偏移与找平，带呼吸起伏、身体移动惯性与随手记录的 vlog 实拍感，不剧烈抖动、不甩镜；**其上每镜按需叠一种轻微的推 / 拉 / 摇 / 移或轻微变焦**来重新取景，不同时堆满多种运动、禁变焦冲击与急速推拉，各镜附加运动不重样、末镜只放慢不停住；**允许人物短暂自然地看向镜头**，但不面对镜头表演、不做夸张鬼脸与现代自拍式表情。写在动作句之后、景深句之前。v5.7「缓慢推拉摇移、禁固定镜头 / 禁手持 / 禁直视」为历史口径，v5.8 起作废。 见 §8.10。

## 1. 任务目标

- 主题：{ctx['theme']}
- 成片：{ctx['duration']} 秒 / {ctx['shot_count']} 镜 / {ctx['scene_count']} 个场景 / {ctx['aspect']} / {ctx['resolution']}
- 输入模式：`{ctx['input_mode']}`；运行通道：`autopilot`
- 图像模型：{ctx['image_model']}
- 视频模型：{ctx['video_model']}
- 生成条：{ctx['unit_count']} 条，逐条 ID 与时间码见第 4 节

## 2. 必须先完成的参考资产（按 A 段提示词逐条执行）

| 顺序 | 提示词 ID | 产出 | 上传 |
|---|---|---|---|
{a_rows}

**色卡**：直接复制生产包 A08 的**成品色卡出图提示词**纯文字出图，不上传任何参考图；12 个 HEX 与用途已写死。归纳 meta 指令只作方法，不要粘到平台。若项目另行提供归纳素材且明显分成两组色温 / 色相，**先停下提醒重新分组，不要强行合并**。
**场景反打**：`SCENE_REVERSE_0X` 是**可选**资产。生产包标注「不用」时整步跳过，C 段【参考绑定】删掉对应 `@SCENE_REVERSE_0X` 行、上传张数相应减少；**不要凭空补一张不存在的反打图**。
**标准首帧**：只同传 2 参考（`ROLE_SHEET_<主角>` + 场景参考 1 张：用了可选反打是 `SCENE_REVERSE_01`，跳过则是 `SCENE_MOOD_01`），**不带色卡**。
**摄影母版**：A10 是文字块，直接复制到每条 C 段提示词的【摄影母版】块，不生成图片。

## 3. 上传顺序（每条生成条相同）

```
{upload_lines}
```

人物部分：每位出镜角色成对上传 `ROLE_SHEET_X` + `FACE_CLOSE_X`。参考位不足时优先保 `ROLE_SHEET_X`，人脸特写优先给近景多的生成条；`FABRIC_DETAIL_X` 仅在材质被画错时按需补 1 张。视觉母版、场景基调版、人物过程图与摄影母版**一律不占参考位**。各条参考图张数：{ctx['upload_counts_text']}。

{ctx['backend_section']}

## 4. 生成条清单（C 段提示词逐字执行）

| 生成条 | 提示词 | 时长 | 成片时间码 | 首帧 | 场景参考 | 人物参考（两类成对） | beat 数 |
|---|---|---|---|---|---|---|---|
{unit_rows}

每条生成条的可复制提示词在 `提示词全集.md` 的 C 段，固定六块结构【视频基本参数】【参考绑定】【摄影母版】【禁止项】【画面描述】【收束与音频】；【禁止项】内部为正向句。每条生成 {ctx['picks']} 次挑 1，最多重跑 {ctx['max_retries']} 次，记录种子值、档位与参考编号。

## 5. 拼接、调色与导出

1. 按 `shot_list.csv` 的时间码切开生成条，按镜序拼接；切点类型（不设切点 / 匹配接续 / 硬切）以分镜表与 `generation_plan.json` 的 `seam_policy` 为准。
2. 全片统一加一次柔光与统一 LUT，**不逐镜叠加**；不加字幕、不叠水印、不引入生产包之外的音乐与对白。
3. 导出 {ctx['aspect']} / {ctx['resolution']} 成片（可先出 720p 打样、定稿升 1080p），命名为 `{ctx['theme']}-成片.mp4`。
4. 回传：成片链接或本地文件、每条生成条的结果与实际生成次数、与生产包不一致之处（如有）。

## 6. 完成标准

同时满足：全部生成条都有结果；已按分镜表拼成一支完整成片；实际生成次数未超过 {ctx['max_total']} 次；成片通过色场验收（主色覆盖 3×3 九分区、光位与肤色稳定、无跨条跳色）。**只给进度卡或派发回执不算完成。**
本后端的完成判定：{ctx['backend_completion']}。产物归属统一标注「**{ctx['backend_attribution']}**」，不冒充本 skill 产出。

## 7. 本包文件与缺失项

缺失的生产包文件：

{missing}

以上缺失项需先补齐；打包脚本不会替你生成图片、也不会虚构不存在的参考图。
"""


def build_manifest(ctx, units):
    return {
        "schema_version": SCHEMA_VERSION,
        "run_mode": ctx["run_mode"],
        "execution_backend": ctx["backend"],
        "execution_backend_name": ctx["backend_name"],
        "execution_actor": ctx["backend_actor"],
        "platform_status": ctx["libtv_status"],
        "requires_fallback": ctx["requires_fallback"],
        "input_mode": ctx["input_mode"],
        "theme": ctx["theme"],
        "project_dir": str(ctx["project"]),
        "generated_at": ctx["generated_at"],
        "target_platform": ctx["platform"] if ctx["backend"] == "libtv" else "n/a（非 libtv 后端）",
        "spec": {
            "duration_seconds": ctx["duration"], "shot_count": ctx["shot_count"],
            "scene_count": ctx["scene_count"], "aspect": ctx["aspect"],
            "resolution": ctx["resolution"],
        },
        "models": {
            "image_chain": ctx["image_model"], "video": ctx["video_model"],
            "selected_from": "生产包定稿组合 / 能力档案 active 主推组合",
        },
        "hard_constraints": {
            "prompt_verbatim": True, "no_rewrite_no_translate": True,
            "color_card_two_usages": True, "color_card_scene_color_scheme_only": True,
            "no_sref_in_image_stage": True,
            "photography_master_is_text_block": True,
            "photography_master_upload": False,
            "video_prompt_structure": VIDEO_BLOCKS,
            "character_reference_pairs": ["ROLE_SHEET_X 上下分区定妆板资产", "FACE_CLOSE_X 人脸特写"],
            "role_sheet_layout": "v5.2 默认 ROLE_SHEET_X 为上下分区定妆板（上 1/3 正侧面头肩特写 + 下 2/3 放大裁头正面服装图与背面全身），出图提示词逐字采用用户定稿、不改写；FACE_CLOSE_X 从新版上方左格裁出",
            "character_hierarchy": "主要人物只以以上两类资产为准，是画面里唯一被表现、唯一有清晰正脸与明确动作线的人物；后景背景人物不占参考位、不给正脸与特写、不与主角同一焦平面、不产生独立动作线、不新增可辨识妆造，只交代生活感。 其余细则见 SKILL.md 第 28 条与 §8.6",
            "background_figure_placement": "只写进画面描述逐镜块的三层空间→背景 与 环境动态；禁止项用正向句写边界；参考绑定不新增人物资产",
            "shot_scale_policy": "禁用大远景/远景/大全景；景别只在全景及更近档位之间拉开，背景人影只作后景焦外虚化层，三条铁律其余取值不变",
            "standard_frame_reference_count": 2,
            "prompt_language": "zh",
            "scene_reference_at": "v5.3 跨场景：一条生成条含 ≥2 处场景时，画面描述每个逐镜块正文开头逐字写 场景参照 @SCENE_MOOD_0X；一镜一次、只 @ 本镜那一处；只写进逐镜块、参考绑定不重复；句式锁定、单场景条不强制",
            "prompt_purity": "v5.4 C 段代码块只写直接告诉 AI 的内容；视频基本参数只写时长/比例/类型/概述；平台/模型/档位/编号/成片时间码/挑片/记录种子/剪辑台衔接/跨步骤说明/按需补图全部移到说明层且信息不丢",
            "camera_motion": "v5.8 手持基底幅度清晰可辨 + 每镜一种轻微推拉摇移或变焦、vlog 实拍感、可短暂直视；禁剧烈抖动/甩镜/变焦冲击/急速推拉",
            "soft_light_applied_once_globally": True,
        },
        "generation_units": units,
        "limits": {
            "generation_unit_count": len(units),
            "picks_per_unit": ctx["picks"],
            "max_total_generations": ctx["max_total"],
            "max_retries_per_unit": ctx["max_retries"],
            "stop_on_limit": True,
        },
        "idempotency_key_prefix": ctx["prefix"],
        "upload_order": UPLOAD_ORDER,
        "upload_counts": ctx["upload_counts"],
        "degradation": {
            "model_unavailable": "search_models 找同档位替代，重算生成条时长与条数并写回本清单",
            "reference_slots_insufficient": "优先保首帧 → 色卡 → ROLE_SHEET_X；FACE_CLOSE_X 给近景多的条",
            "no_multi_image": "用 SCENE_REVERSE_01（启用了可选反打）或 SCENE_MOOD_01（跳过反打）合成首帧承载空间信息，人物走 ROLE_SHEET_X 单张",
            "duration_cap_hit": "按时间码拆条并以上一条末帧接续，不拉长镜头",
            "auto_translation": "关闭自动翻译，要求逐字执行中文原文",
            "color_group_split": "停下提醒重新分组，不强行合并成一张灰卡",
            "audit_failed": "按首帧 → 提示词 → 统一调色 → 模型顺序修",
        },
        "backend_detail": {
            "backend": ctx["backend"],
            "name": ctx["backend_name"],
            "actor": ctx["backend_actor"],
            "note": ctx["backend_note"],
            "execution_section": "见 libtv_handoff.md 的「执行后端与跑法」一节",
        },
        "libtv": {
            "applicable": ctx["backend"] == "libtv",
            "recommended_path": ctx["platform"],
            "canvas": {
                "create_project": "create_project(name, idempotencyKey)",
                "upload": "upload_ticket + upload_complete → documents[].fileRef",
                "delegate": "run_agent(message, autoGenerate=true, idempotencyKey, documents)",
                "poll": "get_agent_status(runId / agentSession)",
                "approve": "resolve_agent_action(精确 actionId, confirmSpend)",
                "export": "export_readiness → export_video → task_status",
                "deliver": "prepare_project_delivery → get_web_operation_status",
                "stop": "stop_agent_run",
            },
            "agent_im_fallback": "upload_file.py → create_session.py 一条消息 → query_session.py 轮询 → download_results.py",
        },
        "acceptance": {
            "completion_requires": ["get_agent_status 回读 artifacts", "实际导出的成片", "color_field_audit.py 通过"],
            "audit_command": "python3 scripts/color_field_audit.py <成片.mp4> --start 0 --end <时长> --out audit_report.json --csv audit_frames.csv",
            "attribution": ctx["backend_attribution"],
        },
        "source_files": SOURCE_FILES,
        "missing_source_files": ctx["missing"],
        "warnings": ctx["warnings"],
    }


def build_assets_manifest(ctx, units, prompt_text):
    ids = []
    for u in units:
        ids += u["scene_references"] + u["character_references"] + u["other_references"]
    ids += ASSET_RE.findall(prompt_text)
    ids = list(dict.fromkeys(ids))
    # 摄影母版必须出现，且标注不上传
    if "PHOTO_MASTER_01" not in ids:
        ids.append("PHOTO_MASTER_01")
    assets = []
    for aid in sorted(ids):
        local = find_asset_file(ctx["project"], aid)
        assets.append({
            "id": aid,
            "kind": asset_kind(aid),
            "local_path": local,
            "exists": bool(local),
            "upload": should_upload(aid),
            "used_in": ["C 段【参考绑定】"] if should_upload(aid) else ["仅生产阶段 / 文字块"],
        })
    return {
        "theme": ctx["theme"],
        "assets": assets,
        "notes": [
            "exists=false 表示本地还没有这张图，需先按 A / B 段提示词生成；脚本不会虚构图片",
            "upload=false 的项一律不占参考位；PHOTO_MASTER_01 是文字块，不是图片",
            "用户原始素材若为中文命名，请按 A 段说明裁切后重命名到 assets/ 目录",
        ],
    }


def main():
    ap = argparse.ArgumentParser(description="把 S0–S5 生产包打成 libtv 交接包（纯打包）")
    ap.add_argument("--project", required=True, help="项目目录")
    ap.add_argument("--out-dir", default="", help="输出目录，默认与项目目录相同")
    ap.add_argument("--picks-per-unit", type=int, default=3, help="每条生成条挑片生成次数，默认 3")
    ap.add_argument("--max-retries", type=int, default=1, help="单条最多重跑次数，默认 1")
    ap.add_argument("--platform", choices=["canvas_agent", "agent_im"], default="canvas_agent",
                    help="仅 --backend libtv 时有效：Canvas Agent 或 agent-im 会话")
    ap.add_argument("--backend", choices=["libtv", "workbuddy", "external"], default="libtv",
                    help="autopilot 执行后端；libtv 不可用时改 workbuddy / external，autopilot 仍可跑通")
    ap.add_argument("--libtv-status", choices=["available", "unavailable", "unknown"], default="unknown",
                    help="libtv 连接状态，由调用方判断后传入；脚本不联网、不自行检测")
    ap.add_argument("--no-first-frame", default="",
                    help="逗号分隔的不设首帧的生成条 ID，例如 U03；不填则按分镜表「使用步骤」判定")
    args = ap.parse_args()
    if args.picks_per_unit < 1 or args.max_retries < 0:
        ap.error("--picks-per-unit 必须 ≥1，--max-retries 必须 ≥0")
    no_first_frame_units = tuple(x.strip() for x in args.no_first_frame.split(",") if x.strip())

    project = pathlib.Path(args.project).expanduser().resolve()
    if not project.is_dir():
        print(f"项目目录不存在：{project}", file=sys.stderr)
        return 1
    out_dir = pathlib.Path(args.out_dir).expanduser().resolve() if args.out_dir else project
    out_dir.mkdir(parents=True, exist_ok=True)

    plan = read_json(project / "generation_plan.json")
    if not plan:
        print("缺少有效的 generation_plan.json，停止打包（先跑 model_adapter.py 或补齐 S2 规划）。", file=sys.stderr)
        return 1
    state = read_json(project / "stage_state.json")
    prompt_text = read_text(project / "提示词全集.md")
    shots = read_shots(project / "shot_list.csv")

    missing = [f for f in SOURCE_FILES if not (project / f).is_file()]
    warnings = []
    if not prompt_text:
        warnings.append("缺少 提示词全集.md：交接包仍可生成，但请补上唯一生效提示词源后再交给 Agent")
    if not shots:
        warnings.append("缺少 shot_list.csv：生成条的参考图清单可能不完整")
    run_mode = state.get("run_mode", "guided")
    if run_mode != "autopilot":
        warnings.append(f"stage_state.json 的 run_mode 仍是 {run_mode}；本包可用于预演，正式全自动前需用户显式授权后设为 autopilot")

    asset_policy = plan.get("asset_policy") or {}
    upload_counts = asset_policy.get("upload_counts") or {}
    cid_map = {uid: cid for cid, uid in C_HEAD_RE.findall(prompt_text)}
    prefix = stable_prefix(project)
    units, unit_warns = build_units(plan, shots, cid_map, prefix,
                                    args.picks_per_unit, args.max_retries, no_first_frame_units)
    warnings += unit_warns
    if not units:
        print("没有可打包的生成条，停止。", file=sys.stderr)
        return 1

    scene_ids = set()
    for row in shots:
        if row.get("场景"):
            scene_ids.add(row["场景"])

    backend = args.backend
    backend_info = BACKENDS[backend]
    libtv_status = args.libtv_status
    requires_fallback = bool(backend == "libtv" and libtv_status == "unavailable")
    status_note = ""
    if requires_fallback:
        status_note = ("> ⚠ **目标平台 libtv 当前不可用**：本包**不可直接执行**。"
                       "请改用 `--backend workbuddy` 或 `--backend external` 重新打包；"
                       "autopilot 通道本身不受影响，不需要回退 guided。")
    elif backend != "libtv" and libtv_status == "unavailable":
        status_note = (f"> 已选用 `{backend}` 后端（libtv 不可用时的降级选择），"
                       "降级原因已写入 `libtv_manifest.json` 的 `platform_status`；autopilot 正常跑通。")
    elif backend != "libtv":
        status_note = f"> 已选用 `{backend}` 后端；不依赖 libtv 连接，autopilot 正常跑通。"

    if backend == "libtv":
        backend_section = f"""## 3.5 执行后端与跑法 · `{backend}`（{backend_info['name']}）

**执行者**：{backend_info['actor']}
**说明**：{backend_info['note']}

1. `create_project` → `upload_ticket` + `upload_complete` 把本包与参考图作为 `documents[].fileRef` 上传。
2. `run_agent(message=本包首段指令, autoGenerate=true, idempotencyKey=<稳定键>, documents=...)` 一次委托整包；**不要拆成 N 条请求**。
3. `get_agent_status(runId)` 轮询、`answer_agent_questions` 只做事实澄清、`resolve_agent_action(精确 actionId, confirmSpend)` 明确批准。
4. `export_readiness → export_video → task_status` 导出成片；`prepare_project_delivery` 回传清单。
5. 超上限 / 报错 / 用户喊停 → `stop_agent_run`，保留全部产物与日志。
6. 也可用 agent-im 会话一条消息托管（见 `agent-autopilot.md` §7），**不把提示词正文抄进消息**。

**平台不可用时**：不要反复重试把任务打散；用 `--backend workbuddy` 或 `--backend external` 重新打包，降级原因写进 manifest。
"""
    elif backend == "workbuddy":
        backend_section = f"""## 3.5 执行后端与跑法 · `{backend}`（{backend_info['name']}）

**执行者**：{backend_info['actor']}
**说明**：{backend_info['note']}

1. 读完本包与 `libtv_manifest.json`，**先向用户确认本次生成次数上限 {len(units) * args.picks_per_unit} 次**；未确认不开始。
2. 按第 2 节 A 段顺序生成全部参考资产（A08 用成品出图提示词纯文字出图；场景反打按生产包标注决定是否生成）→ 2 参考标准首帧；`PHOTO_MASTER_01` 是文字块，不生成图。
3. 按第 4 节清单**逐条**执行 C 段六块提示词：逐字复制、不改写、不翻译，按第 3 节顺序传参考图，每条生成 {args.picks_per_unit} 次挑 1，最多重跑 {args.max_retries} 次。
4. 每条都记录：生成条 ID、种子值、档位、参考编号、挑了哪条、重跑次数；写进 QA 表。
5. 全部完成后按第 5 节拼接、全片统一加一次柔光与统一 LUT、导出成片，再跑 `color_field_audit.py` 验收。
6. 任一环节失败即停、留痕、汇报，不静默重跑或扩大批次；产物标注「WorkBuddy 生成」。

**本后端不依赖 libtv**：不需要 Canvas / agent-im / `confirmSpend` 平台侧动作。
"""
    else:
        backend_section = f"""## 3.5 执行后端与跑法 · `{backend}`（{backend_info['name']}）

**执行者**：{backend_info['actor']}
**说明**：{backend_info['note']}

1. 按第 2 节表格顺序，把每条 A 段提示词粘到你自己的图像平台；提示词**逐字复制，不改写、不翻译**。
2. 生成 `COLOR_CARD_01`（直接复制 A08 **成品色卡出图提示词**，12 HEX 写死、不传参考图）与 `STANDARD_FRAME_01`（只同传 2 参考、不带色卡）；场景反打 `SCENE_REVERSE_0X` 按生产包标注决定是否生成；`PHOTO_MASTER_01` 直接作为文字块备用，不上传。
3. 按第 4 节清单**从上到下逐条**执行 C 段：粘六块提示词 → 按第 3 节顺序传参考图 → 选对应秒数档位 → 每条生成 {args.picks_per_unit} 次挑 1，最多重跑 {args.max_retries} 次。
4. 每条在 QA 表记：生成条 ID、平台、种子值、档位、参考编号、挑片结果、重跑次数。
5. 全部素材齐了按第 5 节时间码拼接、全片统一加一次柔光与统一 LUT、导出成片；把成片与 QA 表回传，由 WorkBuddy 跑 `color_field_audit.py` 验收。
6. 累计生成次数不得超过 **{len(units) * args.picks_per_unit} 次**；超限即停并汇报。

**本后端不依赖 libtv**：交接包即批处理清单，脚本不联网、不代你操作平台。
"""

    ctx = {
        "project": project, "theme": state.get("theme") or plan.get("theme") or project.name,
        "generated_at": datetime.datetime.now().isoformat(timespec="seconds"),
        "platform": args.platform, "run_mode": run_mode,
        "backend": backend, "backend_name": backend_info["name"],
        "backend_actor": backend_info["actor"], "backend_note": backend_info["note"],
        "backend_completion": backend_info["completion"],
        "backend_attribution": backend_info["attribution"],
        "backend_section": backend_section, "status_note": status_note,
        "libtv_status": libtv_status, "requires_fallback": requires_fallback,
        "input_mode": state.get("input_mode") or plan.get("input_mode") or "zero",
        "duration": plan.get("target_duration_seconds", "unknown"),
        "shot_count": plan.get("shot_count", len(shots) or "unknown"),
        "scene_count": plan.get("scene_count") or len(scene_ids) or "unknown",
        "aspect": plan.get("aspect", "16:9"), "resolution": "1080p",
        "image_model": state.get("image_model") or plan.get("image_model") or "按 S1 定稿组合",
        "video_model": state.get("video_model") or plan.get("video_model") or "按 S1 定稿组合",
        "picks": args.picks_per_unit, "max_retries": args.max_retries,
        "unit_count": len(units), "max_total": len(units) * args.picks_per_unit,
        "prefix": prefix, "upload_counts": upload_counts,
        "upload_counts_text": "、".join(f"{k} {v} 张" for k, v in upload_counts.items()) or "见 C00 上传表",
        "missing": missing, "warnings": warnings,
        "a_rows": a_asset_rows(prompt_text),
        "auth_note": ("> ⚠ 当前项目仍是 `guided`：本包为**预演包**，尚未授权自动生成。"
                      "正式交付执行后端前，须由用户显式授权「全自动出成片」，"
                      "再执行 `stage_state.py set --run-mode autopilot --backend <后端>` 并重新打包。"
                      if run_mode != "autopilot" else
                      "> 已获 `autopilot` 授权：交接前仍需用户过目 `libtv_manifest.json` 的生成次数上限，"
                      "并在执行后端侧确认本次媒体生成。"),
    }
    ctx["unit_rows"] = [
        "| `{id}` | `{prompt_id}` | {duration_seconds}s | {timecode} | {first_frame} | {scene} | {chars} | {beat_count} |".format(
            id=u["id"], prompt_id=u["prompt_id"],
            duration_seconds=f"{u['duration_seconds']:g}" if isinstance(u["duration_seconds"], (int, float)) else u["duration_seconds"],
            timecode=u["timecode"], first_frame=u["first_frame"],
            scene="、".join(f"`{x}`" for x in u["scene_references"]) or "—",
            chars="、".join(f"`{x}`" for x in u["character_references"]) or "—",
            beat_count=u["beat_count"])
        for u in units
    ]

    handoff = render_handoff(ctx)
    if "{{" in handoff:
        print("交接包里仍有未替换的槽位，停止写入。", file=sys.stderr)
        return 1
    manifest = build_manifest(ctx, units)
    assets = build_assets_manifest(ctx, units, prompt_text)

    (out_dir / "libtv_handoff.md").write_text(handoff, encoding="utf-8")
    (out_dir / "libtv_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (out_dir / "libtv_assets_manifest.json").write_text(json.dumps(assets, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"交接包已生成：{out_dir}")
    print(f"  libtv_handoff.md / libtv_manifest.json / libtv_assets_manifest.json")
    print(f"  主题 {ctx['theme']} | 通道 {run_mode} | 执行后端 {backend} | 生成条 {len(units)} | 生成上限 {ctx['max_total']} 次 | 参考资产 {len(assets['assets'])} 项")
    print(f"  幂等键前缀 {prefix} | libtv 接法 {args.platform} | 平台状态 {libtv_status}")
    if requires_fallback:
        print("  [阻断] libtv 不可用：请用 --backend workbuddy 或 --backend external 重新打包；autopilot 本身仍可跑通。")
    elif backend != "libtv":
        print(f"  [OK] 已用 {backend} 后端出包，不依赖 libtv 连接；产物归属 {backend_info['attribution']}。")
    if missing:
        print(f"  [警告] 缺失生产包文件 {len(missing)} 个：" + "、".join(missing))
    for w in warnings:
        print(f"  [警告] {w}")
    print("  纯打包完成：未调用任何生成能力、未生成图片或视频、未修改项目原有文件。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
