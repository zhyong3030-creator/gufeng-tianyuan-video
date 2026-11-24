# 自动托管交接包模板（v4.0 · 三后端通用）

> 由 `scripts/build_handoff.py --backend libtv|workbuddy|external` 按本模板填充，产出 `libtv_handoff.md` / `libtv_manifest.json` / `libtv_assets_manifest.json`（文件名保持兼容）。
> `{{双花括号}}` 是替换槽位；生成后的文件里不得残留任何槽位。
> **交接包是给选定执行后端的执行依据，不是给用户看的操作手册**；用户侧说明仍放在 `000_先看这个-操作手册.md`。
> **libtv 是优先但不唯一的后端**：`workbuddy` 用当前会话按清单逐条生成，`external` 把交接包当批处理清单；libtv 未连接时 autopilot 照样跑到 S7。

---

## 一、`libtv_handoff.md` 模板

````markdown
# {{主题}} · 统一色场短片生产包（已定稿，请逐字执行）

## 0. 执行约束（最高优先级，先读这一段）

1. 本包为**已定稿生产包**。所有提示词必须逐字执行，**不得重写、扩写、翻译、精简或自行重新拆分镜与写 prompt**；不得把六块结构压成一段自然语言描述。
2. `COLOR_CARD_01` 由 **A08 成品色卡出图提示词**（12 个 HEX 写死、纯文字出图、不传参考图）生成；「12 色归纳」中文只是生成它的 meta 指令，**不进包、不复制**。色卡**两处使用**：`A01–A0N` 场景基调图与可选反打同传只取色彩方案（12 色色值 / 主辅结构 / 五级明度，不取色块版式与标注文字）、`C01–C03`【参考绑定】上传；`A00` 母版 / 标准首帧 / 人物资产仍不挂色卡，全阶段不写 `--sref`。色卡必须先于 A01 完成。即：在 A 段场景图取色彩方案、在每条视频提示词的【参考绑定】为第二处使用。
3. `PHOTO_MASTER_01` 摄影母版是**中文文字块**，v4.3 起为**一段连续专业摄影描述**（只写跨镜头统一项、不含具体焦段；焦段与 T 光圈下放到逐镜块）；它**不是图片，不生成、不上传、不占参考位**，每条生成条逐字复用同一份。C 段【画面描述】= 全局设定段 + 逐镜块，逐镜块里才写单一焦段与 T 光圈。
4. 人物参考**只有两类成对**：`ROLE_SHEET_X` 上下分区定妆板资产（v5.2 逐字模板：上 1/3 正侧面头肩特写 + 下 2/3 放大裁头正面服装图与背面全身）+ `FACE_CLOSE_X` 人脸特写（从新版上方左格裁出），每位出镜角色一组；不挂四宫格、定妆基准、四格板、单独三视图与服装放大图。**v5.1 人物层级**：主角是唯一被表现、唯一有身份资产的人物；后景焦外可有 1–3 个不具名背景人影，不占参考位、不给正脸与特写、不与主角同焦平面、不产生独立动作线，只写进逐镜块的背景层与环境动态。
5. 主辅色占比、九宫格覆盖、五级明度由色场方案表与摄影母版写死，**不从色卡取**；柔光与光晕全片统一加一次，不逐镜叠加。
6. 提示词正文一律简体中文；仅平台参数、资产 ID、器材型号与色值、模型专有名保留原文。
7. 若平台模型、参考位或时长不支持，按 `libtv_manifest.json` 的 `degradation` 表降级并**记录偏差**，不得悄悄改色场规则。
8. 生成次数上限见 `libtv_manifest.json` 的 `max_total_generations`；**超限即停并汇报，不静默重跑**。
9. **风格固定**：本片为「中式古装田园 / 暖调统一色场」类短片。暖调色场、斜后侧主光、暖象牙—蜜桃肤色、奶油金高光与柔焦质感是风格常量；换主题只换主题、人物、物件与剧情，**不得换成别的视觉风格，不得放宽三条铁律**。**全片禁用大远景 / 远景 / 大全景**（用户 2026-11-08 二次纠偏）：景别只在全景及更近档位之间拉开，背景人影只作后景焦外虚化层，不做纪念碑式空镜头。
10. **v5.3 跨场景「场景参照 @」**：一条生成条装了不止一处场景时，【画面描述】每个逐镜块正文开头逐字写 `场景参照 @SCENE_MOOD_0X；` 再接三层空间句，一镜一次、只 @ 本镜那一处；只写进逐镜块，【参考绑定】不重复绑定说明；句式不得改写，单场景条不强制。这不是新增上传资产，参考张数不因此变化。
11. **v5.4 提示词纯净**：C 段代码块只写直接告诉 AI 的内容，【视频基本参数】只写视频时长 / 视频比例 / 视频类型 / 视频概述；平台 / 模型 / 档位 / 生成条编号 / 成片时间码 / 挑片 / 记录种子 / 剪辑台衔接 / 跨步骤说明 / 按需补图一律移到说明层，不得写进提示词；被删信息必须在说明层找得到。A 段出图提示词不受影响。
12. **v5.6 人物层级句定稿**：【参考绑定】末尾逐字写「主要人物只以以上两类资产为准，是画面里唯一被表现、唯一有清晰正脸与明确动作线的人物；后景背景人物不占参考位、不给正脸与特写、不与主角同一焦平面、不产生独立动作线、不新增可辨识妆造，只交代生活感。」（项目把「主要人物」换成「三位主角」）；主角唯一性半句保留、只简化背景半句，v5.5 中间态作废；背景人影 1–3 人 / 后景焦外 / 不具名 / 禁用大远景等细则仍按第 28 条与 §8.6 执行。见 §8.9。
13. **v5.8 手持基底运镜与视线**：**手持是基底、幅度清晰可辨**：画面随步伐与动作有看得出来的轻微上下浮动、左右摆移、构图偏移与找平，带呼吸起伏、身体移动惯性与随手记录的 vlog 实拍感，不剧烈抖动、不甩镜；**其上每镜按需叠一种轻微的推 / 拉 / 摇 / 移或轻微变焦**来重新取景，不同时堆满多种运动、禁变焦冲击与急速推拉，各镜附加运动不重样、末镜只放慢不停住；**允许人物短暂自然地看向镜头**，但不面对镜头表演、不做夸张鬼脸与现代自拍式表情。写在动作句之后、景深句之前。v5.7「缓慢推拉摇移、禁固定镜头 / 禁手持 / 禁直视」为历史口径，v5.8 起作废。 见 §8.10。
14. **v5.8 表情写法**：禁标签式定性词，先写可见细节再点明情绪与分寸；代码块「笑」字 0；各镜情绪不重样。
15. **v5.8 2.5 规格**：单次 4–30 秒 / 参考 50 / 时间戳切镜 / `generate_audio: true` / 1080p 10bit mov + PCM / Draft / 不支持真人人脸参考 / 风格不与 2.0 混用；瞳孔不发光不异色。
16. **v5.8 独立 BGM**：配乐不进视频提示词，另出一条独立全片配乐；【收束与音频】逐字写「不要字幕，不要 bgm」+ 环境声正向句。
17. **v5.8 帧模式**：S0 按模型二选一（传统首帧链路 / 2.5 全模态参考生视频不设首尾帧），不混用；参考图不是首帧但必须决定视频内容。
18. **v5.8 报错口径**：版权报错多为平台偶发误判，原样重提 1 次即可，不改词 / 不换账号 / 不连点重跑。

