import threading
import time
from dataclasses import replace
from types import SimpleNamespace

import pytest

tk = pytest.importorskip("tkinter")

from test_gui_workflow import prepared_capture  # noqa: E402

from anki_ai_vocab import gui  # noqa: E402
from anki_ai_vocab.anki_client import ExistingNote  # noqa: E402
from anki_ai_vocab.cache import Cache  # noqa: E402
from anki_ai_vocab.errors import GenerationError  # noqa: E402
from anki_ai_vocab.gui_workflow import DesktopWorkflow  # noqa: E402
from anki_ai_vocab.window_state import load_window_state  # noqa: E402


class FakeWorkflow:
    def __init__(self, settings, entry):
        self.settings = settings
        self.entry = entry
        self.calls = []
        self.fail = False

    def prepare(self, word, topic, context):
        self.calls.append("prepare")
        return prepared_capture(
            replace(self.entry, word=word, topic=topic, source_sentence=context)
        )

    def choose_target(self, prepared, action, note_id=None):
        return DesktopWorkflow(self.settings).choose_target(prepared, action, note_id)

    def generate(self, prepared, force=False):
        self.calls.append(("generate", force))
        if self.fail:
            raise GenerationError("mock timeout")
        return replace(self.entry, word=prepared.word, topic=prepared.topic)

    def save(self, entry, prepared, target, *, confirmed=False):
        self.calls.append(("save", entry, confirmed))
        assert confirmed
        return 321


@pytest.fixture
def window(settings, entry, monkeypatch):
    try:
        root = tk.Tk()
    except tk.TclError:
        pytest.skip("GUI interaction tests need a display or Xvfb")
    root.withdraw()
    for name in ("showinfo", "showerror", "showwarning"):
        monkeypatch.setattr(gui.messagebox, name, lambda *args, **kwargs: None)
    fake = FakeWorkflow(settings, entry)
    app = gui.VocabularyWindow(root, settings, fake)
    yield app, fake
    try:
        if root.winfo_exists():
            root.after_cancel(app.poll_id)
            root.destroy()
    except tk.TclError:
        pass  # Tests may already have closed the application normally.


def wait_for_idle(app):
    deadline = time.monotonic() + 3
    while app.busy and time.monotonic() < deadline:
        app.root.update()
        time.sleep(0.01)
    assert not app.busy, "GUI did not complete its background operation"
    app.root.update()


def generate(app):
    app.word.set("degeneracy")
    app.topic.set("SLAM")
    app.generate()
    wait_for_idle(app)


def wait_for_cost(app):
    deadline = time.monotonic() + 3
    while app.cost_loading and time.monotonic() < deadline:
        app.root.update()
        time.sleep(0.01)
    assert not app.cost_loading, "Cost display did not finish reading local usage"


def test_cost_label_reads_existing_history_on_startup(window):
    app, _ = window
    with Cache(app.settings.data_dir / "vocabulary.sqlite3") as cache:
        cache.record_usage("deepseek-flash", 100, 60, 160, 10)
    app.refresh_cost()
    wait_for_cost(app)
    assert "¥0.000330～¥0.000660" in app.cost.get()
    assert "1 次请求" in app.cost.get()


def test_cost_refreshes_after_generation_and_stays_after_reset(window, monkeypatch):
    app, fake = window
    original_generate = fake.generate

    def generate_with_usage(prepared, force=False):
        with Cache(app.settings.data_dir / "vocabulary.sqlite3") as cache:
            cache.record_usage("deepseek-flash", 100, 60, 160, 10)
        return original_generate(prepared, force)

    monkeypatch.setattr(fake, "generate", generate_with_usage)
    generate(app)
    wait_for_cost(app)
    assert "1 次请求" in app.cost.get()
    before = app.cost.get()
    app.reset()
    assert app.cost.get() == before


