# Ubuntu AI 英语收词工具

面向 SLAM、计算机视觉、机器人、编程、数学与控制理论的轻量 Python 桌面与终端工具：

```text
手动输入 / Ctrl+C 复制
    → Anki 查重
    → 本地缓存 / DeepSeek 专业释义
    → 预览、修改、确认
    → AnkiConnect 写入 Ubuntu Anki
    → Anki 原生同步 → AnkiWeb → Android AnkiDroid
```

支持 Python 3.10+，以 Ubuntu 22.04 GNOME 为目标环境。不需要本地模型、Ollama、Android 开发或后台键盘监听器。

## 1. 已实现的功能

- 单词和技术术语收集，自定义领域，简短中文释义、词性、例句、翻译和标签。
- X11 的 xclip/xsel 与 Wayland 的 wl-paste 自动选择和失败回退。
- 整句复制后交互选词，保留完整原句；原句发生变化时不会误用旧例句翻译。
- 使用官方 DeepSeek API 与 OpenAI Python SDK，默认 `deepseek-flash`、JSON 输出、关闭思考、不调用搜索工具。
- SQLite 缓存、强制重新生成、累计 token 账本。
- 小窗口底部显示累计人民币 API 费用估算，自动计入历史用量并在生成后刷新。
- 整个 Anki 集合中的重复词检查，默认跳过；可更新兼容笔记或按不同领域新增。
- 桌面小窗口可输入单词、选择领域、编辑预览、确认保存；生成与保存期间保持界面响应。
- 所有 Anki 写入都需要最终确认；桌面确认框默认取消，终端默认回车取消。
- 优先检查 `vocabsieve-notes`，无法兼容时创建独立 `AI Vocabulary`，不改动已有笔记类型。
- GNOME 快捷键启动脚本，以及不产生真实 API 费用的 Mock 测试。

## 2. 安装与 Python 环境

下面命令在项目目录运行。当前项目路径为：

```bash
cd /home/gys/GitProject/anki-ai-vocab
```

本次开发已在 `.venv` 安装 Python 依赖；直接使用现有环境：

```bash
source .venv/bin/activate
anki-word --help
python -m pytest -q
```

在一台新的 Ubuntu 22.04 机器上安装时，先准备系统依赖。以下 `sudo` 命令由你决定并在本机执行：

```bash
sudo apt update
sudo apt install python3 python3-venv python3-pip python3-tk gnome-terminal
```

检查桌面会话：

```bash
echo "$XDG_SESSION_TYPE"
```

X11 安装一个剪贴板工具即可：

```bash
sudo apt install xclip
```

也可用 `sudo apt install xsel`。Wayland 建议安装原生工具：

```bash
sudo apt install wl-clipboard
```

若经常切换会话，可同时安装 xclip 和 wl-clipboard。程序在 Wayland 优先使用 wl-paste，在 X11 优先使用 xclip、其次 xsel；失败时继续尝试其他已安装后端。