## 1. 任务目标

- 主题：{{主题}}
- 成片：{{总时长}} 秒 / {{镜数}} 镜 / {{场景数}} 个场景 / {{画幅}} / {{分辨率}}
- 输入模式：`{{input_mode}}`；运行通道：`autopilot`；执行后端：`{{execution_backend}}`（{{execution_backend_name}}）
- 图像模型：{{图像模型组合}}；视频模型：{{视频模型}}
- 生成条：{{生成条数}} 条，逐条 ID 与时间码见第 4 节

## 2. 必须先完成的参考资产（按 A 段提示词逐条执行）

| 顺序 | 提示词 ID | 产出 | 上传 |
|---|---|---|---|
{{A段资产表}}

**色卡**：直接复制生产包 A08 的**成品色卡出图提示词**纯文字出图，不上传任何参考图；12 个 HEX 与用途已写死。归纳 meta 指令只作方法，不要粘到平台。若项目另行提供归纳素材且明显分成两组色温 / 色相，**先停下提醒重新分组，不要强行合并**。
**场景反打**：`SCENE_REVERSE_0X` 是**可选**资产。生产包标注「不用」时整步跳过，C 段【参考绑定】删掉对应 `@SCENE_REVERSE_0X` 行、上传张数相应减少；**不要凭空补一张不存在的反打图**。
**标准首帧**：只同传 2 参考（`ROLE_SHEET_<主角>` + 场景参考 1 张：用了可选反打是 `SCENE_REVERSE_01`，跳过则是 `SCENE_MOOD_01`），**不带色卡**。
**摄影母版**：A10 是文字块，直接复制到每条 C 段提示词的【摄影母版】块，不生成图片。

