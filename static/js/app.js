// PDF Toolbox Client Application

let currentFile = null;
let currentLocalFilename = null;
let mergeFiles = [];
let ocrFiles = [];
let ocrObjectUrls = [];
let lastExtractedOcrText = "";
let pollInterval = null;
let ocrPollInterval = null;
let copyFeedbackTimer = null;
let lastCopyStatusMessage = "";

// Core DOM Elements
const dropzone = document.getElementById("dropzone");
const fileInput = document.getElementById("fileInput");
const selectedFileBar = document.getElementById("selectedFileBar");
const selectedFileName = document.getElementById("selectedFileName");
const selectedFileSize = document.getElementById("selectedFileSize");
const progressSection = document.getElementById("progressSection");
const progressBar = document.getElementById("progressBar");
const progressTitle = document.getElementById("progressTitle");
const progressPercentage = document.getElementById("progressPercentage");
const progressStatusMsg = document.getElementById("progressStatusMsg");
const resultSection = document.getElementById("resultSection");
const resultHeading = document.getElementById("resultHeading");
const resultHeadingText = document.getElementById("resultHeadingText");
const errorBox = document.getElementById("errorBox");
const srStatus = document.getElementById("srStatus");

// ==========================================
// 1. TABS & KEYBOARD NAVIGATION (Roving Tabindex)
// ==========================================
const tabButtons = Array.from(document.querySelectorAll('.tab-btn[role="tab"]'));
const tabPanels = Array.from(document.querySelectorAll('.tab-content[role="tabpanel"]'));

function activateTab(tabBtn, focusTab = false) {
  const tabName = tabBtn.dataset.tab;

  tabButtons.forEach((btn) => {
    const isSelected = btn === tabBtn;
    btn.setAttribute("aria-selected", isSelected ? "true" : "false");
    btn.tabIndex = isSelected ? 0 : -1;
  });

  tabPanels.forEach((panel) => {
    panel.hidden = panel.id !== `tab-${tabName}`;
  });

  const singleFileSection = document.getElementById("singleFileSection");
  if (singleFileSection) {
    singleFileSection.hidden = tabName === "merge" || tabName === "webpdf" || tabName === "ocr";
  }

  tabBtn.scrollIntoView({ block: "nearest", inline: "nearest", container: "nearest" });
  if (focusTab) {
    tabBtn.focus();
  }

  clearError();
  hideResult();
  resetMetricLabels();
}

tabButtons.forEach((btn, idx) => {
  btn.addEventListener("click", () => activateTab(btn, false));
  btn.addEventListener("keydown", (e) => {
    let targetIdx = null;
    if (e.key === "ArrowRight") targetIdx = (idx + 1) % tabButtons.length;
    else if (e.key === "ArrowLeft") targetIdx = (idx - 1 + tabButtons.length) % tabButtons.length;
    else if (e.key === "Home") targetIdx = 0;
    else if (e.key === "End") targetIdx = tabButtons.length - 1;

    if (targetIdx !== null) {
      e.preventDefault();
      activateTab(tabButtons[targetIdx], true);
    }
  });
});

function resetMetricLabels() {
  const metricLabels = document.querySelectorAll("#metricsGrid .metric-label");
  if (metricLabels.length >= 4) {
    metricLabels[0].textContent = "Original Size";
    metricLabels[1].textContent = "Final Size";
    metricLabels[2].textContent = "Space Saved";
    metricLabels[3].textContent = "Elapsed Time";
  }
}

// ==========================================
// 2. SINGLE-FILE SELECTOR & LOCAL BANNER
// ==========================================
document.querySelectorAll(".js-select-local").forEach((btn) => {
  btn.addEventListener("click", () => {
    selectLocalFile(btn.dataset.filename, btn.dataset.size);
  });
});

const btnClearSelectedFile = document.getElementById("btnClearSelectedFile");
if (btnClearSelectedFile) {
  btnClearSelectedFile.addEventListener("click", clearSelectedFile);
}

if (dropzone && fileInput) {
  dropzone.addEventListener("click", () => fileInput.click());
  dropzone.addEventListener("dragover", (e) => {
    e.preventDefault();
    dropzone.classList.add("dragover");
  });
  dropzone.addEventListener("dragleave", () => dropzone.classList.remove("dragover"));
  dropzone.addEventListener("drop", (e) => {
    e.preventDefault();
    dropzone.classList.remove("dragover");
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      handleFileChosen(e.dataTransfer.files[0]);
    }
  });

  fileInput.addEventListener("change", (e) => {
    if (e.target.files && e.target.files.length > 0) {
      handleFileChosen(e.target.files[0]);
    }
  });
}

function handleFileChosen(file) {
  if (!file.name.toLowerCase().endsWith(".pdf")) {
    showError("Please select a valid .pdf file.");
    return;
  }
  currentFile = file;
  currentLocalFilename = null;

  selectedFileName.textContent = file.name;
  selectedFileSize.textContent = `(${formatBytes(file.size)})`;
  selectedFileBar.hidden = false;
  dropzone.hidden = true;
  clearError();
}

function selectLocalFile(filename, sizeFormatted) {
  currentFile = null;
  currentLocalFilename = filename;

  selectedFileName.textContent = filename;
  selectedFileSize.textContent = `(${sizeFormatted} · local)`;
  selectedFileBar.hidden = false;
  dropzone.hidden = true;
  clearError();

  const tabBar = document.querySelector(".tabs");
  if (tabBar) {
    tabBar.scrollIntoView({ behavior: "smooth" });
  }
}

