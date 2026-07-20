import re


def estimate_pages(word_count: int, words_per_page: int = 450) -> int:
    if word_count <= 0:
        return 0
    return max(1, round(word_count / words_per_page))


def extract_markdown_headings(text: str) -> list[str]:
    headings = []
    for line in text.splitlines():
        match = re.match(r"^\s{0,3}#{1,6}\s+(.+?)\s*$", line)
        if match:
            headings.append(match.group(1).strip())
    return headings


def extract_likely_section_titles(text: str, limit: int = 12) -> list[str]:
    titles = []
    seen = set()

    for line in text.splitlines():
        candidate = line.strip()
        if not candidate:
            continue

        looks_numbered = bool(re.match(r"^\d+(\.\d+)*[.)]?\s+\S+", candidate))
        looks_short_title = (
            len(candidate) <= 90
            and len(candidate.split()) <= 10
            and not candidate.endswith((".", ",", ";"))
        )

        if not (looks_numbered or looks_short_title):
            continue

        normalized = candidate.lower()
        if normalized in seen:
            continue

        seen.add(normalized)
        titles.append(candidate)
        if len(titles) >= limit:
            break

    return titles


def build_preview_blocks(text: str, max_blocks: int = 3, max_chars: int = 500) -> list[str]:
    blocks = []
    for block in re.split(r"\n\s*\n+", text.strip()):
        normalized = re.sub(r"\s+", " ", block).strip()
        if normalized:
            blocks.append(normalized[:max_chars])
        if len(blocks) >= max_blocks:
            break
    return blocks


def build_document_structure(text: str, file_type: str, word_count: int) -> dict:
    text = text or ""
    markdown_headings = extract_markdown_headings(text) if file_type == "md" else []
    sections = markdown_headings or extract_likely_section_titles(text)

    return {
        "estimated_pages": estimate_pages(word_count),
        "sections": sections,
        "preview_blocks": build_preview_blocks(text),
    }
