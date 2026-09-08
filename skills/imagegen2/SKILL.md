---
name: "imagegen2"
description: "通过 OpenAI 兼容接口生成或编辑位图图片（imagegen2 CLI）。用户需要文生图、带参考图/编辑图的生成、直播/电商/海报等营销素材、透明背景抠图，或指定 gpt-image-2 / gpt-image-1.5 / gpt-image-1 模型与 1K/2K/4K、1:1/16:9/4:3/3:4/9:16、PNG/WebP/JPEG 等参数时使用。不用于纯矢量/SVG/代码原生图形任务。"
---

# ImageGen2 Skill（OpenAI 兼容图片生成/编辑）

调用 `scripts/imagegen2.py`，走 OpenAI 兼容的 `/v1/images/generations`（文生图）与
`/v1/images/edits`（参考图/编辑图）接口生成位图素材。默认模型 `gpt-image-2`，
默认输出目录 `output/imagegen2/`（相对当前工作目录）。

## 何时使用
- 用户要求「生成一张图片 / 画一张海报 / 做直播卖货素材 / 电商主图」等文生图需求。
- 用户提供一张或多张参考图、希望基于某图做编辑/二创/换背景/加元素。
- 用户明确提到透明背景、特定比例（1:1、16:9 等）、清晰度（1K/2K/4K）、
  输出格式（PNG/WebP/JPEG）、数量 n、或指定 gpt-image 系列模型。

## 何时不用
- 图标/Logo 系统、SVG、HTML/CSS、canvas 等代码原生图形，应直接产出代码而非位图。
- 已有内置 `image_gen` 工具且用户没有指定走本 CLI 时，优先内置工具；仅在用户要求
  使用 imagegen2 / 自定义兼容端点 / 上述精细参数时才用本 skill。

## 环境与鉴权
- API key 只从环境变量 `IMAGEGEN2_API_KEY` 读取（脚本内不写死 key）；未设置时脚本会报错并提示设置方法。
- 不要在对话/代码注释/文档中复制明文 key。若需要给用户看请求示例，用 `--dry-run`，
  该模式不会携带 key。
- 若接口返回 `INSUFFICIENT_BALANCE`（HTTP 403），说明该账号余额不足，需要先充值
  或通过环境变量 `IMAGEGEN2_API_KEY` 换一个有余额的 key 再调用。
- 网络可达性：接口域名 `https://www.aivalux.com/v1`。

## 两个子命令
```bash
python3 ~/.codex/skills/imagegen2/scripts/imagegen2.py generate --prompt "..." [参数]
python3 ~/.codex/skills/imagegen2/scripts/imagegen2.py edit --image ref.png [--image ref2.png] --prompt "..." [参数]
```
- `generate`：纯文本 prompt → generations 接口。
- `edit`：带参考图/编辑图 → edits 接口（`--image` 可重复传多张，多张时接口视为参考图）。

## 常用参数
| 参数 | 说明 | 取值 / 默认 |
|---|---|---|
| `--prompt` | 图片描述（必填） | 文本 |
| `--image` | 参考/编辑图路径，edit 必填，可多次 | 路径 |
| `--model` | 模型 | `gpt-image-2`（默认）、`gpt-image-1.5`、`gpt-image-1` |
| `--n` | 张数 | 整数，默认 1，范围 1–10 |
| `--ratio` | 比例 | 不传=接口自动；`1:1` `16:9` `4:3` `3:4` `9:16` |
| `--clarity` | 清晰度 | 不传=接口自动；`1K` `2K` `4K` |
| `--size` | 直接指定尺寸（覆盖 ratio/clarity 推导） | 如 `1024x1024`，或 `auto` |
| `--quality` | 画质 | `low` `medium` `high` `auto`，默认 `medium` |
| `--background` | 背景 | `auto`（默认，自动背景）、`transparent`（透明背景） |
| `--format` | 输出格式 | `png`（默认）、`webp`、`jpeg`（别名 `--output-format`） |
| `--out` / `--out-dir` | 输出文件 / 输出目录 | 默认 `output/imagegen2/output.png`；`--out-dir` 时生成 `image_1.ext...` |
| `--force` | 允许覆盖已存在文件 | 不加时自动生成 `output-2.png` 之类的序号文件 |
| `--dry-run` | 只打印将发送的请求（不含 key），不发 API | — |
| `--no-auto-switch` | 关闭透明背景的模型自动切换（改为报错提示确认） | — |

