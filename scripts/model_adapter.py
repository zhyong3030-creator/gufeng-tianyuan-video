#!/usr/bin/env python3
"""Model-aware planner and prompt adapter for a unified color-field AI film.

Reads the capability database in ../assets/model_profiles.json. It adapts
prompt shape AND re-plans the whole shot structure from the video model's
max single-generation duration. Pure Python standard library.

Usage:
  python3 model_adapter.py --list
  python3 model_adapter.py --video-model seedance-2.0 --image-model nano-banana-2 \
      --duration <成片总时长T> --aspect 16:9 --out-dir <project>
  python3 model_adapter.py --video-model veo-3.1 --image-model gpt-image-2 \
      --stage video --duration <成片总时长T> --out-dir <project>
  python3 model_adapter.py --video-model seedance-2.5 --image-model seedream-5 \
      --stage character --body-ratio "8.5 头身" --out-dir <project>

v3.8: 12-color color card (video-only), PHOTO_MASTER_01 text block, six-block video
prompts, and paired ROLE_SHEET_X + FACE_CLOSE_X video references.
v3.6: --input-mode (zero/partial/provided, default zero) emits asset_chain.md,
writes input_mode + asset_policy into generation_plan.json and prepends a mode
banner to adaptation_spec.md / usage_guide.md. The DEFAULT character asset is
one ROLE_SHEET_X 4-panel sheet per character; the full FACE_QUAD_01 pack below
is the optional EXPANSION pack, used only when the user asks for all turnarounds.

The character stage (expansion pack) emits FIRST a FACE_QUAD_01 four-equal-quarter head close-up
sheet (front / left 90 / right 90 / back 180) as the single facial identity
anchor, then a warm-grey-seamless three-point-neutral-light full-body front
costume reference (locked body_ratio, 105mm head / 85mm+ body, low-density
Tiffen Black Pro-Mist, no modern heavy makeup), a front / exact side / back
turnaround, a four-panel board, six single images, a 13-item checklist,
design/costume self-checks, a correspondence matrix and a character-specific
negative list. Color-field, warm rim light and depth-of-field rules apply only
to film frames, never to the character reference pack.

v3.7: all delivered prompt text is Simplified Chinese; only platform flags,
asset IDs, gear model numbers and colour values keep their original spelling.
All capability numbers are a starting point; verify on the platform on the
day of use. Deprecated models are never recommended by this script.
"""
import argparse
import json
import math
import pathlib
import sys

PROFILES_PATH = pathlib.Path(__file__).resolve().parent.parent / "assets" / "model_profiles.json"

SKELETON_ZH = [
    "[1 主体与动作] <人物固定描述串，逐字复制>，<一个可见动作>。",
    "[2 色场] 主色 <主色> 约 65%，进入服装、建筑、自然、织物、道具、地面、空气与环境光，覆盖 3x3 九分区；辅色 <辅色> 约 20% 落在阴影与远景；暖主光 + 冷环境反射；<浅主色载体> 作为大面积低彩度承载物。",
    "[3 构图] <景别>，人物占画面高度 <比例>；<圆形锚点> 位于下三分之一；<10-30%> 失焦 <前景遮挡物>；<带主色的空气面> 留白。",
    "[4 光与质感] 高位斜后侧光（摄影机反方向 120-150 度），发丝与袖缘金色轮廓光，正面弱暖补光；暖象牙肤色；暗部抬高保留纹理；奶油金高光柔化扩散；柔焦、大而软的散景。",
    "[5 镜头] 眼平静态机位，仅极轻微推进；<焦段倾向>；中浅景深；失焦前景—清晰主体—虚化远景三层。",
    "[6 负向/约束] <按模型机制写：纯名词 / 独立字段 / 正向约束句 / 完全不写>",
]
# v3.7 全中文口径：交付提示词一律简体中文，不再维护英文骨架。
SKELETON_EN = SKELETON_ZH

NEGATIVES_ZH = [
    "全局单色滤镜", "塑料高饱和", "纯白溢出高光", "死黑", "冷灰肤色", "正面平光",
    "硬锐数字质感", "广角畸变", "大远景", "远景", "大全景", "纪念碑式建筑", "清晰前景遮挡",
    "对称徽章构图", "纯白或纯黑空区", "自动运镜", "环绕", "甩镜", "变焦冲击",
    "文字", "字幕", "水印", "现代物件", "多余手指", "器物形变", "多人换脸", "闪烁",
]
# v3.7 全中文口径：负向词也只用中文。
# v5.1 二次纠偏：用户明确「不要用大远景和远景」，大远景 / 远景 / 大全景重新写回全局负向词；景别只在全景及更近档位之间拉开。
NEGATIVES_EN = NEGATIVES_ZH


def load_db():
    if not PROFILES_PATH.exists():
        print(f"Missing capability database: {PROFILES_PATH}", file=sys.stderr)
        sys.exit(2)
    return json.loads(PROFILES_PATH.read_text(encoding="utf-8"))


def build_alias_index(models):
    index = {}
    for key, p in models.items():
        index[key.lower()] = key
        for a in p.get("aliases", []):
            index[a.lower()] = key
    return index


def resolve(name, index, models):
    if not name:
        return None
    key = name.strip().lower()
    if key in index:
        return index[key]
    for alias, model in index.items():
        if key in alias or alias in key:
            return model
    return None


def list_models(db):
    print(f"Capability DB v{db['schema_version']} | researched {db['researched_at']}")
    print(f"{'model':<20} {'kind':<7} {'status':<11} {'lang':<5} {'refs':<5} {'min':<5} {'max':<6} label")
    for key, p in db["models"].items():
        dur_min = p.get("min_duration_s", "-")
        dur_max = p.get("max_duration_s", "-")
        print(f"{key:<20} {p['kind']:<7} {p['status']:<11} {p['lang']:<5} "
              f"{p.get('max_refs', 0):<5} {str(dur_min):<5} {str(dur_max):<6} {p['label']}")
    print("\n" + db["disclaimer"])


def pick_unit_seconds(p):
    """Largest allowed duration option <= max_duration_s; fallback to max."""
    maximum = float(p.get("max_duration_s", 8))
    options = sorted(float(x) for x in p.get("duration_options", []) if float(x) <= maximum)
    if options:
        return options[-1]
    return maximum


def build_units(video, duration, shot_count, aspect):
    max_dur = float(video.get("max_duration_s", 8))
    min_dur = float(video.get("min_duration_s", 4))
    options = sorted(float(x) for x in video.get("duration_options", []))
    unit_target = pick_unit_seconds(video)
    per_shot = duration / shot_count

    warnings = []
    if per_shot > max_dur:
        warnings.append(f"每镜 {per_shot:.2f}s 超过单次上限 {max_dur}s：必须拆镜或换模型")
    if video.get("status") == "deprecated":
        warnings.append(f"{video['label']} 状态为 deprecated，不得作为新项目主力")
    if video.get("status") == "verify":
        warnings.append(f"{video['label']} 状态为 verify：先跑 5s 小样确认时长与档位")
    if video.get("front_end_note"):
        warnings.append("前端限制：" + video["front_end_note"])

    # Quantize each generation unit to an allowed duration option.
    def quantize(seconds):
        for opt in options:
            if opt >= seconds - 1e-6:
                return min(opt, max_dur)
        return max(min_dur, min(max_dur, math.ceil(seconds * 2) / 2))

    units = []
    covered = 0.0
    while covered < duration - 1e-6:
        remaining = duration - covered
        raw = min(unit_target, remaining)
        seconds = quantize(raw)
        if seconds < min_dur:
            seconds = min_dur
        seconds = min(seconds, max_dur)
        if remaining < min_dur:
            seconds = min_dur
        units.append({"unit": f"U{len(units) + 1:02d}", "start": round(covered, 2),
                      "seconds": seconds, "end": round(covered + seconds, 2)})
        covered += seconds
        if len(units) > 40:
            warnings.append("生成条超过 40，检查时长与档位设置")
            break

    trim = round(units[-1]["end"] - duration, 2) if units else 0.0
    if trim > 0:
        warnings.append(f"末条生成 {units[-1]['seconds']}s，成片裁掉 {trim}s（模型最短 {min_dur}s）")

    # Assign editorial shots to units by midpoint, and build timecoded beats.
    shot_times = []
    for i in range(shot_count):
        start = i * per_shot
        end = min(duration, (i + 1) * per_shot)
        shot_times.append((f"S{i + 1:02d}", round(start, 2), round(end, 2)))
    for u in units:
        u["beats"] = []
        for sid, s, e in shot_times:
            mid = (s + e) / 2
            if u["start"] - 1e-6 <= mid < u["end"] - 1e-6:
                u["beats"].append({
                    "shot": sid,
                    "film_time": f"{s:.2f}-{e:.2f}s",
                    "unit_time": f"{round(s - u['start'], 2):.2f}-{round(min(e, u['end']) - u['start'], 2):.2f}s",
                    "seconds": round(min(e, u["end"]) - s, 2),
                    "action": "<一个可见动作，切镜显式声明>",
                })
        u["shot_ids"] = [b["shot"] for b in u["beats"]]
        u["beat_style"] = "Shot N labeled" if video.get("prompt_form") == "structured" and "Kling" in video["label"] else "timecoded"
        u["aspect"] = aspect

    return {
        "model": video["label"],
        "model_key": None,
        "max_duration_s": max_dur,
        "min_duration_s": min_dur,
        "duration_options": options,
        "target_unit_seconds": unit_target,
        "target_duration_seconds": duration,
        "shot_count": shot_count,
        "per_shot_seconds": round(per_shot, 2),
        "suggested_shot_seconds": video.get("suggested_shot_s"),
        "generation_unit_count": len(units),
        "total_generated_seconds": round(sum(u["seconds"] for u in units), 2),
        "trim_seconds": trim,
        "units": units,
        "warnings": warnings,
        "planning_note": (
            f"{video['label']} 单次上限 {max_dur}s：{duration:g}s 成片规划为 {len(units)} 个生成条，"
            f"每条约装 {max(1, round(shot_count / max(1, len(units))))} 个 2-4s 成片镜头；"
            "上限不等于建议镜头长度，长条用时间码显式拆镜，剪辑时切回短镜头节奏。"
        ),
    }


