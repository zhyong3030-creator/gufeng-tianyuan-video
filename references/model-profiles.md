# 模型能力档案（含硬约束与来源）

> **v3.3 角色参考包变更**：第一张图必须是 `FACE_QUAD_01` 面部特写四宫格（同一图四等分：正 / 左 90° / 右 90° / 背 180°，全为头部特写），后面每张定妆图按 `character-sheet-spec.md` §4.4 对应性矩阵指回它；全包统一纯色暖灰 `#C6BCB1` + 三点式 5500K 中性光 + 105mm（头）/85mm+（身）+ 低密度 Tiffen 黑柔 + 无现代浓妆；另产朝向三视图、四格定妆板与六张单图，定妆包验收 13 项。出图前先过 `character-design-aesthetics.md` 设计自检 6 问与 `costume-design.md` 服装自检 6 问。本文件涉及角色参考包的具体表述以 `character-sheet-spec.md` 为准。

> 数据文件：`assets/model_profiles.json`。脚本 `model_adapter.py` 直接读取它，改能力只改 JSON，不改脚本。
> 检索日期 **2026-11-05**。除官方文档外多为第三方汇总，**版本、时长上限、参考图数量、参数与可用状态以平台当日说明为准**，批量前必须跑小样。
> 标注 `verify` 的先验证、`deprecated` 的不进推荐。

## 1. 视频模型：单次时长硬约束（会改变整体分镜规划）

| 模型 | 单次最短–最长 | 可选档位 | 参考输入 | 原生音频 | 状态 | 对示例 35 秒成片的影响（按 `T` 重算） |
|---|---|---|---|---|---|---|
| **Seedance 2.0** | 4–**15s** | 4/5/10/15 | ~15 个（约 9 图+3 视频+3 音频），`@` 指定职责 | 有 | active | 至少 3 个生成条；一条 15s 可吃掉约 4–5 个 2–4s 镜头，即一个完整叙事段落 |
| **Seedance 2.5** | 4–**30s** | 4–30 滑杆 | ~50 个（约 30 图+10 视频+10 音频）；专用首尾帧、3D 白模布局、返回末帧、局部重绘 | 有，立体声 | active | 可压到 2 条（30s+5s）；一条能吃 2–3 个段落，跨生成跳色风险最低；必须写时间码显式声明切镜 |
| **Kling 3.0** | 3–**15s** | 5/10/15 | 多图参考；15s 内约 6 个 labeled shots | 可选 | active | 约 3 条；多镜模式一次生成一整段 |
| **Kling 4.0** | ~4–**30s** | 5/10/15/30 | 同可灵系 | 有 | verify | 若 30s 档可用 → 2 条；未验证前按 15s 规划，避免超承诺 |
| **Veo 3.1** | 4–**8s** | 4/6/8 | 1–2 张图 / Ingredients；角色外观写进正文 | 有，含口型 | active | **至少 5 条**；每条 8s 内用时间码排 3 个短镜头；生成次数最多、跨条一致性风险最高 |
| **Sora 2 Pro** | 4–**20/25s** | 4/8/12/20/25 | 单图 + storyboard | 始终有 | **deprecated** | Web/App 2026-04-26 停服、API 2026-09-24 终止；不进入推荐 |
| **Runway Gen-4.5** | **5 或 10s** | 5/10 | 参考图 + 独立运镜控制 | 无 | active | 约 4 条；**不支持负向词**，只写正向画面 |
| **Wan 3.0 / 2.x** | 2–**30s**（2.2 约 3–8s） | 2/5/10/15/30 | 首尾帧 + 参数，可本地部署 | 可选 | active | 低成本长草稿；先用整条 30s 验证节奏，再把段落交主力精修 |
| **海螺 02 / 2.3** | ~6–**10s** | 6/10 | 单图 | 无 | active | 1080p 约 6s、768p 约 10s，二者互斥；约 6 条；只做近景 |
| **PixVerse V6 / Vidu Q3** | ~1–**15/16s** | 5/8/10/15 | 单图或首尾帧 | 可选 | verify | 只作节奏草稿，终版换主力模型 |

