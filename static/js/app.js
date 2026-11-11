// PDF Toolbox Client Application

let currentFile = null;
let currentLocalFilename = null;
let currentLocalFileSize = null;
let selectedPreset = "screen";
let selectedAngle = 90;
let mergeFiles = [];
let pollInterval = null;

// DOM Elements
const dropzone = document.getElementById("dropzone");
const fileInput = document.getElementById("fileInput");
const selectedFileBar = document.getElementById("selectedFileBar");
const selectedFileName = document.getElementById("selectedFileName");
const selectedFileSize = document.getElementById("selectedFileSize");
const progressSection = document.getElementById("progressSection");
const progressBarFill = document.getElementById("progressBarFill");
const progressPercentage = document.getElementById("progressPercentage");
const progressStatusMsg = document.getElementById("progressStatusMsg");
const resultSection = document.getElementById("resultSection");
const errorBox = document.getElementById("errorBox");

// Tab Navigation
document.querySelectorAll(".tab-btn").forEach((btn) => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".tab-btn").forEach((b) => b.classList.remove("active"));
    document.querySelectorAll(".tab-content").forEach((c) => c.classList.add("hidden"));

    btn.classList.add("active");
    const tabName = btn.dataset.tab;
    const tabContent = document.getElementById(`tab-${tabName}`);
    if (tabContent) tabContent.classList.remove("hidden");

    // Toggle single-file selector vs merge/webpdf/ocr selector
    const singleFileSection = document.getElementById("singleFileSection");
    if (tabName === "merge" || tabName === "webpdf" || tabName === "ocr") {
      singleFileSection.classList.add("hidden");
    } else {
      singleFileSection.classList.remove("hidden");
    }

    clearError();
    hideResult();
    resetMetricLabels();
  });
});

function resetMetricLabels() {
  const metricLabels = document.querySelectorAll("#metricsGrid .metric-label");
  if (metricLabels.length >= 4) {
    metricLabels[0].textContent = "Tamaño Original";
    metricLabels[1].textContent = "Tamaño Final";
    metricLabels[2].textContent = "Espacio Ahorrado";
    metricLabels[3].textContent = "Tiempo";
  }
}

// Dropzone Events for Single File
if (dropzone) {
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
}

if (fileInput) {
  fileInput.addEventListener("change", (e) => {
    if (e.target.files && e.target.files.length > 0) {
      handleFileChosen(e.target.files[0]);
    }
  });
}

function handleFileChosen(file) {
  if (!file.name.toLowerCase().endsWith(".pdf")) {
    showError("Por favor selecciona un archivo con extensión .pdf");
    return;
  }
  currentFile = file;
  currentLocalFilename = null;
  currentLocalFileSize = null;

  selectedFileName.textContent = file.name;
  selectedFileSize.textContent = `(${formatBytes(file.size)})`;
  selectedFileBar.classList.remove("hidden");
  dropzone.classList.add("hidden");
  clearError();
}

function selectLocalFile(filename, sizeFormatted) {
  currentFile = null;
  currentLocalFilename = filename;
  currentLocalFileSize = sizeFormatted;

  selectedFileName.textContent = filename;
  selectedFileSize.textContent = `(${sizeFormatted} · local)`;
  selectedFileBar.classList.remove("hidden");
  dropzone.classList.add("hidden");
  clearError();

  // Scroll smoothly to workspace
  document.querySelector(".tabs").scrollIntoView({ behavior: "smooth" });
}

function clearSelectedFile() {
  currentFile = null;
  currentLocalFilename = null;
  currentLocalFileSize = null;
  fileInput.value = "";
  selectedFileBar.classList.add("hidden");
  dropzone.classList.remove("hidden");
}

function selectPreset(cardEl) {
  document.querySelectorAll("#tab-compress .option-card").forEach((c) => c.classList.remove("selected"));
  cardEl.classList.add("selected");
  selectedPreset = cardEl.dataset.preset;
}

function selectAngle(cardEl) {
  document.querySelectorAll("#tab-rotate .option-card").forEach((c) => c.classList.remove("selected"));
  cardEl.classList.add("selected");
  selectedAngle = parseInt(cardEl.dataset.angle, 10);
}

// Merge Multiple Files Handling
const mergeDropzone = document.getElementById("mergeDropzone");
const mergeFileInput = document.getElementById("mergeFileInput");
const mergeFileList = document.getElementById("mergeFileList");
const btnMerge = document.getElementById("btnMerge");

if (mergeDropzone) {
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
}

