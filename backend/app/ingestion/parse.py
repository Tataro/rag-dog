"""Parse documents into a list of (text, page, section) blocks.

PDF: one block per page, `page` set, `section` None.
DOCX: blocks split on Heading 1/2/3, `section` carries the header path.
Markdown: split on headers, `section` carries the header path.
TXT: single block.
"""
from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True)
class Block:
    text: str
    page: int | None = None
    section: str | None = None


def parse(path: Path, mime_type: str) -> list[Block]:
    ext = path.suffix.lower()
    if ext == ".pdf" or mime_type == "application/pdf":
        blocks = _parse_pdf(path)
    elif ext == ".docx" or mime_type in {
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    }:
        blocks = _parse_docx(path)
    elif ext in {".md", ".markdown"} or mime_type == "text/markdown":
        blocks = _parse_markdown(path)
    else:
        blocks = _parse_text(path)

    # Strip NULL bytes (Postgres TEXT rejects them) and drop empty blocks.
    # pypdf sometimes emits \x00 in Thai / CJK PDF extraction.
    out: list[Block] = []
    for b in blocks:
        text = _clean(b.text)
        if not text:
            continue
        out.append(Block(text=text, page=b.page, section=_clean(b.section) if b.section else None))
    return out


def _clean(s: str) -> str:
    # \x00 breaks Postgres; other ASCII control chars (except tab/newline/CR)
    # are noise from broken PDF extraction.
    s = s.replace("\x00", "")
    return "".join(c for c in s if c >= " " or c in "\t\n\r").strip()


def _parse_pdf(path: Path) -> list[Block]:
    from pypdf import PdfReader

    reader = PdfReader(str(path))
    blocks: list[Block] = []
    for i, page in enumerate(reader.pages, start=1):
        text = (page.extract_text() or "").strip()
        if text:
            blocks.append(Block(text=text, page=i))
    return blocks


def _parse_docx(path: Path) -> list[Block]:
    import docx  # python-docx

    doc = docx.Document(str(path))
    blocks: list[Block] = []
    header_stack: list[str] = []
    buf: list[str] = []

    def flush() -> None:
        if buf:
            blocks.append(Block(text="\n".join(buf).strip(), section=" / ".join(header_stack) or None))
            buf.clear()

    for para in doc.paragraphs:
        style = (para.style.name or "").lower()
        text = para.text.strip()
        if not text:
            continue
        if style.startswith("heading"):
            flush()
            # heading level: "heading 1" -> 1
            try:
                level = int(style.split()[-1])
            except ValueError:
                level = 1
            header_stack[:] = header_stack[: level - 1] + [text]
            continue
        buf.append(text)
    flush()
    return blocks


def _parse_markdown(path: Path) -> list[Block]:
    blocks: list[Block] = []
    header_stack: list[str] = []
    buf: list[str] = []

    def flush() -> None:
        if buf:
            blocks.append(Block(text="\n".join(buf).strip(), section=" / ".join(header_stack) or None))
            buf.clear()

    in_code = False
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.rstrip()
        if line.startswith("```"):
            in_code = not in_code
            buf.append(raw)
            continue
        if not in_code and line.startswith("#"):
            # ATX header
            level = len(line) - len(line.lstrip("#"))
            title = line[level:].strip()
            flush()
            header_stack[:] = header_stack[: level - 1] + [title]
            continue
        buf.append(raw)
    flush()
    return blocks


def _parse_text(path: Path) -> list[Block]:
    text = path.read_text(encoding="utf-8", errors="replace").strip()
    return [Block(text=text)] if text else []