def test_failed_generation_with_usage_still_increases_estimated_cost(
    window, monkeypatch
):
    app, fake = window

    def fail_after_billing(*args, **kwargs):
        with Cache(app.settings.data_dir / "vocabulary.sqlite3") as cache:
            cache.record_usage("deepseek-flash", 100, 60, 160, 10)
        raise GenerationError("模型输出无效，但 usage 已返回")

    monkeypatch.setattr(fake, "generate", fail_after_billing)
    generate(app)
    wait_for_cost(app)
    assert app.entry is None
    assert "1 次请求" in app.cost.get()
    assert "¥0.000330" in app.cost.get()


def test_cost_read_error_does_not_block_the_window(window, monkeypatch):
    app, _ = window
    wait_for_cost(app)

    def fail_read(*args):
        raise OSError("mock read error")

    monkeypatch.setattr(gui, "read_cost", fail_read)
    app.refresh_cost()
    wait_for_cost(app)
    assert "暂时无法读取" in app.cost.get()
    assert str(app.generate_button.cget("state")) == "normal"


def test_generate_fills_editable_preview_without_explanation(window):
    app, fake = window
    assert str(app.save_button.cget("state")) == "disabled"
    generate(app)
    assert app.widgets["phonetic"].get() == fake.entry.phonetic
    assert app.widgets["meaning"].get() == "退化"
    assert app.widgets["example"].get("1.0", "end-1c") == fake.entry.example
    assert "domain_explanation" not in app.widgets
    assert str(app.save_button.cget("state")) == "normal"
    assert not any(isinstance(c, tuple) and c[0] == "save" for c in fake.calls)


def test_declining_save_never_writes(window, monkeypatch):
    app, fake = window
    generate(app)
    monkeypatch.setattr(gui.messagebox, "askyesno", lambda *args, **kwargs: False)
    app.save()
    assert "已取消保存" in app.status.get()
    assert not any(isinstance(c, tuple) and c[0] == "save" for c in fake.calls)


def test_confirmed_save_includes_user_edits(window, monkeypatch):
    app, fake = window
    generate(app)
    app.widgets["meaning"].delete(0, tk.END)
    app.widgets["meaning"].insert(0, "修改后的释义")
    app.widgets["phonetic"].delete(0, tk.END)
    app.widgets["phonetic"].insert(0, "/ˈtest/")
    monkeypatch.setattr(gui.messagebox, "askyesno", lambda *args, **kwargs: True)
    app.save()
    wait_for_idle(app)
    saved = next(
        call for call in fake.calls if isinstance(call, tuple) and call[0] == "save"
    )
    assert saved[1].meaning == "修改后的释义" and saved[2] is True
    assert saved[1].phonetic == "/ˈtest/"
    assert "321" in app.status.get()
    assert str(app.save_button.cget("state")) == "disabled"


def test_old_cache_can_be_previewed_and_phonetic_filled_manually(window):
    app, fake = window
    fake.entry = replace(fake.entry, phonetic="")
    generate(app)
    assert app.widgets["phonetic"].get() == ""
    assert "旧缓存暂无音标" in app.status.get()
    app.widgets["phonetic"].insert(0, "/ˈtest/")
    assert app.edited_entry().phonetic == "/ˈtest/"


def test_changed_word_requires_new_preview(window):
    app, _ = window
    generate(app)
    app.word.set("covariance")
    assert app.entry is None
    assert str(app.save_button.cget("state")) == "disabled"


def test_changed_context_requires_new_preview(window):
    app, _ = window
    generate(app)
    app.context.insert("1.0", "A different sentence.")
    app.root.update()
    assert app.entry is None
    assert str(app.save_button.cget("state")) == "disabled"


def test_regeneration_failure_keeps_preview_and_recovers_controls(window, monkeypatch):
    app, fake = window
    generate(app)
    fake.fail = True
    monkeypatch.setattr(gui.messagebox, "askyesno", lambda *args, **kwargs: True)
    app.regenerate()
    wait_for_idle(app)
    assert app.entry is not None
    assert app.widgets["meaning"].get() == "退化"
    assert str(app.save_button.cget("state")) == "normal"
    assert "mock timeout" in app.status.get()


