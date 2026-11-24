# 双运行通道与自动托管协议（v4.0）

> **本文件是 `guided` / `autopilot` 双运行通道的唯一权威**，配合 `SKILL.md` 第 19 条与 `staged-delivery.md` §8 使用。
> 它只规定「谁来放行阶段闸门」和「把生产包交给哪个执行后端」，**不改任何色场规则、固定风格、阶段产出、提示词口径与验收标准**。
> **v5.0 边界**：7 大步小白引导只属于 `guided` 默认模式；用户显式授权 `autopilot` 时**跳过 7 步引导、不弹选择框**，仍按本文件连续产出 S0–S5 并交给执行后端。两条通道的硬约束与提示词逐字相同，差别只在「谁放行」。
> **v4.0 关键变化**：`autopilot` 与 libtv 解耦。libtv 是**优先但不唯一**的后端；libtv 未连接时换 `workbuddy` / `external`，两条通道照样都能跑到 S7。**两条通道必须都跑通**，离线自检 `scripts/verify_channels.py`。

---

## 1. 为什么是两条通道，而不是把流程改成全自动

这个 skill 的主用途是**一步一步引导人把片子做出来**：用户要看得懂每一步、知道粘哪里、传哪些图、选几秒、怎么挑片，而且每一步都有反悔的机会。这套闸门是产品特性，不是效率缺陷。

但同一套 S0–S5 文档本身已经是一份**完整、机器可执行的生产包**：提示词全集、注意点全集、分镜表、生成条规划、上传序列、摄影母版、色卡边界全都在。把它整体交给一个有生成与剪辑能力的 Agent，就不需要人逐批点确认了。

所以：

| | `guided` | `autopilot` |
|---|---|---|
| 定位 | **默认主模式**，给人用 | 显式授权后的托管模式，给执行后端用 |
| 产物 | 完全相同（S0–S7 同一套文档与规则） | 完全相同 |
| 差异 | 人来放行闸门、逐批确认 | 规则校验放行闸门、整包委托 |
| 执行后端 | 用户自己的平台（默认通道 B） | `libtv` / `workbuddy` / `external` 三选一 |
| 关系 | 失败时可回退到这里 | 从这里派生，不替换它 |

**libtv 不可用 ≠ autopilot 跑不通**：换后端即可，不需要回退 `guided`。只有「用户明确点名 libtv 且平台不可用」时才停下告知并给出两种可用后端，不静默换平台。

**永不因为「能自动」就砍掉引导块、使用指引或暂停边界。**

---

## 2. 授权判定（可执行规则）

```
if 用户说了全自动意图（全自动 / 交给…一次做完 / 不用问我 / 直接出成片）
   AND 用户已给出主题（或已有可复用的项目生产包）
then run_mode = autopilot
     execution_backend = 用户点名的平台（libtv）→ libtv
                       | 用户说「用我自己的平台」  → external
                       | 未点名                    → libtv（不可用时按 §5.3 降级，不回退 guided）
else run_mode = guided
```

> **v4.0 起授权条件不再要求点名 libtv**：「全自动出成片」本身就是预授权。平台只是执行后端的选择，不是授权成立的前提。

| 用户说 | 判定 | 说明 |
|---|---|---|
| 「一步步来」「先出总揽」「确认通过」「继续」 | `guided` | 正常闸门 |
| 只给主题、沉默、「先看看」「只交文档」 | `guided` | **沉默不是预授权** |
| 「全部做完」「一次性出」（无全自动意图） | `guided` | 仅允许连续产出 S0–S5 文档，S6 仍逐批确认 |
| 「交给 libtv 全自动」 | `autopilot` + `backend=libtv` | 见 §4 |
| 「全自动出成片」（未点名平台） | `autopilot` + `backend=libtv`（不可用则按 §5.3 降级） | 不因未点名平台就退回 `guided` |
| 「全自动，用我自己的平台批量」 | `autopilot` + `backend=external` | 交接包作批处理清单 |
| 「全自动，就在当前会话里跑」 | `autopilot` + `backend=workbuddy` | 按清单逐条调用本会话生成能力 |
| 「切回手动 / 还是我来吧 / 停下来」 | 立即回 `guided` | 停止远端运行、保留全部产物，从当前阶段继续 |

