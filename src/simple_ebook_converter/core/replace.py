"""替换规则：解析、校验、按阶段分流、执行。

规则本身是一段 JSON 里的有序列表，因此「先按哪条后按哪条」由列表顺序决定。
替换只作用于标题：改正文直接改源文件更直接。

`stage` 决定匹配发生在 HTML 转义的前后：

- `raw`（默认）：匹配原始标题，替换结果写出时照常转义；
- `html`：匹配已转义的标题，替换结果按 HTML 原样注入，因此可以塞
  `<span class="num">` 之类的标签，再用 `--css-append` 上样式。

`Replacer` 把一批规则和它们的预编译正则绑在一起，避免在每个标题上重复编译。
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path

#: 替换阶段：取值 → 中文标签
STAGES = {
    "raw": "原文",
    "html": "HTML",
}

#: 省略 `stage` 时的默认值：匹配原文、结果照常转义，最安全也最接近旧行为
DEFAULT_STAGE = "raw"

#: 文本标签 → 取值，界面下拉框直接用这份中文标签
STAGE_BY_LABEL = {label: stage for stage, label in STAGES.items()}
STAGE_LABELS = {stage: label for stage, label in STAGES.items()}


@dataclass
class Rule:
    pattern: str
    replace: str
    stage: str = DEFAULT_STAGE
    enabled: bool = True

    @property
    def stage_label(self) -> str:
        return STAGE_LABELS.get(self.stage, self.stage)


def check_stage(stage: str, where: str = "") -> str:
    """校验替换阶段，界面上的中文标签也认，返回真正的取值；不合法抛 `ValueError`。"""
    resolved = STAGE_BY_LABEL.get(stage, stage)
    if resolved not in STAGES:
        prefix = f"{where}的 " if where else ""
        choices = "/".join(STAGE_LABELS.values())
        raise ValueError(f"{prefix}阶段只能是 {choices}（{'/'.join(STAGES)}），收到：{stage!r}")
    return resolved



def rules_from_json(text: str) -> list[Rule]:
    """解析一段 JSON 替换规则（有序列表），出错抛 ValueError。

    每条规则形如 `{"pattern": "...", "replace": "...", "stage": "raw", "enabled": true}`：
    `replace` 省略即删除匹配内容，`stage` 省略即匹配原文（`raw`），`enabled` 省略即启用。
    """
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        raise ValueError(f"替换规则不是合法 JSON：{e}") from e
    if not isinstance(data, list):
        raise ValueError("替换规则必须是 JSON 列表")
    rules: list[Rule] = []
    for index, item in enumerate(data, start=1):
        if not isinstance(item, dict) or not isinstance(item.get("pattern"), str):
            raise ValueError(f"第 {index} 条替换规则缺少 pattern：{item!r}")
        pattern = item["pattern"]
        try:
            re.compile(pattern)
        except re.error as e:
            raise ValueError(f"第 {index} 条替换规则正则非法：{e}") from e
        rules.append(
            Rule(
                pattern,
                str(item.get("replace", "")),
                check_stage(item.get("stage", DEFAULT_STAGE), f"第 {index} 条替换规则"),
                enabled=bool(item.get("enabled", True)),
            )
        )
    return rules


def rules_from_rows(rows: Iterable[Sequence[str] | Rule]) -> list[Rule]:
    """`(查找, 替换为, 阶段)` 三元组 → 规则；`Rule` 原样收下。

    阶段可给中文标签；查找为空的行忽略（表格里的空行）。
    """
    rules: list[Rule] = []
    for row in rows:
        if isinstance(row, Rule):
            rules.append(row)
            continue
        pattern, replace, stage = (list(row) + ["", ""])[:3]
        if not pattern:
            continue
        rules.append(Rule(pattern, replace, check_stage(stage or DEFAULT_STAGE, f"规则「{pattern}」")))
    return rules


def rules_from_source(
    json_text: str | None = None,
    file: str | Path | None = None,
) -> list[Rule]:
    """从 JSON 文本或 JSON 文件读规则，两者只能给一处，都不给返回空列表。"""
    if json_text and file:
        raise ValueError("替换规则只能给一处：JSON 文本或 JSON 文件，不能同时给两处")
    if file:
        try:
            json_text = Path(file).read_text(encoding="utf-8")
        except OSError as e:
            raise ValueError(f"无法读取替换规则文件：{e}") from e
    return rules_from_json(json_text) if json_text else []


def rules_to_json(rules: Iterable[Rule]) -> str:
    """序列化成 JSON 文本（`stage` / `enabled` 总是显式写出）。"""
    return json.dumps(
        [{"pattern": r.pattern, "replace": r.replace, "stage": r.stage, "enabled": r.enabled} for r in rules],
        ensure_ascii=False,
        indent=2,
    )


@dataclass(frozen=True)
class Replacer:
    """一批规则连同预编译的正则，按规则顺序依次替换。"""

    rules: tuple[Rule, ...] = ()
    patterns: tuple[re.Pattern[str], ...] = ()

    @classmethod
    def of(cls, rules: Iterable[Rule]) -> "Replacer":
        rules = tuple(rules)
        return cls(rules, tuple(re.compile(r.pattern) for r in rules))

    def text(self, value: str) -> str:
        for rule, pattern in zip(self.rules, self.patterns):
            value = pattern.sub(rule.replace, value)
        return value


def replacers_by_stage(rules: Iterable[Rule]) -> tuple[Replacer, Replacer]:
    """按阶段拆成 (raw 替换器, html 替换器)；两个阶段一前一后作用在标题上。

    禁用的规则（`enabled=False`）直接跳过，不参与任何阶段。
    """
    rules = [r for r in rules if r.enabled]
    return (
        Replacer.of(r for r in rules if r.stage == "raw"),
        Replacer.of(r for r in rules if r.stage == "html"),
    )

