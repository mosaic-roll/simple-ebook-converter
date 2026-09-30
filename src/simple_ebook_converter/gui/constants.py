"""跨模块共享的常量、选项列表、字体预设表、主题调色板。

判断一个常量放哪，问一句「谁会用它」：

- 两个以上模块用、且是纯数据 → 放这里
- 只有一个模块用 → 留在那个模块里（如 `toc_panel.TOC_*`、`settings_dialog.SETTINGS_*`）
- 是某个模块自己的实现细节 → 也留在那个模块（如 `fonts.FONT_*_OFFSET`）

本模块**不依赖任何其他 gui 模块**，只 import 标准库。
"""

from __future__ import annotations

# ==========================================================================
# 通用间距
# ==========================================================================

PAD = 6
GAP = 6
ROW_PADY = 5
LABEL_PADX = (10, 6)
FIELD_PADX = (0, 10)

# ==========================================================================
# 分组框
# ==========================================================================

GROUP_PADX = 10
GROUP_PADY = (8, 0)
GROUP_TITLE_PADY = (6, 2)

# ==========================================================================
# 复选框 / 分段按钮 / 多行文本
# ==========================================================================

CHECK_PADX = 10
CHECK_PADY_LAST = (0, 10)
CHECK_PADY_MID = (0, 6)
SEG_PADY = (6, 4)

# ==========================================================================
# 顶部栏 / 底部栏
# ==========================================================================

BAR_PADX = 14
BAR_PADY = 6
BAR_HEIGHT_TOP = 40
BAR_HEIGHT_BOTTOM = 44

# ==========================================================================
# 通用控件尺寸
# ==========================================================================

BTN_W_XS = 28  # ↑ ↓ ✕
BTN_W_S = 56  # 浏览、设置、查看
BTN_W_M = 60  # 导入、导出、删除、恢复
BTN_W_L = 80  # 恢复默认、应用、取消
BTN_W_XL = 90  # 重新扫描、添加规则、＋添加、－删除
BTN_GAP = 4  # 并排按钮之间

OPTION_W_S = 70  # 目录深度、额外层级
OPTION_W_M = 90  # 阶段
ENTRY_W_M = 80  # class
GEN_BTN_W = 140
GEN_BTN_H = 28

# ==========================================================================
# 窗口几何
# ==========================================================================

WINDOW_TITLE = "Simple Ebook Converter"
WINDOW_SIZE = "900x720"
WINDOW_MIN = (720, 600)

# ==========================================================================
# 选项列表
# ==========================================================================
# 这些将来要跟 core 对齐（core.config.DEFAULTS / core.encoding.ENCODING_CHOICES /
# core.replace.STAGE_LABELS），所以留在 constants 里作为项目级约定。值与 core
# 取值的对应关系也放这儿（见 FONT_PRESETS_BY_OS），界面上只显示中文。

#: 对齐方式：界面文字 → core 取值（取值同 core.config.ALIGN_CHOICES）
ALIGN_LABELS = {
    "左对齐": "left",
    "居中": "center",
    "右对齐": "right",
    "两端对齐": "justify",
}
HEADINGS = ["h1", "h2", "h3", "h4", "h5", "h6"]
STAGES = ["原文", "HTML"]

#: 编码预设：显示名 -> Python codec 名（收集时用 `.get(显示名, 显示名)` 换回值，同 `ALIGN_LABELS`）。
#: 显示用大家习惯的叫法，存值必须是 codec 名。cp932 与 shift_jis 是两个 codec（前者是
#: 微软扩展），两个都列才选得到。
#: 这不是 core 的 `FALLBACK_ENCODINGS`（那是探测失败后的回退顺序），也不是白名单——
#: core 只查 `codecs.lookup()` 解不解析得开，表外的合法 codec 照样能用。
ENCODING_LABELS: dict[str, str] = {
    "自动探测": "auto",
    "UTF-8": "utf-8",
    "简体中文 GB18030": "gb18030",
    "繁体中文 Big5": "big5",
    "日文 CP932（微软扩展）": "cp932",
    "日文 Shift_JIS（标准）": "shift_jis",
}
#: EPUB 3 的 `dc:language` 写 BCP 47 标签，日文是 `ja`；`jp` 是地区代码，不是语言码。
LANGUAGES = ["zh", "en", "ja"]
TOC_DEPTHS = [str(i) for i in range(1, 7)]