`run_mode` 与 `execution_backend` 写进 `stage_state.json`，由 `stage_state.py --run-mode guided|autopilot --backend libtv|workbuddy|external` 维护。**跨会话续做先读 `status`，不靠上一轮的记忆猜模式或后端。**

---

## 3. 阶段闸门换算

| 阶段 | `guided` 放行 | `autopilot` 放行（写 `autopilot_log`） |
|---|---|---|
| S0 | 用户确认总揽 | 五段结构 / 输入模式 / `ROLE_CHARTER_X` / 色场占比 / 光影摄影两节齐全 |
| S1 | 用户选模型 | 采用生产包定稿组合或能力档案 `active` 主推组合；**不主动问** |
| S2 | 用户确认规划 | `generation_plan.json` 每条 ≤ 模型上限、无未处理 WARN |
| S3 | 用户回传小样 | A08 成品色卡提示词 / A10 一段式摄影母版 / 六块模板 + 逐镜块 / 人物两类成对齐全 |
| S4 | 用户确认分镜 | `shot_list.csv` 含生成条 ID、模型上限、beat，总时长对得上 |
| S5 | 用户抽查提示词 | 六块齐全、摄影母版逐字一致、色卡在【参考绑定】为第二处使用、代码块无英文整句 |
| S6 | 每批 ≤5 镜逐批确认 | 整包交给 `execution_backend`，按 manifest 数量上限跑完全部生成条 |
| S7 | 用户剪辑 / LUT / 验收 | 选定后端拼接 + 统一 LUT + 导出；**回读产物后**再跑 `color_field_audit.py` |

自动放行必须留痕：阶段、时间、校验项、结果、依据文件。`advance --note` 记 **「自动门禁通过」**，**不得写成「用户确认通过」**——托管不等于替用户做了美学决定。

---

## 4. autopilot 执行总流程

```
① 判授权 → 写 run_mode=autopilot + execution_backend
② 连续产出 S0–S5 全套文档（逐阶段自动门禁 + autopilot_log）
③ python3 scripts/build_handoff.py --project <目录> --backend <libtv|workbuddy|external>
      → libtv_handoff.md（给后端的指令正文 + 按后端的跑法）
      → libtv_manifest.json（机器可读字段，含 execution_backend）
      → libtv_assets_manifest.json（参考图清单）
④ 用户过目 manifest 的数量上限（生成条数 × 挑片次数），明确授权本次生成
⑤ 整包交给选定后端（libtv：§6 Canvas / §7 agent-im；workbuddy / external：交接包 §3.5）
⑥ 轮询 / 逐条执行 + 回答追问 + 盯住重跑次数；超上限即停
⑦ 回读素材与实际导出成片 → color_field_audit.py 验收 → 交付
```

第 ④ 步不可省：任何后端执行都会产生实际费用（libtv 平台侧还要求写权限与 `confirmSpend`）。**本 skill 自身永远不直接调用产生费用的生成能力**，只打包、留痕、委托、验收。
**第 ③ 步的 `--backend` 是打通两条通道的关键**：libtv 未连接时用 `--backend workbuddy` 或 `--backend external` 重新打包，`run_mode` 保持 `autopilot`，不需要回退 `guided`。

---

## 5. 交接包规范

| 文件 | 给谁看 | 内容 |
|---|---|---|
| `libtv_handoff.md` | 选定后端（自然语言） | 首段硬约束 + 任务目标 + 完整执行顺序 + **§3.5 按后端的跑法** + 逐条生成条索引 + 剪辑与导出要求 + 完成标准 |
| `libtv_manifest.json` | 编排 / 校验脚本（机器） | `run_mode`、**`execution_backend`**、`platform_status`、`requires_fallback`、`input_mode`、模型组合、生成条列表、数量上限、幂等键前缀、上传序列、降级表、验收命令 |
| `libtv_assets_manifest.json` | 上传步骤 | 每个资产 ID、本地路径、用途、是否上传、出现在哪一块 |

模板见 `assets/libtv-handoff-template.md`。打包命令：

