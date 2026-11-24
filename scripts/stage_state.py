#!/usr/bin/env python3
"""Track staged delivery progress for a color-field AI film project.

Pure Python standard library. Never deletes user files; rollback only clears
confirmation records after a given stage.

Usage:
  python3 stage_state.py --project <dir> init --theme "雪夜药铺" --input-mode zero
  python3 stage_state.py --project <dir> next
  python3 stage_state.py --project <dir> status
  python3 stage_state.py --project <dir> advance --note "总揽通过"
  python3 stage_state.py --project <dir> rollback --stage S1 --note "换模型"
  python3 stage_state.py --project <dir> set --video-model seedance-2.5 --image-model nano-banana-2
  python3 stage_state.py --project <dir> set --input-mode provided --note "用户补了人物图"

v3.6: input_mode (zero / partial / provided) is decided at S0 and read by S1/S3/S5.
Default is zero (most users have no character reference images at all).

v3.9: run_mode (guided / autopilot) decides who releases the stage gate.
guided is the only default: one stage at a time, explicit user confirmation.
autopilot is enabled ONLY by explicit user authorization; it replaces
"user confirmed" with a logged automatic gate check and never fabricates
user confirmation.

v4.0: autopilot is decoupled from LibTV. execution_backend (libtv /
workbuddy / external) decides who runs S6/S7, so BOTH channels can reach S7
even when LibTV is not connected.
"""
import argparse
import datetime
import json
import pathlib
import sys

INPUT_MODES = {
    "zero": "M0 零素材（默认）：用户没有任何人物图；S3 必须从零生成 FACE_CLOSE_X / OUTFIT_X / ROLE_STILL_X，再出 ROLE_SHEET_X",
    "partial": "M1 部分素材：已有半套裁切并写 inherit-nothing-else，缺的那半从零生成",
    "provided": "M2 已有资产：传已有角色图、按 v5.2 逐字模板只生成 ROLE_SHEET_X 上下分区定妆板；FACE_CLOSE_X 从新版上方左格裁出",
}
MODE_ALIASES = {
    "m0": "zero", "m1": "partial", "m2": "provided",
    "零素材": "zero", "部分素材": "partial", "已有资产": "provided",
    "no-assets": "zero", "provided-assets": "provided",
}

RUN_MODES = {
    "guided": "逐步引导（默认）：每阶段一停，等用户明确回应才推进；S6 逐批确认",
    "autopilot": "自动托管：仅用户显式授权后启用，规则校验通过即留痕放行；S6/S7 交给 execution_backend 指定的后端",
}
BACKENDS = {
    "libtv": "LibTV Agent（优先但不唯一；未连接时换 workbuddy / external）",
    "workbuddy": "WorkBuddy 内生成能力按交接清单逐条执行",
    "external": "用户自有平台批量，交接包作批处理清单",
}
RUN_MODE_ALIASES = {
    "auto": "autopilot", "全自动": "autopilot", "托管": "autopilot",
    "manual": "guided", "手动": "guided", "逐步": "guided", "引导": "guided",
}


def normalize_mode(value, default="zero"):
    """Resolve input_mode aliases; default is zero (no reference images)."""
    if not value:
        return default
    key = str(value).strip().lower()
    key = MODE_ALIASES.get(key, key)
    if key not in INPUT_MODES:
        raise ValueError("input_mode must be zero/partial/provided (or M0/M1/M2)")
    return key


def normalize_backend(value, default=""):
    """Resolve execution_backend aliases; empty is allowed in guided mode."""
    if not value:
        return default
    key = str(value).strip().lower()
    aliases = {"agent": "libtv", "libtv-agent": "libtv", "本地": "workbuddy",
               "自己平台": "external", "外部平台": "external"}
    key = aliases.get(key, key)
    if key and key not in BACKENDS:
        raise ValueError("execution_backend must be libtv/workbuddy/external")
    return key


