from dataclasses import replace

import pytest

from anki_ai_vocab import service
from anki_ai_vocab.cache import Cache


@pytest.mark.parametrize("has_phonetic", [True, False])
def test_cache_does_not_require_key_or_remote_client(
    no_key, entry, monkeypatch, has_phonetic
):
    def unexpected(*args, **kwargs):
        raise AssertionError("Cached lookup must not initialize an API client")

    monkeypatch.setattr(service, "DeepSeekClient", unexpected)
    if not has_phonetic:
        entry = replace(entry, phonetic="")
    with Cache(no_key.data_dir / "cache.sqlite3") as cache:
        cache.put(entry)
        result = service.VocabularyService(no_key, cache).get("DEGENERACY", "SLAM")
        assert result.word == "DEGENERACY"
        assert result.meaning == entry.meaning
        assert result.phonetic == entry.phonetic


def test_force_bypasses_cache_and_closes_client(settings, entry, monkeypatch):
    calls = []

    class FakeClient:
        def __init__(self, *args):
            pass

        def generate(self, word, topic, context):
            calls.append("generate")
            return replace(entry, meaning="重新生成")

        def close(self):
            calls.append("close")

    monkeypatch.setattr(service, "DeepSeekClient", FakeClient)
    with Cache(settings.data_dir / "cache.sqlite3") as cache:
        cache.put(replace(entry, phonetic=""))
        result = service.VocabularyService(settings, cache).get(
            entry.word, entry.topic, force=True
        )
        assert result.meaning == "重新生成"
        assert result.phonetic == entry.phonetic
        assert cache.get(entry.word, entry.topic) == result
    assert calls == ["generate", "close"]
