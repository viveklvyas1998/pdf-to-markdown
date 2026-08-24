"""PDF to Markdown converter.

Converts one or more PDF files (or all PDFs in a folder) to Markdown,
preserving headings, tables, lists, and text formatting.

Usage:
    python pdf2md.py file.pdf                    # -> file.md next to the PDF
    python pdf2md.py file1.pdf file2.pdf         # convert several at once
    python pdf2md.py C:\\some\\folder             # convert every PDF in a folder
    python pdf2md.py file.pdf -o C:\\out          # write .md files to a chosen folder
    python pdf2md.py file.pdf --images           # also extract images alongside the .md
    python pdf2md.py file.pdf --pages 1-5        # only convert pages 1 to 5
"""

import argparse
import sys
from pathlib import Path

import pymupdf4llm


def parse_page_range(spec: str, page_count: int) -> list[int]:
    """Turn '1-5', '3', or '2,4,7-9' into a list of 0-based page indices."""
    pages: list[int] = []
    for part in spec.split(","):
        part = part.strip()
        if "-" in part:
            start, end = part.split("-", 1)
            pages.extend(range(int(start) - 1, int(end)))
        else:
            pages.append(int(part) - 1)
    return [p for p in pages if 0 <= p < page_count]


def convert(pdf_path: Path, out_dir: Path | None, extract_images: bool, pages_spec: str | None) -> Path:
    kwargs = {}
    if pages_spec:
        import pymupdf
        with pymupdf.open(pdf_path) as doc:
            kwargs["pages"] = parse_page_range(pages_spec, doc.page_count)

    out_path = (out_dir or pdf_path.parent) / (pdf_path.stem + ".md")

    if extract_images:
        image_dir = out_path.parent / (pdf_path.stem + "_images")
        image_dir.mkdir(parents=True, exist_ok=True)
        kwargs.update(write_images=True, image_path=str(image_dir))

    markdown = pymupdf4llm.to_markdown(str(pdf_path), **kwargs)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(markdown, encoding="utf-8")
    return out_path


def collect_pdfs(inputs: list[str]) -> list[Path]:
    pdfs: list[Path] = []
    for item in inputs:
        path = Path(item)
        if path.is_dir():
            found = sorted(path.glob("*.pdf"))
            if not found:
                print(f"  (no PDF files found in {path})")
            pdfs.extend(found)
        elif path.suffix.lower() == ".pdf" and path.exists():
            pdfs.append(path)
        else:
            print(f"  Skipping (not a PDF or not found): {path}")
    return pdfs


def main() -> int:
    parser = argparse.ArgumentParser(description="Convert PDF files to Markdown.")
    parser.add_argument("inputs", nargs="+", help="PDF file(s) or folder(s) containing PDFs")
    parser.add_argument("-o", "--output", help="Folder to write .md files to (default: next to each PDF)")
    parser.add_argument("--images", action="store_true", help="Also extract images from the PDF")
    parser.add_argument("--pages", help="Page range to convert, e.g. 1-5 or 2,4,7-9")
    args = parser.parse_args()

    out_dir = Path(args.output) if args.output else None
    pdfs = collect_pdfs(args.inputs)
    if not pdfs:
        print("Nothing to convert.")
        return 1

    failures = 0
    for pdf in pdfs:
        print(f"Converting: {pdf.name} ...")
        try:
            out = convert(pdf, out_dir, args.images, args.pages)
            print(f"  -> {out}")
        except Exception as e:
            failures += 1
            print(f"  FAILED: {e}")

    print(f"\nDone. {len(pdfs) - failures} converted, {failures} failed.")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
