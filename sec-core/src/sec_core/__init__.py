"""TXT 转 EPUB3 核心库：sec-cli 与 sec-gui 共用。"""

from importlib.metadata import version

from .builder import build_css, build_epub, font_media_type
from .cleaner import clean_line, clean_lines
from .config import (
    ALIGN_CHOICES,
    DEFAULT_CHAPTER_RE,
    DEFAULT_VOLUME_RE,
    LEVEL_FIELDS,
    Config,
    LevelRule,
    Node,
    config_defaults,
    default_levels,
)
from .encoding import (
    AUTO_ENCODING,
    ENCODING_CHOICES,
    FALLBACK_ENCODINGS,
    EncodingError,
    decode,
    read_lines,
)
from .levels import build_levels, compile_pattern, parse_level_spec
from .meta import guess_metadata, resolve_metadata
from .parser import NoEnabledRulesError, ParseStats, parse, walk
from .pipeline import fallback_title, process
from .replace import Rule, apply, apply_lines, compile_rules, rules_from_json
from .toc import to_json, to_text

#: 版本号以 pyproject.toml 为唯一真源
__version__ = version("sec-core")

__all__ = [
    "ALIGN_CHOICES",
    "AUTO_ENCODING",
    "DEFAULT_CHAPTER_RE",
    "DEFAULT_VOLUME_RE",
    "ENCODING_CHOICES",
    "FALLBACK_ENCODINGS",
    "LEVEL_FIELDS",
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
    "compile_pattern",
    "compile_rules",
    "config_defaults",
    "decode",
    "default_levels",
    "fallback_title",
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