## 3. 上传顺序（每条生成条相同）

```
{{上传序列}}
```

人物部分：每位出镜角色成对上传 `ROLE_SHEET_X` + `FACE_CLOSE_X`。参考位不足时优先保 `ROLE_SHEET_X`，人脸特写优先给近景多的生成条；`FABRIC_DETAIL_X` 仅在材质被画错时按需补 1 张。视觉母版、场景基调版、人物过程图与摄影母版**一律不占参考位**。

## 3.5 执行后端与跑法 · `{{execution_backend}}`

{{按后端生成的跑法：libtv = Canvas / agent-im 工具序列；workbuddy = 当前会话逐条执行顺序 + QA 表；external = 逐条批处理清单 + 使用步骤}}

> **换后端只换本节**：S0–S5 生产包、提示词、固定风格与色场规则一个字不改。

## 4. 生成条清单（C 段提示词逐字执行）

| 生成条 | 时长 | 成片时间码 | 首帧 | 场景参考 | 人物参考 | beat / 切点 |
|---|---|---|---|---|---|---|
{{生成条表}}

每条生成条的可复制提示词在 `提示词全集.md` 的 C 段（C01–C0N），固定六块结构【视频基本参数】【参考绑定】【摄影母版】【禁止项】【画面描述】【收束与音频】；【禁止项】内部为正向句。每条生成 {{picks_per_unit}} 次挑 1，最多重跑 {{max_retries_per_unit}} 次，记录种子值、档位与参考编号。

## 5. 拼接、调色与导出

1. 按 `shot_list.csv` 的时间码切开生成条，按镜序拼接；切点类型（不设切点 / 匹配接续 / 硬切）以分镜表为准，C→D 处 0.5 秒柔化叠化在剪辑台做。
2. 全片统一加一次柔光与统一 LUT，**不逐镜叠加**；不加字幕、不叠水印、不引入生产包之外的音乐与对白。
3. 导出 {{画幅}} / {{分辨率}} 成片，命名为 `{{主题}}-成片.mp4`。
4. 回传：成片链接或本地文件、每条生成条的结果与实际生成次数、与生产包不一致之处（如有）。

## 6. 完成标准

同时满足：全部生成条都有结果；已按分镜表拼成一支完整成片；实际生成次数未超 `max_total_generations`；成片通过色场验收（主色覆盖 3×3 九分区、光位与肤色稳定、无跨条跳色）。**只给进度卡或派发回执不算完成。**
本后端的完成判定：{{execution_backend_completion}}。产物归属统一标注「**{{execution_backend_attribution}}**」。

## 7. 附：本包包含的文件

- `提示词全集.md`（唯一生效提示词源）
- `注意点全集.md`（唯一注意点源）
- `000_先看这个-操作手册.md`（成果地图）
- `01_色场方案表.md`（占比 / 九宫格 / 明度）
- `shot_list.csv`（分镜与生成条）
- `generation_plan.json`（生成条规划）
- `libtv_manifest.json`（机器可读清单）
- `libtv_assets_manifest.json`（参考资产清单）
````