补充约束（投放前复核）：

- Seedance 2.0 在**豆包 App 常锁 5s/10s 预设**，完整 4–15s 只在即梦/Dreamina 网页与火山控制台；不要向 App 用户承诺 15s。
- Veo 3.1 的 Extend 每次加约 7s、可到 ~148s，但**仅 720p** 且 4–5 次后画质下降；本片不用 Extend。
- Kling 付费档 extend 可到约 3 分钟，但超过 2 分钟漂移明显；本片不用。
- 原生音频不是选型依据：本片无对白，环境声与配乐后期加；带音频的模型反而要显式写「无对白」。

## 2. 图像模型：参考图与写法约束

| 模型 | 最大参考图 | 提示词形态 | 负向词 | 关键能力 | 状态 |
|---|---|---|---|---|---|
| **Nano Banana 2 / Pro** | 14（约 10 物件 + 4 角色） | 对话式导演 brief | **无负向字段**，全改正向句 | 角色系列一致性、4K、对话式局部改图、Google 检索接地；**一致性层首选**：三视图 / 四格板 / 场景正反打 / 标准首帧 | active |
| **GPT Image 2 / 2.5** | 10（按 index 引用） | 分段 / JSON 结构化 | 正文排除清单 | 复杂空间指令、文字渲染、编辑保真；可作一致性层备选 | active |
| **Seedream 5.0 Pro / Lite + 即梦** | 10–14 | 中文结构化，`[变量]` 模板 | 正文排除清单 | 中式场景织物、批量变体、九宫格故事板；**人物资产层首选**：人脸四宫格 / 面部单图 / 中国风人物改图；与 Seedance 同生态 | active |
| **Midjourney V8.2 + Edit Model** | 4 | 英文关键词串 + 参数行 | `--no`（版本需确认） | **视觉基调层首选**：视觉母版 / 场景基调 / 服装基调 / 质感与柔焦探索；一致性弱，不能承担角色包与 ≥6 图同传 | verify |
| **FLUX.2 / [pro]** | 1 | 英文长句自然语言 | 独立字段 | photoreal 材质与色准、品牌一致性 | active |
| **SDXL / Qwen-Image + ComfyUI** | 0（走 IP-Adapter / LoRA） | tag 串 + 权重语法 | 独立字段 + 参数 | 本地自控、LoRA 锁角色、大批量 | active |

> Midjourney 旧版 `--cref` / `--oref` / `--cw` / `--ow` 只对 V6/V7 有效；V8 起改用指令式 Edit Model。**版本必须现场确认**，参数行只作示意。
>
> **多图像模型分工（v3.4 / v4.1 补注）**：当用户同时给了 Midjourney / Seedream / Nano Banana 这类组合，按「定基调 / 出人物 / 锁一致性」三段接力，不要平均分活。判据与冲突解法见 `model-selection.md` 4.1；核心是**基调模型（4 参考位、一致性弱、多为 `verify`）只出母版 / 场景基调 / 服装基调，标准首帧与三视图必须由多图参考模型锁定**。场景反打 `SCENE_REVERSE_0X` 在 v4.1 起是**可选**步骤（用户自行选择用不用），不再是必出的锁一致性产物；不用时首帧第 2 张参考改用 `SCENE_MOOD_01`。MJ 原图不直接进视频上传序列。

### 2.1 v3.1：角色参考包与成片画面分离（能力库硬规则）

`model_profiles.json` 的 `character_sheet` 块是机器可读的全局规则，`model_adapter.py --stage character` 会直接读取它产出 `character_sheet_checklist.md` 与 `negative_character.txt`。

