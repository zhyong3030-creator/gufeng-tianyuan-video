# 古风田园群像短视频（gufeng-tianyuan-video）

**本技能明确就是做「古风田园群像短视频」**——中式古装田园、多人劳作群像、暖调统一色场。把这一类短片的可复制视觉规律抽成一套生产流程（统一色场 / 高色彩密度是其视觉方法）。给一个主题，先出整支片子的影像总揽，确认后引导选图像模型 + 视频模型，按模型能力重排分镜与生成条，再一步步产出提示词，每一步都附「怎么用」的操作说明。

## 安装

1. 解压本包，得到 `gufeng-tianyuan-video/` 目录。
2. 将该目录放到用户级技能目录：`~/.workbuddy/skills/gufeng-tianyuan-video/`。
   - 跨项目可用；如需团队共享，改放目标项目的 `.workbuddy/skills/gufeng-tianyuan-video/`。
3. 重启 WorkBuddy 或刷新技能列表后即可触发。

## 触发方式

说下面任意一句即可：

- 「做一条古风田园群像短视频」「古风群像短片」「田园群像同款」
- 「一步步产出」「先出总揽 / 先出第一步」
- 「复刻这个风格」「统一色场」「高色彩密度」
- 「该选哪个模型」「怎么写提示词」「定妆图 / 四视图 / 角色参考板」

## 它做什么

- **默认 `guided`**：每小步弹出选择，确认后再进下一步；小白也能照着做。
- **`autopilot`**（需显式授权）：把同一套生产包整体委托给执行后端，自动跑到成片。
- **执行后端可插拔**：`libtv` Agent / WorkBuddy 内生成 / 自有平台批量，三后端均可离线自检。

## 目录结构

```
gufeng-tianyuan-video/
├── SKILL.md                       主规则（元数据 + 目的 + 33 条升级规则 + 参数层级）
├── references/                    按需加载的参考文档
│   ├── usage-guide.md             全流程使用指引（先读）
│   ├── staged-delivery.md         分步交付口径
│   ├── input-modes.md             M0 零素材 / M1 部分 / M2 已有资产
│   ├── visual-grammar.md          视觉语法与构图锚点
│   ├── color-system.md            色卡与色值体系
│   ├── character-design-aesthetics.md / costume-design.md
│   ├── character-sheet-spec.md    定妆板规格与验收
│   ├── model-selection.md / model-profiles.md / model-adapter.md
│   ├── agent-autopilot.md         autopilot 通道
│   ├── script-template.md         分镜脚本模板
│   ├── prompt-playbook.md         提示词编写手册
│   ├── prompt-examples-image.md / prompt-examples-video.md
├── assets/                        产出时直接使用的模板与档案
│   ├── model_profiles.json        模型能力档案（单次时长硬约束等）
│   ├── overview-template.md / theme-brief-template.md
│   ├── step-delivery-template.md / step-prompt-box.md
│   ├── shot-list-template.csv
│   ├── character-sheet-prompts.md
│   ├── libtv-handoff-template.md
├── scripts/                       确定性脚本（可离线运行）
│   ├── verify_channels.py         双通道 + 口径一致性自检
│   ├── color_field_audit.py       成片/提示词色场审计
│   ├── model_adapter.py           模型参数适配
│   ├── build_handoff.py           交接包生成
│   └── stage_state.py             阶段状态机
└── README.md                      本文件
```

打包发布时已排除开发用的 `.backup/` 与 `__pycache__/`。

## 风格边界（重要）

本技能**明确只做「古风田园群像短视频」**，即「中式古装田园 / 暖调统一色场、多人劳作群像」，并且是刻意固定的：肤色、高光、主光角度、色彩占比、黑柔、圆形锚点、交领右衽等取值都是锁死的风格常量。换的只有主题、人物、物件与剧情，不提供风格切换；要做都市夜、霓虹、黑白纪实等别的风格，应另建技能。

可改的是**项目参数**：成片时长、镜数、场景数、段落数、单镜时长、生成条数、画幅、帧率、声音方案——这些在 S0 阶段确定，换时长只重算数量与时间码，不动风格口径。

## 版本与自检

- 当前版本：**v5.8.0**（v5.8 起逐镜运镜为「手持基底 + 每镜一种轻微附加运动、vlog 实拍感、可短暂自然直视」）。
- 离线自检：

```bash
python3 ~/.workbuddy/skills/gufeng-tianyuan-video/scripts/verify_channels.py
```

预期输出 `结果：576/576 项通过`，并确认两条通道都能从 S0 跑到 S7。

- 需联网调用收费能力时，技能默认不主动使用；`autopilot` 仅在用户显式授权后启用。

## 提示词形态

视频提示词固定六块：【视频基本参数】【参考绑定】【摄影母版】【禁止项】【画面描述】【收束与音频】。代码块内只写直接告诉 AI 的内容，平台 / 模型 / 档位 / 编号 / 种子 / 剪辑台等一律移到说明层。人物资产恒为每人 1 张 `ROLE_SHEET_X` 上下分区定妆板，视频层成对加挂 `FACE_CLOSE_X` 人脸特写。
