import feedparser
import requests


def fetch_feed_entries(feed_urls: list[str]) -> list[dict]:
    """RSS 피드 목록에서 항목을 수집한다. 파싱 실패한 피드는 건너뛴다."""
    entries = []
    for url in feed_urls:
        try:
            response = requests.get(url, timeout=10)
            parsed = feedparser.parse(response.content)
            if parsed.bozo and not parsed.entries:
                continue
            for entry in parsed.entries:
                published = entry.get("published_parsed")
                if published is None:
                    continue
                entries.append(
                    {
                        "title": entry.get("title", ""),
                        "summary": entry.get("summary", ""),
                        "link": entry.get("link", ""),
                        "published": published,
                    }
                )
        except Exception:
            print(f"RSS 피드 파싱 실패, 건너뜀: {url}")
            continue
    return entries
