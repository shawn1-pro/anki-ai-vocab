# Anki AI Vocab

Ubuntu 上的 AI 英语收词工具，适合阅读论文、技术文档和代码时积累词汇。

**输入或复制单词 → DeepSeek 生成简短释义与例句 → 预览修改 → 确认保存到 Anki → 手机同步复习。**

- 桌面窗口和命令行两种入口，支持原句语境、自定义领域、词性及标签。
- 自动查重、本地缓存；可跳过、更新兼容笔记或按不同领域新增。
- 显示累计 token 用量及人民币费用估算，支持窗口大小记忆与固定。
- 通过 AnkiConnect 写入本机 Anki，再使用 AnkiWeb 同步到 AnkiDroid。

## 快速开始

需要 Ubuntu 22.04 / Python 3.10+、[Anki](https://apps.ankiweb.net/)、[AnkiConnect 插件](https://ankiweb.net/shared/info/2055492159)和 [DeepSeek API Key](https://platform.deepseek.com/)。

### 1. 安装

下载或克隆本项目，进入项目根目录。以下命令适用于 zsh 和 Bash：

```bash
sudo apt update
sudo apt install python3-venv python3-pip python3-tk gnome-terminal

python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip setuptools wheel
python -m pip install -e .
```

### 2. 配置密钥

```bash
cp -n .env.example .env
chmod 600 .env
nano .env
```

在 `.env` 中填写 `DEEPSEEK_API_KEY`。如果 AnkiConnect 设置了 `apiKey`，再填写 `ANKICONNECT_API_KEY`。进程环境变量优先于 `.env`。

### 3. 打开 Anki 并启动

在 Anki 中启用 AnkiConnect，并创建牌组 **专业学习**；已有该牌组则直接使用。Anki 需保持运行。

```bash
anki-word doctor
anki-word gui
```

`doctor` 只读检查连接、牌组和配置，不调用 DeepSeek；密钥是否有效需通过生成操作验证。

## 日常使用

### 桌面窗口

输入单词、选择领域 → 点击“生成预览” → 修改内容 → 点击“保存到 Anki”并确认。只想查词，看完关闭即可。

- 在“原句”框粘贴上下文，生成结果会使用原句作为例句。
- `Ctrl+Enter` 生成预览；“重新生成”可能再次产生 API 费用。
- 拖动边缘调整窗口，勾选“固定窗口大小”锁定；关闭后会记住尺寸。

安装桌面与应用菜单图标，在项目根目录执行一次：

```bash
.venv/bin/python scripts/install_desktop.py
```

安装器会创建当前用户的应用菜单和桌面入口。之后搜索“AI 英语收词”或点击图标即可；若提示不受信任，右键选择“允许启动”。项目移动后需更新启动路径，安装器不会覆盖内容不同的同名文件。

也可直接运行启动脚本，它会自动定位项目、虚拟环境和 `.env`：

```bash
/bin/bash scripts/launch_gui.sh
```

### 命令行

```bash
anki-word add degeneracy --topic SLAM
anki-word add covariance --topic "Control Theory"
anki-word add iterator --topic "C++"
anki-word add degeneracy --topic SLAM \
  --context "Geometric degeneracy may cause localization drift."
```

预览菜单：`s` 保存、`c` 或回车取消、`e` 编辑、`r` 重新生成。可添加 `--force` 绕过缓存；`--preview-only` 仅生成预览，跳过 Anki 检查和写入，但仍可能产生 API 费用。

预设领域包括 General、SLAM、Computer Vision、C++、Python、Robotics、Mathematics、Control Theory。可直接填写自定义领域，如 `--topic ROS2`。

### 剪贴板收词

按桌面会话安装相应工具，可用 `echo "$XDG_SESSION_TYPE"` 查看会话类型：

```bash
sudo apt install xclip          # X11；也可安装 xsel
sudo apt install wl-clipboard   # Wayland
```

在阅读软件中复制单词或英文原句，再运行：

```bash
anki-word clipboard --topic SLAM
```

复制整句时，按编号或输入单词选择目标词，完整原句会保留为语境。文本上限为 8000 字符。

**自动读取剪贴板的入口使用终端选词和确认；桌面窗口使用 Ctrl+V 粘贴单词及原句。**

## 全局快捷键

在项目根目录执行以下命令，复制输出的整行内容：

```bash
# 打开桌面窗口
printf '/bin/bash "%s/scripts/launch_gui.sh"\n' "$PWD"

# 自动读取剪贴板，打开终端选词和确认
printf '/bin/bash "%s/scripts/launch_clipboard.sh" --topic SLAM\n' "$PWD"
```

进入 Ubuntu **设置 → 键盘 → 查看及自定义快捷键 → 自定义快捷键**，填写名称，将所需入口的输出粘贴到 **Command**，再设置组合键。

候选组合为 `Ctrl+Alt+W`、`Ctrl+Alt+E`、`Super+Shift+W`；若冲突，保留已有绑定并换一个。桌面启动推荐使用项目 `.env`，不依赖 `.zshrc` 中导出的密钥。

关闭当前窗口可用 `Alt+F4`，或在 **窗口 → 关闭窗口** 中自定义；此动作不需要填写 Command。参见 [GNOME 快捷键说明](https://help.gnome.org/gnome-help/keyboard-shortcuts-set.html)。

## 配置与数据

需要修改默认设置时：

```bash
cp -n config.example.json config.json
nano config.json
```

| 配置项 | 默认值 | 用途 |
| --- | --- | --- |
| `model` | `deepseek-flash` | DeepSeek 模型 |
| `deepseek_base_url` | `https://api.deepseek.com` | 官方 API 地址 |
| `deck` | `专业学习` | 已存在的目标牌组 |
| `anki_url` | `http://127.0.0.1:8765` | 本机 AnkiConnect 地址 |
| `default_topic` | `General` | 默认领域 |
| `api_timeout` / `anki_timeout` | `30` / `10` | 网络超时，秒 |
| `max_tokens` | `1000` | 单次输出上限，支持 128–4096 |
| `data_dir` | `data` | 缓存、用量和窗口偏好目录 |

完整选项见 [config.example.json](config.example.json)。默认从当前目录读取配置和 `.env`；启动脚本会切换到项目根目录。相对 `data_dir` 以配置文件所在目录为基准。

从其他目录使用时，可用 `ANKI_WORD_CONFIG` 指定配置绝对路径；`.env` 默认放在配置旁。也可使用全局参数 `--config`、`--env-file`，它们须放在 `add`、`gui` 等子命令之前。

- **Anki 保护**：优先复用字段和模板兼容的 `vocabsieve-notes`，否则确认后创建独立的 `AI Vocabulary` 类型；已有模板不被改写。
- **重复检测**：检查整个集合，默认跳过；更新仅覆盖预览中列出的映射字段。自定义笔记类型和词形变化可能影响查重。
- **缓存**：按单词、领域和完整原句区分，保存在 `data/vocabulary.sqlite3`。命中缓存无需再次调用 API。
- **费用**：窗口显示本工具累计费用的估算区间，终端通过 `anki-word usage` 查看 token。费率快照见 [pricing.py](src/anki_ai_vocab/pricing.py)，来源为 [DeepSeek 官方价格](https://api-docs.deepseek.com/zh-cn/quick_start/pricing/)；实际扣费以平台账单为准，超时后未收到的 usage 可能无法计入。
- **隐私**：单词和原句会发送到 DeepSeek，并保留在本地缓存。提交 Git 前检查密钥、`.env`、`data/`、`.venv/` 未被纳入提交；仅分享空白密钥模板 `.env.example`。

## 手机同步

1. 在 Ubuntu Anki 点击“同步”，登录 AnkiWeb 账号，可在首选项中启用打开/关闭集合时自动同步。
2. AnkiDroid 登录同一账号。
3. 电脑收词后，先在电脑同步，再在手机同步；手机复习结束后再同步一次。

首次或完整同步需要核对上传/下载方向，已有数据先备份。**AnkiConnect 负责本机写入，云同步由 Anki 与 AnkiWeb 完成。** 详见 [Anki 同步手册](https://docs.ankiweb.net/manual/syncing)和 [AnkiDroid 手册](https://docs.ankidroid.org/#_via_cloud_sync)。

## 常见问题

| 问题 | 处理方式 |
| --- | --- |
| 找不到 `anki-word` | 激活 `.venv`，或使用 `.venv/bin/anki-word` |
| 找不到 API Key | 检查当前目录、配置路径以及 `.env` 中的 `DEEPSEEK_API_KEY` |
| 无法连接 Anki | 打开正确资料，确认插件已启用、牌组存在，运行 `anki-word doctor` |
| 401 / 402 / 429 / 超时 | 分别检查密钥、余额、限流及网络；按提示手动重试 |
| 模型名或 JSON 错误 | 核对 [DeepSeek 官方文档](https://api-docs.deepseek.com/)；被截断时适当增加 `max_tokens` |
| 剪贴板读不到 | 先按 Ctrl+C，安装对应 X11/Wayland 工具，在当前图形会话运行 |
| 桌面窗口打不开 | 安装 `python3-tk`，在本机图形桌面运行启动脚本检查错误 |
| 更新或写入结果不确定 | 先退出该笔记的编辑界面；写入超时后先在 Anki 中检查，避免重复操作 |

## 开发

```bash
python -m pip install -e '.[dev]'
python -m pytest -q
python -m ruff check src tests scripts/install_desktop.py
python -m ruff format --check src tests scripts/install_desktop.py
```

测试使用 Mock，不需要 API Key，不访问真实 Anki，也不产生 API 费用。图形交互测试需要桌面或 Xvfb，无显示环境时会跳过。

| 目录 / 模块 | 职责 |
| --- | --- |
| `src/anki_ai_vocab/cli.py`、`gui.py` | 终端与桌面入口 |
| `service.py`、`gui_workflow.py` | 查重、生成和确认保存流程 |
| `deepseek_client.py`、`anki_client.py` | API 通信与错误处理 |
| `cache.py`、`pricing.py`、`window_state.py` | 缓存、费用估算和窗口偏好 |
| `scripts/` | 启动脚本与桌面图标安装器 |
| `tests/` | 单元测试及交互流程测试 |

## 开源基础与致谢

本项目是独立的 Python 应用，基于以下开源组件构建，并通过接口接入 Anki 生态：

| 开源项目 | 在本项目中的作用 |
| --- | --- |
| [Anki](https://github.com/ankitects/anki) | 桌面卡片管理与间隔复习平台，通过 AnkiConnect 对接 |
| [AnkiConnect](https://github.com/FooSoft/anki-connect) | 提供本机查询、查重与笔记写入 API；上游已迁移至 [SourceHut](https://git.sr.ht/~foosoft/anki-connect) |
| [OpenAI Python SDK](https://github.com/openai/openai-python) | 通过兼容接口调用 DeepSeek 官方 API |
| [HTTPX](https://github.com/encode/httpx) | AnkiConnect HTTP 通信及 SDK 网络传输 |
| [python-dotenv](https://github.com/theskumar/python-dotenv) | 从 `.env` 加载本地配置 |
| [Python / Tkinter](https://docs.python.org/3/library/tkinter.html) 与 [Tcl/Tk](https://www.tcl-lang.org/) | 桌面界面、事件循环与窗口管理 |
| [SQLite](https://www.sqlite.org/) | 通过 Python 标准库保存词汇缓存和 token 账本 |

开发工具使用 [pytest](https://github.com/pytest-dev/pytest) 和 [Ruff](https://github.com/astral-sh/ruff)。手机复习端为 [AnkiDroid](https://github.com/ankidroid/Anki-Android)。

[VocabSieve](https://github.com/FreeLanguageTools/vocabsieve) 是可选的笔记类型兼容对象，无需安装即可使用本工具。本项目未基于其代码仓库派生。释义生成使用 DeepSeek 的托管 API 服务。

第三方组件的许可证见各上游项目。本仓库当前尚未提供 `LICENSE`，项目源码的授权方式需由维护者另行确定。
