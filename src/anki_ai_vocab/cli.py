"""Interactive CLI. Every Anki mutation follows an explicit final confirmation."""

import argparse
import json
import logging
import sqlite3
import sys
from pathlib import Path

from . import __version__
from .anki_client import AnkiClient, ExistingNote, ModelPlan, note_fields, plain_text
from .cache import Cache
from .clipboard import clipboard_commands, process_text, read_clipboard, select_word
from .config import Settings, load_settings
from .errors import ValidationError, VocabError
from .service import VocabularyService
from .vocabulary import Vocabulary, validate_topic, validate_word

LABELS = {
    "word": "单词",
    "topic": "领域",
    "meaning": "中文释义",
    "example": "英文例句",
    "example_translation": "例句翻译",
    "part_of_speech": "词性",
    "tags": "标签",
}
EDITABLE = (
    "meaning",
    "example",
    "example_translation",
    "part_of_speech",
    "tags",
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="DeepSeek 专业英语收词 → Anki")
    parser.add_argument("--version", action="version", version=__version__)
    parser.add_argument("--config", type=Path, help="JSON 配置文件路径")
    parser.add_argument("--env-file", type=Path, help="本地 .env 文件路径")
    sub = parser.add_subparsers(dest="command", required=True)
    for name, help_text in (("add", "手动输入"), ("clipboard", "读取系统剪贴板")):
        command = sub.add_parser(name, help=help_text)
        if name == "add":
            command.add_argument("word")
            command.add_argument("--context", default="", help="可选的完整英文原句")
        else:
            command.add_argument("--word", help="指定原句中的目标词，跳过编号选择")
        command.add_argument("--topic", help="专业领域；允许自定义")
        command.add_argument("--force", action="store_true", help="绕过缓存重新生成")
        command.add_argument(
            "--preview-only",
            action="store_true",
            help="仅生成预览，不连接或写入 Anki",
        )
    sub.add_parser("topics", help="列出预设领域")
    sub.add_parser("usage", help="查看本地累计 token 使用量")
    sub.add_parser("doctor", help="只读检测配置、剪贴板工具和 AnkiConnect")
    sub.add_parser("gui", help="打开桌面收词小窗口")
    return parser


def preview(entry: Vocabulary) -> None:
    print("\n" + "─" * 48)
    for key, label in LABELS.items():
        value = getattr(entry, key)
        print(f"{label}：{', '.join(value) if key == 'tags' else value}")
    if entry.source_sentence:
        print(f"原始语境：{entry.source_sentence}")
    print("─" * 48)


def edit_entry(entry: Vocabulary) -> Vocabulary:
    for index, key in enumerate(EDITABLE, 1):
        print(f"{index}. {LABELS[key]}")
    answer = input("选择要修改的字段编号（回车返回）：").strip()
    if not answer:
        return entry
    if not answer.isdigit() or not 1 <= int(answer) <= len(EDITABLE):
        print("无效编号。")
        return entry
    key = EDITABLE[int(answer) - 1]
    print("当前值：", getattr(entry, key))
    value = input("新值（单行；标签用英文逗号分隔；回车保留）：").strip()
    if not value:
        return entry
    data = entry.to_dict()
    data[key] = (
        [t.strip() for t in value.split(",") if t.strip()] if key == "tags" else value
    )
    try:
        return Vocabulary.from_dict(data)
    except ValidationError as exc:
        print(f"未修改：{exc}")
        return entry


def duplicate_action(
    anki: AnkiClient,
    notes: list[ExistingNote],
    topic: str,
) -> tuple[str, ExistingNote | None, ModelPlan | None]:
    print("\n该单词已存在于 Anki（检查整个集合）：")
    for note in notes:
        status = {"same": "相同领域", "other": "其他领域", "unknown": "领域未知"}
        print(
            f"  ID {note.note_id} · {note.model} · {status[note.topic_status(topic)]}"
        )
    print("领域未知时，选择新增前请确认已有笔记属于不同领域。")
    while True:
        choice = (
            input("[s] 跳过（默认） / [u] 更新 / [n] 按不同领域新增：").strip().lower()
        )
        if choice in ("", "s"):
            return "skip", None, None
        if choice == "n":
            if any(note.topic_status(topic) == "same" for note in notes):
                print("已存在相同单词、相同领域的卡片，请跳过或更新。")
                continue
            return "new", None, None
        if choice == "u":
            candidates = []
            for note in notes:
                if note.topic_status(topic) == "other":
                    continue
                plan = anki.inspect_model(note.model)
                if plan:
                    candidates.append((note, plan))
            if not candidates:
                print("没有可安全映射且领域一致的笔记。可跳过，或按不同领域新增。")
                continue
            for index, (note, _) in enumerate(candidates, 1):
                print(f"  {index}. ID {note.note_id} · {note.model}")
            answer = input("选择要更新的编号（回车返回）：").strip()
            if answer.isdigit() and 1 <= int(answer) <= len(candidates):
                note, plan = candidates[int(answer) - 1]
                return "update", note, plan
        else:
            print("请输入 s、u 或 n。")