def profile_summary(p):
    rows = [
        ("模型", p["label"]),
        ("层级 / 状态", f'{p["kind"]} / {p["status"]}'),
        ("语言 / 形态", f'{p["lang"]} / {p["prompt_form"]}'),
        ("参考上限", str(p.get("max_refs", 0))),
        ("参考写法", p.get("reference_syntax", "-")),
        ("负向词机制", f'{p.get("negative_mode", "inline")} — {p.get("negative_rules", "-")}'),
        ("音频", ("有 → " + p.get("audio_rule", "")) if p.get("audio") else "无（后期补）"),
        ("画幅", ", ".join(p.get("aspect_ratios", []))),
        ("分辨率", ", ".join(p.get("resolutions", []))),
    ]
    if p["kind"] == "video":
        rows.insert(3, ("单次时长", f'{p.get("min_duration_s")}–{p.get("max_duration_s")}s，档位 {p.get("duration_options")}'))
        if p.get("front_end_note"):
            rows.append(("前端限制", p["front_end_note"]))
        rows.append(("规划影响", p.get("planning_impact", "-")))
    else:
        rows.append(("产出角色", p.get("output_role", "-")))
        rows.append(("规划影响", p.get("planning_impact", "-")))
    return rows


def render_adapted_prompt(p, plan, stage, base_text, db):
    lang = p["lang"]
    is_char = stage == "character"
    cs = db.get("character_sheet", {})
    head = [
        f"# 适配后提示词 | {p['label']} | 阶段 {stage}", "",
        f"> 能力数据库 v{db['schema_version']}（{db['researched_at']}）。参数与时长上限以平台当日为准。", "",
        "## 一、本模型能力（决定提示词形态）", "",
        "| 项目 | 结论 |", "|---|---|",
    ]
    head += [f"| {k} | {v} |" for k, v in profile_summary(p)]
    head += ["", "## 二、写法规则（逐条遵守）", ""]
    head += [f"{i + 1}. {r}" for i, r in enumerate(p.get("prompt_rules", []))]
    if is_char:
        lt = cs.get("lighting", {})
        br = cs.get("body_ratio", {})
        bl = cs.get("board_layout", {})
        fq = cs.get("face_quad", {})
        fs = cs.get("face_spec", {})
        da = cs.get("design_aesthetics", {})
        cd = cs.get("costume_design", {})
        co = cs.get("correspondence", {})
        head += ["", "## 三、角色参考包硬规范（**不是六段式色场**）", "",
                 f"**{cs.get('rule', '')}**", "",
                 f"> 规范：{cs.get('spec', '')}；模板：{cs.get('templates', '')}", "",
                 f"本项目锁定头身比：**{plan.get('body_ratio', '未设置')}**", "",
                 "### 输入参考职责", ""]
        head += [f"- `{k}` — {v}" for k, v in cs.get("input_slots", {}).items()]
        head += ["", "### 光照：三点式中性白棚拍还原光", "",
                 "| 灯位 | 规格 |", "|---|---|"]
        head += [f"| {k} | {lt.get(k, '-')} |" for k in ("key", "fill", "rim", "white_balance", "background")]
        head += ["", f"- 禁止：{lt.get('forbidden', '-')}",
                 f"- 视频层必写：{lt.get('video_binding_note', '-')}",
                 f"- 降级：{lt.get('flat_fallback', '-')}", "",
                 "### 人体比例（跨所有视图锁定同一数值）", "",
                 f"- 参数 `{br.get('param', 'body_ratio')}`：{br.get('default', '-')}",
                 f"- 规则：{br.get('rule', '-')}",
                 f"- 姿态：{br.get('posture', '-')}",
                 f"- 禁止：{br.get('forbidden', '-')}", "",
                 "### 面部统一规格（本项目模式：" + str(plan.get('face_spec_mode', 'unified')) + "）", "",
                 "| 项 | 规格 |", "|---|---|",
                 f"| 背景 | {fs.get('background', '-')} |",
                 f"| 镜头（头） | {fs.get('lens_face', '-')} |",
                 f"| 镜头（身） | {fs.get('lens_body', '-')} |",
                 f"| 滤镜 | {fs.get('filter', '-')} |",
                 f"| 妆造 | {fs.get('makeup', '-')} |",
                 f"| 白平衡 | {fs.get('white_balance', '-')} |",
                 f"| 四个「不是」 | {fs.get('nots', '-')} |",
                 f"| 成片边界 | {fs.get('film_boundary', '-')} |", "",
                 f"- 模式切换：`{fs.get('switch', '-')}`；默认 `{fs.get('default_mode', 'unified')}`。", "",
                 "### 面部特写四宫格 `FACE_QUAD_01`（**S3 第一张，先于任何全身图**）", "",
                 f"- **顺序**：{fq.get('order', '-')}",
                 f"- **版式**：{fq.get('layout', '-')}",
                 f"- **备选版式**：{fq.get('fallback_layout', '-')}",
                 f"- **取景**：{fq.get('framing', '-')}",
                 f"- **一致性**：{fq.get('consistency', '-')}",
                 f"- **四张单图**：{'、'.join(fq.get('single_images', []))}",
                 f"- **易错点**：{fq.get('check', '-')}", ""]
        head += [f"- **{k}**：{v}" for k, v in fq.get("cells", {}).items()]
        head += ["", "### 角色设计与服装造型（出图前先过两组自检）", "",
                 f"- 参考原片：{da.get('rule', '-')}",
                 f"- 美感锚点：{da.get('anchors', '-')}",
                 f"- 反同质化：{da.get('anti_sameness', '-')}",
                 f"- 设计自检：{da.get('checklist', '-')}",
                 f"- 服装六维：{' / '.join(cd.get('six_dimensions', []))}",
                 f"- 服装四朝向：{cd.get('four_directions', '-')}",
                 f"- 服装功能性：{cd.get('functional', '-')}",
                 f"- 服装与色场边界：{cd.get('color_boundary', '-')}",
                 f"- 服装自检：{cd.get('checklist', '-')}", "",
                 "### 对应性矩阵（后面每张定妆图都必须指回四宫格）", "",
                 f"- 规则：{co.get('rule', '-')}",
                 f"- 失败修法：{co.get('repair', '-')}", ""]
        head += [f"- **{k}** → {v}" for k, v in co.get("map", {}).items()]
        head += ["", "### 四格定妆板版式", ""]
        head += [f"- **{k}**：{v}" for k, v in bl.items()]
        head += ["", f"### {len(cs.get('hard_rules', []))} 条硬规格", ""]
        head += [f"{i + 1}. {r}" for i, r in enumerate(cs.get("hard_rules", []))]
        head += ["", "### 必产文件（拼版与单图都要有）", ""] + [f"- {x}" for x in cs.get("required_outputs", [])]
        head += ["", "### 视频层绑定（逐条复制进镜头提示词）", "", "```text",
                 cs.get("video_binding", ""), "```", "",
                 f"单图输入模型：{cs.get('single_image_binding', '-')}", "",
                 "> 定妆阶段禁止：主色占比、色卡 / `--sref`、成片主光方位、暖金轮廓光、前景遮挡、留白、中浅景深、柔焦、整屏雾感。"
                 "低密度 Tiffen 黑柔是**正向要求**，不要写进负向清单；禁的是场景光晕与镜头炫光。", ""]
    else:
        head += ["", "## 三、六段式骨架（内容不变，形态按模型）", ""]
        head += SKELETON_ZH  # v3.7：语言口径不随模型切换，一律中文
    head += ["", "## 四、参考图绑定与约束", "", p.get("reference_syntax", "-"), ""]
    if is_char:
        head += ["定妆阶段：先传 `FACE_REF_01` / `OUTFIT_REF_01`（有则传），再传 `ROLE_REF_01` 出派生图；**不传色卡、不传场景空镜**；角色外观写进正文或用固定描述串。", ""]
    if p.get("audio") and not is_char:
        head += ["音频约束：" + p.get("audio_rule", ""), ""]
    head += ["负向/约束机制：" + p.get("negative_rules", "-"), ""]
    if p.get("params") and not is_char:
        head += ["参数行（示意）：`" + " ".join(str(x) for x in p["params"]).replace("<unit_seconds>", str(plan["target_unit_seconds"])) + "`", ""]
    if is_char:
        head += ["## 五、完整实例（照这个形态写；全文另存 `character_prompts.md` 可直接复制）", "",
                 "### 0. `FACE_QUAD_01` 面部特写四宫格（**第一张，四等分：正 / 左 90° / 右 90° / 背 180°，全为头部特写**）", "",
                 "```text", p.get("face_quad_example_prompt", "-"), "```", "",
                 "### A. `ROLE_REF_01` 定妆基准图（暖灰 / 三点式中性光 / 105mm+85mm+ / 低密度黑柔 / 全身正面）", "",
                 "```text", p.get("character_example_prompt", "-"), "```", "",
                 "### B. `ROLE_TRIVIEW_01` 朝向三视图（正面 0° / 正侧 90° / 背面 180°）", "",
                 "```text", p.get("triview_example_prompt", "-"), "```", "",
                 "### C. `ROLE_BOARD_01` 四格定妆板（上 1/3 头部特写 + 下 2/3 放大服装 / 背面全身）", "",
                 "```text", p.get("board_example_prompt", "-"), "```", "",
                 "### D. `FACE_CLOSE_01..04` 四张头部特写单图（对应四宫格四格）", "",
                 "```text", p.get("face_close_example_prompt", "-"), "```", "",
                 "### E. `ROLE_OUTFIT_DETAIL_01` 放大服装单图（只管材质）", "",
                 "```text", p.get("outfit_detail_example_prompt", "-"), "```", "",
                 "### F. 定妆负向词（有独立负向字段时粘贴；无负向字段改正向约束句）", "",
                 "```text", cs.get("negative_for_character", ""), "```", "",
                 f"> 左下裁头格失败时的降级路径：{cs.get('board_layout', {}).get('downgrade', '-')}", ""]
    else:
        head += ["## 五、完整实例（照这个形态写）", "", "```text", p.get("example_prompt", "-"), "```", ""]
        if p["kind"] == "image":
            head += ["> 该实例是**标准首帧 / 场景空镜（成片画面）**，不是定妆图；定妆请用 `--stage character`。", ""]
    if base_text:
        head += ["## 六、你的原提示词（已按本模型插入专属段）", "", base_text.strip(), ""]
    head += ["## 七、现在怎么用（按顺序做）", ""]
    head += [f"{i + 1}. {s}" for i, s in enumerate(p.get("usage_steps", []))]
    head += ["", "## 八、失败先这样修", ""]
    head += [f"- {f}" for f in p.get("failure_fixes", [])]
    head += ["", "> 完整实例库：references/prompt-examples-image.md / prompt-examples-video.md；角色规范：references/character-sheet-spec.md；操作总纲：references/usage-guide.md。", ""]
    return "\n".join(head)


