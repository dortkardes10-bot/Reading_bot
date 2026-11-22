import re
from services.converter import count_words


def split_message_chunks(text: str, max_len: int = 3800) -> list[str]:
    """
    Telegram-ның 4096 таңба шегіне жеткізбей, мәтінді бірнеше хабарламаға бөледі.
    """
    text = text.strip()
    if not text:
        return []
    if len(text) <= max_len:
        return [text]

    chunks: list[str] = []
    remaining = text

    while len(remaining) > max_len:
        window = remaining[:max_len]
        # Алдымен абзац соңын іздеу
        cut_pos = window.rfind("\n\n")
        if cut_pos < int(max_len * 0.5):
            # Болмаса сөйлем соңын (. ! ? …) іздеу
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
    """
    md_path файлынан start_char позициясынан бастап шамамен target_words сөз алады.
    Қайтарады: (portion_text, actual_words, new_start_char, new_end_char, is_book_finished)
    """
    with open(md_path, "r", encoding="utf-8") as f:
        full_text = f.read()

    total_len = len(full_text)
    if start_char >= total_len:
        return "", 0, start_char, start_char, True

    actual_start = start_char
    # Бастапқы бос орындарды өткізу
    while actual_start < total_len and full_text[actual_start].isspace():
        actual_start += 1

    if actual_start >= total_len:
        return "", 0, total_len, total_len, True

    # Сөз санап отырып шамамен target_words-ке жету
    word_pattern = re.compile(r"\b\w+\b", flags=re.UNICODE)
    words_seen = 0
    cut_index = total_len

    for match in word_pattern.finditer(full_text, pos=actual_start):
        words_seen += 1
        if words_seen >= target_words:
            cut_index = match.end()
            break

    # Егер кітаптың соңына жақын қалса, соңына дейін қоса салу
    if total_len - cut_index < 250:
        cut_index = total_len
    elif cut_index < total_len:
        # Сөйлемнің ортасынан үзбеу үшін келесі тыныс белгісіне дейін созу (макс +220 таңба)
        tail = full_text[cut_index : min(total_len, cut_index + 220)]
        sent_match = re.search(r"[.!?…]+(?:\s+|\n|$)", tail)
        if sent_match:
            cut_index = cut_index + sent_match.end()

    portion_text = full_text[actual_start:cut_index].strip()
    actual_words = count_words(portion_text)
    is_finished = cut_index >= total_len

    return portion_text, actual_words, actual_start, cut_index, is_finished