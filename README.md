# PDF to Markdown Converter

Converts PDF and HTML files into Markdown (`.md`) files, preserving headings, tables, lists, and bold/italic text.

## Web app (recommended)

Double-click **Start-Web-App.bat** — it opens http://localhost:5001 in your browser.
Drop one or more PDFs or HTML files onto the page (or click to browse). Every converted file is
**automatically saved to `Downloads\markdown`** — no clicking needed. Each file also
gets Preview and Download buttons on the page, plus a "Download all" button.
Runs entirely on your computer — no files leave your machine.

There is no fixed limit on how many PDFs you can upload at once — files are
converted one after another, each up to 100 MB.

Or start it manually with `python app.py`.

## Drag and drop (no browser)

Drag one or more PDF files onto **Drop-PDF-Here.bat**. Each PDF gets a `.md` file created right next to it.

## Command line

```
python pdf2md.py file.pdf                  # -> file.md next to the PDF
python pdf2md.py file1.pdf file2.pdf       # convert several at once
python pdf2md.py C:\some\folder            # convert every PDF in a folder
python pdf2md.py file.pdf -o C:\out        # save .md files to a chosen folder
python pdf2md.py file.pdf --images         # also extract images (saved to a _images folder)
python pdf2md.py file.pdf --pages 1-5      # only convert specific pages (also: 2,4,7-9)
```

## Requirements

- Python 3.10+
- `pip install pymupdf4llm markdownify beautifulsoup4` (already installed)

## Scanned pages (OCR)

The web app can read **scanned / image-only pages** using Tesseract OCR. Keep the
"Use OCR for scanned / image pages" box checked. It's smart about it: normal pages
use fast text extraction, and OCR only kicks in on pages that have no selectable
text, so regular PDFs aren't slowed down. Each result shows how many pages used OCR.

OCR requires the Tesseract program (installed at `C:\Program Files\Tesseract-OCR`)
plus `pip install pytesseract pillow`.

**Limitation:** OCR recovers *text*, not meaning from colors. A color-coded graphic
(e.g. a heatmap where yellow cells indicate a rating) will have its labels read, but
not the meaning conveyed by the shading — that needs a vision model, not OCR.

## Notes

- Works best on PDFs with real (selectable) text; scanned pages fall back to OCR.
