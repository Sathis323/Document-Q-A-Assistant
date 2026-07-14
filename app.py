

import os
import uuid
import traceback

from dotenv import load_dotenv
from flask import Flask, request, jsonify, render_template, session
from werkzeug.utils import secure_filename
from PyPDF2 import PdfReader
from groq import Groq

# Load variables from a .env file (if present) into the environment.
load_dotenv()

# --------------------------------------------------------------------------
# App / client setup
# --------------------------------------------------------------------------

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "dev-secret-change-me")

UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), "uploads")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
app.config["MAX_CONTENT_LENGTH"] = 20 * 1024 * 1024  # 20 MB upload limit

GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
client = None

if GROQ_API_KEY:
    try:
        client = Groq(api_key=GROQ_API_KEY)
    except Exception as e:
        # Don't let a bad SDK/version combo crash the whole server.
        # The app will fall back to offline keyword-matching mode instead.
        print(f"[warning] Could not initialize Groq client: {e}")
        client = None

# Groq-hosted model. See https://console.groq.com/docs/models for current options.
MODEL_NAME = "llama-3.3-70b-versatile"

# In-memory store mapping document_id -> extracted text.
# For a production app, replace with a real database or cache (e.g. Redis).
DOCUMENT_STORE = {}


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------

def extract_pdf_text(filepath: str) -> str:
    """Extract all text from a PDF file, page by page."""
    reader = PdfReader(filepath)
    pages_text = []
    for i, page in enumerate(reader.pages, start=1):
        text = page.extract_text() or ""
        pages_text.append(f"--- Page {i} ---\n{text.strip()}")
    return "\n\n".join(pages_text).strip()


def build_prompt(source_document: str, user_question: str) -> str:
    """Build the strict research-assistant prompt."""
    return f"""You are an expert research assistant. Your task is to answer the
user's question accurately, using only the provided source document.

<source_document>
{source_document}
</source_document>

User Question: {user_question}

Instructions:
1. Base your answer strictly on the text provided inside the <source_document> tags.
2. If the answer cannot be found in the document, reply with: "I cannot find the
   answer to this question in the provided document." Do not try to make up
   information or use external knowledge.
3. Keep your answer concise, objective, and directly relevant to the question.
4. If applicable, cite the specific section or context from the document where
   you found the answer.
"""


def ask_groq(source_document: str, user_question: str) -> str:
    """Send the strict prompt to Groq and return its answer."""
    if client is None:
        raise RuntimeError(
            "GROQ_API_KEY is not set. Set it as an environment variable "
            "before starting the server."
        )

    prompt = build_prompt(source_document, user_question)

    response = client.chat.completions.create(
        model=MODEL_NAME,
        max_tokens=1024,
        temperature=0.2,
        messages=[{"role": "user", "content": prompt}],
    )

    return response.choices[0].message.content.strip()


# --------------------------------------------------------------------------
# Offline fallback (no API key required)
# --------------------------------------------------------------------------
# This is a simple keyword-overlap search, NOT an LLM. It splits the document
# into sentences, scores each one by how many question words it shares, and
# returns the best-matching passage(s). It exists so you can test the whole
# upload -> ask -> answer flow before you have a Groq API key.

import re

STOPWORDS = {
    "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
    "of", "in", "on", "at", "to", "for", "and", "or", "but", "with",
    "what", "when", "where", "who", "whom", "which", "how", "why", "does",
    "do", "did", "this", "that", "these", "those", "it", "its", "as", "by",
    "from", "about", "into", "than", "then", "there", "their", "can",
}


def _tokenize(text: str) -> set:
    words = re.findall(r"[a-zA-Z0-9']+", text.lower())
    return {w for w in words if w not in STOPWORDS and len(w) > 1}


def ask_offline(source_document: str, user_question: str) -> str:
    """Fallback answer using simple keyword/sentence overlap (no API needed)."""
    question_words = _tokenize(user_question)
    if not question_words:
        return "I cannot find the answer to this question in the provided document."

    # Split into rough sentences while keeping some context.
    sentences = re.split(r"(?<=[.!?])\s+", source_document.replace("\n", " "))
    sentences = [s.strip() for s in sentences if s.strip()]

    scored = []
    for s in sentences:
        s_words = _tokenize(s)
        if not s_words:
            continue
        overlap = len(question_words & s_words)
        if overlap > 0:
            scored.append((overlap, s))

    if not scored:
        return "I cannot find the answer to this question in the provided document."

    scored.sort(key=lambda x: x[0], reverse=True)
    top_sentences = [s for _, s in scored[:3]]

    answer = " ".join(top_sentences)
    if len(answer) > 800:
        answer = answer[:800].rsplit(" ", 1)[0] + "..."

    return (
        f"{answer}\n\n"
        "(Offline mode: this is a keyword-matched excerpt from the document, "
        "not an AI-generated answer. Add a GROQ_API_KEY for full "
        "natural-language answers.)"
    )


# --------------------------------------------------------------------------
# Routes
# --------------------------------------------------------------------------

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/upload", methods=["POST"])
def upload_document():
    """Accept a PDF upload, extract its text, and store it server-side."""
    if "file" not in request.files:
        return jsonify({"error": "No file part in the request."}), 400

    file = request.files["file"]
    if file.filename == "":
        return jsonify({"error": "No file selected."}), 400

    if not file.filename.lower().endswith(".pdf"):
        return jsonify({"error": "Only PDF files are supported."}), 400

    filename = secure_filename(file.filename)
    doc_id = uuid.uuid4().hex
    saved_path = os.path.join(app.config["UPLOAD_FOLDER"], f"{doc_id}_{filename}")

    try:
        file.save(saved_path)
        text = extract_pdf_text(saved_path)

        if not text:
            return jsonify({
                "error": "No extractable text found in this PDF. "
                         "It may be a scanned/image-only document."
            }), 422

        DOCUMENT_STORE[doc_id] = {"filename": filename, "text": text}

        return jsonify({
            "document_id": doc_id,
            "filename": filename,
            "char_count": len(text),
            "preview": text[:500],
        })
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": f"Failed to process PDF: {str(e)}"}), 500
    finally:
        # Clean up the raw uploaded file; we only need the extracted text.
        if os.path.exists(saved_path):
            os.remove(saved_path)


@app.route("/api/ask", methods=["POST"])
def ask_question():
    """Answer a question strictly from a previously uploaded document."""
    data = request.get_json(silent=True) or {}
    doc_id = data.get("document_id")
    question = (data.get("question") or "").strip()

    if not doc_id or doc_id not in DOCUMENT_STORE:
        return jsonify({"error": "Document not found. Please upload a PDF first."}), 404

    if not question:
        return jsonify({"error": "Question cannot be empty."}), 400

    source_document = DOCUMENT_STORE[doc_id]["text"]

    try:
        if client is not None:
            answer = ask_groq(source_document, question)
            mode = "ai"
        else:
            answer = ask_offline(source_document, question)
            mode = "offline"
        return jsonify({"answer": answer, "mode": mode})
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": f"Failed to get an answer: {str(e)}"}), 500


@app.route("/api/health")
def health():
    return jsonify({
        "status": "ok",
        "api_key_configured": client is not None,
        "documents_in_memory": len(DOCUMENT_STORE),
    })


if __name__ == "__main__":
    app.run(debug=True, port=5000)
