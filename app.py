"""PDF/HTML to Markdown web app.

Run:  python app.py
Then open http://localhost:5001 in your browser.
Upload one or more PDF or HTML files; each converted .md file is
automatically saved to your Downloads\\markdown folder, and can also be
downloaded from the page.
"""

import io
import shutil
import tempfile
import threading
import uuid
from pathlib import Path

import pymupdf
import pymupdf4llm
from flask import Flask, render_template_string, request
from bs4 import BeautifulSoup
from markdownify import markdownify

# OCR is optional: if Tesseract or the wrapper is missing, the app still runs
# (just without scanned-page support).
try:
    import pytesseract
    from PIL import Image

    _tess = shutil.which("tesseract")
    if not _tess:
        for _p in (
            r"C:\Program Files\Tesseract-OCR\tesseract.exe",
            r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
        ):
            if Path(_p).exists():
                _tess = _p
                break
    if _tess:
        pytesseract.pytesseract.tesseract_cmd = _tess
        OCR_AVAILABLE = True
    else:
        OCR_AVAILABLE = False
except Exception:
    OCR_AVAILABLE = False

# A page with fewer than this many characters of real text is treated as a
# scanned/image page and sent to OCR (when OCR is enabled).
OCR_TEXT_THRESHOLD = 20

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 100 * 1024 * 1024  # 100 MB per uploaded file

# Converted files are auto-saved here
OUTPUT_DIR = Path.home() / "Downloads" / "markdown"

# In-memory job registry for progress reporting
JOBS: dict[str, dict] = {}
JOBS_LOCK = threading.Lock()


def unique_path(directory: Path, stem: str) -> Path:
    """Return <stem>.md, or <stem> (2).md etc. if it already exists."""
    path = directory / f"{stem}.md"
    counter = 2
    while path.exists():
        path = directory / f"{stem} ({counter}).md"
        counter += 1
    return path


def ocr_page(doc: pymupdf.Document, index: int) -> str:
    """Render a page to a high-res image and read its text with Tesseract."""
    pix = doc[index].get_pixmap(dpi=300)
    img = Image.open(io.BytesIO(pix.tobytes("png")))
    text = pytesseract.image_to_string(img).strip()
    return text


def page_to_markdown(doc: pymupdf.Document, index: int, use_ocr: bool) -> tuple[str, bool]:
    """Return (markdown, ocr_used) for a single page.

    Normal pages use fast text extraction. Pages with almost no selectable
    text are treated as scanned and sent to OCR when it's enabled.
    """
    plain = doc[index].get_text().strip()
    if use_ocr and OCR_AVAILABLE and len(plain) < OCR_TEXT_THRESHOLD:
        text = ocr_page(doc, index)
        if text:
            return text + "\n\n", True
    try:
        return pymupdf4llm.to_markdown(doc, pages=[index]), False
    except Exception:
        # pymupdf4llm chokes on some table layouts (e.g. 'NoneType has no
        # attribute h_lines'); fall back to plain text for just this page.
        return plain + "\n\n", False


def save_result(job_id: str, original_name: str, markdown: str, ocr_pages: int = 0) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    saved = unique_path(OUTPUT_DIR, Path(original_name).stem)
    saved.write_text(markdown, encoding="utf-8")
    with JOBS_LOCK:
        JOBS[job_id].update(
            status="done", markdown=markdown, name=saved.stem,
            saved_to=str(saved), ocr_pages=ocr_pages,
        )


def run_html_conversion(job_id: str, tmp_path: Path, original_name: str) -> None:
    try:
        html = tmp_path.read_text(encoding="utf-8", errors="replace")
        soup = BeautifulSoup(html, "html.parser")
        for tag in soup.find_all(["title", "script", "style", "head"]):
            tag.decompose()
        markdown = markdownify(str(soup), heading_style="ATX").strip() + "\n"
        with JOBS_LOCK:
            JOBS[job_id]["total_pages"] = 1
            JOBS[job_id]["done_pages"] = 1
        save_result(job_id, original_name, markdown)
    except Exception as e:
        with JOBS_LOCK:
            JOBS[job_id].update(status="error", error=f"Could not convert this HTML file: {e}")
    finally:
        tmp_path.unlink(missing_ok=True)