```bash
python3 scripts/build_handoff.py --project <项目目录> --backend libtv
python3 scripts/build_handoff.py --project <项目目录> --backend workbuddy
python3 scripts/build_handoff.py --project <项目目录> --backend external --picks-per-unit 3 --max-retries 1
# libtv 未连接且用户点名了 libtv：如实标注，不静默换平台
python3 scripts/build_handoff.py --project <项目目录> --backend libtv --libtv-status unavailable
```

脚本**纯打包**：只读项目文件、只写上述三份文本，**不生成任何图片或视频、不联网、不调用任何生成 API**。

### 5.1 `libtv_handoff.md` 首段必须逐字包含的五条硬约束

```
1. 本包为已定稿生产包。所有提示词必须逐字执行，不得重写、扩写、翻译、精简或自行重新拆分镜与写 prompt。
2. COLOR_CARD_01（A08 成品色卡出图提示词生成的 12 色色卡；归纳 meta 指令不进包）在 A01–A0N 场景基调图 / 可选反打同传取色彩方案、在每条视频提示词的【参考绑定】上传；A00 母版 / 标准首帧 / 人物资产不挂色卡，全阶段不写 --sref。
3. PHOTO_MASTER_01 摄影母版是中文文字块，v4.3 起为**一段连续专业摄影描述**（只写跨镜头统一项、不含具体焦段；焦段与 T 光圈下放到逐镜块）；它不是图片，不生成、不上传、不占参考位；每条生成条逐字复用同一份。C 段【画面描述】= 全局设定段 +【镜头N | 时间码 | 镜头名】逐镜块，焦段与 T 光圈只在逐镜块给。
4. 人物参考只有两类成对：ROLE_SHEET_X 上下分区定妆板资产（v5.2 逐字模板）+ FACE_CLOSE_X 人脸特写（从新版上方左格裁出）；每位出镜角色一组，不挂四宫格 / 定妆基准 / 四格板 / 单独三视图 / 服装放大图。**v5.1 人物层级**：主角是唯一被表现、唯一有身份资产的人物；后景焦外可有 1–3 个不具名背景人影，不占参考位、不给正脸与特写、不与主角同焦平面、不产生独立动作线，只写进逐镜块的背景层与环境动态；全片禁用大远景 / 远景 / 大全景，景别只在全景及更近档位之间拉开。
5. 风格固定：本片为「中式古装田园 / 暖调统一色场」类短片。暖调色场、斜后侧主光、暖象牙—蜜桃肤色、奶油金高光与柔焦质感是风格常量；换主题只换主题、人物、物件与剧情，不得换成别的视觉风格，不得放宽三条铁律。
```

**为什么第 1 条最重要**：libtv 后端 Agent 的默认行为是「理解需求 → 自己拆剧本 / 分镜 → 自己写 prompt」。若交接包没把这条钉死，它会把我们从 S0 到 S5 精心锁定的色场、光位、时间码、六块结构全部重写成通用描述，成片会变成另一支片子。这不是模型能力问题，是交接丢失约束。

### 5.2 `libtv_manifest.json` 必填字段

| 字段 | 含义 | 缺省 |
|---|---|---|
| `run_mode` / `input_mode` | 运行通道 / 输入模式 | `autopilot` / `zero` |
| **`execution_backend`** | **谁跑 S6/S7：`libtv` / `workbuddy` / `external`** | **`libtv`** |
| **`platform_status`** / **`requires_fallback`** | libtv 连接状态（调用方传入）/ 是否需要换后端 | `unknown` / `false` |
| `backend_detail` | 后端名称、执行者、注意事项、跑法章节索引 | 自动填 |
| `image_models` / `video_model` | 定稿模型组合 | 来自 `model_plan.md` 或能力档案 |
| `generation_units` | 生成条数组（ID、时长、时间码、首帧、参考图 ID） | 来自 `generation_plan.json` + `shot_list.csv` |
| `picks_per_unit` | 每条挑片生成次数 | 3 |
| `max_total_generations` | = 条数 × 挑片次数，**硬上限** | 自动算 |
| `max_retries_per_unit` | 单条最多重跑 | 1 |
| `stop_on_limit` | 超限即停 | `true` |
| `idempotency_key_prefix` | 稳定幂等键前缀 | `cfaf-<项目短名>-v1` |
| `upload_order` | 首帧 → 色卡 → 场景版 → 人物两类成对 | 固定 |
| `degradation` | 模型 / 参考位 / 时长 / 语言降级表 | §9 |
| `acceptance` | 完成判定与验收命令 | §11 |

