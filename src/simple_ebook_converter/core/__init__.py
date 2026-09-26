"""TXT → EPUB3 核心库：解析、切分、清理、替换、组装。与前端无关，两个前端共用。

唯一总入口是 `process()`，书名/作者猜测、取值校验、无标题时的兜底标题都在那里，
前端不必各自实现。
"""

from .._meta import __version__
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
from .coverpage import (
    COVER_SECTION_TYPE,
    image_cover_body,
    text_cover_body,
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
from .mediatypes import (
    COVER_TYPES,
    FONT_TYPES,
    cover_media_type,
    find_cover,
    font_media_type,
)
from .meta import guess_metadata, resolve_metadata
from .parser import NoEnabledRulesError, ParseStats, parse, walk
from .pipeline import fallback_title, process
from .replace import (
    DEFAULT_SCOPE,
    SCOPE_ALL,
    SCOPE_BODY,
    SCOPE_CHOICES,
    SCOPE_LABELS,
    SCOPE_TITLE,
    Rule,
    apply,
    apply_lines,
    check_scope,
    compile_rules,
    rules_from_json,
    rules_to_json,
    split_by_scope,
)
from .toc import to_json, to_text

__all__ = [
    "ALIGN_CHOICES",
    "AUTO_ENCODING",
    "COVER_SECTION_TYPE",
    "COVER_TYPES",
    "DEFAULT_CHAPTER_RE",
    "DEFAULT_SCOPE",
    "DEFAULT_VOLUME_RE",
    "ENCODING_CHOICES",
    "FALLBACK_ENCODINGS",
    "FONT_TYPES",
    "LEVEL_FIELDS",
    "SCOPE_ALL",
    "SCOPE_BODY",
    "SCOPE_CHOICES",
    "SCOPE_LABELS",
    "SCOPE_TITLE",
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
    "check_scope",
    "clean_line",
    "clean_lines",
    "compile_pattern",
    "compile_rules",
    "config_defaults",
    "cover_media_type",    "decode",
    "default_levels",
    "fallback_title",
    "find_cover",
    "font_media_type",
    "guess_metadata",
    "image_cover_body",
    "parse",
    "parse_level_spec",
    "process",
    "read_lines",
    "resolve_metadata",
    "rules_from_json",
    "rules_to_json",
    "split_by_scope",
    "text_cover_body",
    "to_json",
    "to_text",
    "walk",
]