def normalize_run_mode(value, default="guided"):
    """Resolve run_mode aliases; guided is ALWAYS the default."""
    if not value:
        return default
    key = str(value).strip().lower()
    key = RUN_MODE_ALIASES.get(key, key)
    if key not in RUN_MODES:
        raise ValueError("run_mode must be guided/autopilot (or 手动/全自动)")
    return key


STAGES = [
    {
        "id": "S0", "name": "影像总揽", "outputs": ["master_overview.md"],
        "decision": "整支片子的结构、基调、美学设定（含角色设计差异化清单与服装六维）、色彩氛围、光影特点",
        "action": "只确认这份总揽是否通过；本阶段不谈模型、不给提示词",
        "options": ["A. 通过，进入模型选型", "B. 修改主色 / 五段时间分配 / 圆形锚点 / 光位 / 时长画幅 / 角色三处记忆点", "C. 换主题方向"],
        "howto": "总揽里的每一项都要能落到可见物件、光位、比例或数值；不写抽象风格词。"
                 "美学设定·人物子表必须定稿：角色固定描述串、body_ratio、三处记忆点、差异化清单 ≥3 条、一处生活痕迹、"
                 "服装六维与四朝向结构清单、面部规格模式与黑柔档位（见 character-design-aesthetics.md / costume-design.md）。",
        "next": "S1 模型选型（意向模型 + 推荐模型）",
    },
    {
        "id": "S1", "name": "模型选型", "outputs": ["model_plan.md"],
        "decision": "图像模型 + 视频模型、生成通道、单次时长上限与访问方式",
        "action": "告诉我你的意向图像模型与视频模型；或直接采用我给的推荐组合",
        "options": ["A. 采用推荐组合", "B. 用我的意向模型（写出图像 + 视频模型名）", "C. 只交文档，我自己在平台生成（通道 B）"],
        "howto": "推荐必须给主推 + 备选 + 理由，并列出两层的硬约束；deprecated 模型不进推荐。",
        "next": "S2 适配规格与整体规划",
    },
    {
        "id": "S2", "name": "适配规格与整体规划", "outputs": ["adaptation_spec.md", "generation_plan.json", "usage_guide.md"],
        "decision": "镜数 / 每镜秒数 / 生成条数 / 时间码结构 / 提示词形态",
        "action": "确认生成条时长没有超过该模型的单次上限，且分镜规划与总揽五段结构一致",
        "options": ["A. 通过，继续下一步", "B. 修改镜数 / 每镜时长 / 画幅", "C. 换模型（回退到 S1 重跑）"],
        "howto": "必须运行 model_adapter.py 读能力档案；长上限只用于把短镜头合成一次生成，不是拉长镜头。",
        "next": "S3 定妆定景提示词与使用指引",
    },
    {
        "id": "S3", "name": "角色资产（默认：每人 1 张 ROLE_SHEET_X；按 input_mode 分支）+ 定景提示词与小样",
        "outputs": ["character_prompts.md（M0：B-Z 从零生成组；M2：B00 裁切说明；三种模式共用 B02 拼板 + 角色/服装设计段）", "prompts_character_scene.md（成品色卡出图提示词 / 场景通用正文含色彩参考限定句与固定画质段 + N 条场景句 / 可选统一反打 / 2 参考标准首帧 / 一段式摄影母版文字块）", "character_sheet_checklist.md（拼板 8 项；扩展包 13 项）", "使用步骤", "角色设计 6 问 + 服装造型 6 问 + 拼板 8 项 + 成片 6 项检查结论"],
        "decision": "input_mode 是否已判定；M0 是否写全 12 项 ROLE_CHARTER_X 并从零生成前两格；ROLE_SHEET_X 是否每人 1 张且四格齐全；过程资产（FACE_CLOSE_X 除外）是否一张未上传；STANDARD_FRAME_01 是否只挂 2 参考且不带色卡；色卡是否两处使用且 A 段只取色彩方案、先于 A01 完成；场景图是否用指令式模型并含固定画质段；视频提示词是否六块齐全",
        "action": "按使用步骤跑小样：M0 先出面部 / 服装 / 定妆照再出拼板，M2 裁两格后直接出拼板，把结果发回来",
        "options": ["A. 拼板与成片小样都通过，继续下一步", "B. 不通过：说明哪一项不过（输入模式 / B-Z 生成组 / 12 项设定 / 上下 1/3 : 2/3 分区格位 / 同一张脸 / 发饰 / 不对称不换边 / 背面不空白 / 头身比 / 暖灰全清晰 / 无色场 / 过程图误上传）", "C. 换图像模型或改输入模式（回退到 S0）"],
        "howto": "【默认规格，三种输入模式共用】先按 character-design-aesthetics.md 过设计自检 6 问、按 costume-design.md 过服装自检 6 问，定稿角色固定描述串、服装六维与四朝向结构清单，锁定 body_ratio。"
                 "读 stage_state.json 的 input_mode：M0 零素材（默认）写全 12 项 ROLE_CHARTER_X 文字设定，按 character-sheet-prompts.md §14 从零生成 CHARACTER_MOOD_X / FACE_CLOSE_X / OUTFIT_X / ROLE_STILL_X（面部出 4 挑 1 锁定），再由一致性模型按 v5.2 逐字模板出每人 1 张 ROLE_SHEET_X 上下分区定妆板（M0 用 ROLE_STILL_X 当参考形象、同一版式）；"
                 "M1 已有半套裁切并写 inherit-nothing-else、缺的那半生成；M2 前两格从用户已有图裁切、不生成，只出拼板。三种模式最终人物资产都只交 1 张 ROLE_SHEET_X；v3.8 视频层另按出镜角色成对加挂 FACE_CLOSE_X（唯一允许进视频的过程件），其余过程资产一张不上传。FABRIC_DETAIL_X 默认不出；STANDARD_FRAME_01 只同传 2 参考（主角拼板 + 场景参考 1 张：用了可选反打是 SCENE_REVERSE_01，跳过则是 SCENE_MOOD_01，不带色卡）；A08 是 12 个 HEX 写死的成品出图提示词（归纳 meta 指令只作方法，不传参考图），**必须先于 A01 完成**；COLOR_CARD_01 先给 A01–A0N 与可选反打同传只取色彩方案（12 色色值 / 主辅结构 / 五级明度，不取色块版式与标注文字），再到 C 段【参考绑定】锁色；A00 母版 / 标准首帧 / 人物资产不挂色卡，全阶段不写 `--sref`；A01–A0N 由 `gpt-image-2.5` 类指令式模型出图，通用正文含色彩参考限定句与固定画质段、一条通用正文 + N 条场景句，占比等验收口径不进代码块；SCENE_REVERSE_0X 可选；PHOTO_MASTER_01 是 v4.3 一段式文字块、不含具体焦段、不上传。"
                 "全板统一纯色暖灰 #C6BCB1 无缝影棚 + 三点式 5500K 中性白 + 全清晰 + 无现代浓妆 + 低密度黑柔仅高光轻晕；色场、暖金轮廓光、前景遮挡与景深只进 STANDARD_FRAME_01。过拼板 8 项；零素材三禁：不虚构 @参考图、不把首张随机图当权威、不跨图改描述串。 **v5.1 人物层级**：主角是唯一被表现、唯一有身份资产的人物；后景焦外可有 1–3 个不具名背景人影，不占参考位、不给正脸与特写、不与主角同焦平面、不产生独立动作线，只写进逐镜块的背景层与环境动态；全片禁用大远景 / 远景 / 大全景，景别只在全景及更近档位之间拉开，三条铁律其余取值不变。"
                 "【扩展包，仅用户主动要求完整多视图时】才按 character-sheet-spec.md 正文出 FACE_QUAD_01 面部四宫格（最先）、定妆基准、朝向三视图、四格板与六张单图，过 13 项；模板 character-sheet-prompts.md §1-13。",
        "next": "S4 脚本与分镜表",
    },
    {
        "id": "S4", "name": "脚本与分镜表", "outputs": ["shot_list.csv"],
        "decision": "镜序、景别节奏、生成条 ID、圆形锚点与前景遮挡",
        "action": "确认分镜表的节奏、镜数、镜序，以及每条生成条装了哪几个镜头",
        "options": ["A. 通过，继续下一步", "B. 修改镜序 / 景别 / 单镜时长", "C. 换段落结构（回退到 S0）"],
        "howto": "分镜表必须含「生成条 ID」与「模型单次上限」两列；总时长 T / 镜数 / 场景数 / 段落数按 S0 用户给定值（不卡死），长条用时间码按用户给定区间拆成短镜头（建议 2-4 秒，可改）。",
        "next": "S5 逐镜提示词与使用指引",
    },
    {
        "id": "S5", "name": "逐镜提示词", "outputs": ["prompts_shots.md", "使用步骤"],
        "decision": "语言、六块结构、参考图绑定（人物两类成对 / 色卡在【参考绑定】为第二处使用）、摄影母版一段式且逐字一致、禁止项正向句、画面描述全局段 + 逐镜块、焦段 / 光圈只在逐镜块、跨块去重、画质段短语、参数行、跨场景「场景参照 @」（v5.3）、v5.4 提示词纯净（代码块只写直接告诉 AI 的内容 / 元信息出代码块）、v5.8 手持基底运镜与视线（可短暂直视）",
        "action": "抽查 2-3 条提示词，确认语言、参考图绑定、摄影母版一段式且三条逐字一致、逐镜块与焦段下放、跨块去重、负向词机制和生成条时长都正确",
        "options": ["A. 通过，进入生成", "B. 修改语言 / 负向词 / 摄影母版 / 逐镜块 / 时间码 / 参数行 / 提示词纯净", "C. 先别生成，只交文档"],
        "howto": "每条提示词固定六块结构【视频基本参数】【参考绑定】【摄影母版】【禁止项】【画面描述】【收束与音频】；【摄影母版】= PHOTO_MASTER_01 全文逐字复用，v4.3 起是一段连续专业摄影描述、只写跨镜头统一项、不含具体 mm 焦段与 T 光圈；【画面描述】= 全局设定段（统一场景 / 占比 / 光位 / 动作克制 / 切镜规则，每条只写一次）+【镜头N | 时间码 | 镜头名】逐镜块，每块写三层空间、景别构图、机位高度 + 单一焦段 + T 光圈、占画面比、动作、运镜、焦点、环境动态、切点匹配；焦段与光圈只在逐镜块写一次，跨块不复述（器材 / 质感 / 肤色 / 滤镜只在母版，占比 / 光位只在全局段，身份锁定只在【参考绑定】）。人物参考只有 ROLE_SHEET_X + FACE_CLOSE_X 两类成对，色卡在【参考绑定】是第二处使用（第一处在 A 段场景图取色彩方案）。**v5.3 跨场景「场景参照 @」**：一条生成条含 ≥2 处场景时，【画面描述】每个逐镜块正文开头逐字写 `场景参照 @SCENE_MOOD_0X；` 再接三层空间句，一镜一次、只 @ 本镜那一处；只写进逐镜块，【参考绑定】不重复绑定说明；句式锁定、单场景条不强制。另附：粘到哪里、传哪些参考、选几秒档、生成几次、怎么挑片、怎么修错帧。",
        "next": "S6 生成执行（每批 ≤5 镜）",
    },
    {
        "id": "S6", "name": "生成执行", "outputs": ["每批 ≤5 镜的镜头素材"],
        "decision": "本批镜头是否达到色场、光位与一致性要求",
        "action": "按使用步骤跑完这一批，把结果回传给我确认",
        "options": ["A. 本批通过，继续下一批", "B. 本批重跑：指出镜号与问题", "C. 暂停生成"],
        "howto": "本批开跑前先按 asset_chain.md / C00 备齐本批参考图；一张图都还没出时先出图，不要直接把空槽传上去。先复用标准首帧、摄影母版与【参考绑定】里那张成品色卡（A08 成品提示词生成，12 HEX 写死，已在 A 段场景图取过色彩方案），按档位设时长，生成 2-3 条挑 1，写进 QA 表；项目若跳过可选场景反打，按清单删掉对应 @SCENE_REVERSE_0X 行再上传；未确认不扩大批次。",
        "next": "S7 验收与交付",
    },
    {
        "id": "S7", "name": "验收与交付", "outputs": ["成片", "audit_report.json / .md"],
        "decision": "成片是否通过量化与人工检查",
        "action": "按使用步骤剪辑、统一 LUT、跑验收脚本，确认成片或指出需补拍的镜号",
        "options": ["A. 完成", "B. 补拍指定镜号", "C. 回退到 S0 / S1 调整色场或模型"],
        "howto": "只测成片段；不达标按「首帧 → 提示词 → 统一调色 → 模型」顺序修。",
        "next": "项目完成",
    },
]
INDEX = {s["id"]: i for i, s in enumerate(STAGES)}


