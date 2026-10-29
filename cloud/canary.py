"""Canary hằng đêm: crawl trận tham chiếu, báo admin nếu hỏng (Flashscore đổi DOM / chặn IP).

  python -m cloud.canary [link]       (cron trên VM: docker compose exec -T worker python -m cloud.canary)

Không ghi vào thư viện, không tính hạn mức. Đồng thời giữ cho VM có tải định kỳ.
"""
from __future__ import annotations

import sys
import time

from . import config, datasource, mail

REFERENCE = "https://www.flashscore.com/match/football/johor-dt-AVV6BGlb/svay-rieng-IHTx6E4O/?mid=vLuGlk0n"


def main() -> int:
    settings = config.load()
    url = sys.argv[1] if len(sys.argv) > 1 else REFERENCE
    source = datasource.get()
    started = time.monotonic()
    try:
        result = source.fetch(source.parse_ref(url), lambda p: None)
        stats = result["stats"]
        rows = sum(len(stats["teams"][c]["Top Stats"]["rows"]) for c in (stats["home"], stats["away"]))
        if rows < 22 or not (result.get("summary") or {}).get("events"):
            raise RuntimeError(f"thiếu dữ liệu: {rows} dòng Top Stats, timeline rỗng")
        print(f"✓ canary {time.monotonic() - started:.1f} s · cảnh báo: {[w['code'] for w in result['warnings']]}")
        return 0
    except Exception as exc:                       # mọi lỗi đều phải báo admin
        mail.alert_admin(settings, "Nightly crawl check failed",
                         f"The reference match could not be read: {exc}\nCheck tests/live and the crawler.")
        print(f"✗ canary: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
