# -*- mode: python ; coding: utf-8 -*-
"""把命令行版与图形界面版打进同一个发行目录，共用一份 `_internal`。

为什么必须写 spec：PyInstaller 每次 onedir 打包都会生成自己独立的 `_internal`，
两次打包就是两个目录，Python 运行时和依赖各存一份，没有任何命令行开关能把它们
合并。要让多个 exe 共用一份依赖，官方做法就是把多个 `Analysis` 的
`binaries` / `datas` 一起交给同一个 `COLLECT`，由它去重。

控制台行为在这个方案里是「天生正确」的：`console` 是每个 `EXE` 独立的属性，
所以命令行版 `console=True` 能正常输出，图形界面版 `console=False` 是 GUI 子系统、
双击没有黑框。原先那套 `ShowWindow` / `FreeConsole` 运行时 hack 全部不需要。

代价：`_internal` 是两者依赖的并集，因此不能按 exe 单独排除模块
（例如不能为了命令行版排掉 tkinter，因为图形界面版要用）。

`EXCLUDES` 是对两者统一生效的排除表，理由见那里的注释。
"""

from pathlib import Path

from PyInstaller.utils.hooks import copy_metadata

# SPECPATH 由 PyInstaller 注入，指向本 spec 所在目录
SPEC_DIR = Path(SPECPATH)
SRC_DIR = SPEC_DIR.parent / "src"

DIST_NAME = "simple-ebook-converter"

# 统一排除的模块。判断依据是「运行期没人 import 它」，不是「看着像用不上」。
EXCLUDES = [
    # ── ssl 与它的整条上游 ──
    #
    # 本项目纯本地跑，不联网。ssl 完全是静态分析的连带品，跟业务代码没关系：
    # ebooklib.utils 的 `parse_html_string()` 在函数体内 `from lxml import html`，
    # PyInstaller 不区分函数体内外的 import，于是把 lxml.html 收进来，
    # 它又 import urllib.request → ftplib → ssl。
    # 而 `parse_html_string()` 在 ebooklib 0.20 里没有任何调用方（本仓库也用不到），
    # 这条链从头到尾是死的。
    #
    # 连带排除 ftplib / netrc / http.client / urllib.request：它们只是 ssl 的上游，
    # 排掉 ssl 之后剩下的这几块对文本转换一行都用不到。
    # 一并写出来是为了让「为什么不联网」在 spec 里自证，而不是靠人记得。
    "ssl",
    "_ssl",
    "ftplib",
    "netrc",
    "http.client",
    "urllib.request",
    # ── _hashlib ──
    #
    # 排掉 _ssl.pyd 只省下 libssl-3-x64.dll，libcrypto-3-x64.dll（5.7 MB，本仓库最大单个文件）
    # 仍会被收，因为 _hashlib.pyd 静态链接了它。真正的大头要连 _hashlib 一起排。
    #
    # 代价：hashlib 少了 OpenSSL 提供的那批算法（md4 / ripemd160 / sm3 / whirlpool 等）
    # 与 pbkdf2_hmac / scrypt。但常用摘要不受影响——hashlib 会回退到
    # _md5 / _sha1 / _sha2 / _sha3 / _blake2，这些在 Windows 版 CPython 里是
    # 编译进 python3.dll 的内置模块，冻结后照样能 import，不需要额外打包。
    # 已实测：md5 / sha1 / sha256 / sha512 / blake2b / sha3_256、hmac、
    # random、uuid4、secrets、hashlib.file_digest 全部正常。
    # 文本转 EPUB 用不到被舍掉的那部分。
    "_hashlib",
]

# 冻结后的程序仍要靠 importlib.metadata 查自己的版本号，所以把 dist-info 拷进去，
# 等价于命令行方式的 --copy-metadata
METADATA = copy_metadata(DIST_NAME)


def analyze(entry, hiddenimports=()):
    return Analysis(
        [str(SPEC_DIR / entry)],
        pathex=[str(SRC_DIR)],
        binaries=[],
        datas=METADATA,
        # customtkinter 是在函数体内 import 的，静态分析能覆盖到，但显式声明更稳妥
        hiddenimports=list(hiddenimports),
        hookspath=[],
        hooksconfig={},
        runtime_hooks=[],
        excludes=list(EXCLUDES),
        noarchive=False,
        optimize=0,
    )


a_cli = analyze("entry_cli.py")
a_gui = analyze("entry_gui.py", hiddenimports=["customtkinter"])

pyz_cli = PYZ(a_cli.pure)
pyz_gui = PYZ(a_gui.pure)

# exclude_binaries=True：二进制不进 exe，交给下面的 COLLECT 统一存放，
# 这样两个 exe 才会共用同一个 _internal 而不是各带一份
exe_cli = EXE(
    pyz_cli,
    a_cli.scripts,
    [],
    exclude_binaries=True,
    name=f"{DIST_NAME}-cli",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

exe_gui = EXE(
    pyz_gui,
    a_gui.scripts,
    [],
    exclude_binaries=True,
    name=DIST_NAME,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    # 崩溃时弹出错误对话框：GUI 子系统没有控制台，否则出错会完全静默
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe_cli,
    exe_gui,
    a_cli.binaries,
    a_cli.datas,
    a_gui.binaries,
    a_gui.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name=DIST_NAME,
)