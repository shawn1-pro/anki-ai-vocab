from dataclasses import replace

import pytest

from anki_ai_vocab.config import Settings
from anki_ai_vocab.vocabulary import Vocabulary


@pytest.fixture
def settings(tmp_path):
    return Settings(data_dir=tmp_path / "data", api_key="test_key_never_sent")


@pytest.fixture
def entry():
    return Vocabulary(
        word="degeneracy",
        topic="SLAM",
        meaning="退化",
        example="Geometric degeneracy may cause localization drift.",
        example_translation="几何退化可能导致定位漂移。",
        part_of_speech="noun",
        tags=("SLAM", "state_estimation"),
    )


@pytest.fixture
def no_key(settings):
    return replace(settings, api_key="")