function clearSelectedFile() {
  currentFile = null;
  currentLocalFilename = null;
  if (fileInput) fileInput.value = "";
  selectedFileBar.hidden = true;
  dropzone.hidden = false;
}

// ==========================================
// 3. HELPERS
// ==========================================
function getRadioValue(name, fallback) {
  const checked = document.querySelector(`input[name="${name}"]:checked`);
  return checked ? checked.value : fallback;
}

function getActiveFormData() {
  const fd = new FormData();
  if (currentLocalFilename) {
    fd.append("local_filename", currentLocalFilename);
  } else if (currentFile) {
    fd.append("file", currentFile);
  } else {
    showError("Please select or drop a PDF file first.");
    return null;
  }
  return fd;
}

function announceStatus(message) {
  if (!srStatus) return;
  srStatus.textContent = "";
  requestAnimationFrame(() => {
    srStatus.textContent = message;
  });
}

function showError(msg) {
  errorBox.textContent = msg;
  errorBox.hidden = false;
}

function clearError() {
  errorBox.textContent = "";
  errorBox.hidden = true;
}

function showProgress(title, percent, msg) {
  progressSection.hidden = false;
  progressTitle.textContent = title;
  progressPercentage.textContent = `${percent}%`;
  progressBar.value = percent;
  progressStatusMsg.textContent = msg;
}

function hideProgress() {
  progressSection.hidden = true;
}

function hideResult() {
  resultSection.hidden = true;
  const ocrExtraActions = document.getElementById("ocrExtraActions");
  if (ocrExtraActions) ocrExtraActions.hidden = true;
  const ocrTextPreviewBox = document.getElementById("ocrTextPreviewBox");
  if (ocrTextPreviewBox) ocrTextPreviewBox.hidden = true;
}

function revealResult(headingMsg) {
  resultHeadingText.textContent = headingMsg;
  resultSection.hidden = false;
  announceStatus(headingMsg);
  resultSection.scrollIntoView({ behavior: "smooth" });
}

function formatBytes(bytes) {
  if (bytes <= 0) return "0 B";
  const units = ["B", "KB", "MB", "GB"];
  let i = 0;
  let val = bytes;
  while (val >= 1024 && i < units.length - 1) {
    val /= 1024;
    i++;
  }
  return `${val.toFixed(2)} ${units[i]}`;
}

function escapeHtml(text) {
  const div = document.createElement("div");
  div.textContent = String(text ?? "");
  return div.innerHTML;
}

// ==========================================
// 4. COMPRESS PDF
// ==========================================
const btnCompress = document.getElementById("btnCompress");
if (btnCompress) {
  btnCompress.addEventListener("click", handleCompress);
}

async function handleCompress() {
  clearError();
  hideResult();

  const fd = getActiveFormData();
  if (!fd) return;

  const preset = getRadioValue("compressPreset", "screen");
  const toGrayscale = document.getElementById("chkGrayscale").checked;
  fd.append("preset", preset);
  fd.append("to_grayscale", toGrayscale ? "true" : "false");

  btnCompress.disabled = true;
  showProgress("Starting compression", 5, "Sending document to optimization engine...");

  try {
    const res = await fetch("/api/compress", { method: "POST", body: fd });
    const data = await res.json();

    if (!res.ok) {
      throw new Error(data.detail || "Failed to start compression job.");
    }

    pollCompressionTask(data.task_id);
  } catch (err) {
    btnCompress.disabled = false;
    hideProgress();
    showError(err.message);
  }
}

function pollCompressionTask(taskId) {
  if (pollInterval) clearInterval(pollInterval);

  pollInterval = setInterval(async () => {
    try {
      const res = await fetch(`/api/tasks/${taskId}`);
      const task = await res.json();

      if (!res.ok) {
        clearInterval(pollInterval);
        btnCompress.disabled = false;
        hideProgress();
        showError("Failed to query compression task status.");
        return;
      }

      showProgress("Compressing PDF...", task.progress, task.message);

      if (task.status === "completed") {
        clearInterval(pollInterval);
        btnCompress.disabled = false;
        hideProgress();
        showCompressionResult(task.result);
      } else if (task.status === "failed") {
        clearInterval(pollInterval);
        btnCompress.disabled = false;
        hideProgress();
        showError(task.message || "Compression failed.");
      }
    } catch {
      clearInterval(pollInterval);
      btnCompress.disabled = false;
      hideProgress();
      showError("Network error while checking compression progress.");
    }
  }, 750);
}

function showCompressionResult(res) {
  resetMetricLabels();
  document.getElementById("resOrigSize").textContent = res.original_size_formatted;
  document.getElementById("resCompSize").textContent = res.compressed_size_formatted;
  document.getElementById("resSaved").textContent = `-${res.saved_percentage}% (${res.saved_bytes_formatted})`;
  document.getElementById("resDuration").textContent = `${res.duration_seconds}s`;

  const btnDl = document.getElementById("btnDownloadLink");
  btnDl.href = `/api/download/${encodeURIComponent(res.filename)}`;
  btnDl.textContent = `Download Compressed PDF (${res.compressed_size_formatted})`;

  revealResult("PDF compressed successfully!");
}