def state_path(project):
    return pathlib.Path(project) / "stage_state.json"


def now():
    return datetime.datetime.now().isoformat(timespec="seconds")


def load(project):
    p = state_path(project)
    if not p.exists():
        print(f"No state file at {p}. Run 'init' first.", file=sys.stderr)
        return None
    return json.loads(p.read_text(encoding="utf-8"))


def save(project, state):
    p = state_path(project)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def guidance(stage, state):
    auto = state.get("run_mode", "guided") == "autopilot"
    lines = [
        f"[{stage['id']} {stage['name']}]",
        "",
        f"✅ 本阶段产出：{'、'.join(stage['outputs'])}",
        f"   关键决策点：{stage['decision']}。",
        f"   使用指引：{stage['howto']}",
        "",
    ]
    if auto:
        lines += [
            "🤖 自动门禁（autopilot）：校验下列条件通过即留痕放行，不等待人工确认。",
            f"   放行条件：{stage['decision']}；产出文件齐全且符合 v3.9 硬约束。",
            f"   留痕：写入 autopilot_log（阶段 / 时间 / 校验项 / 结果 / 依据文件），advance 记「自动门禁通过」。",
            f"   校验通过后自动进入 {stage['next']}；任一条件不满足即停下并汇报，回退 guided 由人工接手。",
            f"   S6/S7 由执行后端 `{state.get('execution_backend') or '未指定'}` 按交接清单的数量上限执行，"
            "本 skill 不自行发起产生费用的生成；libtv 未连接时换 workbuddy / external，autopilot 仍可跑到 S7。",
        ]
    else:
        lines += [f"👉 现在请你：{stage['action']}"]
        lines += ["   " + o for o in stage["options"]]
        lines += ["", f"⏸ 收到你的确认后才会进入 {stage['next']}；在此之前不会生成后续内容。"]
    model_text = state.get("video_model") or state.get("model") or "未设置"
    image_text = state.get("image_model") or "未设置"
    mode = state.get("input_mode", "zero")
    run_mode = state.get("run_mode", "guided")
    lines += ["", f"当前：主题 {state.get('theme', '未设置')} | 图像 {image_text} | 视频 {model_text} | 输入模式 {mode} | 运行通道 {run_mode}"]
    lines += [f"输入模式：{INPUT_MODES.get(mode, INPUT_MODES['zero'])}"]
    lines += [f"运行通道：{RUN_MODES.get(run_mode, RUN_MODES['guided'])}"]
    if stage["id"] == "S0":
        lines += ["S0 必做：扫 assets/ 判定 input_mode（默认 zero，没图不是缺项）；M0/M1 定稿 12 项 ROLE_CHARTER_X 文字设定。不因没图追问或卡阶段。"]
    elif stage["id"] == "S3":
        lines += ["S3 起点按 input_mode 分支；三种模式最终都只交每人 1 张 ROLE_SHEET_X 给视频层，过程资产一张不上传。"]
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(description="Staged delivery progress tracker")
    ap.add_argument("--project", required=True, help="project directory")
    ap.add_argument("action", choices=["init", "status", "next", "advance", "rollback", "set", "reset"])
    ap.add_argument("--theme", default="")
    ap.add_argument("--model", default="", help="legacy alias of --video-model")
    ap.add_argument("--video-model", default="")
    ap.add_argument("--image-model", default="")
    ap.add_argument("--channel", default="")
    ap.add_argument("--input-mode", default="",
                    help="zero (M0 无人物图，默认) / partial (M1 半套) / provided (M2 已有资产)")
    ap.add_argument("--run-mode", default="",
                    help="guided (逐步引导，默认) / autopilot (仅用户显式授权后全自动)")
    ap.add_argument("--backend", default="",
                    help="execution_backend: libtv / workbuddy / external（autopilot 用；libtv 不可用也能跑通）")
    ap.add_argument("--note", default="")
    ap.add_argument("--stage", default="", help="stage id for rollback/reset, e.g. S2")
    args = ap.parse_args()
    try:
        requested_mode = normalize_mode(args.input_mode)
        requested_run_mode = normalize_run_mode(args.run_mode)
        requested_backend = normalize_backend(args.backend)
    except ValueError as exc:
        ap.error(str(exc))

    project = args.project
    if args.action == "init":
        if state_path(project).exists():
            print(f"State already exists at {state_path(project)}. Use 'status' or 'reset'.", file=sys.stderr)
            return 1
        video_model = args.video_model or args.model
        state = {
            "project": project, "theme": args.theme, "model": video_model,
            "video_model": video_model, "image_model": args.image_model,
            "channel": args.channel, "input_mode": requested_mode,
            "run_mode": requested_run_mode,
            "execution_backend": requested_backend or ("libtv" if requested_run_mode == "autopilot" else ""),
            "current": "S0", "confirmed": {}, "history": [], "autopilot_log": [],
            "created_at": now(),
        }
        save(project, state)
        print(f"Initialized {project} at S0. theme={args.theme or '未设置'}, "
              f"image={args.image_model or '未设置'}, video={video_model or '未设置'}, "
              f"input_mode={requested_mode}, run_mode={requested_run_mode}, "
              f"execution_backend={state['execution_backend'] or 'n/a（guided）'}")
        if requested_run_mode == "autopilot":
            print("⚠ autopilot 仅在用户显式授权「全自动出成片」后启用；默认永远是 guided。"
                  "libtv 未连接可用 --backend workbuddy / external。")
        print()
        print(guidance(STAGES[0], state))
        return 0

    state = load(project)
    if state is None:
        return 1

    if args.action == "set":
        pairs = [("theme", args.theme), ("video_model", args.video_model or args.model),
                 ("image_model", args.image_model), ("channel", args.channel),
                 ("input_mode", requested_mode if args.input_mode else ""),
                 ("run_mode", requested_run_mode if args.run_mode else ""),
                 ("execution_backend", requested_backend if args.backend else "")]
        for key, value in pairs:
            if value:
                state[key] = value
                if key == "video_model":
                    state["model"] = value
                state["history"].append({"at": now(), "event": f"set {key}={value}"})
        save(project, state)
        print(f"Updated: theme={state.get('theme')} image={state.get('image_model')} "
              f"video={state.get('video_model')} channel={state.get('channel')} "
              f"input_mode={state.get('input_mode', 'zero')} run_mode={state.get('run_mode', 'guided')} "
              f"execution_backend={state.get('execution_backend') or 'n/a'}")
        if args.input_mode:
            print("输入模式变更：请回 S0 重出总揽，并同步 S1 分工表与 S3 提示词组；分镜与色场方案不变。")
        return 0

    if args.action == "status":
        print(f"Project : {state['project']}")
        print(f"Theme   : {state.get('theme', '未设置')}")
        print(f"Image   : {state.get('image_model', '未设置')}")
        print(f"Video   : {state.get('video_model') or state.get('model', '未设置')}")
        print(f"Channel : {state.get('channel', '未设置')}")
        mode = state.get("input_mode", "zero")
        print(f"InputMode: {mode}  ({INPUT_MODES.get(mode, INPUT_MODES['zero'])})")
        run_mode = state.get("run_mode", "guided")
        print(f"RunMode  : {run_mode}  ({RUN_MODES.get(run_mode, RUN_MODES['guided'])})")
        backend = state.get("execution_backend", "")
        print(f"Backend  : {backend or 'n/a'}  ({BACKENDS.get(backend, '未指定；guided 不需要')})")
        print(f"Current : {state['current']} {STAGES[INDEX[state['current']]]['name']}")
        confirmed = state.get("confirmed", {})
        print(f"Confirmed: {', '.join(confirmed.keys()) if confirmed else 'none'}")
        print()
        for s in STAGES:
            mark = "✓" if s["id"] in confirmed else ("→" if s["id"] == state["current"] else " ")
            print(f" {mark} {s['id']} {s['name']}")
        return 0

    if args.action == "next":
        print(guidance(STAGES[INDEX[state["current"]]], state))
        return 0

    if args.action == "advance":
        current = state["current"]
        if current not in INDEX or INDEX[current] >= len(STAGES) - 1:
            print("Already at the final stage.", file=sys.stderr)
            return 1
        auto = state.get("run_mode", "guided") == "autopilot"
        default_note = "自动门禁通过" if auto else "用户确认通过"
        note = args.note or default_note
        state["confirmed"][current] = {
            "at": now(), "note": note, "by": "autopilot" if auto else "user",
        }
        state["current"] = STAGES[INDEX[current] + 1]["id"]
        state["history"].append({"at": now(), "event": f"advance {current} -> {state['current']}", "note": note})
        if auto:
            state.setdefault("autopilot_log", []).append({
                "at": now(), "stage": current, "result": "自动门禁通过",
                "check": STAGES[INDEX[current]]["decision"],
                "outputs": STAGES[INDEX[current]]["outputs"], "note": note,
            })
        save(project, state)
        print(f"Confirmed {current}. Now at {state['current']} {STAGES[INDEX[state['current']]]['name']}.")
        print()
        print(guidance(STAGES[INDEX[state["current"]]], state))
        return 0

    if args.action == "rollback":
        target = args.stage.upper()
        if target not in INDEX:
            print(f"Unknown stage '{target}'. Valid: {', '.join(INDEX)}", file=sys.stderr)
            return 1
        removed = [k for k in state.get("confirmed", {}) if INDEX[k] >= INDEX[target]]
        for k in removed:
            del state["confirmed"][k]
        state["current"] = target
        state["history"].append({"at": now(), "event": f"rollback to {target}", "note": args.note, "cleared": removed})
        save(project, state)
        print(f"Rolled back to {target}. Cleared confirmations: {', '.join(removed) if removed else 'none'}.")
        print("Product files are kept; nothing was deleted.")
        print()
        print(guidance(STAGES[INDEX[target]], state))
        return 0

    if args.action == "reset":
        target = (args.stage or "S0").upper()
        if target not in INDEX:
            print(f"Unknown stage '{target}'.", file=sys.stderr)
            return 1
        state["current"] = target
        state["confirmed"] = {}
        state["history"].append({"at": now(), "event": f"reset to {target}", "note": args.note})
        save(project, state)
        print(f"Reset to {target}; all confirmations cleared. Files kept.")
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
