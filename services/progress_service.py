import html
import re
import unicodedata
from services.converter import count_words


ARABIC_CHAR_RE = re.compile(r"[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF]")
HEADING_KEYWORD_RE = re.compile(
    r"^(?:#{1,6}\s*|тарау|бөлім|кіріспе|қорытынды|алғы сөз|глава|часть|введение|заключение|chapter|part|introduction|conclusion)\b",
    flags=re.IGNORECASE,
)


def make_progress_bar(percent: int, length: int = 8) -> str:
    clamped = max(0, min(100, percent))
    filled = round((clamped / 100) * length)
    return "🟩" * filled + "⬜" * (length - filled)


def prepare_readable_text(text: str) -> str:
    if not text:
        return ""

    cleaned = unicodedata.normalize("NFKC", text)
    cleaned = cleaned.replace("\r\n", "\n").replace("\r", "\n")
    cleaned = re.sub(r"(\w)-\s*\n\s*(\w)", r"\1\2", cleaned)

    raw_lines = [line.strip() for line in cleaned.split("\n")]
    paragraphs: list[str] = []
    current_para: list[str] = []

    def _flush_para() -> None:
        if current_para:
            joined = re.sub(r"\s+", " ", " ".join(current_para)).strip()
            if joined:
                paragraphs.append(joined)
            current_para.clear()

    for line in raw_lines:
        if not line:
            _flush_para()
            continue

        is_md_heading = bool(re.match(r"^#{1,6}\s+.+$", line))
        is_keyword_heading = bool(HEADING_KEYWORD_RE.match(line)) and len(line) <= 110
        is_short_title = (
            len(line) <= 65
            and not re.search(r"[.!?:;…]$", line)
            and len(line.split()) <= 8
            and not current_para
        )

        if is_md_heading or is_keyword_heading or is_short_title:
            _flush_para()
            paragraphs.append(line)
            continue

        current_para.append(line)

        if len(line) > 95 and re.search(r"[.!?…]$", line):
            _flush_para()

    _flush_para()
    return "\n\n".join(paragraphs).strip()


def _is_heading_paragraph(para: str) -> bool:
    s = para.strip()
    if not s:
        return False
    if re.match(r"^#{1,6}\s+.+$", s):
        return True
    if HEADING_KEYWORD_RE.match(s) and len(s) <= 110:
        return True
    words = s.split()
    if len(s) <= 60 and 1 <= len(words) <= 7 and not re.search(r"[.!?…,:;]$", s):
        return True
    return False


def format_portion_html(text: str) -> str:
    readable = prepare_readable_text(text)
    if not readable:
        return ""

    blocks = readable.split("\n\n")
    out_blocks: list[str] = []

    for block in blocks:
        b = block.strip()
        if not b:
            continue

        if _is_heading_paragraph(b):
            heading_clean = re.sub(r"^#{1,6}\s*", "", b).strip().strip("*").strip()
            heading_html = f"<b>📌 {html.escape(heading_clean)}</b>"
            if ARABIC_CHAR_RE.search(heading_clean):
                heading_html = "\u200f" + heading_html
            out_blocks.append(heading_html)
            continue

        escaped = html.escape(b)
        escaped = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", escaped)
        escaped = re.sub(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)", r"<i>\1</i>", escaped)

        arabic_count = len(ARABIC_CHAR_RE.findall(b))
        if arabic_count >= 5:
            escaped = "\u200f" + escaped

        out_blocks.append(escaped)

    return "\n\n".join(out_blocks).strip()


def split_message_chunks(text: str, max_len: int = 3500) -> list[str]:
    readable = prepare_readable_text(text)
    if not readable:
        return []
    if len(readable) <= max_len:
        return [readable]

    chunks: list[str] = []
    remaining = readable

    while len(remaining) > max_len:
        window = remaining[:max_len]
        cut_pos = window.rfind("\n\n")
        if cut_pos < int(max_len * 0.5):
            match = None
            for m in re.finditer(r"[.!?…]+(?:\s+|\n|$)", window):
                if m.end() >= int(max_len * 0.5):
                    match = m
            cut_pos = match.end() if match else window.rfind(" ")
        if cut_pos <= 0:
            cut_pos = max_len

        part = remaining[:cut_pos].strip()
        if part:
            chunks.append(part)
        remaining = remaining[cut_pos:].lstrip()

    if remaining.strip():
        chunks.append(remaining.strip())

    return chunks