def test_reset_clears_preview_and_never_saves(window):
    app, fake = window
    generate(app)
    app.reset()
    assert app.word.get() == ""
    assert app.widgets["meaning"].get() == ""
    assert app.widgets["phonetic"].get() == ""
    assert app.entry is None
    assert not any(isinstance(c, tuple) and c[0] == "save" for c in fake.calls)


def test_duplicate_skip_stops_before_generation(window, monkeypatch):
    app, fake = window
    note = ExistingNote(7, "AI Vocabulary", {}, ())
    prepared = prepared_capture(fake.entry, [note])
    monkeypatch.setattr(fake, "prepare", lambda *args: prepared)
    monkeypatch.setattr(
        gui, "DuplicateDialog", lambda *args: SimpleNamespace(result=None)
    )
    generate(app)
    assert fake.calls == []
    assert "已跳过" in app.status.get()
    assert str(app.save_button.cget("state")) == "disabled"


def test_slow_generation_keeps_main_window_responsive(window, monkeypatch):
    app, fake = window
    started, release = threading.Event(), threading.Event()
    original_generate = fake.generate

    def slow_generate(prepared, force=False):
        started.set()
        release.wait(timeout=3)
        return original_generate(prepared, force)

    monkeypatch.setattr(fake, "generate", slow_generate)
    app.word.set("degeneracy")
    app.generate()
    deadline = time.monotonic() + 2
    try:
        while not started.is_set() and time.monotonic() < deadline:
            app.root.update()
            time.sleep(0.01)
        assert started.is_set()
        events = []
        app.root.after(0, lambda: events.append("UI responded"))
        app.root.update()
        assert events == ["UI responded"] and app.busy
    finally:
        release.set()
        wait_for_idle(app)


def test_resize_then_lock_saves_the_selected_dimensions(window):
    app, _ = window
    app.root.deiconify()
    app.root.geometry("1100x800")
    app.root.update()
    app.size_lock_button.invoke()
    assert app.root.resizable() == (0, 0)
    state = load_window_state(app.window_state_path)
    assert (state.width, state.height, state.locked) == (1100, 800, True)
    app.size_lock_button.invoke()
    assert app.root.resizable() == (1, 1)
    assert load_window_state(app.window_state_path).locked is False


def test_close_and_reopen_restore_dimensions_and_lock(window):
    app, fake = window
    app.root.deiconify()
    app.root.geometry("1100x800")
    app.root.update()
    app.size_lock_button.invoke()
    app.close()

    root = tk.Tk()
    root.withdraw()
    restored = gui.VocabularyWindow(root, app.settings, fake)
    try:
        root.deiconify()
        root.update()
        assert (root.winfo_width(), root.winfo_height()) == (1100, 800)
        assert restored.size_locked.get() is True
        assert root.resizable() == (0, 0)
    finally:
        root.after_cancel(restored.poll_id)
        root.destroy()


def test_maximized_geometry_does_not_overwrite_normal_size(window, monkeypatch):
    app, _ = window
    app.root.deiconify()
    app.root.update()
    before = app.window_state
    monkeypatch.setattr(app.root, "attributes", lambda option: 1)
    monkeypatch.setattr(app.root, "winfo_width", lambda: 1920)
    monkeypatch.setattr(app.root, "winfo_height", lambda: 1080)
    app._remember_window_size()
    assert app.window_state == before


def test_system_close_while_saving_keeps_the_window_open(window):
    app, _ = window
    app.saving = True
    app.close()
    assert app.root.winfo_exists()
    assert not app.window_state_path.exists()


def test_declining_close_during_generation_keeps_window_and_preferences(
    window, monkeypatch
):
    app, _ = window
    app.busy = True
    monkeypatch.setattr(gui.messagebox, "askyesno", lambda *args, **kwargs: False)
    app.close()
    assert app.root.winfo_exists()
    assert not app.window_state_path.exists()
