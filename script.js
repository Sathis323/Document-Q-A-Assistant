const dropzone = document.getElementById("dropzone");
const fileInput = document.getElementById("fileInput");
const dropzoneText = document.getElementById("dropzoneText");
const uploadStatus = document.getElementById("uploadStatus");
const docInfo = document.getElementById("docInfo");
const docName = document.getElementById("docName");
const docMeta = document.getElementById("docMeta");

const chat = document.getElementById("chat");
const chatEmpty = document.getElementById("chatEmpty");
const askForm = document.getElementById("askForm");
const questionInput = document.getElementById("questionInput");
const askBtn = document.getElementById("askBtn");

let currentDocumentId = null;

// ---------------------------------------------------------------------
// Upload handling
// ---------------------------------------------------------------------

fileInput.addEventListener("change", () => {
  if (fileInput.files.length > 0) {
    uploadFile(fileInput.files[0]);
  }
});

["dragover", "dragenter"].forEach((evt) => {
  dropzone.addEventListener(evt, (e) => {
    e.preventDefault();
    dropzone.classList.add("dragover");
  });
});

["dragleave", "drop"].forEach((evt) => {
  dropzone.addEventListener(evt, (e) => {
    e.preventDefault();
    dropzone.classList.remove("dragover");
  });
});

dropzone.addEventListener("drop", (e) => {
  const file = e.dataTransfer.files[0];
  if (file) uploadFile(file);
});

function setUploadStatus(message, type) {
  uploadStatus.textContent = message;
  uploadStatus.className = "status" + (type ? ` status--${type}` : "");
}

async function uploadFile(file) {
  if (!file.name.toLowerCase().endsWith(".pdf")) {
    setUploadStatus("Only PDF files are supported.", "error");
    return;
  }

  setUploadStatus("Extracting text from PDF...", "loading");
  docInfo.hidden = true;
  dropzoneText.textContent = file.name;

  const formData = new FormData();
  formData.append("file", file);

  try {
    const res = await fetch("/api/upload", { method: "POST", body: formData });
    const data = await res.json();

    if (!res.ok) {
      setUploadStatus(data.error || "Upload failed.", "error");
      return;
    }

    currentDocumentId = data.document_id;
    setUploadStatus("Document ready.", "success");

    docName.textContent = data.filename;
    docMeta.textContent = ` — ${data.char_count.toLocaleString()} characters extracted`;
    docInfo.hidden = false;

    enableChat();
    resetChat();
  } catch (err) {
    setUploadStatus("Network error while uploading.", "error");
  }
}

// ---------------------------------------------------------------------
// Chat handling
// ---------------------------------------------------------------------

function enableChat() {
  questionInput.disabled = false;
  askBtn.disabled = false;
  questionInput.focus();
}

function resetChat() {
  chat.innerHTML = "";
  addAssistantBubble(
    "Document loaded. Ask me anything about it — I'll answer strictly from its content."
  );
}

function addUserBubble(text) {
  chatEmpty.remove?.();
  const el = document.createElement("div");
  el.className = "bubble bubble--user";
  el.textContent = text;
  chat.appendChild(el);
  chat.scrollTop = chat.scrollHeight;
}

function addAssistantBubble(text) {
  const el = document.createElement("div");
  el.className = "bubble bubble--assistant";
  el.textContent = text;
  chat.appendChild(el);
  chat.scrollTop = chat.scrollHeight;
  return el;
}

function addErrorBubble(text) {
  const el = document.createElement("div");
  el.className = "bubble bubble--error";
  el.textContent = text;
  chat.appendChild(el);
  chat.scrollTop = chat.scrollHeight;
}

function addLoadingBubble() {
  const el = document.createElement("div");
  el.className = "bubble bubble--loading";
  el.textContent = "Thinking...";
  chat.appendChild(el);
  chat.scrollTop = chat.scrollHeight;
  return el;
}

askForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  const question = questionInput.value.trim();
  if (!question || !currentDocumentId) return;

  addUserBubble(question);
  questionInput.value = "";
  askBtn.disabled = true;
  questionInput.disabled = true;

  const loadingEl = addLoadingBubble();

  try {
    const res = await fetch("/api/ask", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ document_id: currentDocumentId, question }),
    });
    const data = await res.json();

    loadingEl.remove();

    if (!res.ok) {
      addErrorBubble(data.error || "Something went wrong.");
    } else {
      addAssistantBubble(data.answer);
    }
  } catch (err) {
    loadingEl.remove();
    addErrorBubble("Network error while asking the question.");
  } finally {
    askBtn.disabled = false;
    questionInput.disabled = false;
    questionInput.focus();
  }
});

// Submit on Enter (Shift+Enter for newline)
questionInput.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    askForm.requestSubmit();
  }
});