---

## 二、`libtv_manifest.json` 骨架

```json
{
  "schema_version": "4.0.0",
  "run_mode": "autopilot",
  "execution_backend": "libtv",
  "execution_backend_name": "LibTV Agent 托管",
  "execution_actor": "LibTV 后端 Agent",
  "platform_status": "unknown",
  "requires_fallback": false,
  "input_mode": "zero",
  "theme": "{{主题}}",
  "project_dir": "{{项目目录}}",
  "spec": {
    "duration_seconds": 40,
    "shot_count": 15,
    "scene_count": 6,
    "aspect": "16:9",
    "resolution": "1080p"
  },
  "models": {
    "image_chain": ["Midjourney（定基调）", "Seedream（出人物）", "Nano Banana（锁一致性）"],
    "video": "Seedance 2.0",
    "selected_from": "生产包定稿组合 / 能力档案 active 主推组合"
  },
  "hard_constraints": {
    "prompt_verbatim": true,
    "no_rewrite_no_translate": true,
    "color_card_only_in_reference_binding": true,
    "no_sref_in_image_stage": true,
    "photography_master_is_text_block": true,
    "video_prompt_structure": ["视频基本参数", "参考绑定", "摄影母版", "禁止项", "画面描述", "收束与音频"],
    "character_reference_pairs": ["ROLE_SHEET_X 上下分区定妆板资产", "FACE_CLOSE_X 人脸特写"],
    "standard_frame_reference_count": 2,
    "prompt_language": "zh"
  },
  "generation_units": [
    {
      "id": "U01",
      "prompt_id": "C01",
      "duration_seconds": 15,
      "timecode": "0–15s",
      "first_frame": "STANDARD_FRAME_01",
      "scene_references": ["SCENE_REVERSE_01", "SCENE_REVERSE_02"],  // 可选：项目标注「不用反打」时为 []
      "character_references": ["ROLE_SHEET_A", "FACE_CLOSE_A", "ROLE_SHEET_B", "FACE_CLOSE_B"],
      "picks": 3,
      "max_retries": 1,
      "idempotency_key": "cfaf-{{项目短名}}-v1-U01"
    }
  ],
  "limits": {
    "generation_unit_count": 3,
    "picks_per_unit": 3,
    "max_total_generations": 9,
    "max_retries_per_unit": 1,
    "stop_on_limit": true
  },
  "idempotency_key_prefix": "cfaf-{{项目短名}}-v1",
  "upload_order": ["首帧", "COLOR_CARD_01", "〔可选〕SCENE_REVERSE_0X", "ROLE_SHEET_X + FACE_CLOSE_X 成对"],  // 跳过反打时删掉该项
  "backend_detail": {
    "backend": "libtv",
    "name": "LibTV Agent 托管",
    "actor": "LibTV 后端 Agent",
    "note": "需要平台连接、项目写权限与 confirmSpend",
    "execution_section": "见 libtv_handoff.md 的「执行后端与跑法」一节"
  },
  "degradation": {
    "libtv_unavailable": "--backend workbuddy 或 --backend external 重新打包，run_mode 保持 autopilot；用户点名 libtv 时先停下汇报，不静默换平台",
    "model_unavailable": "search_models 找同档位替代，重算生成条时长与条数并写回本清单",
    "reference_slots_insufficient": "优先保首帧 → 色卡 → ROLE_SHEET_X；FACE_CLOSE_X 给近景多的条",
    "no_multi_image": "用 SCENE_REVERSE_01（启用了可选反打）或 SCENE_MOOD_01（跳过反打）合成首帧承载空间信息，人物走 ROLE_SHEET_X 单张",
    "duration_cap_hit": "按时间码拆条并以上一条末帧接续，不拉长镜头",
    "auto_translation": "关闭自动翻译，要求逐字执行中文原文",
    "color_group_split": "停下提醒重新分组，不强行合并成一张灰卡",
    "audit_failed": "按首帧 → 提示词 → 统一调色 → 模型顺序修"
  },
  "libtv": {
    "recommended_path": "canvas_agent",
    "canvas": {
      "create_project": "create_project(name, idempotencyKey)",
      "upload": "upload_ticket + upload_complete → documents[].fileRef",
      "delegate": "run_agent(message, autoGenerate=true, idempotencyKey, documents)",
      "poll": "get_agent_status(runId / agentSession)",
      "approve": "resolve_agent_action(精确 actionId, confirmSpend)",
      "export": "export_readiness → export_video → task_status",
      "deliver": "prepare_project_delivery → get_web_operation_status",
      "stop": "stop_agent_run"
    },
    "agent_im_fallback": "upload_file.py → create_session.py 一条消息 → query_session.py 轮询 → download_results.py"
  },
  "acceptance": {
    "completion_requires": ["回读逐条素材", "实际导出的成片", "color_field_audit.py 通过"],
    "audit_command": "python3 scripts/color_field_audit.py <成片.mp4> --start 0 --end <时长> --out audit_report.json --csv audit_frames.csv",
    "attribution": "{{libtv Agent 生成 / WorkBuddy 生成 / 用户平台生成}}"
  },
  "source_files": ["提示词全集.md", "注意点全集.md", "000_先看这个-操作手册.md", "shot_list.csv", "generation_plan.json", "stage_state.json"]
}
```