def extract_next_portion(
    md_path: str,
    start_char: int,
    target_words: int,
) -> tuple[str, int, int, int, bool]:
    with open(md_path, "r", encoding="utf-8") as f:
        full_text = f.read()

    total_len = len(full_text)
    if start_char >= total_len:
        return "", 0, start_char, start_char, True

    actual_start = start_char
    while actual_start < total_len and full_text[actual_start].isspace():
        actual_start += 1

    if actual_start >= total_len:
        return "", 0, total_len, total_len, True

    word_pattern = re.compile(r"\b\w+\b", flags=re.UNICODE)
    words_seen = 0
    cut_index = total_len

    for match in word_pattern.finditer(full_text, pos=actual_start):
        words_seen += 1
        if words_seen >= target_words:
            cut_index = match.end()
            break

    if total_len - cut_index < 250:
        cut_index = total_len
    elif cut_index < total_len:
        tail = full_text[cut_index : min(total_len, cut_index + 220)]
        sent_match = re.search(r"[.!?…]+(?:\s+|\n|$)", tail)
        if sent_match:
            cut_index = cut_index + sent_match.end()

    portion_text = full_text[actual_start:cut_index].strip()
    actual_words = count_words(portion_text)
    is_finished = cut_index >= total_len

    return portion_text, actual_words, actual_start, cut_index, is_finished


def get_page_char_offset(
    md_path: str,
    page_number: int,
    words_per_page: int,
) -> tuple[int, int]:
    """
    Көрсетілген бет нөміріне (page_number) дейінгі оқылған сөз саны мен .md позициясын қайтарады.
    Қайтарады: (char_offset, read_words_count)
    """
    with open(md_path, "r", encoding="utf-8") as f:
        full_text = f.read()

    total_len = len(full_text)
    if page_number <= 1 or total_len == 0:
        return 0, 0

    target_words = max(0, (page_number - 1) * max(1, words_per_page))
    if target_words == 0:
        return 0, 0

    word_pattern = re.compile(r"\b\w+\b", flags=re.UNICODE)
    words_seen = 0
    offset = total_len

    for match in word_pattern.finditer(full_text):
        words_seen += 1
        if words_seen >= target_words:
            offset = match.end()
            break

    return offset, words_seen


def find_text_char_offset(
    md_path: str,
    query_text: str,
) -> tuple[int, int] | None:
    """
    Мәтін үзіндісін іздеп, табылған жердің бастапқы символ орнын және сол жерге дейінгі сөз санын қайтарады.
    """
    cleaned_query = unicodedata.normalize("NFKC", query_text).strip()
    if not cleaned_query:
        return None

    with open(md_path, "r", encoding="utf-8") as f:
        full_text = f.read()

    norm_full = unicodedata.normalize("NFKC", full_text)
    idx = norm_full.lower().find(cleaned_query.lower())
    if idx == -1:
        # Бос орындар мен жаңа жолдарды бір бос орынға келтіріп қайта іздеу
        compact_query = re.sub(r"\s+", " ", cleaned_query).strip().lower()
        compact_full = re.sub(r"\s+", " ", norm_full).lower()
        c_idx = compact_full.find(compact_query)
        if c_idx == -1:
            return None
        words_before = count_words(compact_full[:c_idx])
        # Сөз санына сәйкес шамамен char offset табу
        word_pattern = re.compile(r"\b\w+\b", flags=re.UNICODE)
        seen = 0
        char_pos = 0
        for m in word_pattern.finditer(full_text):
            if seen >= words_before:
                break
            seen += 1
            char_pos = m.end()
        return char_pos, words_before

    words_before = count_words(norm_full[:idx])
    return idx, words_before