"""Cache-first generation, separate from desktop and Anki interaction."""

import logging
from dataclasses import replace

from .cache import Cache
from .config import Settings
from .deepseek_client import DeepSeekClient
from .vocabulary import Vocabulary

logger = logging.getLogger(__name__)


class VocabularyService:
    def __init__(self, settings: Settings, cache: Cache):
        self.settings = settings
        self.cache = cache

    def get(
        self,
        word: str,
        topic: str,
        context: str = "",
        force: bool = False,
    ) -> Vocabulary:
        if not force:
            cached = self.cache.get(word, topic, context)
            if cached:
                logger.info("使用本地缓存，未调用 DeepSeek。")
                return replace(cached, word=word, topic=topic)
        print("正在请求 DeepSeek（可能产生 API 费用）…")
        client = DeepSeekClient(self.settings, self.cache)
        try:
            entry = client.generate(word, topic, context)
        finally:
            client.close()
        self.cache.put(entry)
        return entry