---

## 5.3 三种执行后端与降级（v4.0 · 两条通道都能跑通的关键）

| 后端 | 谁执行 | 交接包形态 | 完成判定 | 产物归属 |
|---|---|---|---|---|
| `libtv` （优先） | LibTV 后端 Agent | 整包指令 + `run_agent(autoGenerate=true)` / agent-im 会话 | `get_agent_status` 回读 artifacts + 实际导出成片 + 验收脚本 | 「libtv Agent 生成」 |
| `workbuddy` | 当前 WorkBuddy 会话按清单逐条调用生成能力 | 整包指令 + 逐条执行顺序 + QA 表 | 逐条结果落盘 + 成片 + 验收脚本 | 「WorkBuddy 生成」 |
| `external` | 用户 / 用户侧脚本在自己的平台批量粘贴 | **批处理清单**：逐条「粘提示词 → 传参考 → 选档位 → 生成 N 次挑 1 → 记录」 | 用户回传逐条结果与成片 + 验收脚本 | 「用户平台生成」 |

**降级规则（写进 manifest 的 `degradation`）**

| 情况 | 动作 | 不许做 |
|---|---|---|
| libtv 未连接 / 不可用，用户未点名平台 | `--backend workbuddy` 或 `--backend external` 重新打包，`run_mode` 仍是 `autopilot`，头部写明降级原因 | 不判成「autopilot 跑不通」、不默认回退 `guided` |
| 用户明确点名 libtv，但平台不可用 | 停下汇报，给出两个可用后端与重打包命令；`requires_fallback=true` | 不静默替用户换平台、不反复重试把任务打散 |
| 后端换了 | 只改 `execution_backend` 与交接包 §3.5，**S0–S5 生产包、提示词、色场规则一个字不改** | 不重写提示词、不重新拆分镜 |
| 后端执行失败 / 超上限 | 停止、留痕、保留产物；必要时 `stage_state.py set --run-mode guided` 从 S5 人工接手 | 不删用户文件、不静默重跑 |

**三条通道无关的恒定项**：三条铁律与固定风格、12 色色卡两处使用（A 段取色 + C 段【参考绑定】）、一段式摄影母版（焦段下放逐镜）、视频六块结构 + 逐镜块、人物两类成对、标准首帧 2 参考、生成次数上限、验收脚本。**换后端只换「谁按包执行」，不换包的内容。**

`python3 scripts/verify_channels.py` 会离线把 `guided` 与 `autopilot` 三条后端各跑一遍 S0→S7 状态机与交接包生成，断言两条通道都能跑通；不联网、不生成任何媒体。

---

## 6. 接法 A · Canvas Agent（仅 `libtv` 后端；结构化、可控，推荐）

适用于需要精确控制项目、参考图、时间线与导出的场景。全部为 MCP 工具，参数以当日 schema 为准。

### 6.1 工具序列

```
create_project(name, idempotencyKey)                       → projectId / projectContext
upload_ticket + upload_complete（或 upload_media）         → documents[].fileRef
    上传：libtv_handoff.md、libtv_manifest.json、参考图清单里的图片/首帧
run_agent(
    message        = 交接包首段指令（见 §7.2 的中文消息模板），
    autoGenerate   = true,          ← 明确授权媒体制作，需 task-write 权限
    idempotencyKey = <稳定键>,
    projectId / projectContext,
    documents      = [交接包 fileRef],
    skills         = 可选模板（服务端解析，最多 1 个）
)                                                        → runId（不是 media task_id）
get_agent_status(runId / agentSession)                    → 轮询状态、pending question、artifacts
answer_agent_questions / resolve_agent_action             → 回答追问 / 按精确 actionId 明确 confirmSpend
steer_agent_run                                          → 运行中纠偏（不新开运行）
export_readiness → export_video → task_status             → 拼接、统一 LUT、导出成片
prepare_project_delivery → get_web_operation_status       → 交付清单
stop_agent_run                                           → 失败 / 超限 / 用户喊停
```