def render_character_prompts(p, db, plan):
    """Standalone copy-paste block for all character reference prompts."""
    cs = db["character_sheet"]
    lt, br = cs["lighting"], cs["body_ratio"]
    fs, fq = cs["face_spec"], cs["face_quad"]
    items = [
        ("FACE_QUAD_01", "面部特写四宫格（**S3 第一张**：四等分 正 0° / 左 90° / 右 90° / 背 180°，全为头部特写）",
         p.get("face_quad_example_prompt", "-")),
        ("ROLE_REF_01", "定妆基准图（暖灰 / 三点式中性光 / 105mm 头 + 85mm+ 身 / 低密度黑柔 / 无现代浓妆 / 全身正面）",
         p.get("character_example_prompt", "-")),
        ("ROLE_TRIVIEW_01", "朝向三视图（正面 0° / 正侧 90° / 背面 180°，头部结构对应四宫格）",
         p.get("triview_example_prompt", "-")),
        ("ROLE_BOARD_01", "四格定妆板（上 1/3 两张头部特写；下 2/3 左放大服装 + 右背面全身）",
         p.get("board_example_prompt", "-")),
        ("FACE_CLOSE_01..04", "四张头部特写单图（分别对应四宫格四格）",
         p.get("face_close_example_prompt", "-")),
        ("ROLE_OUTFIT_DETAIL_01", "放大服装单图（只管材质，不判断身份与比例）",
         p.get("outfit_detail_example_prompt", "-")),
    ]
    lines = ["# S3 角色参考包 · 可复制提示词", "",
             f"图像模型：**{p['label']}** | 头身比：**{plan.get('body_ratio', '未设置')}** | "
             f"光照模式：**{lt.get('mode', 'three_point_neutral')}** | "
             f"面部规格模式：**{plan.get('face_spec_mode', 'unified')}**", "",
             f"> {cs['rule']}", "",
             f"> 光位：{lt.get('key')} / {lt.get('fill')} / {lt.get('rim')}；{lt.get('white_balance')}。",
             f"> 背景：{lt.get('background')}。滤镜：{lt.get('filter')}。妆造：{lt.get('makeup')}。",
             f"> 比例：{br.get('rule')}；禁止 {br.get('forbidden')}。", "",
             f"> **生成顺序不能颠倒**：{fq.get('order')}；后面每张图都要写明引用 `@FACE_QUAD_01` 的哪一格。",
             f"> 出图前先过 `{cs['design_aesthetics']['spec']}` 设计自检 6 问与 `{cs['costume_design']['spec']}` 服装自检 6 问。", "",
             "所有实例里的 `[body_ratio]` 占位请全部替换成本项目锁定的**同一个数值**，一个字都不要改；"
             "`[角色固定描述串]`、`[服装造型设计]`、`[四朝向服装结构]` 同样逐字复制。", ""]
    for file_id, desc, text in items:
        lines += ["---", "", f"## `{file_id}` — {desc}", "", "```text", text, "```", ""]
    lines += ["---", "", "## 定妆负向词（按模型机制处理）", "", "```text",
              cs["negative_for_character"], "```", "",
              f"> {cs['negative_note']}", "",
              "## 角色设计 / 服装造型 / 对应性（出图前必读）", "",
              f"- 参考原片：{cs['design_aesthetics']['rule']}",
              f"- 美感锚点：{cs['design_aesthetics']['anchors']}",
              f"- 设计自检：{cs['design_aesthetics']['checklist']}",
              f"- 服装六维：{' / '.join(cs['costume_design']['six_dimensions'])}",
              f"- 服装四朝向：{cs['costume_design']['four_directions']}",
              f"- 服装自检：{cs['costume_design']['checklist']}",
              f"- 对应性：{cs['correspondence']['rule']}", "",
              "```text", cs["design_aesthetics"]["prompt_zh"], "```", "",
              "```text", cs["costume_design"]["prompt_zh"], "```", "",
              "## 失败与降级", "",
              f"- 裁头放大格：{cs['board_layout']['downgrade']}",
              f"- 光照/滤镜继承：{lt.get('flat_fallback')}",
              f"- 四宫格左右两格出成同一张：{cs['face_quad']['check']}",
              f"- 对应性失败：{cs['correspondence']['repair']}", "",
              f"> 规范：{cs['spec']}；中文模板：{cs['templates']}；"
              f"设计：{cs['design_aesthetics']['spec']}；服装：{cs['costume_design']['spec']}。", ""]
    return "\n".join(lines)


