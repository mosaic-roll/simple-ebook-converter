from __future__ import annotations

import json
import re
from dataclasses import dataclass


@dataclass
class Rule:
    pattern: str
    replace: str

    def compile(self) -> re.Pattern[str]:
        return re.compile(self.pattern)


def rules_from_json(text: str) -> list[Rule]:
    """解析一段替换规则 JSON（有序列表），出错抛 ValueError。CLI 与 GUI 共用。"""
    data = json.loads(text)
    if not isinstance(data, list):
        raise ValueError("替换规则必须是 JSON 列表")
    rules: list[Rule] = []
    for item in data:
        if not isinstance(item, dict) or "pattern" not in item:
            raise ValueError(f"替换规则条目格式错误：{item!r}")
        rules.append(Rule(item["pattern"], item.get("replace", "")))
    return rules


def compile_rules(rules: list[Rule]) -> list[re.Pattern[str]]:
    return [r.compile() for r in rules]


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