新环境的 Python 安装步骤：

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip setuptools wheel
python -m pip install -e '.[dev]'
python -m pip check
anki-word --version
```

只使用工具而不开发时，可将安装命令替换为 `python -m pip install -e .`。不要使用 `sudo pip`；依赖保存在项目虚拟环境，不影响 ROS2、VocabSieve 或系统 Python。zsh 中 `'.[dev]'` 必须加引号。

## 3. 配置 DeepSeek API Key

在 [DeepSeek 开放平台](https://platform.deepseek.com/) 自行创建 API Key 并检查余额。程序不会代你登录或充值。

```bash
cp -n .env.example .env
chmod 600 .env
nano .env
```

把 `.env` 中 `DEEPSEEK_API_KEY=` 右侧填为你的真实密钥，然后保存。不要把密钥发到聊天、截图或代码仓库。

也可使用进程环境变量 `DEEPSEEK_API_KEY`。环境变量优先于 `.env`，程序不会覆盖已有环境变量。

`.env` 已被 `.gitignore` 忽略，`.env.example` 只包含变量名称。API Key 不进入缓存、配置 JSON 或 token 账本。

## 4. 配置文件与路径

不创建 `config.json` 也能使用默认值。需要调整时：

```bash
cp -n config.example.json config.json
nano config.json
```

| 配置 | 默认值 | 用途 |
| --- | --- | --- |
| `model` | `deepseek-flash` | 官方可用模型名称 |
| `deepseek_base_url` | `https://api.deepseek.com` | 仅接受官方 HTTPS 地址，也允许 `/v1` |
| `api_timeout` | `30` | SDK 网络操作超时，秒 |
| `max_tokens` | `1000` | 单次输出 token 上限，允许 128–4096 |
| `anki_url` | `http://127.0.0.1:8765` | 仅允许本机 AnkiConnect 地址 |
| `anki_timeout` | `10` | 本机 Anki 请求超时，秒 |
| `deck` | `专业学习` | 已有的目标牌组 |
| `preferred_model` | `vocabsieve-notes` | 优先检查的笔记类型 |
| `default_topic` | `General` | 不传 `--topic` 时的领域 |
| `topics` | 8 个预设领域 | `topics` 命令展示的列表 |
| `data_dir` | `data` | SQLite 缓存和 token 账本目录 |

`topics` 是便捷列表，不限制 `--topic`，例如 `--topic ROS2` 可直接使用。

默认从**当前工作目录**读取 `config.json` 和 `.env`，相对 `data_dir` 以配置文件所在目录为基准。这使项目内运行和快捷键运行使用相同数据。

从其他目录使用时，明确传入配置，且全局参数放在子命令之前：

```bash
/home/gys/GitProject/anki-ai-vocab/.venv/bin/anki-word \
  --config /home/gys/GitProject/anki-ai-vocab/config.json \
  add covariance --topic "Control Theory"
```

也可设置 `ANKI_WORD_CONFIG` 为配置绝对路径；指定路径必须存在。`.env` 默认位于该配置文件旁。特殊情况可用全局 `--env-file /绝对路径/.env` 或 `ANKI_WORD_ENV_FILE` 指定。显式参数优先于对应路径环境变量。

## 5. AnkiConnect 设置与 VocabSieve 共存