def render_character_checklist(db, image, plan=None):
    cs = db["character_sheet"]
    lt, br, bl = cs["lighting"], cs["body_ratio"], cs["board_layout"]
    fq, fs = cs["face_quad"], cs["face_spec"]
    da, cd, co = cs["design_aesthetics"], cs["costume_design"], cs["correspondence"]
    mode = plan.get("face_spec_mode", "unified") if plan else "unified"
    lines = ["# 角色参考包验收清单（S3 必过）", "",
             f"图像模型：**{image['label'] if image else '未指定'}** | 头身比：**{plan.get('body_ratio', '未设置') if plan else '未设置'}** | "
             f"面部规格模式：**{mode}**", "",
             f"> **{cs['rule']}**", "",
             f"理由：{cs['reason']}", "",
             "## 一、开工前先定死的五件事", "",
             f"1. [ ] 头身比 `body_ratio`：{br['default']}；写进 theme_brief.md 并逐字复制到所有提示词",
             f"2. [ ] 光照/滤镜模式：默认 `{lt['mode']}`；触发降级条件时整套切平光 + 无滤镜，不能只改一张",
             "3. [ ] 输入参考：确认 `FACE_REF_01` / `OUTFIT_REF_01` 是否上传，缺项记为假设",
             f"4. [ ] 面部规格模式：`{fs['default_mode']}`（可整套切 `layered`）；黑柔档位 {fs['filter']}",
             "5. [ ] 角色设计差异化清单 ≥3 条 + 服装六维表 + 四朝向服装结构清单，在 S0 定稿", "",
             "## 二、必产文件（拼版与单图都要有；`FACE_QUAD_01` 必须最先出）", ""]
    for item in cs["required_outputs"]:
        file_id, sep, desc = item.partition("：")
        lines.append(f"- [ ] `{file_id}` — {desc}" if sep else f"- [ ] {item}")
    lines += ["", f"## 三、{len(cs['hard_rules'])} 条硬规格", ""]
    lines += [f"{i + 1}. [ ] {r}" for i, r in enumerate(cs["hard_rules"])]
    lines += ["", f"## 四、{len(cs['checklist'])} 项验收（逐项打勾，不通过先重出参考图）", ""]
    lines += [f"{i + 1}. [ ] {c}" for i, c in enumerate(cs["checklist"])]
    lines += ["", "## 五、面部四宫格与面部统一规格", "",
              f"- **顺序**：{fq['order']}",
              f"- **版式**：{fq['layout']}",
              f"- **备选**：{fq['fallback_layout']}",
              f"- **取景**：{fq['framing']}",
              f"- **一致性**：{fq['consistency']}",
              f"- **易错点**：{fq['check']}", ""]
    lines += [f"- [ ] {k}：{v}" for k, v in fq["cells"].items()]
    lines += ["", "| 面部规格 | 值 |", "|---|---|"]
    lines += [f"| {k} | {v} |" for k, v in fs.items() if isinstance(v, str)]
    lines += ["", "## 六、对应性矩阵（后面每张图都要指回四宫格）", "",
              f"- 规则：{co['rule']}", f"- 修法：{co['repair']}", ""]
    lines += [f"- [ ] **{k}** → {v}" for k, v in co["map"].items()]
    lines += ["", "## 七、角色设计 / 服装造型自检（出图前过，另记 QA 表）", "",
              f"- 参考原片：{da['rule']}",
              f"- 美感锚点：{da['anchors']}",
              f"- 反同质化：{da['anti_sameness']}",
              f"- [ ] 设计自检 6 问：{da['checklist']}",
              f"- 服装六维：{' / '.join(cd['six_dimensions'])}",
              f"- 服装四朝向：{cd['four_directions']}",
              f"- [ ] 服装自检 6 问：{cd['checklist']}", "",
              "可粘贴的 `[角色设计]` / `[服装造型设计]` / `[四朝向服装结构]` 中英完整段见 `character_prompts.md` 末尾，"
              "或 `character-design-aesthetics.md` §5 / `costume-design.md` §5。", "",
              "## 八、四格板版式与降级", ""]
    lines += [f"- **{k}**：{v}" for k, v in bl.items()]
    lines += ["", "## 九、单图输入模型", "", cs["single_images"]["reason"],
              "必产：" + "、".join(cs["single_images"]["files"]), "",
              "```text", cs["single_image_binding"], "```", "",
              "## 十、定妆负向词（按所选图像模型机制处理）", "", "```text",
              cs["negative_for_character"], "```", "",
              f"> {cs['negative_note']}", "",
              "## 十一、上传顺序与视频层绑定", "",
              "上传顺序：`" + "` → `".join(cs["upload_order"]) + "`", "",
              "```text", cs["video_binding"], "```", "",
              "## 十二、与成片检查的边界", "", cs["note"], "",
              f"> 规范：{cs['spec']}；可复制模板：{cs['templates']}；"
              f"设计：{da['spec']}；服装：{cd['spec']}。", ""]
    return "\n".join(lines)


def render_spec(video, image, plan, aspect, db):
    lines = [f"# 适配规格与整体规划 | v{db['schema_version']}", "",
             f"- 视频模型：**{video['label']}**（单次上限 {video.get('max_duration_s')}s）",
             f"- 图像模型：**{image['label'] if image else '未指定'}**",
             f"- 成片：{plan['target_duration_seconds']:g}s / {aspect} / {plan['shot_count']} 镜 / 每镜 {plan['per_shot_seconds']}s", "",
             "## 一、视频模型能力", "", "| 项目 | 结论 |", "|---|---|"]
    lines += [f"| {k} | {v} |" for k, v in profile_summary(video)]
    if image:
        lines += ["", "## 二、图像模型能力", "", "| 项目 | 结论 |", "|---|---|"]
        lines += [f"| {k} | {v} |" for k, v in profile_summary(image)]
    lines += ["", "## 三、时长约束如何改变整体规划", "", plan["planning_note"], "",
              "| 生成条 | 成片区间 | 生成时长 | 装入镜头 | 时间码要求 |", "|---|---|---|---|---|"]
    for u in plan["units"]:
        lines.append(f"| {u['unit']} | {u['start']}–{u['end']}s | {u['seconds']}s | "
                     f"{', '.join(u['shot_ids']) or '—'} | 每 {plan['per_shot_seconds']}s 一个 beat，每 beat 一个动作，切镜显式 |")
    if plan["warnings"]:
        lines += ["", "## 四、WARN（必须先处理）", ""] + [f"- {w}" for w in plan["warnings"]]
    lines += ["", "## 五、改写指令", ""]
    lines += [f"{i + 1}. {r}" for i, r in enumerate(video.get("prompt_rules", []))]
    lines += ["", "## 六、产出结果调整", "",
              f"- 分镜表新增「生成条 ID」列，共 {plan['generation_unit_count']} 条；镜数 {plan['shot_count']}，每镜 {plan['per_shot_seconds']}s。",
              f"- 逐镜提示词一律简体中文（v3.7 全中文口径），按 {video['label']} 的负向机制（{video['negative_mode']}）改写；仅平台参数、资产 ID、器材型号与色值保留原文。",
              "- 图像层**最先出 FACE_QUAD_01 面部特写四宫格（四等分：正/左90°/右90°/背180°，全为头部特写）作为唯一面部身份锚**，"
              "再按所选图像模型产出暖灰影棚三点式中性光 + 105mm/85mm+ + 低密度黑柔 + 无现代浓妆的全身定妆基准、正/侧/背三视图、"
              "四格定妆板与六张单图（不带色场与成片光影）/ 空镜 / 色卡 / 标准首帧；"
              "后面每张图都要按对应性矩阵指回四宫格，并按角色设计/服装造型自检；附使用步骤与 13 项验收清单。",
              "- 额外交付：adapted_prompt.md、usage_guide.md、generation_plan.json、按需的 negative_prompt.txt / generation_params.json。",
              "", "## 七、注意", "", f"- {db['disclaimer']}",
              "- 上限不等于建议镜头长度；成片镜头按用户给定区间（建议 2-4 秒，可改），长条只用来减少跨生成跳色。", "",
              "## 八、v4.3 硬口径（优先级高于上文旧版示例）", "",
              "0. **交付方式（v5.0 七大步小白引导）**：对用户只讲 0 准备 / 1 视频总规划 / 2 视觉美学基调 / 3 视频分镜设计及脚本 / 4 人物场景资产设计 / 5 视频生成设计 / 6 自查；每小步弹 A / B / C 选择框，每大步给「本地一份 md + 对话框直接给提示词与用法 + 每条提示词各一个独立一键复制框」三件套；只给生成类提示词，规划 / 分镜 / 自查步不硬造；旧文档先归档再重建。**本脚本仍是内部引擎，交付文件里不出现内部编号；硬口径与提示词一字不动。** **v5.1 人物层级**：主角是唯一被表现、唯一有身份资产的人物，后景焦外可有 1–3 个不具名背景人影，不占参考位；**全片禁用大远景 / 远景 / 大全景**，景别只在全景及更近档位之间拉开。", ""
              "1. **色卡（v4.2 两步走、两处使用）**：先用「12 色归纳 meta 指令」对参考素材做实际归纳 + 分组检查，再把 12 个 HEX 写死成**成品出图提示词**纯文字出图、不传参考图；那段归纳中文不是出图提示词。色卡**必须先于 A01 完成**，先给 `A01–A0N` 场景基调图与可选反打同传、**只取色彩方案**（不取色块版式与标注文字），再到 C 段【参考绑定】锁色；`A00` 母版 / 标准首帧 / 人物资产不挂色卡，全阶段不写 `--sref`。",
              "2. **摄影母版（v4.3 一段式）**：`PHOTO_MASTER_01` 中文文字块，为一段连续专业摄影描述、只写跨镜头统一项、**不含具体焦段与光圈**（焦段 / T 光圈下放到【画面描述】逐镜块）；不生成图、不上传，C 段逐字复用。",
              "2b. **场景图模型与画质段（v4.2）**：`A01–A0N` 与可选反打推荐 `gpt-image-2.5` 类指令式图像模型，通用正文含「画面干净通透，真实的景深与空气透视，焦内细腻，焦外柔和虚化，光影纯净统一，色彩平滑，明暗过渡稳定，严禁噪点，杂乱纹理，斑点，过度锐化，色彩混乱，塑料感。」且逐字一致；该段只进 A 段图像提示词，C 段【禁止项】仍写正向句；末尾只写「画幅 16:9。」。",
              "3. **视频提示词（v4.3 格式）**：六块结构【视频基本参数】【参考绑定】【摄影母版】【禁止项】【画面描述】【收束与音频】；【画面描述】= 全局设定段（统一场景 / 占比 / 光位 / 动作克制 / 切镜规则，每条只写一次）+【镜头N / 时间码 / 镜头名】逐镜块，每块写三层空间、景别构图、机位高度 + 单一焦段 + T 光圈、占画面比、动作、运镜、焦点、环境动态、切点匹配；人物参考只有 `ROLE_SHEET_X` + `FACE_CLOSE_X` 两类成对；标准首帧 2 参考、不带色卡。",
              "3b. **跨块去重（v4.3）**：器材 / 帧率 / 质感 / 肤色原则 / 滤镜只在【摄影母版】；统一场景 / 占比 / 光位 / 动作 / 切镜只在全局段；人物身份与不继承声明只在【参考绑定】；正向禁句只在【禁止项】；焦段 / 光圈 / 机位 / 焦点 / 切点只在逐镜块；【收束与音频】不复述人物一致性。",
              "3c. **跨场景「场景参照 @」（v5.3）**：一条生成条含 ≥2 处场景时，【画面描述】每个逐镜块正文开头逐字写 `场景参照 @SCENE_MOOD_0X；` 再接三层空间句，一镜一次、只 @ 本镜那一处；只写进逐镜块，【参考绑定】不重复绑定说明；句式锁定、单场景条不强制；不是新增上传资产。见 references/prompt-examples-video.md §8.7。",
              "3d. **提示词纯净（v5.4）**：C 段代码块只写直接告诉 AI 的内容（画面 / 光影 / 动作 / 运镜 / 声音 / 参考图怎么用）；【视频基本参数】只写视频时长 / 视频比例 / 视频类型 / 视频概述四类；模型与平台名、档位、生成条编号、成片时间码、分辨率与帧率等平台表单项、上传张数、挑片次数、记录种子 / 档位 / 参考编号、留给下一条或剪辑台的衔接、跨步骤说明与按需补图一律移到框外说明层，信息不丢。见 references/prompt-examples-video.md §8.8。",
              "3e. **手持基底运镜与视线（v5.8）**：每个逐镜块以幅度清晰可辨的手持为基底（vlog 实拍感），其上只叠一种轻微推 / 拉 / 摇 / 移或轻微变焦；不剧烈抖动 / 甩镜 / 变焦冲击 / 急速推拉，允许短暂自然看向镜头。见 references/prompt-examples-video.md §8.10。",
              "4. **运行通道（v3.9）**：默认 `guided` 逐步引导，每阶段一停、S6 逐批确认；仅用户显式授权「交给 libtv 全自动」才设 `autopilot`，连续产出 S0–S5 并自动门禁留痕，S6/S7 由 `build_handoff.py` 打包后整包委托 libtv Agent 跑到成片。两条通道的色场规则与提示词完全相同，见 references/agent-autopilot.md。", ""]
    return "\n".join(lines)


