"""posted_videos.json → 채널 프로필 링크용 페이지 한 장 (GitHub Pages로 배포)."""
import html
import json
import os

from description_builder import COUPANG_DISCLOSURE

ROOT = os.path.dirname(os.path.abspath(__file__))
RECORDS_PATH = os.path.join(ROOT, "posted_videos.json")
SITE_DIR = os.path.join(ROOT, "site")

PAGE = """<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>영상 속 제품 모음</title>
<style>
body {{ margin: 0 auto; max-width: 560px; padding: 16px; font-family: system-ui, sans-serif;
       background: #fafafa; color: #222; line-height: 1.5; }}
.notice {{ font-size: 13px; color: #666; background: #eee; padding: 10px 12px; border-radius: 8px; }}
section {{ background: #fff; border-radius: 12px; padding: 12px 16px; margin: 14px 0;
          box-shadow: 0 1px 3px rgba(0,0,0,.08); }}
h2 {{ font-size: 18px; margin: 4px 0 8px; }}
h2 a {{ color: inherit; }}
ol {{ margin: 0; padding-left: 0; list-style: none; }}
li {{ margin: 8px 0; }}
li a {{ display: block; padding: 10px 12px; border-radius: 8px; background: #fff3c4;
        color: #222; text-decoration: none; font-weight: 600; }}
</style>
</head>
<body>
<p class="notice">{notice}</p>
{sections}
</body>
</html>
"""


def build_page(records: list[dict]) -> str:
    """최신 영상부터 '#번호 주제 → 순위별 상품 링크'. 쿠팡으로 자동 이동하지 않는다."""
    sections = []
    for record in reversed(records):
        items = "".join(
            f'<li><a href="{html.escape(p["link"])}" rel="sponsored nofollow">'
            f'{rank}위 · {html.escape(p["name"])}</a></li>'
            for rank, p in enumerate(record["products"], start=1)
        )
        sections.append(
            f'<section id="{record["number"]}"><h2>#{record["number"]} '
            f'<a href="{html.escape(record["url"])}">{html.escape(record["topic"])}</a></h2>'
            f"<ol>{items}</ol></section>"
        )
    return PAGE.format(notice=html.escape(COUPANG_DISCLOSURE),
                       sections="\n".join(sections) or "<p>아직 영상이 없어요.</p>")


if __name__ == "__main__":
    records = []
    if os.path.exists(RECORDS_PATH):
        with open(RECORDS_PATH, "r", encoding="utf-8") as f:
            records = json.load(f)
    os.makedirs(SITE_DIR, exist_ok=True)
    with open(os.path.join(SITE_DIR, "index.html"), "w", encoding="utf-8") as f:
        f.write(build_page(records))
    print(f"페이지 생성: 영상 {len(records)}편")