1. 打开 Ubuntu Anki，选择你平常使用的用户资料，确保牌组 `专业学习` 存在。
2. 在“工具 → 插件”确认 AnkiConnect 已安装并启用；如刚安装，重启 Anki。官方插件编号为 `2055492159`，见 [AnkiConnect 插件页面](https://ankiweb.net/shared/info/2055492159)。已有插件无需重装。
3. 保留本机监听地址 `127.0.0.1`、端口 `8765`。终端程序无需将 `webCorsOriginList` 改成 `*`，也不需要修改 VocabSieve 设置。
4. 若你的 AnkiConnect 配置了 `apiKey`，在 `.env` 填入对应的 `ANKICONNECT_API_KEY`。它与 DeepSeek Key 是两把不同的密钥。
5. 运行只读检查：

```bash
anki-word doctor
```

`doctor` 检查密钥是否配置、剪贴板程序、AnkiConnect API 版本、目标牌组、现有笔记类型和字段；不会调用 DeepSeek，也不会创建或更新任何 Anki 数据。它不会验证密钥是否有效。

程序仅在 `vocabsieve-notes` 包含可映射的单词、释义、例句、翻译字段，且单张卡片模板为“单词正面、完整答案背面”时复用它。常见别名包括 `Word/Expression/Term`、`Meaning/Definition`、`Example/Sentence`、`ExampleTranslation/Translation`。词性、领域若没有单独的可显示字段，将合并到释义中；音频、图片等其他字段不参与映射。

无法兼容时，预览会说明将创建 `AI Vocabulary`。**只有输入最终保存确认后才创建**，从不改写原模板。如已有同名但不兼容类型，则使用 `AI Vocabulary 2` 等独立名称。

独立类型包含 `Word、Meaning、Example、ExampleTranslation、PartOfSpeech、Topic、SourceSentence`。正面仅显示单词；背面显示简短释义、词性、领域、例句和翻译，支持手机宽度和夜间模式。标签保存在 Anki 原生标签中。

旧缓存中的专业解释会在读取时忽略，仍可复用原来的释义与例句，无需重新调用 API。若已有 Anki 模板仍展示专业解释，新增时会选择独立的新类型（例如 `AI Vocabulary 2`），不会留下空标题或改写现有模板；已有卡片的显示保持原样。

2026-11-11 本机只读检查已确认 AnkiConnect 和 `专业学习` 可用；实际 `vocabsieve-notes` 字段为 `Sentence、Word、Definition、Definition#2、Image、Pronunciation`，因此会选择独立类型。目前尚未创建该类型。

## 6. 手动输入与专业领域

### 桌面小窗口（推荐）

先打开 Anki，再启动窗口：

```bash
/bin/bash /home/gys/GitProject/anki-ai-vocab/scripts/launch_gui.sh
```

已激活虚拟环境时，也可以执行 `anki-word gui`。

使用流程：输入单词 → 选择或手动填写领域 → 点击“生成预览” → 直接修改释义、词性、例句、翻译或标签 → 点击“保存到 Anki”并确认。`Ctrl+Enter` 可生成预览。“清空 / 下一个”用于继续收词，不会写入 Anki。

窗口默认放大为 1000×820 像素，较小屏幕会自动缩小到可用范围。拖动窗口边缘调整到合适大小后，可勾选右上角“固定窗口大小”防止误拖；取消勾选即可继续调整。正常关闭后会记住尺寸和固定状态，下次打开自动恢复。最大化或最小化不会覆盖此前的正常尺寸。偏好保存在已忽略的 `data/window_state.json`，不影响词汇和费用记录。

关闭快捷键可以自行在 Ubuntu“设置 → 键盘 → 查看及自定义快捷键 → 窗口 → 关闭窗口”中修改，默认是 `Alt+F4`。这是系统现成的动作，不用创建带 Command 的自定义入口；作用于当前有焦点的窗口。保存到 Anki 期间，程序会要求等待写入结果后再关闭。设置步骤参见 [GNOME 官方说明](https://help.gnome.org/gnome-help/keyboard-shortcuts-set.html)。

可选原句会作为语境使用。已有单词会先弹出重复词选择窗口，默认跳过；可选择更新兼容笔记，或在领域不同时新增。没有选择继续前不会调用 AI。“重新生成”会先提示可能产生费用，生成失败后保留当前预览。

窗口复用项目 `.env`、配置、缓存、token 统计和牌组设置，不需要重新填写密钥。Tkinter 本机已可用；新机器若提示缺少模块，请安装上方列出的 `python3-tk`。Wayland 桌面上的 Tk 窗口通常由 XWayland 显示。

一次性安装桌面与应用菜单图标（此命令会在当前用户的应用目录和桌面创建启动文件，不需要 sudo）：

```bash
cd /home/gys/GitProject/anki-ai-vocab
.venv/bin/python scripts/install_desktop.py
```

安装后，从应用菜单搜索“AI 英语收词”或点击桌面图标。桌面若提示不受信任，请右键选择“允许启动”。也可右键应用菜单中的图标，选择添加到收藏夹。以后收词无需打开终端。

图标默认位于 `$XDG_DATA_HOME/applications/anki-ai-vocab.desktop`（未设置时使用 `~/.local/share/applications/`）和 `xdg-user-dir DESKTOP` 返回的桌面目录。仅安装应用菜单时使用 `--menu-only`。安装器不会覆盖内容不同的同名文件；项目移动后，需核对并重新配置入口路径。

### 终端输入

```bash
anki-word add degeneracy --topic SLAM
anki-word add covariance --topic "Control Theory"
anki-word add "Kalman filter" --topic Robotics
anki-word add iterator --topic "C++"
anki-word add observability --topic ROS2
anki-word topics
```

领域影响词义选择和例句。释义保持简短，不展开背景或原理；若没有公认的专业含义，使用通常词义。AI 结果仍应由你在预览时核对。

视频、论文原句也可以手动提供：

```bash
anki-word add degeneracy --topic SLAM \
  --context "Geometric degeneracy may cause localization drift."
```

有原句时，模型必须原样使用原句作为例句，并生成对应翻译；若模型改写原句，会提示重新生成，避免静默配错翻译。

想先体验生成，不连接 Anki：

```bash
anki-word add degeneracy --topic SLAM --preview-only
```

`--preview-only` 不查 Anki 重复词、不写入 Anki；缓存未命中仍会产生 API 费用。普通收词模式要求交互式终端，不接受通过管道绕过确认。

## 7. 剪贴板收词

在 VS Code、Firefox、PDF 阅读器中选中英文，按 `Ctrl+C`：

```bash
anki-word clipboard --topic SLAM
```

复制单词时直接处理。复制整句时显示原文与单词编号，可输入编号或原句中的目标词，回车取消。支持 `C++`、`C#`、下划线标识符与连字符词。长段落建议先缩小到一句，剪贴板文本最多 8000 字符。

已知目标词时可省略选择步骤：

```bash
anki-word clipboard --topic SLAM --word degeneracy
```

选择后保留完整原句，包括内部换行；词汇含义按该语境生成。剪贴板使用系统的 **CLIPBOARD**，不是鼠标选区 PRIMARY，必须先 `Ctrl+C`。纯图片剪贴板不支持。

## 8. 重复词、缓存、预览和编辑

默认先检查 Anki，再考虑请求 DeepSeek：

- **跳过 `s` / 回车**：默认行为，不调用 DeepSeek、不写入 Anki。
- **更新 `u`**：选择一个领域一致或领域未知、字段和模板兼容的笔记；最终预览显示编号与将覆盖字段的原内容。只更新映射字段、追加标签，保留复习进度、牌组、音频、图片和其他字段。若该笔记正在 Anki 浏览器中编辑，请先切换到其他笔记或关闭浏览器，再运行更新。
- **不同领域新增 `n`**：已有相同领域时拒绝新增；领域未知时须由你核对确实为不同领域。该选项不会修改已有笔记。不兼容的旧笔记可在 Anki 中手工维护。

查重不区分大小写，比较去除 HTML 后的完整词字段，并覆盖整个集合，不只目标牌组。对常见词字段使用别名映射，未知类型以第一字段作为候选；任意自定义类型若将单词藏在其他字段，可能无法识别。不会自动进行词形还原，因此 `drift` 和 `drifting` 视为不同词。

最终预览菜单：

| 输入 | 行为 |
| --- | --- |
| `s` | 确认写入 Anki |
| `c` / 回车 | 取消，保留生成缓存 |
| `r` | 明确请求重新生成，可能再次付费 |
| `e` | 按编号修改释义、例句、翻译、词性或标签，再次预览 |

单词与领域作为身份不在编辑菜单中修改；需改变时重新运行命令。标签使用英文逗号分隔，空格等字符会规范为下划线。编辑例句时请同时核对翻译。编辑结果在确认保存时更新缓存；取消时未确认的编辑不覆盖缓存。

缓存路径默认 `data/vocabulary.sqlite3`，键为规范化单词、领域和完整原句。相同查询优先用缓存，即使未配置 API Key 也能命中缓存。不同原句会独立生成，以免专业含义或翻译串用。

强制刷新：

```bash
anki-word add degeneracy --topic SLAM --force
```

`--force` 仅绕过缓存，不跳过查重或保存确认。若先选择跳过重复词，不会生成。

写入前再次查重和检查更新目标的内容变化。网络写入超时后的结果可能已经落到 Anki，请先在 Anki 浏览器中查找单词，再重试。AnkiConnect 的多个写入操作不构成事务；如果创建类型后新增失败，独立类型可能留下，重试会复用；若字段更新成功但标签失败，会明确报告部分成功。

## 9. Ubuntu GNOME 全局快捷键

先在图形桌面的终端验证启动脚本：

```bash
/bin/bash /home/gys/GitProject/anki-ai-vocab/scripts/launch_clipboard.sh --topic SLAM
```

脚本根据自身位置定位项目，切换工作目录，使用绝对路径 `.venv/bin/python`，打开可交互终端，自动从项目配置旁加载 `.env`；完成或出错后按回车关闭窗口。GNOME 优先使用 gnome-terminal，也支持 x-terminal-emulator 回退。不依赖 `.zshrc` 中的别名、`source` 或终端 PATH 激活状态。

配置步骤：

1. 打开“设置 → 键盘 → 查看及自定义快捷键 → 自定义快捷键”。Ubuntu 不同语言下名称略有差异。
2. 点击 `+`，名称填 `AI 英语收词`。
3. 命令粘贴以下整行，不要把 API Key 放进命令：

```text
/bin/bash /home/gys/GitProject/anki-ai-vocab/scripts/launch_clipboard.sh --topic SLAM
```

4. 选择快捷键，建议先试 `Ctrl+Alt+W`。
5. 回到阅读软件，选词 → `Ctrl+C` → 按快捷键 → 在终端预览并确认。

如果 GNOME 提示冲突，或者已被 VocabSieve、剪贴板管理器、桌面扩展占用，保留原设置，从下面选一个空闲组合：

| 候选 | 适用建议 |
| --- | --- |
| `Ctrl+Alt+W` | 首选候选，W 对应 word |
| `Ctrl+Alt+E` | 备选，E 对应 English |
| `Super+Shift+W` | 使用 Super 的备选 |

这些只是候选，无法保证你的个性化环境中空闲。配置前同时检查 GNOME 自定义快捷键和 VocabSieve 的热键。不要选 `Ctrl+C`、`Ctrl+Alt+T`、`Super+L` 等已有常用组合。本次没有改动任何系统快捷键，也没有替你选择或覆盖冲突绑定。

想默认使用别的领域，可改快捷键命令的 `--topic`；或移除此参数，使用配置中的 `default_topic`。

桌面快捷键通常不会读取 `.zshrc` 导出的环境变量，推荐用项目 `.env`。若设置了 `ANKI_WORD_CONFIG`，请确保桌面会话中的路径也有效。SSH、无显示服务的容器或后台服务无法弹出桌面终端，应在本机已登录的 GNOME 会话使用。

## 10. AnkiWeb 与 Android AnkiDroid 同步

**AnkiConnect 仅负责本机读写，不负责云同步。本工具不会登录 AnkiWeb，也不会自动调用同步接口。**

1. 在 [AnkiWeb](https://ankiweb.net/) 注册或使用已有账号。
2. Ubuntu Anki 主界面点右上角“同步”（或按 `Y`），按提示登录你的 AnkiWeb 账号。可在“工具 → 首选项 → 同步/网络”检查自动同步选项；启用后，Anki 在打开或关闭集合时自动同步。
3. 如果本机已有全部卡片，而 AnkiWeb 为空，首次同步选择“上传到 AnkiWeb”。若两边都有不同数据，先各自导出备份并参考官方合并说明，不能随意选择覆盖方向。
4. Android 打开 AnkiDroid，在牌组列表点同步按钮，登录**同一个 AnkiWeb 账号**。新手机为空时，从已有 AnkiWeb 集合下载。若手机已有要保留的卡片，先处理合并，不要直接覆盖。
5. Ubuntu 收词后希望立即到手机复习：先在 Ubuntu Anki 点同步，再在 AnkiDroid 点同步。电脑 Anki 一直开着时，不应只等退出时自动同步。
6. 手机开始复习前同步一次，结束后再同步一次；切换设备前确保上一台的修改已上传。

创建新笔记类型后，Anki 有时需要完整单向同步。若电脑是包含新卡片与模板的完整版本，按提示上传，再让手机从 AnkiWeb 下载；选择前核对两端内容与备份。具体以界面提示为准，避免把有新内容的一端覆盖。

同步细节参见 [Anki 官方同步手册](https://docs.ankiweb.net/manual/syncing) 和 [AnkiDroid 云同步手册](https://docs.ankidroid.org/#_via_cloud_sync)。

## 11. Token 统计、成本与隐私

```bash
anki-word usage
```

按模型展示已收到 usage 的响应次数、输入 token、输出 token、缓存命中输入 token、总 token 与累计总量。即使生成结果 JSON 错误或被截断，收到的 usage 也会记录。

小窗口底部还会显示例如“累计 API 花费（估算）：¥0.001600～¥0.003200 · 2 次请求”。打开窗口时会读取已有账本，每次操作完成后自动刷新；清空输入、取消保存或重开窗口不会清零。读取统计只访问本地数据库，不调用 API；命中本地词汇缓存不会新增费用。

费用区间下限按官方空闲时段价、上限按高峰时段价计算，分别计入缓存命中输入、未命中输入和输出 token。暂不推断节假日、促销、账户赠送额度或跨计费时段请求，因此显示估算而非实际扣款。仅统计本工具收到 usage 的调用，不含其他程序消耗；未知模型会明确提示未计价，不会按零费用混入完整统计。

- 默认输出上限 1000 token，提示词约束解释长度；JSON 模式仍可能返回空内容或截断结果，程序会报告错误，不会把它写入 Anki。
- SDK 自动重试关闭，429、网络错误、认证失败、余额不足均给出提示。你手动选择重新生成或再次运行时，可能产生新的费用。
- 超时或断网可能导致服务端已经完成请求，但本地未收到 usage，因此本地累计量不是账单；以 DeepSeek 控制台为准。
- 内置费率快照核对日期为 2026-11-11：每百万 token，Flash 空闲时段缓存命中输入 ¥0.02、未命中输入 ¥1、输出 ¥4；Pro 分别为 ¥0.15、¥4.5、¥13.5，高峰价格均为两倍。以 [DeepSeek 官方人民币价格](https://api-docs.deepseek.com/zh-cn/quick_start/pricing/) 为准；价格变动时需更新 `pricing.py`。历史记录也按这份快照估算，不是保存的历史账单。
- 单词、领域和原句会发送到 DeepSeek。不要复制包含密钥、个人信息或未授权资料的内容。SQLite 也保留学习原句，不适合存放敏感文本。
- `.env`、`config.json`、`data/`、`.venv/` 已加入忽略列表；提交前仍应检查差异和历史。密钥泄露后需在平台撤销并换新。
- AnkiConnect 维持仅本机监听，不要将端口暴露到公网；若配置了插件 API Key，请一并保护。
- HTML 展示字段在写入前转义，模型不能注入脚本到卡片。原有笔记模板由 Anki 管理，工具不会重写它们。

接口依据：[DeepSeek 首次调用](https://api-docs.deepseek.com/)、[Chat Completions 参数](https://api-docs.deepseek.com/api/create-chat-completion/)、[JSON 模式](https://api-docs.deepseek.com/guides/json_mode/)。AnkiConnect 请求依据其[官方插件源码](https://github.com/FooSoft/anki-connect/blob/master/plugin/__init__.py)，项目已迁移至 [SourceHut](https://git.sr.ht/~foosoft/anki-connect)。

## 12. 常见问题

| 问题 | 排查方式 |
| --- | --- |
| `anki-word: command not found` | `source .venv/bin/activate`，或使用 `.venv/bin/anki-word` 绝对路径 |
| 小窗口提示缺少 Tkinter | 安装 Ubuntu 的 `python3-tk`，使用项目 `.venv` 启动 |
| 小窗口无法显示 | 从已登录的图形桌面启动，检查 DISPLAY/XWayland；SSH 或无显示服务的容器中无法直接显示 |
| 桌面图标无法启动 | 先核对项目路径与 .venv，再右键“允许启动”；可在终端执行 `launch_gui.sh` 查看启动错误 |
| 安装后包名变成 UNKNOWN / 找不到入口 | 旧版 setuptools 不支持项目元数据；先升级虚拟环境内 pip、setuptools、wheel，再重新 `pip install -e '.[dev]'` |
| 未设置 `DEEPSEEK_API_KEY` | 检查 `.env` 是否位于所用配置旁；确认从项目目录运行，或显式指定配置路径 |
| 认证失败 / 余额不足 | 检查 DeepSeek 平台密钥及余额，不要把完整错误请求或密钥贴到公开位置 |
| HTTP 400 / 模型不可用 | 核对当前官方模型名和参数，修改配置 `model`；不会自动切换到其他付费模型 |
| 429 或请求超时 | 稍后重试，检查网络和代理；可合理调整 `api_timeout`，不进行无限重试 |
| JSON 不合法、空响应或被截断 | 手动重试；多次截断可适当增加 `max_tokens`，同时留意费用 |
| 无法连接 AnkiConnect | 打开 Anki 并保持正确资料已加载，确认插件已启用、端口未占用；再执行 `doctor` |
| AnkiConnect 操作失败 | 检查 `ANKICONNECT_API_KEY`、插件版本、当前 Anki 对话框状态，确认牌组与字段没有同时被其他程序改动 |
| 牌组不存在 | 在 Anki 中手动创建 `专业学习` 或修改配置中的 `deck`，程序不会擅自创建或改名牌组 |
| 未复用 vocabsieve-notes | 字段或卡片展示方式不兼容是正常情况；确认后使用独立类型，不影响 VocabSieve |
| 更新后看不到变化 | 先切换/关闭正在编辑该笔记的 Anki 浏览器，再重新读取，避免编辑窗口覆盖外部更新 |
| 剪贴板无内容 | 先 `Ctrl+C`；检查 `XDG_SESSION_TYPE`，安装对应工具；从当前图形会话运行 |
| Wayland 下 xclip 读不到 | 安装 wl-clipboard，程序会优先使用 wl-paste |
| 快捷键窗口不出现 | 先在终端执行同一启动脚本，核对绝对路径、.venv、gnome-terminal、当前桌面会话及热键冲突 |
| 桌面启动找不到 Key | 不依赖 .zshrc，改用项目 .env，或明确配置桌面会话环境 |
| 手机没有新卡片 | 先电脑 Anki 同步，再 AnkiDroid 同步；AnkiConnect 不会上云 |
| SQLite 无法打开或锁定 | 检查 data_dir 权限与磁盘空间；避免同时修改数据库或放在不可靠的网络盘 |

退出码：`0` 为完成、跳过或正常取消；`1` 为配置/网络/内容/存储错误；`2` 为命令参数错误；`130` 为 Ctrl+C 或输入流中断。

## 13. 测试与维护

```bash
source .venv/bin/activate
python -m pytest -q
python -m ruff check src tests scripts/install_desktop.py
python -m ruff format --check src tests scripts/install_desktop.py
bash -n scripts/launch_clipboard.sh
bash -n scripts/launch_gui.sh
```

所有单元与流程测试使用 Mock，不访问真实 DeepSeek 或真实 Anki，不需要 API Key，也不产生费用。覆盖 JSON/缺失字段、SDK JSON 请求、超时/429/401/402/500、token 记账、缓存持久化与语境隔离、剪贴板后端回退和选词、Anki 查重/HTML 转义/模型选择/更新字段、确认前零写入、编辑取消、不同领域新增与并发内容变化。

桌面流程另测确认门槛、缓存复用、后台生成、编辑后保存、切换输入后禁止误存、错误恢复、启动路径与图标安装，以及人民币费用计算、历史账本读取、生成成功/失败后刷新、清空后保留累计值、窗口尺寸记忆、固定与解除固定、关闭后恢复和小屏幕适配。窗口交互测试需要显示环境；无显示环境时会跳过，也可以在本机安装 Xvfb 后使用 `xvfb-run -a .venv/bin/python -m pytest -q`。本次已在临时虚拟显示中实际运行，165 项测试全部通过，并检查窗口截图；没有安装或修改系统文件。

桌面实现参考 [Python Tkinter 线程模型](https://docs.python.org/3/library/tkinter.html#threading-model) 和 [freedesktop.org 桌面入口规范](https://specifications.freedesktop.org/desktop-entry/latest/exec-variables.html)。

真实验证顺序：

1. `anki-word doctor`，只读确认 AnkiConnect 与字段。
2. 你配置 API Key 后，`anki-word add degeneracy --topic SLAM --preview-only`，验证真实生成和 token 使用量。
3. 打开 Anki，运行普通 `add`，检查预览，输入 `s`，在 Anki 浏览器确认卡片。
4. 在 X11/Wayland 桌面分别验证复制、整句选词、快捷键弹窗。
5. 手动验证 Anki → AnkiWeb → AnkiDroid 同步，以及手机卡片排版。

截至本次开发验证：Python 依赖已安装，Mock 测试和静态检查通过，本机 AnkiConnect/牌组/字段只读检查通过；没有真实 DeepSeek 调用，没有向真实 Anki 写入数据。图形剪贴板、快捷键、手机渲染与云同步需要在你的桌面和手机上实际操作验证。

## 14. 项目结构

```text
anki-ai-vocab/
├── README.md
├── pyproject.toml
├── .env.example
├── .gitignore
├── config.example.json
├── src/anki_ai_vocab/
│   ├── __init__.py
│   ├── __main__.py
│   ├── cli.py                # 命令、预览、编辑、最终确认
│   ├── gui.py                # Tkinter 桌面窗口与后台任务
│   ├── window_state.py       # 窗口尺寸与固定状态的保存和恢复
│   ├── gui_workflow.py       # 窗口使用的查重、生成与确认保存流程
│   ├── desktop.py            # 用户级桌面启动文件
│   ├── config.py             # JSON 配置和环境变量
│   ├── vocabulary.py         # 内容校验与词汇身份
│   ├── deepseek_client.py    # 官方 API、错误处理、token 统计
│   ├── cache.py              # SQLite 缓存与使用账本
│   ├── pricing.py            # 人民币费用区间与费率快照
│   ├── service.py            # 缓存优先的生成流程
│   ├── anki_client.py        # AnkiConnect、字段映射和查重
│   ├── clipboard.py          # 多后端读取、原句选词
│   └── errors.py             # 可向用户展示的错误
├── scripts/
│   ├── launch_clipboard.sh
│   ├── launch_gui.sh
│   ├── install_desktop.py
│   └── anki-ai-vocab.desktop
└── tests/
    ├── conftest.py
    ├── test_vocabulary.py
    ├── test_config.py
    ├── test_deepseek.py
    ├── test_cache.py
    ├── test_pricing.py
    ├── test_service.py
    ├── test_anki.py
    ├── test_clipboard.py
    ├── test_cli.py
    ├── test_gui.py
    ├── test_window_state.py
    ├── test_gui_workflow.py
    ├── test_desktop.py
    └── test_launcher.py
```

运行产生的 `.venv/`、`data/`、缓存、安装元数据不属于源码。当前提供的 `.git` 目录为空，尚不是有效 Git 仓库；本次没有创建 Git 提交。
