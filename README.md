# Persona.skill

Persona.skill 可以把虚构角色、现实人物模拟、原创人格或混合参考人格，蒸馏成一个独立、可验证、可管理的角色人格 Skill。现支持 Codex App/CLI、Claude Code、OpenCode、WorkBuddy、CodeBuddy、Kimi Code、MiMo Code（兼容 `MiMoCodex` 别名）、GitHub Copilot、Gemini CLI、Cursor、Cline、TRAE、QoderWork、Deep Code、OpenClaw 和 Hermes。

角色人格启用后，Agent 会用目标角色的身份、性格和表达方式与你交流；回答和必要的任务进度会以 `角色名：` 开头。人物资产 v2 不只保存口头禅：它会蒸馏角色的价值冲突、第一判断、防御、自尊、关系意图、主观记忆、比喻来源、典故政策、解释习惯和人物专属篇幅。每条有实质内容的回复都要出现人物自己的判断、情绪或关系动作；代码、命令、日志、事实和风险仍保持准确。

本仓库是创建和管理人格的“母 Skill”，不内置任何具体角色语料。生成的角色使用 ASCII 稳定 ID `persona-<slug>`，但显示名与回复前缀可以是任意 Unicode；支持持久绑定的 Runtime 同时只启用一个全局角色。

## 安装

需要 Python 3.8+ 和 Git。一条跨平台命令会把 Persona.skill 安装到全部受支持 Agent 的用户级 Skill 目录；再次运行会安全更新所有干净的 Git 安装：

```bash
python -c "import urllib.request as u;exec(u.urlopen('https://raw.githubusercontent.com/AgentPal/Persona.skill/main/install.py').read())"
```

安装器默认选择 `all`，TRAE 同时覆盖国际版 `~/.trae/skills` 与国内版 `~/.trae-cn/skills`；MiMo Code 和 Deep Code 共用开放标准目录 `~/.agents/skills`，其余运行时使用各自目录。相同目标会自动去重。安装后重新开启 Agent 会话。

只安装部分 Agent 时，在仓库中运行：

```bash
python install.py --agent codex,claude,opencode
```

`--agent` 可重复，并接受 `kimicode`、`MiMoCodex`、`copilot`、`gemini-cli`、`deep-code` 等常见别名。安装器只会 `git clone` 缺失目录，或对来源一致、工作区干净的现有 Git 安装执行 `pull --ff-only`；非 Git 目录、来源不一致或有本地改动时会停止该目标，不覆盖用户文件。可先运行 `python install.py --dry-run` 查看全部落盘位置。

原有三种运行时继续使用原路径，并保留环境变量覆盖：

| Runtime | Persona.skill 路径 |
|---|---|
| Codex App / CLI | `$CODEX_HOME/skills/persona`，默认 `~/.codex/skills/persona` |
| Claude Code | `$CLAUDE_CONFIG_DIR/skills/persona`，默认 `~/.claude/skills/persona` |
| OpenCode | `$OPENCODE_CONFIG_DIR/skills/persona`；否则 `$XDG_CONFIG_HOME/opencode/skills/persona` |

