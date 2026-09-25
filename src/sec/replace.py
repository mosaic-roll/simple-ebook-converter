from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class Rule:
    pattern: str
    replace: str

    def compile(self) -> re.Pattern[str]:
        return re.compile(self.pattern)


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