"""Chẩn đoán crawler NGAY TRÊN máy chủ (vd Hugging Face): Flashscore có thể hiển thị khác theo vùng IP.

Chạy khi khởi động nếu đặt biến FS_DIAG_URL (cloud.hf_main gọi `run_in_background`). Ghi lại: trạng thái từng bước,
các phần tử nổi (overlay) đang che nút chọn đội, call log đầy đủ của lỗi click, HTML + ảnh chụp trang player stats.
Kết quả tải lên Dataset riêng tư (thư mục diag/<thời điểm>/) — không đụng tới thư viện trận, không đổi crawler.
"""
from __future__ import annotations

import json
import logging
import os
import tempfile
import threading
import time
from pathlib import Path

log = logging.getLogger("cloud.diag")

JS_OVERLAYS = r"""() => {
  const btn = document.querySelector('[data-testid="wcl-selectButton"]');
  const out = {button: null, topAtButton: null, fixed: []};
  if (btn) {
    const r = btn.getBoundingClientRect();
    out.button = {x: r.x, y: r.y, w: r.width, h: r.height, text: btn.innerText, visible: !!btn.getClientRects().length};
    const el = document.elementFromPoint(r.x + r.width / 2, r.y + r.height / 2);
    out.topAtButton = el ? (el.outerHTML || '').slice(0, 600) : null;
  }
  for (const el of document.querySelectorAll('body *')) {
    const cs = getComputedStyle(el);
    if ((cs.position === 'fixed' || cs.position === 'sticky') && cs.display !== 'none' && cs.visibility !== 'hidden') {
      const r = el.getBoundingClientRect();
      if (r.width * r.height > 20000) out.fixed.push({tag: el.tagName, id: el.id, cls: String(el.className).slice(0, 120),
        z: cs.zIndex, rect: [Math.round(r.x), Math.round(r.y), Math.round(r.width), Math.round(r.height)],
        text: (el.innerText || '').slice(0, 200)});
    }
  }
  out.cookieBanners = [...document.querySelectorAll('[id*="onetrust"], [id*="consent"], [class*="consent"], [id*="cmp"], [class*="cmp"]')]
    .slice(0, 10).map(e => ({tag: e.tagName, id: e.id, cls: String(e.className).slice(0, 80), visible: !!e.getClientRects().length}));
  out.lang = document.documentElement.lang; out.url = location.href; out.title = document.title;
  return out;
}"""


JS_OPTION_DETAIL = r"""() => [...document.querySelectorAll('[role="option"]')].map(o => {
  const r = o.getBoundingClientRect(), cs = getComputedStyle(o);
  let p = o, chain = [];
  for (let i = 0; i < 6 && p; i++, p = p.parentElement) {
    const c = getComputedStyle(p);
    chain.push({tag: p.tagName, cls: String(p.className).slice(0, 60), display: c.display, vis: c.visibility, op: c.opacity,
      pos: c.position, transform: c.transform.slice(0, 40), h: Math.round(p.getBoundingClientRect().height)});
  }
  return {text: o.innerText, rect: [Math.round(r.x), Math.round(r.y), Math.round(r.width), Math.round(r.height)],
          display: cs.display, visibility: cs.visibility, opacity: cs.opacity, chain};
})"""