### 6.2 七条平台侧硬约束（来自 `get_capabilities` 的 `agent-delegation`）

1. 新运行要求**稳定幂等键**与项目写权限；`autoGenerate=true` 才允许媒体制作。
2. 运行状态用**精确 `runId` / `agentSession`** 回读，别用派发回执或进度卡当结果。
3. **不以派发回执或进度卡证明最终媒体已验收**；必须有 artifacts + 实际成片。
4. 改编原稿 / 生产包要用**项目上传完成后的 `documents.fileRef`**；VFS 选区不能替代原稿附件。
5. 正式审批、单集恢复与 Agent 交接用 `pendingActions` 里的**精确 `actionId`**；允许执行必须显式 `confirmSpend`，普通问答不算批准。
6. Web 创作模式与当前节点绑定会话，节点与文件引用由授权项目回读；换节点 / 换模型需新会话，不能复用 `runId`。
7. `run_agent` 是**可选**委托入口；环境未开放时走接法 B，不要反复重试把任务打散。

### 6.3 幂等键

格式 `cfaf-<项目短名>-v1-<生成条ID>`，同一键重发**只恢复原运行、不产生新任务**。因此「重跑一条」必须换键并记进 `autopilot_log`；自动重试最多 `max_retries_per_unit` 次，且每次都要留痕。

### 6.4 轮询与问答

- `get_agent_status` 按平台建议间隔轮询；活动运行持有单写锁，**回读之后**再写画布。
- 出现 `pending question` 用 `answer_agent_questions` 回答；回答内容只做事实澄清，**不重写提示词、不新增美术要求**。
- 运行中用 `steer_agent_run` 纠偏；不新开 `run_agent`，否则会产生第二个并行运行。

### 6.5 完成判定

同时满足才算完成：① `get_agent_status` 回读为终态且有 artifacts；② `export_video` / `task_status` 给出实际成片；③ 成片跑过 `color_field_audit.py`。三者缺一，只能报「运行中」或「未验收」。

---

## 7. 接法 B · agent-im 会话（仅 `libtv` 后端；轻量、一句话托管）

适用于只想把整包丢给后端 Agent、不操作画布的场景。使用 `libtv-skill` 的脚本：

```bash
export LIBTV_ACCESS_KEY="..."
python3 {libtv-skill}/scripts/upload_file.py <项目目录>/libtv_handoff.md     → oss_url_1
python3 {libtv-skill}/scripts/upload_file.py <项目目录>/libtv_manifest.json  → oss_url_2
python3 {libtv-skill}/scripts/create_session.py "请按附件生产包逐字执行……生产包：{oss_url_1} 清单：{oss_url_2}"
python3 {libtv-skill}/scripts/query_session.py SESSION_ID --after-seq 0      # 每 8 秒增量轮询
python3 {libtv-skill}/scripts/download_results.py SESSION_ID --output-dir <项目目录>/libtv_results --prefix final
```

### 7.1 中文消息模板（整段复制，只换 URL）

```
请按附件《统一色场短片生产包》完整执行，一次做到成片，中途不需要向我逐条确认。
生产包内的提示词、分镜表、生成条规划、上传序列、摄影母版与色卡边界均已定稿，必须逐字执行：不要重写、扩写、翻译提示词，不要自行重新拆分镜或另写镜头描述。
依次完成：按 A 段提示词生成全部参考资产 → 归纳 12 色色卡 → 生成 2 参考标准首帧 → 按 C 段六块结构逐条生成全部视频生成条（每条按清单上传首帧、色卡、场景反打（可选）与人物两类成对参考）→ 按分镜表时间码拼接、全片统一加一次柔光与统一 LUT → 导出 16:9 成片。
色卡在 A 段场景图取色彩方案、在每条视频提示词的【参考绑定】为第二处使用；摄影母版是文字块、不生成图片、不上传；人物只参考 ROLE_SHEET_X 与 FACE_CLOSE_X 两类。
完成后请给出：成片链接、每条生成条的结果、实际生成次数、与生产包不一致之处（如有）。
生产包：{oss_url_1}　机器清单：{oss_url_2}
```

