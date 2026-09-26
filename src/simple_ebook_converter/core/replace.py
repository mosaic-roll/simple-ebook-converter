from __future__ import annotations

import json
import re
from dataclasses import dataclass

#: 替换规则的作用范围。默认只作用于标题：GUI 里只能看到目录，
#: 「默认只改标题」才符合直觉；需要改正文或两者都改得显式写 `"scope"`。
SCOPE_TITLE = "title"
SCOPE_BODY = "body"
SCOPE_ALL = "all"

SCOPE_CHOICES = (SCOPE_TITLE, SCOPE_BODY, SCOPE_ALL)
DEFAULT_SCOPE = SCOPE_TITLE

#: 供前端显示用的中文标签，避免 GUI 另写一份映射
SCOPE_LABELS = {SCOPE_TITLE: "标题", SCOPE_BODY: "正文", SCOPE_ALL: "全文"}


@dataclass
class Rule:
    pattern: str
    replace: str
    scope: str = DEFAULT_SCOPE

    def compile(self) -> re.Pattern[str]:
        return re.compile(self.pattern)

    @property
    def scope_label(self) -> str:
        return SCOPE_LABELS.get(self.scope, self.scope)


def check_scope(scope: str, index: int | None = None) -> str:
    """校验作用范围并返回它，出错抛 ValueError（消息可直接展示给用户）。"""
    if scope not in SCOPE_CHOICES:
        where = f"第 {index} 条替换规则的 " if index is not None else ""
        supported = "/".join(SCOPE_CHOICES)
        raise ValueError(f"{where}scope 只能是 {supported}，收到：{scope!r}")
    return scope


def rules_from_json(text: str) -> list[Rule]:
    """解析一段替换规则 JSON（有序列表），出错抛 ValueError。CLI 与 GUI 共用。

    `scope` 可省略，省略时为 `"title"`（只作用于标题）。
    """
    data = json.loads(text)
    if not isinstance(data, list):
        raise ValueError("替换规则必须是 JSON 列表")
    rules: list[Rule] = []
    for index, item in enumerate(data, start=1):
        if not isinstance(item, dict) or "pattern" not in item:
            raise ValueError(f"替换规则条目格式错误：{item!r}")
        pattern = item["pattern"]
        try:
            re.compile(pattern)
        except re.error as e:
            raise ValueError(f"第 {index} 条替换规则正则非法：{e}") from e
        scope = check_scope(item.get("scope", DEFAULT_SCOPE), index)
        rules.append(Rule(pattern, item.get("replace", ""), scope))
    return rules


def rules_to_json(rules: list[Rule]) -> str:
    """把规则序列化成 JSON 文本（GUI 导出用；`scope` 总是显式写出）。"""
    return json.dumps(
        [{"pattern": r.pattern, "replace": r.replace, "scope": r.scope} for r in rules],
        ensure_ascii=False,
        indent=2,
    )


def compile_rules(rules: list[Rule]) -> list[re.Pattern[str]]:
    return [r.compile() for r in rules]


def split_by_scope(rules: list[Rule]) -> tuple[list[Rule], list[Rule]]:
    """按作用范围拆成 (标题规则, 正文规则)；`scope="all"` 两边都算。

    拆完各自编译一次，避免在每行、每个标题上重复编译正则。
    """
    title = [r for r in rules if r.scope in (SCOPE_TITLE, SCOPE_ALL)]
    body = [r for r in rules if r.scope in (SCOPE_BODY, SCOPE_ALL)]
    return title, body


def apply(text: str, rules: list[Rule], compiled: list[re.Pattern[str]] | None = None) -> str:
    if not rules:
        return text
    if compiled is None:
        compiled = compile_rules(rules)
    for rule, pat in zip(rules, compiled):
        text = pat.sub(rule.replace, text)
    return text


def apply_lines(
    lines: list[str],
    rules: list[Rule],
    compiled: list[re.Pattern[str]] | None = None,
) -> list[str]:
    if not rules:
        return lines
    return [apply(line, rules, compiled) for line in lines]