def diagnose(url: str) -> dict:
    from playwright.sync_api import sync_playwright

    from crawler import browser as fsb
    from crawler.urls import parse_match_url

    ref = parse_match_url(url)
    report: dict = {"url": url, "steps": [], "started": time.strftime("%Y-%m-%d %H:%M:%S")}
    files: dict[str, bytes] = {}

    def step(name: str, **data) -> None:
        report["steps"].append({"step": name, **data})
        log.info("diag %s %s", name, data)

    with sync_playwright() as p:
        browser = fsb.launch(p)
        try:
            ctx = fsb.new_context(browser)
            page = ctx.new_page()
            resp = fsb.goto(page, ref.url())
            step("match_page", status=resp.status if resp else None, final_url=page.url)
            step("consent", used=fsb.dismiss_consent(page, ctx))
            page.wait_for_timeout(2000)
            step("header", info=page.evaluate("""() => ({names: [...document.querySelectorAll('.participant__participantName')]
                .map(e => e.innerText), status: (document.querySelector('.detailScore__status') || {}).innerText,
                tabs: [...document.querySelectorAll('[role=tab]')].map(t => t.textContent.trim()).slice(0, 12)})"""))
            resp = fsb.goto(page, ref.url("summary/player-stats/top"))
            step("player_stats_page", status=resp.status if resp else None, final_url=page.url)
            try:
                page.wait_for_selector('[data-testid="wcl-table"]', timeout=15000)
                step("table", ok=True)
            except Exception as exc:
                step("table", ok=False, error=str(exc)[:2000])
            page.wait_for_timeout(1500)
            step("overlays_before_click", data=page.evaluate(JS_OVERLAYS))
            files["player_stats.html"] = page.content().encode("utf-8")
            files["player_stats.png"] = page.screenshot(full_page=False)
            try:
                page.locator('[data-testid="wcl-selectButton"]').first.click(timeout=5000)
                page.wait_for_timeout(800)
                step("click_select", ok=True, options=page.evaluate(
                    "() => [...document.querySelectorAll('[role=\"option\"]')].map(o => o.innerText)"))
                opt = page.locator('[role="option"]').first
                step("options_detail", pw_visible=opt.is_visible(), viewport=page.viewport_size, data=page.evaluate(JS_OPTION_DETAIL))
                files["after_click.png"] = page.screenshot(full_page=False)
            except Exception as exc:
                step("click_select", ok=False, error=str(exc)[:4000])          # call log: ai chặn click
                files["after_click_fail.png"] = page.screenshot(full_page=False)
        finally:
            browser.close()
    report["finished"] = time.strftime("%Y-%m-%d %H:%M:%S")
    files["report.json"] = json.dumps(report, ensure_ascii=False, indent=1).encode("utf-8")
    return {"report": report, "files": files}


def upload(files: dict[str, bytes]) -> str:
    from huggingface_hub import HfApi
    api = HfApi(token=os.environ["HF_TOKEN"])
    folder = "diag/" + time.strftime("%Y%m%d-%H%M%S")
    with tempfile.TemporaryDirectory() as tmp:
        for name, data in files.items():
            (Path(tmp) / name).write_bytes(data)
        api.upload_folder(folder_path=tmp, path_in_repo=folder, repo_id=os.environ["HF_BACKUP_REPO"],
                          repo_type="dataset", commit_message="crawler diagnostics")
    return folder


def full_crawls(urls: list[str], rounds: int) -> list[dict]:
    """Chạy crawler thật (giống worker) nhiều lần ⇒ đo tỉ lệ thành công trên chính máy chủ."""
    from crawler import CrawlError, crawl
    out = []
    for r in range(rounds):
        for url in urls:
            t0 = time.monotonic()
            try:
                res = crawl(url)
                out.append({"url": url, "round": r, "ok": True, "s": round(time.monotonic() - t0, 1),
                            "warnings": [w["code"] for w in res["warnings"]]})
            except CrawlError as exc:
                out.append({"url": url, "round": r, "ok": False, "s": round(time.monotonic() - t0, 1),
                            "code": exc.code, "hint": exc.hint[:600]})
            log.info("diag crawl %s", out[-1])
    return out


def run_in_background() -> None:
    urls = [u.strip() for u in os.environ.get("FS_DIAG_URL", "").split(",") if u.strip()]
    if not urls:
        return
    rounds = max(0, min(10, int(os.environ.get("FS_DIAG_CRAWLS", "0") or 0)))

    def job() -> None:
        try:
            result = diagnose(urls[0])
            if rounds:
                runs = full_crawls(urls, rounds)
                result["files"]["crawls.json"] = json.dumps(runs, ensure_ascii=False, indent=1).encode("utf-8")
        except Exception as exc:
            result = {"files": {"report.json": json.dumps({"url": urls[0], "fatal": repr(exc)}).encode("utf-8")}}
            log.error("diag lỗi: %r", exc)
        try:
            if os.environ.get("HF_TOKEN") and os.environ.get("HF_BACKUP_REPO"):
                log.info("diag đã tải lên %s", upload(result["files"]))
        except Exception as exc:
            log.error("diag không tải lên được: %r", exc)

    threading.Thread(target=job, name="diag", daemon=True).start()