if (mergeFileInput) {
  mergeFileInput.addEventListener("change", (e) => {
    if (e.target.files) {
      addMergeFiles(Array.from(e.target.files));
    }
  });
}

function addMergeFiles(files) {
  const pdfs = files.filter((f) => f.name.toLowerCase().endsWith(".pdf"));
  mergeFiles = [...mergeFiles, ...pdfs];
  renderMergeList();
}

function removeMergeFile(index) {
  mergeFiles.splice(index, 1);
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
    item.innerHTML = `
      <div>
        <span style="font-size:0.75rem; color:var(--text-muted); margin-right:0.5rem;">#${idx + 1}</span>
        <span class="file-name-text">${escapeHtml(file.name)}</span>
        <span class="file-meta-text">(${formatBytes(file.size)})</span>
      </div>
      <button type="button" class="btn-clear" onclick="removeMergeFile(${idx})">&times;</button>
    `;
    mergeFileList.appendChild(item);
  });

  btnMerge.disabled = mergeFiles.length < 2;
}

// Helpers
function getActiveFormData() {
  const fd = new FormData();
  if (currentLocalFilename) {
    fd.append("local_filename", currentLocalFilename);
  } else if (currentFile) {
    fd.append("file", currentFile);
  } else {
    showError("Por favor selecciona un archivo PDF primero.");
    return null;
  }
  return fd;
}

function showError(msg) {
  errorBox.textContent = msg;
  errorBox.classList.remove("hidden");
}

function clearError() {
  errorBox.textContent = "";
  errorBox.classList.add("hidden");
}

function showProgress(title, percent, msg) {
  progressSection.classList.remove("hidden");
  document.getElementById("progressTitle").textContent = title;
  progressPercentage.textContent = `${percent}%`;
  progressBarFill.style.width = `${percent}%`;
  progressStatusMsg.textContent = msg;
}

function hideProgress() {
  progressSection.classList.add("hidden");
}

function hideResult() {
  resultSection.classList.add("hidden");
  const ocrExtraActions = document.getElementById("ocrExtraActions");
  if (ocrExtraActions) ocrExtraActions.classList.add("hidden");
  const ocrTextPreviewBox = document.getElementById("ocrTextPreviewBox");
  if (ocrTextPreviewBox) ocrTextPreviewBox.classList.add("hidden");
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
  div.textContent = text;
  return div.innerHTML;
}

// Actions Execution

// 1. COMPRESS
async function handleCompress() {
  clearError();
  hideResult();

  const fd = getActiveFormData();
  if (!fd) return;

  const toGrayscale = document.getElementById("chkGrayscale").checked;
  fd.append("preset", selectedPreset);
  fd.append("to_grayscale", toGrayscale ? "true" : "false");

  const btn = document.getElementById("btnCompress");
  btn.disabled = true;

  showProgress("Iniciando compresión", 5, "Enviando documento al motor de optimización...");

  try {
    const res = await fetch("/api/compress", {
      method: "POST",
      body: fd,
    });
    const data = await res.json();

    if (!res.ok) {
      throw new Error(data.detail || "Error al procesar la solicitud.");
    }

    pollTask(data.task_id);
  } catch (err) {
    btn.disabled = false;
    hideProgress();
    showError(err.message);
  }
}

function pollTask(taskId) {
  if (pollInterval) clearInterval(pollInterval);

  pollInterval = setInterval(async () => {
    try {
      const res = await fetch(`/api/tasks/${taskId}`);
      const task = await res.json();

      if (!res.ok) {
        clearInterval(pollInterval);
        document.getElementById("btnCompress").disabled = false;
        hideProgress();
        showError("Error consultando estado de la tarea.");
        return;
      }

      showProgress("Aligerando PDF...", task.progress, task.message);

      if (task.status === "completed") {
        clearInterval(pollInterval);
        document.getElementById("btnCompress").disabled = false;
        hideProgress();
        showCompressionResult(task.result);
      } else if (task.status === "failed") {
        clearInterval(pollInterval);
        document.getElementById("btnCompress").disabled = false;
        hideProgress();
        showError(task.message || "La compresión falló.");
      }
    } catch (e) {
      clearInterval(pollInterval);
      document.getElementById("btnCompress").disabled = false;
      hideProgress();
      showError("Error de conexión durante el proceso.");
    }
  }, 750);
}