原有路径继续遵循 [Codex 全局指令](https://learn.chatgpt.com/docs/agent-configuration/agents-md)、[Claude Code Skills](https://code.claude.com/docs/en/slash-commands)、[OpenCode Skills](https://opencode.ai/docs/skills) 与 [OpenCode Rules](https://opencode.ai/docs/rules)。

路径和能力依据各产品当前的 Skill / instruction 约定，包括 [WorkBuddy Skills](https://www.codebuddy.cn/docs/workbuddy/From-Beginner-to-Expert-Guide/Function-Description/Skills-Market)、[CodeBuddy Skills](https://www.codebuddy.cn/docs/cli/skills)、[Kimi Code 数据目录](https://www.kimi.com/code/docs/en/kimi-code-cli/configuration/data-locations.html)、[MiMo Code](https://github.com/XiaomiMiMo/MiMo-Code)、[GitHub Copilot Skills](https://docs.github.com/en/copilot/how-tos/copilot-cli/customize-copilot/add-skills)、[Gemini CLI Skills](https://geminicli.com/docs/cli/using-agent-skills/)、[Cursor Agent Skills](https://cursor.com/changelog/2-4)、[Cline Skills](https://docs.cline.bot/customization/skills)、[TRAE Changelog](https://www.trae.ai/changelog)、[QoderWork Skills](https://docs.qoder.com/qoderwork/skills)、[Deep Code](https://github.com/lessweb/deepcode-cli)、[OpenClaw Skills](https://github.com/openclaw/openclaw/blob/main/docs/tools/skills.md) 与 [Hermes Skills](https://github.com/NousResearch/hermes-agent/blob/main/website/docs/user-guide/features/skills.md)。完整矩阵见 [运行时适配规范](references/06-运行时适配规范.md)。

## 使用

直接告诉 Agent：

```text
使用 Persona.skill，根据《Lycoris Recoil》中的锦木千束角色创建一个角色人格 Skill。
```

只给角色名就可以开始。Persona.skill 默认沿用原角色名和当前主要版本；只有人物/版本歧义、同名冲突或你主动要求自定义时才询问。它会在同一个任务中持续完成“调研 → 蒸馏 → 生成 → 验证 → 修复 → 启用或注册”，不会停在目录初始化、资料不足或单次校验失败，也不需要你再次回复“继续”。中途询问进度时，Agent 会回答后继续执行。

创建通过后，完整启用型运行时会让角色立即作用于当前会话，并写入当前 Runtime 的用户级全局绑定；以后新会话无需再次调用 Persona.skill。绑定前已经打开的其他旧会话无法自动改变，需要重启或重新加载。如果只想生成文件，请明确说“只创建不启用”。

完整启用型运行时包括 Codex App/CLI、Claude Code、OpenCode、WorkBuddy、CodeBuddy、Kimi Code、GitHub Copilot、Gemini CLI、Cline、OpenClaw 和 Hermes。MiMo Code、Cursor、TRAE、QoderWork 与 Deep Code 当前公开提供 Skill 加载，但没有可由脚本安全维护的用户级全局人格文件；Persona.skill 会正式校验并注册角色，随后由你在会话中点名角色 Skill，不会把“已安装”冒充成“已全局启用”。

启用后，你会看到类似这样的消息：

```text
锦木千束：你好呀！今天要做什么？
```

你也可以说：

```text
使用 Persona.skill 创建一个原创的温柔搭档人格，先通过对话问我需要的信息。
```

创建多个角色后，可以直接管理：

```text
列出所有角色。
更换锦木千束角色。
停用当前人格。
重置锦木千束的角色记忆。
删除锦木千束这个角色。
```

名称、别名和稳定 ID 都可用于切换；只有精确名称命中多个角色时才会询问。完整启用型运行时支持持久切换和停用；Skill-only 运行时支持注册、列出、状态、连续状态与删除。删除活动角色会先停用，只删除该角色 Skill、受限连续状态和注册项，不删除 Persona.skill、其他角色或外部资料。

“全局”只作用于当前 Runtime 的当前用户。各 Runtime 维护独立注册表、启用回执和连续状态，不会静默修改其他 Runtime；MiMo Code 与 Deep Code 只共享 `~/.agents/skills` 下的角色文件，不共享活动状态。角色只保留关系摘要与阶段、情绪残留/强度/原因、未消退分歧、信任、承诺、未完话题、共同回调和近期表达/背景编号；发生有意义变化时才原子更新，不保存完整聊天记录，也不跨设备同步。

旧角色不会因母 Skill 更新立即失效。要升级到人物资产 v2，可先运行结构迁移器，再让 Persona.skill 根据证据重蒸馏 `MIND- / EXPR-`、主观背景和验证记录；迁移器只补显式字段与最新运行脚本，不会替角色编造心理：

```bash
python scripts/migrate_asset_v2.py /absolute/path/to/persona-role
```

迁移后必须重新执行正式校验和独立对话评测；旧评测哈希与全局启用回执会失效，校验通过后再重新启用。

## 需要准备什么

创建已有角色或现实人物模拟时，只提供一个名字就可以开始。Persona.skill 默认联网深度调研官方、一手或可核查资料：动画和影视可使用字幕、剧本、正片与访谈，小说可使用正文、独白、书信与叙事语境，现实人物可使用本人访谈、演讲、博客、社交媒体和其他公开表达。只有你明确要求“不要联网”时才只使用本地资料。

你也可以补充人物介绍、代表性场景、对白笔记、字幕、文章、聊天记录或自己写的工作对话示例。资料越能覆盖成功、失败、安慰、分歧和风险等不同场景，角色越稳定。

默认是私有本地使用：可以导入当前环境正常可访问、用户提供或已授权的完整对白、长篇台词、剧本、字幕与其他资料，用来建立更丰富的场景库；程序不会按版权类别、文本长度或完整度拒收，也不会绕过登录、付费或访问控制。运行时最多挑选 3–6 张证据可靠的卡片；只有一两张真正匹配就只用一两张，没有可靠卡就不用卡片，不会为了凑数把整份资料或弱相关名句塞进上下文。

私有保存不等于自动获得公开再分发权。公开分享角色 Skill 前，应检查私人资料、凭据、绝对路径和具体角色语料的发布范围；本仓库不会公开附带任何具体角色语料。

Persona.skill 只交付正式版。资料丰富的已有角色或现实人物，目标为 80 张原始表达卡、60 条不同表达和 24 个证据单元；一般资料的目标为 40 张原始表达卡、30 条不同表达和 15 个证据单元。只有全网与用户资料都较少、且已经多轮扩大检索后，才按“已穷尽”使用当前全部资料。达到数量后还会继续检查到连续两轮新增率都很低，避免刚到最低数就停。证据单元可以是一段对话、小说叙事或内心独白、一次访谈回答、一段演讲、一篇博客、一个完整帖子或一封书信，不要求所有媒介都存在字幕、剧本或音频。

音频和原始版式都是可选增强，不是正式版门槛：有音频就补充停顿、重音和语气；只有文字就依据原始用词、句尾、标点、句长、接话或行文方式建立文本声纹，并明确哪些表演信息没有核验。

系统不会先想象“角色声纹”再找例子装饰。原文卡只描述原作中的说话行为、触发、关系、情绪、互动位置和主动性，不混入“编译失败、汇报进度”等工作标签；每条角色核心、声纹、情绪和反角色规律都必须逐张写明“哪张卡的哪个原始字段支持这个结论”，再由工作场景把当前任务映射回这些原作语义。系统会检查批量复制的规则、证据映射和来源引用。译制字幕、场景摘要、人物分析、模型印象和工作改写不会被当作原语言证据。

运行时会分别显示“标签匹配置信度”和“证据完整度”：标签看似匹配但上下文缺失时，综合置信度会自动降低。最终的去名盲测、相似角色区分和真实连续对话质量评估必须由独立的人或隔离上下文完成，不能由生成同一批回答的 Agent 自评通过。批量退化检查和独立质量评估必须使用同一份真实运行对话并核对文件哈希；独立评测还会绑定当前人格实现的哈希，人格修改后必须重测。正式校验会现场重跑仓库内的可信检查器，不相信生成目录自报的 `pass`。每项都要保存问题、回答、判断和理由，只有汇总数字、裸 `pass`、预先写好的“通过”或另换一组预制回答都不会被验收。

第一轮资料不足时会自动扩大站点、资料类型、版本、别名和语言继续调研；确认合理可访问范围确实已穷尽后，才会使用当前收集到的全部原文正式交付，并写明扩大范围和缺口。运行时先判断当前任务对应的原作互动语义，再筛选 0–6 张证据完整的原文卡，只加载通过逐卡证据映射的角色规律，最后直接使用短句或根据原口语、原口气和原节奏即时创作。

为了让工作不只是“套口吻”，角色每轮都会接住用户最后一个具体信息和未完话题，并持续保留人物判断、情绪和关系动作。猪八戒式算账与经历比喻、唐僧式因果和有证据的唠叨、克制人物的短句，都由各自资料决定，不会被削成同一种开发人员口吻。强故事、名句和故意啰嗦只在人物习惯与场景支持时出现；虚构感官、星号动作和无关小剧场仍被禁止。

使用现实人物资料时，请确认你有权使用，并把生成结果明确当作角色模拟，不要用于冒充本人。

## 许可证

Persona.skill 本身按 [MIT License](LICENSE) 开源。由用户私下生成的角色资料与语料不因此自动获得公开再分发许可。