### 7.2 与 libtv-skill「用户侧只做传话」原则的关系

`libtv-skill` 明确要求用户侧 Agent **不要替后端扩写 / 润色 / 翻译 prompt、不要自行拆任务、不要自编镜头描述**。这条原则针对的是「用户随口一句话，用户侧自作主张改写成自编 prompt」的情形。

autopilot 不违反它，前提是分清两件事：

| | 性质 | 允许 |
|---|---|---|
| 交接包 | **用户已确认的 S0–S5 生产资产**，属于用户提供的文件 | 按「用户提供参考文件」场景上传，原样传过去 |
| 消息正文 | 只说明「按附件执行」+ 上传后的 URL | 不把提示词正文抄进消息、不改写、不拆成 N 条请求 |

**禁止**：把 6 条生成条拆成 6 次 `create_session` 分别发；把六块提示词改写成自己的话；在消息里补「超写实、电影感、8K」之类自编描述；后端 Agent 追问时擅自改色场规则。若后端 Agent 仍坚持自由创作，改用接法 A，用 `documents.fileRef` + `run_agent` 把生产包作为原稿附件绑定。

---

## 8. 自动模式下一条都不放宽的硬约束

| # | 约束 | 自动模式常见破口 |
|---|---|---|
| 1 | 成品色卡出图提示词（12 个 HEX 写死、纯文字出图、必须先于 A01 完成）；生成的色卡供 A 段场景图取色彩方案 + C 段【参考绑定】两处使用 | 平台把色卡当风格垫图全局套用；把 meta 指令当成出图提示词 |
| 2 | 场景基调图 / 可选反打同传色卡取色彩方案（正文限定只取 12 色）；A00 母版 / 首帧 / 人物资产不挂色卡；全阶段不写 `--sref` | 为「保险」把整张色卡当风格垫图、或用 `--sref` 继承方格版式，六个场景被压成一个颜色 |
| 3 | `PHOTO_MASTER_01` 是文字块，逐字复用、不生成图、不上传 | 被误当成一张参考图上传占位 |
| 4 | 视频提示词六块结构齐全，【禁止项】内部全正向句 | Agent 自动精简成一段自然语言描述 |
| 5 | 人物参考两类成对，参考位不足优先保 `ROLE_SHEET_X` | 把过程图一股脑全传，串脸 |
| 6 | 占比 / 九宫格 / 五级明度由色场方案表与摄影母版写死，不从色卡取 | 按色卡面积自动分配占比 |
| 7 | 提示词正文简体中文，仅平台参数 / 资产 ID / 器材型号 / 模型名保留原文 | 平台自动翻译成英文再生成 |
| 8 | 标准首帧 2 参考、不带色卡；第 2 张场景参考按项目是否启用可选反打取 `SCENE_REVERSE_01` 或 `SCENE_MOOD_01` | Agent 自作主张补挂色卡、或凭空补一张不存在的 `SCENE_REVERSE_0X` |
| 9 | 柔光与光晕全片统一加一次，不逐镜叠加 | 每条生成条各加一次，成片越来越雾 |
| 10 | 生成条时长 ≤ 模型单次上限 | 长条被平台截断，S06 丢镜头 |
| 11 | 固定「中式古装田园 / 暖调统一色场」风格 | 后端 Agent 自动「优化」成冷调都市或通用电影感 |

---

## 9. 降级表（写进 manifest，执行时留痕）