function showCompressionResult(res) {
  document.getElementById("resultHeading").textContent = "¡PDF aligerado con éxito!";
  document.getElementById("resOrigSize").textContent = res.original_size_formatted;
  document.getElementById("resCompSize").textContent = res.compressed_size_formatted;
  document.getElementById("resSaved").textContent = `-${res.saved_percentage}% (${res.saved_bytes_formatted})`;
  document.getElementById("resDuration").textContent = `${res.duration_seconds}s`;

  const btnDl = document.getElementById("btnDownloadLink");
  btnDl.href = `/api/download/${res.filename}`;
  btnDl.textContent = `Descargar PDF Aligerado (${res.compressed_size_formatted})`;

  resultSection.classList.remove("hidden");
  resultSection.scrollIntoView({ behavior: "smooth" });
}

// 2. SPLIT / EXTRACT
async function handleSplit() {
  clearError();
  hideResult();

  const fd = getActiveFormData();
  if (!fd) return;

  const ranges = document.getElementById("pageRanges").value.trim();
  if (!ranges) {
    showError("Por favor ingresa los rangos de páginas a extraer (ej: 1-5, 8).");
    return;
  }
  fd.append("page_ranges", ranges);

  showProgress("Extrayendo páginas", 50, "Generando nuevo PDF con las páginas seleccionadas...");

  try {
    const res = await fetch("/api/split", {
      method: "POST",
      body: fd,
    });
    const data = await res.json();
    hideProgress();

    if (!res.ok) throw new Error(data.detail || "Error al dividir el PDF.");

    document.getElementById("resultHeading").textContent = `¡Páginas extraídas! (${data.extracted_pages} páginas)`;
    document.getElementById("resOrigSize").textContent = "-";
    document.getElementById("resCompSize").textContent = data.size_formatted;
    document.getElementById("resSaved").textContent = `${data.extracted_pages} páginas`;
    document.getElementById("resDuration").textContent = "Instantáneo";

    const btnDl = document.getElementById("btnDownloadLink");
    btnDl.href = `/api/download/${data.filename}`;
    btnDl.textContent = `Descargar PDF Extraído (${data.size_formatted})`;

    resultSection.classList.remove("hidden");
  } catch (err) {
    hideProgress();
    showError(err.message);
  }
}

// 3. MERGE
async function handleMerge() {
  clearError();
  hideResult();

  if (mergeFiles.length < 2) {
    showError("Debes seleccionar al menos dos archivos PDF.");
    return;
  }

  const fd = new FormData();
  mergeFiles.forEach((f) => fd.append("files", f));

  showProgress("Uniendo PDFs", 50, "Combinando documentos y optimizando referencias...");

  try {
    const res = await fetch("/api/merge", {
      method: "POST",
      body: fd,
    });
    const data = await res.json();
    hideProgress();

    if (!res.ok) throw new Error(data.detail || "Error al unir los PDFs.");

    document.getElementById("resultHeading").textContent = `¡PDFs unidos con éxito! (${data.total_pages} páginas)`;
    document.getElementById("resOrigSize").textContent = "-";
    document.getElementById("resCompSize").textContent = data.size_formatted;
    document.getElementById("resSaved").textContent = `${data.total_pages} págs.`;
    document.getElementById("resDuration").textContent = "Instantáneo";

    const btnDl = document.getElementById("btnDownloadLink");
    btnDl.href = `/api/download/${data.filename}`;
    btnDl.textContent = `Descargar PDF Combinado (${data.size_formatted})`;

    resultSection.classList.remove("hidden");
  } catch (err) {
    hideProgress();
    showError(err.message);
  }
}

// 4. ROTATE
async function handleRotate() {
  clearError();
  hideResult();

  const fd = getActiveFormData();
  if (!fd) return;

  const ranges = document.getElementById("rotateRanges").value.trim();
  fd.append("angle", selectedAngle);
  if (ranges) fd.append("page_ranges", ranges);

  showProgress("Rotando páginas", 50, `Aplicando rotación de ${selectedAngle}°...`);

  try {
    const res = await fetch("/api/rotate", {
      method: "POST",
      body: fd,
    });
    const data = await res.json();
    hideProgress();

    if (!res.ok) throw new Error(data.detail || "Error al rotar páginas.");

    document.getElementById("resultHeading").textContent = `¡Páginas rotadas (${data.angle}°)!`;
    document.getElementById("resOrigSize").textContent = "-";
    document.getElementById("resCompSize").textContent = data.size_formatted;
    document.getElementById("resSaved").textContent = `${data.rotated_pages_count} págs. rotadas`;
    document.getElementById("resDuration").textContent = "Instantáneo";

    const btnDl = document.getElementById("btnDownloadLink");
    btnDl.href = `/api/download/${data.filename}`;
    btnDl.textContent = `Descargar PDF Rotado (${data.size_formatted})`;

    resultSection.classList.remove("hidden");
  } catch (err) {
    hideProgress();
    showError(err.message);
  }
}

