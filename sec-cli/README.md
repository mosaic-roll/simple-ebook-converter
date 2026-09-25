# sec-cli — TXT 转 EPUB3 命令行工具

将 TXT 文本解析为章节并生成 EPUB3。核心模块（`sec_cli.parser` / `sec_cli.builder` / `sec_cli.toc` 等）设计为可被 CLI 与 `sec-gui` 共用。

依赖：`click` / `ebooklib` / `chardet`。使用 [uv](https://github.com/astral-sh/uv) 管理。

## 安装

`sec-cli` 是 `sec` 工作区（`sec-cli` + `sec-gui`）的成员，在工作区根目录执行：

```bash
uv sync
```

## 用法

单一命令，靠 `--toc-only` 切换「只输出目录」模式：

```bash
uv run sec-cli 我的小说.txt                       # 生成 我的小说.epub
uv run sec-cli 我的小说.txt --title "书名" --author "作者"
uv run sec-cli 我的小说.txt --toc-only            # 只输出目录（stdout）
uv run sec-cli 我的小说.txt --toc-only --toc-format json
uv run sec-cli 我的小说.txt --toc-only -o toc.json # 目录写入文件
```

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
