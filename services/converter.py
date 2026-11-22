import os
import re
import unicodedata
from pathlib import Path

from markitdown import MarkItDown

try:
    import pytesseract
    from pypdf import PdfReader
    from pdf2image import convert_from_path
    HAS_OCR_DEPS = True
except ImportError:
    HAS_OCR_DEPS = False


def normalize_arabic_text(text: str) -> str:
    """
    Араб әріптерінің Unicode пішіндерін қалыпты таза күйге келтіреді.
    """
    if not text:
        return ""
    return unicodedata.normalize("NFKC", text)


def count_words(text: str) -> int:
    words = re.findall(r"\b\w+\b", text, flags=re.UNICODE)
    return len(words)


def clean_markdown(raw_text: str) -> str:
    text = normalize_arabic_text(raw_text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _configure_tesseract() -> None:
    if not HAS_OCR_DEPS:
        return
    default_win_path = Path(r"C:\Program Files\Tesseract-OCR\tesseract.exe")
    if default_win_path.exists():
        pytesseract.pytesseract.tesseract_cmd = str(default_win_path)


def _ocr_pdf_file(pdf_path: str, lang: str = "ara+rus+eng") -> str:
    if not HAS_OCR_DEPS:
        raise RuntimeError(
            "OCR кітапханалары орнатылмаған. Терминалда: "
            "pip install pypdf pdf2image pytesseract pillow"
        )

    _configure_tesseract()

    reader = PdfReader(pdf_path)
    num_pages = len(reader.pages)
    if num_pages == 0:
        return ""

    recognized_pages: list[str] = []
    for page_num in range(1, num_pages + 1):
        images = convert_from_path(
            pdf_path,
            dpi=200,
            first_page=page_num,
            last_page=page_num,
        )
        for img in images:
            try:
                page_text = pytesseract.image_to_string(img, lang=lang)
            except pytesseract.TesseractError:
                try:
                    page_text = pytesseract.image_to_string(img, lang="rus+eng")
                except pytesseract.TesseractError:
                    page_text = pytesseract.image_to_string(img)

            cleaned_page = clean_markdown(page_text)
            if cleaned_page:
                recognized_pages.append(f"## Бет {page_num}\n\n{cleaned_page}")

    return "\n\n".join(recognized_pages).strip()


def convert_book_to_markdown(file_path: str, md_output_path: str) -> tuple[str, int]:
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Файл табылмады: {file_path}")

    ext = os.path.splitext(file_path)[1].lower()
    raw_markdown = ""

    try:
        converter = MarkItDown()
        result = converter.convert(file_path)
        raw_markdown = getattr(result, "markdown", None) or getattr(result, "text_content", "") or ""
    except Exception:
        raw_markdown = ""

    cleaned_text = clean_markdown(raw_markdown)

    if ext == ".pdf" and count_words(cleaned_text) < 30:
        ocr_text = _ocr_pdf_file(file_path)
        if count_words(ocr_text) > count_words(cleaned_text):
            cleaned_text = ocr_text

    if not cleaned_text:
        raise ValueError(
            "Файлдан мәтін шығарылмады. Егер бұл суреттік PDF болса, "
            "Tesseract OCR орнатылғанын тексеріңіз."
        )

    os.makedirs(os.path.dirname(md_output_path), exist_ok=True)
    with open(md_output_path, "w", encoding="utf-8") as f:
        f.write(cleaned_text)

    total_words = count_words(cleaned_text)
    return cleaned_text, total_words