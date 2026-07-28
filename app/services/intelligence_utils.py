import re
from datetime import datetime

DATE_PATTERNS = [
    r"\b\d{4}-\d{2}-\d{2}\b",
    r"\b\d{1,2}[./-]\d{1,2}[./-]\d{2,4}\b",
]


def split_sentences(text: str) -> list[str]:
    return [
        sentence.strip()
        for sentence in re.split(r"(?<=[.!?])\s+|\n+", text or "")
        if sentence.strip()
    ]


def parse_date_text(value: str) -> datetime | None:
    value = (value or "").strip()
    for fmt in ["%Y-%m-%d", "%d.%m.%Y", "%d/%m/%Y", "%d-%m-%Y", "%d.%m.%y", "%d/%m/%y"]:
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    return None


def first_date_in_text(text: str) -> tuple[str | None, datetime | None]:
    for pattern in DATE_PATTERNS:
        match = re.search(pattern, text or "")
        if match:
            return match.group(0), parse_date_text(match.group(0))
    return None, None


def infer_amount(text: str) -> tuple[float | None, str | None]:
    match = re.search(
        r"(?P<currency>USD|EUR|KZT|RUB|₸|\$|€)?\s*(?P<amount>\d+(?:[\s,]\d{3})*(?:[.,]\d{2})?)\s*(?P<tail>USD|EUR|KZT|RUB|тенге|руб(?:\.|лей)?|₸|\$|€)?",
        text or "",
        flags=re.IGNORECASE,
    )
    if not match:
        return None, None
    raw_amount = match.group("amount").replace(" ", "").replace(",", ".")
    try:
        amount = float(raw_amount)
    except ValueError:
        amount = None
    currency = match.group("currency") or match.group("tail")
    return amount, currency
