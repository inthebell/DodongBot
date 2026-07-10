import asyncio
import json
import re
import time
import unicodedata
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable
from urllib.parse import urlparse

import aiohttp
from bs4 import BeautifulSoup


BASE_URL = "https://dongle-land.gitbook.io/dongle_land"
SITEMAP_URL = f"{BASE_URL}/sitemap.xml"
CACHE_PATH = Path("data/wiki_cache.json")
CACHE_SECONDS = 60 * 60 * 12
REQUEST_TIMEOUT = aiohttp.ClientTimeout(total=20)
USER_AGENT = "DodongBot-Wiki/1.0"


@dataclass
class WikiPage:
    title: str
    url: str
    text: str


@dataclass
class WikiSearchResult:
    title: str
    url: str
    summary: str
    score: float


def normalize_text(text: str) -> str:
    text = unicodedata.normalize("NFKC", text)
    text = text.lower()
    return re.sub(r"[^0-9a-z가-힣]+", "", text)


def tokenize(text: str) -> list[str]:
    normalized = unicodedata.normalize("NFKC", text).lower()
    return re.findall(r"[0-9a-z가-힣]{2,}", normalized)


def unique_in_order(values: Iterable[str]) -> list[str]:
    result = []
    seen = set()

    for value in values:
        if value in seen:
            continue

        seen.add(value)
        result.append(value)

    return result


def clean_page_text(soup: BeautifulSoup) -> tuple[str, str]:
    title = ""

    heading = soup.find("h1")

    if heading:
        title = heading.get_text(" ", strip=True)

    if not title and soup.title:
        title = soup.title.get_text(" ", strip=True)
        title = title.split("|")[0].strip()

    content = (
        soup.find("main")
        or soup.find("article")
        or soup.body
    )

    if content is None:
        return title or "동글랜드 위키", ""

    for tag in content.find_all(
        ["script", "style", "nav", "footer", "button", "svg", "noscript"]
    ):
        tag.decompose()

    lines = []

    for element in content.find_all(
        ["h1", "h2", "h3", "h4", "p", "li", "td", "th"]
    ):
        text = element.get_text(" ", strip=True)
        text = re.sub(r"\s+", " ", text)

        if len(text) < 2:
            continue

        lines.append(text)

    lines = unique_in_order(lines)
    body = "\n".join(lines)

    return title or "동글랜드 위키", body


def make_summary(page: WikiPage, query: str, limit: int = 650) -> str:
    lines = [
        re.sub(r"\s+", " ", line).strip()
        for line in page.text.splitlines()
        if line.strip()
    ]

    if not lines:
        return (
            "질문과 관련된 위키 페이지를 찾았습니다.\n"
            "자세한 내용은 아래 위키 바로가기를 확인해주세요."
        )

    query_tokens = [
        normalize_text(token)
        for token in tokenize(query)
        if normalize_text(token)
    ]

    scored_lines = []

    for index, line in enumerate(lines):
        normalized_line = normalize_text(line)
        score = 0

        for token in query_tokens:
            if token in normalized_line:
                score += 5

        if index == 0:
            score += 2

        if len(line) > 180:
            score -= 2

        if re.search(r"[x×]\s*\d+|\d+\s*개", line, re.IGNORECASE):
            score -= 1

        scored_lines.append(
            (score, index, line)
        )

    scored_lines.sort(
        key=lambda item: (-item[0], item[1])
    )

    selected = []
    used_indexes = set()

    for score, index, line in scored_lines:
        if len(selected) >= 3:
            break

        if score <= 0 and selected:
            continue

        if index in used_indexes:
            continue

        selected.append((index, line))
        used_indexes.add(index)

    if not selected:
        selected = [
            (index, line)
            for index, line in enumerate(lines[:3])
        ]

    selected.sort(key=lambda item: item[0])

    summary_lines = [
        line
        for _, line in selected
    ]

    summary = "\n".join(summary_lines)
    summary += (
        "\n\n자세한 수치, 재료, 조건 등은 "
        "아래 위키 바로가기를 확인해주세요."
    )

    if len(summary) > limit:
        summary = summary[: limit - 1].rstrip() + "…"

    return summary