// ==========================================
// 5. SPLIT / EXTRACT PAGES
// ==========================================
const btnSplit = document.getElementById("btnSplit");
if (btnSplit) {
  btnSplit.addEventListener("click", handleSplit);
}

async function handleSplit() {
  clearError();
  hideResult();

  const fd = getActiveFormData();
  if (!fd) return;

  const ranges = document.getElementById("pageRanges").value.trim();
  if (!ranges) {
    showError("Please enter page numbers or ranges to extract (e.g., 1-5, 8).");
    document.getElementById("pageRanges").focus();
    return;
  }
  fd.append("page_ranges", ranges);

  btnSplit.disabled = true;
  showProgress("Extracting pages", 50, "Building a new PDF with the selected pages...");

  try {
    const res = await fetch("/api/split", { method: "POST", body: fd });
    const data = await res.json();
    hideProgress();
    btnSplit.disabled = false;

    if (!res.ok) throw new Error(data.detail || "Failed to extract pages.");

    resetMetricLabels();
    document.getElementById("resOrigSize").textContent = "-";
    document.getElementById("resCompSize").textContent = data.size_formatted;
    document.getElementById("resSaved").textContent = `${data.extracted_pages} page(s)`;
    document.getElementById("resDuration").textContent = "Instant";

    const btnDl = document.getElementById("btnDownloadLink");
    btnDl.href = `/api/download/${encodeURIComponent(data.filename)}`;
    btnDl.textContent = `Download Extracted PDF (${data.size_formatted})`;

    revealResult(`Pages extracted (${data.extracted_pages} pages)!`);
  } catch (err) {
    btnSplit.disabled = false;
    hideProgress();
    showError(err.message);
  }
}

// ==========================================
// 6. MERGE MULTIPLE PDFS
// ==========================================
const mergeDropzone = document.getElementById("mergeDropzone");
const mergeFileInput = document.getElementById("mergeFileInput");
const mergeFileList = document.getElementById("mergeFileList");
const btnMerge = document.getElementById("btnMerge");

if (mergeDropzone && mergeFileInput) {
  mergeDropzone.addEventListener("click", () => mergeFileInput.click());
  mergeDropzone.addEventListener("dragover", (e) => {
    e.preventDefault();
    mergeDropzone.classList.add("dragover");
  });
  mergeDropzone.addEventListener("dragleave", () => mergeDropzone.classList.remove("dragover"));
  mergeDropzone.addEventListener("drop", (e) => {
    e.preventDefault();
    mergeDropzone.classList.remove("dragover");
    if (e.dataTransfer.files) {
      addMergeFiles(Array.from(e.dataTransfer.files));
    }
  });

  mergeFileInput.addEventListener("change", (e) => {
    if (e.target.files) {
      addMergeFiles(Array.from(e.target.files));
      mergeFileInput.value = "";
    }
  });
}

if (mergeFileList) {
  mergeFileList.addEventListener("click", (e) => {
    const removeBtn = e.target.closest("button[data-remove-merge-idx]");
    if (!removeBtn) return;
    const idx = parseInt(removeBtn.dataset.removeMergeIdx, 10);
    if (!Number.isNaN(idx)) {
      mergeFiles.splice(idx, 1);
      renderMergeList();
    }
  });
}

if (btnMerge) {
  btnMerge.addEventListener("click", handleMerge);
}

function addMergeFiles(files) {
  const pdfs = files.filter((f) => f.name.toLowerCase().endsWith(".pdf"));
  if (pdfs.length === 0) {
    showError("Please select valid .pdf files to merge.");
    return;
  }
  mergeFiles = [...mergeFiles, ...pdfs];
  clearError();
  renderMergeList();
}

function renderMergeList() {
  if (!mergeFileList) return;
  mergeFileList.innerHTML = "";
  if (mergeFiles.length === 0) {
    btnMerge.disabled = true;
    return;
  }

  mergeFiles.forEach((file, idx) => {
    const item = document.createElement("div");
    item.className = "selected-file-indicator";
    item.style.marginBottom = "0.5rem";

    const info = document.createElement("div");
    info.innerHTML = `
      <span style="font-size:0.75rem; color:var(--text-muted); margin-right:0.5rem;">#${idx + 1}</span>
      <span class="file-name-text">${escapeHtml(file.name)}</span>
      <span class="file-meta-text">(${formatBytes(file.size)})</span>
    `;

    const rmBtn = document.createElement("button");
    rmBtn.type = "button";
    rmBtn.className = "btn-clear";
    rmBtn.dataset.removeMergeIdx = String(idx);
    rmBtn.setAttribute("aria-label", `Remove ${file.name}`);
    rmBtn.innerHTML = "&times;";

    item.appendChild(info);
    item.appendChild(rmBtn);
    mergeFileList.appendChild(item);
  });

  btnMerge.disabled = mergeFiles.length < 2;
}