### 字段填写规则

| 字段 | 从哪读 | 缺失时 |
|---|---|---|
| `execution_backend` | 命令行 `--backend`；默认 `libtv` | 不许按平台喜好静默改；libtv 不可用要写 `platform_status=unavailable` 与 `requires_fallback=true` |
| `execution_backend_name` / `execution_actor` | 后端字典 | 自动填 |
| `backend_detail` | 后端字典 + 交接包 §3.5 | 自动填 |
| `spec` | `generation_plan.json` + `shot_list.csv` | 从 `stage_state.json` 与总揽补；仍缺则标 `unknown` 并停止打包 |
| `models` | `model_plan.md` / `generation_plan.json` / 能力档案 | 用 `active` 主推组合，写进 `selected_from` |
| `generation_units` | `generation_plan.json` 的生成条 + `shot_list.csv` 的参考图 ID | 缺任一条即停止打包，不臆造 |
| `limits` | 命令行 `--picks-per-unit` / `--max-retries` | 3 / 1，`stop_on_limit=true` 不可改 |
| `upload_order` | 固定值 | 不允许按平台喜好重排 |
| `source_files` | 项目目录实存文件 | 缺文件要列出并警告，**不静默略过** |

---

## 三、`libtv_assets_manifest.json` 骨架

```json
{
  "theme": "{{主题}}",
  "assets": [
    {
      "id": "ROLE_SHEET_A",
      "kind": "人物上下分区定妆板资产",
      "local_path": "assets/ROLE_SHEET_A.png",
      "used_in": ["A09 标准首帧", "C01–C03 参考绑定"],
      "upload": true,
      "prompt_id": "B02"
    },
    {
      "id": "FACE_CLOSE_A",
      "kind": "人脸特写（唯一允许进视频的过程件）",
      "local_path": "assets/FACE_CLOSE_A.png",
      "used_in": ["B02 拼板输入", "C01–C03 参考绑定"],
      "upload": true,
      "prompt_id": "B-Z1"
    },
    {
      "id": "PHOTO_MASTER_01",
      "kind": "摄影母版文字块",
      "local_path": null,
      "used_in": ["C01–C03 摄影母版"],
      "upload": false,
      "prompt_id": "A10"
    }
  ],
  "notes": [
    "本地路径为相对项目目录的占位，实际图片由 A 段提示词生成后补齐",
    "upload=false 的项一律不占参考位；摄影母版不是图片"
  ]
}
```

> 若项目里已有真实图片文件，脚本按文件名匹配 `local_path` 并标 `exists=true`；未生成的资产保留 `exists=false`，**不虚构图片、不代替用户生成**。