| 情况 | 降级动作 | 不许做 |
|---|---|---|
| libtv 未连接 / 不可用 | `--backend workbuddy` 或 `--backend external` 重新打包，`run_mode` 保持 `autopilot` | 不回退 `guided`、不静默换平台（用户点名 libtv 时先停下汇报） |
| 定稿视频模型在该平台不可用 | 用 `search_models` 找同档位替代，按 `model_adapter.py` 重算生成条时长与条数，写回 manifest | 不硬套旧时长、不臆造参数 |
| 参考位少于清单 | 优先保首帧 → 色卡 → `ROLE_SHEET_X`；`FACE_CLOSE_X` 优先给近景多的条；`FABRIC_DETAIL_X` 直接不出 | 不删色卡、不把摄影母版传上去占位 |
| 平台不支持多图同传 | 用 `SCENE_REVERSE_01`（项目启用了可选反打）或 `SCENE_MOOD_01`（跳过反打）合成一张首帧承载空间信息，人物走 `ROLE_SHEET_X` 单张 | 不逐镜独立文生视频 |
| 单次时长不够装一条 | 按时间码拆成两条、以上一条末帧接续；接缝不改色场 | 不把镜头拉长、不改 beat |
| 平台自动翻译提示词 | 关掉自动翻译 / 改回中文原文；实在不行在交接包附中文原文并要求逐字执行 | 不默认接受英文译文 |
| 按归纳 meta 指令分析参考素材时明显分两组色温 | **停下提醒重新分组**，不强行合并 | 不硬凑一张灰卡 |
| 验收不达标 | 按「首帧 → 提示词 → 统一调色 → 模型」顺序修 | 不先换模型、不静默重跑全部 |

---

## 10. 数量、成本与停止

- `max_total_generations = generation_units × picks_per_unit`，`max_retries_per_unit = 1`，`stop_on_limit = true`。
- 超上限、平台报错、用户喊停 → `stop_agent_run`（接法 A）或停止轮询并汇报（接法 B），**保留全部产物与日志**。
- 不静默重跑、不扩大批次、不因为「看起来快好了」追加次数。
- 每次生成都要能回答：跑了几条、挑了哪条、重跑过几次、有没有超上限。

---

## 11. 验收与产物归属

```bash
python3 scripts/color_field_audit.py <成片.mp4> --start 0 --end <成片时长> --out audit_report.json --csv audit_frames.csv
```

- 只测成片段，排除讲解 / UI；报告区分「实测数值」与「人工检查结论」。
- 产物按 `execution_backend` 标注 **「libtv Agent 生成」/「WorkBuddy 生成」/「用户平台生成」**；WorkBuddy 侧的产出是生产包、门禁记录与验收报告，**不把任何后端的成片说成本 skill 生成**。
- 交付给用户：成片链接 / 本地文件、`libtv_manifest.json` 实际执行记录（含偏差）、`audit_report.json/md`、以及 `autopilot_log`。

---

## 12. 失败回退 `guided`

```
停止远端运行 → 保留全部产物 → 写 autopilot_log（失败阶段 / 原因 / 已生成条数）
→ stage_state.py set --run-mode guided
→ 从 S5（提示词与用法）继续人工逐批生成；已成功的生成条不必重跑
```

**不删除任何用户文件**，回退只清状态记录。用户之后再说「继续全自动」时，重新走 §2 授权判定，不沿用上一次的预授权。
> **后端切换不属于失败回退**：libtv 不可用时换 `workbuddy` / `external` 仍留在 `autopilot`，只有后端本身执行失败才走本节回退 `guided`。

---

## 13. 自检清单

1. `run_mode` 是否由用户**显式授权**后才设为 `autopilot`？沉默 / 「全部做完」有没有被误判？
2. 两条通道的 S0–S5 产出是否完全相同，只是放行方式不同？
3. 交接包首段四条硬约束（逐字执行 / 色卡边界 / 摄影母版 / 人物两类）是否齐全？
4. `libtv_manifest.json` 的数量上限、幂等键前缀、降级表、验收命令是否都填了？
5. 是否**没有**把生产包拆成多条独立请求、没有在消息里自编 prompt？
6. `documents.fileRef` 是否来自项目上传完成后的票据（而非 VFS 选区）？
7. `autoGenerate=true` 是否对应用户本次明确授权与项目写权限？
8. 完成是否以**回读 artifacts + 实际导出成片 + 验收脚本**三者为准，而不是派发回执？
9. 超上限 / 失败是否停下、留痕、回退 `guided`，且没删用户文件？
10. 产物归属是否按 `execution_backend` 写清，没把任何后端的成片冒称本 skill 产出？
11. **两条通道是否都跑到 S7**：`guided` 逐阶段放行、`autopilot` 自动门禁放行，且 `verify_channels.py` 全绿？
12. libtv 不可用时是否换后端继续跑（而非误判 autopilot 不可用、误回退 guided）？
