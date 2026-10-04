# simple-ebook-converter-cli 命令行说明书

本文档面向用户，介绍如何使用命令行转换电子书。

## 基本用法

```bash
uv run simple-ebook-converter-cli 我的小说.txt           # 生成 我的小说.epub
uv run simple-ebook-converter-cli -i 输入.txt -o 输出    # 指定输入输出
uv run simple-ebook-converter-cli --help                 # 查看全部选项
```

## 常用选项

| 选项 | 说明 |
|------|------|
| `--title TEXT` | 书名，不写则从文件名猜（`《书名》作者：作者`） |
| `--author TEXT` | 作者，不写则从文件名猜 |
| `--date TEXT` | 出版日期，如 `2024-05-13`，不写则省略 |
| `--language zh` | 语言代码（默认 `zh`） |
| `--cover cover.jpg` | 封面图片路径，不写则自动发现同目录的 `cover.*` |
| `--no-text-cover` | 不要文字封面页 |
| `--no-overwrite` | 输出文件已存在时不覆盖 |

## 章节识别

程序按标题正则把 TXT 切分成章节。内置默认能识别常见的「第X章」「Chapter 1」等格式。

```bash
# 自定义卷/章标题正则
uv run simple-ebook-converter-cli 我的小说.txt \
  --volume "自定义卷正则" --chapter "自定义章正则"

# 关闭卷识别（只识别章节）
uv run simple-ebook-converter-cli 我的小说.txt --no-volume
```

## 替换规则

对识别出的标题做文字修改，规则写在 JSON 文件里：

```json
[
  { "pattern": "^第(.+)章\\s*", "replace": "第\\1章 " },
  { "pattern": "(第.{1,10}章)\\s*", "replace": "<span class=\"chapter-number\">\\1</span>", "stage": "html" }
]
```

| `stage` | 说明 |
|---------|------|
| `raw`（默认） | 改纯文本标题，影响目录和元数据 |
| `html` | 改书页 HTML，可注入标签配合 CSS 样式 |

## 只输出目录

```bash
uv run simple-ebook-converter-cli 我的小说.txt --toc-only          # 输出到 stdout
uv run simple-ebook-converter-cli 我的小说.txt --toc-only -o toc.json --toc-format json
```

## 排版选项

| 选项 | 说明 | 默认 |
|------|------|------|
| `--indent N` | 缩进字数 | 2 |
| `--line-height TEXT` | 行高，如 `1.5` | 1.5 |
| `--para-spacing TEXT` | 段间距，如 `1em` / `12px` | 1em |
| `--chapter-align center` | 章标题对齐（left/center/right/justify） | center |

## 禁用默认行为

| 默认开启 | 禁用参数 |
|----------|----------|
| 清理段首空格与空行 | `--no-clean` |
| 自动发现封面 | `--no-cover-discovery` |
| 生成文字封面页 | `--no-text-cover` |
| 识别卷标题 | `--no-volume` |
| 覆盖已有文件 | `--no-overwrite` |
