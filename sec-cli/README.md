# sec-cli — TXT 转 EPUB3 命令行工具

将 TXT 文本解析为章节并生成 EPUB3。命令行前端；解析、切分、清理、替换与组装等核心实现都在
[`sec-core`](../sec-core)（`sec_core.*`），与 `sec-gui` 共用同一套逻辑。

依赖：`click` + `sec-core`（后者带来 `ebooklib` / `chardet`）。使用 [uv](https://github.com/astral-sh/uv) 管理。

## 安装

工作区成员为 `sec-core` / `sec-cli` / `sec-gui`。在**工作区根目录**执行：

```bash
uv sync --all-packages
```

> 直接 `uv sync` 只会装根工程（无依赖），不会安装三个成员包。

## 用法

单一命令，靠 `--toc-only` 切换「只输出目录」模式：

```bash
uv run sec-cli 我的小说.txt                       # 生成 我的小说.epub
uv run sec-cli 我的小说.txt --title "书名" --author "作者"
uv run sec-cli 我的小说.txt --toc-only            # 只输出目录（stdout）
uv run sec-cli 我的小说.txt --toc-only --toc-format json
uv run sec-cli 我的小说.txt --toc-only -o toc.json # 目录写入文件
```

书名与作者未显式指定时，会先从文件名猜（`《书名》作者：作者`，见 `sec_core.meta.resolve_metadata`）。

完整选项见 `uv run sec-cli --help`。

## 处理流程

1. 读取与编码识别（BOM → chardet → 逐个尝试，`--encoding` 可手动指定）
2. 按标题正则切分为章节（在原始行上进行，保留空行/空格信息）
3. 逐页清理（去段首/段尾空格、删空行，`--no-clean` 关闭）
4. 逐页应用替换规则（`--replace-json` / `--replace-file`，同时作用于标题与正文）
5. 组装 EPUB3（zip 最高压缩等级 `compresslevel=9`）

## 测试

```bash
uv run pytest              # 工作区根目录，全部用例
uv run pytest sec-cli      # 仅 sec-cli
```
