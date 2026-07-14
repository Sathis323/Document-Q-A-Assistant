# Document Q&A Assistant

A small full-stack app that answers questions **strictly** from an uploaded PDF.
If the answer isn't in the document, it replies:
"I cannot find the answer to this question in the provided document."

## Stack
- **Backend:** Python + Flask, PyPDF2 (text extraction), Anthropic API (Claude)
- **Frontend:** Plain HTML, CSS, JavaScript (no framework, no build step)

## Project structure
```
doc-qa-app/
└── backend/
    ├── app.py                # Flask app (routes + Claude prompt logic)
    ├── requirements.txt
    ├── templates/
    │   └── index.html        # Frontend page
    ├── static/
    │   ├── style.css
    │   └── script.js
    └── uploads/               # temp storage, auto-cleaned after extraction
```

## Setup

1. Install dependencies:
   ```bash
   cd backend
   pip install -r requirements.txt
   ```

2. Set your Anthropic API key:
   ```bash
   export ANTHROPIC_API_KEY="sk-ant-..."
   ```
   (On Windows PowerShell: `$env:ANTHROPIC_API_KEY="sk-ant-..."`)

3. Run the server:
   ```bash
   python app.py
   ```

4. Open your browser at **http://localhost:5000**

## How it works

1. **Upload** — You drag/select a PDF. The backend extracts its text with
   PyPDF2 and stores it in memory, keyed by a generated `document_id`.
2. **Ask** — Your question and the extracted text are combined into a strict
   prompt (see `build_prompt()` in `app.py`) and sent to Claude:
   - Answer only from the `<source_document>` text.
   - If the answer isn't there, say so explicitly — no guessing.
   - Keep answers concise and cite the relevant section when possible.
3. The answer is returned as JSON and rendered as a chat bubble.

## Notes / things you may want to change for production
- `DOCUMENT_STORE` is an in-memory Python dict — it resets on server restart
  and won't work across multiple worker processes. Swap in Redis or a
  database for production use.
- There's no auth — anyone hitting the API can upload/ask. Add auth/session
  scoping if deploying publicly.
- Scanned/image-only PDFs won't extract text; add OCR (e.g. `pytesseract`)
  if you need to support those.
- Max upload size is capped at 20 MB (`MAX_CONTENT_LENGTH` in `app.py`).