async function handleMerge() {
  clearError();
  hideResult();

  if (mergeFiles.length < 2) {
    showError("Please select at least two PDF files.");
    return;
  }

  const fd = new FormData();
  mergeFiles.forEach((f) => fd.append("files", f));

  btnMerge.disabled = true;
  showProgress("Merging PDFs", 50, "Combining documents and optimizing page references...");

  try {
    const res = await fetch("/api/merge", { method: "POST", body: fd });
    const data = await res.json();
    hideProgress();
    btnMerge.disabled = mergeFiles.length < 2;

    if (!res.ok) throw new Error(data.detail || "Failed to merge PDFs.");

    resetMetricLabels();
    document.getElementById("resOrigSize").textContent = "-";
    document.getElementById("resCompSize").textContent = data.size_formatted;
    document.getElementById("resSaved").textContent = `${data.total_pages} page(s)`;
    document.getElementById("resDuration").textContent = "Instant";

    const btnDl = document.getElementById("btnDownloadLink");
    btnDl.href = `/api/download/${encodeURIComponent(data.filename)}`;
    btnDl.textContent = `Download Merged PDF (${data.size_formatted})`;

    revealResult(`PDFs merged successfully (${data.total_pages} pages)!`);
  } catch (err) {
    btnMerge.disabled = mergeFiles.length < 2;
    hideProgress();
    showError(err.message);
  }
}

// ==========================================
// 7. ROTATE PAGES
// ==========================================
const btnRotate = document.getElementById("btnRotate");
if (btnRotate) {
  btnRotate.addEventListener("click", handleRotate);
}

async function handleRotate() {
  clearError();
  hideResult();

  const fd = getActiveFormData();
  if (!fd) return;

  const angle = getRadioValue("rotateAngle", "90");
  const ranges = document.getElementById("rotateRanges").value.trim();
  fd.append("angle", angle);
  if (ranges) fd.append("page_ranges", ranges);

  btnRotate.disabled = true;
  showProgress("Rotating pages", 50, `Applying ${angle}° rotation...`);

  try {
    const res = await fetch("/api/rotate", { method: "POST", body: fd });
    const data = await res.json();
    hideProgress();
    btnRotate.disabled = false;

    if (!res.ok) throw new Error(data.detail || "Failed to rotate pages.");

    resetMetricLabels();
    document.getElementById("resOrigSize").textContent = "-";
    document.getElementById("resCompSize").textContent = data.size_formatted;
    document.getElementById("resSaved").textContent = `${data.rotated_pages_count} page(s) rotated`;
    document.getElementById("resDuration").textContent = "Instant";

    const btnDl = document.getElementById("btnDownloadLink");
    btnDl.href = `/api/download/${encodeURIComponent(data.filename)}`;
    btnDl.textContent = `Download Rotated PDF (${data.size_formatted})`;

    revealResult(`Pages rotated (${data.angle}°)!`);
  } catch (err) {
    btnRotate.disabled = false;
    hideProgress();
    showError(err.message);
  }
}

// ==========================================
// 8. INSPECT & EDIT METADATA
// ==========================================
const btnInspect = document.getElementById("btnInspect");
if (btnInspect) {
  btnInspect.addEventListener("click", handleInspect);
}

async function handleInspect() {
  clearError();
  hideResult();

  const container = document.getElementById("inspectResultContainer");
  container.innerHTML = "";

  const fd = getActiveFormData();
  if (!fd) return;

  btnInspect.disabled = true;
  showProgress("Inspecting PDF", 50, "Reading metadata, dimensions, and page structure...");

  try {
    const res = await fetch("/api/inspect", { method: "POST", body: fd });
    const data = await res.json();
    hideProgress();
    btnInspect.disabled = false;

    if (!res.ok) throw new Error(data.detail || "Failed to inspect PDF.");

    const meta = data.metadata || {};
    const titleVal = meta.title && meta.title !== "Untitled" ? meta.title : "";
    const authorVal = meta.author && meta.author !== "Not specified" ? meta.author : "";

    container.innerHTML = `
      <div class="table-scroll">
        <table class="info-table">
          <caption class="visually-hidden">Technical details and metadata for ${escapeHtml(data.filename)}</caption>
          <tbody>
            <tr><th scope="row">Filename</th><td>${escapeHtml(data.filename)}</td></tr>
            <tr><th scope="row">File Size</th><td>${escapeHtml(data.filesize_formatted)} (${data.filesize_bytes.toLocaleString()} bytes)</td></tr>
            <tr><th scope="row">Total Pages</th><td><strong>${data.pages}</strong></td></tr>
            <tr><th scope="row">Page Dimensions</th><td>${escapeHtml(data.dimensions)}</td></tr>
            <tr><th scope="row">Title</th><td>${escapeHtml(meta.title)}</td></tr>
            <tr><th scope="row">Author</th><td>${escapeHtml(meta.author)}</td></tr>
            <tr><th scope="row">Creator Application</th><td>${escapeHtml(meta.creator)}</td></tr>
            <tr><th scope="row">PDF Producer</th><td>${escapeHtml(meta.producer)}</td></tr>
            <tr><th scope="row">Creation Date</th><td>${escapeHtml(meta.creation_date)}</td></tr>
            <tr><th scope="row">Images (Sampled)</th><td>${data.sample_images_first_pages} images across first ${data.sample_pages_checked} page(s)</td></tr>
            <tr><th scope="row">Encrypted / Protected</th><td>${data.is_encrypted ? "Yes" : "No"}</td></tr>
          </tbody>
        </table>
      </div>

      <form id="editMetadataForm" class="meta-edit-box" novalidate>
        <h3 class="meta-edit-heading">Edit PDF Metadata (for Zotero)</h3>
        <div class="meta-grid-two">
          <div>
            <label class="meta-field-label" for="editMetaTitle">Title</label>
            <input type="text" id="editMetaTitle" class="input-text" value="${escapeHtml(titleVal)}">
          </div>
          <div>
            <label class="meta-field-label" for="editMetaAuthor">Author</label>
            <input type="text" id="editMetaAuthor" class="input-text" value="${escapeHtml(authorVal)}">
          </div>
        </div>
        <div class="meta-grid-two">
          <div>
            <label class="meta-field-label" for="editMetaSubject">Subject</label>
            <input type="text" id="editMetaSubject" class="input-text" value="${escapeHtml(meta.subject || "")}">
          </div>
          <div>
            <label class="meta-field-label" for="editMetaKeywords">Keywords</label>
            <input type="text" id="editMetaKeywords" class="input-text" value="${escapeHtml(meta.keywords || "")}">
          </div>
        </div>
        <button type="submit" class="btn-primary" id="btnSaveMetadata" style="font-size: 0.85rem; padding: 0.55rem 1.1rem;">
          Save &amp; Download with Updated Metadata
        </button>
      </form>
    `;

    const editForm = document.getElementById("editMetadataForm");
    if (editForm) {
      editForm.addEventListener("submit", (e) => {
        e.preventDefault();
        handleSaveMetadata();
      });
    }

    announceStatus(`Inspection complete: ${data.pages} pages in ${data.filename}`);
  } catch (err) {
    btnInspect.disabled = false;
    hideProgress();
    showError(err.message);
  }
}