// 5. INSPECT
async function handleInspect() {
  clearError();
  hideResult();

  const container = document.getElementById("inspectResultContainer");
  container.innerHTML = "";

  const fd = getActiveFormData();
  if (!fd) return;

  showProgress("Analizando PDF", 50, "Leyendo metadatos, objetos y páginas...");

  try {
    const res = await fetch("/api/inspect", {
      method: "POST",
      body: fd,
    });
    const data = await res.json();
    hideProgress();

    if (!res.ok) throw new Error(data.detail || "Error al analizar el PDF.");

    const meta = data.metadata || {};
    container.innerHTML = `
      <table class="info-table">
        <tbody>
          <tr><th>Nombre de archivo</th><td>${escapeHtml(data.filename)}</td></tr>
          <tr><th>Tamaño</th><td>${escapeHtml(data.filesize_formatted)} (${data.filesize_bytes.toLocaleString()} bytes)</td></tr>
          <tr><th>Páginas totales</th><td><strong>${data.pages}</strong></td></tr>
          <tr><th>Dimensiones de página</th><td>${escapeHtml(data.dimensions)}</td></tr>
          <tr><th>Título actual</th><td>${escapeHtml(meta.title)}</td></tr>
          <tr><th>Autor actual</th><td>${escapeHtml(meta.author)}</td></tr>
          <tr><th>Generador / Creador</th><td>${escapeHtml(meta.creator)}</td></tr>
          <tr><th>Productor</th><td>${escapeHtml(meta.producer)}</td></tr>
          <tr><th>Fecha creación</th><td>${escapeHtml(meta.creation_date)}</td></tr>
          <tr><th>Imágenes (en muestra)</th><td>${data.sample_images_first_pages} imágenes en las primeras ${data.sample_pages_checked} págs.</td></tr>
          <tr><th>Protegido / Encriptado</th><td>${data.is_encrypted ? "Sí" : "No"}</td></tr>
        </tbody>
      </table>

      <!-- Editor de Metadatos para Zotero -->
      <div style="margin-top: 1.25rem; background-color: var(--bg-subtle); padding: 1.1rem; border-radius: var(--radius-sm); border: 1px solid var(--border-color);">
        <h4 style="font-size: 0.9rem; font-weight: 700; margin-bottom: 0.75rem; color: var(--text-main);">Editar Metadatos de este PDF (para Zotero)</h4>
        <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 0.75rem; margin-bottom: 0.75rem;">
          <div>
            <label style="font-size: 0.78rem; font-weight: 600; color: var(--text-secondary); display: block; margin-bottom: 0.2rem;">Título</label>
            <input type="text" id="editMetaTitle" class="input-text" value="${escapeHtml(meta.title !== 'Sin título' ? meta.title : '')}">
          </div>
          <div>
            <label style="font-size: 0.78rem; font-weight: 600; color: var(--text-secondary); display: block; margin-bottom: 0.2rem;">Autor</label>
            <input type="text" id="editMetaAuthor" class="input-text" value="${escapeHtml(meta.author !== 'No especificado' ? meta.author : '')}">
          </div>
        </div>
        <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 0.75rem; margin-bottom: 0.75rem;">
          <div>
            <label style="font-size: 0.78rem; font-weight: 600; color: var(--text-secondary); display: block; margin-bottom: 0.2rem;">Asunto / Materia</label>
            <input type="text" id="editMetaSubject" class="input-text" value="${escapeHtml(meta.subject || '')}">
          </div>
          <div>
            <label style="font-size: 0.78rem; font-weight: 600; color: var(--text-secondary); display: block; margin-bottom: 0.2rem;">Palabras Clave (Keywords)</label>
            <input type="text" id="editMetaKeywords" class="input-text" value="${escapeHtml(meta.keywords || '')}">
          </div>
        </div>
        <button type="button" class="btn-primary" onclick="handleSaveMetadata()" style="font-size: 0.85rem; padding: 0.55rem 1.1rem;">
          Guardar y Descargar con nuevos metadatos
        </button>
      </div>
    `;
  } catch (err) {
    hideProgress();
    showError(err.message);
  }
}