def run_conversion(job_id: str, tmp_path: Path, original_name: str, use_ocr: bool) -> None:
    """Convert page by page so progress can be reported."""
    try:
        doc = pymupdf.open(tmp_path)
        total = doc.page_count
        with JOBS_LOCK:
            JOBS[job_id]["total_pages"] = total

        parts = []
        ocr_pages = 0
        for i in range(total):
            md, ocr_used = page_to_markdown(doc, i, use_ocr)
            parts.append(md)
            if ocr_used:
                ocr_pages += 1
            with JOBS_LOCK:
                JOBS[job_id]["done_pages"] = i + 1
                JOBS[job_id]["ocr_pages"] = ocr_pages
        doc.close()
        markdown = "".join(parts)
        save_result(job_id, original_name, markdown, ocr_pages)
    except Exception as e:
        with JOBS_LOCK:
            JOBS[job_id].update(status="error", error=f"Could not convert this PDF: {e}")
    finally:
        tmp_path.unlink(missing_ok=True)


PAGE = """
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>PDF to Markdown</title>
<style>
  :root {
    --bg: #f6f7fb; --card: #ffffff; --accent: #4f46e5; --accent-dark: #4338ca;
    --text: #1f2430; --muted: #6b7280; --border: #e5e7eb;
    --ok: #16a34a; --err: #b91c1c;
  }
  * { box-sizing: border-box; }
  body {
    margin: 0; font-family: "Segoe UI", system-ui, sans-serif;
    background: var(--bg); color: var(--text); min-height: 100vh;
  }
  .container { max-width: 860px; margin: 0 auto; padding: 40px 20px; }
  h1 { text-align: center; font-size: 1.9rem; margin-bottom: 6px; }
  .subtitle { text-align: center; color: var(--muted); margin-bottom: 10px; }
  .savenote { text-align: center; color: var(--muted); font-size: .85rem; margin-bottom: 28px; }
  .savenote code { background: #eef0ff; padding: 2px 6px; border-radius: 5px; }

  #dropzone {
    background: var(--card); border: 2px dashed var(--border); border-radius: 14px;
    padding: 48px 24px; text-align: center; cursor: pointer;
    transition: border-color .15s, background .15s;
  }
  #dropzone:hover, #dropzone.dragover { border-color: var(--accent); background: #eef0ff; }
  #dropzone .icon { font-size: 44px; margin-bottom: 10px; }
  #dropzone p { margin: 4px 0; }
  #dropzone .hint { color: var(--muted); font-size: .9rem; }
  #file-input { display: none; }

  #ocr-toggle {
    display: flex; align-items: center; gap: 8px; margin-top: 14px;
    font-size: .9rem; color: var(--text); cursor: pointer; justify-content: center;
  }
  #ocr-toggle input { width: 16px; height: 16px; cursor: pointer; }
  .ocr-hint { color: var(--muted); font-size: .82rem; }

  /* Overall progress bar */
  #progress-wrap { display: none; margin-top: 24px; }
  #progress-label { display: flex; justify-content: space-between; font-size: .88rem; color: var(--muted); margin-bottom: 6px; }
  #progress-track {
    height: 14px; background: var(--border); border-radius: 999px; overflow: hidden;
  }
  #progress-fill {
    height: 100%; width: 0%; background: linear-gradient(90deg, var(--accent), #818cf8);
    border-radius: 999px; transition: width .3s ease;
  }

  #results { margin-top: 24px; display: flex; flex-direction: column; gap: 12px; }
  .item {
    background: var(--card); border: 1px solid var(--border); border-radius: 12px;
    padding: 14px 18px;
  }
  .item-bar { display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 10px; }
  .item-name { font-weight: 600; }
  .item-sub { font-size: .82rem; color: var(--muted); margin-top: 3px; }
  .item-sub.saved { color: var(--ok); }
  .item-sub.failed { color: var(--err); }
  .btns { display: flex; gap: 8px; }
  button {
    font: inherit; border: none; border-radius: 8px; padding: 8px 16px;
    cursor: pointer; transition: background .15s;
  }
  .btn-primary { background: var(--accent); color: #fff; }
  .btn-primary:hover { background: var(--accent-dark); }
  .btn-secondary { background: var(--card); color: var(--text); border: 1px solid var(--border); }
  .btn-secondary:hover { background: #f0f1f5; }

  .spinner {
    display: inline-block; width: 15px; height: 15px; border: 3px solid var(--border);
    border-top-color: var(--accent); border-radius: 50%; vertical-align: -3px;
    margin-right: 6px; animation: spin .8s linear infinite;
  }
  @keyframes spin { to { transform: rotate(360deg); } }

  .preview {
    display: none; margin-top: 12px; background: var(--bg); border: 1px solid var(--border);
    border-radius: 10px; padding: 16px; max-height: 340px; overflow: auto;
    white-space: pre-wrap; font-family: Consolas, "Courier New", monospace;
    font-size: .85rem; line-height: 1.55;
  }

  #summary { display: none; text-align: center; margin-top: 20px; color: var(--muted); }
  #download-all { display: none; margin: 18px auto 0; }
</style>
</head>
<body>
<div class="container">
  <h1>PDF &rarr; Markdown</h1>
  <p class="subtitle">Upload one or many PDFs or HTML files &mdash; headings, tables and lists preserved.</p>
  <p class="savenote">Converted files are saved automatically to <code>Downloads\\markdown</code></p>

  <div id="dropzone">
    <div class="icon">&#128196;</div>
    <p><strong>Drop your PDFs or HTML files here</strong> or click to browse</p>
    <p class="hint">Select as many files as you like &middot; up to 100 MB each</p>
    <input type="file" id="file-input" accept=".pdf,application/pdf,.html,.htm,text/html" multiple>
  </div>

  <label id="ocr-toggle">
    <input type="checkbox" id="ocr-checkbox" checked>
    Use OCR for scanned / image pages
    <span class="ocr-hint">(reads text off pages that have no selectable text &mdash; slower)</span>
  </label>

  <div id="progress-wrap">
    <div id="progress-label"><span id="progress-text"></span><span id="progress-pct"></span></div>
    <div id="progress-track"><div id="progress-fill"></div></div>
  </div>

  <div id="results"></div>
  <button class="btn-primary" id="download-all">Download all (.md)</button>
  <div id="summary"></div>
</div>

<script>
const dropzone = document.getElementById("dropzone");
const fileInput = document.getElementById("file-input");
const resultsEl = document.getElementById("results");
const summaryEl = document.getElementById("summary");
const downloadAllBtn = document.getElementById("download-all");
const progressWrap = document.getElementById("progress-wrap");
const progressFill = document.getElementById("progress-fill");
const progressText = document.getElementById("progress-text");
const progressPct = document.getElementById("progress-pct");

const converted = [];   // { name, markdown }
let busy = false;

dropzone.addEventListener("click", () => fileInput.click());
fileInput.addEventListener("change", () => {
  if (fileInput.files.length) handleFiles([...fileInput.files]);
  fileInput.value = "";
});
["dragover", "dragenter"].forEach(ev =>
  dropzone.addEventListener(ev, e => { e.preventDefault(); dropzone.classList.add("dragover"); }));
["dragleave", "drop"].forEach(ev =>
  dropzone.addEventListener(ev, e => { e.preventDefault(); dropzone.classList.remove("dragover"); }));
dropzone.addEventListener("drop", e => {
  const files = [...e.dataTransfer.files];
  if (files.length) handleFiles(files);
});

function updateBar(fileIdx, totalFiles, filePart, label) {
  const overall = ((fileIdx + filePart) / totalFiles) * 100;
  progressFill.style.width = overall + "%";
  progressPct.textContent = Math.round(overall) + "%";
  progressText.textContent = label;
}

async function handleFiles(files) {
  if (busy) { alert("Please wait for the current batch to finish."); return; }
  busy = true;
  progressWrap.style.display = "block";
  let ok = 0, failed = 0;

  for (let f = 0; f < files.length; f++) {
    const file = files[f];
    const item = addItem(file.name);
    const fileLabel = files.length > 1 ? "File " + (f + 1) + " of " + files.length + ": " : "";

    const lower = file.name.toLowerCase();
    if (!lower.endsWith(".pdf") && !lower.endsWith(".html") && !lower.endsWith(".htm")) {
      setStatus(item, "failed", "Skipped - not a PDF or HTML file");
      failed++;
      updateBar(f, files.length, 1, fileLabel + file.name + " skipped");
      continue;
    }

    setStatus(item, "working", "Uploading...");
    updateBar(f, files.length, 0, fileLabel + "Uploading " + file.name + "...");

    try {
      const form = new FormData();
      form.append("file", file);
      form.append("ocr", document.getElementById("ocr-checkbox").checked ? "true" : "false");
      const resp = await fetch("/convert", { method: "POST", body: form });
      const start = await resp.json();
      if (!resp.ok) throw new Error(start.error || "Upload failed.");

      // Poll conversion progress
      let data;
      while (true) {
        await new Promise(r => setTimeout(r, 400));
        const p = await (await fetch("/progress/" + start.job)).json();
        if (p.status === "error") throw new Error(p.error);
        const done = p.done_pages || 0, total = p.total_pages || 0;
        if (total > 0) {
          const ocrNote = p.ocr_pages ? " (OCR)" : "";
          setStatus(item, "working", "Converting page " + Math.min(done + 1, total) + " of " + total + ocrNote + "...");
          updateBar(f, files.length, done / total,
            fileLabel + file.name + " - page " + done + "/" + total + ocrNote);
        }
        if (p.status === "done") { data = p; break; }
      }

      converted.push({ name: data.name, markdown: data.markdown });
      finishItem(item, data);
      ok++;
      updateBar(f, files.length, 1, fileLabel + file.name + " done");
    } catch (err) {
      setStatus(item, "failed", err.message);
      failed++;
      updateBar(f, files.length, 1, fileLabel + file.name + " failed");
    }
  }

  updateBar(files.length - 1, files.length, 1,
    "Finished: " + ok + " converted" + (failed ? ", " + failed + " failed" : ""));
  summaryEl.textContent = ok + " converted" + (failed ? ", " + failed + " failed" : "") +
    (ok ? " - saved to Downloads\\\\markdown" : "");
  summaryEl.style.display = "block";
  downloadAllBtn.style.display = converted.length > 1 ? "block" : "none";
  busy = false;
}

function addItem(name) {
  const div = document.createElement("div");
  div.className = "item";
  div.innerHTML =
    '<div class="item-bar">' +
      '<div><span class="item-name"></span><div class="item-sub"></div></div>' +
      '<div class="btns"></div>' +
    '</div><div class="preview"></div>';
  div.querySelector(".item-name").textContent = name;
  resultsEl.appendChild(div);
  return div;
}

function setStatus(item, kind, text) {
  const sub = item.querySelector(".item-sub");
  sub.className = "item-sub " + (kind === "failed" ? "failed" : kind === "saved" ? "saved" : "");
  sub.innerHTML = kind === "working" ? '<span class="spinner"></span>' : "";
  sub.appendChild(document.createTextNode(text));
}

function finishItem(item, data) {
  item.querySelector(".item-name").textContent = data.name + ".md";
  const ocrNote = data.ocr_pages ? " - OCR used on " + data.ocr_pages + " page(s)" : "";
  setStatus(item, "saved", "Saved to " + data.saved_to + ocrNote);
  const btns = item.querySelector(".btns");

  const previewBtn = document.createElement("button");
  previewBtn.className = "btn-secondary";
  previewBtn.textContent = "Preview";
  previewBtn.onclick = () => {
    const p = item.querySelector(".preview");
    const open = p.style.display === "block";
    p.style.display = open ? "none" : "block";
    previewBtn.textContent = open ? "Preview" : "Hide";
    if (!open) p.textContent = data.markdown || "(The PDF contained no extractable text.)";
  };

  const dlBtn = document.createElement("button");
  dlBtn.className = "btn-primary";
  dlBtn.textContent = "Download";
  dlBtn.onclick = () => downloadMd(data.name, data.markdown);

  btns.append(previewBtn, dlBtn);
}

function downloadMd(name, markdown) {
  const blob = new Blob([markdown], { type: "text/markdown;charset=utf-8" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = name + ".md";
  a.click();
  URL.revokeObjectURL(a.href);
}

downloadAllBtn.addEventListener("click", () => {
  converted.forEach((c, i) => setTimeout(() => downloadMd(c.name, c.markdown), i * 300));
});
</script>
</body>
</html>
"""


