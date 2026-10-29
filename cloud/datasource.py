"""Nguồn dữ liệu cắm thay được (design doc cloud §5.4).

Mọi nguồn trả về `result` đúng hợp đồng schemaVersion 2 của crawler (CLAUDE.md §3) ⇒ dashboard không đổi.
Hôm nay chỉ có FlashscoreSource (bọc crawler/ — logic không đổi). Nguồn có giấy phép sẽ là lớp khác.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Protocol

from crawler.errors import CrawlError

from .errors import ApiError


@dataclass(frozen=True)
class SourceRef:
    source: str          # "flashscore"
    key: str             # khoá trận trong nguồn (Flashscore: mid)
    url: str             # link đã chuẩn hoá — dựng lại từ thành phần đã kiểm tra, không dùng nguyên văn


class DataSource(Protocol):
    name: str

    def parse_ref(self, url: str) -> SourceRef: ...

    def fetch(self, ref: SourceRef, progress: Callable[[dict], None]) -> dict: ...


class FlashscoreSource:
    name = "flashscore"

    def parse_ref(self, url: str) -> SourceRef:
        from crawler.urls import parse_match_url
        ref = parse_match_url(url)                      # ném CrawlError E_URL_INVALID như bản local
        if not ref.mid:
            # thiếu ?mid= thì Flashscore tự chọn trận ⇒ không xác định được khoá thư viện
            raise ApiError("E_MID_REQUIRED", hint="Copy the link again from the match page — it should end with ?mid=…")
        return SourceRef(self.name, ref.mid, ref.url())

    def fetch(self, ref: SourceRef, progress: Callable[[dict], None]) -> dict:
        from crawler import crawl
        return crawl(ref.url, progress=progress)


_SOURCE: DataSource = FlashscoreSource()


def get() -> DataSource:
    return _SOURCE


def set_source(source: DataSource) -> None:
    """Thay nguồn (test dùng nguồn giả; sau này: nguồn có giấy phép)."""
    global _SOURCE
    _SOURCE = source


__all__ = ["SourceRef", "DataSource", "FlashscoreSource", "get", "set_source", "CrawlError"]