async function handleSaveMetadata() {
  clearError();
  const fd = getActiveFormData();
  if (!fd) return;

  const title = document.getElementById("editMetaTitle") ? document.getElementById("editMetaTitle").value.trim() : "";
  const author = document.getElementById("editMetaAuthor") ? document.getElementById("editMetaAuthor").value.trim() : "";
  const subject = document.getElementById("editMetaSubject") ? document.getElementById("editMetaSubject").value.trim() : "";
  const keywords = document.getElementById("editMetaKeywords") ? document.getElementById("editMetaKeywords").value.trim() : "";

  fd.append("title", title);
  fd.append("author", author);
  fd.append("subject", subject);
  fd.append("keywords", keywords);

  showProgress("Actualizando metadatos", 50, "Escribiendo campos de autor y título en el archivo PDF...");

  try {
    const res = await fetch("/api/update-metadata", { method: "POST", body: fd });
    const data = await res.json();
    hideProgress();

    if (!res.ok) throw new Error(data.detail || "Error al actualizar metadatos.");

    document.getElementById("resultHeading").textContent = "¡Metadatos actualizados con éxito!";
    document.getElementById("resOrigSize").textContent = data.author || "No especificado";
    document.getElementById("resCompSize").textContent = data.size_formatted;
    document.getElementById("resSaved").textContent = data.title || "PDF Actualizado";
    document.getElementById("resDuration").textContent = "Instantáneo";

    const metricLabels = document.querySelectorAll("#metricsGrid .metric-label");
    if (metricLabels.length >= 4) {
      metricLabels[0].textContent = "Autor";
      metricLabels[1].textContent = "Tamaño";
      metricLabels[2].textContent = "Título";
      metricLabels[3].textContent = "Estado";
    }

    const btnDl = document.getElementById("btnDownloadLink");
    btnDl.href = `/api/download/${data.filename}`;
    btnDl.textContent = `Descargar PDF con nuevos metadatos (${data.size_formatted})`;

    resultSection.classList.remove("hidden");
    resultSection.scrollIntoView({ behavior: "smooth" });
  } catch (err) {
    hideProgress();
    showError(err.message);
  }
}

// 6. WEB TO PDF (ZOTERO)
let selectedZoteroMode = "standalone";
let selectedWebMode = "reader";
let selectedWebStyle = "academic";

function selectZoteroMode(cardEl) {
  document.querySelectorAll("#tab-webpdf .option-card[data-zoteromode]").forEach((c) => c.classList.remove("selected"));
  cardEl.classList.add("selected");
  selectedZoteroMode = cardEl.dataset.zoteromode;
}

function setSampleUrl(url) {
  const input = document.getElementById("webUrlInput");
  if (input) {
    input.value = url;
    detectUrlMetadata();
  }
}

async function detectUrlMetadata() {
  const urlInput = document.getElementById("webUrlInput");
  const url = urlInput ? urlInput.value.trim() : "";
  if (!url || (!url.startsWith("http://") && !url.startsWith("https://"))) return;

  const btnDetect = document.getElementById("btnDetectMeta");
  const origBtnText = btnDetect ? btnDetect.textContent : "";
  if (btnDetect) {
    btnDetect.disabled = true;
    btnDetect.textContent = "Detectando...";
  }

  try {
    const fd = new FormData();
    fd.append("url", url);
    const res = await fetch("/api/web-metadata", { method: "POST", body: fd });
    if (res.ok) {
      const data = await res.json();
      if (data.author) document.getElementById("webAuthorInput").value = data.author;
      if (data.title) document.getElementById("webTitleInput").value = data.title;
      if (data.date) document.getElementById("webDateInput").value = data.date;
    }
  } catch (e) {
    console.error("Error detectando metadatos", e);
  } finally {
    if (btnDetect) {
      btnDetect.disabled = false;
      btnDetect.textContent = origBtnText;
    }
  }
}

function autoDetectUrlMetadata() {
  detectUrlMetadata();
}

function selectWebMode(cardEl) {
  document.querySelectorAll("#tab-webpdf .option-card[data-webmode]").forEach((c) => c.classList.remove("selected"));
  cardEl.classList.add("selected");
  selectedWebMode = cardEl.dataset.webmode;

  const readerOpts = document.getElementById("readerOptions");
  if (readerOpts) {
    if (selectedWebMode === "fullpage") {
      readerOpts.classList.add("hidden");
    } else {
      readerOpts.classList.remove("hidden");
    }
  }
}

