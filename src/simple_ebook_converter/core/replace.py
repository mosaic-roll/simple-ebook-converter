"""替换规则：解析、校验、按作用范围分流、执行。

规则本身是一段 JSON 里的有序列表，因此「先按哪条后按哪条」由列表顺序决定。
`Replacer` 把一批规则和它们的预编译正则绑在一起，避免在每行、每个标题上重复编译。
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path

#: 替换规则的作用范围：取值 → (中文标签, 是否改标题, 是否改正文)
SCOPES = {
    "title": ("标题", True, False),
    "body": ("正文", False, True),
    "all": ("全文", True, True),
}

#: 界面上「不选作用范围」时的取值。默认只改标题：界面只看得到目录，
#: 「默认也动正文」反而不符合直觉，要改正文时显式写出来。
DEFAULT_SCOPE = next(iter(SCOPES))

#: 文本标签 → 取值，界面下拉框直接用这份中文标签
SCOPE_BY_LABEL = {label: scope for scope, (label, _, _) in SCOPES.items()}
SCOPE_LABELS = {scope: label for scope, (label, _, _) in SCOPES.items()}


@dataclass
class Rule:
    pattern: str
    replace: str
    scope: str = DEFAULT_SCOPE

    @property
    def scope_label(self) -> str:
        return SCOPE_LABELS.get(self.scope, self.scope)


def check_scope(scope: str, where: str = "") -> str:
    """校验作用范围，界面上的中文标签也认，返回真正的取值；不合法抛 `ValueError`。"""
    resolved = SCOPE_BY_LABEL.get(scope, scope)
    if resolved not in SCOPES:
        prefix = f"{where}的 " if where else ""
        choices = "/".join(SCOPE_LABELS.values())
        raise ValueError(f"{prefix}作用范围只能是 {choices}（{'/'.join(SCOPES)}），收到：{scope!r}")
    return resolved



def rules_from_json(text: str) -> list[Rule]:
    """解析一段 JSON 替换规则（有序列表），出错抛 ValueError。

    每条规则形如 `{"pattern": "...", "replace": "...", "scope": "title"}`：
    `replace` 省略即删除匹配内容，`scope` 省略即只作用于标题。
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
                check_scope(item.get("scope", DEFAULT_SCOPE), f"第 {index} 条替换规则"),
            )
        )
    return rules


def rules_from_rows(rows: Iterable[Sequence[str] | Rule]) -> list[Rule]:
    """`(查找, 替换为, 作用范围)` 三元组 → 规则；`Rule` 原样收下。

    作用范围可给中文标签；查找为空的行忽略（表格里的空行）。
    """
    rules: list[Rule] = []
    for row in rows:
        if isinstance(row, Rule):
            rules.append(row)
            continue
        pattern, replace, scope = (list(row) + ["", ""])[:3]
        if not pattern:
            continue
        rules.append(Rule(pattern, replace, check_scope(scope or DEFAULT_SCOPE, f"规则「{pattern}」")))
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
    """序列化成 JSON 文本（`scope` 总是显式写出）。"""
    return json.dumps(
        [{"pattern": r.pattern, "replace": r.replace, "scope": r.scope} for r in rules],
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

    def lines(self, lines: Iterable[str]) -> list[str]:
        return [self.text(line) for line in lines]


def replacers_by_scope(rules: Iterable[Rule]) -> tuple[Replacer, Replacer]:
    """按作用范围拆成 (标题替换器, 正文替换器)，`scope=all` 两边都进。"""
    rules = list(rules)
    return (
        Replacer.of(r for r in rules if SCOPES[r.scope][1]),
        Replacer.of(r for r in rules if SCOPES[r.scope][2]),
    )

