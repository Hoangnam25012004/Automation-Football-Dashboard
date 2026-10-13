"""Crawler Flashscore: 1 link trận → JSON đúng hình dạng `state` của match_report.html.

Thiết kế: docs/detailed-design-url-ingestion.md. Dùng:  from crawler import crawl
"""
from .errors import CrawlError
from .run import crawl

__all__ = ["crawl", "CrawlError"]
