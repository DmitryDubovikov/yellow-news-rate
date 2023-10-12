import asyncio
from enum import Enum

from aiohttp import ClientResponseError, ClientSession, InvalidURL
from anyio import create_task_group
from async_timeout import timeout
from pymorphy2 import MorphAnalyzer

from adapters.exceptions import ArticleNotFound
from adapters.inosmi_ru import sanitize
from text_tools import calculate_jaundice_rate, split_by_words

FETCH_TIMEOUT = 3


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


async def process_article(
    results: list, url: str, morph: MorphAnalyzer, charged_words: list[str]
) -> None:
    result = {"rate": None, "url": url, "status": ProcessingStatus.OK}
    async with ClientSession() as session:
        try:
            async with timeout(FETCH_TIMEOUT):
                html = await fetch(session, url)
            sanitized_text = sanitize(html)
            words = split_by_words(morph, sanitized_text)
            rate = calculate_jaundice_rate(words, charged_words)
            result["rate"] = rate
        except (ClientResponseError, InvalidURL):
            result["status"] = ProcessingStatus.FETCH_ERROR.value
        except ArticleNotFound:
            result["status"] = ProcessingStatus.PARSING_ERROR.value
        except (asyncio.TimeoutError, TimeoutError):
            result["status"] = ProcessingStatus.TIMEOUT.value
        results.append(result)


async def main():
    morph = MorphAnalyzer()
    charged_words = get_charged_words()

    results = []

    test_articles = [
        "https://inosmi.ru/economic/20190629/245384784.html",
        "https://inosmi.ru/20231012/zelenskiy-266090827.html",
        "https://inosmi.ru/20231012/es-266088279.html",
        "https://inosmi.ru/20231012/yaponiya-266090719.html",
        "https://inosmi.ru/20231012/finlyandiya-266094161.html",
        "https://inosmi.ru/20231012/finl",
        "https://lenta.ru/brief/2021/08/26/afg_terror/",
    ]

    async with create_task_group() as tg:
        for url in test_articles:
            tg.start_soon(process_article, results, url, morph, charged_words)

    print(*results, sep="\n")


asyncio.run(main())
