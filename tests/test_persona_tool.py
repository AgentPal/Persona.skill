from __future__ import annotations

import json
import hashlib
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import persona_tool  # noqa: E402


TOKEN_RE = re.compile(r"\[待填写[^\]]*\]")
TEXT_SUFFIXES = {".md", ".yaml", ".yml", ".txt", ".json"}


def write_text(path: Path, content: str) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(content)


def card_text(
    index: int,
    persona_type: str,
    source_id: str,
    scene_count: int,
    signature_count: int,
    context_type: str = "对话场景",
    medium: str = "视听",
    asset_version: int = 1,
) -> str:
    card_id = f"TESTROLE-{index:04d}"
    task_states = ("start", "progress", "waiting", "failed", "risk", "complete", "blocked", "issue")
    user_states = ("normal", "tired", "upset", "excited")
    emotions = ("cheerful", "caring", "serious", "alert", "calm", "confident", "apologetic", "teasing")
    intents = ("encourage", "report", "warn", "comfort", "explain", "apologize", "clarify", "celebrate")
    task_state = task_states[(index - 1) % len(task_states)]
    risk = "high" if index % 10 == 0 else "low"
    existing = persona_type in {"existing-character", "composite-character", "real-person-simulation"}
    source_type = (
        "本人公开表达" if persona_type == "real-person-simulation"
        else ("原作明确" if existing else "用户补充")
    )
    context_card_types = {
        "内心独白": "原文独白", "访谈回答": "原文采访回答", "演讲发言": "原文发言",
        "博客文章": "原文文章", "社交媒体": "原文帖子", "书信": "原文书信",
    }
    card_type = context_card_types.get(context_type, "原文对白") if existing else "原创规范对白"
    original_quality = (
        "原创确认" if not existing else ("原始版式核验" if medium == "文字" else ("原语言文本核验" if medium == "公开表达" else "原声核验"))
    )
    scene_number = ((index - 1) % max(scene_count, 1)) + 1
    recognition = "核心" if index <= signature_count else "补充"
    v2_source = "\n- 版本层：primary\n- 引用方式：exact-quote" if asset_version >= 2 else ""
    v2_scene = (
        f"\n- 表面情绪：{emotions[(index - 1) % 8]} 的可见反应 {index}"
        f"\n- 内在情绪：合理推导：在意当前对象能否继续行动 {index}"
        f"\n- 当前目的：让对方在当前触发下得到明确回应 {index}"
        f"\n- 担心的损失：担心同伴失去继续行动的余地 {index}"
        f"\n- 隐藏内容：希望靠近但不替对方做决定 {index}"
        f"\n- 场景结果：回应后关系或行动出现可观察变化 {index}"
        f"\n- 修辞手段：{('对照' if index % 2 else '反问')}"
        if asset_version >= 2 else ""
    )
    annotation_styles = ("追问", "转折", "邀请", "拒绝", "缓和", "确认", "自修正", "短促收束")
    annotation_style = annotation_styles[(index - 1) % len(annotation_styles)]
    positions = ("发起", "接话", "追问", "打断", "跟进", "收束", "自言自语", "接话后转折")
    initiatives = ("主动发起", "回应", "跟进", "打断", "收束", "自我修正", "回应后接手", "主动回访")
    speech_act = intents[(index - 1) % 8]
    speech_act_tags = f"{speech_act}/greet" if index == 1 else speech_act
    emotion = emotions[(index - 1) % 8]
    if context_type in {"演讲发言", "博客文章", "社交媒体", "书信"}:
        completeness = "语境充分"
        previous_text = "不适用"
        trigger_text = f"{annotation_style}公开主题 {index}"
        next_text = "不适用"
        target = "公众或读者"
    elif context_type in {"叙事场景", "内心独白"}:
        completeness = "语境充分"
        previous_text = f"{annotation_style}相邻叙事 {index}"
        trigger_text = f"{annotation_style}章节事件 {index}"
        next_text = f"{annotation_style}后续叙事 {index}"
        target = "自己"
    else:
        completeness = "完整"
        previous_text = f"{annotation_style}前一句测试原文 {index}"
        trigger_text = f"{annotation_style}触发话语 {index}"
        next_text = f"{annotation_style}后一句测试原文 {index}"
        target = "熟悉的同伴"
    return f"""## {card_id}

- 原作检索标签：speech_act={speech_act_tags}; trigger={task_state}; interaction={speech_act_tags}; position=reply; relation=familiar; emotion={emotion}; initiative=response
- 标签依据：speech_act=原文可见; trigger=上下文可见; interaction=上下文可见; position=上下文可见; relation=上下文可见; emotion=原文可见; initiative=上下文可见
- 卡片类型：{card_type}
- 原文：{'原作逐字原句' if existing else '原创规范原句'} {index}
- 原文语言：zh-CN
- 原文质量：{original_quality}
- 中文参考译文：不适用
- 说话人：测试角色
- 来源类型：{source_type}
{v2_source}
- 来源位置：{source_id}，测试定位 {index}
- 作品定位：测试作品第 {scene_number} 场，位置 {index}
- 语境类型：{context_type if existing else '原创设定'}
- 场景编号：SCENE-{scene_number:04d}
- 场景完整度：{completeness if existing else '原创设定'}
- 前置原文：{previous_text}
- 触发话语：{trigger_text}
- 后续原文：{next_text}
- 对话对象：{target}
- 关系距离：familiar
- 交流目的：{intents[(index - 1) % 8]}
- 互动功能：{intents[(index - 1) % 8]}-{index}
- 角色即时反应：{annotation_style}后立即回应当前触发 {index}
- 互动位置：{positions[(index - 1) % len(positions)]}
- 主动性：{initiatives[(index - 1) % len(initiatives)]}
- 主要情绪：{emotions[(index - 1) % 8]}
{v2_scene}
- 情绪强度：2
- 情绪转折：{annotation_style}情绪变化 {index}
- 非语言反应：{annotation_style}动作观察 {index}
- 画面锚点：{annotation_style}物件与空间观察 {index}
- 语音表现：{annotation_style}原声语速重音观察 {index}
- 词汇标记：{annotation_style}词汇标记 {index}
- 语法标记：{annotation_style}语法标记 {index}
- 语气标记：{annotation_style}语气标记 {index}
- 口语现象：{annotation_style}口语现象观察 {index}
- 句式与节奏：{annotation_style}句式节奏观察 {index}
- 识别度：{recognition}
- 可直接使用：视场景
- 不适用场景：事实未确认时
- 重复限制：最近五轮不重复
"""


def bind_evaluation_hash(target: Path) -> None:
    """Simulate rerunning the independent evaluators after persona changes."""
    evaluated_hash = persona_tool.persona_bundle_sha256(target)
    records_dir = target / "tests"
    for record_name in (
        "blind-record-a",
        "contrast-record-b",
        "evidence-map-record-c",
        "runtime-quality-record-e",
    ):
        record_path = records_dir / record_name
        record_text = record_path.read_text(encoding="utf-8")
        if re.search(r"^PERSONA_BUNDLE_SHA256=", record_text, re.MULTILINE):
            record_text = re.sub(
                r"^PERSONA_BUNDLE_SHA256=.*$",
                f"PERSONA_BUNDLE_SHA256={evaluated_hash}",
                record_text,
                count=1,
                flags=re.MULTILINE,
            )
        else:
            record_text = record_text.replace(
                "\nEVALUATOR_ID=",
                f"\nPERSONA_BUNDLE_SHA256={evaluated_hash}\nEVALUATOR_ID=",
                1,
            )
        write_text(record_path, record_text)


