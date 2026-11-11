import json

import pytest

from anki_ai_vocab.window_state import (
    WindowState,
    load_window_state,
    save_window_state,
)


def test_missing_preferences_use_larger_default_without_creating_files(tmp_path):
    path = tmp_path / "data/window_state.json"
    assert load_window_state(path) == WindowState(1000, 820, False)
    assert not path.parent.exists()


def test_size_and_lock_persist(tmp_path):
    path = tmp_path / "data/window_state.json"
    state = WindowState(1100, 800, True)
    save_window_state(path, state)
    assert load_window_state(path) == state


@pytest.mark.parametrize(
    "data", [[], {"width": -1}, {"height": "820"}, {"locked": "yes"}]
)
def test_invalid_preferences_fall_back_to_defaults(tmp_path, data):
    path = tmp_path / "window_state.json"
    path.write_text(json.dumps(data))
    assert load_window_state(path) == WindowState()


def test_corrupt_json_falls_back_to_defaults(tmp_path):
    path = tmp_path / "window_state.json"
    path.write_text("interrupted write")
    assert load_window_state(path) == WindowState()


def test_oversized_preferences_fit_a_smaller_screen():
    assert WindowState(3000, 2000, True).fit_screen(1024, 768) == WindowState(
        984, 688, True
    )


def test_tiny_preferences_keep_the_usable_minimum():
    assert WindowState(1, 1).fit_screen(1920, 1080) == WindowState(650, 640)
