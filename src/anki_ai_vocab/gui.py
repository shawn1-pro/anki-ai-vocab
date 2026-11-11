"""Small Tk desktop UI. Network and SQLite work stays outside the UI thread."""

import logging
import queue
import sqlite3
import threading
import tkinter as tk
from collections.abc import Callable
from tkinter import messagebox, simpledialog, ttk
from tkinter.scrolledtext import ScrolledText
from typing import Any

from .anki_client import note_fields, plain_text
from .config import Settings
from .errors import VocabError
from .gui_workflow import DesktopWorkflow, PreparedCapture, SaveTarget
from .pricing import CostEstimate, read_cost
from .vocabulary import Vocabulary
from .window_state import (
    MIN_HEIGHT,
    MIN_WIDTH,
    WindowState,
    load_window_state,
    save_window_state,
)

logger = logging.getLogger(__name__)
EDIT_FIELDS = {
    "meaning": "中文释义",
    "part_of_speech": "词性",
    "example": "英文例句",
    "example_translation": "例句翻译",
    "tags": "标签",
}


class DuplicateDialog(simpledialog.Dialog):
    def __init__(self, parent: tk.Misc, prepared: PreparedCapture):
        self.prepared = prepared
        self.action = tk.StringVar(parent, "skip")
        self.result: tuple[str, int | None] | None = None
        super().__init__(parent, title="这个单词已在 Anki 中")

    def body(self, master: tk.Misc) -> tk.Widget:
        ttk.Label(master, text="请选择处理方式。跳过不会调用 AI。", padding=6).pack(
            anchor="w"
        )
        self.notes = tk.Listbox(
            master, width=72, height=min(6, len(self.prepared.notes))
        )
        for note in self.prepared.notes:
            status = {"same": "相同领域", "other": "其他领域", "unknown": "领域未知"}
            editable = "可更新" if note.note_id in self.prepared.updates else "不可更新"
            self.notes.insert(
                tk.END,
                f"{note.note_id} · {note.model} · "
                f"{status[note.topic_status(self.prepared.topic)]} · {editable}",
            )
        self.notes.pack(fill="x", padx=6, pady=6)
        self.notes.selection_set(0)
        for text, value in (
            ("跳过", "skip"),
            ("更新选中的兼容笔记", "update"),
            ("按不同领域新增", "new"),
        ):
            button = ttk.Radiobutton(
                master, text=text, value=value, variable=self.action
            )
            button.pack(anchor="w", padx=6, pady=3)
            if value == "update" and not self.prepared.updates:
                button.state(["disabled"])
            if value == "new" and any(
                n.topic_status(self.prepared.topic) == "same"
                for n in self.prepared.notes
            ):
                button.state(["disabled"])
        ttk.Label(
            master,
            text="领域未知时，新增前请确认已有笔记属于不同领域。",
            padding=6,
        ).pack(anchor="w")
        return self.notes

    def validate(self) -> bool:
        if self.action.get() == "update":
            selected = self.notes.curselection()
            if (
                not selected
                or self.prepared.notes[selected[0]].note_id not in self.prepared.updates
            ):
                messagebox.showwarning(
                    "无法更新", "请选择标记为“可更新”的笔记。", parent=self
                )
                return False
        return True

    def apply(self) -> None:
        selected = self.notes.curselection()
        note_id = self.prepared.notes[selected[0]].note_id if selected else None
        self.result = self.action.get(), note_id


