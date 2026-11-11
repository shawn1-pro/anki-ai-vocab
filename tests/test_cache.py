import json
from dataclasses import replace

from anki_ai_vocab.cache import Cache


def test_cache_persists_and_normalizes(tmp_path, entry):
    path = tmp_path / "cache.sqlite3"
    with Cache(path) as cache:
        assert cache.get(entry.word, entry.topic) is None
        cache.put(entry)
        cache.put(replace(entry, meaning="更新的释义"))
    with Cache(path) as cache:
        assert cache.get("  DEGENERACY ", "slam").meaning == "更新的释义"
        assert cache.get(entry.word, "Robotics") is None


def test_cache_separates_sentence_context(tmp_path, entry):
    with Cache(tmp_path / "cache.sqlite3") as cache:
        sentence = "Degeneracy affects observability."
        contextual = replace(entry, example=sentence, source_sentence=sentence)
        cache.put(entry)
        cache.put(contextual)
        assert cache.get(entry.word, entry.topic) == entry
        assert cache.get(entry.word, entry.topic, sentence) == contextual
        assert cache.get(entry.word, entry.topic, "Another sentence.") is None


def test_corrupt_cache_is_ignored(tmp_path, entry):
    with Cache(tmp_path / "cache.sqlite3") as cache:
        cache.put(entry)
        cache.db.execute("UPDATE vocabulary SET content='broken json'")
        cache.db.commit()
        assert cache.get(entry.word, entry.topic) is None


def test_legacy_explanation_is_ignored_without_losing_cached_content(tmp_path, entry):
    with Cache(tmp_path / "cache.sqlite3") as cache:
        legacy = {**entry.to_dict(), "domain_explanation": "旧版冗长的解释"}
        cache.db.execute(
            "INSERT INTO vocabulary(word, topic, context, content) VALUES(?,?,?,?)",
            (entry.word, "slam", "", json.dumps(legacy)),
        )
        cache.db.commit()
        cached = cache.get(entry.word, entry.topic)
        assert cached == entry
        assert "domain_explanation" not in cached.to_dict()


def test_token_ledger(tmp_path):
    with Cache(tmp_path / "cache.sqlite3") as cache:
        cache.record_usage("deepseek-flash", 100, 60, 160, 10)
        cache.record_usage("deepseek-flash", 50, 20, 70)
        row = cache.usage()[0]
        assert row == {
            "model": "deepseek-flash",
            "requests": 2,
            "prompt_tokens": 150,
            "completion_tokens": 80,
            "total_tokens": 230,
            "cached_tokens": 10,
        }