def review_and_save(
    entry: Vocabulary,
    service: VocabularyService,
    anki: AnkiClient,
    plan: ModelPlan,
    existing: ExistingNote | None,
    allow_duplicate: bool,
) -> None:
    while True:
        preview(entry)
        if existing:
            print(f"将更新笔记 ID {existing.note_id}，保留牌组、复习进度和其他字段。")
            print("本次将覆盖以下字段，当前内容为：")
            for field in note_fields(entry, plan):
                print(f"  {field}: {plain_text(existing.fields[field]['value'])}")
        else:
            print(f"目标牌组：{anki.settings.deck}；笔记类型：{plan.name}")
            if plan.create:
                print("确认后会创建这个独立笔记类型及一张卡片。")
        choice = (
            input("[s] 确认保存 / [c] 取消（默认） / [r] 重新生成（付费） / [e] 修改：")
            .strip()
            .lower()
        )
        if choice in ("", "c"):
            print("已取消，未写入 Anki；生成内容仍保存在本地缓存。")
            return
        if choice == "e":
            entry = edit_entry(entry)
            continue
        if choice == "r":
            try:
                entry = service.get(
                    entry.word, entry.topic, entry.source_sentence, force=True
                )
            except VocabError as exc:
                print(f"重新生成失败，保留当前预览：{exc}")
            continue
        if choice != "s":
            print("请输入 s、c、r 或 e。")
            continue

        anki.check_save_target(entry, existing, allow_duplicate)
        service.cache.put(entry)
        if existing:
            anki.update(existing, entry, plan)
            note_id = existing.note_id
        else:
            note_id = anki.add(entry, plan, allow_duplicate=allow_duplicate)
        print(
            f"已保存到 Anki，笔记 ID：{note_id}。请使用 Anki 原生同步发送到 AnkiWeb。"
        )
        return


def capture(args: argparse.Namespace, settings: Settings) -> None:
    if not sys.stdin.isatty() and not args.preview_only:
        raise VocabError(
            "收词保存需要交互式终端，请使用终端或 scripts/launch_clipboard.sh。"
        )
    topic = validate_topic(args.topic or settings.default_topic)
    if args.command == "clipboard":
        data = process_text(read_clipboard())
        word, context = select_word(data, args.word)
    else:
        word, context = validate_word(args.word), args.context.strip()
        if len(context) > 8000:
            raise ValidationError("原句最多 8000 字符。")
    if args.preview_only:
        print("仅预览模式：跳过 Anki 重复检查；缓存未命中时会请求 DeepSeek。")
        with Cache(settings.data_dir / "vocabulary.sqlite3") as cache:
            preview(
                VocabularyService(settings, cache).get(word, topic, context, args.force)
            )
        return
    with AnkiClient(settings) as anki:
        models = anki.check()
        notes = anki.find_duplicates(word)
        existing, plan, action = None, None, "new"
        if notes:
            action, existing, plan = duplicate_action(anki, notes, topic)
            if action == "skip":
                print("已跳过，未调用 DeepSeek，未修改 Anki。")
                return
        plan = plan or anki.plan_model(models)
        with Cache(settings.data_dir / "vocabulary.sqlite3") as cache:
            service = VocabularyService(settings, cache)
            entry = service.get(word, topic, context, args.force)
            review_and_save(entry, service, anki, plan, existing, bool(notes))


def doctor(settings: Settings) -> int:
    import shutil

    print(f"DeepSeek 模型：{settings.model}")
    print(f"API Key：{'已配置（未发起 API 请求）' if settings.api_key else '未配置'}")
    print(f"数据目录：{settings.data_dir}")
    print("剪贴板读取顺序：", " → ".join(c[0] for c in clipboard_commands()))
    for tool in ("xclip", "xsel", "wl-paste", "gnome-terminal"):
        print(f"  {tool}: {shutil.which(tool) or '未安装'}")
    with AnkiClient(settings) as anki:
        models = anki.check()
        print(f"AnkiConnect 正常；目标牌组：{settings.deck}")
        for model in models:
            names = anki.invoke("modelFieldNames", modelName=model)
            print(f"  {model}: {', '.join(names)}")
        plan = anki.plan_model(models)
        mode = "需确认后新建" if plan.create else "复用现有模板"
        print(f"保存时使用：{plan.name}；{mode}")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    # SDK transport logs are unnecessary and could contain account metadata.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("openai").setLevel(logging.WARNING)
    try:
        settings = load_settings(args.config, args.env_file)
        if args.command == "topics":
            print("\n".join(settings.topics))
        elif args.command == "usage":
            db_path = settings.data_dir / "vocabulary.sqlite3"
            if not db_path.exists():
                print("尚无本地 API 使用记录。")
            else:
                with Cache(db_path) as cache:
                    rows = cache.usage()
                print(json.dumps(rows, ensure_ascii=False, indent=2))
                print(f"累计 token：{sum(r['total_tokens'] for r in rows)}")
                print("统计仅含本工具收到 usage 的响应；金额以 DeepSeek 控制台为准。")
        elif args.command == "doctor":
            return doctor(settings)
        elif args.command == "gui":
            try:
                from .gui import run_gui
            except ImportError as exc:
                raise VocabError(
                    "桌面窗口需要 Tkinter，请安装 Ubuntu 的 python3-tk。"
                ) from exc
            return run_gui(settings)
        else:
            capture(args, settings)
        return 0
    except (KeyboardInterrupt, EOFError):
        print(
            "\n操作已中断；如果正在写入，请在 Anki 中检查结果后再重试。",
            file=sys.stderr,
        )
        return 130
    except VocabError as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 1
    except (OSError, sqlite3.Error):
        print(
            "错误：无法访问本地文件或 SQLite 数据库，请检查路径、权限和剩余空间。",
            file=sys.stderr,
        )
        return 1
