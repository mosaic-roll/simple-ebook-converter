"""TXT 转 EPUB3 核心库：sec-cli 与 sec-gui 共用。"""

from .builder import build_css, build_epub, font_media_type
from .cleaner import clean_line, clean_lines
from .config import (
    DEFAULT_CHAPTER_RE,
    DEFAULT_VOLUME_RE,
    Config,
    LevelRule,
    Node,
    config_defaults,
    default_levels,
)
from .encoding import EncodingError, decode, read_lines
from .levels import build_levels, parse_level_spec
from .meta import guess_metadata, resolve_metadata
from .parser import NoEnabledRulesError, ParseStats, parse, walk
from .pipeline import process
from .replace import Rule, apply, apply_lines, compile_rules, rules_from_json
from .toc import to_json, to_text

__all__ = [
    "DEFAULT_CHAPTER_RE",
    "DEFAULT_VOLUME_RE",
    "Config",
    "EncodingError",
    "LevelRule",
    "NoEnabledRulesError",
    "Node",
    "ParseStats",
    "Rule",
    "apply",
    "apply_lines",
    "build_css",
    "build_epub",
    "build_levels",
    "clean_line",
    "clean_lines",
    "compile_rules",
    "config_defaults",
    "decode",
    "default_levels",
    "font_media_type",
    "guess_metadata",
    "parse",
    "parse_level_spec",
    "process",
    "read_lines",
    "resolve_metadata",
    "rules_from_json",
    "to_json",
    "to_text",
    "walk",
]

__version__ = "0.1.0"