def render_usage(video, image, plan, db):
    cs = db["character_sheet"]
    lines = ["# 本项目使用指引（照顺序做）", "",
             f"视频：{video['label']} | 图像：{image['label'] if image else '未指定'} | "
             f"{plan['target_duration_seconds']:g}s / {plan['shot_count']} 镜 / {plan['generation_unit_count']} 个生成条", "",
             "> **v4.3 当前默认口径（覆盖下文 §1–13 扩展包旧例）**：A08 是 12 个 HEX 写死的成品出图提示词（归纳 meta 指令只作方法），必须先于 A01 完成；色卡第一处在 A 段场景图取色彩方案、第二处在 C 段【参考绑定】；",
             "> A01–A0N 场景提示词为「一条通用正文（含色彩参考限定句 + 固定画质段）+ N 条场景句」，用 `gpt-image-2.5` 类指令式模型出图，占比等验收口径不进代码块；`SCENE_REVERSE_0X` 场景反打**可选**；",
             "> 场景基调图 / 可选反打同传 `@COLOR_CARD_01` 只取 12 色色值、主辅结构与五级明度；A00 母版 / 标准首帧 / 人物资产不挂色卡，全阶段不写 `--sref`；摄影母版 `PHOTO_MASTER_01` 是 v4.3 一段式文字块、不含具体焦段、不上传；",
             "> 视频提示词固定六块结构；人物视频参考只有 `ROLE_SHEET_X` + `FACE_CLOSE_X` 两类成对；标准首帧 2 参考、不带色卡。",
             "> 【摄影母版】= 一段连续专业摄影描述、只写跨镜头统一项、不含具体 mm 焦段；【画面描述】= 全局设定段 +【镜头N / 时间码 / 镜头名】逐镜块，焦段与 T 光圈只在逐镜块写一次，各块之间不复述。",
              "> **v5.3 跨场景「场景参照 @」**：一条生成条含 ≥2 处场景时，【画面描述】每个逐镜块正文开头逐字写 `场景参照 @SCENE_MOOD_0X；`，一镜一次、只 @ 本镜那一处；【参考绑定】不重复绑定说明。",
               "> **v5.4 提示词纯净**：代码块只写直接告诉 AI 的内容，【视频基本参数】只写视频时长 / 视频比例 / 视频类型 / 视频概述；平台 / 模型 / 档位 / 编号 / 成片时间码 / 挑片 / 记录种子 / 剪辑台衔接全部在说明层，不进提示词。", "",
             "## 第一步：图像层做参考图包（**先面部四宫格 → 再全身定妆 → 最后才色场光影**）", "",
             f"> **{cs['rule']}** 规范见 `{cs['spec']}`，模板见 `{cs['templates']}`。", "",
             f"> 本项目头身比：**{plan.get('body_ratio', '未设置')}**；光照模式：`{cs['lighting']['mode']}`（可整套降级平光 + 无滤镜）；"
             f"面部规格模式：`{plan.get('face_spec_mode', 'unified')}`。", "",
             "> **出图前**：按 `" + cs['design_aesthetics']['spec'] + "` 过角色设计自检 6 问，按 `"
             + cs['costume_design']['spec'] + "` 过服装造型自检 6 问，定稿 `[角色固定描述串]`、`[服装造型设计]`、`[四朝向服装结构]`。", "",
             "> **第一张图只能是 `FACE_QUAD_01`**：" + cs['face_quad']['order'] + "；出 4 张挑 1 锁定后，"
             "后面的 `ROLE_REF_01` / 三视图 / 四格板 / 六张单图都要写明引用它的哪一格。", ""]
    if image:
        lines += [f"{i + 1}. {s}" for i, s in enumerate(image.get("usage_steps", []))]
    lines += ["", "必产文件：", ""]
    for item in cs["required_outputs"]:
        file_id, sep, desc = item.partition("：")
        lines.append(f"- `{file_id}` — {desc}" if sep else f"- `{item}`")
    lines += ["", f"定妆包 {len(cs['checklist'])} 项验收见 `character_sheet_checklist.md`；"
              "**不要用主色占比、暖金轮廓光或柔焦去否定一张合格的定妆图**；"
              "低密度 Tiffen 黑柔是正向要求，不要写进负向清单，禁的是场景光晕与整屏雾感。",
              "四宫格与后面每张图的对应性：" + cs['correspondence']['rule'],
              "单图输入模型：" + cs["single_image_binding"],
              "", "视频层上传顺序：`" + "` → `".join(cs["upload_order"]) + "`", "",
              "```text", cs["video_binding"], "```", "",
              "## 第二步：视频层按生成条逐条做", ""]
    lines += [f"{i + 1}. {s}" for i, s in enumerate(video.get("usage_steps", []))]
    lines += ["", "## 第三步：本项目的生成条清单", "",
              "| 生成条 | 生成时长 | 覆盖镜头 | 每条要写的时间码 |", "|---|---|---|---|"]
    for u in plan["units"]:
        beats = "；".join(f"{b['unit_time']} {b['shot']}" for b in u["beats"])
        lines.append(f"| {u['unit']} | {u['seconds']}s | {', '.join(u['shot_ids']) or '—'} | {beats or '—'} |")
    lines += ["", "## 第四步：剪辑与验收", "",
              "1. 按分镜表把每条生成条切回用户给定区间的短镜头（建议 2-4 秒，可改）；长条不是长镜头。",
              "2. 全片只套一个 LUT：抬黑、压高光到奶油金、统一阴影色偏；不逐镜调色。",
              "3. 补环境音与一段克制配乐，不加对白与字幕朗读。",
              "4. 运行 `python3 scripts/color_field_audit.py <成片.mp4> --start 0 --end <时长> --out audit_report.json --csv audit_frames.csv`。",
              "5. 不达标按「标准首帧 → 提示词 → 统一调色 → 模型」顺序修。", "",
              "## 记录表（每批都填）", "",
              "| 生成条 | 模型/档位 | 分辨率 | seed | 参考编号 | 挑片理由 |", "|---|---|---|---|---|---|",
              "| U01 |  |  |  |  |  |", "",
              "> 完整操作总纲见 references/usage-guide.md；每批最多 5 镜，回传确认后才放行下一批。", "",
              "## 第五步：v4.3 动作清单（S3 → S5 必做）", "",
              "| # | 动作 | 不做什么 |", "|---|---|---|",
              "| 1 | `A01–A0N` 用「一条通用正文 + N 条场景句组件表」出齐场景基调图，由 `gpt-image-2.5` 出图、正文含固定画质段、同传色卡取色彩方案 | 不逐场景复写、不写 `--sref`、不传人物图 |",
              "| 2 | 按归纳 meta 指令分析参考素材并并排做分组检查：明显分两组就提醒重新分组 | 不强行合并、不把 meta 指令当出图提示词 |",
              "| 3 | 把 12 个 HEX 写死成 **A08 成品出图提示词**纯文字出 `COLOR_CARD_01`，**必须先于 A01 完成** | 不传参考图、不写占比、不加渐变与相近色 |",
              "| 4 | **〔可选〕统一场景反打**：由用户选择用不用；不用时删 C 段 `@SCENE_REVERSE_0X` 行、首帧第 2 张参考换 `@SCENE_MOOD_01` | 不默认塞进上传序列 |",
              "| 4b | `STANDARD_FRAME_01` 只同传 2 参考 | 不带色卡 |",
              "| 5 | 把 S0「光影特点 / 摄影设定」固化成 `PHOTO_MASTER_01` **一段连续专业摄影描述**文字块 | 不生成图片、不上传、不写具体 mm 焦段与 T 光圈 |",
              "| 6 | C 段每条按六块结构写，【摄影母版】逐字复用 A10；【画面描述】= 全局设定段 + 逐镜块 | 【禁止项】不写否定句；焦段 / 光圈只在逐镜块写一次；不跨块复述 |",
              "| 7 | 上传：首帧 → 色卡 →〔可选〕场景反打 → 人物两类成对 | 不传过程图与摄影母版；跳过反打时张数相应减少 |", "",
              "## 第六步：想全自动出成片（可选，v4.0）", "",
              "默认不需要这一步——本指引就是给用户逐步操作用的。只有你明确说「全自动 / 不用问我 / 直接出成片」时切 autopilot；不必点名平台。", "",
              "| # | 动作 | 不做什么 |", "|---|---|---|",
              "| 1 | `stage_state.py set --run-mode autopilot --backend <libtv\\|workbuddy\\|external>` | 不靠沉默或「全部做完」推断授权 |",
              "| 2 | `python3 scripts/build_handoff.py --project <目录> --backend <后端>` 出交接包 | 不生成图片、不发起任何生成任务 |",
              "| 3 | 过目 `libtv_manifest.json` 的生成次数上限并明确授权本次生成 | 不静默扩大批次 |",
              "| 4 | 整包交给选定后端，轮询 / 逐条执行并回读素材与成片 | 不以派发回执当完成 |",
              "| 5 | libtv 未连接时换 `--backend workbuddy` 或 `--backend external` 重新打包 | 不误判 autopilot 不可用、不默认回退 guided |",
              "| 6 | 跑 `color_field_audit.py` 验收；后端执行失败才回退 `guided` 从 S5 继续 | 不删任何文件 |", "",
              "交接包首段会写死「提示词逐字执行、不得重写 / 扩写 / 翻译」「风格固定为中式古装田园暖调统一色场」，色卡边界、摄影母版与人物两类参考在自动模式下一条都不放宽。换后端只换谁按包执行，生产包内容不变。完整协议见 references/agent-autopilot.md。", ""]
    return "\n".join(lines)