- **定妆基准图 `ROLE_REF_01`**：纯灰 `#B8B8B8` 无缝影棚 + 三点式 5500K 中性白还原光、全身正面、头到鞋完整、锁定 `body_ratio`、全画面清晰、真实皮肤与材质质感；**另外**必须产出正面 0° / 正侧 90° / 背面 180° 朝向三视图（`ROLE_REF_02`、`ROLE_REF_03`、`ROLE_TRIVIEW_01`）、四格定妆板 `ROLE_BOARD_01`（上 1/3 面部正+侧特写，下 2/3 左放大裁头服装图 + 右背面全身）与六张单图（`FACE_CLOSE_01/02`、`ROLE_OUTFIT_DETAIL_01`、`ROLE_REF_03`）。
- 色场占比、斜后侧主光、轮廓光、前景遮挡、留白、中浅景深、柔焦只进 `STANDARD_FRAME_01` / `SCENE_REF_*` / 逐镜提示词，**不进定妆图**。
- 每个图像模型在 JSON 里另存 `face_quad_example_prompt`（**第一张**）/ `character_example_prompt` / `triview_example_prompt` / `board_example_prompt` / `face_close_example_prompt` / `outfit_detail_example_prompt` 共六条**按该模型形态写好的完整实例**（对话式 / JSON / 中文分段 / 关键词串 / 英文长句 / tag 串）；每条派生实例末尾已叠加 `[面部统一规格]` `[对应性]` `[服装造型设计]` 段，`--stage character` 时替换掉原来的成片画面实例。`character_sheet` 块另存 `face_quad` / `face_spec` / `design_aesthetics` / `costume_design` / `correspondence` 五个 v3.3 子块。
- 定妆阶段不传色卡、不加 `--sref`、不写主色占比；负向词改用 `negative_for_character`（禁 `rim light / backlight / bokeh / cropped feet / props` 等；`flat frontal light` 在成片里是禁项，在定妆里是正向要求）。
- 规范与验收见 `references/character-sheet-spec.md`，可复制模板见 `assets/character-sheet-prompts.md`。

## 3. 两个必须分清的长度

| 概念 | 定义 | 是否随模型变 |
|---|---|---|
| **editorial shot（成片镜头）** | 最终剪出来的镜头，时长按用户给定区间（建议 **2–4 秒，可改**） | 否，属项目参数 |
| **generation unit（生成条）** | 一次提交给模型的生成，长度必须是允许的档位且 ≤ `max_duration_s` | **是**，由模型决定 |

**上限 ≠ 建议。** 30s 上限的价值是「把相邻短镜头合成一次生成、用时间码显式声明切镜」，减少跨生成换脸与跳色；不是把镜头拉成 30 秒长镜头。成片仍靠剪辑切回用户给定的单镜区间（建议 2–4 秒，可改）。

`model_adapter.py` 的计算顺序：

1. `T` / `镜数` / `段落数` 由用户在 S0 给定（建议值 35 秒 / 13–16 镜 / 5 段，均可改）；`每镜秒数 = T / 镜数`。
2. 每镜秒数 > `suggested_shot_s` → 加镜；> `max_duration_s` → 必须拆镜或换模型（报 WARN）。
3. `unit_seconds` 取 ≥ 每镜秒数的**最小允许档位**，并夹在 `[min_duration_s, max_duration_s]`。
4. `unit_seconds > 每镜秒数` 时，把相邻镜头并入同一生成条，输出 `timecoded_beats`；每个 beat 只写一个可见动作。
5. `生成条数 = ceil(成片时长 / unit_seconds)`，写进 `generation_plan.json` 与分镜表的「生成条 ID」列。

## 4. GitHub 高星提示词仓库：可复用的写法（已读原文）