#: 目录表的 ttk tag 名。`theme.py` 按这三个名字配色、`toc_panel.py` 按同三个名字挂载，
#: 只写一份。「既删除又命中 html」单独一个 tag，是为了删线和变色能同时看见，
#: 不去赌 Tk 多 tag 时哪个的颜色生效。
TAG_DELETED = "deleted"
TAG_HTML = "html"
TAG_HTML_DELETED = "html_deleted"

# ==========================================================================
# 字号
# ==========================================================================

FONT_SIZES = ["默认"] + [str(i) for i in range(9, 21)]
DEFAULT_UI_SIZE = 13
DEFAULT_TOC_SIZE = 14
DEFAULT_FONT_LABEL = "系统默认"
SIZE_LABEL_DEFAULT = FONT_SIZES[0]

# ==========================================================================
# 字体预设：显示名 → 实际字体族名（按操作系统分表）
# ==========================================================================

FONT_PRESETS_BY_OS = {
    "win32": {
        "系统默认": "Microsoft YaHei",
        "微软雅黑": "Microsoft YaHei",
        "宋体": "SimSun",
        "黑体": "SimHei",
        "楷体": "KaiTi",
        "仿宋": "FangSong",
    },
    "darwin": {
        "系统默认": "TkDefaultFont",
        "苹方": "PingFang SC",
        "冬青黑体": "Hiragino Sans GB",
        "华文黑体": "STHeiti",
        "宋体-简": "Songti SC",
        "楷体-简": "Kaiti SC",
    },
    "linux": {
        "系统默认": "TkDefaultFont",
        "Noto Sans CJK": "Noto Sans CJK SC",
        "文泉驿微米黑": "WenQuanYi Micro Hei",
        "文泉驿正黑": "WenQuanYi Zen Hei",
        "思源黑体": "Source Han Sans SC",
        "思源宋体": "Source Han Serif SC",
    },
}

# ==========================================================================
# 主题调色板
# ==========================================================================
# 目录表格是 ttk 控件，配色不走 CTk 的主题机制，这里手写两套。
# 新增表格样式时只在这里加键，theme.py 统一套用。

THEME_DARK = {
    "bg": "#2b2b2b",
    "fg": "#e0e0e0",
    "field": "#2b2b2b",
    "head_bg": "#3a3a3a",
    "head_fg": "#e0e0e0",
    "sel_bg": "#1f538d",
    "sel_fg": "#ffffff",
    "del_fg": "#8a8a8a",
    "html_fg": "#4a9eff",
}

THEME_LIGHT = {
    "bg": "#ffffff",
    "fg": "#000000",
    "field": "#ffffff",
    "head_bg": "#e5e5e5",
    "head_fg": "#000000",
    "sel_bg": "#3b8ed0",
    "sel_fg": "#ffffff",
    "del_fg": "gray60",
    "html_fg": "#1668c4",
}

#: 主题切换分段按钮的取值
THEME_CHOICES = ["浅色", "深色"]
THEME_CHOICE_DARK = "深色"
DEFAULT_THEME_CHOICE = "浅色"

#: 状态文字配色：kind → (浅色, 深色)。CTk 外观模式二元组，由 CTk 自己按当前模式
#: 取值，所以不走 theme.py 的调色板（那一套只喂 ttk 的目录表格）。
STATUS_COLORS = {
    "info": ("gray30", "gray70"),
    "ok": ("green4", "lightgreen"),
    "error": ("firebrick3", "salmon"),
}