async function handleSaveMetadata() {
  clearError();
  const fd = getActiveFormData();
  if (!fd) return;

  const titleEl = document.getElementById("editMetaTitle");
  const authorEl = document.getElementById("editMetaAuthor");
  const subjectEl = document.getElementById("editMetaSubject");
  const keywordsEl = document.getElementById("editMetaKeywords");

  fd.append("title", titleEl ? titleEl.value.trim() : "");
  fd.append("author", authorEl ? authorEl.value.trim() : "");
  fd.append("subject", subjectEl ? subjectEl.value.trim() : "");
  fd.append("keywords", keywordsEl ? keywordsEl.value.trim() : "");

  const saveBtn = document.getElementById("btnSaveMetadata");
  if (saveBtn) saveBtn.disabled = true;
  showProgress("Updating metadata", 50, "Writing updated title, author, and keywords to PDF...");

  try {
    const res = await fetch("/api/update-metadata", { method: "POST", body: fd });
    const data = await res.json();
    hideProgress();
    if (saveBtn) saveBtn.disabled = false;

    if (!res.ok) throw new Error(data.detail || "Failed to update PDF metadata.");

    document.getElementById("resOrigSize").textContent = data.author || "Not specified";
    document.getElementById("resCompSize").textContent = data.size_formatted;
    document.getElementById("resSaved").textContent = data.title || "Updated PDF";
    document.getElementById("resDuration").textContent = "Instant";

    const metricLabels = document.querySelectorAll("#metricsGrid .metric-label");
    if (metricLabels.length >= 4) {
      metricLabels[0].textContent = "Author";
      metricLabels[1].textContent = "File Size";
      metricLabels[2].textContent = "Title";
      metricLabels[3].textContent = "Status";
    }

    const btnDl = document.getElementById("btnDownloadLink");
    btnDl.href = `/api/download/${encodeURIComponent(data.filename)}`;
    btnDl.textContent = `Download Updated PDF (${data.size_formatted})`;

    revealResult("PDF metadata updated successfully!");
  } catch (err) {
    if (saveBtn) saveBtn.disabled = false;
    hideProgress();
    showError(err.message);
  }
}

// ==========================================
// 9. WEB TO PDF (ZOTERO)
// ==========================================
const webUrlInput = document.getElementById("webUrlInput");
const btnDetectMeta = document.getElementById("btnDetectMeta");
const btnWebToPdf = document.getElementById("btnWebToPdf");

document.querySelectorAll("button[data-sample-url]").forEach((btn) => {
  btn.addEventListener("click", () => {
    if (webUrlInput) {
      webUrlInput.value = btn.dataset.sampleUrl || "";
      detectUrlMetadata();
    }
  });
});

if (webUrlInput) {
  webUrlInput.addEventListener("change", detectUrlMetadata);
}

if (btnDetectMeta) {
  btnDetectMeta.addEventListener("click", detectUrlMetadata);
}

document.querySelectorAll('input[name="webMode"]').forEach((radio) => {
  radio.addEventListener("change", () => {
    const readerOpts = document.getElementById("readerOptions");
    if (readerOpts) {
      readerOpts.hidden = getRadioValue("webMode", "reader") === "fullpage";
    }
  });
});

if (btnWebToPdf) {
  btnWebToPdf.addEventListener("click", handleWebToPdf);
}