class WikiManager:
    def __init__(self) -> None:
        self.pages: list[WikiPage] = []
        self.lock = asyncio.Lock()
        self.last_loaded_at = 0.0

    async def _fetch_text(
        self,
        session: aiohttp.ClientSession,
        url: str,
    ) -> str:
        async with session.get(url) as response:
            response.raise_for_status()
            return await response.text()

    async def _read_sitemap_urls(
        self,
        session: aiohttp.ClientSession,
        sitemap_url: str,
        visited: set[str],
    ) -> list[str]:
        if sitemap_url in visited:
            return []

        visited.add(sitemap_url)
        xml_text = await self._fetch_text(session, sitemap_url)
        root = ET.fromstring(xml_text)

        urls = []

        for element in root.iter():
            if not element.tag.endswith("loc"):
                continue

            if not element.text:
                continue

            location = element.text.strip()

            if location.endswith(".xml"):
                urls.extend(
                    await self._read_sitemap_urls(
                        session,
                        location,
                        visited,
                    )
                )
                continue

            parsed = urlparse(location)

            if parsed.netloc != urlparse(BASE_URL).netloc:
                continue

            if not location.startswith(BASE_URL):
                continue

            urls.append(location)

        return unique_in_order(urls)

    async def _fetch_page(
        self,
        session: aiohttp.ClientSession,
        url: str,
        semaphore: asyncio.Semaphore,
    ) -> WikiPage | None:
        async with semaphore:
            try:
                html = await self._fetch_text(session, url)
            except (
                aiohttp.ClientError,
                asyncio.TimeoutError,
            ):
                return None

        soup = BeautifulSoup(html, "html.parser")
        title, text = clean_page_text(soup)

        if len(text) < 20:
            return None

        return WikiPage(
            title=title,
            url=url,
            text=text,
        )

    def _load_cache(self) -> bool:
        if not CACHE_PATH.exists():
            return False

        try:
            data = json.loads(
                CACHE_PATH.read_text(encoding="utf-8")
            )
        except (OSError, json.JSONDecodeError):
            return False

        saved_at = float(data.get("saved_at", 0))

        if time.time() - saved_at > CACHE_SECONDS:
            return False

        raw_pages = data.get("pages", [])

        self.pages = [
            WikiPage(
                title=page["title"],
                url=page["url"],
                text=page["text"],
            )
            for page in raw_pages
            if page.get("title")
            and page.get("url")
            and page.get("text")
        ]

        self.last_loaded_at = saved_at
        return bool(self.pages)

    def _save_cache(self) -> None:
        CACHE_PATH.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        payload = {
            "saved_at": time.time(),
            "pages": [
                {
                    "title": page.title,
                    "url": page.url,
                    "text": page.text,
                }
                for page in self.pages
            ],
        }

        CACHE_PATH.write_text(
            json.dumps(
                payload,
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

    async def refresh(self, force: bool = False) -> int:
        async with self.lock:
            if not force and self.pages:
                if time.time() - self.last_loaded_at < CACHE_SECONDS:
                    return len(self.pages)

            if not force and self._load_cache():
                return len(self.pages)

            headers = {
                "User-Agent": USER_AGENT,
            }

            async with aiohttp.ClientSession(
                headers=headers,
                timeout=REQUEST_TIMEOUT,
            ) as session:
                urls = await self._read_sitemap_urls(
                    session,
                    SITEMAP_URL,
                    set(),
                )

                semaphore = asyncio.Semaphore(5)

                tasks = [
                    self._fetch_page(
                        session,
                        url,
                        semaphore,
                    )
                    for url in urls
                ]

                fetched_pages = await asyncio.gather(*tasks)

            self.pages = [
                page
                for page in fetched_pages
                if page is not None
            ]
            self.last_loaded_at = time.time()

            if self.pages:
                self._save_cache()

            return len(self.pages)

    def _score_page(
        self,
        page: WikiPage,
        query: str,
    ) -> float:
        normalized_query = normalize_text(query)
        normalized_title = normalize_text(page.title)
        normalized_body = normalize_text(page.text)

        if not normalized_query:
            return 0.0

        score = 0.0

        if normalized_query == normalized_title:
            score += 150.0
        elif normalized_query in normalized_title:
            score += 100.0
        elif normalized_title in normalized_query:
            score += 65.0

        if normalized_query in normalized_body:
            score += 55.0

        for token in tokenize(query):
            normalized_token = normalize_text(token)

            if normalized_token in normalized_title:
                score += 24.0

            body_count = normalized_body.count(normalized_token)
            score += min(body_count, 8) * 4.0

        return score

    async def search(
        self,
        query: str,
    ) -> WikiSearchResult | None:
        await self.refresh()

        if not self.pages:
            return None

        ranked = sorted(
            (
                (self._score_page(page, query), page)
                for page in self.pages
            ),
            key=lambda item: item[0],
            reverse=True,
        )

        best_score, best_page = ranked[0]

        if best_score < 8:
            return None

        return WikiSearchResult(
            title=best_page.title,
            url=best_page.url,
            summary=make_summary(best_page, query),
            score=best_score,
        )


wiki_manager = WikiManager()