| 仓库 | 量级 | 直接可复用的写法 |
|---|---|---|
| `f/prompts.chat` | ~16.8 万 | 「角色 + 任务 + 约束」的模板化，先定身份再定输出 |
| `dair-ai/Prompt-Engineering-Guide` | ~7.8 万 | 四要素 **Instruction / Context / Input Data / Output Indicator**；不必全有，但要有明确输出指示 |
| `freestylefly/awesome-gpt-image-2` | ~2.7 万 | **Prompt as Code**：把主体、光线、材质、布局拆成可组合原子字段；`[变量]` 占位；JSON 模板；每条模板配「避坑指南」 |
| `BaYue-SYJ/shuixian-prompts` | ~531 | 中文词库 6,011 条；`{参数}` 变量填空；按**媒介 / 风格 / 色调**分面检索；**每条配效果图**再抄结构 |
| `jnMetaCode/ai-shortfilm-prompts` | ~515 | **五段式** Core theme / Character & scene / Atmosphere & look / Camera rules / Storyboard；**per-second timecoded beats**；写真实机身镜头而非 `cinematic feel`；结尾留白；7 hard rules + 10 项自检；逐模型负向词机制表 |
| `LearnPrompt/awesome-seedance` | ~759 | 27 个模板 / 937+ 案例；**时间码切分**（每段时间码 + 一个动作 + 一条声音）；**stable token + 继承什么 / 不继承什么 / inherit-nothing-else**；故事板九宫格先出图再喂视频；timestamped QA 记录 |
| `OSideMedia/higgsfield-ai-prompt-skill` | ~832 | MCSLA 公式、DISCIPLINE 决策框架、**FAILURE-MODES 失败模式目录**（先诊断再重抽） |
| `qingshuiyixin2025/awesome-short-drama-skills` | 索引 | 短剧 skill 生态：`lanshu-awesome-ai-video-kit`(427)、`awesome-seedance-2.5-prompts-skills`(247，T2V/R2V/I2V 路线)、`ai-shortfilm-prompts`(485) |

由这些仓库归纳出的**五条硬写法**（写进本 skill 的每条提示词）：

1. **不写 praise adjectives**（epic / stunning / 电影感 / 高级感），改写可见物件、光位、比例、机身与镜头参数、物理反应。
2. **参考图给稳定编号**，分别写「继承什么 / 不继承什么 / 其余一律不继承」。
3. **时间码切分**：每个 beat 只一个可见动作 + 一条声音，切镜显式声明。
4. **负向词按模型机制变**：Veo 用纯名词且禁 `no/don't`；Runway 完全不支持，只写正向；Kling/Wan 只写具体瑕疵；Nano Banana/Seedance 无字段，改正向约束句。
5. **结尾留白**：不堆特效、不加对白、不加爆光，停在一个带主色的空气面。

## 5. 来源清单（JSON `sources` 字段同 ID）

S1 `github.com/jnMetaCode/ai-shortfilm-prompts` (README + methodology.md) · S2 `github.com/LearnPrompt/awesome-seedance` · S3 `github.com/freestylefly/awesome-gpt-image-2` · S4 `github.com/BaYue-SYJ/shuixian-prompts` · S5 `github.com/dair-ai/Prompt-Engineering-Guide` + `promptingguide.ai/introduction/elements` · S6 `github.com/f/prompts.chat` · S7 `github.com/OSideMedia/higgsfield-ai-prompt-skill` · S8 `github.com/qingshuiyixin2025/awesome-short-drama-skills` · S9 Midjourney 官方 Character/Omni Reference 文档 · S10 `tryseedance.ai/seedance-2-5` · S11 `seedance.tv` · S12 `kenerateai.com/blogs/best-text-to-video-models-2026` · S13 `invideo.io/blog/ai-video-length-limits` · S14 `golden-prompts.com/guides/best-ai-image-models-2026` · S15 `atlascloud.ai/blog/tips/best-ai-image-editing-models-2026` · S16 `veo3ai.io/zh/home` · S17 `seedance3.tools/seedance-2-5` · S18 `most.tw/posts/blog/ai-video-generation-tools-comparison-2026`

> 星标数与版本均为检索当日快照；仓库内容可能更新，引用时以仓库当前 README 为准。原片画面与本 skill 引用的第三方提示词均不可直接商用，需自行确认权利来源。