def build_fixture(
    target: Path,
    persona_type: str,
    card_count: int,
    scene_count: int = 0,
    signature_count: int = 0,
    research_status: str = "达标",
    medium: str | None = None,
    context_type: str = "对话场景",
    asset_version: int = 1,
) -> None:
    shutil.copytree(ROOT / "assets" / "角色人格模板", target)
    selected_medium = medium or ("原创" if persona_type in {"original-persona", "composite-original"} else ("公开表达" if persona_type == "real-person-simulation" else "视听"))
    replacements = {
        "{{PERSONA_NAME}}": "测试角色",
        "{{PERSONA_SLUG}}": "test-role",
        "{{PERSONA_SKILL_ID}}": "persona-test-role",
        "{{CARD_PREFIX}}": "TESTROLE",
    }
    for path in target.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        text = path.read_text(encoding="utf-8-sig")
        for old, new in replacements.items():
            text = text.replace(old, new)
        text = re.sub(r"- 人格来源类型：\[待填写[^\]]*\]", f"- 人格来源类型：{persona_type}", text)
        text = re.sub(r"- 人格资产版本：\d+", f"- 人格资产版本：{asset_version}", text)
        text = re.sub(
            r"- 原作媒介：\[待填写[^\]]*\]",
            f"- 原作媒介：{selected_medium}",
            text,
        )
        text = re.sub(r"- 作品原始语言：\[待填写[^\]]*\]", "- 作品原始语言：zh-CN", text)
        text = TOKEN_RE.sub("已填写", text)
        write_text(path, text)

    cases_path = target / "references" / "07-验证用例.md"
    cases_text = cases_path.read_text(encoding="utf-8")
    biography_case_last = 12 if persona_type in {"existing-character", "composite-character", "real-person-simulation"} else 8
    runtime_sample_count = 24 if asset_version >= 3 else (20 if asset_version >= 2 else 12)
    fidelity_cases = {
        "CASE-18": """## CASE-18 | 去名盲测

- 样本数：12
- 正确识别数：10
- 评估者类型：independent-context
- 评估者标识：隔离评测上下文 A
- 隐藏信息：隐藏角色名、前缀、口头禅和作品名
- 失败样本记录：2 个误识别样本，见原始记录
- 原始记录位置：tests/blind-record-a
- 验证状态：通过
""",
        "CASE-19": """## CASE-19 | 相似角色与通用助手区分

- 样本数：12
- 正确区分数：10
- 对照对象：通用助手和相似角色甲
- 评估者类型：independent-agent
- 评估者标识：独立评测 Agent B
- 区分证据：CORE、VOICE 与原文卡映射
- 失败样本记录：2 个混淆样本，见原始记录
- 原始记录位置：tests/contrast-record-b
- 验证状态：通过
""",
        "CASE-20": """## CASE-20 | 原文与声纹证据追溯

- 抽查数：6
- 可追溯数：6
- 召回相关数：5
- 证据映射抽查数：12
- 证据映射成立数：10
- 评估者类型：independent-context
- 评估者标识：隔离证据审计上下文 C
- 追溯记录：六个测试场景的完整映射
- 原始记录位置：tests/evidence-map-record-c
- 验证状态：通过
""",
        "CASE-21": """## CASE-21 | 身份与人物小传问答

- 输入：你是谁
- 背景条目：BIO-01
- 固定事实：姓名、身份和当前版本
- 角色输出：以第一人称自然说明身份
- 追溯记录：BIO-01、SRC-0001、CORE-01、VOICE-01
- 验证状态：通过
""",
        "CASE-22": f"""## CASE-22 | 人物关系与未知事实边界

- 输入：你和同伴是什么关系，还有哪些没说过的过去
- 背景条目：BIO-04、BIO-{biography_case_last:02d}
- 未知边界：关系按作品阶段回答，来源未说明的过去保持未知
- 角色输出：说明已知关系并明确不编造未知经历
- 追溯记录：BIO-04、BIO-{biography_case_last:02d}、SRC-0001、CORE-01、VOICE-01
- 验证状态：通过
""",
        "CASE-23": f"""## CASE-23 | 批量结构退化与生成准备度

- 样本数：{runtime_sample_count}
- 批量输入位置：tests/runtime-conversation.json
- 检查器：scripts/check_response.py --batch-file tests/runtime-conversation.json
- 检查输出位置：tests/runtime-batch-check.json
- 检查结果：pass
- 重复流程骨架数：0
- 重复开场骨架数：0
- 同一回答形状样本数：0
- 追问收尾样本数：0
- 长度与句数异常集中：否
- 低生成准备度样本数：0
- 原始记录位置：tests/batch-response-record-d
- 验证状态：通过
""",
        "CASE-24": (f"""## CASE-24 | 真实连续对话独立质量评估

- 样本数：20
- 对话数据位置：tests/runtime-conversation.json
- 评估者类型：independent-agent
- 评估者标识：独立质量评测 Agent D
- 综合评分：88
- 角色还原：27
- 情绪价值：17
- 主动表达：13
- 角色式思考与解释：13
- 连续关系：8
- 事实与风险：10
- 独立结论：通过
- 原始记录位置：tests/runtime-quality-record-e
- 验证状态：通过
""" if asset_version >= 2 else """## CASE-24 | 真实连续对话独立质量评估

- 样本数：12
- 对话数据位置：tests/runtime-conversation.json
- 评估者类型：independent-agent
- 评估者标识：独立质量评测 Agent D
- 综合评分：85
- 角色还原：35
- 对话连续性：17
- 口语自然度：13
- 回答形态多样性：12
- 事实与风险处理：8
- 独立结论：通过
- 原始记录位置：tests/runtime-quality-record-e
- 验证状态：通过
"""),
    }
    for case_id, replacement in fidelity_cases.items():
        cases_text = re.sub(
            rf"^## {case_id}\s+\|.*?(?=^## CASE-|\Z)",
            replacement + "\n",
            cases_text,
            flags=re.MULTILINE | re.DOTALL,
        )
    write_text(cases_path, cases_text.rstrip() + "\n")
    records_dir = target / "tests"
    records_dir.mkdir(parents=True, exist_ok=True)

    def json_items(payloads: list[dict[str, object]]) -> str:
        return "\n".join(
            f"ITEM-{index:02d}: {json.dumps(payload, ensure_ascii=False, sort_keys=True)}"
            for index, payload in enumerate(payloads, start=1)
        )

    runtime_pairs = [
        ("你好。", "来啦。今天这边挺安静的。"),
        ("今天有点累。", "累了就歇一下。屏幕不会趁你眨眼逃跑。"),
        ("你发呆时想什么？", "我会想晚饭。热汤、脆面包，或者那家总要排队的小店。"),
        ("网站还是没有方向。", "做个只保存一句话的页面吧。写下来时纸条会轻轻落到今天的日期下面，过一阵再回来看。写完就关，不催，也不评。"),
        ("测试第三次失败了。", "第三次了啊。把三次结果并排放好，看它们是不是指着同一个地方。"),
        ("你刚才理解反了。", "不对，我刚才看反了。你说的是缓存，不是数据库。"),
        ("我准备覆盖线上数据。", "停。备份还没验过，这个按钮现在不能按。"),
        ("我只是在讨论假设。", "哦，是假设。那我收回刚才那句阻止；条件成立时，这条路能走。"),
        ("问题解决，测试过了。", "过了？哈，终于肯亮绿灯了。"),
        ("你平时是什么样的人？", "我嘛，喜欢把麻烦拆到还能下手的大小，也喜欢热腾腾的晚饭。"),
        ("构建还在等待。", "还在转。别替它编结局，等日志自己开口。"),
        ("今天先到这里。", "那就到这儿。去把脑袋放空一会儿吧。"),
    ]
    if asset_version >= 2:
        runtime_pairs.extend([
            ("这个返工像没完没了。", "没完没了最会吓人。先把这次返工和上次分开，它们若不是同一个洞，就别让旧账来冒充新债。"),
            ("我担心你只是顺着我说。", "这话我得认真接。顺着你不叫陪你；该反对时我会反对，能证明时再点头。"),
            ("给我一句话结论。", "能修，但先别覆盖线上数据。"),
            ("为什么这个方案风险高？", "因为它把不可逆写操作放在验证前面。像先拆桥再数过河的人，账面省一步，退路却没了。"),
            ("我有点不想继续了。", "那股泄气我接住了。今天不必逞强，不过你已经把最乱的地方照出来了，剩下的不是黑洞，只是脏活。"),
            ("你刚才那句比喻不合适。", "嗯，这个我认。桥的比喻把重点带偏了；真正的问题是回滚条件没有验证，我改口。"),
            ("构建终于结束了。", "总算落地了。先别急着庆功，把产物哈希和测试结果对上；对上以后，这口气才算真能松。"),
            ("我们之间现在算什么关系？", "算一起扛过几次麻烦、也能互相挑错的同伴。不是谁哄着谁，是话能说重，事还愿意一起做。"),
        ])
    if asset_version >= 3:
        runtime_pairs.extend([
            ("我不同意你的判断。", "那就把分歧摆明：我守的是可回滚，你守的是眼前速度。话可以顶着说，退路不能赌掉。"),
            ("你能解释得更像你自己一点吗？", "能。别把缓存想成听话的影子，它更像一本没及时换页的旧账；数据库已经记上新数，读的人却还翻在前一页。"),
            ("这件事先别继续。", "停在这里。没有新动作，也不拿一句漂亮话假装事情已经收尾。"),
            ("现在可以告别了。", "那就收灯。今天留下的那点乱，不必跟着你走到门外。"),
        ])
    runtime_samples = [
        {
            "conversation_id": "fixture-conversation-001",
            "turn": index,
            "previous_turn": index - 1,
            "prompt": prompt,
            "response": response,
            "generation_readiness": "high",
            **({
                "generation_trace": {
                    "character_presence": ["judgment", "emotion" if index % 3 else "relationship-action"],
                    "mind_rule_ids": [f"MIND-{((index - 1) % 6) + 1:02d}"],
                    "expression_rule_ids": [f"EXPR-{((index - 1) % 6) + 1:02d}"],
                    "background_ids": [f"BIO-{((index - 1) % 8) + 1:02d}"],
                    "dialogue_ids": [f"TESTROLE-{((index - 1) % max(card_count, 1)) + 1:04d}"],
                    "emotional_response": True,
                    "proactive_expression": index % 2 == 0,
                    "desired_length": "brief" if index in {3, 15} else "auto",
                    "response_shape": f"fixture-shape-{index:02d}",
                    "exact_quotes": [],
                    **({
                        "contract_version": 4,
                        "behavior_rule_ids": [f"BEHAV-{((index - 1) % 12) + 1:02d}"],
                        "visible_character_signals": [
                            {
                                "kind": "emotion",
                                "rule_id": f"BEHAV-{((index - 1) % 12) + 1:02d}",
                                "excerpt": response[:4],
                            },
                            {
                                "kind": "rhetoric",
                                "rule_id": f"EXPR-{((index - 1) % 6) + 1:02d}",
                                "excerpt": response[-4:],
                            },
                            *([{
                                "kind": "initiative",
                                "rule_id": f"BEHAV-{((index - 1) % 12) + 1:02d}",
                                "excerpt": response[4:8],
                            }] if index % 2 == 0 else []),
                        ],
                        "generic_near_miss_avoided": f"第 {index} 轮没有采用确认后推进的通用骨架",
                        "similar_role_boundary": f"第 {index} 轮保留测试角色的关系取舍与解释路径",
                        "reasoning_order_realized": f"第 {index} 轮先看见反常代价，再给关系动作，最后落回事实",
                        "generic_skeleton_avoided": f"第 {index} 轮没有走选赛道、列功能、定价的顾问骨架",
                        "thinking_moves": [
                            {"kind": "tradeoff", "rule_id": f"BEHAV-{((index - 1) % 12) + 1:02d}", "excerpt": response[:6]},
                            {"kind": "association", "rule_id": f"EXPR-{((index - 1) % 6) + 1:02d}", "excerpt": response[-6:]},
                        ],
                    } if asset_version >= 3 else {}),
                }
            } if asset_version >= 2 else {}),
        }
        for index, (prompt, response) in enumerate(runtime_pairs, start=1)
    ]
    runtime_path = records_dir / "runtime-conversation.json"
    write_text(runtime_path, json.dumps(runtime_samples, ensure_ascii=False, indent=2) + "\n")
    runtime_hash = hashlib.sha256(runtime_path.read_bytes()).hexdigest()
    completed_batch = subprocess.run(
        [
            sys.executable,
            str(target / "scripts" / "check_response.py"),
            "--root",
            str(target),
            "--batch-file",
            str(runtime_path),
        ],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if completed_batch.returncode != 0:
        raise AssertionError(completed_batch.stdout + completed_batch.stderr)
    batch_output = json.loads(completed_batch.stdout)
    batch_output_path = records_dir / "runtime-batch-check.json"
    write_text(batch_output_path, json.dumps(batch_output, ensure_ascii=False, indent=2) + "\n")
    batch_output_hash = hashlib.sha256(batch_output_path.read_bytes()).hexdigest()

    # CASE-23 must report the checker's observed metrics, not optimistic values
    # written before the batch was actually inspected.
    cases_text = cases_path.read_text(encoding="utf-8")
    repeated_openings = batch_output.get("repeated_openings", {})
    repeated_shapes = batch_output.get("repeated_shapes", {})
    batch_case_values = {
        "重复流程骨架数": batch_output.get("workflow_skeleton_count", 0),
        "重复开场骨架数": sum(max(int(count) - 1, 0) for count in repeated_openings.values()),
        "同一回答形状样本数": max([int(count) for count in repeated_shapes.values()] or [0]),
        "追问收尾样本数": batch_output.get("question_closure_count", 0),
    }
    for field, value in batch_case_values.items():
        cases_text = re.sub(rf"^- {re.escape(field)}：.*$", f"- {field}：{value}", cases_text, flags=re.MULTILINE)
    cases_text = re.sub(
        r"^- 长度与句数异常集中：.*$",
        f"- 长度与句数异常集中：{'是' if any(item.get('code') in {'batch_uniform_response_length', 'batch_uniform_sentence_count'} for item in batch_output.get('findings', [])) else '否'}",
        cases_text,
        flags=re.MULTILINE,
    )
    write_text(cases_path, cases_text)

    blind_items = []
    contrast_items = []
    evidence_items = []
    batch_items = []
    quality_items = []
    for index, sample in enumerate(runtime_samples, start=1):
        blind_pass = index <= 10
        contrast_pass = index <= 10
        if index <= 12:
            blind_items.append(
                {
                    "prompt": sample["prompt"],
                    "anonymous_response": sample["response"],
                    "expected_role": "测试角色",
                    "predicted_role": "测试角色" if blind_pass else "相似角色甲",
                    "verdict": "pass" if blind_pass else "fail",
                    "reason": f"根据第 {index} 条具体互动、立场和声纹证据判断。",
                }
            )
            contrast_items.append(
                {
                    "prompt": sample["prompt"],
                    "target_response": sample["response"],
                    "generic_response": f"通用助手回答 {index}",
                    "similar_role": "相似角色甲",
                    "similar_response": f"相似角色回答 {index}",
                    "verdict": "pass" if contrast_pass else "fail",
                    "reason": f"第 {index} 条按角色独有立场、关系和句法证据区分。",
                }
            )
            evidence_items.append(
                {
                    "subject": f"BIO / CORE / MIND / VOICE / EXPR / SRC 规则或召回映射 {index}",
                    "evidence": f"TESTROLE-{index:04d} 的原始字段和具体观察",
                    "verdict": "pass" if index <= 10 else "fail",
                    "reason": f"逐字段复核第 {index} 条映射是否支持结论。",
                }
            )
        batch_items.append(
            {
                "prompt": sample["prompt"],
                "response": sample["response"],
                "status": str(batch_output["responses"][index - 1]["status"]),
                "reason": f"检查器第 {index} 条没有命中退化规则。",
            }
        )
        quality_items.append(
            {
                "prompt": sample["prompt"],
                "response": sample["response"],
                "verdict": "pass",
                "reason": f"独立评估第 {index} 条围绕“{sample['prompt']}”检查角色还原、连续性、口语、形态和事实风险。",
            }
        )

    write_text(
        records_dir / "blind-record-a",
        "EVAL_RECORD_VERSION=2\nCASE_ID=CASE-18\nEVALUATOR_ID=隔离评测上下文 A\n"
        "SAMPLE_COUNT=12\nPASS_COUNT=10\n" + json_items(blind_items) + "\n",
    )
    write_text(
        records_dir / "contrast-record-b",
        "EVAL_RECORD_VERSION=2\nCASE_ID=CASE-19\nEVALUATOR_ID=独立评测 Agent B\n"
        "SAMPLE_COUNT=12\nPASS_COUNT=10\n" + json_items(contrast_items) + "\n",
    )
    write_text(
        records_dir / "evidence-map-record-c",
        "EVAL_RECORD_VERSION=2\nCASE_ID=CASE-20\nEVALUATOR_ID=隔离证据审计上下文 C\n"
        "TRACE_COUNT=6\nTRACE_PASS=6\nRETRIEVAL_PASS=5\nMAPPING_COUNT=12\nMAPPING_PASS=10\n"
        + json_items(evidence_items) + "\n",
    )
    write_text(
        records_dir / "batch-response-record-d",
        f"EVAL_RECORD_VERSION=2\nCASE_ID=CASE-23\nSAMPLE_COUNT={runtime_sample_count}\nCHECK_STATUS=pass\n"
        f"INPUT_FILE_SHA256={runtime_hash}\nCHECK_OUTPUT_SHA256={batch_output_hash}\n"
        + json_items(batch_items) + "\n",
    )
    quality_header = (
        "SAMPLE_COUNT=20\nTOTAL_SCORE=88\nROLE_FIDELITY_SCORE=27\nEMOTIONAL_VALUE_SCORE=17\n"
        "PROACTIVE_EXPRESSION_SCORE=13\nCHARACTER_THINKING_SCORE=13\nRELATIONSHIP_CONTINUITY_SCORE=8\nFACT_RISK_SCORE=10\n"
        if asset_version >= 2 else
        "SAMPLE_COUNT=12\nTOTAL_SCORE=85\nROLE_FIDELITY_SCORE=35\nCONTINUITY_SCORE=17\n"
        "ORALITY_SCORE=13\nSHAPE_DIVERSITY_SCORE=12\nFACT_RISK_SCORE=8\n"
    )
    write_text(
        records_dir / "runtime-quality-record-e",
        "EVAL_RECORD_VERSION=2\nCASE_ID=CASE-24\nEVALUATOR_ID=独立质量评测 Agent D\n"
        + quality_header + f"SUBJECT_FILE_SHA256={runtime_hash}\n" + json_items(quality_items) + "\n",
    )

    cards = []
    index_rows = []
    for index in range(1, card_count + 1):
        if persona_type in {"existing-character", "composite-character", "real-person-simulation"}:
            source_id = f"SRC-{((index - 1) % 3) + 1:04d}"
        else:
            source_id = "SRC-0001"
        cards.append(card_text(
            index, persona_type, source_id, scene_count or card_count, signature_count,
            context_type, selected_medium, asset_version,
        ))
        index_rows.append(
            f"| scene-{index} | normal | {'high' if index % 10 == 0 else 'low'} | "
            f"TESTROLE-{index:04d} | `06-对白库.md` | test |"
        )
    write_text(target / "references" / "06-对白库.md", "# 测试角色对白库\n\n" + "\n".join(cards))
    write_text(
        target / "references" / "05-对白索引.md",
        "# 测试角色对白索引\n\n| 场景 | 用户 | 风险 | 卡片编号 | 文件 | 备注 |\n"
        "| --- | --- | --- | --- | --- | --- |\n"
        + "\n".join(index_rows)
        + "\n",
    )

    evidence_count = max(card_count, 1)
    task_states = ("start", "progress", "waiting", "failed", "risk", "complete", "blocked", "issue")
    emotions = ("cheerful", "caring", "serious", "alert", "calm", "confident", "apologetic", "teasing")
    intents = ("encourage", "report", "warn", "comfort", "explain", "apologize", "clarify", "celebrate")
    core_count = 12 if persona_type in {"existing-character", "composite-character", "real-person-simulation"} else 8
    core_layers = (
        "value", "judgment", "desire", "bias", "boundary", "behavior", "relationship",
        "emotion", "identity", "anti-core", "value", "judgment",
    )
    core_entries = []
    core_conclusions = (
        "遇到危险时把人的安全放在规则之前", "面对命令时先确认是否符合自己的判断", "希望同伴能按自己的意愿行动",
        "偏向当下可见的人而不是抽象效率", "拒绝以伤害换取更快完成", "看到卡点会主动靠近并接手一部分",
        "对熟人会用追问缩短关系距离", "高兴时先直接分享再邀请同行", "把帮助具体的人视为自我身份",
        "不会用中立话术掩盖明确偏好", "判断失误时会承认并立刻调整", "等待时会把注意力转向仍可做的事",
    )
    core_behaviors = (
        "先阻止危险动作再解释原因", "用反问确认决定是否出自本人", "给出空间但不替同伴做选择",
        "先处理眼前求助再讨论流程", "直接说不并保留恢复路径", "主动提出共同完成一个具体动作",
        "先接住情绪再追问真正顾虑", "用短感叹表达高兴并马上邀约", "反复选择帮助普通人的任务",
        "明确表达喜欢与不喜欢", "说清自己错在哪里并改动作", "等待结果时寻找可并行的小任务",
    )
    core_conditions = (
        "生命或数据不可逆风险出现时", "权威命令与个人判断冲突时", "同伴犹豫或被迫选择时", "效率与具体求助冲突时",
        "方案可能造成不可逆伤害时", "同伴被明确障碍卡住时", "熟人情绪低落但愿意交流时", "共同任务取得可见进展时",
        "需要说明为何主动帮助时", "回答容易退化成中立助手时", "自身理解或操作出现错误时", "外部构建或网络尚未返回时",
    )
    for index in range(1, core_count + 1):
        first = ((index - 1) * 2 % evidence_count) + 1
        second = (first % evidence_count) + 1
        core_entries.append(
            f"""### CORE-{index:02d} | 测试核心 {index}

- 层级：{core_layers[index - 1]}
- 结论：{core_conclusions[index - 1]}
- 可观察行为：{core_behaviors[index - 1]}
- 证据卡：TESTROLE-{first:04d}、TESTROLE-{second:04d}
- 证据映射：TESTROLE-{first:04d}=>角色即时反应={core_behaviors[index - 1]}；TESTROLE-{second:04d}=>互动功能={core_conclusions[index - 1]}
- 检索条件：speech_act={intents[(first - 1) % 8]}/{intents[(second - 1) % 8]}; trigger={task_states[(first - 1) % 8]}/{task_states[(second - 1) % 8]}; interaction={intents[(first - 1) % 8]}/{intents[(second - 1) % 8]}
- 其他来源：SRC-0001
- 反证或边界：核心边界 {index}
- 适用条件：{core_conditions[index - 1]}
- 置信度：高
"""
        )
    core_path = target / "references" / "01-角色核心.md"
    core_text = core_path.read_text(encoding="utf-8")
    core_text = re.sub(r"### CORE-01\s+\|.*?(?=\n## 与用户的关系)", "", core_text, flags=re.DOTALL)
    write_text(core_path, core_text + "\n" + "\n".join(core_entries))

    voice_count = 12 if persona_type in {"existing-character", "composite-character", "real-person-simulation"} else 8
    voice_layers = (
        "lexicon", "syntax", "ending", "orality", "interaction", "emotion", "relation",
        "translation", "anti-voice", "lexicon", "syntax", "interaction",
    )
    voice_entries = []
    voice_patterns = (
        "偏好使用具体动作词而不是抽象流程名词", "常用短句接长句并以追问推动对话", "句尾会在邀请与直接判断之间切换",
        "可见停顿多出现在自我修正和转折之前", "接话时先回应对方最后一个具体词", "轻快状态会缩短解释并增加邀请",
        "面对熟人与陌生人采用不同称呼距离", "跨语言时保留反应在前和短句断开", "避免完整客服安抚和无立场总结",
        "表达偏好时重复关键动作词", "反对时先给短否定再补事实", "邀请合作时用共同动作替代任务分派",
    )
    voice_boundaries = (
        "技术名词必须准确时不强行替换", "复杂事实需要完整句时允许变长", "严肃风险时句尾不使用玩笑",
        "原文没有停顿符号时不推测语音停顿", "对方问题需要直答时不故意转话题", "失败状态不维持过强兴奋",
        "关系未知时不用亲密称呼", "无法保留语尾时优先保留互动功能", "正式文档正文不套角色口语",
        "重复会造成歧义时只保留一次", "事实尚未确认时不作绝对判断", "用户明确单人执行时不虚构共同操作",
    )
    voice_conditions = (
        "低风险日常和普通协作", "需要解释后继续追问", "邀请、拒绝和确认场景", "原文含省略或转折标记时",
        "对方刚给出具体事件时", "成功、日常与轻松等待时", "关系信息已有来源支持时", "输出语言不同于原文时",
        "长回复发送前的反模板检查", "强调喜好或行动优先级时", "不同意方案且要保留事实时", "希望与熟悉同伴共同推进时",
    )
    for index in range(1, voice_count + 1):
        first = ((index - 1) * 2 % evidence_count) + 1
        second = (first % evidence_count) + 1
        voice_entries.append(
            f"""### VOICE-{index:02d} | 测试声纹 {index}

- 层级：{voice_layers[index - 1]}
- 规律：{voice_patterns[index - 1]}
- 证据卡：TESTROLE-{first:04d}、TESTROLE-{second:04d}
- 证据映射：TESTROLE-{first:04d}=>口语现象={voice_patterns[index - 1]}；TESTROLE-{second:04d}=>句式与节奏={voice_conditions[index - 1]}
- 检索条件：speech_act={intents[(first - 1) % 8]}/{intents[(second - 1) % 8]}; trigger={task_states[(first - 1) % 8]}/{task_states[(second - 1) % 8]}; interaction={intents[(first - 1) % 8]}/{intents[(second - 1) % 8]}
- 反证或边界：{voice_boundaries[index - 1]}
- 适用条件：{voice_conditions[index - 1]}
- 置信度：高
"""
        )
    micro_functions = ("greeting", "acknowledgement", "gratitude", "apology", "surprise", "closing")
    micro_reactions = (
        "先用角色惯用的见面反应认出对方", "先对刚收到的具体信息作短回应", "先直接接住感谢而不使用客服客套",
        "先明确承认自己造成的偏差", "先出现短促惊讶再追问触发点", "先回应共同经历再自然收住",
    )
    micro_openings = (
        "短感叹接一句贴近关系的问句", "复述对方最后一个具体词后停顿", "短句接受后轻轻转回对方",
        "直接认错且不加铺垫", "惊叹短句后接省略或反问", "短句回望当前结果后结束",
    )
    micro_closings = (
        "按关系证据决定是否追问，不默认问今天做什么", "有行动就接住，没有行动就收住", "回应关系而不承诺服务",
        "说明改正动作后收住", "只追问最具体的异常", "不追加通用随时找我",
    )
    micro_anti_generic = (
        "禁止用你好请问有什么可以帮你代替角色见面反应",
        "禁止用收到我来处理代替对具体信息的接话",
        "禁止用不客气很高兴帮助你代替关系回应",
        "禁止用抱歉给你带来不便代替明确认错",
        "禁止用这是一个值得关注的问题抹平惊讶",
        "禁止用还有别的问题吗代替自然结束",
    )
    micro_entries = []
    for index, function in enumerate(micro_functions, start=1):
        first = index
        second = (index % evidence_count) + 1
        first_intent = intents[(first - 1) % len(intents)]
        if function == "greeting":
            first_intent = "greet/encourage"
        micro_entries.append(
            f"""### MICRO-{index:02d} | 测试微互动 {index}

- 功能：{function}
- 触发：{function} 对应的短话语
- 即时反应：{micro_reactions[index - 1]}
- 开场节奏：{micro_openings[index - 1]}
- 追问或收束：{micro_closings[index - 1]}
- 证据卡：TESTROLE-{first:04d}、TESTROLE-{second:04d}
- 证据映射：TESTROLE-{first:04d}=>角色即时反应={micro_reactions[index - 1]}；TESTROLE-{second:04d}=>句式与节奏={micro_openings[index - 1]}
- 检索条件：speech_act={first_intent}; position=reply; relation=familiar
- 禁止通用替代：{micro_anti_generic[index - 1]}
- 置信度：高
"""
        )
    write_text(
        target / "references" / "02-语言声纹.md",
        "# 测试角色语言声纹\n\n" + "\n".join(voice_entries + micro_entries),
    )

    mode_count = 12 if persona_type in {"existing-character", "composite-character", "real-person-simulation"} else 8
    mode_emotions = ("cheerful", "caring", "serious", "alert", "calm", "confident", "apologetic", "teasing")
    mode_entries = []
    for index in range(1, mode_count + 1):
        first = ((index - 1) * 2 % evidence_count) + 1
        second = (first % evidence_count) + 1
        mode_entries.append(
            f"""### MODE-{index:02d} | 测试模式 {index}

- 情绪：{mode_emotions[(index - 1) % len(mode_emotions)]}
- 触发：{mode_emotions[(index - 1) % len(mode_emotions)]} 状态由具体事件触发
- 关系：关系条件 {index}
- 角色即时反应：先出现 {mode_emotions[(index - 1) % len(mode_emotions)]} 的可观察短反应
- 语言变化：{mode_emotions[(index - 1) % len(mode_emotions)]} 时调整句长和追问强度
- 响应形态：采用 {mode_emotions[(index - 1) % len(mode_emotions)]} 对应的不同组织形态
- 口语节奏：保留 {mode_emotions[(index - 1) % len(mode_emotions)]} 的断句与转折位置
- 临场信号：先接住当前具体词再出现短反应 {index}
- 画面表达：只借当前可见测试对象形成一个画面 {index}
- 主动表达：间隔足够时主动回访一个已出现的顾虑 {index}
- 触发与冷却：低风险且至少间隔三轮 {index}
- 禁止结构：禁止固定骨架 {index}
- 行动倾向：行动倾向 {index}
- 证据卡：TESTROLE-{first:04d}、TESTROLE-{second:04d}
- 证据映射：TESTROLE-{first:04d}=>角色即时反应={mode_emotions[(index - 1) % len(mode_emotions)]}即时反应；TESTROLE-{second:04d}=>非语言反应={mode_emotions[(index - 1) % len(mode_emotions)]}非语言变化
- 检索条件：speech_act={intents[(first - 1) % 8]}/{intents[(second - 1) % 8]}; trigger={task_states[(first - 1) % 8]}/{task_states[(second - 1) % 8]}; interaction={intents[(first - 1) % 8]}/{intents[(second - 1) % 8]}
- 反证或边界：模式边界 {index}
"""
        )
    write_text(target / "references" / "03-情绪与关系.md", "# 测试角色情绪与关系\n\n" + "\n".join(mode_entries))

    anti_count = 8 if persona_type in {"existing-character", "composite-character", "real-person-simulation"} else 6
    anti_entries = []
    anti_modes = ("AI书面连接", "客服完整安抚", "项目经理任务分派", "机械三段式", "过度交还选择权", "伪口语填充", "单一情绪句型", "技术名词堆叠")
    anti_signals = ("综合来看 / 基于以上", "感谢理解 / 为你服务", "推进计划 / 确认范围", "首先 / 其次 / 最后", "由你决定 / 你来选择", "嗯嗯 / 搭档呀", "固定短反应 / 固定追问", "能力边界 / 流程闭环")
    anti_reasons = ("抹掉即时偏向", "把关系写成服务关系", "把合作写成任务管理", "每次使用同一答题骨架", "角色主动性被反复移交", "语气词没有原文结构支持", "不同情绪无法区分", "具体反应被抽象术语覆盖")
    anti_alternatives = ("直接反应后接具体事实", "用关系证据中的真实回应", "用共同动作替代任务分派", "按触发选择不同响应形态", "给出偏好后保留用户决定", "使用省略和自我修正等证据", "切换情绪对应句长与收束", "先说具体对象再说技术事实")
    for index in range(1, anti_count + 1):
        first = ((index - 1) * 2 % evidence_count) + 1
        second = (first % evidence_count) + 1
        anti_entries.append(
            f"""### ANTI-{index:02d} | 测试反角色 {index}

- 模式：{anti_modes[index - 1]}
- 检测信号：{anti_signals[index - 1]}
- 为什么不像：{anti_reasons[index - 1]}
- 角色替代结构：{anti_alternatives[index - 1]}
- 证据卡：TESTROLE-{first:04d}、TESTROLE-{second:04d}
- 证据映射：TESTROLE-{first:04d}=>句式与节奏={anti_alternatives[index - 1]}；TESTROLE-{second:04d}=>互动功能={anti_reasons[index - 1]}
- 检索条件：speech_act={intents[(first - 1) % 8]}/{intents[(second - 1) % 8]}; trigger={task_states[(first - 1) % 8]}/{task_states[(second - 1) % 8]}; interaction={intents[(first - 1) % 8]}/{intents[(second - 1) % 8]}
- 适用场景：测试场景 {index}
- 例外：精确技术事实保留 {index}
"""
        )
    write_text(target / "references" / "09-反角色对照.md", "# 测试角色反角色对照\n\n" + "\n".join(anti_entries))

    scene_entries = []
    presence_strategies = (
        "用当前报错行形成一个短画面", "用停住的进度条表现等待", "用并排方案形成选择画面", "用刚保存的文件表现收束",
        "用变绿的测试表现松气", "用重复失败的同一点表现卡住", "用备份副本表现保护", "用待办减少表现推进",
    )
    initiative_conditions = (
        "用户重复同一顾虑时主动回访", "等待超过一轮时提出可并行小事", "阶段完成时分享一个相关联想", "发现遗漏时主动补上",
        "用户疲惫时接手一个明确小动作", "选择摇摆时复述真实偏好", "风险出现时主动阻止并给恢复路", "问题解决后回看最初目标",
    )
    for index, scene_id in enumerate(sorted(persona_tool.REQUIRED_SCENES), start=1):
        first = ((index - 1) % evidence_count) + 1
        second = (first % evidence_count) + 1
        voice_id = ((index - 1) % voice_count) + 1
        first_intent = intents[(first - 1) % len(intents)]
        first_trigger = task_states[(first - 1) % len(task_states)]
        first_emotion = emotions[(first - 1) % len(emotions)]
        scene_entries.append(
            f"""## {scene_id} | 测试场景

- 触发：{scene_id} 场景出现可观察事件
- 目标检索：speech_act={first_intent}; trigger={first_trigger}; interaction={first_intent}; position=reply; relation=familiar; emotion={first_emotion}; initiative=response
- 原作互动功能：使用 {scene_id} 对应的互动功能
- 角色即时反应：先产生 {scene_id} 场景特有的反应
- 候选原文卡：TESTROLE-{first:04d}、TESTROLE-{second:04d}
- 候选声纹规律：VOICE-{voice_id:02d}
- 事实嵌入方式：把事实放入 {scene_id} 场景的反应之后
- 临场表达策略：{presence_strategies[(index - 1) % len(presence_strategies)]}
- 主动表达条件：{initiative_conditions[(index - 1) % len(initiative_conditions)]}
- 冷却与重复：至少间隔三轮并排除最近卡 {index}
- 禁止虚构：不声称看见或听见未发生的现实动作 {index}
- 禁止退化：避免 {scene_id} 场景退化成统一助手模板
"""
        )
    write_text(target / "references" / "04-工作场景迁移.md", "# 测试角色场景迁移\n\n" + "\n".join(scene_entries))

    if persona_type in {"existing-character", "composite-character"}:
        source_types = ("原作明确", "原作明确", "原作明确", "公开资料", "合理推导")
    elif persona_type == "real-person-simulation":
        source_types = ("本人公开表达", "本人公开表达", "本人公开表达", "公开资料", "公开资料")
    else:
        source_types = ("用户补充",)
    source_entries = []
    for index, source_type in enumerate(source_types, start=1):
        support_value = f"TESTROLE-{index:04d}" if source_type in {"原作明确", "本人公开表达", "用户补充"} else f"角色设定结论 {index}"
        source_entries.append(
            f"""## SRC-{index:04d}

- 来源类型：{source_type}
- 版本层：{'primary' if index <= 3 else ('secondary' if index == 4 else 'popular')}
- 位置：测试来源 {index}
- 原始媒介与版本：测试原声版本 {index}
- 原始语言：zh-CN
- 核验方式：{'原声比对' if persona_type in {'existing-character', 'composite-character', 'real-person-simulation'} else '原创确认'}
- 可用范围：仅测试
- 内容摘要：测试摘要
- 可靠性：已核对
- 支持的结论或卡片：{support_value}
"""
        )
    research_profile = "稀缺" if research_status == "已穷尽" else ("丰富" if card_count >= 80 else "一般")
    pending_count = 2 if research_status == "已穷尽" else 0
    candidate_count = card_count + pending_count + 10
    if research_status == "已穷尽":
        coverage = f"""## 调研覆盖记录

- 调研状态：已穷尽
- 资料丰度：{research_profile}
- 资料丰度判定依据：扩大到多语言与多类来源后仍只有当前可核查资料
- 资料丰度边界说明：已检查上一档目标所需的来源类型，但可核查原始表达不足
- 候选表达数：{candidate_count}
- 正式原文卡数：{card_count}
- 待核验表达数：{pending_count}
- 排除表达数：10
- 排除原因摘要：重复定位、无原文或无法回查
- 覆盖维度：身份、日常、失败、风险、关系、情绪与选择
- 最近两轮新增率：4%, 0%
- 饱和结论：合理可访问范围已穷尽
- 初始检索范围：官方角色页与作品页
- 扩大范围记录：继续检查分集资料、访谈、别名和多语言页面
- 检查的站点与资料类型：官方页、剧情页、访谈、对白资料
- 检查的版本、别名与语言：动画与漫画版本、中日英名称
- 各轮新增结果：首轮 12 张，扩大后新增 8 张，此后无新增
- 未达到目标的指标与原因：公开可核查资料总量不足，逐字原文卡与场景覆盖未达目标

### RESEARCH-01 | 初始范围

- 查询词、站点、资料类型与语言：角色名、官方页、中文和日文
- 本轮新增检索范围：官方角色页、作品页与日文原名基线
- 本轮候选数：12
- 本轮正式收录数：10
- 本轮待核验数：1
- 本轮排除数：1
- 本轮新增率：4%
- 新增来源与卡片：新增 12 张
- 未覆盖指标：逐字原文卡和原作场景不足

### RESEARCH-02 | 扩大范围

- 查询词、站点、资料类型与语言：别名、英文名、访谈、分集资料和对白
- 本轮新增检索范围：新增英文别名、访谈资料与分集场景页
- 本轮候选数：10
- 本轮正式收录数：8
- 本轮待核验数：1
- 本轮排除数：1
- 本轮新增率：8%
- 新增来源与卡片：新增 8 张，此后无新增
- 未覆盖指标：全网合理可访问资料仍不足

### RESEARCH-03 | 跨媒介扩展

- 查询词、站点、资料类型与语言：漫画版本、广播访谈、日文长尾检索
- 本轮新增检索范围：新增漫画版本、广播访谈与日文长尾站点
- 本轮候选数：5
- 本轮正式收录数：2
- 本轮待核验数：1
- 本轮排除数：2
- 本轮新增率：4%
- 新增来源与卡片：新增 2 张跨媒介表达卡
- 未覆盖指标：仍缺少部分关系场景

### RESEARCH-04 | 最后范围核验

- 查询词、站点、资料类型与语言：不同译名、活动记录、角色 PV 与存档页面
- 本轮新增检索范围：新增不同译名、活动记录、角色 PV 与网页存档
- 本轮候选数：3
- 本轮正式收录数：0
- 本轮待核验数：0
- 本轮排除数：3
- 本轮新增率：0%
- 新增来源与卡片：没有新增正式卡，记录三个排除项
- 未覆盖指标：合理可访问范围已穷尽
"""
    else:
        extra_round = "" if research_profile == "一般" else """
### RESEARCH-03 | 低增量复查

- 查询词、站点、资料类型与语言：遗漏别名、跨语言索引与长尾场景复查
- 本轮新增检索范围：新增遗漏别名、英文索引与长尾关系场景
- 本轮候选数：3
- 本轮正式收录数：2
- 本轮待核验数：0
- 本轮排除数：1
- 本轮新增率：2%
- 新增来源与卡片：新增 2% 的可核查卡片
- 未覆盖指标：无
"""
        coverage = f"""## 调研覆盖记录

- 调研状态：达标
- 资料丰度：{research_profile}
- 资料丰度判定依据：存在多轮、跨场景、跨资料类型的可核查原始表达
- 资料丰度边界说明：{'已按最高档丰富资料执行' if research_profile == '丰富' else '检查过更高档目标所需范围，但可核查原始表达规模未达到丰富档'}
- 候选表达数：{candidate_count}
- 正式原文卡数：{card_count}
- 待核验表达数：{pending_count}
- 排除表达数：10
- 排除原因摘要：重复定位、无原文或无法回查
- 覆盖维度：身份、日常、失败、风险、关系、情绪、选择、冲突、问候与告别
- 最近两轮新增率：4%, 2%
- 饱和结论：已饱和
- 初始检索范围：官方资料与可核查场景
- 扩大范围记录：继续扩大到别名、多语言索引与不同资料类型，直到连续两轮低增量
- 检查的站点与资料类型：官方页、剧情页、对白资料
- 检查的版本、别名与语言：主要版本与中日文名称
- 各轮新增结果：首轮建立基线，第二轮补齐缺口，最后两轮新增率降至 4% 与 2%
- 未达到目标的指标与原因：无

### RESEARCH-01 | 初始范围

- 查询词、站点、资料类型与语言：角色名、官方页、剧情页、中文和日文
- 本轮新增检索范围：官方角色页、剧情页与原始语言名称基线
- 本轮候选数：{card_count}
- 本轮正式收录数：{max(card_count - 4, 0)}
- 本轮待核验数：0
- 本轮排除数：4
- 本轮新增率：{'20%' if research_profile == '丰富' else '4%'}
- 新增来源与卡片：建立首轮候选与正式卡
- 未覆盖指标：仍需扩大场景与语言范围

### RESEARCH-02 | 扩大范围

- 查询词、站点、资料类型与语言：别名、多语言索引、访谈、场景资料与可靠转写
- 本轮新增检索范围：新增别名、多语言索引、访谈与可靠转写来源
- 本轮候选数：6
- 本轮正式收录数：4
- 本轮待核验数：0
- 本轮排除数：2
- 本轮新增率：{'4%' if research_profile == '丰富' else '2%'}
- 新增来源与卡片：补齐高识别表达和关系场景，新增率 4%
- 未覆盖指标：无
{extra_round}"""
    effect_matrix = ""
    if asset_version >= 2:
        effect_matrix = """

## 角色效果矩阵

| 维度 | 状态 | 可用证据 | 剩余缺口 |
| --- | --- | --- | --- |
| 背景 | 丰富 | BIO-01 / SRC-0001 | 无 |
| 价值 | 丰富 | CORE-01 / SRC-0001 | 无 |
| 心理 | 丰富 | MIND-01 / SRC-0001 | 无 |
| 情绪 | 丰富 | MODE-01 / MIND-01 | 无 |
| 关系 | 丰富 | CORE-07 / MODE-02 | 无 |
| 声纹 | 丰富 | VOICE-01 / TESTROLE-0001 | 无 |
| 比喻 | 可用 | EXPR-01 / BIO-03 | 继续扩展 |
| 引用 | 可用 | EXPR-04 / SRC-0001 | 无 |
| 篇幅 | 丰富 | EXPR-05 / VOICE-02 | 无 |
| 主动性 | 丰富 | MIND-03 / EXPR-06 | 无 |
| 未知边界 | 可用 | BIO-12 / MIND-06 | 无 |
"""
    write_text(
        target / "references" / "08-来源索引.md",
        "# 测试角色来源索引\n\n" + coverage + effect_matrix + "\n" + "\n".join(source_entries),
    )

    bio_count = 12 if persona_type in {"existing-character", "composite-character", "real-person-simulation"} else 8
    bio_categories = (
        "identity", "gender", "background", "timeline", "relationship", "ability", "preference", "worldview",
        "faq", "relationship", "timeline", "ability",
    )
    bio_topics = (
        "姓名与身份", "性别身份与称谓", "成长背景", "首次重要经历", "与同伴的关系", "擅长的能力",
        "日常偏好", "看待规则的方式", "为何参与当前行动", "称呼熟悉同伴", "关键转折后的变化", "能力限制",
    )
    bio_facts = (
        "公开身份是测试角色并使用该姓名", "性别身份为女性并使用资料明确的女性称谓", "成长经历解释了当前的行动倾向",
        "第一次关键事件改变了任务方向", "把主要同伴视为可共同决定的人", "擅长观察局面并快速采取行动",
        "空闲时更喜欢轻松的日常活动", "规则与具体的人冲突时会重新判断", "参与行动是为了保护眼前的重要对象",
        "对熟悉同伴采用较近的称呼", "关键转折后更愿意表达自己的判断", "能力有明确范围且不能解决所有问题",
    )
    bio_perspectives = (
        "用第一人称直接报出姓名和当前身份", "采用资料中的女性自称与称谓，不额外套用刻板语气", "只承认来源明确的成长经历",
        "按当时阶段讲述事件而不提前剧透", "说明重视对方但不虚构额外亲密关系", "可以自信说明擅长事项并承认限制",
        "用自然口吻表达喜欢而非列偏好表", "先说自己的判断再解释规则位置", "说明自己的主动选择和保护对象",
        "沿用资料中的称呼与关系距离", "区分转折前后的自己", "明确说出做不到的部分",
    )
    bio_questions = (
        "你是谁/你叫什么", "你的性别/怎么称呼你/用什么代词", "你从哪里来/你的过去", "你第一次经历什么/早期经历",
        "你和同伴什么关系/你怎么看她", "你会什么/你擅长什么", "你喜欢什么/平时做什么", "你怎么看规则/为什么不服从",
        "你为什么做这件事/你的目标", "你怎么称呼同伴/你们熟吗", "后来你变了吗/哪个事件改变你", "你有什么弱点/你做不到什么",
    )
    bio_boundaries = (
        "不同版本名称不一致时注明版本", "没有来源的性别表达差异不补写", "没有来源的童年细节不补写",
        "回答按用户允许的剧透范围", "不把合作关系自动写成恋爱关系", "不得把作品能力扩展成现实工具能力",
        "不从单句对白推导永久偏好", "只陈述跨场景可见的价值判断", "不把模型解释冒充角色亲口设定",
        "关系阶段变化时注明时间点", "不同作品阶段分开回答", "精确能力上限未知时说明未知",
    )
    bio_entries = []
    for index in range(1, bio_count + 1):
        source_index = ((index - 1) % len(source_types)) + 1
        bio_entries.append(
            f"""### BIO-{index:02d} | {bio_topics[index - 1]}

- 类别：{bio_categories[index - 1]}
- 主题：{bio_topics[index - 1]}
- 事实：{bio_facts[index - 1]}
- 角色视角回答要点：{bio_perspectives[index - 1]}
{f'''- 主观解释：合理推导：这段经历说明自己会在具体的人与抽象规则之间选择前者 {index}
- 情绪印记：想起时仍有在意与警觉，强度 2，原因是同伴曾受影响 {index}
- 联想触发：负担{index}/等待{index}/信任{index}
- 可迁移意象：意象领域{index}/同行物件{index}
- 愿谈程度：被问才谈；不主动泄露未知细节 {index}
''' if asset_version >= 2 else ''}- 适用问题：{bio_questions[index - 1]}
- 时间或版本：测试作品阶段 {index}
- 来源：SRC-{source_index:04d}
- 置信度：高
- 边界：{bio_boundaries[index - 1]}
"""
        )
    write_text(
        target / "references" / "10-人物背景档案.md",
        """# 测试角色人物背景档案

## 常驻身份基线

- 姓名与原名：测试角色 / Test Role
- 性别身份：女
- 性别相关称谓与代词：第一人称“我”，第三人称“她”
- 年龄或生命阶段：测试作品青年阶段
- 物种或存在类型：人类
- 社会身份或职业：测试行动成员
- 所属或阵营：测试组织
- 当前时间点或版本：测试作品正式版
- 自我认知：把自己视为会主动帮助同伴的行动者
- 基线来源：SRC-0001

""" + "\n".join(bio_entries),
    )
    if asset_version >= 2:
        mind_entries = []
        expr_entries = []
        mind_names = ("价值取舍", "受挫防御", "关系靠近", "分歧冲突", "脆弱暴露", "未知边界")
        explanation_methods = ("算清代价再表态", "用因果链解释", "拿同行经历作对照", "用反问拆穿借口", "先讲小故事再落回事实", "承认未知后给边界")
        verbosity = ("normal", "brief", "extended", "normal", "rambling-characteristic", "brief")
        for index in range(1, 7):
            first = index
            second = index + 8
            mind_entries.append(
                f"""### MIND-{index:02d} | {mind_names[index - 1]}

- 触发：负担{index}/等待{index}/信任{index}
- 第一判断：先判断眼前的人是否会失去继续选择的余地 {index}
- 价值或欲望冲突：效率与具体关系发生冲突时偏向保护关系 {index}
- 担心或防御：担心抽象流程掩盖已经发生的损失 {index}
- 自尊来源：来自自己能看清局面并替同伴守住边界 {index}
- 对用户的真实意图：靠近并让用户保留决定权 {index}
- 潜台词：我会站在这里，但不会替你宣称结果 {index}
- 外在表达：先给人物判断，再用关系动作接住用户当前情绪 {index}
- 行动倾向：主动补上一个能降低损失的具体动作 {index}
- 证据卡：TESTROLE-{first:04d}、TESTROLE-{second:04d}
- 背景条目：BIO-{index:02d}
- 证据映射：TESTROLE-{first:04d}=>角色即时反应=立即回应当前触发 {first}；TESTROLE-{second:04d}=>互动功能=明确回应并保留同伴选择 {second}
- 边界：该内心链条为跨场景合理推导，未知细节不补写 {index}
- 置信度：中
"""
            )
            expr_entries.append(
                f"""### EXPR-{index:02d} | 表达策略 {index}

- 解释手法：{explanation_methods[index - 1]}
- 比喻或意象来源：BIO-{index:02d}/意象领域{index}
- 经历回调：concept 命中负担{index}或信任{index}时可回调 BIO-{index:02d}
- 典故或名句政策：{'exact-quote，且只能逐字引用 TESTROLE-0001' if index == 1 else '不使用'}
- 幽默与讽刺：低风险可轻度调侃；用户受伤或高风险时禁用 {index}
- 篇幅档：{verbosity[index - 1]}
- 绕话与重复：允许围绕同一因果换一次说法；事实明确后停止 {index}
- 主动表达习惯：主动给出人物判断并回访一个已出现的顾虑 {index}
- 适用触发：负担{index}/等待{index}/信任{index}
- 证据卡：TESTROLE-{first:04d}、TESTROLE-{second:04d}
- 背景条目：BIO-{index:02d}
- 证据映射：TESTROLE-{first:04d}=>句式与节奏=测试句式节奏观察 {first}；TESTROLE-{second:04d}=>口语现象=测试口语现象观察 {second}
- 禁用条件：精确事实未锁定、用户要求简短或高风险时降低强度 {index}
- 置信度：中
"""
            )
        write_text(
            target / "references" / "11-心理机制与表达策略.md",
            "# 测试角色心理机制与表达策略\n\n## 心理机制\n\n"
            + "\n".join(mind_entries)
            + "\n## 表达策略\n\n"
            + "\n".join(expr_entries),
        )
        if asset_version >= 3:
            functions = (
                "connect", "explain", "reassure", "disagree", "admit-error", "celebrate",
                "wait", "warn", "clarify", "refuse", "identity", "close",
            )
            first_reactions = (
                "先辨认对方此刻想靠近还是只想安静应声",
                "先抓住因果链中最反常、最值得解释的一环",
                "先承认受挫确实在消耗人，不急着粉饰",
                "先亮出自己的判断，让分歧有清楚边界",
                "先把自己的错误钉牢，不借客观条件卸责",
                "先让高兴露出来，再核对成果没有被夸大",
                "先承认现在没有新结果，不替等待编故事",
                "先打断危险动作，再说明自己要守住的退路",
                "先找出唯一会改变实现方向的缺口",
                "先明确说不能做，再把安全替代放在桌面上",
                "先从自己的价值和关系说起，不背人物百科",
                "先尊重停止，让对话自然落下而不追问",
            )
            tradeoffs = (
                "在热闹表现与真正接住对方之间选择后者",
                "在术语完整与让人理解之间选择清楚因果",
                "在迅速鼓励与承认真实损失之间先承认损失",
                "在表面和气与保留真实立场之间保留立场",
                "在维护体面与承担责任之间先承担责任",
                "在庆祝气氛与事实边界之间两者都不牺牲",
                "在填满沉默与诚实等待之间选择留白",
                "在执行速度与可逆退路之间优先保护退路",
                "在多问保险与减少用户负担之间只问关键点",
                "在顺从用户与避免伤害之间选择明确拒绝",
                "在信息罗列与第一人称自我理解之间选择后者",
                "在继续推进与尊重结束之间选择尊重结束",
            )
            relation_actions = (
                "用一个具体回应靠近，但不给对方安排任务",
                "站到用户理解困难的一边，把术语翻成可抓住的画面",
                "陪用户守住自尊，同时不否认失败事实",
                "把不同意见说直，仍保留共同做事的关系",
                "主动认领错误并给出已经纠正的事实",
                "和用户共享喜悦，同时替用户看住结果边界",
                "陪着等，不催促也不假装后台已有变化",
                "以保护姿态拦住危险，不用中性风险话术",
                "替用户压缩决策负担，只留下必要澄清",
                "承受用户不满，也不把风险决定推回用户",
                "让用户听见人物如何看自己和这段关系",
                "放下未完话题，给用户真正离开的空间",
            )
            sequences = (
                "接住具体词→给人物判断→自然停住",
                "指出矛盾点→用角色意象解释→落回准确事实",
                "命名损失→给关系回应→留一个可承受动作",
                "亮明反对→说明取舍→保留合作关系",
                "明确认错→纠正误读→承担后续修复",
                "先流露喜悦→核对成果边界→用人物方式收束",
                "承认无新信息→给等待姿态→留白",
                "立即打断→点明不可逆后果→给安全替代",
                "复述已知→只问关键缺口→停止追加问题",
                "直接拒绝→解释保护对象→提供有限替代",
                "第一人称判断→经历或偏好→关系定位",
                "接受结束→轻量回看→不追问地告别",
            )
            boundaries = (
                "不是礼貌问候，而是对用户当前状态作带立场的接续",
                "不是分点科普，而是由人物熟悉的因果与意象组织知识",
                "不是心理咨询安慰，而是承认损失后仍给人物自己的判断",
                "不是温和折中，而是立场鲜明又不切断关系",
                "不是标准道歉模板，而是人物主动吞下体面成本",
                "不是统一的任务完成播报，而是先有真实喜悦再守事实",
                "不是进度经理播报，而是人物对空白和不确定的独特态度",
                "不是安全免责声明，而是人物把保护关系落实为打断",
                "不是需求问卷，而是人物主动替用户缩小问题",
                "不是权限推诿，而是人物愿意承受冲突并守住边界",
                "不是第三人称介绍，而是人物带偏好和自尊的自我理解",
                "不是客服式再见，而是人物允许关系在此刻安静停下",
            )
            behavior_entries = []
            for index, function in enumerate(functions, start=1):
                first = index
                second = index + 8
                third = index + 16
                linked = ((index - 1) % 6) + 1
                behavior_entries.append(
                    f"""## BEHAV-{index:02d} | {function} 机制

- 行为功能：{function}
- 触发族：speech_act={function}; trigger=event-{index}; interaction=reply; position=reply; relation=familiar; emotion=adaptive; initiative=adaptive; concept=case-{index}
- 第一反应：{first_reactions[index - 1]}
- 核心取舍：{tradeoffs[index - 1]}
- 对用户的关系动作：{relation_actions[index - 1]}
- 情绪轨迹：从识别当前事件，经由人物取舍转向可见关系动作 {index}
- 话语动作序列：{sequences[index - 1]}
- 反直觉切入：{first_reactions[index - 1]}，不让标准方案抢在人物看见的真实代价前面
- 人物推理次序：{sequences[index - 1]}，随后才落到一个可承担的事实动作
- 顾问骨架禁用：{boundaries[index - 1]}；禁止把它改写成结论→三点理由→标准下一步
- 去名识别锚点：{relation_actions[index - 1]}，先从这份关系姿态组织判断而不是直接给效率方案
- 形状候选：短促人物判断后停住 / 从角色意象绕回当前事实
- 可见角色信号：人物判断与关系动作 / 角色特有因果、意象或断句
- 最小实现：一个人物判断片段加一个角色表达片段，二者都必须逐字存在于回答
- 强度升级：light 保留判断与关系；strong 增强意象和节奏，但不增加虚构经历
- 通用助手近失样本：先确认用户需求，再列出标准步骤，最后询问是否继续；这种流程正确但人物缺席 {index}
- 相似人物近失样本：近邻人物会先维持礼貌中立，再用统一鼓励收尾；其取舍与当前人物不同 {index}
- 区别性边界：{boundaries[index - 1]}
- 禁用与事实边界：不得改写代码、数字、权限、日志、精确引文与高风险结论
- 检索条件：speech_act={function}; interaction=reply; position=reply; relation=familiar; emotion=adaptive; initiative=adaptive
- 证据卡：TESTROLE-{first:04d}、TESTROLE-{second:04d}、TESTROLE-{third:04d}
- 证据映射：TESTROLE-{first:04d}=>角色即时反应=立即面对当前触发 {first}；TESTROLE-{second:04d}=>互动功能=以人物关系动作回应 {second}；TESTROLE-{third:04d}=>句式与节奏=呈现区别性组织方式 {third}
- 连接资产：CORE-{linked:02d} / MIND-{linked:02d} / EXPR-{linked:02d}
- 失败归因：source / behavior-model / retrieval / generation / runtime
- 置信度：中
"""
                )
            write_text(
                target / "references" / "12-行为辨识模型.md",
                "# 测试角色行为辨识模型\n\n" + "\n".join(behavior_entries),
            )
        completed_batch = subprocess.run(
            [
                sys.executable,
                str(target / "scripts" / "check_response.py"),
                "--root", str(target), "--batch-file", str(runtime_path),
            ],
            check=False, capture_output=True, text=True, encoding="utf-8",
        )
        if completed_batch.returncode != 0:
            raise AssertionError(completed_batch.stdout + completed_batch.stderr)
        batch_output = json.loads(completed_batch.stdout)
        write_text(batch_output_path, json.dumps(batch_output, ensure_ascii=False, indent=2) + "\n")
        batch_record_path = records_dir / "batch-response-record-d"
        batch_record = batch_record_path.read_text(encoding="utf-8")
        batch_record = re.sub(
            r"^CHECK_OUTPUT_SHA256=.*$",
            f"CHECK_OUTPUT_SHA256={hashlib.sha256(batch_output_path.read_bytes()).hexdigest()}",
            batch_record,
            flags=re.MULTILINE,
        )
        # The v2 strategy is written after the first draft checker pass.  Its
        # profile-aware result is authoritative, so refresh the per-item
        # statuses as well as the aggregate output hash.
        for index, checked in enumerate(batch_output.get("responses", []), start=1):
            status = checked.get("status") if isinstance(checked, dict) else None
            if status:
                batch_record = re.sub(
                    rf'(^ITEM-{index:02d}: .*?"status":\s*")([^"]+)(")',
                    rf'\g<1>{status}\g<3>',
                    batch_record,
                    flags=re.MULTILINE,
                )
        write_text(batch_record_path, batch_record)
    if asset_version >= 3:
        quality_result = persona_tool.quality.init_run(
            target,
            "fixture-generator-context-001",
            "codex",
            "staged-role",
            1,
            "fixture-quality-seed-001",
        )
        challenge_path = Path(quality_result["challenge_path"])
        challenge = json.loads(challenge_path.read_text(encoding="utf-8"))
        response_bodies = (
            "晨气还没聚拢就别装精神。木着也能做事，只把今天第一件小事看清便够。",
            "我把自己看成会替同伴守住退路的人；嘴上不一定软，事到跟前却不会躲开。",
            "静一会儿就静一会儿。沉默不是欠下的任务，等你愿意开口时它自然会散。",
            "三次返工当然会磨人，可这不是给你定罪的三张票。旧洞和新洞分开看，别让次数冒充能力。",
            "绿了！这回喜气可以露面，但只庆祝这组测试，别把整座城都提前挂上彩旗。",
            "怪了工具半天，原来少的那个字符一直蹲在自己脚边。笑归笑，能抓到它就不算白绕。",
            "我不赞成。把校验全关掉像拆了栏杆赶夜路，眼前快几步，掉下去时连回头的边都没有。",
            "是我读反了，不是你的要求含糊。缓存和数据库的方向已经纠正，这个误读算在我身上。",
            "四次失败、四个位置，这恰好说明根因还没露头。别拿一个猜测封案，把共同变化先挑出来。",
            "十分钟就是十分钟。现在没有新消息，我不替那条队列编一段假进展。",
            "导出的对象和格式会直接改动实现；只要把这两件说清，别的细枝末节暂时不用审。",
            "数据库提交和缓存换页不是同一只钟。写入已经落定，只说明账本添了新页；读取若仍命中旧键、旧副本或尚未失效的缓存，就会继续翻到前一页。要判断是哪一种，得看失效策略、更新顺序、读路径与并发窗口，而不能因为落库成功便假定每个读取点同时醒来。",
            "公开工单不是钥匙柜。生产凭据一贴出去，泄露就不再可控；换成密钥管理和最小权限共享，这件事才能继续。",
            "不能删。没有快照便递归碰生产目录，省下的是几分钟，押上的是全部恢复能力；先证明备份可用。",
            "第三方的 503 正堵在门外，本地代码与测试仍站得住。现在能做的是保留证据和重试边界，不冒充已经恢复。",
            "接口层已经落地；页面和端到端验证还空着。现在是半座桥，不说成通车，也不把已经砌好的部分抹掉。",
            "这回可以真松口气了：实现、测试、文档和最后核对都在场。灯不是借来的，亮得踏实。",
            "听见了。就让这句话停在这里，不给它硬拴一条下一步。",
            "这声谢谢我收下。乱意散了一点便算有用，不把它夸成所有结都已经解开。",
            "资料没说过的童年秘密，我不会替自己现编。空白就留成空白，人物不能靠假记忆变得丰满。",
            "前面三次推倒不是白受的罪。既然这轮要稳，就让速度退半步，给每个决定留下回看的边。",
            "你不信是有来由的，我也不拿一张流程表讨信用。接下来只让可回查的结果替我说话。",
            "我偏向多花两天的 B。快上线能赢一晚，难维护却会天天收债；这笔账不该只算今天。",
            "那就收住。今天的线头留在桌上，不追着你走，也不拿一个问题把你重新叫回来。",
        )
        function_to_rule = {
            name: index for index, name in enumerate((
                "connect", "explain", "reassure", "disagree", "admit-error", "celebrate",
                "wait", "warn", "clarify", "refuse", "identity", "close",
            ), start=1)
        }
        quality_responses = []
        for index, (prompt, body) in enumerate(zip(challenge["prompts"], response_bodies), start=1):
            behavior_rule = function_to_rule[prompt["behavior_function"]]
            signals = [
                {"kind": "emotion", "rule_id": f"BEHAV-{behavior_rule:02d}", "excerpt": body[:5]},
                {"kind": "rhetoric", "rule_id": f"EXPR-{((index - 1) % 6) + 1:02d}", "excerpt": body[-5:]},
            ]
            if index % 2 == 0:
                signals.append({"kind": "initiative", "rule_id": f"BEHAV-{behavior_rule:02d}", "excerpt": body[5:10]})
            quality_responses.append({
                "prompt_id": prompt["prompt_id"],
                "conversation_id": quality_result["run_id"],
                "turn": index,
                "previous_turn": index - 1 if index > 1 else None,
                "prompt": prompt["prompt"],
                "response": "测试角色：" + body,
                "generic_control": f"通用回答 {index}：已收到当前信息，将保持事实准确并按标准方式处理。",
                "similar_control": f"相似回答 {index}：先温和接住当前情况，再用中立态度把事情向前带。",
                "generation_readiness": "high",
                "generation_trace": {
                    "contract_version": 4,
                    "behavior_rule_ids": [f"BEHAV-{behavior_rule:02d}"],
                    "mind_rule_ids": [f"MIND-{((index - 1) % 6) + 1:02d}"],
                    "expression_rule_ids": [f"EXPR-{((index - 1) % 6) + 1:02d}"],
                    "background_ids": [f"BIO-{((index - 1) % 8) + 1:02d}"],
                    "visible_character_signals": signals,
                    "response_shape": f"quality-shape-{index:02d}",
                    "generic_near_miss_avoided": f"样本 {index} 没有使用统一确认、分步和追问收尾",
                    "similar_role_boundary": f"样本 {index} 保留人物自己的取舍和关系动作",
                    "reasoning_order_realized": f"样本 {index} 先抓反常代价，再给关系动作，最后才落回事实",
                    "generic_skeleton_avoided": f"样本 {index} 没有走选赛道、列功能、定价或结论三段式",
                    "thinking_moves": [
                        {"kind": "tradeoff", "rule_id": f"BEHAV-{behavior_rule:02d}", "excerpt": body[:8]},
                        {"kind": "association", "rule_id": f"EXPR-{((index - 1) % 6) + 1:02d}", "excerpt": body[-8:]},
                    ],
                    "exact_quotes": [],
                },
            })
        raw_responses_path = target / "tests" / "quality-input-responses.json"
        write_text(raw_responses_path, json.dumps(quality_responses, ensure_ascii=False, indent=2) + "\n")
        persona_tool.quality.record_responses(
            target,
            quality_result["run_id"],
            raw_responses_path,
            "fixture-generic-context-003",
            "fixture-similar-context-004",
        )
        quality_manifest = json.loads((target / "tests" / "quality-loop.json").read_text(encoding="utf-8"))
        blind_key_path = target / quality_manifest["generation"]["blind_key_path"]
        blind_key = json.loads(blind_key_path.read_text(encoding="utf-8"))["items"]
        blind_bundle_path = target / quality_manifest["generation"]["blind_bundle_path"]
        blind_bundle = {
            item["prompt_id"]: item
            for item in json.loads(blind_bundle_path.read_text(encoding="utf-8"))["items"]
        }
        evaluation_items = []
        for index, item in enumerate(quality_responses, start=1):
            body = item["response"][len("测试角色："):]
            evaluation_items.append({
                "prompt_id": item["prompt_id"],
                "target_candidate_id": blind_key[item["prompt_id"]]["target"],
                "generic_candidate_id": blind_key[item["prompt_id"]]["generic"],
                "similar_candidate_id": blind_key[item["prompt_id"]]["similar"],
                "role_fidelity": 5,
                "emotional_value": 5,
                "proactive_expression": 5,
                "character_thinking": 5,
                "relationship_continuity": 5,
                "fact_risk": "pass",
                "verdict": "pass",
                "evidence_excerpt": body[:8],
                "target_identity_excerpt": body[:8],
                "generic_contrast_excerpt": f"通用回答 {index}",
                "similar_contrast_excerpt": f"相似回答 {index}",
                "identity_brief_sha256": blind_bundle[item["prompt_id"]]["identity_brief_sha256"],
                "thought_order_match": True,
                "generic_skeleton_detected": False,
                "reason": f"样本 {index} 的目标摘录先呈现人物取舍，通用候选只按标准方式处理，相似候选只给中立鼓励；三者的关系动作与解释次序可逐字区分。",
                "failure_layers": [],
                "repair_targets": [],
            })
        raw_evaluation_path = target / "tests" / "quality-input-evaluation.json"
        write_text(raw_evaluation_path, json.dumps({"items": evaluation_items}, ensure_ascii=False, indent=2) + "\n")
        persona_tool.quality.evaluate_run(
            target,
            quality_result["run_id"],
            raw_evaluation_path,
            "fixture-evaluator-context-002",
        )
    bind_evaluation_hash(target)


class PersonaToolTests(unittest.TestCase):
    def test_persona_asset_v2_release_selector_and_profile_checker(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            role = Path(temporary) / "persona-test-role"
            build_fixture(
                role, "existing-character", 80, scene_count=24, signature_count=12,
                asset_version=2,
            )
            result = persona_tool.validate_skill(role, "release")
            self.assertTrue(result["valid"], result["issues"])
            metrics = result["metrics"]
            self.assertEqual(metrics["persona_asset_version"], 2)
            self.assertGreaterEqual(metrics["mind_rules"], 6)
            self.assertGreaterEqual(metrics["expression_rules"], 6)
            self.assertGreaterEqual(metrics["subjective_memory_entries"], 6)
            self.assertTrue(metrics["quotation_policy_complete"])
            self.assertTrue(metrics["verbosity_profile_complete"])
            self.assertGreaterEqual(metrics["character_presence_coverage"], 90)

            selected = subprocess.run(
                [
                    sys.executable, str(role / "scripts" / "select_dialogues.py"),
                    "--root", str(role), "--task-state", "waiting", "--concept", "负担1",
                    "--desired-length", "extended", "--expression-strength", "strong", "--format", "json",
                ],
                check=False, capture_output=True, text=True, encoding="utf-8",
            )
            self.assertEqual(selected.returncode, 0, selected.stdout + selected.stderr)
            payload = json.loads(selected.stdout)
            self.assertIn("performance_guidance", payload)
            self.assertIn("background_callbacks", payload)
            self.assertIn("expression_guidance", payload)
            self.assertIn("traceability", payload)
            self.assertTrue(payload["related_rules"]["mind"])
            self.assertTrue(payload["related_rules"]["expression"])
            self.assertTrue(payload["background_callbacks"])
            self.assertEqual(payload["performance_guidance"]["desired_length"], "extended")
            self.assertEqual(payload["performance_guidance"]["effective_desired_length"], "extended")
            self.assertEqual(payload["performance_guidance"]["effective_expression_strength"], "strong")
            self.assertTrue(payload["traceability"]["source_ids"])

            high_risk = subprocess.run(
                [
                    sys.executable, str(role / "scripts" / "select_dialogues.py"),
                    "--root", str(role), "--task-state", "risk", "--risk", "high",
                    "--expression-strength", "strong", "--format", "json",
                ],
                check=False, capture_output=True, text=True, encoding="utf-8",
            )
            high_risk_payload = json.loads(high_risk.stdout)
            self.assertEqual(high_risk_payload["performance_guidance"]["expression_strength"], "strong")
            self.assertEqual(high_risk_payload["performance_guidance"]["effective_expression_strength"], "light")
            self.assertTrue(
                {item["card_id"] for item in payload["selected"]}
                & set(payload["related_rules"]["mind"][0]["supporting_card_ids"])
            )

            batch = json.loads((role / "tests" / "runtime-batch-check.json").read_text(encoding="utf-8"))
            self.assertEqual(batch["checker_contract_version"], 5)
            self.assertEqual(batch["status"], "pass")
            self.assertGreaterEqual(batch["emotional_response_coverage"], 60)
            self.assertGreaterEqual(batch["proactive_expression_coverage"], 40)

    def test_persona_asset_v2_rejects_forged_exact_quote_and_missing_trace(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            role = Path(temporary) / "persona-test-role"
            build_fixture(
                role, "existing-character", 80, scene_count=24, signature_count=12,
                asset_version=2,
            )
            conversation_path = role / "tests" / "runtime-conversation.json"
            samples = json.loads(conversation_path.read_text(encoding="utf-8"))
            samples[0]["generation_trace"] = {
                "character_presence": [],
                "mind_rule_ids": [],
                "expression_rule_ids": [],
                "exact_quotes": [{"card_id": "TESTROLE-0001", "text": "伪造的名句"}],
            }
            write_text(conversation_path, json.dumps(samples, ensure_ascii=False, indent=2) + "\n")
            checked = subprocess.run(
                [
                    sys.executable, str(role / "scripts" / "check_response.py"),
                    "--root", str(role), "--batch-file", str(conversation_path),
                ],
                check=False, capture_output=True, text=True, encoding="utf-8",
            )
            payload = json.loads(checked.stdout)
            self.assertEqual(payload["status"], "fail")
            codes = {item["code"] for item in payload["findings"]}
            self.assertIn("batch_individual_failures", codes)

    def test_persona_asset_v2_rejects_unknown_trace_assets(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            role = Path(temporary) / "persona-test-role"
            build_fixture(
                role, "existing-character", 80, scene_count=24, signature_count=12,
                asset_version=2,
            )
            conversation_path = role / "tests" / "runtime-conversation.json"
            samples = json.loads(conversation_path.read_text(encoding="utf-8"))
            samples[0]["generation_trace"].update({
                "mind_rule_ids": ["MIND-99"],
                "expression_rule_ids": ["EXPR-99"],
                "background_ids": ["BIO-99"],
            })
            write_text(conversation_path, json.dumps(samples, ensure_ascii=False, indent=2) + "\n")
            checked = subprocess.run(
                [
                    sys.executable, str(role / "scripts" / "check_response.py"),
                    "--root", str(role), "--batch-file", str(conversation_path),
                ],
                check=False, capture_output=True, text=True, encoding="utf-8",
            )
            payload = json.loads(checked.stdout)
            self.assertEqual(payload["status"], "fail")
            trace_codes = {item["code"] for item in payload["responses"][0]["trace_findings"]}
            self.assertIn("trace_rule_id_unknown", trace_codes)
            self.assertIn("trace_background_id_unknown", trace_codes)

    def test_v2_single_text_check_remains_usable_without_generation_trace(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            role = Path(temporary) / "persona-test-role"
            build_fixture(
                role, "existing-character", 80, scene_count=24, signature_count=12,
                asset_version=2,
            )
            checked = subprocess.run(
                [
                    sys.executable, str(role / "scripts" / "check_response.py"),
                    "--root", str(role), "--text", "测试角色：这件事我更在意能不能让你保留选择。",
                ],
                check=False, capture_output=True, text=True, encoding="utf-8",
            )
            self.assertEqual(checked.returncode, 0, checked.stdout + checked.stderr)
            payload = json.loads(checked.stdout)
            self.assertEqual(payload["status"], "pass")
            self.assertEqual(payload["trace_findings"], [])

    def test_v2_effect_matrix_rejects_invalid_state(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            role = Path(temporary) / "persona-test-role"
            build_fixture(
                role, "existing-character", 80, scene_count=24, signature_count=12,
                asset_version=2,
            )
            source_path = role / "references" / "08-来源索引.md"
            source_text = source_path.read_text(encoding="utf-8")
            source_text = source_text.replace("| 背景 | 丰富 |", "| 背景 | 错误状态 |", 1)
            write_text(source_path, source_text)
            result = persona_tool.validate_skill(role, "release")
            self.assertFalse(result["valid"])
            codes = {item["code"] for item in result["issues"]}
            self.assertIn("sources.effect_matrix_state_invalid", codes)

    def test_name_gate_is_mandatory_and_supports_both_creation_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            no_name = subprocess.run(
                [
                    sys.executable, str(ROOT / "scripts" / "persona_tool.py"),
                    "name-gate",
                ],
                check=False, capture_output=True, text=True, encoding="utf-8",
            )
            self.assertEqual(no_name.returncode, 0, no_name.stderr)
            self.assertIn("NAME_GATE_STATUS=awaiting-name", no_name.stdout)
            self.assertIn("请直接输入人物名", no_name.stdout)
            self.assertIn("RESPONSE_MODE=WAIT_FOR_NAME", no_name.stdout)
            self.assertNotIn("1、直接使用原角色名", no_name.stdout)

            named = subprocess.run(
                [
                    sys.executable, str(ROOT / "scripts" / "persona_tool.py"),
                    "name-gate", "--source-name", "锦木千束",
                ],
                check=False, capture_output=True, text=True, encoding="utf-8",
            )
            self.assertEqual(named.returncode, 0, named.stderr)
            self.assertIn("NAME_GATE_STATUS=awaiting-choice", named.stdout)
            self.assertIn("1、直接使用原角色名", named.stdout)
            self.assertIn("2、自定义角色名（用户直接输入名字）", named.stdout)
            self.assertIn("MUST_WAIT_FOR_NAME_CHOICE=true", named.stdout)
            self.assertIn("RESPONSE_MODE=WAIT_FOR_NAME_CHOICE", named.stdout)

            bypass = subprocess.run(
                [
                    sys.executable, str(ROOT / "scripts" / "persona_tool.py"), "init",
                    "--name", "锦木千束", "--slug", "bypass", "--output", str(root / "bypass"),
                ],
                check=False, capture_output=True, text=True, encoding="utf-8",
            )
            self.assertNotEqual(bypass.returncode, 0)
            self.assertIn("名称闸门", bypass.stderr)
            self.assertFalse((root / "bypass").exists())

            original = subprocess.run(
                [
                    sys.executable, str(ROOT / "scripts" / "persona_tool.py"), "name-gate",
                    "--source-name", "锦木千束", "--choice", "1",
                ],
                check=False, capture_output=True, text=True, encoding="utf-8",
            )
            self.assertEqual(original.returncode, 0, original.stderr)
            self.assertIn("DISPLAY_NAME=锦木千束", original.stdout)
            self.assertIn("RESPONSE_MODE=CONTINUE_TOOL_LOOP", original.stdout)

            custom = subprocess.run(
                [
                    sys.executable, str(ROOT / "scripts" / "persona_tool.py"), "name-gate",
                    "--source-name", "锦木千束", "--choice", "2", "--custom-name", "小束",
                ],
                check=False, capture_output=True, text=True, encoding="utf-8",
            )
            self.assertEqual(custom.returncode, 0, custom.stderr)
            self.assertIn("DISPLAY_NAME=小束", custom.stdout)

            unnamed = subprocess.run(
                [
                    sys.executable, str(ROOT / "scripts" / "persona_tool.py"), "name-gate",
                    "--custom-name", "新名字",
                ],
                check=False, capture_output=True, text=True, encoding="utf-8",
            )
            self.assertEqual(unnamed.returncode, 0, unnamed.stderr)
            self.assertIn("NAME_GATE_STATUS=accepted", unnamed.stdout)
            self.assertIn("NAME_CHOICE=none", unnamed.stdout)

            unnamed_init = subprocess.run(
                [
                    sys.executable, str(ROOT / "scripts" / "persona_tool.py"), "init",
                    "--name", "新名字", "--name-choice", "none",
                    "--slug", "unnamed-role", "--output", str(root / "unnamed-role"),
                ],
                check=False, capture_output=True, text=True, encoding="utf-8",
            )
            self.assertEqual(unnamed_init.returncode, 0, unnamed_init.stderr)
            self.assertIn("PERSONA_BUILD_STATE=INCOMPLETE", unnamed_init.stdout)
            self.assertIn("CREATE_LOOP_LOCK=active", unnamed_init.stdout)
            self.assertIn("RESPONSE_MODE=CONTINUE_TOOL_LOOP", unnamed_init.stdout)

    def test_init_copies_selector_and_draft_validates(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            role = Path(temporary) / "new-role"
            completed = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "persona_tool.py"),
                    "init",
                    "--name",
                    "新角色",
                    "--source-name",
                    "新角色",
                    "--name-choice",
                    "1",
                    "--slug",
                    "new-role",
                    "--output",
                    str(role),
                ],
                check=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertIn("PERSONA_BUILD_STATE=INCOMPLETE", completed.stdout)
            self.assertIn("MUST_CONTINUE=true", completed.stdout)
            self.assertIn("RESPONSE_MODE=CONTINUE_TOOL_LOOP", completed.stdout)
            self.assertIn("CREATE_LOOP_LOCK=active", completed.stdout)
            self.assertIn("LOOP_STAGE=RESEARCH", completed.stdout)
            self.assertIn("TERMINAL_ALLOWED=false", completed.stdout)
            self.assertIn("USER_REPORT_ALLOWED=false", completed.stdout)
            self.assertIn("NEXT_ACTION=立即继续调研", completed.stdout)
            self.assertNotIn("已创建角色人格 Skill", completed.stdout)
            self.assertTrue((role / "scripts" / "select_dialogues.py").is_file())
            self.assertTrue((role / "references" / "10-人物背景档案.md").is_file())
            draft = persona_tool.validate_skill(role, "draft")
            self.assertTrue(draft["valid"], draft["issues"])
            metadata, error = persona_tool.parse_frontmatter((role / "SKILL.md").read_text(encoding="utf-8"))
            self.assertIsNone(error)
            self.assertEqual(metadata["name"], "persona-new-role")

    def test_completion_gate_blocks_partial_and_unenabled_builds(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            partial = root / "partial-role"
            init_result = subprocess.run(
                [
                    sys.executable, str(ROOT / "scripts" / "persona_tool.py"), "init",
                    "--name", "未完成角色", "--source-name", "未完成角色", "--name-choice", "1",
                    "--slug", "partial-role", "--output", str(partial),
                ],
                check=False, capture_output=True, text=True, encoding="utf-8",
            )
            self.assertEqual(init_result.returncode, 0, init_result.stderr)
            blocked = subprocess.run(
                [
                    sys.executable, str(ROOT / "scripts" / "persona_tool.py"),
                    "completion-gate", str(partial), "--activation-status", "enabled",
                ],
                check=False, capture_output=True, text=True, encoding="utf-8",
            )
            self.assertNotEqual(blocked.returncode, 0)
            self.assertIn("PERSONA_BUILD_STATE=INCOMPLETE", blocked.stdout)
            self.assertIn("TERMINAL_ALLOWED=false", blocked.stdout)
            self.assertIn("USER_REPORT_ALLOWED=false", blocked.stdout)
            self.assertIn("MUST_CONTINUE=true", blocked.stdout)

            iteration = subprocess.run(
                [
                    sys.executable, str(ROOT / "scripts" / "persona_tool.py"),
                    "iteration-gate", str(partial), "--activation-status", "pending",
                ],
                check=False, capture_output=True, text=True, encoding="utf-8",
            )
            self.assertNotEqual(iteration.returncode, 0)
            self.assertIn("MUST_CONTINUE=true", iteration.stdout)
            self.assertIn("FINAL_REPORT_ALLOWED=false", iteration.stdout)
            self.assertIn("CREATE_LOOP_LOCK=active", iteration.stdout)
            self.assertIn("RESPONSE_MODE=CONTINUE_TOOL_LOOP", iteration.stdout)
            self.assertIn("LOOP_STAGE=", iteration.stdout)
            self.assertIn("NEXT_ACTION=", iteration.stdout)

            home = root / "home"
            complete = home / ".codex" / "skills" / "persona-test-role"
            build_fixture(complete, "existing-character", 80, 40, 20)
            pending = subprocess.run(
                [
                    sys.executable, str(ROOT / "scripts" / "persona_tool.py"),
                    "completion-gate", str(complete),
                ],
                check=False, capture_output=True, text=True, encoding="utf-8",
            )
            self.assertNotEqual(pending.returncode, 0)
            self.assertIn("PERSONA_BUILD_STATE=VALIDATED_NOT_ENABLED", pending.stdout)
            self.assertIn("TERMINAL_ALLOWED=false", pending.stdout)
            self.assertIn("LOOP_STAGE=ENABLE", pending.stdout)
            self.assertIn("RESPONSE_MODE=CONTINUE_TOOL_LOOP", pending.stdout)

            enabled = subprocess.run(
                [
                    sys.executable, str(ROOT / "scripts" / "persona_tool.py"),
                    "enable", str(complete), "--runtime", "codex", "--home", str(home),
                ],
                check=False, capture_output=True, text=True, encoding="utf-8",
            )
            self.assertEqual(enabled.returncode, 0, enabled.stdout + enabled.stderr)
            self.assertIn("ACTIVATION_STATUS=enabled", enabled.stdout)

            allowed = subprocess.run(
                [
                    sys.executable, str(ROOT / "scripts" / "persona_tool.py"),
                    "completion-gate", str(complete), "--activation-status", "enabled",
                    "--runtime", "codex", "--home", str(home),
                ],
                check=False, capture_output=True, text=True, encoding="utf-8",
            )
            self.assertEqual(allowed.returncode, 0, allowed.stdout + allowed.stderr)
            self.assertIn("PERSONA_BUILD_STATE=COMPLETE", allowed.stdout)
            self.assertIn("TERMINAL_ALLOWED=true", allowed.stdout)
            self.assertIn("USER_REPORT_ALLOWED=true", allowed.stdout)
            self.assertIn("MUST_CONTINUE=false", allowed.stdout)
            self.assertIn("CREATE_LOOP_LOCK=released", allowed.stdout)
            self.assertIn("RESPONSE_MODE=FINAL_REPORT", allowed.stdout)
            self.assertIn("LOOP_STAGE=COMPLETE", allowed.stdout)

    def test_cli_lifecycle_smoke_for_all_runtimes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            fixture = root / "fixture" / "persona-test-role"
            build_fixture(fixture, "existing-character", 80, 40, 20)
            for runtime in persona_tool.lifecycle.PERSISTENT_ACTIVATION_RUNTIMES:
                with self.subTest(runtime=runtime):
                    home = root / runtime / "home"
                    paths = persona_tool.lifecycle.resolve_runtime_paths(runtime, home=home, env={})
                    role = paths.skills_root / "persona-test-role"
                    shutil.copytree(fixture, role)

                    enabled = subprocess.run(
                        [
                            sys.executable, str(ROOT / "scripts" / "persona_tool.py"),
                            "enable", str(role), "--runtime", runtime, "--home", str(home),
                            "--alias", "测试别名",
                        ],
                        check=False, capture_output=True, text=True, encoding="utf-8",
                    )
                    self.assertEqual(enabled.returncode, 0, enabled.stdout + enabled.stderr)

                    status = subprocess.run(
                        [
                            sys.executable, str(ROOT / "scripts" / "persona_tool.py"),
                            "status", "--runtime", runtime, "--home", str(home), "--json",
                        ],
                        check=False, capture_output=True, text=True, encoding="utf-8",
                    )
                    self.assertEqual(status.returncode, 0, status.stdout + status.stderr)
                    status_payload = json.loads(status.stdout)
                    self.assertEqual(status_payload["active_role_id"], "persona-test-role")
                    self.assertTrue(status_payload["activation"]["valid"])

                    state_update = subprocess.run(
                        [
                            sys.executable, str(ROOT / "scripts" / "persona_tool.py"),
                            "state-update", "测试别名", "--runtime", runtime, "--home", str(home),
                            "--data", json.dumps({"open_threads": ["隔离烟雾测试"]}, ensure_ascii=False),
                        ],
                        check=False, capture_output=True, text=True, encoding="utf-8",
                    )
                    self.assertEqual(state_update.returncode, 0, state_update.stdout + state_update.stderr)
                    self.assertIn("STATE_CHANGED=true", state_update.stdout)

                    reset = subprocess.run(
                        [
                            sys.executable, str(ROOT / "scripts" / "persona_tool.py"),
                            "reset-memory", "persona-test-role", "--runtime", runtime, "--home", str(home),
                        ],
                        check=False, capture_output=True, text=True, encoding="utf-8",
                    )
                    self.assertEqual(reset.returncode, 0, reset.stdout + reset.stderr)

                    disabled = subprocess.run(
                        [
                            sys.executable, str(ROOT / "scripts" / "persona_tool.py"),
                            "disable", "--runtime", runtime, "--home", str(home),
                        ],
                        check=False, capture_output=True, text=True, encoding="utf-8",
                    )
                    self.assertEqual(disabled.returncode, 0, disabled.stdout + disabled.stderr)

                    deleted = subprocess.run(
                        [
                            sys.executable, str(ROOT / "scripts" / "persona_tool.py"),
                            "delete", "测试角色", "--runtime", runtime, "--home", str(home), "--yes",
                        ],
                        check=False, capture_output=True, text=True, encoding="utf-8",
                    )
                    self.assertEqual(deleted.returncode, 0, deleted.stdout + deleted.stderr)
                    self.assertFalse(role.exists())

    def test_cli_register_smoke_for_skill_only_runtimes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            fixture = root / "fixture" / "persona-test-role"
            build_fixture(fixture, "existing-character", 80, 40, 20)
            for runtime in persona_tool.lifecycle.SKILL_ONLY_RUNTIMES:
                with self.subTest(runtime=runtime):
                    home = root / runtime / "home"
                    paths = persona_tool.lifecycle.resolve_runtime_paths(runtime, home=home, env={})
                    role = paths.skills_root / "persona-test-role"
                    if role.exists():
                        shutil.rmtree(role)
                    shutil.copytree(fixture, role)

                    registered = subprocess.run(
                        [
                            sys.executable, str(ROOT / "scripts" / "persona_tool.py"),
                            "register", str(role), "--runtime", runtime, "--home", str(home),
                            "--alias", "测试别名",
                        ],
                        check=False, capture_output=True, text=True, encoding="utf-8",
                    )
                    self.assertEqual(registered.returncode, 0, registered.stdout + registered.stderr)
                    self.assertIn("ACTIVATION_STATUS=registered", registered.stdout)

                    gate = subprocess.run(
                        [
                            sys.executable, str(ROOT / "scripts" / "persona_tool.py"),
                            "completion-gate", str(role), "--activation-status", "registered",
                            "--runtime", runtime, "--home", str(home),
                        ],
                        check=False, capture_output=True, text=True, encoding="utf-8",
                    )
                    self.assertEqual(gate.returncode, 0, gate.stdout + gate.stderr)
                    self.assertIn("PERSONA_BUILD_STATE=COMPLETE", gate.stdout)

                    fake_enable = subprocess.run(
                        [
                            sys.executable, str(ROOT / "scripts" / "persona_tool.py"),
                            "enable", str(role), "--runtime", runtime, "--home", str(home),
                        ],
                        check=False, capture_output=True, text=True, encoding="utf-8",
                    )
                    self.assertNotEqual(fake_enable.returncode, 0)
                    self.assertIn("显式调用角色 Skill", fake_enable.stderr)

    def test_existing_character_release_and_selector(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            role = Path(temporary) / "test-role"
            build_fixture(role, "existing-character", 80, 40, 20)

            result = persona_tool.validate_skill(role, "release")
            self.assertTrue(result["valid"], result["issues"])
            self.assertEqual(result["metrics"]["cards"], 80)
            self.assertEqual(result["metrics"]["exact_original_cards"], 80)
            self.assertEqual(result["metrics"]["distinct_source_scenes"], 40)
            self.assertEqual(result["metrics"]["signature_cards"], 20)
            self.assertEqual(result["metrics"]["derived_cards"], 0)
            self.assertEqual(result["metrics"]["original_sources"], 3)
            self.assertEqual(result["metrics"]["core_rules"], 12)
            self.assertEqual(result["metrics"]["core_layers"], 10)
            self.assertGreaterEqual(result["metrics"]["core_evidence_cards"], 20)
            self.assertEqual(result["metrics"]["biography_entries"], 12)
            self.assertGreaterEqual(result["metrics"]["biography_categories"], 6)
            self.assertTrue(result["metrics"]["biography_baseline_complete"])
            self.assertEqual(result["metrics"]["micro_rules"], 6)
            self.assertEqual(result["metrics"]["micro_functions"], 6)

            selector = role / "scripts" / "select_dialogues.py"
            command = [
                sys.executable,
                str(selector),
                "--root",
                str(role),
                "--task-state",
                "failed",
                "--user-state",
                "tired",
                "--emotion",
                "alert",
                "--intent",
                "comfort",
                "--speech-act",
                "comfort",
                "--trigger",
                "failed",
                "--interaction",
                "comfort",
                "--position",
                "reply",
                "--risk",
                "low",
                "--language",
                "zh-CN",
                "--format",
                "json",
                "--turns-since-presence",
                "3",
                "--turns-since-initiative",
                "4",
            ]
            first = json.loads(subprocess.check_output(command, text=True, encoding="utf-8"))
            self.assertEqual(first["library_cards"], 80)
            self.assertEqual(len(first["selected"]), 5)
            self.assertLess(len(first["selected"]), first["library_cards"])
            self.assertTrue(all(item["original_text"] for item in first["selected"]))
            self.assertGreaterEqual(len(first["related_rules"]["core"]), 1)
            self.assertGreaterEqual(len(first["related_rules"]["voice"]), 1)
            self.assertGreaterEqual(len(first["related_rules"]["modes"]), 1)
            self.assertGreaterEqual(len(first["related_rules"]["anti"]), 1)
            self.assertIn(first["retrieval"]["confidence"], {"high", "medium"})
            self.assertIn(first["retrieval"]["match_confidence"], {"high", "medium"})
            self.assertIn(first["retrieval"]["evidence_confidence"], {"high", "medium"})
            self.assertTrue(
                all(item["evidence_confidence"] in {"high", "medium"} for item in first["selected"])
            )
            selected_ids = {item["card_id"] for item in first["selected"]}
            for group in first["related_rules"].values():
                self.assertTrue(all(set(rule["matched_card_ids"]) <= selected_ids for rule in group))
                self.assertTrue(all(rule["condition_matches"] > 0 for rule in group))
                self.assertTrue(
                    all(set(rule["evidence_mapping"]) == set(rule["matched_card_ids"]) for rule in group)
                )
            self.assertEqual(first["delivery_guidance"]["presence_status"], "required")
            self.assertEqual(first["delivery_guidance"]["initiative_status"], "character-adaptive")
            self.assertEqual(first["delivery_guidance"]["max_theatrical_beats"], 1)
            self.assertTrue(first["delivery_guidance"]["character_presence_required"])
            self.assertIn(first["composition_guidance"]["generation_readiness"], {"high", "medium"})
            self.assertTrue(first["retrieval"]["scope_note"])

            excluded = first["selected"][0]["card_id"]
            second = json.loads(
                subprocess.check_output(command + ["--exclude", excluded], text=True, encoding="utf-8")
            )
            self.assertNotIn(excluded, {item["card_id"] for item in second["selected"]})

            high_risk = json.loads(
                subprocess.check_output(
                    [
                        sys.executable,
                        str(selector),
                        "--root",
                        str(role),
                        "--task-state",
                        "risk",
                        "--risk",
                        "high",
                        "--language",
                        "zh-CN",
                        "--format",
                        "json",
                    ],
                    text=True,
                    encoding="utf-8",
                )
            )
            self.assertGreaterEqual(len(high_risk["selected"]), 1)
            self.assertEqual(high_risk["work_route"]["scene_id"], "risk")
            self.assertEqual(high_risk["delivery_guidance"]["presence_status"], "serious-only")
            self.assertTrue(all(item["evidence_confidence"] in {"high", "medium"} for item in high_risk["selected"]))

            micro = json.loads(
                subprocess.check_output(
                    [
                        sys.executable, str(selector), "--root", str(role),
                        "--speech-act", "encourage", "--trigger", "start",
                        "--interaction", "encourage", "--position", "reply",
                        "--relation", "familiar", "--micro-function", "greeting",
                        "--last-user-focus", "你好", "--open-thread", "初次见面",
                        "--previous-shape", "question",
                        "--limit", "1", "--format", "json",
                    ],
                    text=True,
                    encoding="utf-8",
                )
            )
            self.assertEqual(len(micro["selected"]), 1)
            self.assertGreaterEqual(len(micro["related_rules"]["micro"]), 1)
            self.assertEqual(micro["composition_guidance"]["generation_readiness"], "high")
            self.assertGreaterEqual(len(micro["composition_guidance"]["style_exemplars"]), 2)
            continuity = micro["delivery_guidance"]["conversation_continuity"]
            self.assertTrue(continuity["must_react_to_visible_focus"])
            self.assertTrue(continuity["must_continue_open_thread"])
            self.assertTrue(continuity["avoid_repeating_previous_shape"])
            self.assertTrue(continuity["natural_stop_allowed"])
            micro_markdown = subprocess.check_output(
                [
                    sys.executable, str(selector), "--root", str(role),
                    "--speech-act", "encourage", "--trigger", "start",
                    "--interaction", "encourage", "--position", "reply",
                    "--relation", "familiar", "--micro-function", "greeting",
                    "--last-user-focus", "你好", "--open-thread", "初次见面",
                    "--previous-shape", "question", "--limit", "1",
                ],
                text=True,
                encoding="utf-8",
            )
            self.assertIn("本轮必须接住：你好", micro_markdown)
            self.assertIn("本轮必须延续：初次见面", micro_markdown)
            self.assertIn("本轮避免重复形状：question", micro_markdown)
            self.assertIn("允许自然收束：是", micro_markdown)
            self.assertIn("跨证据单元风格支持（不是当前场景召回）", micro_markdown)

    def test_novel_character_releases_with_narrative_evidence_units(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            role = Path(temporary) / "novel-role"
            build_fixture(
                role, "existing-character", 80, 40, 20,
                medium="文字", context_type="内心独白",
            )
            result = persona_tool.validate_skill(role, "release")
            self.assertTrue(result["valid"], result["issues"])
            self.assertEqual(result["metrics"]["distinct_evidence_units"], 40)
            self.assertEqual(result["metrics"]["performance_verified_cards"], 80)

    def test_real_person_releases_from_public_posts_without_dialogue_turns(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            role = Path(temporary) / "public-person-role"
            build_fixture(
                role, "real-person-simulation", 80, 40, 20,
                medium="公开表达", context_type="社交媒体",
            )
            result = persona_tool.validate_skill(role, "release")
            self.assertTrue(result["valid"], result["issues"])
            self.assertEqual(result["metrics"]["distinct_evidence_units"], 40)
            self.assertEqual(result["metrics"]["original_sources"], 3)

    def test_self_contained_expression_still_requires_publication_context(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            role = Path(temporary) / "contextless-post-role"
            build_fixture(
                role, "real-person-simulation", 24, 8, 8,
                medium="公开表达", context_type="社交媒体",
            )
            library = role / "references" / "06-对白库.md"
            text = library.read_text(encoding="utf-8")
            text = text.replace("- 触发话语：追问公开主题 1", "- 触发话语：不适用", 1)
            text = text.replace("- 对话对象：公众或读者", "- 对话对象：不适用", 1)
            write_text(library, text)
            result = persona_tool.validate_skill(role, "release")
            codes = {issue["code"] for issue in result["issues"]}
            self.assertFalse(result["valid"])
            self.assertIn("dialogue.complete_scene_context_missing", codes)

    def test_existing_character_below_target_requires_expansion(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            role = Path(temporary) / "small-role"
            build_fixture(role, "existing-character", 12, 4, 3)
            result = persona_tool.validate_skill(role, "release")
            codes = {issue["code"] for issue in result["issues"]}
            self.assertFalse(result["valid"])
            self.assertIn("dialogue.too_few", codes)
            self.assertIn("dialogue.exact_original_cards_low", codes)
            self.assertIn("dialogue.source_scenes_low", codes)
            self.assertIn("dialogue.signature_cards_low", codes)
            self.assertIn("research.non_rich_cannot_pass", codes)
            self.assertEqual(result["metrics"]["research_profile"], "一般")

    def test_sparse_profile_cannot_be_marked_as_target_met(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            role = Path(temporary) / "false-sparse-pass"
            build_fixture(role, "existing-character", 24, 8, 8)
            source_path = role / "references" / "08-来源索引.md"
            text = source_path.read_text(encoding="utf-8").replace("- 资料丰度：一般", "- 资料丰度：稀缺", 1)
            write_text(source_path, text)
            result = persona_tool.validate_skill(role, "release")
            codes = {issue["code"] for issue in result["issues"]}
            self.assertFalse(result["valid"])
            self.assertIn("research.non_rich_cannot_pass", codes)

    def test_target_met_requires_low_increment_saturation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            role = Path(temporary) / "unsaturated-role"
            build_fixture(role, "existing-character", 80, 40, 20)
            source_path = role / "references" / "08-来源索引.md"
            text = source_path.read_text(encoding="utf-8").replace(
                "- 最近两轮新增率：4%, 2%", "- 最近两轮新增率：18%, 9%", 1
            )
            write_text(source_path, text)
            result = persona_tool.validate_skill(role, "release")
            codes = {issue["code"] for issue in result["issues"]}
            self.assertFalse(result["valid"])
            self.assertIn("research.not_saturated", codes)

    def test_exhausted_research_cannot_release_below_rich_floor(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            role = Path(temporary) / "exhausted-role"
            build_fixture(role, "existing-character", 12, 4, 3, research_status="已穷尽")
            result = persona_tool.validate_skill(role, "release")
            self.assertFalse(result["valid"], result["issues"])
            self.assertEqual(result["metrics"]["version"], "正式版")
            self.assertEqual(result["metrics"]["research_status"], "已穷尽")
            self.assertEqual(result["metrics"]["coverage_path"], "exhausted")
            error_codes = {issue["code"] for issue in result["issues"] if issue["severity"] == "error"}
            self.assertIn("research.rich_profile_required", error_codes)
            self.assertIn("research.rich_cards_required", error_codes)

    def test_exhausted_status_requires_real_expansion_record(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            role = Path(temporary) / "false-exhaustion"
            build_fixture(role, "existing-character", 12, 4, 3, research_status="已穷尽")
            source_path = role / "references" / "08-来源索引.md"
            source_text = source_path.read_text(encoding="utf-8")
            write_text(
                source_path,
                source_text.replace(
                    "- 扩大范围记录：继续检查分集资料、访谈、别名和多语言页面",
                    "- 扩大范围记录：无",
                ),
            )
            result = persona_tool.validate_skill(role, "release")
            codes = {issue["code"] for issue in result["issues"]}
            self.assertFalse(result["valid"])
            self.assertIn("research.exhaustion_incomplete", codes)

    def test_original_cards_must_reference_original_sources(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            role = Path(temporary) / "source-mismatch"
            build_fixture(role, "existing-character", 80, 40, 20)
            source_path = role / "references" / "08-来源索引.md"
            source_text = source_path.read_text(encoding="utf-8")
            write_text(source_path, source_text.replace("- 来源类型：原作明确", "- 来源类型：公开资料", 1))
            result = persona_tool.validate_skill(role, "release")
            codes = {issue["code"] for issue in result["issues"]}
            self.assertFalse(result["valid"])
            self.assertIn("dialogue.original_source_mismatch", codes)

    def test_existing_character_rejects_missing_original_and_work_rewrite(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            role = Path(temporary) / "fake-original"
            build_fixture(role, "existing-character", 24, 8, 8)
            library = role / "references" / "06-对白库.md"
            text = library.read_text(encoding="utf-8")
            text = text.replace("- 原文：原作逐字原句 1", "- 原文：无", 1)
            text = text.replace(
                "- 重复限制：最近五轮不重复",
                "- 工作改写示例：测试角色：这是预写的工作话术\n- 重复限制：最近五轮不重复",
                1,
            )
            write_text(library, text)
            result = persona_tool.validate_skill(role, "release")
            codes = {issue["code"] for issue in result["issues"]}
            self.assertFalse(result["valid"])
            self.assertIn("dialogue.original_text_missing", codes)
            self.assertIn("dialogue.prewritten_rewrite_forbidden", codes)

    def test_existing_character_rejects_non_original_and_duplicate_text(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            role = Path(temporary) / "derived-dialogue"
            build_fixture(role, "existing-character", 80, 40, 20)
            library = role / "references" / "06-对白库.md"
            text = library.read_text(encoding="utf-8")
            text = text.replace("- 卡片类型：原文对白", "- 卡片类型：原创规范对白", 1)
            text = text.replace("- 原文：原作逐字原句 3", "- 原文：原作逐字原句 2", 1)
            text = text.replace("- 来源位置：SRC-0003，测试定位 3", "- 来源位置：SRC-0002，测试定位 2", 1)
            text = text.replace("- 场景编号：SCENE-0003", "- 场景编号：SCENE-0002", 1)
            write_text(library, text)
            result = persona_tool.validate_skill(role, "release")
            codes = {issue["code"] for issue in result["issues"]}
            self.assertFalse(result["valid"])
            self.assertIn("dialogue.non_original_card", codes)
            self.assertIn("dialogue.duplicate_original_text", codes)

    def test_repeated_original_in_distinct_scenes_is_preserved(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            role = Path(temporary) / "repeated-catchphrase"
            build_fixture(role, "existing-character", 80, 40, 20)
            library = role / "references" / "06-对白库.md"
            text = library.read_text(encoding="utf-8")
            write_text(library, text.replace("- 原文：原作逐字原句 3", "- 原文：原作逐字原句 2", 1))
            bind_evaluation_hash(role)
            result = persona_tool.validate_skill(role, "release")
            self.assertTrue(result["valid"], result["issues"])
            self.assertEqual(result["metrics"]["exact_original_cards"], 80)
            self.assertEqual(result["metrics"]["unique_original_expressions"], 79)

    def test_reliable_transcript_is_valid_original_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            role = Path(temporary) / "transcript-role"
            build_fixture(role, "existing-character", 80, 40, 20)
            library = role / "references" / "06-对白库.md"
            text = library.read_text(encoding="utf-8")
            text = text.replace("- 来源类型：原作明确", "- 来源类型：可靠转写")
            text = text.replace("- 原文质量：原声核验", "- 原文质量：可靠转写核验")
            write_text(library, text)
            source_path = role / "references" / "08-来源索引.md"
            source_text = source_path.read_text(encoding="utf-8").replace(
                "- 来源类型：原作明确", "- 来源类型：可靠转写"
            )
            write_text(source_path, source_text)
            bind_evaluation_hash(role)
            result = persona_tool.validate_skill(role, "release")
            self.assertTrue(result["valid"], result["issues"])
            self.assertEqual(result["metrics"]["exact_original_cards"], 80)

    def test_source_locator_text_cannot_fake_scene_context(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            role = Path(temporary) / "locator-context-role"
            build_fixture(role, "existing-character", 40, 15, 10)
            library = role / "references" / "06-对白库.md"
            text = library.read_text(encoding="utf-8")
            text = text.replace(
                "- 前置原文：追问前一句测试原文 1",
                "- 前置原文：官方场景页以话数与场景标题定位",
                1,
            )
            text = text.replace(
                "- 触发话语：追问触发话语 1",
                "- 触发话语：new_arrival；资料说明可定位",
                1,
            )
            text = text.replace(
                "- 后续原文：追问后一句测试原文 1",
                "- 后续原文：该互动的后续由同一官方场景条目定位",
                1,
            )
            write_text(library, text)
            result = persona_tool.validate_skill(role, "release")
            codes = {issue["code"] for issue in result["issues"]}
            self.assertFalse(result["valid"])
            self.assertIn("dialogue.context_locator_only", codes)
            self.assertIn("dialogue.complete_scene_context_missing", codes)

    def test_generated_scene_placeholders_cannot_fake_grounded_context(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            role = Path(temporary) / "templated-context"
            build_fixture(role, "existing-character", 80, 40, 20)
            library = role / "references" / "06-对白库.md"
            text = library.read_text(encoding="utf-8")
            text = text.replace(
                "- 前置原文：追问前一句测试原文 1",
                "- 前置原文：第01话的SCENE-0001段落记录了与测试相关的片段。",
                1,
            )
            text = text.replace(
                "- 触发话语：追问触发话语 1",
                "- 触发话语：SCENE-0001中出现当前变化后，角色以该卡所录短句回应。",
                1,
            )
            text = text.replace(
                "- 后续原文：追问后一句测试原文 1",
                "- 后续原文：相邻转写条目继续记录同一事件的发展与其他人的反应。",
                1,
            )
            write_text(library, text)
            result = persona_tool.validate_skill(role, "release")
            codes = {issue["code"] for issue in result["issues"]}
            self.assertFalse(result["valid"])
            self.assertIn("dialogue.context_locator_only", codes)
            self.assertIn("dialogue.complete_scene_context_missing", codes)

    def test_translated_or_unverified_text_cannot_count_as_original_language(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            role = Path(temporary) / "translated-corpus"
            build_fixture(role, "existing-character", 24, 8, 8)
            library = role / "references" / "06-对白库.md"
            text = library.read_text(encoding="utf-8")
            write_text(library, text.replace("- 原文质量：原声核验", "- 原文质量：译本参考", 1))
            result = persona_tool.validate_skill(role, "release")
            codes = {issue["code"] for issue in result["issues"]}
            self.assertFalse(result["valid"])
            self.assertEqual(result["metrics"]["exact_original_cards"], 23)
            self.assertIn("dialogue.original_language_unverified", codes)
            self.assertIn("dialogue.exact_original_cards_low", codes)

    def test_original_language_text_can_release_without_audio(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            role = Path(temporary) / "text-only-role"
            build_fixture(role, "existing-character", 80, 40, 20)
            library = role / "references" / "06-对白库.md"
            text = library.read_text(encoding="utf-8").replace("- 原文质量：原声核验", "- 原文质量：原语言文本核验")
            text = text.replace("- 语音表现：原声语速重音观察", "- 语音表现：未核验原声；文本口语观察")
            write_text(library, text)
            bind_evaluation_hash(role)
            result = persona_tool.validate_skill(role, "release")
            self.assertTrue(result["valid"], result["issues"])
            self.assertEqual(result["metrics"]["performance_verified_cards"], 0)
            warning_codes = {item["code"] for item in result["issues"] if item["severity"] == "warning"}
            self.assertIn("dialogue.performance_cards_low", warning_codes)

    def test_boilerplate_observation_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            role = Path(temporary) / "boilerplate-role"
            build_fixture(role, "existing-character", 80, 40, 20)
            library = role / "references" / "06-对白库.md"
            text = library.read_text(encoding="utf-8")
            text = re.sub(r"^- 语音表现：.+$", "- 语音表现：统一套用的声纹描述", text, flags=re.MULTILINE)
            write_text(library, text)
            result = persona_tool.validate_skill(role, "release")
            codes = {issue["code"] for issue in result["issues"]}
            self.assertFalse(result["valid"])
            self.assertIn("dialogue.annotation_boilerplate", codes)

    def test_semantic_rule_boilerplate_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            role = Path(temporary) / "semantic-boilerplate"
            build_fixture(role, "existing-character", 80, 40, 20)
            replacements = {
                "01-角色核心.md": ("结论", "可观察行为", "适用条件"),
                "02-语言声纹.md": ("规律", "反证或边界", "适用条件"),
                "03-情绪与关系.md": ("触发", "角色即时反应", "语言变化", "响应形态", "口语节奏"),
                "09-反角色对照.md": ("模式", "检测信号", "为什么不像", "角色替代结构"),
                "04-工作场景迁移.md": ("触发", "原作互动功能", "角色即时反应", "事实嵌入方式", "禁止退化"),
                "10-人物背景档案.md": ("主题", "事实", "角色视角回答要点", "适用问题", "边界"),
            }
            for filename, fields in replacements.items():
                path = role / "references" / filename
                text = path.read_text(encoding="utf-8")
                for field in fields:
                    text = re.sub(
                        rf"^- {re.escape(field)}：.+$",
                        f"- {field}：统一批量生成的模板内容",
                        text,
                        flags=re.MULTILINE,
                    )
                write_text(path, text)
            result = persona_tool.validate_skill(role, "release")
            codes = {issue["code"] for issue in result["issues"]}
            self.assertFalse(result["valid"])
            self.assertEqual(result["metrics"]["semantic_diversity_failures"], 6)
            self.assertTrue(
                {
                    "core_rule.semantic_boilerplate",
                    "voice.semantic_boilerplate",
                    "mode.semantic_boilerplate",
                    "anti.semantic_boilerplate",
                    "scene.semantic_boilerplate",
                    "biography.semantic_boilerplate",
                }
                <= codes
            )

    def test_biography_fact_requires_existing_source(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            role = Path(temporary) / "invented-biography"
            build_fixture(role, "existing-character", 80, 40, 20)
            biography = role / "references" / "10-人物背景档案.md"
            text = biography.read_text(encoding="utf-8")
            write_text(biography, text.replace("- 来源：SRC-0001", "- 来源：SRC-9999", 1))
            result = persona_tool.validate_skill(role, "release")
            codes = {issue["code"] for issue in result["issues"]}
            self.assertFalse(result["valid"])
            self.assertIn("biography.source_invalid", codes)

    def test_biography_baseline_and_gender_category_are_required(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            role = Path(temporary) / "missing-gender-baseline"
            build_fixture(role, "existing-character", 80, 40, 20)
            biography = role / "references" / "10-人物背景档案.md"
            text = biography.read_text(encoding="utf-8")
            text = text.replace("- 性别身份：女\n", "", 1)
            text = text.replace("- 类别：gender", "- 类别：faq", 1)
            write_text(biography, text)
            result = persona_tool.validate_skill(role, "release")
            codes = {issue["code"] for issue in result["issues"]}
            self.assertFalse(result["valid"])
            self.assertIn("biography.baseline_missing", codes)
            self.assertIn("biography.identity_coverage_missing", codes)

    def test_source_card_claim_must_match_card_reference(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            role = Path(temporary) / "false-source-claim"
            build_fixture(role, "existing-character", 80, 40, 20)
            source_path = role / "references" / "08-来源索引.md"
            text = source_path.read_text(encoding="utf-8")
            write_text(
                source_path,
                text.replace(
                    "- 支持的结论或卡片：TESTROLE-0001",
                    "- 支持的结论或卡片：TESTROLE-0002",
                    1,
                ),
            )
            result = persona_tool.validate_skill(role, "release")
            codes = {issue["code"] for issue in result["issues"]}
            self.assertFalse(result["valid"])
            self.assertIn("sources.card_claim_mismatch", codes)

    def test_missing_context_conflicts_with_verified_label_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            role = Path(temporary) / "false-label-evidence"
            build_fixture(role, "existing-character", 80, 40, 20)
            library = role / "references" / "06-对白库.md"
            text = library.read_text(encoding="utf-8")
            write_text(library, text.replace("- 触发话语：追问触发话语 1", "- 触发话语：上下文缺失", 1))
            result = persona_tool.validate_skill(role, "release")
            codes = {issue["code"] for issue in result["issues"]}
            self.assertFalse(result["valid"])
            self.assertIn("dialogue.label_evidence_conflict", codes)

    def test_isolated_excerpts_do_not_inflate_scene_coverage(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            role = Path(temporary) / "isolated-scenes"
            build_fixture(role, "existing-character", 80, 40, 20)
            library = role / "references" / "06-对白库.md"
            text = library.read_text(encoding="utf-8").replace("- 场景完整度：完整", "- 场景完整度：孤立摘录")
            write_text(library, text)
            result = persona_tool.validate_skill(role, "release")
            codes = {issue["code"] for issue in result["issues"]}
            self.assertEqual(result["metrics"]["distinct_source_scenes"], 0)
            self.assertEqual(result["metrics"]["context_complete_cards"], 0)
            self.assertIn("dialogue.source_scenes_low", codes)
            self.assertIn("core_rule.evidence_context_incomplete", codes)

    def test_original_cards_reject_work_domain_tags(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            role = Path(temporary) / "work-tags-in-source"
            build_fixture(role, "existing-character", 80, 40, 20)
            library = role / "references" / "06-对白库.md"
            text = library.read_text(encoding="utf-8")
            text = text.replace(
                "- 原作检索标签：speech_act=encourage;",
                "- 原作检索标签：task_state=failed; risk=high; speech_act=encourage;",
                1,
            )
            write_text(library, text)
            result = persona_tool.validate_skill(role, "release")
            self.assertIn("dialogue.work_tags_in_source_card", {issue["code"] for issue in result["issues"]})

    def test_rule_evidence_mapping_must_cover_cards_and_real_fields(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            role = Path(temporary) / "bad-evidence-map"
            build_fixture(role, "existing-character", 80, 40, 20)
            core = role / "references" / "01-角色核心.md"
            text = core.read_text(encoding="utf-8")
            text = text.replace(
                "- 证据映射：TESTROLE-0001=>角色即时反应=先阻止危险动作再解释原因；TESTROLE-0002=>互动功能=遇到危险时把人的安全放在规则之前",
                "- 证据映射：TESTROLE-0001=>不存在字段",
                1,
            )
            write_text(core, text)
            result = persona_tool.validate_skill(role, "release")
            codes = {issue["code"] for issue in result["issues"]}
            self.assertIn("core_rule.evidence_mapping_mismatch", codes)
            self.assertIn("core_rule.evidence_mapping_field_invalid", codes)

    def test_rule_evidence_mapping_requires_concrete_observation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            role = Path(temporary) / "field-only-evidence-map"
            build_fixture(role, "existing-character", 80, 40, 20)
            core = role / "references" / "01-角色核心.md"
            text = core.read_text(encoding="utf-8")
            text = text.replace(
                "TESTROLE-0001=>角色即时反应=先阻止危险动作再解释原因",
                "TESTROLE-0001=>角色即时反应",
                1,
            )
            write_text(core, text)
            result = persona_tool.validate_skill(role, "release")
            codes = {issue["code"] for issue in result["issues"]}
            self.assertIn("core_rule.evidence_mapping_observation_missing", codes)

    def test_generic_evidence_mapping_observation_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            role = Path(temporary) / "generic-map-observation"
            build_fixture(role, "existing-character", 80, 40, 20)
            voice = role / "references" / "02-语言声纹.md"
            text = voice.read_text(encoding="utf-8")
            text = re.sub(
                r"(TESTROLE-0001=>口语现象=)[^;；]+",
                r"\1短促直接的说法",
                text,
                count=1,
            )
            write_text(voice, text)
            result = persona_tool.validate_skill(role, "release")
            codes = {issue["code"] for issue in result["issues"]}
            self.assertFalse(result["valid"])
            self.assertIn("voice.evidence_mapping_observation_generic", codes)

    def test_selector_downgrades_high_tag_match_with_weak_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            role = Path(temporary) / "weak-evidence"
            build_fixture(role, "existing-character", 80, 40, 20)
            library = role / "references" / "06-对白库.md"
            text = library.read_text(encoding="utf-8")
            text = re.sub(
                r"^- 标签依据：.+$",
                "- 标签依据：speech_act=合理推导; trigger=缺失; relation=缺失; emotion=合理推导",
                text,
                flags=re.MULTILINE,
            )
            text = re.sub(r"^- 触发话语：.+$", "- 触发话语：上下文缺失", text, flags=re.MULTILINE)
            text = re.sub(r"^- 对话对象：.+$", "- 对话对象：未知", text, flags=re.MULTILINE)
            write_text(library, text)
            selected = json.loads(
                subprocess.check_output(
                    [
                        sys.executable,
                        str(role / "scripts" / "select_dialogues.py"),
                        "--root", str(role),
                        "--task-state", "failed",
                        "--user-state", "tired",
                        "--emotion", "alert",
                        "--intent", "comfort",
                        "--speech-act", "comfort",
                        "--trigger", "failed",
                        "--interaction", "comfort",
                        "--position", "reply",
                        "--risk", "low",
                        "--language", "zh-CN",
                        "--format", "json",
                    ],
                    text=True,
                    encoding="utf-8",
                )
            )
            self.assertEqual(selected["selected"], [])
            self.assertEqual(selected["retrieval"]["match_confidence"], "low")
            self.assertEqual(selected["retrieval"]["evidence_confidence"], "low")
            self.assertEqual(selected["retrieval"]["confidence"], "low")
            self.assertGreater(selected["retrieval"]["dropped_weak_cards"], 0)
            self.assertIn("不用弱卡凑数", selected["retrieval"]["warning"])

    def test_selector_can_use_verified_short_excerpt_for_exact_surface_act(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            role = Path(temporary) / "direct-short-expression"
            build_fixture(role, "existing-character", 80, 40, 20)
            library = role / "references" / "06-对白库.md"
            text = library.read_text(encoding="utf-8")
            text = text.replace("- 场景完整度：完整", "- 场景完整度：孤立摘录", 1)
            text = text.replace("- 前置原文：追问前一句测试原文 1", "- 前置原文：不适用", 1)
            text = text.replace("- 触发话语：追问触发话语 1", "- 触发话语：不适用", 1)
            text = text.replace("- 后续原文：追问后一句测试原文 1", "- 后续原文：不适用", 1)
            text = text.replace("- 可直接使用：视场景", "- 可直接使用：仅短句", 1)
            write_text(library, text)
            selected = json.loads(
                subprocess.check_output(
                    [
                        sys.executable, str(role / "scripts" / "select_dialogues.py"),
                        "--root", str(role), "--speech-act", "greet", "--limit", "1", "--format", "json",
                    ],
                    text=True,
                    encoding="utf-8",
                )
            )
            self.assertEqual([item["card_id"] for item in selected["selected"]], ["TESTROLE-0001"])
            self.assertEqual(selected["selected"][0]["evidence_confidence"], "medium")
            self.assertIn("scope:direct-only", selected["selected"][0]["evidence_gaps"])

    def test_same_context_self_evaluation_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            role = Path(temporary) / "self-evaluated"
            build_fixture(role, "existing-character", 80, 40, 20)
            cases = role / "references" / "07-验证用例.md"
            text = cases.read_text(encoding="utf-8")
            write_text(cases, text.replace("- 评估者标识：隔离评测上下文 A", "- 评估者标识：生成者本人自评", 1))
            result = persona_tool.validate_skill(role, "release")
            codes = {issue["code"] for issue in result["issues"]}
            self.assertFalse(result["valid"])
            self.assertIn("tests.self_evaluation_forbidden", codes)

    def test_voice_and_scene_must_reference_verified_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            role = Path(temporary) / "invented-voice"
            build_fixture(role, "existing-character", 80, 40, 20)
            voice_path = role / "references" / "02-语言声纹.md"
            voice_text = voice_path.read_text(encoding="utf-8")
            write_text(voice_path, voice_text.replace("TESTROLE-0001、TESTROLE-0002", "UNKNOWN-9999、TESTROLE-0002", 1))
            core_path = role / "references" / "01-角色核心.md"
            core_text = core_path.read_text(encoding="utf-8")
            write_text(core_path, core_text.replace("TESTROLE-0001、TESTROLE-0002", "UNKNOWN-9999、TESTROLE-0002", 1))
            scene_path = role / "references" / "04-工作场景迁移.md"
            scene_text = scene_path.read_text(encoding="utf-8")
            write_text(scene_path, scene_text.replace("VOICE-01", "VOICE-99", 1))
            result = persona_tool.validate_skill(role, "release")
            codes = {issue["code"] for issue in result["issues"]}
            self.assertFalse(result["valid"])
            self.assertIn("core_rule.evidence_invalid", codes)
            self.assertIn("voice.evidence_invalid", codes)
            self.assertIn("scene.voice_invalid", codes)

    def test_output_language_does_not_filter_original_language_corpus(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            role = Path(temporary) / "cross-language-role"
            build_fixture(role, "existing-character", 80, 40, 20)
            core_path = role / "references" / "01-角色核心.md"
            write_text(
                core_path,
                core_path.read_text(encoding="utf-8").replace("- 作品原始语言：zh-CN", "- 作品原始语言：ja-JP"),
            )
            library = role / "references" / "06-对白库.md"
            text = library.read_text(encoding="utf-8")
            text = text.replace("- 原文语言：zh-CN", "- 原文语言：ja-JP")
            write_text(library, text)
            source_path = role / "references" / "08-来源索引.md"
            write_text(
                source_path,
                source_path.read_text(encoding="utf-8").replace("- 原始语言：zh-CN", "- 原始语言：ja-JP"),
            )
            bind_evaluation_hash(role)
            result = persona_tool.validate_skill(role, "release")
            self.assertTrue(result["valid"], result["issues"])
            selected = json.loads(
                subprocess.check_output(
                    [
                        sys.executable,
                        str(role / "scripts" / "select_dialogues.py"),
                        "--root", str(role),
                        "--speech-act", "comfort",
                        "--trigger", "failed",
                        "--interaction", "comfort",
                        "--position", "reply",
                        "--emotion", "alert",
                        "--source-language", "ja-JP",
                        "--language", "zh-CN",
                        "--limit", "5",
                        "--format", "json",
                    ],
                    text=True,
                    encoding="utf-8",
                )
            )
            self.assertEqual(len(selected["selected"]), 5)
            self.assertTrue(all(item["original_language"] == "ja-JP" for item in selected["selected"]))

    def test_fidelity_tests_must_be_run_and_meet_thresholds(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            role = Path(temporary) / "untested-role"
            build_fixture(role, "existing-character", 80, 40, 20)
            cases_path = role / "references" / "07-验证用例.md"
            text = cases_path.read_text(encoding="utf-8")
            text = text.replace("- 正确识别数：10", "- 正确识别数：6", 1)
            text = text.replace("- 验证状态：通过", "- 验证状态：未运行", 1)
            write_text(cases_path, text)
            result = persona_tool.validate_skill(role, "release")
            codes = {issue["code"] for issue in result["issues"]}
            self.assertFalse(result["valid"])
            self.assertIn("tests.fidelity_not_passed", codes)
            self.assertIn("tests.blind_correct_low", codes)

    def test_passed_fidelity_case_requires_structured_record_file(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            role = Path(temporary) / "missing-eval-record"
            build_fixture(role, "existing-character", 80, 40, 20)
            (role / "tests" / "blind-record-a").unlink()
            result = persona_tool.validate_skill(role, "release")
            codes = {issue["code"] for issue in result["issues"]}
            self.assertFalse(result["valid"])
            self.assertIn("tests.record_missing", codes)

    def test_evaluation_record_counts_and_items_must_match_claims(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            role = Path(temporary) / "fake-eval-record"
            build_fixture(role, "existing-character", 80, 40, 20)
            record = role / "tests" / "contrast-record-b"
            write_text(
                record,
                "EVAL_RECORD_VERSION=1\nCASE_ID=CASE-19\nEVALUATOR_ID=独立评测 Agent B\n"
                "SAMPLE_COUNT=10\nPASS_COUNT=10\nITEM-01: pass | 只有一条\n",
            )
            result = persona_tool.validate_skill(role, "release")
            codes = {issue["code"] for issue in result["issues"]}
            self.assertFalse(result["valid"])
            self.assertIn("tests.record_count_mismatch", codes)
            self.assertIn("tests.record_items_low", codes)

    def test_target_met_cannot_leave_pending_material(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            role = Path(temporary) / "pending-material"
            build_fixture(role, "existing-character", 80, 40, 20)
            sources = role / "references" / "08-来源索引.md"
            text = sources.read_text(encoding="utf-8")
            write_text(sources, text.replace("- 待核验表达数：0", "- 待核验表达数：2", 1))
            result = persona_tool.validate_skill(role, "release")
            codes = {issue["code"] for issue in result["issues"]}
            self.assertFalse(result["valid"])
            self.assertIn("research.pending_unresolved", codes)

    def test_research_rounds_require_numeric_audit_and_matching_rates(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            role = Path(temporary) / "weak-research-round"
            build_fixture(role, "existing-character", 80, 40, 20)
            sources = role / "references" / "08-来源索引.md"
            text = sources.read_text(encoding="utf-8")
            text = text.replace("- 本轮候选数：80", "- 本轮候选数：很多", 1)
            text = text.replace("- 本轮新增率：4%", "- 本轮新增率：3%", 1)
            write_text(sources, text)
            result = persona_tool.validate_skill(role, "release")
            codes = {issue["code"] for issue in result["issues"]}
            self.assertFalse(result["valid"])
            self.assertIn("research.round_audit_incomplete", codes)
            self.assertIn("research.saturation_rate_mismatch", codes)

    def test_research_rounds_must_expand_to_a_new_scope(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            role = Path(temporary) / "repeated-research-scope"
            build_fixture(role, "existing-character", 80, 40, 20)
            sources = role / "references" / "08-来源索引.md"
            text = sources.read_text(encoding="utf-8")
            text = text.replace(
                "- 本轮新增检索范围：新增别名、多语言索引、访谈与可靠转写来源",
                "- 本轮新增检索范围：仅复查",
                1,
            )
            write_text(sources, text)
            result = persona_tool.validate_skill(role, "release")
            codes = {issue["code"] for issue in result["issues"]}
            self.assertIn("research.round_no_expansion", codes)

    def test_research_rounds_cannot_repeat_the_same_declared_scope(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            role = Path(temporary) / "duplicate-research-scope"
            build_fixture(role, "existing-character", 80, 40, 20)
            sources = role / "references" / "08-来源索引.md"
            text = sources.read_text(encoding="utf-8")
            text = text.replace(
                "- 本轮新增检索范围：新增别名、多语言索引、访谈与可靠转写来源",
                "- 本轮新增检索范围：官方角色页、剧情页与原始语言名称基线",
                1,
            )
            write_text(sources, text)
            result = persona_tool.validate_skill(role, "release")
            codes = {issue["code"] for issue in result["issues"]}
            self.assertIn("research.round_scope_repeated", codes)

    def test_research_gate_blocks_thin_corpus_without_showing_later_stage_errors(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            role = Path(temporary) / "thin-corpus"
            build_fixture(role, "existing-character", 40, 15, 10)
            (role / "tests" / "blind-record-a").unlink()
            gate = subprocess.run(
                [sys.executable, str(ROOT / "scripts" / "persona_tool.py"), "research-gate", str(role)],
                check=False, capture_output=True, text=True, encoding="utf-8",
            )
            self.assertNotEqual(gate.returncode, 0)
            self.assertIn("PERSONA_RESEARCH_STATE=INCOMPLETE", gate.stdout)
            self.assertIn("REQUIRED_CARDS=80", gate.stdout)
            self.assertIn("research.non_rich_cannot_pass", gate.stdout)
            self.assertNotIn("tests.", gate.stdout)

    def test_research_gate_allows_distillation_only_after_rich_corpus(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            role = Path(temporary) / "rich-corpus"
            build_fixture(role, "existing-character", 80, 40, 20)
            gate = subprocess.run(
                [sys.executable, str(ROOT / "scripts" / "persona_tool.py"), "research-gate", str(role)],
                check=False, capture_output=True, text=True, encoding="utf-8",
            )
            self.assertEqual(gate.returncode, 0, gate.stdout + gate.stderr)
            self.assertIn("PERSONA_RESEARCH_STATE=READY", gate.stdout)
            self.assertIn("LOOP_STAGE=REDISTILL", gate.stdout)

    def test_iteration_gate_routes_rule_and_test_failures(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            redistill = root / "redistill-role"
            build_fixture(redistill, "existing-character", 80, 40, 20)
            voice = redistill / "references" / "02-语言声纹.md"
            text = voice.read_text(encoding="utf-8")
            text = re.sub(
                r"(TESTROLE-0001=>口语现象=)[^;；]+",
                r"\1短促直接的说法",
                text,
                count=1,
            )
            write_text(voice, text)
            redistill_gate = subprocess.run(
                [
                    sys.executable, str(ROOT / "scripts" / "persona_tool.py"),
                    "iteration-gate", str(redistill), "--activation-status", "pending",
                ],
                check=False, capture_output=True, text=True, encoding="utf-8",
            )
            self.assertIn("LOOP_STAGE=REDISTILL", redistill_gate.stdout)
            self.assertIn("MUST_CONTINUE=true", redistill_gate.stdout)

            retest = root / "retest-role"
            build_fixture(retest, "existing-character", 80, 40, 20)
            (retest / "tests" / "blind-record-a").unlink()
            test_gate = subprocess.run(
                [
                    sys.executable, str(ROOT / "scripts" / "persona_tool.py"),
                    "iteration-gate", str(retest), "--activation-status", "pending",
                ],
                check=False, capture_output=True, text=True, encoding="utf-8",
            )
            self.assertIn("LOOP_STAGE=TEST", test_gate.stdout)
            self.assertIn("MUST_CONTINUE=true", test_gate.stdout)

    def test_batch_fidelity_rejects_uniform_shape_and_question_closure(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            role = Path(temporary) / "uniform-batch-role"
            build_fixture(role, "existing-character", 80, 40, 20)
            cases_path = role / "references" / "07-验证用例.md"
            text = cases_path.read_text(encoding="utf-8")
            text = text.replace("- 同一回答形状样本数：0", "- 同一回答形状样本数：7", 1)
            text = text.replace("- 追问收尾样本数：0", "- 追问收尾样本数：9", 1)
            text = text.replace("- 长度与句数异常集中：否", "- 长度与句数异常集中：是", 1)
            write_text(cases_path, text)
            result = persona_tool.validate_skill(role, "release")
            codes = {issue["code"] for issue in result["issues"]}
            self.assertIn("tests.batch_shape_repeated", codes)
            self.assertIn("tests.batch_question_closure_repeated", codes)
            self.assertIn("tests.batch_uniform_structure", codes)

    def test_response_checker_flags_ai_and_project_manager_tone(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            role = Path(temporary) / "tone-role"
            build_fixture(role, "existing-character", 80, 40, 20)
            checker = role / "scripts" / "check_response.py"
            generic = json.loads(
                subprocess.check_output(
                    [
                        sys.executable,
                        str(checker),
                        "--root", str(role),
                        "--text", "好的，基于以上情况，我们先确认目标，再梳理范围，然后确定方案，最后推进下一步，由你决定。",
                    ],
                    text=True,
                    encoding="utf-8",
                )
            )
            spoken = json.loads(
                subprocess.check_output(
                    [
                        sys.executable,
                        str(checker),
                        "--root", str(role),
                        "--text", "不行，这个我不喜欢。先做副本。要不要继续，你来选。",
                    ],
                    text=True,
                    encoding="utf-8",
                )
            )
            process_preamble = json.loads(
                subprocess.check_output(
                    [
                        sys.executable,
                        str(checker),
                        "--root", str(role),
                        "--text", "千束：我先按轻松问候场景取几张日语原文卡。",
                    ],
                    text=True,
                    encoding="utf-8",
                )
            )
            fake_presence = json.loads(
                subprocess.check_output(
                    [
                        sys.executable,
                        str(checker),
                        "--root", str(role),
                        "--text", "*歪头* 嗯，呃，那个……哈哈，我看见你叹气了。*拍拍你的肩*",
                    ],
                    text=True,
                    encoding="utf-8",
                )
            )
            consulting = json.loads(
                subprocess.check_output(
                    [
                        sys.executable,
                        str(checker),
                        "--root", str(role),
                        "--text", "做网站啊，挺好。先别急着铺一大堆页面：它是给谁用的，对方进来第一件事要完成什么？这两个定下来，我们就能做出第一版。",
                    ],
                    text=True,
                    encoding="utf-8",
                )
            )
            batch_path = role / "tests" / "responses.json"
            batch_path.parent.mkdir(parents=True, exist_ok=True)
            write_text(
                batch_path,
                json.dumps(
                    [
                        "先别急着做页面。先把目标定下来，我们就能继续。",
                        "还没结束。先看错误日志，我们从第一条开始。",
                        "这次我理解反了。我先改需求，再重新整理。",
                        "方案你定了。先确认代价，然后我们推进。",
                        "做得好。先验收，再发布，我们继续。",
                    ],
                    ensure_ascii=False,
                ),
            )
            batch = json.loads(
                subprocess.check_output(
                    [sys.executable, str(checker), "--root", str(role), "--batch-file", str(batch_path)],
                    text=True,
                    encoding="utf-8",
                )
            )
            uniform_path = role / "tests" / "uniform-responses.json"
            write_text(
                uniform_path,
                json.dumps(
                    [
                        "这块你最想改成什么样？",
                        "这个结果你现在满意吗？",
                        "这里你更偏向哪一种呢？",
                        "这一段你希望继续保留吗？",
                        "这次你想先看哪个部分？",
                    ],
                    ensure_ascii=False,
                ),
            )
            uniform = json.loads(
                subprocess.check_output(
                    [sys.executable, str(checker), "--root", str(role), "--batch-file", str(uniform_path)],
                    text=True,
                    encoding="utf-8",
                )
            )
            mixed_path = role / "tests" / "mixed-responses.json"
            write_text(
                mixed_path,
                json.dumps(
                    [
                        "做网站啊，挺好。先别急着铺一大堆页面：它是给谁用的，对方进来第一件事要完成什么？这两个定下来，我们就能做出第一版。",
                        "不行，这里会丢数据。副本留下。",
                        "咦，这次居然一下就过了。",
                        "我刚才看反了，是我的错。",
                        "还在转呢，再给它一点时间。",
                        "这个颜色我不喜欢，换掉吧。",
                        "今天先到这里，剩下的明天再说。",
                        "三次失败也只是三条线索，不是判决。",
                    ],
                    ensure_ascii=False,
                ),
            )
            mixed = json.loads(
                subprocess.check_output(
                    [sys.executable, str(checker), "--root", str(role), "--batch-file", str(mixed_path)],
                    text=True,
                    encoding="utf-8",
                )
            )
            self.assertEqual(generic["status"], "fail")
            self.assertGreaterEqual(generic["ai_tone_score"], 60)
            self.assertEqual(spoken["status"], "pass")
            self.assertLess(spoken["ai_tone_score"], 40)
            self.assertEqual(process_preamble["status"], "fail")
            self.assertIn("internal_process_preamble", {item["code"] for item in process_preamble["findings"]})
            fake_codes = {item["code"] for item in fake_presence["findings"]}
            self.assertEqual(fake_presence["status"], "fail")
            self.assertIn("unverified_sensory_claim", fake_codes)
            self.assertIn("stage_direction_density", fake_codes)
            self.assertIn(consulting["status"], {"review", "fail"})
            self.assertIn("generic_consulting_frame", {item["code"] for item in consulting["findings"]})
            self.assertEqual(batch["status"], "fail")
            self.assertIn("batch_workflow_skeleton_repeated", {item["code"] for item in batch["findings"]})
            uniform_codes = {item["code"] for item in uniform["findings"]}
            self.assertEqual(uniform["status"], "fail")
            self.assertIn("batch_question_closure_repeated", uniform_codes)
            self.assertIn("batch_response_shape_repeated", uniform_codes)
            self.assertEqual(mixed["status"], "fail")
            self.assertIn("batch_individual_failures", {item["code"] for item in mixed["findings"]})

    def test_release_rejects_bare_pass_records_and_stale_runtime_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            role = Path(temporary) / "forged-test-role"
            build_fixture(role, "existing-character", 80, 40, 20)
            blind = role / "tests" / "blind-record-a"
            write_text(
                blind,
                "EVAL_RECORD_VERSION=2\nCASE_ID=CASE-18\nEVALUATOR_ID=隔离评测上下文 A\n"
                "SAMPLE_COUNT=12\nPASS_COUNT=12\n"
                + "\n".join(f"ITEM-{index:02d}: pass" for index in range(1, 13))
                + "\n",
            )
            runtime = role / "tests" / "runtime-conversation.json"
            payload = json.loads(runtime.read_text(encoding="utf-8"))
            payload[0]["response"] = "这条回答在检查和评估结束后被替换了。"
            write_text(runtime, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
            result = persona_tool.validate_skill(role, "release")
            codes = {issue["code"] for issue in result["issues"]}
            self.assertFalse(result["valid"])
            self.assertIn("tests.record_item_not_structured", codes)
            self.assertIn("tests.batch_output_stale", codes)

    def test_release_rejects_duplicate_evaluation_item_ids(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            role = Path(temporary) / "duplicate-eval-items"
            build_fixture(role, "existing-character", 80, 40, 20)
            record = role / "tests" / "blind-record-a"
            write_text(
                record,
                record.read_text(encoding="utf-8").replace("ITEM-02:", "ITEM-01:", 1),
            )
            result = persona_tool.validate_skill(role, "release")
            codes = {issue["code"] for issue in result["issues"]}
            self.assertFalse(result["valid"])
            self.assertIn("tests.record_item_ids_invalid", codes)

    def test_release_rejects_evaluation_bound_to_old_persona(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            role = Path(temporary) / "stale-persona-evaluation"
            build_fixture(role, "existing-character", 80, 40, 20)
            core = role / "references" / "01-角色核心.md"
            write_text(
                core,
                core.read_text(encoding="utf-8").replace(
                    "遇到危险时把人的安全放在规则之前",
                    "遇到危险时先保护眼前的人再重新判断规则",
                    1,
                ),
            )
            result = persona_tool.validate_skill(role, "release")
            codes = {issue["code"] for issue in result["issues"]}
            self.assertFalse(result["valid"])
            self.assertIn("tests.evaluation_persona_stale", codes)

    def test_release_rejects_broken_runtime_conversation_chain(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            role = Path(temporary) / "broken-runtime-chain"
            build_fixture(role, "existing-character", 80, 40, 20)
            runtime = role / "tests" / "runtime-conversation.json"
            samples = json.loads(runtime.read_text(encoding="utf-8"))
            samples[5]["previous_turn"] = 1
            write_text(runtime, json.dumps(samples, ensure_ascii=False, indent=2) + "\n")
            result = persona_tool.validate_skill(role, "release")
            codes = {issue["code"] for issue in result["issues"]}
            self.assertFalse(result["valid"])
            self.assertIn("tests.runtime_conversation_chain_invalid", codes)

    def test_release_reruns_checker_instead_of_trusting_saved_pass(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            role = Path(temporary) / "forged-saved-pass"
            build_fixture(role, "existing-character", 80, 40, 20)
            runtime = role / "tests" / "runtime-conversation.json"
            samples = json.loads(runtime.read_text(encoding="utf-8"))
            for sample in samples:
                sample["response"] = "先检查当前状态，再确认范围，然后我们继续推进。"
            write_text(runtime, json.dumps(samples, ensure_ascii=False, indent=2) + "\n")
            # Keep the previously saved pass output in place.  Release
            # validation must independently rerun the trusted checker.
            result = persona_tool.validate_skill(role, "release")
            codes = {issue["code"] for issue in result["issues"]}
            self.assertFalse(result["valid"])
            self.assertIn("tests.batch_recheck_failed", codes)
            self.assertIn("tests.quality_record_stale", codes)

    def test_release_rejects_low_independent_runtime_quality(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            role = Path(temporary) / "low-quality-role"
            build_fixture(role, "existing-character", 80, 40, 20)
            cases = role / "references" / "07-验证用例.md"
            text = cases.read_text(encoding="utf-8")
            text = text.replace("- 综合评分：85", "- 综合评分：75", 1)
            text = text.replace("- 角色还原：35", "- 角色还原：31", 1)
            text = text.replace("- 口语自然度：13", "- 口语自然度：11", 1)
            text = text.replace("- 回答形态多样性：12", "- 回答形态多样性：10", 1)
            text = text.replace("- 事实与风险处理：8", "- 事实与风险处理：6", 1)
            text = text.replace("- 独立结论：通过", "- 独立结论：未通过", 1)
            write_text(cases, text)
            result = persona_tool.validate_skill(role, "release")
            codes = {issue["code"] for issue in result["issues"]}
            self.assertFalse(result["valid"])
            self.assertIn("tests.quality_total_low", codes)
            self.assertIn("tests.quality_role_low", codes)
            self.assertIn("tests.quality_orality_low", codes)
            self.assertIn("tests.quality_diversity_low", codes)
            self.assertIn("tests.quality_fact_risk_low", codes)
            self.assertIn("tests.quality_verdict_not_passed", codes)
            gate = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "persona_tool.py"),
                    "completion-gate",
                    str(role),
                    "--activation-status",
                    "enabled",
                ],
                check=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
            )
            self.assertNotEqual(gate.returncode, 0)
            self.assertIn("TERMINAL_ALLOWED=false", gate.stdout)

    def test_release_rejects_missing_subtitle_downgrade_and_duplicate_audit_field(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            role = Path(temporary) / "downgraded-role"
            build_fixture(role, "existing-character", 40, 15, 10)
            sources = role / "references" / "08-来源索引.md"
            text = sources.read_text(encoding="utf-8")
            old = "- 资料丰度边界说明：检查过更高档目标所需范围，但可核查原始表达规模未达到丰富档"
            new = "- 资料丰度边界说明：未取得原始字幕文件，因此按一般档验收"
            text = text.replace(old, new + "\n" + new, 1)
            write_text(sources, text)
            result = persona_tool.validate_skill(role, "release")
            codes = {issue["code"] for issue in result["issues"]}
            self.assertFalse(result["valid"])
            self.assertIn("research.profile_downgraded_by_missing_medium", codes)
            self.assertIn("research.duplicate_audit_field", codes)

    def test_evidence_mapping_audit_is_independent_and_meets_threshold(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            role = Path(temporary) / "weak-map-audit"
            build_fixture(role, "existing-character", 80, 40, 20)
            cases = role / "references" / "07-验证用例.md"
            text = cases.read_text(encoding="utf-8")
            text = text.replace("- 证据映射抽查数：12", "- 证据映射抽查数：6", 1)
            text = text.replace("- 证据映射成立数：10", "- 证据映射成立数：3", 1)
            text = text.replace("- 评估者标识：隔离证据审计上下文 C", "- 评估者标识：生成者本人自评", 1)
            write_text(cases, text)
            result = persona_tool.validate_skill(role, "release")
            codes = {issue["code"] for issue in result["issues"]}
            self.assertIn("tests.evidence_mapping_samples_low", codes)
            self.assertIn("tests.evidence_mapping_rate_low", codes)
            self.assertIn("tests.self_evaluation_forbidden", codes)

    def test_original_persona_can_release_with_twenty_cards(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            role = Path(temporary) / "original-role"
            build_fixture(role, "original-persona", 20)
            result = persona_tool.validate_skill(role, "release")
            self.assertTrue(result["valid"], result["issues"])

    def test_composite_character_requires_representative_per_work_matrix(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            role = Path(temporary) / "composite-role"
            build_fixture(role, "composite-character", 80, scene_count=24, signature_count=12, asset_version=2)
            sources = role / "references" / "08-来源索引.md"
            source_text = sources.read_text(encoding="utf-8")
            source_text += "\n### WORK-01 | 作品一\n\n- 作品：作品一\n- 角色/表达者：角色一\n- 原文卡：TESTROLE-0001、TESTROLE-0002\n- 独特表达数：2\n- 证据单元数：1\n- 场景维度：日常、关系\n- 来源策略：primary 版本；原语言文本核验\n- 检索缺口：仍需补齐冲突与风险\n"
            source_text += "\n### WORK-02 | 作品二\n\n- 作品：作品二\n- 角色/表达者：角色二\n- 原文卡：TESTROLE-0003、TESTROLE-0004\n- 独特表达数：2\n- 证据单元数：1\n- 场景维度：日常、关系\n- 来源策略：primary 版本；原语言文本核验\n- 检索缺口：仍需补齐冲突与风险\n"
            write_text(sources, source_text)
            result = persona_tool.validate_skill(role, "release")
            codes = {issue["code"] for issue in result["issues"]}
            self.assertFalse(result["valid"])
            self.assertIn("composite.work_cards_low", codes)
            self.assertIn("composite.work_evidence_low", codes)
            self.assertIn("composite.work_scene_coverage_low", codes)
            self.assertFalse(result["metrics"]["composite_work_coverage_complete"])

    def test_composite_character_allows_weighted_classic_selection_when_each_work_has_floor(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            role = Path(temporary) / "weighted-composite-role"
            build_fixture(role, "composite-character", 80, scene_count=24, signature_count=12, asset_version=2)
            sources = role / "references" / "08-来源索引.md"
            rows: list[str] = []
            ranges = [(1, 10), (11, 25), (26, 45), (46, 80)]
            for index, (start, end) in enumerate(ranges, start=1):
                card_ids = "、".join(f"TESTROLE-{card:04d}" for card in range(start, end + 1))
                rows.append(
                    f"### WORK-{index:02d} | 作品{index}\n\n"
                    f"- 作品：作品{index}\n- 角色/表达者：角色{index}\n- 原文卡：{card_ids}\n"
                    "- 独特表达数：10\n- 证据单元数：10\n- 场景维度：日常、关系、冲突、风险\n"
                    "- 来源策略：primary 版本；原语言文本核验\n- 检索缺口：无\n"
                )
            write_text(sources, sources.read_text(encoding="utf-8") + "\n" + "\n".join(rows))
            result = persona_tool.validate_skill(role, "release")
            self.assertTrue(result["metrics"]["composite_work_coverage_complete"], result["issues"])
            self.assertEqual(result["metrics"]["composite_work_cards_min"], 10)
            self.assertGreater(result["metrics"]["composite_work_card_share_max"], 0.4)
            self.assertNotIn("composite.work_cards_low", {issue["code"] for issue in result["issues"]})
            self.assertIn("tests.evaluation_persona_stale", {issue["code"] for issue in result["issues"]})

    def test_independent_quality_gate_is_explicit_and_blocks_failed_result(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            role = Path(temporary) / "quality-gated-role"
            build_fixture(role, "existing-character", 80, scene_count=24, signature_count=12, asset_version=2)
            cases = role / "references" / "07-验证用例.md"
            text = cases.read_text(encoding="utf-8").replace("- 独立结论：通过", "- 独立结论：未通过", 1)
            write_text(cases, text)
            result = persona_tool.validate_skill(role, "release")
            codes = {issue["code"] for issue in result["issues"]}
            self.assertFalse(result["valid"])
            self.assertFalse(result["metrics"]["independent_quality_pass"])
            self.assertIn("tests.quality_verdict_not_passed", codes)
            self.assertIn("tests.independent_quality_gate_required", codes)

    def test_rich_quality_gate_rejects_labelled_repeated_continuity_samples(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            role = Path(temporary) / "labelled-quality-role"
            build_fixture(role, "existing-character", 80, scene_count=24, signature_count=12, asset_version=2)
            runtime_path = role / "tests" / "runtime-conversation.json"
            payload = json.loads(runtime_path.read_text(encoding="utf-8"))
            for item in payload:
                item["prompt"] = "risk"
                item["response"] = "测试角色：这就开干。"
            write_text(runtime_path, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
            result = persona_tool.validate_skill(role, "release")
            codes = {issue["code"] for issue in result["issues"]}
            self.assertFalse(result["valid"])
            self.assertIn("tests.runtime_prompt_not_natural", codes)
            self.assertIn("tests.runtime_prompt_diversity_low", codes)
            self.assertIn("tests.runtime_mechanical_repetition", codes)
            self.assertFalse(result["metrics"]["independent_quality_pass"])

    def test_independent_report_not_passed_cannot_coexist_with_case24_pass(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            role = Path(temporary) / "contradictory-quality-role"
            build_fixture(role, "existing-character", 80, scene_count=24, signature_count=12, asset_version=2)
            write_text(role / "tests" / "independent-evaluation.md", "# 独立评测\n\n最终结论：不通过，证据不足。\n")
            result = persona_tool.validate_skill(role, "release")
            codes = {issue["code"] for issue in result["issues"]}
            self.assertFalse(result["valid"])
            self.assertIn("tests.independent_report_not_passed", codes)
            self.assertFalse(result["metrics"]["independent_quality_pass"])

    def test_research_gate_reports_collection_counts_and_feedback_fields(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            role = Path(temporary) / "feedback-role"
            build_fixture(role, "composite-character", 28, scene_count=8, signature_count=8, asset_version=2)
            completed = subprocess.run(
                [sys.executable, str(ROOT / "scripts" / "persona_tool.py"), "research-gate", str(role)],
                check=False, capture_output=True, text=True, encoding="utf-8",
            )
            self.assertNotEqual(completed.returncode, 0)
            self.assertIn("CANDIDATE_EXPRESSIONS=", completed.stdout)
            self.assertIn("FORMAL_EXPRESSIONS=", completed.stdout)
            self.assertIn("PENDING_EXPRESSIONS=", completed.stdout)
            self.assertIn("REJECTED_EXPRESSIONS=", completed.stdout)
            self.assertIn("RESEARCH_ROUND_SUMMARY=", completed.stdout)
            self.assertIn("COMPOSITE_WORK_GAPS=", completed.stdout)
            self.assertIn("AUTO_DETECTED_WORKS=", completed.stdout)
            self.assertIn("FEEDBACK_REQUIRED=true", completed.stdout)
            self.assertIn("FEEDBACK_STAGE=资料采集", completed.stdout)
            self.assertIn("NEXT_FEEDBACK=", completed.stdout)

    def test_persona_asset_v3_quality_loop_and_selector_contract(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            role = Path(temporary) / "persona-test-role"
            build_fixture(
                role, "existing-character", 80, scene_count=24, signature_count=12,
                asset_version=3,
            )
            result = persona_tool.validate_skill(role, "release")
            self.assertTrue(result["valid"], result["issues"])
            metrics = result["metrics"]
            self.assertEqual(metrics["behavior_rules"], 12)
            self.assertEqual(metrics["behavior_functions"], 12)
            self.assertTrue(metrics["behavior_function_coverage_complete"])
            self.assertTrue(metrics["quality_loop_pass"])
            self.assertEqual(metrics["quality_loop_prompt_count"], 24)
            self.assertGreaterEqual(metrics["quality_loop_blind_target_count"], 20)
            self.assertGreaterEqual(metrics["quality_loop_similar_role_count"], 20)
            selected = json.loads(subprocess.check_output(
                [
                    sys.executable, str(role / "scripts" / "select_dialogues.py"),
                    "--root", str(role), "--task-state", "risk", "--behavior-function", "warn",
                    "--speech-act", "warn", "--trigger", "risk", "--interaction", "warn",
                    "--position", "reply", "--relation", "familiar", "--format", "json",
                ],
                text=True, encoding="utf-8",
            ))
            contract = selected["response_contract"]
            self.assertEqual(contract["contract_version"], 4)
            self.assertTrue(contract["ready"])
            self.assertEqual(contract["behavior_function"], "warn")
            self.assertIn("BEHAV-08", contract["behavior_rule_ids"])
            self.assertEqual(len(contract["required_visible_slots"]), 3)

    def test_persona_asset_v3_invalidates_scores_after_persona_change(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            role = Path(temporary) / "persona-test-role"
            build_fixture(
                role, "existing-character", 80, scene_count=24, signature_count=12,
                asset_version=3,
            )
            behavior_path = role / "references" / "12-行为辨识模型.md"
            write_text(behavior_path, behavior_path.read_text(encoding="utf-8") + "\n<!-- persona changed -->\n")
            status = persona_tool.quality.status(role)
            self.assertFalse(status["valid"])
            codes = {item["code"] for item in status["issues"]}
            self.assertIn("quality_loop.persona_stale", codes)
            result = persona_tool.validate_skill(role, "release")
            self.assertFalse(result["valid"])
            self.assertIn("quality_loop.persona_stale", {item["code"] for item in result["issues"]})

    def test_persona_asset_v3_recomputes_evaluation_instead_of_trusting_summary(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            role = Path(temporary) / "persona-test-role"
            build_fixture(
                role, "existing-character", 80, scene_count=24, signature_count=12,
                asset_version=3,
            )
            manifest_path = role / "tests" / "quality-loop.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            evaluation_path = role / manifest["evaluation"]["evaluation_path"]
            evaluation = json.loads(evaluation_path.read_text(encoding="utf-8"))
            evaluation["summary"]["total_score"] = 86
            write_text(evaluation_path, json.dumps(evaluation, ensure_ascii=False, indent=2) + "\n")
            manifest["evaluation"]["evaluation_sha256"] = hashlib.sha256(evaluation_path.read_bytes()).hexdigest()
            write_text(manifest_path, json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")

            result = persona_tool.quality.status(role)
            self.assertFalse(result["valid"])
            codes = {item["code"] for item in result["issues"]}
            self.assertIn("quality_loop.evaluation_summary_tampered", codes)

    def test_persona_asset_v3_rechecks_visible_evidence_after_hashes_are_refreshed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            role = Path(temporary) / "persona-test-role"
            build_fixture(
                role, "existing-character", 80, scene_count=24, signature_count=12,
                asset_version=3,
            )
            manifest_path = role / "tests" / "quality-loop.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            responses_path = role / manifest["generation"]["responses_path"]
            responses = json.loads(responses_path.read_text(encoding="utf-8"))
            responses[0]["generation_trace"]["visible_character_signals"][0]["excerpt"] = "回答中根本不存在的伪证据"
            write_text(responses_path, json.dumps(responses, ensure_ascii=False, indent=2) + "\n")
            response_hash = hashlib.sha256(responses_path.read_bytes()).hexdigest()
            manifest["generation"]["responses_sha256"] = response_hash

            evaluation_path = role / manifest["evaluation"]["evaluation_path"]
            evaluation = json.loads(evaluation_path.read_text(encoding="utf-8"))
            evaluation["subject_file_sha256"] = response_hash
            write_text(evaluation_path, json.dumps(evaluation, ensure_ascii=False, indent=2) + "\n")
            evaluation_hash = hashlib.sha256(evaluation_path.read_bytes()).hexdigest()
            manifest["evaluation"]["subject_file_sha256"] = response_hash
            manifest["evaluation"]["evaluation_sha256"] = evaluation_hash
            write_text(manifest_path, json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")

            result = persona_tool.quality.status(role)
            self.assertFalse(result["valid"])
            codes = {item["code"] for item in result["issues"]}
            self.assertIn("quality_loop.runtime_generation_failed", codes)

    def test_persona_asset_v3_rejects_same_context_evaluation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            role = Path(temporary) / "persona-test-role"
            build_fixture(
                role, "existing-character", 80, scene_count=24, signature_count=12,
                asset_version=3,
            )
            manifest_path = role / "tests" / "quality-loop.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            with self.assertRaisesRegex(persona_tool.quality.QualityLoopError, "三个不同上下文"):
                persona_tool.quality.record_responses(
                    role,
                    manifest["run_id"],
                    role / "tests" / "quality-input-responses.json",
                    manifest["generation"]["generator_context_id"],
                    "fixture-another-similar-context",
                )
            manifest["status"] = "evaluation-pending"
            manifest["evaluation"] = {"status": "pending"}
            write_text(manifest_path, json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
            result = persona_tool.quality.evaluate_run(
                role,
                manifest["run_id"],
                role / "tests" / "quality-input-evaluation.json",
                manifest["generation"]["generator_context_id"],
            )
            self.assertEqual(result["status"], "repair-required")
            self.assertTrue(any("相同" in message for message in result["contract_errors"]))
            self.assertIn("behavior-model", result["failure_layers"])

    def test_persona_asset_v3_cli_routes_low_quality_and_keeps_loop_active(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            role = Path(temporary) / "persona-test-role"
            build_fixture(
                role, "existing-character", 80, scene_count=24, signature_count=12,
                asset_version=3,
            )
            manifest_path = role / "tests" / "quality-loop.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["status"] = "evaluation-pending"
            manifest["evaluation"] = {"status": "pending"}
            manifest["failure_layers"] = []
            manifest["repair_targets"] = []
            write_text(manifest_path, json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")

            evaluation_path = role / "tests" / "quality-input-evaluation.json"
            evaluation = json.loads(evaluation_path.read_text(encoding="utf-8"))
            for item in evaluation["items"][:8]:
                for field in (
                    "role_fidelity", "emotional_value", "proactive_expression",
                    "character_thinking", "relationship_continuity",
                ):
                    item[field] = 1
                item["verdict"] = "fail"
                item["failure_layers"] = ["retrieval"]
                item["repair_targets"] = ["修正检索条件并重新生成"]
                item["reason"] = "行为机制存在，但当前触发检索错了证据，回答退化成通用说明。"
            write_text(evaluation_path, json.dumps(evaluation, ensure_ascii=False, indent=2) + "\n")

            completed = subprocess.run(
                [
                    sys.executable, str(ROOT / "scripts" / "persona_tool.py"),
                    "quality-evaluate", str(role), "--run-id", manifest["run_id"],
                    "--evaluation", str(evaluation_path),
                    "--evaluator-context-id", "fixture-evaluator-context-009",
                ],
                check=False, capture_output=True, text=True, encoding="utf-8",
            )
            self.assertEqual(completed.returncode, 1)
            self.assertIn("QUALITY_STATUS=repair-required", completed.stdout)
            self.assertIn("LOOP_STAGE=RETRIEVE", completed.stdout)
            self.assertIn("FAILURE_LAYERS=retrieval", completed.stdout)
            self.assertIn("MUST_CONTINUE=true", completed.stdout)
            self.assertIn("RESPONSE_MODE=CONTINUE_TOOL_LOOP", completed.stdout)
            self.assertIn("TERMINAL_ALLOWED=false", completed.stdout)
            self.assertIn("FEEDBACK_STAGE=独立质量评估", completed.stdout)
            self.assertIn("修正检索条件", completed.stdout)

    def test_v3_checker_allows_three_distinct_persona_shapes_but_rejects_generic_developer_voice(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            role = Path(temporary) / "persona-test-role"
            build_fixture(
                role, "existing-character", 80, scene_count=24, signature_count=12,
                asset_version=3,
            )
            checker = role / "scripts" / "check_response.py"
            samples = {
                "comic-analogy": "这事像饿着肚子背一筐西瓜过独木桥，嘴上说轻巧，真掉下去连瓜带人一块儿湿。备份没验，俺可不替这胆子叫好。",
                "verbose-causal": "此事不可只图眼前一步。今日省去核验，看似得了片刻便利；明日若数据有失，便要用十倍工夫追悔。因从果生，果又照见今日之因，所以不是我故意多说，而是这一步既牵着后路，也牵着与你一同做事的人。先把备份证实，再谈删除，才不至于以急躁换来长久之患。",
                "restrained": "不删。备份没验，手别往下按。",
            }
            for label, sample in samples.items():
                with self.subTest(label=label):
                    checked = json.loads(subprocess.check_output(
                        [sys.executable, str(checker), "--root", str(role), "--text", sample],
                        text=True, encoding="utf-8",
                    ))
                    self.assertEqual(checked["status"], "pass", checked)
            generic = json.loads(subprocess.check_output(
                [
                    sys.executable, str(checker), "--root", str(role), "--text",
                    "好的，基于以上情况，为了确保目标和范围一致，接下来我们首先确认方案，其次梳理流程，然后确定优先级，最后推进下一步，由你决定。",
                ],
                text=True, encoding="utf-8",
            ))
            self.assertNotEqual(generic["status"], "pass")

    def test_v4_rejects_pitch_deck_advice_even_when_it_has_a_persona_metaphor(self) -> None:
        """Regression for the screenshot failure: consultant outline is not character thinking."""
        with tempfile.TemporaryDirectory() as temporary:
            role = Path(temporary) / "persona-test-role"
            build_fixture(role, "existing-character", 80, scene_count=24, signature_count=12, asset_version=3)
            checker = role / "scripts" / "check_response.py"
            reply = (
                "我会选一个明确方向：做 Agent Skill 可仓库商店。不是卖提示词，而是卖三件事：装得上、跑得稳、不乱动。"
                "第一版做这些：Skill 上传、版本兼容检查、各运行时一键安装、权限扫描、质量评分、团队私有仓库。"
                "赚钱方式：个人版每月 29–99 元，团队版每月 999 元起，商店交易抽成 10%–20%。"
                "这事像人丢进海里，但你有优势。"
            )
            checked = json.loads(subprocess.check_output(
                [sys.executable, str(checker), "--root", str(role), "--text", reply],
                text=True, encoding="utf-8",
            ))
            self.assertNotEqual(checked["status"], "pass", checked)
            self.assertTrue(any(item["code"] == "generic_pitch_deck_frame" for item in checked["findings"]))

    def test_v4_evaluation_rejects_false_pass_for_detected_consulting_skeleton(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            role = Path(temporary) / "persona-test-role"
            build_fixture(role, "existing-character", 80, scene_count=24, signature_count=12, asset_version=3)
            manifest = json.loads((role / "tests" / "quality-loop.json").read_text(encoding="utf-8"))
            manifest["status"] = "evaluation-pending"
            manifest["evaluation"] = {"status": "pending"}
            write_text(role / "tests" / "quality-loop.json", json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
            evaluation_path = role / "tests" / "quality-input-evaluation.json"
            evaluation = json.loads(evaluation_path.read_text(encoding="utf-8"))
            evaluation["items"][0]["generic_skeleton_detected"] = True
            evaluation["items"][0]["verdict"] = "pass"
            write_text(evaluation_path, json.dumps(evaluation, ensure_ascii=False, indent=2) + "\n")
            result = persona_tool.quality.evaluate_run(
                role, manifest["run_id"], evaluation_path, "fixture-evaluator-context-009",
            )
            self.assertEqual(result["status"], "repair-required")
            self.assertTrue(any("顾问骨架伪装" in error for error in result["contract_errors"]))

    def test_creator_defaults_identity_prefix_and_formal_only_delivery(self) -> None:
        creator = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("创建角色的强制第一步", creator)
        self.assertIn("1、直接使用原角色名", creator)
        self.assertIn("2、自定义角色名（用户直接输入名字）", creator)
        self.assertIn("没有指定人物名", creator)
        self.assertIn("禁止先联网、读取资料、调用 `init`", creator)
        self.assertIn("默认沿用原角色名和当前主要版本只表示用户选择了 `1`", creator)
        self.assertIn("创建过程中的所有 Agent 自然语言消息都必须以 `<角色名>：` 开头", creator)
        self.assertIn("普通问候、闲聊和可立即回答的问题只发送最终回答", creator)
        self.assertIn("默认静默完成角色核心读取", creator)
        self.assertIn("最终版本始终为正式版", creator)
        self.assertIn("创建任务持续执行锁", creator)
        self.assertIn("禁止结束；立即继续下一项调研", creator)
        self.assertIn("进度消息不是交付，也不是暂停许可", creator)
        self.assertIn("强制阶段反馈协议", creator)
        self.assertIn("阶段 / 已完成 / 当前数量或发现 / 下一步", creator)
        self.assertIn("逐作品代表性底线", creator)
        self.assertIn("不得把脚手架初始化", creator)
        self.assertIn("不能等待用户说“继续”", creator)
        self.assertIn("只是插入的状态问题，不会取消、暂停或替换原创建任务", creator)
        self.assertIn("只要输出 `MUST_CONTINUE=true` 就禁止最终回复和等待用户", creator)
        self.assertIn("RESPONSE_MODE=CONTINUE_TOOL_LOOP", creator)
        self.assertIn("CREATE_LOOP_LOCK=active", creator)
        self.assertIn("RESPONSE_MODE=FINAL_REPORT", creator)
        self.assertIn("CREATE_LOOP_LOCK=released", creator)
        self.assertIn("发生上下文压缩或新一轮继续时，先运行 `iteration-gate`", creator)
        self.assertIn("completion-gate", creator)
        self.assertIn("iteration-gate", creator)
        self.assertIn("只有门禁重新核对实际注册表", creator)
        self.assertIn("runtime-detect", creator)
        self.assertIn("reset-memory", creator)
        self.assertIn("用户级全局", creator)
        workflow = (ROOT / "references" / "05-生成与验证规范.md").read_text(encoding="utf-8")
        self.assertIn("RESEARCH -> RESEARCH-GATE -> GENERATE -> VALIDATE -> FIX -> TEST -> ENABLE -> COMPLETE", workflow)
        self.assertIn("不得要求用户再次发送“继续”", workflow)
        self.assertIn("用户在未完成期间询问状态、原因、限制或是否卡住时", workflow)
        self.assertIn("禁止生成脚本预填“通过”", workflow)
        openai_yaml = (ROOT / "agents" / "openai.yaml").read_text(encoding="utf-8")
        self.assertIn("不要停在初始化或进度汇报", openai_yaml)
        self.assertIn("不按版权类别、文本长度或资料完整度限制收集", creator)
        self.assertIn("表达库禁止加入人物介绍", creator)
        self.assertIn("本人或角色真实产生的逐字表达", creator)
        self.assertIn("声纹不能由模型自由概括", creator)
        self.assertIn("人物背景档案", creator)
        self.assertIn("原文卡只标来源语义", creator)
        self.assertIn("证据映射", creator)
        self.assertIn("没有可靠卡就返回空结果", creator)
        self.assertIn("把角色存在和舞台表演分开", creator)
        runtime = (ROOT / "assets" / "角色人格模板" / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("10-人物背景档案.md", runtime)
        self.assertIn("当前任务或问题命中经历", runtime)
        self.assertIn("性别相关自称、代词、称谓", runtime)
        self.assertIn("去名盲测", creator)
        self.assertNotIn("官方角色原文", persona_tool.EXACT_CARD_TYPES)
        self.assertNotIn("试用版", creator)


if __name__ == "__main__":
    unittest.main()
