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
"""

from pathlib import Path

from PyInstaller.utils.hooks import copy_metadata

# SPECPATH 由 PyInstaller 注入，指向本 spec 所在目录
SPEC_DIR = Path(SPECPATH)
SRC_DIR = SPEC_DIR.parent / "src"

DIST_NAME = "simple-ebook-converter"

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
        excludes=[],
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