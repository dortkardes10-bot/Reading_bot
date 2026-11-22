import re
from services.converter import count_words


HEADING_PATTERN = re.compile(
    r"^(#{1,4}\s+.+|(?:тарау|бөлім|глава|chapter|part)\b.+)$",
    flags=re.IGNORECASE | re.MULTILINE,
)


def estimate_pages(total_words: int, words_per_page: int = 290) -> int:
    if total_words <= 0:
        return 0
    return max(1, round(total_words / max(1, words_per_page)))


def split_text_into_days(text: str, days: int = 7) -> list[str]:
    """
    Мәтінді шамамен тең сөз көлемімен `days` күнге бөледі.
    Мүмкіндігінше тарау/абзац шекарасында бөлуге тырысады.
    """
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text.strip()) if p.strip()]
    if not paragraphs:
        return ["" for _ in range(days)]

    total_words = sum(count_words(p) for p in paragraphs)
    target_per_day = max(1, total_words / days)

    day_chunks: list[str] = []
    current_paras: list[str] = []
    current_words = 0

    for idx, para in enumerate(paragraphs):
        para_words = count_words(para)
        remaining_days = days - len(day_chunks)

        # Қалған күндерге әрқайсысына кем дегенде 1 абзац қалуы үшін
        remaining_paras = len(paragraphs) - idx
        must_break_for_remaining_days = (
            remaining_days > 1 and remaining_paras <= remaining_days and len(current_paras) > 0
        )

        # Келесі абзац тарау атауы болса және бүгінгі норманың 75%-ынан асқан болса, жаңа күннен бастау тиімді
        is_next_heading = bool(HEADING_PATTERN.match(para))
        good_chapter_break = (
            is_next_heading
            and len(current_paras) > 0
            and current_words >= target_per_day * 0.75
            and remaining_days > 1
        )

        exceeds_target = (
            len(current_paras) > 0
            and (current_words + para_words) > target_per_day * 1.15
            and remaining_days > 1
        )

        if must_break_for_remaining_days or good_chapter_break or exceeds_target:
            day_chunks.append("\n\n".join(current_paras))
            current_paras = [para]
            current_words = para_words
        else:
            current_paras.append(para)
            current_words += para_words

    if current_paras:
        if len(day_chunks) < days:
            day_chunks.append("\n\n".join(current_paras))
        else:
            day_chunks[-1] = day_chunks[-1] + "\n\n" + "\n\n".join(current_paras)

    while len(day_chunks) < days:
        day_chunks.append("")

    return day_chunks[:days]