@app.route("/")
def index():
    return render_template_string(PAGE)


@app.route("/convert", methods=["POST"])
def convert():
    file = request.files.get("file")
    if not file or not file.filename:
        return {"error": "No file was uploaded."}, 400
    name = file.filename.lower()
    is_html = name.endswith(".html") or name.endswith(".htm")
    if not (name.endswith(".pdf") or is_html):
        return {"error": "Only PDF or HTML files are supported."}, 400

    # Stage the upload in a temp file, then convert in a background thread
    suffix = ".html" if is_html else ".pdf"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        file.save(tmp)
        tmp_path = Path(tmp.name)

    job_id = uuid.uuid4().hex
    with JOBS_LOCK:
        JOBS[job_id] = {"status": "working", "done_pages": 0, "total_pages": 0, "ocr_pages": 0}

    if is_html:
        threading.Thread(
            target=run_html_conversion, args=(job_id, tmp_path, file.filename), daemon=True
        ).start()
    else:
        use_ocr = request.form.get("ocr", "true").lower() != "false"
        threading.Thread(
            target=run_conversion, args=(job_id, tmp_path, file.filename, use_ocr), daemon=True
        ).start()
    return {"job": job_id}


@app.route("/progress/<job_id>")
def progress(job_id):
    with JOBS_LOCK:
        job = JOBS.get(job_id)
        if job is None:
            return {"status": "error", "error": "Unknown job."}, 404
        result = dict(job)
        if job["status"] in ("done", "error"):
            del JOBS[job_id]  # one-shot: final poll consumes the result
    return result


if __name__ == "__main__":
    import os

    port = int(os.environ.get("PORT", 5001))
    print(f"PDF to Markdown web app running at:  http://localhost:{port}")
    print(f"Converted files are auto-saved to:   {OUTPUT_DIR}")
    app.run(host="127.0.0.1", port=port, threaded=True)
