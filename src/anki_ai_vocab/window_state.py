"""Remember the preferred window dimensions independently of vocabulary data."""

import json
import logging
from dataclasses import asdict, dataclass, replace
from pathlib import Path

logger = logging.getLogger(__name__)
MIN_WIDTH = 650
MIN_HEIGHT = 640


@dataclass(frozen=True)
class WindowState:
    width: int = 1000
    height: int = 820
    locked: bool = False

    def fit_screen(self, screen_width: int, screen_height: int) -> "WindowState":
        available_width = max(1, screen_width - 40)
        available_height = max(1, screen_height - 80)
        return replace(
            self,
            width=min(
                available_width, max(min(MIN_WIDTH, available_width), self.width)
            ),
            height=min(
                available_height, max(min(MIN_HEIGHT, available_height), self.height)
            ),
        )


def load_window_state(path: Path) -> WindowState:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("Window preferences must be a JSON object")
        state = WindowState(
            data.get("width", 1000),
            data.get("height", 820),
            data.get("locked", False),
        )
        if (
            type(state.width) is not int
            or type(state.height) is not int
            or state.width <= 0
            or state.height <= 0
            or type(state.locked) is not bool
        ):
            raise ValueError("Invalid window preferences")
        return state
    except FileNotFoundError:
        return WindowState()
    except (OSError, ValueError):
        logger.warning("窗口尺寸记录无法读取，将使用默认大小。")
        return WindowState()


def save_window_state(path: Path, state: WindowState) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(state), indent=2) + "\n", encoding="utf-8")