function selectWebStyle(cardEl) {
  document.querySelectorAll("#tab-webpdf .option-card[data-webstyle]").forEach((c) => c.classList.remove("selected"));
  cardEl.classList.add("selected");
  selectedWebStyle = cardEl.dataset.webstyle;
}

async function handleWebToPdf() {
  clearError();
  hideResult();

  const urlInput = document.getElementById("webUrlInput");
  const rawUrl = urlInput ? urlInput.value.trim() : "";

  if (!rawUrl) {
    showError("Por favor ingresa la URL de la página o artículo que deseas convertir.");
    return;
  }

  if (!rawUrl.startsWith("http://") && !rawUrl.startsWith("https://")) {
    showError("La URL debe comenzar con http:// o https://");
    return;
  }

  const btn = document.getElementById("btnWebToPdf");
  btn.disabled = true;

  const chkImages = document.getElementById("chkWebImages");
  const includeImages = chkImages ? chkImages.checked : true;

  const customAuthor = document.getElementById("webAuthorInput") ? document.getElementById("webAuthorInput").value.trim() : "";
  const customTitle = document.getElementById("webTitleInput") ? document.getElementById("webTitleInput").value.trim() : "";
  const customDate = document.getElementById("webDateInput") ? document.getElementById("webDateInput").value.trim() : "";

  showProgress(
    "Extrayendo y formateando artículo...",
    30,
    "Descargando contenido web, eliminando publicidad y generando maquetación limpia para Zotero..."
  );

  const fd = new FormData();
  fd.append("url", rawUrl);
  fd.append("mode", selectedWebMode);
  fd.append("style", selectedWebStyle);
  fd.append("include_images", includeImages ? "true" : "false");
  fd.append("zotero_mode", selectedZoteroMode);
  if (customAuthor) fd.append("custom_author", customAuthor);
  if (customTitle) fd.append("custom_title", customTitle);
  if (customDate) fd.append("custom_date", customDate);

  try {
    const res = await fetch("/api/web-to-pdf", {
      method: "POST",
      body: fd,
    });
    const data = await res.json();
    hideProgress();
    btn.disabled = false;

    if (!res.ok) {
      throw new Error(data.detail || "Error al convertir la página a PDF.");
    }

    // Render result
    document.getElementById("resultHeading").textContent = `¡Artículo convertido a PDF! (${data.pages} páginas)`;
    document.getElementById("resOrigSize").textContent = data.author && data.author !== "No especificado" ? data.author : "Artículo Web";
    document.getElementById("resCompSize").textContent = data.filesize_formatted;
    document.getElementById("resSaved").textContent = `${data.pages} páginas`;
    document.getElementById("resDuration").textContent = "100% Vectorial";

    // Change labels temporarily for Web to PDF result
    const metricLabels = document.querySelectorAll("#metricsGrid .metric-label");
    if (metricLabels.length >= 4) {
      metricLabels[0].textContent = "Autor Detectado";
      metricLabels[1].textContent = "Tamaño PDF";
      metricLabels[2].textContent = "Páginas";
      metricLabels[3].textContent = "Texto en Zotero";
    }

    const btnDl = document.getElementById("btnDownloadLink");
    btnDl.href = `/api/download/${data.filename}`;
    btnDl.textContent = `Descargar PDF para Zotero (${data.filesize_formatted})`;

    resultSection.classList.remove("hidden");
    resultSection.scrollIntoView({ behavior: "smooth" });
  } catch (err) {
    btn.disabled = false;
    hideProgress();
    showError(err.message);
  }
}

// ==========================================
// 7. OCR SCANNER / DIGITALIZAR LIBRO
// ==========================================
let ocrFiles = [];
let selectedOcrLang = "spa";
let lastExtractedOcrText = "";
let ocrPollInterval = null;

const ocrDropzone = document.getElementById("ocrDropzone");
const ocrFileInput = document.getElementById("ocrFileInput");
const ocrPreviewSection = document.getElementById("ocrPreviewSection");
const ocrPreviewGrid = document.getElementById("ocrPreviewGrid");
const ocrPageCountText = document.getElementById("ocrPageCountText");
const btnRunOcr = document.getElementById("btnRunOcr");

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

function naturalSortComparator(a, b) {
  return a.name.localeCompare(b.name, undefined, { numeric: true, sensitivity: "base" });
}