async function detectUrlMetadata() {
  const url = webUrlInput ? webUrlInput.value.trim() : "";
  if (!url || (!url.startsWith("http://") && !url.startsWith("https://"))) return;

  const origBtnText = btnDetectMeta ? btnDetectMeta.textContent : "";
  if (btnDetectMeta) {
    btnDetectMeta.disabled = true;
    btnDetectMeta.textContent = "Detecting...";
  }

  try {
    const fd = new FormData();
    fd.append("url", url);
    const res = await fetch("/api/web-metadata", { method: "POST", body: fd });
    if (res.ok) {
      const data = await res.json();
      document.getElementById("webAuthorInput").value = data.author || "";
      document.getElementById("webTitleInput").value = data.title || "";
      document.getElementById("webDateInput").value = data.date || "";
    }
  } catch (err) {
    console.error("Failed to detect metadata", err);
  } finally {
    if (btnDetectMeta) {
      btnDetectMeta.disabled = false;
      btnDetectMeta.textContent = origBtnText;
    }
  }
}

async function handleWebToPdf() {
  clearError();
  hideResult();

  const rawUrl = webUrlInput ? webUrlInput.value.trim() : "";
  if (!rawUrl) {
    showError("Please enter the URL of the article or webpage you want to convert.");
    if (webUrlInput) webUrlInput.focus();
    return;
  }

  if (!rawUrl.startsWith("http://") && !rawUrl.startsWith("https://")) {
    showError("URL must start with http:// or https://");
    if (webUrlInput) webUrlInput.focus();
    return;
  }

  btnWebToPdf.disabled = true;

  const webMode = getRadioValue("webMode", "reader");
  const webStyle = getRadioValue("webStyle", "academic");
  const zoteroMode = getRadioValue("zoteroMode", "standalone");
  const chkImages = document.getElementById("chkWebImages");
  const includeImages = chkImages ? chkImages.checked : true;

  const customAuthor = document.getElementById("webAuthorInput").value.trim();
  const customTitle = document.getElementById("webTitleInput").value.trim();
  const customDate = document.getElementById("webDateInput").value.trim();

  showProgress(
    "Extracting & rendering article...",
    35,
    "Downloading webpage, cleaning clutter, and building selectable PDF..."
  );

  const fd = new FormData();
  fd.append("url", rawUrl);
  fd.append("mode", webMode);
  fd.append("style", webStyle);
  fd.append("include_images", includeImages ? "true" : "false");
  fd.append("zotero_mode", zoteroMode);
  if (customAuthor) fd.append("custom_author", customAuthor);
  if (customTitle) fd.append("custom_title", customTitle);
  if (customDate) fd.append("custom_date", customDate);

  try {
    const res = await fetch("/api/web-to-pdf", { method: "POST", body: fd });
    const data = await res.json();
    hideProgress();
    btnWebToPdf.disabled = false;

    if (!res.ok) {
      throw new Error(data.detail || "Failed to convert webpage to PDF.");
    }

    document.getElementById("resOrigSize").textContent =
      data.author && data.author !== "Not specified" ? data.author : "Web Article";
    document.getElementById("resCompSize").textContent = data.filesize_formatted;
    document.getElementById("resSaved").textContent = `${data.pages} page(s)`;
    document.getElementById("resDuration").textContent = "100% Vector";

    const metricLabels = document.querySelectorAll("#metricsGrid .metric-label");
    if (metricLabels.length >= 4) {
      metricLabels[0].textContent = "Detected Author";
      metricLabels[1].textContent = "PDF Size";
      metricLabels[2].textContent = "Pages";
      metricLabels[3].textContent = "Text Layer";
    }

    const btnDl = document.getElementById("btnDownloadLink");
    btnDl.href = `/api/download/${encodeURIComponent(data.filename)}`;
    btnDl.textContent = `Download PDF for Zotero (${data.filesize_formatted})`;

    revealResult(`Article converted to PDF (${data.pages} pages)!`);
  } catch (err) {
    btnWebToPdf.disabled = false;
    hideProgress();
    showError(err.message);
  }
}

// ==========================================
// 10. OCR SCANNER / DIGITIZE BOOK OR DOCUMENT
// ==========================================
const ocrDropzone = document.getElementById("ocrDropzone");
const ocrFileInput = document.getElementById("ocrFileInput");
const ocrPreviewSection = document.getElementById("ocrPreviewSection");
const ocrPreviewGrid = document.getElementById("ocrPreviewGrid");
const ocrPageCountText = document.getElementById("ocrPageCountText");
const btnRunOcr = document.getElementById("btnRunOcr");
const btnClearOcrFiles = document.getElementById("btnClearOcrFiles");
const btnCopyOcrText = document.getElementById("btnCopyOcrText");

if (ocrDropzone && ocrFileInput) {
  ocrDropzone.addEventListener("click", () => ocrFileInput.click());
  ocrDropzone.addEventListener("dragover", (e) => {
    e.preventDefault();
    ocrDropzone.classList.add("dragover");
  });
  ocrDropzone.addEventListener("dragleave", () => ocrDropzone.classList.remove("dragover"));
  ocrDropzone.addEventListener("drop", (e) => {
    e.preventDefault();
    ocrDropzone.classList.remove("dragover");
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      handleOcrFilesChosen(Array.from(e.dataTransfer.files));
    }
  });

  ocrFileInput.addEventListener("change", (e) => {
    if (e.target.files && e.target.files.length > 0) {
      handleOcrFilesChosen(Array.from(e.target.files));
      ocrFileInput.value = "";
    }
  });
}

if (btnClearOcrFiles) {
  btnClearOcrFiles.addEventListener("click", clearOcrFiles);
}