class VocabularyWindow:
    def __init__(
        self,
        root: tk.Tk,
        settings: Settings,
        workflow: DesktopWorkflow | None = None,
    ):
        self.root = root
        self.settings = settings
        self.workflow = workflow or DesktopWorkflow(settings)
        self.prepared: PreparedCapture | None = None
        self.target: SaveTarget | None = None
        self.entry: Vocabulary | None = None
        self.busy = False
        self.saving = False
        self.events: queue.Queue[tuple[Callable, Any, Exception | None]] = queue.Queue()
        self.cost_events: queue.Queue[CostEstimate | Exception] = queue.Queue()
        self.cost_loading = False
        self.cost_dirty = False
        self.word = tk.StringVar(root)
        self.topic = tk.StringVar(root, settings.default_topic)
        self.status = tk.StringVar(root, "输入单词，点击“生成预览”。请先打开 Anki。")
        self.destination = tk.StringVar(root, f"保存到：{settings.deck}")
        self.cost = tk.StringVar(root, "正在读取累计 API 花费…")
        self.window_state_path = settings.data_dir / "window_state.json"
        self.window_state = load_window_state(self.window_state_path).fit_screen(
            root.winfo_screenwidth(),
            root.winfo_screenheight(),
        )
        self.size_locked = tk.BooleanVar(root, self.window_state.locked)
        self.widgets: dict[str, tk.Entry | tk.Text | ttk.Entry] = {}
        self._build()
        self.word.trace_add("write", self._input_changed)
        self.topic.trace_add("write", self._input_changed)
        self.context.bind("<<Modified>>", self._context_changed)
        self.root.bind("<Control-Return>", lambda _: self.generate())
        self.root.bind("<Configure>", self._remember_window_size, add="+")
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self.poll_id = root.after(75, self._poll)
        self.refresh_cost()
        self.word_input.focus_set()

    def _build(self) -> None:
        self.root.title("AI 英语收词")
        self.root.geometry(f"{self.window_state.width}x{self.window_state.height}")
        self.root.minsize(
            min(MIN_WIDTH, self.window_state.width),
            min(MIN_HEIGHT, self.window_state.height),
        )
        self.root.resizable(not self.size_locked.get(), not self.size_locked.get())
        style = ttk.Style(self.root)
        if "clam" in style.theme_names():
            style.theme_use("clam")
        style.configure("TLabel", font=("sans-serif", 11))
        style.configure("TButton", font=("sans-serif", 11), padding=(12, 7))
        style.configure("Title.TLabel", font=("sans-serif", 20, "bold"))
        frame = ttk.Frame(self.root, padding=20)
        frame.pack(fill="both", expand=True)
        frame.columnconfigure(1, weight=1)
        frame.rowconfigure(5, weight=1)
        frame.rowconfigure(6, weight=1)
        header = ttk.Frame(frame)
        header.grid(row=0, column=0, columnspan=2, sticky="ew")
        header.columnconfigure(0, weight=1)
        ttk.Label(header, text="AI 英语收词", style="Title.TLabel").grid(
            row=0,
            column=0,
            sticky="w",
        )
        self.size_lock_button = ttk.Checkbutton(
            header,
            text="固定窗口大小",
            variable=self.size_locked,
            command=self._toggle_size_lock,
        )
        self.size_lock_button.grid(row=0, column=1, sticky="e")
        ttk.Label(
            frame, text="记住词义，用一句例句加深印象。", foreground="#59636e"
        ).grid(
            row=1,
            column=0,
            columnspan=2,
            sticky="w",
            pady=(4, 14),
        )
        inputs = ttk.Frame(frame)
        inputs.grid(row=2, column=0, columnspan=2, sticky="ew")
        inputs.columnconfigure(0, weight=1)
        ttk.Label(inputs, text="单词 / 短语").grid(row=0, column=0, sticky="w")
        ttk.Label(inputs, text="专业领域（可自定义）").grid(
            row=0, column=1, sticky="w", padx=(12, 0)
        )
        self.word_input = ttk.Entry(
            inputs, textvariable=self.word, font=("sans-serif", 14)
        )
        self.word_input.grid(row=1, column=0, sticky="ew", pady=5)
        self.topic_input = ttk.Combobox(
            inputs,
            textvariable=self.topic,
            values=settings_topics(self.settings),
            width=21,
        )
        self.topic_input.grid(row=1, column=1, sticky="ew", padx=(12, 0), pady=5)
        self.generate_button = ttk.Button(
            inputs, text="生成预览", command=self.generate
        )
        self.generate_button.grid(row=1, column=2, padx=(12, 0))
        ttk.Label(frame, text="原句（可选）").grid(row=3, column=0, sticky="nw", pady=9)
        self.context = ScrolledText(
            frame, height=2, wrap="word", font=("sans-serif", 11)
        )
        self.context.grid(row=3, column=1, sticky="ew", pady=9)
        short_fields = ttk.Frame(frame)
        short_fields.grid(row=4, column=0, columnspan=2, sticky="ew", pady=(12, 8))
        short_fields.columnconfigure(0, weight=3)
        short_fields.columnconfigure(1, weight=1)
        for col, key in enumerate(("meaning", "part_of_speech")):
            ttk.Label(short_fields, text=EDIT_FIELDS[key]).grid(
                row=0, column=col, sticky="w"
            )
            widget = ttk.Entry(short_fields, font=("sans-serif", 12))
            widget.grid(
                row=1, column=col, sticky="ew", padx=(0, 12) if col == 0 else 0, pady=5
            )
            self.widgets[key] = widget
        for row, key in ((5, "example"), (6, "example_translation")):
            ttk.Label(frame, text=EDIT_FIELDS[key]).grid(
                row=row, column=0, sticky="nw", pady=8
            )
            widget = ScrolledText(frame, height=3, wrap="word", font=("sans-serif", 12))
            widget.grid(row=row, column=1, sticky="nsew", pady=8)
            self.widgets[key] = widget
        ttk.Label(frame, text="标签（英文逗号分隔）").grid(
            row=7, column=0, sticky="w", pady=8
        )
        self.widgets["tags"] = ttk.Entry(frame, font=("sans-serif", 11))
        self.widgets["tags"].grid(row=7, column=1, sticky="ew", pady=8)
        ttk.Label(frame, textvariable=self.destination, foreground="#59636e").grid(
            row=8,
            column=0,
            columnspan=2,
            sticky="w",
            pady=(6, 12),
        )
        actions = ttk.Frame(frame)
        actions.grid(row=9, column=0, columnspan=2, sticky="ew")
        actions.columnconfigure(1, weight=1)
        self.reset_button = ttk.Button(
            actions, text="清空 / 下一个", command=self.reset
        )
        self.reset_button.grid(row=0, column=0)
        self.regenerate_button = ttk.Button(
            actions, text="重新生成", command=self.regenerate
        )
        self.regenerate_button.grid(row=0, column=2, padx=10)
        self.save_button = ttk.Button(actions, text="保存到 Anki", command=self.save)
        self.save_button.grid(row=0, column=3)
        self.progress = ttk.Progressbar(frame, mode="indeterminate")
        self.progress.grid(row=10, column=0, columnspan=2, sticky="ew", pady=(14, 6))
        ttk.Label(frame, textvariable=self.status, wraplength=700).grid(
            row=11,
            column=0,
            columnspan=2,
            sticky="w",
        )
        ttk.Label(
            frame,
            textvariable=self.cost,
            wraplength=700,
            foreground="#59636e",
        ).grid(row=12, column=0, columnspan=2, sticky="w", pady=(8, 0))
        ttk.Label(
            frame,
            text="按空闲～高峰单价估算，仅统计本工具用量，以平台账单为准。",
            foreground="#59636e",
            wraplength=700,
        ).grid(row=13, column=0, columnspan=2, sticky="w", pady=(2, 0))
        self._set_busy(False)

    def _set_busy(self, busy: bool) -> None:
        self.busy = busy
        for widget in (
            self.word_input,
            self.topic_input,
            self.generate_button,
            self.reset_button,
        ):
            widget.configure(state="disabled" if busy else "normal")
        self.context.configure(state="disabled" if busy else "normal")
        for widget in self.widgets.values():
            widget.configure(
                state="disabled" if busy or self.entry is None else "normal"
            )
        ready = not busy and self.entry is not None
        self.save_button.configure(state="normal" if ready else "disabled")
        self.regenerate_button.configure(state="normal" if ready else "disabled")
        if busy:
            self.progress.start(12)
        else:
            self.progress.stop()

    def _submit(self, work: Callable[[], Any], done: Callable, status: str) -> None:
        self.status.set(status)
        self._set_busy(True)

        def worker() -> None:
            try:
                self.events.put((done, work(), None))
            except Exception as exc:
                self.events.put((done, None, exc))

        threading.Thread(target=worker, daemon=True).start()

    def _poll(self) -> None:
        try:
            done, value, error = self.events.get_nowait()
        except queue.Empty:
            pass
        else:
            self.saving = False
            self._set_busy(False)
            self.refresh_cost()
            if error:
                self._show_error(error)
            else:
                done(value)
        try:
            estimate = self.cost_events.get_nowait()
        except queue.Empty:
            pass
        else:
            self.cost_loading = False
            self.cost.set(
                "累计 API 花费：暂时无法读取本地记录"
                if isinstance(estimate, Exception)
                else estimate.display()
            )
            if self.cost_dirty:
                self.refresh_cost()
        self.poll_id = self.root.after(75, self._poll)

    def refresh_cost(self) -> None:
        if self.cost_loading:
            self.cost_dirty = True
            return
        self.cost_loading = True
        self.cost_dirty = False

        def worker() -> None:
            try:
                result = read_cost(self.settings.data_dir / "vocabulary.sqlite3")
            except (OSError, sqlite3.Error) as exc:
                result = exc
            self.cost_events.put(result)

        threading.Thread(target=worker, daemon=True).start()

    def _show_error(self, error: Exception) -> None:
        if isinstance(error, VocabError):
            text = str(error)
        elif isinstance(error, (OSError, sqlite3.Error)):
            text = "无法访问本地文件或缓存，请检查路径、权限和剩余空间。"
        else:
            logger.error("桌面操作失败：%s", type(error).__name__)
            text = "操作未完成，请重试。若正在保存，请先在 Anki 中检查结果。"
        self.status.set(text)
        messagebox.showerror("操作未完成", text, parent=self.root)

    def _input_changed(self, *_: Any) -> None:
        if self.prepared and not self.busy:
            self.entry = self.prepared = self.target = None
            self.destination.set(f"保存到：{self.settings.deck}")
            self.status.set("输入已变化，请重新生成预览。")
            self._set_busy(False)

    def _context_changed(self, _: Any = None) -> None:
        if self.context.edit_modified():
            self.context.edit_modified(False)
            self._input_changed()

    def generate(self) -> None:
        if self.busy:
            return
        word, topic = self.word.get(), self.topic.get()
        context = self.context.get("1.0", "end-1c")
        self.entry = self.prepared = self.target = None
        self._submit(
            lambda: self.workflow.prepare(word, topic, context),
            self._prepared,
            "正在连接 Anki 并检查重复单词…",
        )

    def _prepared(self, prepared: PreparedCapture) -> None:
        self.prepared = prepared
        action, note_id = "new", None
        if prepared.notes:
            dialog = DuplicateDialog(self.root, prepared)
            action, note_id = dialog.result or ("skip", None)
        try:
            self.target = self.workflow.choose_target(prepared, action, note_id)
        except VocabError as exc:
            self._show_error(exc)
            return
        if self.target is None:
            self.status.set("已跳过，未调用 AI。可以输入下一个单词。")
            return
        self._submit(
            lambda: self.workflow.generate(prepared),
            self._generated,
            "正在生成学习内容；缓存未命中时会调用 DeepSeek…",
        )

    def _generated(self, entry: Vocabulary) -> None:
        self.entry = entry
        self._set_busy(False)
        for key, widget in self.widgets.items():
            value = ", ".join(entry.tags) if key == "tags" else getattr(entry, key)
            if isinstance(widget, tk.Text):
                widget.delete("1.0", tk.END)
                widget.insert("1.0", value)
            else:
                widget.delete(0, tk.END)
                widget.insert(0, value)
        target = self.target
        if target.existing:
            destination = f"更新笔记 {target.existing.note_id} · {target.model.name}"
        else:
            suffix = "（确认后新建类型）" if target.model.create else ""
            destination = f"{self.settings.deck} · {target.model.name}{suffix}"
        self.destination.set(destination)
        self.status.set("预览已就绪，可直接修改内容，满意后点击“保存到 Anki”。")

    def regenerate(self) -> None:
        if self.busy or self.entry is None:
            return
        if not messagebox.askyesno(
            "重新生成",
            "重新生成会调用 DeepSeek，可能再次产生费用。继续吗？",
            default="no",
            parent=self.root,
        ):
            return
        prepared = self.prepared
        self._submit(
            lambda: self.workflow.generate(prepared, force=True),
            self._generated,
            "正在重新生成…",
        )

    def edited_entry(self) -> Vocabulary:
        data = self.entry.to_dict()
        for key, widget in self.widgets.items():
            value = (
                widget.get("1.0", "end-1c")
                if isinstance(widget, tk.Text)
                else widget.get()
            )
            data[key] = (
                [t.strip() for t in value.split(",") if t.strip()]
                if key == "tags"
                else value
            )
        return Vocabulary.from_dict(data)

    def save(self) -> None:
        if self.busy or self.entry is None:
            return
        try:
            entry = self.edited_entry()
        except VocabError as exc:
            self._show_error(exc)
            return
        target, prepared = self.target, self.prepared
        message = f"{self.destination.get()}\n\n保存单词“{entry.word}”及当前预览内容？"
        if target.existing:
            previous = "\n".join(
                f"{name}: {plain_text(target.existing.fields[name]['value'])[:120]}"
                for name in note_fields(entry, target.model)
            )
            message += f"\n\n将替换以下字段的旧内容：\n{previous}"
        if not messagebox.askyesno(
            "确认保存到 Anki", message, default="no", parent=self.root
        ):
            self.status.set("已取消保存，可继续修改预览。")
            return
        self.saving = True
        self._submit(
            lambda: self.workflow.save(entry, prepared, target, confirmed=True),
            self._saved,
            "正在保存到 Anki，请稍候…",
        )

    def _saved(self, note_id: int) -> None:
        self.entry = self.prepared = self.target = None
        self._set_busy(False)
        self.status.set(f"已保存到 Anki（ID {note_id}）。可清空后收下一个单词。")
        messagebox.showinfo(
            "保存成功",
            f"已保存到 Anki，笔记 ID：{note_id}。\n手机复习前记得同步。",
            parent=self.root,
        )

    def reset(self) -> None:
        if self.busy:
            return
        self.entry = self.prepared = self.target = None
        self.word.set("")
        self.context.delete("1.0", tk.END)
        self.context.edit_modified(False)
        for widget in self.widgets.values():
            widget.configure(state="normal")
            if isinstance(widget, tk.Text):
                widget.delete("1.0", tk.END)
            else:
                widget.delete(0, tk.END)
        self._set_busy(False)
        self.destination.set(f"保存到：{self.settings.deck}")
        self.status.set("输入下一个单词。")
        self.word_input.focus_set()

    def _remember_window_size(self, event: tk.Event | None = None) -> None:
        if event is not None and event.widget is not self.root:
            return
        if self.root.state() != "normal":
            return
        if self.root.tk.getboolean(self.root.attributes("-zoomed")):
            return
        self.window_state = WindowState(
            self.root.winfo_width(),
            self.root.winfo_height(),
            self.size_locked.get(),
        )

    def _save_window_size(self) -> None:
        self._remember_window_size()
        try:
            save_window_state(self.window_state_path, self.window_state)
        except OSError:
            logger.warning("无法保存窗口大小，请检查数据目录权限。")

    def _toggle_size_lock(self) -> None:
        self.root.resizable(not self.size_locked.get(), not self.size_locked.get())
        self.window_state = WindowState(
            self.window_state.width,
            self.window_state.height,
            self.size_locked.get(),
        )
        self._save_window_size()

    def close(self) -> None:
        if self.saving:
            messagebox.showinfo(
                "正在保存", "请等待写入结果，再关闭窗口。", parent=self.root
            )
            return
        if self.busy and not messagebox.askyesno(
            "关闭窗口",
            "当前请求尚未结束，关闭后 API 仍可能计费。确定关闭？",
            default="no",
            parent=self.root,
        ):
            return
        self._save_window_size()
        self.root.after_cancel(self.poll_id)
        self.root.destroy()


def settings_topics(settings: Settings) -> tuple[str, ...]:
    return tuple(dict.fromkeys((settings.default_topic, *settings.topics)))


def run_gui(settings: Settings) -> int:
    try:
        root = tk.Tk()
    except tk.TclError as exc:
        raise VocabError("无法打开桌面窗口，请在已登录的图形桌面会话运行。") from exc
    VocabularyWindow(root, settings)
    root.mainloop()
    return 0