INPUT_MODE_ALIASES = {
    "m0": "zero", "m1": "partial", "m2": "provided",
    "零素材": "zero", "部分素材": "partial", "已有资产": "provided",
}
INPUT_MODE_TITLE = {
    "zero": "M0 零素材（默认）：用户没有任何人物参考图，前两格全部从零生成",
    "partial": "M1 部分素材：已有半套裁切、缺的那半从零生成",
    "provided": "M2 已有资产：前两格从用户图裁切、不生成，只出最终拼板",
}


def normalize_input_mode(value):
    """Resolve aliases; the default is zero (most users have no character images)."""
    if not value:
        return "zero"
    key = str(value).strip().lower()
    key = INPUT_MODE_ALIASES.get(key, key)
    if key not in INPUT_MODE_TITLE:
        raise ValueError("input_mode must be zero/partial/provided (or M0/M1/M2)")
    return key


def input_mode_banner(mode):
    """Short header prepended to spec/usage so downstream files never assume assets exist."""
    return "\n".join([
        f"> **输入模式 `input_mode={mode}`**：{INPUT_MODE_TITLE[mode]}。",
        "> 输入模式只决定传哪张参考图（M1/M2 用已有角色图、M0 用 ROLE_STILL_X）；**最终人物资产恒为每人 1 张 `ROLE_SHEET_X` 上下分区定妆板（v5.2 逐字模板）**，",
        "> 它是唯一最终人物资产；v3.8 视频层另有两类成对参考 `ROLE_SHEET_X` + `FACE_CLOSE_X`，`FACE_CLOSE_X` 是唯一允许进视频的过程件；",
        "> A08 是 12 个 HEX 写死的成品出图提示词（归纳 meta 指令只作方法），在 A 段场景图（取色彩方案）与 C 段视频【参考绑定】两处使用；A01–A0N 为通用正文 + 场景句，场景反打可选；摄影母版是文字块不上传，视频提示词固定六块结构。",
        "> 其余过程资产一张不上传；三条铁律与色场方案不变。详见 `references/input-modes.md` 与本目录 `asset_chain.md`。",
        "",
        "---",
        "",
    ])