function handleOcrFilesChosen(newFiles) {
  const allowedExts = [".jpg", ".jpeg", ".png", ".webp", ".tiff", ".tif", ".bmp", ".pdf"];
  const validFiles = newFiles.filter((f) => {
    const ext = "." + f.name.split(".").pop().toLowerCase();
    return allowedExts.includes(ext);
  });

  if (validFiles.length === 0) {
    showError("Por favor selecciona imágenes válidas (JPG, PNG, WEBP, TIFF) o un archivo PDF.");
    return;
  }

  const hasPdf = validFiles.some((f) => f.name.toLowerCase().endsWith(".pdf"));
  if (hasPdf) {
    ocrFiles = [validFiles.find((f) => f.name.toLowerCase().endsWith(".pdf"))];
  } else {
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

  if (ocrFiles.length === 0) {
    ocrPreviewSection.classList.add("hidden");
    btnRunOcr.disabled = true;
    return;
  }

  ocrPreviewSection.classList.remove("hidden");
  btnRunOcr.disabled = false;
  ocrPreviewGrid.innerHTML = "";

  const isSinglePdf = ocrFiles.length === 1 && ocrFiles[0].name.toLowerCase().endsWith(".pdf");

  if (isSinglePdf) {
    ocrPageCountText.textContent = `Archivo PDF escaneado listo: ${ocrFiles[0].name} (${formatBytes(ocrFiles[0].size)})`;
    const card = document.createElement("div");
    card.className = "ocr-page-card";
    card.innerHTML = `
      <div class="ocr-pdf-thumb-placeholder">
        <svg style="width: 32px; height: 32px; margin-bottom: 4px;" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.8" d="M7 21h10a2 2 0 002-2V9.414a1 1 0 00-.293-.707l-5.414-5.414A1 1 0 0012.586 3H7a2 2 0 00-2 2v14a2 2 0 002 2z"/>
        </svg>
        <span>PDF Completo</span>
      </div>
      <button type="button" class="ocr-page-remove" onclick="removeOcrFile(0)" title="Quitar archivo">&times;</button>
      <div class="ocr-page-name">${escapeHtml(ocrFiles[0].name)}</div>
    `;
    ocrPreviewGrid.appendChild(card);
    return;
  }

  ocrPageCountText.textContent = `${ocrFiles.length} página(s) listas para procesar con OCR`;

  ocrFiles.forEach((file, idx) => {
    const card = document.createElement("div");
    card.className = "ocr-page-card";

    const badge = document.createElement("div");
    badge.className = "ocr-page-badge";
    badge.textContent = `Pág. ${idx + 1}`;

    const removeBtn = document.createElement("button");
    removeBtn.type = "button";
    removeBtn.className = "ocr-page-remove";
    removeBtn.innerHTML = "&times;";
    removeBtn.title = "Quitar página";
    removeBtn.onclick = (e) => {
      e.stopPropagation();
      removeOcrFile(idx);
    };

    const img = document.createElement("img");
    img.className = "ocr-page-thumb";
    img.alt = file.name;
    img.src = URL.createObjectURL(file);

    const name = document.createElement("div");
    name.className = "ocr-page-name";
    name.textContent = file.name;
    name.title = file.name;

    card.appendChild(badge);
    card.appendChild(removeBtn);
    card.appendChild(img);
    card.appendChild(name);

    ocrPreviewGrid.appendChild(card);
  });
}

function removeOcrFile(idx) {
  if (idx >= 0 && idx < ocrFiles.length) {
    ocrFiles.splice(idx, 1);
    renderOcrPreviews();
  }
}

function clearOcrFiles() {
  ocrFiles = [];
  renderOcrPreviews();
}

function selectOcrLang(card) {
  document.querySelectorAll("#tab-ocr .option-card").forEach((c) => c.classList.remove("selected"));
  card.classList.add("selected");
  selectedOcrLang = card.dataset.ocrlang || "spa";
}

async function handleOcrScan() {
  clearError();
  hideResult();

  if (ocrFiles.length === 0) {
    showError("Por favor selecciona al menos una imagen o un PDF para digitalizar.");
    return;
  }

  const btn = document.getElementById("btnRunOcr");
  btn.disabled = true;

  const titleInput = document.getElementById("ocrTitleInput");
  const customTitle = titleInput ? titleInput.value.trim() : "";
  const chkEnhance = document.getElementById("chkOcrEnhance");
  const enhanceContrast = chkEnhance ? chkEnhance.checked : false;
  const chkAutoOrient = document.getElementById("chkOcrAutoOrient");
  const autoOrient = chkAutoOrient ? chkAutoOrient.checked : true;

  showProgress("Iniciando digitalización...", 5, "Subiendo páginas al servidor...");

  const fd = new FormData();
  ocrFiles.forEach((file) => {
    fd.append("files", file);
  });
  fd.append("language", selectedOcrLang);
  fd.append("enhance_contrast", enhanceContrast ? "true" : "false");
  fd.append("auto_orient", autoOrient ? "true" : "false");
  if (customTitle) {
    fd.append("custom_title", customTitle);
  }

  try {
    const res = await fetch("/api/ocr-scan", {
      method: "POST",
      body: fd,
    });
    const data = await res.json();

    if (!res.ok) {
      throw new Error(data.detail || "Error al iniciar la digitalización OCR.");
    }

    pollOcrTask(data.task_id);
  } catch (err) {
    btn.disabled = false;
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
        document.getElementById("btnRunOcr").disabled = false;
        hideProgress();
        showError("Error consultando estado de la digitalización.");
        return;
      }

      showProgress("Digitalizando documento...", task.progress, task.message);

      if (task.status === "completed") {
        clearInterval(ocrPollInterval);
        document.getElementById("btnRunOcr").disabled = false;
        hideProgress();
        showOcrResult(task.result);
      } else if (task.status === "failed") {
        clearInterval(ocrPollInterval);
        document.getElementById("btnRunOcr").disabled = false;
        hideProgress();
        showError(task.message || "La digitalización falló.");
      }
    } catch (e) {
      clearInterval(ocrPollInterval);
      document.getElementById("btnRunOcr").disabled = false;
      hideProgress();
      showError("Error de conexión durante el proceso de OCR.");
    }
  }, 750);
}

