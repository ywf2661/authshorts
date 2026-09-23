import hashlib
import json
import os

MAX_HISTORY = 500


def hash_link(link: str) -> str:
    return hashlib.sha256(link.encode("utf-8")).hexdigest()


def load_posted_ids(path: str) -> set[str]:
    if not os.path.exists(path):
        return set()
    with open(path, "r", encoding="utf-8") as f:
        return set(json.load(f))


def save_posted_ids(path: str, ids: set[str]) -> None:
    # Read existing ordered list (oldest-first)
    existing_order = []
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            existing_order = json.load(f)

    # Build new ordered list: keep existing entries that are still in ids
    ordered = [entry for entry in existing_order if entry in ids]

    # Add any new entries (those in ids but not in existing_order)
    existing_set = set(existing_order)
    new_entries = [entry for entry in ids if entry not in existing_set]
    ordered.extend(new_entries)

    # Trim from front (oldest) if exceeds MAX_HISTORY
    if len(ordered) > MAX_HISTORY:
        ordered = ordered[-MAX_HISTORY:]

    # Write to file
    with open(path, "w", encoding="utf-8") as f:
        json.dump(ordered, f)


def pick_next_entry(entries: list[dict], posted_ids: set[str]) -> dict | None:
    """미게시 항목 중 published가 가장 최신인 1건을 반환한다."""
    unposted = [e for e in entries if hash_link(e["link"]) not in posted_ids]
    if not unposted:
        return None
    return max(unposted, key=lambda e: e["published"])