def render_asset_chain(mode, db):
    """Emit the per-mode asset chain, model relay and upload whitelist."""
    rules = db["planning_rules"]
    chain = {
        "zero": [
            ("1", "ROLE_CHARTER_X（12 项文字设定，S0 定稿）", "— 文字锚", "不生成", "❌"),
            ("2", "参考素材按归纳 meta 指令分析 → COLOR_CARD_01（先于 A01）", "成品出图提示词纯文字出图", "1 张", "A 段取色 + C 段上传"),
            ("3", "FACE_CLOSE_X 面部特写", "出人物（Seedream 类）", "出 4 挑 1", "❌"),
            ("4", "OUTFIT_X 服装展示图", "出人物（Seedream 类）", "出 2–4 挑 1", "❌"),
            ("5", "ROLE_STILL_X 定妆照（建议必出）", "出人物（Seedream 类）", "出 4 挑 1", "❌"),
            ("6", "**ROLE_SHEET_X 上下分区定妆板**", "**锁一致（Nano Banana 类）**", "出 2–4 挑 1", "✅ **最终资产**"),
            ("7", "FABRIC_DETAIL_X 服装材质", "锁一致", "按需 1 张", "⚠️ 画错才补"),
            ("8", "SCENE_REVERSE_0X + STANDARD_FRAME_01", "锁一致", "—", "✅ 2 参考（不带色卡）"),
        ],
        "partial": [
            ("1", "ROLE_CHARTER_X（12 项文字设定，S0 定稿）", "— 文字锚", "不生成", "❌"),
            ("2", "已有半套：裁切 FACE_CLOSE_X 或 OUTFIT_X", "用户素材", "裁，不生成", "❌"),
            ("3", "缺的那半：CHARACTER_MOOD_X + 从零生成", "定基调 + 出人物", "1–2 张", "❌"),
            ("4", "ROLE_STILL_X 定妆照（建议）", "出人物", "出 4 挑 1", "❌"),
            ("5", "**ROLE_SHEET_X 上下分区定妆板**", "**锁一致**", "出 2–4 挑 1", "✅ **最终资产**"),
            ("6", "SCENE_REVERSE_0X + STANDARD_FRAME_01", "锁一致", "—", "✅ 2 参考（不带色卡）"),
        ],
        "provided": [
            ("1", "FACE_CLOSE_X / OUTFIT_X 从用户已有图裁切", "用户素材", "裁，不生成", "❌"),
            ("2", "ROLE_STILL_X 定妆照（可选 / 复用已有）", "出人物", "0–1 张", "❌"),
            ("3", "**ROLE_SHEET_X 上下分区定妆板**", "**锁一致（Nano Banana 类）**", "出 2–4 挑 1", "✅ **最终资产**"),
            ("4", "FABRIC_DETAIL_X（按需）+ 场景版 + STANDARD_FRAME_01", "锁一致", "按需", "✅ 2 参考（不带色卡）"),
        ],
    }
    lines = [
        "# 资产链 · 按输入模式",
        "",
        f"**`input_mode = {mode}`** — {INPUT_MODE_TITLE[mode]}",
        "",
        "> 本文件由 `model_adapter.py` 生成。判定规则见 `references/input-modes.md`；可复制提示词见 `assets/character-sheet-prompts.md` §14。",
        "",
        "## 1. 本模式要做什么（顺序不可跳步）",
        "",
        "| 顺序 | 产出 | 模型角色 | 生成次数 | 上传视频 |",
        "|---|---|---|---|---|",
    ]
    lines += [f"| {n} | {asset} | {role} | {count} | {upload} |" for n, asset, role, count, upload in chain[mode]]
    lines += [
        "",
        "## 2. 三条模式都成立的不变量",
        "",
        "- **最终人物资产（v5.2）**：每人 1 张 `ROLE_SHEET_X` 上下分区定妆板（上 1/3 左正面 + 右侧面面部特写；下 2/3 左放大裁头正面服装图 + 右完整背面全身），出图提示词逐字采用用户定稿、不改写。",
        "- **上传白名单（v4.2 / v5.1）**：每位出镜角色成对挂 `ROLE_SHEET_X` + `FACE_CLOSE_X` 两类；`CHARACTER_MOOD` / `OUTFIT` / `ROLE_STILL` 一张都不上传；后景焦外的不具名背景人影没有任何资产、不占参考位。",
        "- `FABRIC_DETAIL_X` 默认不出；`STANDARD_FRAME_01` 只同传 2 参考（主角拼板 + 场景参考 1 张：用了可选反打是 `SCENE_REVERSE_01`，跳过则是 `SCENE_MOOD_01`，**不带色卡**）。",
        "- **色卡**：A08 按两步走，交付 12 个 HEX 写死的**成品出图提示词**（纯文字出图、不传参考图、先于 A01 完成）；`COLOR_CARD_01` 先给 `A01–A0N` / 可选反打同传**只取色彩方案**，再到 C 段【参考绑定】锁色；A00 母版 / 标准首帧 / 人物资产不挂色卡，全阶段不写 `--sref`。",
        "- **场景提示词**：`A01–A0N` 恒为一条通用正文（含「以 @COLOR_CARD_01 为色彩方案参考：只取卡上的 12 色色值、主辅色结构与五级明度，不取色块的版式、HEX 标注文字与构图。」与固定画质段）+ N 条场景句组件表，由 `gpt-image-2.5` 类指令式模型出图，共用同一条正文、同一张色卡与同一组平台设置；占比等验收口径不进代码块。",
        "- **场景反打可选**：`SCENE_REVERSE_0X` 由用户自行选择用不用；不用时删 C 段引用、首帧第 2 张参考换 `SCENE_MOOD_01`、上传张数相应减少。",
        "- **摄影母版**：`PHOTO_MASTER_01` 中文文字块，v4.3 起为一段连续专业摄影描述（只写跨镜头统一项、不含具体焦段），不生成图、不上传，每条视频提示词逐字复用；【画面描述】= 全局设定段 + 逐镜块。",
        "- **视频提示词六块**：【视频基本参数】【参考绑定】【摄影母版】【禁止项】【画面描述】【收束与音频】，缺一块判不合格。",
        "- 三条铁律、色场占比、LUT、生成条规划与成果二分交付**不因输入模式改变**。",
        "",
        "## 3. 规则原文（来自能力档案）",
        "",
        f"- **input_mode_rule**：{rules.get('input_mode_rule', '见 references/input-modes.md')}",
        f"- **asset_chain_matrix**：{rules.get('asset_chain_matrix', '见 references/input-modes.md')}",
        f"- **zero_input_character_rule**：{rules.get('zero_input_character_rule', '见 references/input-modes.md §3')}",
        f"- **asset_minimal_rule**：{rules.get('asset_minimal_rule', '见 character-sheet-spec.md 附录 A')}",
        f"- **video_reference_rule**：{rules.get('video_reference_rule', '见 model-selection.md 附录')}",
        f"- **color_card_rule**：{rules.get('color_card_rule', '见 color-system.md §7')}",
        f"- **photography_master_rule**：{rules.get('photography_master_rule', '见 prompt-examples-video.md §8')}",
        f"- **video_prompt_structure_rule**：{rules.get('video_prompt_structure_rule', '见 prompt-examples-video.md §8')}",
        f"- **face_close_video_rule**：{rules.get('face_close_video_rule', '见 input-modes.md §4.2')}",
        "",
        "## 4. 零素材三禁（`zero` / `partial` 适用）",
        "",
        "1. 不写「@参考图 1 / 图 2」这类虚构引用；身份只由 `ROLE_CHARTER_X` 与上一环生成结果提供。",
        "2. 不把第一张随机出图当权威：面部出 4 挑 1 锁定后才进下一步。",
        "3. 不在同批图里改描述串、`body_ratio`、发饰或固有色 HEX；一次只改一个变量。",
        "",
        "> 用户只给一个图像模型时，按同样顺序由该模型全包，不拆三段接力。",
        "",
    ]
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(description="Model-aware planner / prompt adapter")
    ap.add_argument("--list", action="store_true", help="list capability database")
    ap.add_argument("--video-model", default="", help="video model name or alias")
    ap.add_argument("--model", default="", help="alias of --video-model (backward compatible)")
    ap.add_argument("--image-model", default="", help="image model name or alias")
    ap.add_argument("--stage", default="video", choices=["character", "scene", "video"])
    ap.add_argument("--duration", type=float, default=35.0,
                        help="成片总时长 T（秒），由 S0 用户给定；缺省 35 仅为建议值，可改")
    ap.add_argument("--aspect", default="16:9")
    ap.add_argument("--shots", type=int, default=0, help="override editorial shot count")
    ap.add_argument("--theme", default="")
    ap.add_argument("--body-ratio", default="8 头身",
                    help="locked head-to-body ratio for ALL character reference images")
    ap.add_argument("--face-spec", choices=["unified", "layered"], default="unified",
                    help="unified: whole pack uses warm grey + low-density Black Pro-Mist; "
                         "layered: face layer keeps it, full-body layer returns to neutral grey without filter")
    ap.add_argument("--input-mode", default="zero",
                    help="zero (M0 无人物图，默认) / partial (M1 半套) / provided (M2 已有资产)")
    ap.add_argument("--out-dir", default="")
    ap.add_argument("--base", default="", help="existing prompt file to adapt")
    args = ap.parse_args()
    try:
        input_mode = normalize_input_mode(args.input_mode)
    except ValueError as exc:
        ap.error(str(exc))

    db = load_db()
    models = db["models"]
    index = build_alias_index(models)

    if args.list:
        list_models(db)
        return 0

    video_name = args.video_model or args.model
    video_key = resolve(video_name, index, models)
    if not video_key or models[video_key]["kind"] != "video":
        print("Missing/unknown VIDEO model. Use --list, e.g. --video-model seedance-2.5", file=sys.stderr)
        return 2
    video = models[video_key]

    image_key = resolve(args.image_model, index, models)
    if image_key and models[image_key]["kind"] != "image":
        print(f"'{args.image_model}' is a video model; --image-model needs an image model.", file=sys.stderr)
        return 2
    image = models[image_key] if image_key else None
    if args.stage in ("character", "scene") and not image:
        print("Character/scene stage needs --image-model (e.g. nano-banana-2).", file=sys.stderr)
        return 2

    shot_count = args.shots or int(video.get("default_shots", 14))
    suggested = float(video.get("suggested_shot_s", 3.0))
    while args.duration / shot_count > suggested and shot_count < 24:
        shot_count += 1
    plan = build_units(video, args.duration, shot_count, args.aspect)
    plan["model_key"] = video_key
    plan["image_model"] = image["label"] if image else None
    plan["image_model_key"] = image_key
    plan["theme"] = args.theme
    plan["aspect"] = args.aspect
    plan["stage"] = args.stage
    plan["body_ratio"] = args.body_ratio
    plan["character_lighting_mode"] = db["character_sheet"]["lighting"]["mode"]
    plan["face_spec_mode"] = args.face_spec
    plan["input_mode"] = input_mode
    plan["asset_policy"] = {
        "final_character_assets": "ROLE_SHEET_X (one top/bottom-split 4-panel board per character)",
        "role_sheet_layout": "v5.2 上下分区定妆板：上 1/3 左正面 + 右侧面头肩特写；下 2/3 左放大裁头正面服装图（A-pose、头完整出画、只裁头不裁手脚）+ 右完整背面全身；纯净灰无缝影棚、正左主光/正右辅光/后右轮廓光、全清晰、真实材质；出图提示词逐字采用用户 2026-11-08 定稿、不改写；Nano Banana Pro 类、竖版 9:16",
        "role_sheet_prompt_source": "assets/character-sheet-prompts.md §14.6",
        "face_close_source_v52": "M1/M2 从新版 ROLE_SHEET_X 上方左格裁出；M0 从零生成后作拼板面部依据；两种来源都与拼板成对进视频",
        "video_character_references": ["ROLE_SHEET_X 上下分区定妆板资产", "FACE_CLOSE_X 人脸特写"],
        "process_assets_never_upload": [
            "CHARACTER_MOOD_X", "OUTFIT_X", "ROLE_STILL_X",
        ],
        "face_close_source": {
            "zero": "generated from scratch", "partial": "crop if available else generated",
            "provided": "cropped from user image, never generated",
        }[input_mode],
        "outfit_source": {
            "zero": "generated from scratch", "partial": "crop if available else generated",
            "provided": "cropped from user image, never generated",
        }[input_mode],
        "role_still": {
            "zero": "recommended (generate 1)", "partial": "recommended (generate 1)",
            "provided": "optional / reuse user still",
        }[input_mode],
        "fabric_detail": "on_demand_only",
        "standard_frame_references": 2,
        "standard_frame_references_detail": ["ROLE_SHEET_<主角>", "SCENE_REVERSE_01 或 SCENE_MOOD_01"],
        "standard_frame_second_reference_options": ["SCENE_REVERSE_01（启用可选反打）", "SCENE_MOOD_01（跳过反打）"],
        "scene_prompt_format": "one_shared_body_plus_N_scene_sentences",
        "scene_reverse": "optional_user_choice",
        "scene_reverse_when_skipped": "删除 C 段 @SCENE_REVERSE_0X 行；标准首帧第 2 张参考改 SCENE_MOOD_01；上传张数相应减少",
        "color_card_deliverable": "finished_text_to_image_prompt_with_12_hardcoded_HEX",
        "prompt_purity_rule": "only_current_generation_content_reference_usage_and_platform_params_in_code_blocks",
        "color_card_usage": "scene_color_scheme_plus_video_reference_binding",
        "scene_color_card_reference": "A01–A0N 与可选反打同传 @COLOR_CARD_01；只取 12 色色值 / 主辅结构 / 五级明度，不取色块版式、HEX 标注文字与构图；不写 --sref",
        "scene_image_model": "gpt-image-2.5",
        "scene_quality_clause": "画面干净通透，真实的景深与空气透视，焦内细腻，焦外柔和虚化，光影纯净统一，色彩平滑，明暗过渡稳定，严禁噪点，杂乱纹理，斑点，过度锐化，色彩混乱，塑料感。",
        "color_card_must_precede_A01": True,
        "run_mode": "guided",
        "autopilot_handoff_script": "scripts/build_handoff.py",
        "video_prompt_structure": ["视频基本参数", "参考绑定", "摄影母版", "禁止项", "画面描述", "收束与音频"],
        "photography_master": {
            "id": "PHOTO_MASTER_01",
            "kind": "text_block_not_an_image",
            "upload": False,
            "format": "one_continuous_professional_photography_paragraph_v4.3",
            "subsections": [],
            "excluded_from_master": [
                "具体 mm 焦段与 T 光圈（下放到【画面描述】逐镜块）",
                "面积占比与九宫格（【画面描述】全局段写一次）",
                "三层结构比例与圆形锚点（每镜单独写）",
            ],
            "focal_length_placement": "shot_blocks_in_picture_description_only",
            "reuse": "逐字复用到每条生成条的【摄影母版】块",
        },
        "shot_description_format": "global_setup_paragraph_plus_numbered_shot_blocks",
        "cross_block_dedup": "器材/质感/肤色/滤镜只在摄影母版；场景/占比/光位/动作/切镜只在全局段；身份锁定只在参考绑定；正向禁句只在禁止项；焦段/光圈/机位/焦点/切点只在逐镜块",
        "quality_clause_phrase": "明暗过渡稳定",
        "character_hierarchy": "主要人物只以以上两类资产为准，是画面里唯一被表现、唯一有清晰正脸与明确动作线的人物；后景背景人物不占参考位、不给正脸与特写、不与主角同一焦平面、不产生独立动作线、不新增可辨识妆造，只交代生活感。 其余细则见 SKILL.md 第 28 条与 §8.6",
        "camera_motion": "v5.8 手持基底幅度清晰可辨 + 每镜一种轻微推拉摇移或变焦、vlog 实拍感、可短暂直视；禁剧烈抖动/甩镜/变焦冲击/急速推拉",
        "background_figure_placement": "只写进画面描述逐镜块的三层空间→背景 与 环境动态；不写进动作/焦点/切点；禁止项用正向句写边界；参考绑定不新增人物资产",
        "shot_scale_policy": "禁用大远景/远景/大全景；默认中近景 50% / 两三人中景 30% / 特写 15% / 群像 5%，只在全景及更近档位之间拉开；三条铁律其余取值不变",
    }
    plan["face_quad_first"] = True
    plan["character_check_count"] = len(db["character_sheet"]["checklist"])
    plan["disclaimer"] = db["disclaimer"]
    plan["editorial_shot_rule"] = db["planning_rules"]["editorial_shot"]
    plan["generation_unit_rule"] = db["planning_rules"]["generation_unit"]

    active = image if args.stage in ("character", "scene") else video
    base_text = pathlib.Path(args.base).read_text(encoding="utf-8") if args.base else ""
    prompt_text = render_adapted_prompt(active, plan, args.stage, base_text, db)
    banner = input_mode_banner(input_mode)
    spec_text = banner + render_spec(video, image, plan, args.aspect, db)
    usage_text = banner + render_usage(video, image, plan, db)
    checklist_text = render_character_checklist(db, image, plan)
    character_prompts_text = render_character_prompts(active, db, plan) if args.stage == "character" else ""
    if character_prompts_text:
        character_prompts_text = (
            "> **范围提示（v3.6）**：以下六条是**扩展定妆包**模板（面部四宫格 + 六类实例），"
            "只有用户主动要求完整多视图时才用。默认路径与 `input_mode="
            + input_mode + "` 的实际步骤请看 `asset_chain.md`，可复制提示词见 "
            "`assets/character-sheet-prompts.md` §14。\n\n---\n\n" + character_prompts_text
        )
    asset_chain_text = render_asset_chain(input_mode, db)

    print(f"Video : {video['label']} | max {video.get('max_duration_s')}s | options {video.get('duration_options')}")
    print(f"Image : {image['label'] if image else 'not set'}")
    print(f"Input : {input_mode} — {INPUT_MODE_TITLE[input_mode]}")
    if args.stage == "character":
        print(f"Stage : character | FACE_QUAD_01 first | warm grey + 105mm + Black Pro-Mist / "
              f"face_spec={args.face_spec} / body_ratio={args.body_ratio} | "
              "face quad + full-body front + turnaround + four-panel board + 6 singles + "
              f"{plan['character_check_count']}-item checklist + design/costume/correspondence checks")
    print(f"Plan  : {plan['shot_count']} shots x {plan['per_shot_seconds']}s = {args.duration:g}s | "
          f"{plan['generation_unit_count']} generation units | trim {plan['trim_seconds']}s")
    for u in plan["units"]:
        print(f"  {u['unit']} {u['seconds']}s -> {', '.join(u['shot_ids']) or '—'}")
    for w in plan["warnings"]:
        print("  WARN: " + w)

    if args.out_dir:
        out = pathlib.Path(args.out_dir)
        out.mkdir(parents=True, exist_ok=True)
        (out / "adapted_prompt.md").write_text(prompt_text, encoding="utf-8")
        (out / "adaptation_spec.md").write_text(spec_text, encoding="utf-8")
        (out / "usage_guide.md").write_text(usage_text, encoding="utf-8")
        (out / "generation_plan.json").write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
        (out / "character_sheet_checklist.md").write_text(checklist_text, encoding="utf-8")
        (out / "asset_chain.md").write_text(asset_chain_text, encoding="utf-8")
        written = ["adapted_prompt.md", "adaptation_spec.md", "usage_guide.md",
                   "generation_plan.json", "character_sheet_checklist.md", "asset_chain.md"]
        if args.stage == "character":
            (out / "negative_character.txt").write_text(db["character_sheet"]["negative_for_character"], encoding="utf-8")
            (out / "character_prompts.md").write_text(character_prompts_text, encoding="utf-8")
            written += ["negative_character.txt", "character_prompts.md"]
        elif active.get("negative_mode") in ("field", "separate"):
            neg = NEGATIVES_ZH  # v3.7：负向词一律中文
            (out / "negative_prompt.txt").write_text("\n".join(neg), encoding="utf-8")
            written.append("negative_prompt.txt")
        params = [str(x) for x in active.get("params", [])]
        if any(k in params for k in ("seed", "CFG", "steps")):
            pd = {k: "按平台填写" for k in params}
            pd["width"] = 1280 if args.aspect == "16:9" else 720
            pd["height"] = 720 if args.aspect == "16:9" else 1280
            (out / "generation_params.json").write_text(json.dumps(pd, ensure_ascii=False, indent=2), encoding="utf-8")
            written.append("generation_params.json")
        print("Written: " + ", ".join(written))
    return 0


if __name__ == "__main__":
    sys.exit(main())