function showOcrResult(res) {
  document.getElementById("resultHeading").textContent = `¡Digitalización OCR completada! (${res.total_pages} páginas)`;
  document.getElementById("resOrigSize").textContent = `${res.total_pages} página(s)`;
  document.getElementById("resCompSize").textContent = res.pdf_size_formatted;
  document.getElementById("resSaved").textContent = res.language.toUpperCase();
  document.getElementById("resDuration").textContent = `${res.duration_seconds}s`;

  // Update metric labels for OCR
  const metricLabels = document.querySelectorAll("#metricsGrid .metric-label");
  if (metricLabels.length >= 4) {
    metricLabels[0].textContent = "Páginas Procesadas";
    metricLabels[1].textContent = "Tamaño PDF";
    metricLabels[2].textContent = "Idioma OCR";
    metricLabels[3].textContent = "Tiempo";
  }

  // Primary PDF Download Link
  const btnDl = document.getElementById("btnDownloadLink");
  btnDl.href = `/api/download/${res.filename}`;
  btnDl.textContent = `Descargar PDF con Texto Seleccionable (${res.pdf_size_formatted})`;

  // TXT Companion Download Link
  const ocrExtraActions = document.getElementById("ocrExtraActions");
  if (ocrExtraActions) ocrExtraActions.classList.remove("hidden");

  const btnDlTxt = document.getElementById("btnDownloadTxt");
  if (btnDlTxt && res.text_filename) {
    btnDlTxt.href = `/api/download/${res.text_filename}`;
    btnDlTxt.classList.remove("hidden");
  }

  const btnCopy = document.getElementById("btnCopyOcrText");
  if (btnCopy) btnCopy.classList.remove("hidden");

  // Preview Box
  lastExtractedOcrText = res.text_sample || "";
  const previewBox = document.getElementById("ocrTextPreviewBox");
  const previewContent = document.getElementById("ocrTextPreviewContent");
  if (previewBox && previewContent) {
    previewContent.textContent = lastExtractedOcrText;
    previewBox.classList.remove("hidden");
  }

  resultSection.classList.remove("hidden");
  resultSection.scrollIntoView({ behavior: "smooth" });
}

function copyOcrText() {
  if (!lastExtractedOcrText) return;
  navigator.clipboard.writeText(lastExtractedOcrText).then(() => {
    const btn = document.getElementById("btnCopyOcrText");
    if (btn) {
      const origHtml = btn.innerHTML;
      btn.innerHTML = `
        <svg style="width: 16px; height: 16px; color: #16a34a;" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="M5 13l4 4L19 7"/>
        </svg>
        ¡Texto Copiado!
      `;
      setTimeout(() => {
        btn.innerHTML = origHtml;
      }, 2000);
    }
  }).catch(() => {
    showError("No se pudo copiar automáticamente al portapapeles.");
  });
}


