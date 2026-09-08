---
name: audio-gen
description: 通过 OpenAI 兼容接口把文本合成语音（TTS，audio-gen CLI）。用户需要文字转语音、生成配音/播报/有声内容、指定 gpt-4o-mini-tt 模型、音色 voice、语速 speed、输出格式 mp3/opus/aac/flac/wav/pcm 时使用。不用于音乐生成、音色克隆或非 TTS 音频任务。
---

# AudioGen Skill（OpenAI 兼容文本转语音）

调用 `scripts/audio_gen.py`，走 OpenAI 兼容的 `/v1/audio/speech` 接口把文本合成为语音。
默认模型 `gpt-4o-mini-tt`，默认输出目录 `output/audio-gen/`（相对当前工作目录）。

## 何时使用
- 用户要求「把这段话读出来 / 生成配音 / 文字转语音 / 播报 / 有声内容」等 TTS 需求。
- 用户明确提到音色 voice、语速 speed、输出格式（mp3/opus/aac/flac/wav/pcm）或指定模型 `gpt-4o-mini-tt`。

## 何时不用
- 音乐生成、音效合成、音色克隆、语音识别（ASR）等非 TTS 任务。
- 已有内置语音/音频工具且用户未指定走本 CLI 时，优先内置工具。

## 环境与鉴权
- API key 只从环境变量 `AUDIOGEN_API_KEY` 读取（脚本内不写死 key）；未设置时脚本会报错并提示设置方法。
- 不要在对话/代码注释/文档中复制明文 key。若需要给用户看请求示例，用 `--dry-run`，该模式不会携带 key。
- 端点默认 `https://www.aivalux.com/v1`，可用环境变量 `AUDIOGEN_API_BASE_URL` 覆盖为
  任意 OpenAI 兼容的 TTS 网关（脚本会拼接 `/audio/speech` 路径）。
- 注意：imagegen2 所用的 aivalux 网关目前只暴露 `gpt-image-2`（无 `/v1/audio/*` 路由），
  因此真实生成前请先把 `AUDIOGEN_API_BASE_URL` 指向支持 `/v1/audio/speech` 的端点。

## 子命令
```bash
python3 ~/.codex/skills/audio-gen/scripts/audio_gen.py generate --text "..." [参数]
```
`generate`：纯文本 → `/v1/audio/speech` 接口，返回音频二进制内容并落盘。

## 常用参数
| 参数 | 说明 | 取值 / 默认 |
|---|---|---|
| `--text` | 要合成的文本（必填） | 文本 |
| `--model` | 模型 | `gpt-4o-mini-tt`（默认） |
| `--voice` | 音色 | `alloy`（默认）、`ash`、`ballad`、`coral`、`echo`、`fable`、`onyx`、`nova`、`sage`、`shimmer`、`verse` |
| `--format` / `--response-format` | 输出格式 | `mp3`（默认）、`opus`、`aac`、`flac`、`wav`、`pcm` |
| `--speed` | 语速 | 浮点数，0.25–4.0，默认 1.0 |
| `--instructions` | 附加指令（语气/发音/停顿等，可选） | 文本 |
| `--out` | 输出文件 | 默认 `output/audio-gen/output.mp3`（扩展名按 format 自动调整） |
| `--force` | 允许覆盖已存在文件 | 不加时自动生成 `output-2.mp3` 之类序号文件 |
| `--dry-run` | 只打印将发送的请求（不含 key），不发 API | — |
| `--timeout` | API 超时秒数 | 默认 120 |

## 参数映射
- `--text` → 请求体 `input`。
- `--format mp3/opus/aac/flac/wav/pcm` → 请求体 `response_format`。
- `--voice`、`--speed`、`--instructions`（可选）原样透传。
- 输出扩展名跟随 `--format`：mp3→`.mp3`、opus→`.opus`、aac→`.aac`、flac→`.flac`、wav→`.wav`、pcm→`.pcm`。

## 推荐工作流
1. 判断需求：纯文本 → `generate`。
2. 必要时用 `--dry-run` 先核对解析后的参数与输出路径。
3. 生成后检查音频，按需调整 `--text`/`--voice`/`--speed`/`--instructions` 再跑一次。
4. 汇报最终文件绝对路径与使用的命令；不要把 key 或完整请求头写进回复。

## 示例
```bash
# 默认模型/默认音色/默认 mp3
python3 ~/.codex/skills/audio-gen/scripts/audio_gen.py generate \
  --text "中转站 Token 滞销了，直播卖货风格，快来抢购！"

# 指定音色、语速、wav 格式
python3 ~/.codex/skills/audio-gen/scripts/audio_gen.py generate \
  --text "..." --voice nova --speed 1.2 --format wav

# 附加语气指令
python3 ~/.codex/skills/audio-gen/scripts/audio_gen.py generate \
  --text "..." --instructions "用热情带货主播的语气，语速稍快，重点词加重"
```

## 说明
- 输出文件默认写到 `output/audio-gen/`（相对当前运行目录），脚本会自动创建目录。
- 已存在的文件名会自动加序号（如 `output-2.mp3`），除非显式 `--force`。
- 依赖：`python3` + `requests`（本机已装）。
