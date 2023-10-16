import asyncio
import time
from contextlib import asynccontextmanager
from enum import Enum

import pytest
from aiohttp import ClientResponseError, ClientSession, InvalidURL
from anyio import create_task_group
from async_timeout import timeout
from pymorphy2 import MorphAnalyzer

from adapters.exceptions import ArticleNotFound
from adapters.inosmi_ru import sanitize
from text_tools import calculate_jaundice_rate, split_by_words

FETCH_TIMEOUT = 5
PROCESSING_TIMEOUT = 10

morph = MorphAnalyzer()


class ProcessingStatus(Enum):
    OK = "OK"
    FETCH_ERROR = "FETCH_ERROR"
    PARSING_ERROR = "PARSING_ERROR"
    TIMEOUT = "TIMEOUT"
    INVALID_URL = "INVALID_URL"


async def fetch(session, url):
    async with session.get(url) as response:
        response.raise_for_status()
        return await response.text()


@asynccontextmanager
async def log_execution_time():
    start_timestamp = time.monotonic()
    try:
        yield
    finally:
        processing_time = time.monotonic() - start_timestamp
        print(f"Анализ закончен за {round(processing_time, 4)} сек")


def get_charged_words():
    with open(
        "charged_dict/positive_words.txt", "r", encoding="utf-8"
    ) as positive_file:
        positive_words = positive_file.read().splitlines()

    with open(
        "charged_dict/negative_words.txt", "r", encoding="utf-8"
    ) as negative_file:
        negative_words = negative_file.read().splitlines()

    return positive_words + negative_words


async def process_article(results: list, url: str, charged_words: list[str]) -> None:
    result = {"rate": None, "url": url, "status": ProcessingStatus.OK.value}
    async with ClientSession() as session:
        try:
            async with timeout(FETCH_TIMEOUT):
                html = await fetch(session, url)
            async with timeout(PROCESSING_TIMEOUT):
                async with log_execution_time():
                    sanitized_text = sanitize(html)
                    words = await split_by_words(morph, sanitized_text)
                    rate = calculate_jaundice_rate(words, charged_words)
                    result["rate"] = rate
        except (ClientResponseError, InvalidURL):
            result["status"] = ProcessingStatus.FETCH_ERROR.value
        except ArticleNotFound:
            result["status"] = ProcessingStatus.PARSING_ERROR.value
        except (asyncio.TimeoutError, TimeoutError):
            result["status"] = ProcessingStatus.TIMEOUT.value
        results.append(result)


async def process(articles: list[str]) -> list[dict]:
    charged_words = get_charged_words()
    results = []

    async with create_task_group() as tg:
        for url in articles:
            tg.start_soon(process_article, results, url, charged_words)

    return results


# asyncio.run(main())
@pytest.mark.asyncio
async def test_process_article():
    charged_words = get_charged_words()

    async with ClientSession() as session:
        results = []
        url = "https://inosmi.ru/20211116/250914886.html"
        await process_article(results, url, charged_words)
        assert len(results) == 1
        result = results[0]
        assert result["status"] == ProcessingStatus.OK.value
        assert result["url"] == url
        assert result["rate"] >= 0
        assert result["rate"] <= 100

        results = []
        url = "https://inosmi.ru/article_does_not_exist.html"
        await process_article(results, url, charged_words)
        assert len(results) == 1
        result = results[0]
        assert result["status"] == ProcessingStatus.FETCH_ERROR.value
        assert result["url"] == url
        assert result["rate"] is None

        results = []
        url = "https://www.bbc.com/news/world-middle-east-67084141"
        await process_article(results, url, charged_words)
        assert len(results) == 1
        result = results[0]
        assert result["status"] == ProcessingStatus.PARSING_ERROR.value
        assert result["url"] == url
        assert result["rate"] is None