if (ocrPreviewGrid) {
  ocrPreviewGrid.addEventListener("click", (e) => {
    const removeBtn = e.target.closest("button[data-remove-ocr-idx]");
    if (!removeBtn) return;
    e.stopPropagation();
    const idx = parseInt(removeBtn.dataset.removeOcrIdx, 10);
    if (!Number.isNaN(idx) && idx >= 0 && idx < ocrFiles.length) {
      ocrFiles.splice(idx, 1);
      renderOcrPreviews();
    }
  });
}

if (btnRunOcr) {
  btnRunOcr.addEventListener("click", handleOcrScan);
}

if (btnCopyOcrText) {
  btnCopyOcrText.addEventListener("click", copyOcrText);
}

function naturalSortComparator(a, b) {
  return a.name.localeCompare(b.name, undefined, { numeric: true, sensitivity: "base" });
}

function revokeOcrObjectUrls() {
  ocrObjectUrls.forEach((url) => URL.revokeObjectURL(url));
  ocrObjectUrls = [];
}

function handleOcrFilesChosen(newFiles) {
  const allowedExts = [".jpg", ".jpeg", ".png", ".webp", ".tiff", ".tif", ".bmp", ".pdf"];
  const validFiles = newFiles.filter((f) => {
    const parts = f.name.split(".");
    const ext = parts.length > 1 ? "." + parts.pop().toLowerCase() : "";
    return allowedExts.includes(ext);
  });

  if (validFiles.length === 0) {
    showError("Please select valid images (JPG, PNG, WEBP, TIFF, BMP) or a PDF file.");
    return;
  }

  const pdfFile = validFiles.find((f) => f.name.toLowerCase().endsWith(".pdf"));
  if (pdfFile) {
    ocrFiles = [pdfFile];
  } else {
    if (ocrFiles.length === 1 && ocrFiles[0].name.toLowerCase().endsWith(".pdf")) {
      ocrFiles = [];
    }
    const existingNames = new Set(ocrFiles.map((f) => f.name));
    validFiles.forEach((f) => {
      if (!existingNames.has(f.name)) {
        ocrFiles.push(f);
      }
    });
    ocrFiles.sort(naturalSortComparator);
  }

  renderOcrPreviews();
  clearError();
}

function renderOcrPreviews() {
  if (!ocrPreviewGrid || !ocrPreviewSection || !btnRunOcr) return;

  revokeOcrObjectUrls();

  if (ocrFiles.length === 0) {
    ocrPreviewSection.hidden = true;
    btnRunOcr.disabled = true;
    ocrPreviewGrid.innerHTML = "";
    return;
  }

  ocrPreviewSection.hidden = false;
  btnRunOcr.disabled = false;
  ocrPreviewGrid.innerHTML = "";

  const isSinglePdf = ocrFiles.length === 1 && ocrFiles[0].name.toLowerCase().endsWith(".pdf");

  if (isSinglePdf) {
    ocrPageCountText.textContent = `Scanned PDF ready: ${ocrFiles[0].name} (${formatBytes(ocrFiles[0].size)})`;
    const card = document.createElement("div");
    card.className = "ocr-page-card";
    card.innerHTML = `
      <div class="ocr-pdf-thumb-placeholder">
        <svg aria-hidden="true" style="width: 32px; height: 32px; margin-bottom: 4px;" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.8" d="M7 21h10a2 2 0 002-2V9.414a1 1 0 00-.293-.707l-5.414-5.414A1 1 0 0012.586 3H7a2 2 0 00-2 2v14a2 2 0 002 2z"/>
        </svg>
        <span>Full PDF</span>
      </div>
      <button type="button" class="ocr-page-remove" data-remove-ocr-idx="0" aria-label="Remove file">&times;</button>
      <div class="ocr-page-name">${escapeHtml(ocrFiles[0].name)}</div>
    `;
    ocrPreviewGrid.appendChild(card);
    return;
  }

  ocrPageCountText.textContent = `${ocrFiles.length} page(s) queued for OCR processing`;

  ocrFiles.forEach((file, idx) => {
    const card = document.createElement("div");
    card.className = "ocr-page-card";

    const badge = document.createElement("div");
    badge.className = "ocr-page-badge";
    badge.textContent = `Page ${idx + 1}`;

    const removeBtn = document.createElement("button");
    removeBtn.type = "button";
    removeBtn.className = "ocr-page-remove";
    removeBtn.dataset.removeOcrIdx = String(idx);
    removeBtn.innerHTML = "&times;";
    removeBtn.setAttribute("aria-label", `Remove ${file.name}`);

    const objUrl = URL.createObjectURL(file);
    ocrObjectUrls.push(objUrl);

    const img = document.createElement("img");
    img.className = "ocr-page-thumb";
    img.alt = `Preview of ${file.name}`;
    img.src = objUrl;

    const name = document.createElement("div");
    name.className = "ocr-page-name";
    name.textContent = file.name;

    card.appendChild(badge);
    card.appendChild(removeBtn);
    card.appendChild(img);
    card.appendChild(name);

    ocrPreviewGrid.appendChild(card);
  });
}

function clearOcrFiles() {
  ocrFiles = [];
  renderOcrPreviews();
}