## 比例/清晰度 → 尺寸推导（自动映射）
不传 `--ratio`/`--clarity` 时：不发送 size，由接口自动决定。
只传 `--ratio`：按该比例的 1K 档推导。只传 `--clarity`：1K→`1024x1024`、2K→`2048x2048`、
4K→`3840x2160`。两者都传时查下表：

| 比例 | 1K | 2K | 4K |
|---|---|---|---|
| 1:1 | 1024x1024 | 2048x2048 | 2880x2880（接口像素上限内最大方图） |
| 16:9 | 1536x864 | 2048x1152 | 3840x2160 |
| 9:16 | 864x1536 | 1152x2048 | 2160x3840 |
| 4:3 | 1024x768 | 2048x1536 | 2880x2160 |
| 3:4 | 768x1024 | 1536x2048 | 2160x2880 |

gpt-image-2 的尺寸约束：长边 ≤ 3840、宽高均为 16 的倍数、长宽比 ≤ 3:1、
总像素 655,360–8,294,400。上表所有值均满足；4K 档 1:1/4:3/3:4 因像素上限无法取到
4096 边长，取约束内最大近似值。

`gpt-image-1.5` / `gpt-image-1` 仅支持 `1024x1024`、`1536x1024`、`1024x1536`、`auto`；
若推导结果不在其中，脚本会自动就近调整（横图→1536x1024、竖图→1024x1536、方图→1024x1024、
超大档→auto）并打印提示。

## 其他参数映射
- 自动背景 → 请求体 `background=auto`（若接口拒绝该参数，脚本会自动去掉并重试，仅提示一次）。
- 透明背景 → 请求体 `background=transparent`。`gpt-image-2` 不支持透明背景：
  默认自动切换到 `gpt-image-1.5` 并打印提示；加 `--no-auto-switch` 则改为报错，
  等待用户确认改用 `--model gpt-image-1.5` 或改回自动背景。
- 透明背景只允许 PNG/WebP，配 JPEG 会直接报错。
- PNG/WebP/JPEG → 请求体 `output_format=png/webp/jpeg`。
- quality `low/medium/high/auto` 原样透传，默认 `medium`。

## 推荐工作流
1. 判断需求：纯文生图 → `generate`；带参考图/编辑图 → `edit`。
2. 必要时用 `--dry-run` 先核对解析后的参数与输出路径。
3. 生成后检查图片，按需单点迭代（改 prompt 或参数再跑一次）。
4. 汇报最终文件绝对路径与使用的命令；不要把 key 或完整请求头写进回复。

## 示例
```bash
# 纯文生图（默认模型/默认参数）
python3 ~/.codex/skills/imagegen2/scripts/imagegen2.py generate \
  --prompt "中转站 Token 滞销了，直播卖货风格"

# 指定 16:9 2K，自动背景，PNG
python3 ~/.codex/skills/imagegen2/scripts/imagegen2.py generate \
  --prompt "..." --ratio 16:9 --clarity 2K --format png --background auto

# 参考图/编辑图：基于已有图二创，透明背景输出
python3 ~/.codex/skills/imagegen2/scripts/imagegen2.py edit \
  --image output/imagegen2/output.png \
  --prompt "保持主体不变，改成透明背景的电商主图" \
  --background transparent --format png
```

## 说明
- 输出文件默认写到 `output/imagegen2/`（相对当前运行目录），脚本会自动创建目录。
- 已存在的文件名会自动加序号（如 `output-2.png`），除非显式 `--force`。
- 依赖：`python3` + `requests`（本机已装）。
