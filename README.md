# Persona.skill

Persona.skill 可以把虚构角色、原创人格或你有权使用的人物资料，整理成一个独立的角色人格 Skill。

角色人格启用后，Agent 会用目标角色的身份、性格和表达方式与你交流；代码、命令、文件、日志、事实和风险判断不会被改写。

本仓库是创建人格的“母 Skill”，不内置任何具体作品的大型对白库。

## 安装

下载这个仓库，把整个文件夹改名为 `persona`，放到对应目录：

- Codex：`~/.codex/skills/persona`
- Claude Code：`~/.claude/skills/persona`

也可以用 Git：

```powershell
# Codex
git clone https://github.com/AgentPal/Persona.skill.git "$HOME\.codex\skills\persona"

# Claude Code
git clone https://github.com/AgentPal/Persona.skill.git "$HOME\.claude\skills\persona"
```

如果 Agent 已经打开，安装后重新开启一次会话。

## 使用

直接告诉 Agent：

```text
使用 Persona.skill，根据我提供的资料创建一个角色人格 Skill。
```

你也可以说：

```text
使用 Persona.skill 创建一个原创的温柔搭档人格，先通过对话问我需要的信息。
```

创建完成后，可以继续说：

```text
启用刚刚创建的人格。
停用当前人格。
恢复默认表达。
卸载这个人格，但保留 Persona.skill。
```

启用时默认只作用于当前项目，并且同一作用域只启用一个人格。用户资料和生成的人格默认保存在本地；是否调研、安装、启用或公开分享，都由你决定。

## 需要准备什么

可以只描述你想要的角色，也可以提供人物介绍、代表性场景、对白笔记、字幕、文章、聊天记录或自己写的工作对话示例。资料越能覆盖成功、失败、安慰、分歧和风险等不同场景，角色越稳定。

使用现实人物资料时，请确认你有权使用，并把生成结果明确当作角色模拟，不要用于冒充本人。
