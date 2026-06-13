# Matt Wolfe 中文播报

每日精选 Matt Wolfe 的最新 AI 资讯，中文同音翻译播客，开车通勤最佳伴侣。

## 功能特性

- **自动抓取**：每天定时从 Matt Wolfe YouTube 频道获取最新视频
- **智能翻译**：使用大语言模型将英文内容翻译为自然流畅的中文
- **语音合成**：基于 Edge TTS 引擎，生成高质量中文语音
- **RSS 输出**：生成标准播客 RSS feed，支持小宇宙等平台接入
- **全自动运行**：支持 Windows 任务计划程序定时执行

## 安装步骤

### 1. 克隆项目

```bash
git clone <your-repo-url> matt-wolfe-podcast
cd matt-wolfe-podcast
```

### 2. 安装依赖

本项目依赖 Python 3.9+。

```bash
pip install -r requirements.txt
```

### 3. 配置环境变量

复制环境变量模板并填入你的 API Key：

```bash
copy .env.template .env
```

编辑 `.env` 文件，填入你的 Anthropic API Key（兼容 DeepSeek API 端点）。

### 4. 检查配置

编辑 `config.yaml`，按需调整以下设置：

- `llm.model`：使用的语言模型
- `tts.voice`：TTS 语音角色
- `podcast.title`：播客名称
- `schedule.daily_time`：每日运行时间

## 使用方法

### 查看支持的 TTS 语音

```bash
python run.py list-voices
```

### 查看运行状态

```bash
python run.py status
```

### 试运行（不实际生成音频）

```bash
python run.py dry-run
```

### 运行一次（抓取 + 翻译 + TTS + RSS）

```bash
python run.py run
```

### 查询子命令帮助

```bash
python run.py --help
```

## 自动化设置（Windows 任务计划程序）

1. 打开 **任务计划程序**（Task Scheduler）
2. 创建基本任务
3. 触发器：每天，时间设为 `21:00`（与 `config.yaml` 中的 `daily_time` 一致）
4. 操作：启动程序
   - 程序或脚本：`python`
   - 参数：`run.py run`
   - 起始于：`C:\path\to\matt-wolfe-podcast`
5. 确保运行用户已登录或选择"不管用户是否登录都要运行"

## 配置说明

`config.yaml` 字段详解：

| 字段 | 说明 | 默认值 |
|------|------|--------|
| `channel.youtube_url` | YouTube 频道 URL | `https://www.youtube.com/@mattwolfe` |
| `channel.channel_id` | YouTube 频道 ID（可选，留空自动解析） | `""` |
| `llm.provider` | LLM 提供商 | `anthropic` |
| `llm.model` | 模型名称 | `deepseek-v4-flash` |
| `llm.max_tokens` | 最大生成 token 数 | `4096` |
| `llm.temperature` | 生成温度 | `0.3` |
| `tts.engine` | TTS 引擎 | `edge-tts` |
| `tts.voice` | TTS 语音角色 | `zh-CN-XiaoxiaoNeural` |
| `tts.rate` | 语速调整 | `+0%` |
| `tts.volume` | 音量调整 | `+0%` |
| `podcast.title` | 播客标题 | `Matt Wolfe 中文播报` |
| `podcast.description` | 播客描述 | 见默认值 |
| `podcast.author` | 播客作者 | `AI 播客工坊` |
| `podcast.language` | 播客语言 | `zh-CN` |
| `podcast.website` | 播客网站 URL | GitHub Pages 地址 |
| `podcast.episode_image_url` | 单集封面图 URL（可选） | `""` |
| `podcast.feed_filename` | RSS feed 文件名 | `feed.xml` |
| `schedule.daily_time` | 每日运行时间 | `21:00` |
| `schedule.max_episodes_per_run` | 每次运行最多处理集数 | `1` |

## 小宇宙接入指南

1. 确保 `public/feed.xml` 可通过公网访问（建议部署到 GitHub Pages 或 Vercel）
2. 打开小宇宙 App
3. 进入"发现" -> 右上角 RSS 订阅
4. 输入 RSS feed 地址：`https://<你的域名>/matt-wolfe-podcast/feed.xml`
5. 点击订阅即可

### 部署到 GitHub Pages

1. 在 GitHub 上创建仓库并推送代码
2. 进入仓库 Settings -> Pages
3. Source 选择 `GitHub Actions`
4. 创建 GitHub Actions workflow，定时运行 `python run.py run` 并将 `public/` 目录部署到 Pages

## 项目结构

```
matt-wolfe-podcast/
├── config.yaml          # 配置文件
├── .env                 # 环境变量（不提交到 Git）
├── .env.template        # 环境变量模板
├── requirements.txt     # Python 依赖
├── run.py              # 主入口脚本
├── podcast/
│   ├── __init__.py      # 包初始化
│   ├── fetcher.py       # YouTube 视频抓取
│   ├── translator.py    # 翻译模块
│   ├── tts_engine.py    # 语音合成引擎
│   └── feed_builder.py  # RSS feed 生成
├── data/
│   └── episodes/        # 音频文件存储目录
├── public/
│   └── feed.xml         # 生成的 RSS feed
└── README.md
```

## 许可证

MIT