async function handleOcrScan() {
  clearError();
  hideResult();

  if (ocrFiles.length === 0) {
    showError("Please select at least one image or scanned PDF file to digitize.");
    return;
  }

  btnRunOcr.disabled = true;

  const titleInput = document.getElementById("ocrTitleInput");
  const customTitle = titleInput ? titleInput.value.trim() : "";
  const enhanceContrast = document.getElementById("chkOcrEnhance").checked;
  const autoOrient = document.getElementById("chkOcrAutoOrient").checked;
  const selectedOcrLang = getRadioValue("ocrLang", "eng");

  showProgress("Starting digitization...", 5, "Uploading pages to OCR server...");

  const fd = new FormData();
  ocrFiles.forEach((file) => fd.append("files", file));
  fd.append("language", selectedOcrLang);
  fd.append("enhance_contrast", enhanceContrast ? "true" : "false");
  fd.append("auto_orient", autoOrient ? "true" : "false");
  if (customTitle) {
    fd.append("custom_title", customTitle);
  }

  try {
    const res = await fetch("/api/ocr-scan", { method: "POST", body: fd });
    const data = await res.json();

    if (!res.ok) {
      throw new Error(data.detail || "Failed to start OCR digitization.");
    }

    pollOcrTask(data.task_id);
  } catch (err) {
    btnRunOcr.disabled = false;
    hideProgress();
    showError(err.message);
  }
}

function pollOcrTask(taskId) {
  if (ocrPollInterval) clearInterval(ocrPollInterval);

  ocrPollInterval = setInterval(async () => {
    try {
      const res = await fetch(`/api/ocr-tasks/${taskId}`);
      const task = await res.json();

      if (!res.ok) {
        clearInterval(ocrPollInterval);
        btnRunOcr.disabled = false;
        hideProgress();
        showError("Failed to query OCR digitization status.");
        return;
      }

      showProgress("Digitizing document...", task.progress, task.message);

      if (task.status === "completed") {
        clearInterval(ocrPollInterval);
        btnRunOcr.disabled = false;
        hideProgress();
        showOcrResult(task.result);
      } else if (task.status === "failed") {
        clearInterval(ocrPollInterval);
        btnRunOcr.disabled = false;
        hideProgress();
        showError(task.message || "OCR digitization failed.");
      }
    } catch {
      clearInterval(ocrPollInterval);
      btnRunOcr.disabled = false;
      hideProgress();
      showError("Connection error during OCR processing.");
    }
  }, 750);
}

function showOcrResult(res) {
  document.getElementById("resOrigSize").textContent = `${res.total_pages} page(s)`;
  document.getElementById("resCompSize").textContent = res.pdf_size_formatted;
  document.getElementById("resSaved").textContent = res.language.toUpperCase();
  document.getElementById("resDuration").textContent = `${res.duration_seconds}s`;

  const metricLabels = document.querySelectorAll("#metricsGrid .metric-label");
  if (metricLabels.length >= 4) {
    metricLabels[0].textContent = "Pages Processed";
    metricLabels[1].textContent = "PDF Size";
    metricLabels[2].textContent = "OCR Language";
    metricLabels[3].textContent = "Elapsed Time";
  }

  const btnDl = document.getElementById("btnDownloadLink");
  btnDl.href = `/api/download/${encodeURIComponent(res.filename)}`;
  btnDl.textContent = `Download Searchable PDF (${res.pdf_size_formatted})`;

  const ocrExtraActions = document.getElementById("ocrExtraActions");
  if (ocrExtraActions) ocrExtraActions.hidden = false;

  const btnDlTxt = document.getElementById("btnDownloadTxt");
  if (btnDlTxt) {
    if (res.text_filename) {
      btnDlTxt.href = `/api/download/${encodeURIComponent(res.text_filename)}`;
      btnDlTxt.hidden = false;
    } else {
      btnDlTxt.hidden = true;
    }
  }

  lastExtractedOcrText = res.text_sample || "";
  const previewBox = document.getElementById("ocrTextPreviewBox");
  const previewContent = document.getElementById("ocrTextPreviewContent");
  if (previewBox && previewContent) {
    previewContent.textContent = lastExtractedOcrText;
    previewBox.hidden = false;
  }

  revealResult(`OCR digitization complete (${res.total_pages} pages)!`);
}

function legacyCopyText(text) {
  const field = Object.assign(document.createElement("textarea"), { value: text });
  field.setAttribute("readonly", "");
  field.style.cssText = "position:fixed;inset-block-start:0;opacity:0";
  document.body.append(field);
  field.select();
  try {
    return document.execCommand("copy");
  } finally {
    field.remove();
  }
}

function reportCopyStatus(ok) {
  const tip = document.getElementById("copyStatus");
  if (!tip) return;

  clearTimeout(copyFeedbackTimer);
  let msg = ok ? "Copied!" : "Copy failed";
  if (msg === lastCopyStatusMessage) msg += "\u00A0";
  lastCopyStatusMessage = msg;

  tip.textContent = "";
  requestAnimationFrame(() => {
    tip.textContent = msg;
  });

  copyFeedbackTimer = setTimeout(() => {
    tip.textContent = "";
  }, 2000);
}

async function copyOcrText() {
  if (!lastExtractedOcrText) return;
  try {
    await navigator.clipboard.writeText(lastExtractedOcrText);
    reportCopyStatus(true);
  } catch {
    const fallbackOk = legacyCopyText(lastExtractedOcrText);
    reportCopyStatus(fallbackOk);
    if (!fallbackOk) {
      showError("Could not copy automatically to the clipboard.");
    }
  }
}
