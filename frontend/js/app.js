"use strict";

const API_BASE = ""; // Diproksikan oleh frontend_server.py ke http://127.0.0.1:8000
const POLL_INTERVAL = 2200;

const state = {
  file: null,
  fileUrl: null,
  fileKind: null,
  currentJobId: null,
  currentResult: null,
  pollTimer: null,
  editMode: false,
};

const $ = (id) => document.getElementById(id);

function escapeHtml(value = "") {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function normalizeStatus(value) {
  return String(value || "").trim().replaceAll(" ", "_").toUpperCase();
}

function formatPercent(value) {
  if (value === null || value === undefined || value === "") return "—";
  const number = Number(value);
  if (!Number.isFinite(number)) return "—";
  return `${(number <= 1 ? number * 100 : number).toFixed(2)}%`;
}

function showToast(message, type = "info", duration = 4600) {
  const toast = document.createElement("div");
  toast.className = `toast toast-${type}`;
  toast.textContent = message;
  $("toastContainer").appendChild(toast);
  window.setTimeout(() => toast.remove(), duration);
}

async function api(path, options = {}) {
  const response = await fetch(`${API_BASE}${path}`, options);
  const raw = await response.text();
  let data = null;
  if (raw) {
    try { data = JSON.parse(raw); } catch { data = raw; }
  }
  if (!response.ok) {
    const detail = data?.detail;
    let message = detail || data || `HTTP ${response.status}`;
    if (Array.isArray(detail)) message = detail.map((item) => item.msg || JSON.stringify(item)).join("; ");
    if (typeof message !== "string") message = JSON.stringify(message);
    throw new Error(message);
  }
  return data;
}

function setBackendStatus(online, text) {
  const box = $("backendStatus");
  box.className = `connection ${online ? "connection-online" : "connection-offline"}`;
  $("backendStatusText").textContent = text;
}

async function checkBackend() {
  try {
    await api("/health");
    setBackendStatus(true, "Backend terhubung");
    return true;
  } catch {
    setBackendStatus(false, "Backend belum berjalan");
    return false;
  }
}

function setProcess(status, title, message, detail = "") {
  const normalized = normalizeStatus(status || "IDLE");
  $("processBadge").textContent = normalized;
  $("processBadge").className = `badge badge-${normalized.toLowerCase().replaceAll("_", "-")}`;
  $("processTitle").textContent = title;
  $("processMessage").textContent = message;
  $("processDetail").textContent = detail;
  $("spinner").hidden = !["PROCESSING", "UPLOADED"].includes(normalized);
}

function releaseFileUrl() {
  if (state.fileUrl) URL.revokeObjectURL(state.fileUrl);
  state.fileUrl = null;
}

function detectKind(file) {
  if (!file) return null;
  if (file.type === "application/pdf" || file.name.toLowerCase().endsWith(".pdf")) return "pdf";
  if (file.type.startsWith("image/")) return "image";
  return null;
}

function showPreviewIn(targetImageId, targetPdfId, emptyId = null) {
  const image = $(targetImageId);
  const pdf = $(targetPdfId);
  const empty = emptyId ? $(emptyId) : null;
  image.hidden = true;
  pdf.hidden = true;
  if (empty) empty.hidden = true;

  if (!state.fileUrl) {
    if (empty) empty.hidden = false;
    return;
  }
  if (state.fileKind === "pdf") {
    pdf.src = state.fileUrl;
    pdf.hidden = false;
  } else if (state.fileKind === "image") {
    image.src = state.fileUrl;
    image.hidden = false;
  } else if (empty) {
    empty.hidden = false;
  }
}

function selectFile(file) {
  if (!file) return;
  const kind = detectKind(file);
  if (!kind) {
    showToast("Format file tidak didukung. Gunakan PDF, JPG, PNG, WEBP, atau TIFF.", "error");
    return;
  }
  releaseFileUrl();
  state.file = file;
  state.fileKind = kind;
  state.fileUrl = URL.createObjectURL(file);

  $("selectedFileInfo").hidden = false;
  $("selectedFileInfo").textContent = `${file.name} • ${(file.size / 1024 / 1024).toFixed(2)} MB`;
  $("uploadButton").disabled = false;
  $("localPreview").hidden = false;
  showPreviewIn("imagePreview", "pdfPreview");
  setProcess("IDLE", "Dokumen siap diproses", "Klik Mulai Proses OCR.", file.name);
}

const dropzone = $("dropzone");
$("documentInput").addEventListener("change", (event) => selectFile(event.target.files?.[0]));
["dragenter", "dragover"].forEach((name) => dropzone.addEventListener(name, (event) => {
  event.preventDefault();
  dropzone.classList.add("dragging");
}));
["dragleave", "drop"].forEach((name) => dropzone.addEventListener(name, (event) => {
  event.preventDefault();
  dropzone.classList.remove("dragging");
}));
dropzone.addEventListener("drop", (event) => selectFile(event.dataTransfer.files?.[0]));

$("uploadForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!state.file) return;
  const online = await checkBackend();
  if (!online) {
    showToast("Backend belum berjalan. Jalankan backend SAIPF terlebih dahulu.", "error", 7000);
    return;
  }

  const button = $("uploadButton");
  button.disabled = true;
  button.textContent = "Mengunggah dokumen…";
  try {
    const body = new FormData();
    body.append("file", state.file);
    const result = await api("/api/scans", { method: "POST", body });
    state.currentJobId = result.job_id;
    $("jobIdText").textContent = result.job_id ?? "—";
    $("jobFilenameText").textContent = result.filename || state.file.name;
    setProcess("PROCESSING", "Dokumen sedang diproses", "OCR dan NLP sedang membaca dokumen.", "Popup verifikasi akan muncul otomatis setelah selesai.");
    showToast(`Upload berhasil. Job ID ${result.job_id} sedang diproses.`, "success");
    startPolling(result.job_id);
  } catch (error) {
    setProcess("FAILED", "Upload gagal", error.message, "Periksa backend lalu coba kembali.");
    showToast(error.message, "error", 8000);
  } finally {
    button.disabled = false;
    button.textContent = "Mulai Proses OCR";
  }
});

function stopPolling() {
  if (state.pollTimer) window.clearTimeout(state.pollTimer);
  state.pollTimer = null;
}

function startPolling(jobId) {
  stopPolling();
  const poll = async () => {
    try {
      const job = await api(`/api/scans/${jobId}`);
      $("jobIdText").textContent = job.id ?? jobId;
      $("jobFilenameText").textContent = job.original_filename || state.file?.name || "—";
      $("jobEngineText").textContent = job.selected_engine || "Menunggu…";
      $("jobReliabilityText").textContent = formatPercent(job.estimated_reliability);
      const status = normalizeStatus(job.status);

      if (["PROCESSING", "UPLOADED"].includes(status)) {
        setProcess(status, "Dokumen sedang diproses", "OCR dan NLP sedang membaca dokumen.", "Halaman ini akan membuka popup verifikasi otomatis.");
        state.pollTimer = window.setTimeout(poll, POLL_INTERVAL);
        return;
      }
      if (status === "NEEDS_REVIEW") {
        stopPolling();
        setProcess(status, "Hasil siap diverifikasi", "Periksa metadata dan tabel elemen.", "Edit data bila ada hasil OCR yang salah.");
        const result = await api(`/api/scans/${jobId}/result`);
        openVerification(result);
        return;
      }
      if (status === "COMPLETED") {
        stopPolling();
        setProcess(status, "Sudah tersimpan", "Data inspeksi sudah berada di SQLite.", "Lihat pada daftar inspeksi tersimpan.");
        await loadInspections();
        return;
      }
      if (status === "FAILED") {
        stopPolling();
        setProcess(status, "Proses OCR gagal", job.error_message || "Backend tidak dapat memproses dokumen.", "Periksa log backend.");
        showToast(job.error_message || "Proses OCR gagal.", "error", 8000);
        return;
      }
      state.pollTimer = window.setTimeout(poll, POLL_INTERVAL);
    } catch (error) {
      showToast(`Gagal memeriksa job: ${error.message}`, "error");
      state.pollTimer = window.setTimeout(poll, POLL_INTERVAL * 2);
    }
  };
  poll();
}

function openModal(id) {
  $(id).classList.add("open");
  $(id).setAttribute("aria-hidden", "false");
  document.body.style.overflow = "hidden";
}

function closeModal(id) {
  $(id).classList.remove("open");
  $(id).setAttribute("aria-hidden", "true");
  if (!document.querySelector(".modal.open")) document.body.style.overflow = "";
}

$("closeVerification").addEventListener("click", () => closeModal("verificationModal"));
$("cancelReview").addEventListener("click", () => closeModal("verificationModal"));
$("closeSuccess").addEventListener("click", () => closeModal("successModal"));
$("closeDetail").addEventListener("click", () => closeModal("detailModal"));
document.querySelectorAll(".modal-backdrop").forEach((backdrop) => backdrop.addEventListener("click", () => closeModal(backdrop.parentElement.id)));
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape") document.querySelectorAll(".modal.open").forEach((modal) => closeModal(modal.id));
});

function ensureSelectOption(select, value) {
  if (!value) return;
  const exists = [...select.options].some((option) => option.value === value);
  if (!exists) select.add(new Option(value, value));
  select.value = value;
}

function openVerification(result) {
  state.currentResult = result;
  state.currentJobId = result.job.id;
  const structured = result.structured || {};
  const metadata = structured.metadata || {};

  $("reviewJobId").value = result.job.id;
  $("verificationSubtitle").textContent = `${result.job.original_filename} • Job ID ${result.job.id}`;
  $("modalFilename").textContent = result.job.original_filename || "Dokumen";
  $("metricJobId").textContent = result.job.id;
  $("metricEngine").textContent = result.job.selected_engine || "—";
  const selectedConfidence = result.job.selected_engine === "PaddleOCR" ? result.job.paddle_confidence : result.job.tesseract_confidence;
  $("metricConfidence").textContent = formatPercent(selectedConfidence);
  $("metricReliability").textContent = formatPercent(result.job.estimated_reliability);
  $("rawText").textContent = result.raw_text || "Teks OCR tidak tersedia.";

  $("formNo").value = metadata.form_no || "";
  $("revision").value = metadata.revision || "";
  $("equipmentId").value = metadata.equipment_id || "";
  $("equipmentName").value = metadata.equipment_name || "";
  $("location").value = metadata.location || "";
  $("equipmentType").value = metadata.equipment_type || "";
  $("inspectionDate").value = metadata.inspection_date || "";
  $("inspector").value = metadata.inspector || "";
  $("method").value = metadata.method || "";
  ensureSelectOption($("inspectionStatus"), normalizeStatus(metadata.status || "PENDING_REVIEW"));
  $("overallCondition").value = structured.overall_condition || "";
  $("recommendation").value = structured.recommendation || "";

  renderRows(structured.elements || []);
  setEditMode(false);
  updateWarnings();
  showPreviewIn("modalImagePreview", "modalPdfPreview", "previewUnavailable");
  openModal("verificationModal");
}

function createRow(item = {}) {
  const row = document.createElement("tr");
  row.innerHTML = `
    <td><input class="row-no" data-row-editable type="number" min="1" value="${escapeHtml(item.row_number ?? "")}" disabled></td>
    <td><input class="row-tag" data-row-editable type="text" value="${escapeHtml(item.element_tag ?? "")}" placeholder="STR-001" disabled></td>
    <td><input class="row-name" data-row-editable type="text" value="${escapeHtml(item.element_name ?? "")}" disabled></td>
    <td>
      <select class="row-category" data-row-editable disabled>
        <option value="">—</option>
        ${["A", "B", "C", "D", "E"].map((cat) => `<option value="${cat}" ${String(item.category || "").toUpperCase() === cat ? "selected" : ""}>${cat}</option>`).join("")}
      </select>
    </td>
    <td><input class="row-findings" data-row-editable type="text" value="${escapeHtml(item.findings ?? "")}" placeholder="Catatan / temuan" disabled></td>
    <td class="row-action"><button class="remove-row" type="button" title="Hapus baris">×</button></td>
  `;
  row.querySelector(".remove-row").addEventListener("click", () => {
    row.remove();
    updateSummary();
    updateWarnings();
  });
  row.querySelectorAll("input, select").forEach((field) => field.addEventListener("input", () => {
    updateSummary();
    updateWarnings();
  }));
  return row;
}

function renderRows(items) {
  const tbody = $("elementRows");
  tbody.innerHTML = "";
  items.forEach((item) => tbody.appendChild(createRow(item)));
  updateSummary();
}

function collectRows() {
  return [...$("elementRows").querySelectorAll("tr")]
    .map((row) => {
      const rowNumberText = row.querySelector(".row-no").value;
      const rowNumber = rowNumberText ? Number(rowNumberText) : null;
      const elementTag = row.querySelector(".row-tag").value.trim();
      const elementName = row.querySelector(".row-name").value.trim();
      const category = row.querySelector(".row-category").value || null;
      const findings = row.querySelector(".row-findings").value.trim() || null;
      const sourceLine = [rowNumber, elementTag, elementName, category, findings].filter((value) => value !== null && value !== "").join(" ");
      return {
        row_number: rowNumber,
        element_tag: elementTag,
        element_name: elementName,
        category,
        findings,
        source_line: sourceLine || null,
      };
    })
    .filter((item) => item.element_tag || item.element_name || item.row_number);
}

function collectStructured() {
  return {
    metadata: {
      form_no: $("formNo").value.trim() || null,
      revision: $("revision").value.trim() || null,
      equipment_id: $("equipmentId").value.trim() || null,
      equipment_name: $("equipmentName").value.trim() || null,
      location: $("location").value.trim() || null,
      equipment_type: $("equipmentType").value.trim() || null,
      inspection_date: $("inspectionDate").value || null,
      inspector: $("inspector").value.trim() || null,
      method: $("method").value.trim() || null,
      status: normalizeStatus($("inspectionStatus").value || "PENDING_REVIEW"),
    },
    elements: collectRows(),
    overall_condition: $("overallCondition").value || null,
    recommendation: $("recommendation").value.trim() || null,
    warnings: [],
  };
}

function missingNumbers(rows) {
  const values = rows.map((item) => Number(item.row_number)).filter(Number.isFinite).sort((a, b) => a - b);
  if (values.length < 2) return [];
  const missing = [];
  for (let number = values[0]; number <= values[values.length - 1]; number += 1) {
    if (!values.includes(number)) missing.push(number);
  }
  return missing;
}

function reviewIssues(structured) {
  const issues = [];
  if (!structured.metadata.equipment_id) issues.push("Equipment ID belum terisi.");
  if (!structured.metadata.inspector) issues.push("Nama inspektor belum terisi.");
  if (!structured.elements.length) issues.push("Elemen inspeksi belum ada.");
  const missing = missingNumbers(structured.elements);
  if (missing.length) issues.push(`Nomor elemen yang hilang: ${missing.join(", ")}.`);
  const badCategory = structured.elements.filter((item) => !["A", "B", "C", "D", "E"].includes(String(item.category || "").toUpperCase()));
  if (badCategory.length) issues.push(`${badCategory.length} elemen belum memiliki kategori A–E.`);
  return issues;
}

function updateWarnings() {
  const box = $("reviewWarning");
  const issues = reviewIssues(collectStructured());
  if (!issues.length) {
    box.hidden = true;
    box.innerHTML = "";
    return;
  }
  box.hidden = false;
  box.innerHTML = `<strong>Perlu diperiksa:</strong><ul>${issues.map((issue) => `<li>${escapeHtml(issue)}</li>`).join("")}</ul>`;
}

function updateSummary() {
  const rows = collectRows();
  const counts = { A: 0, B: 0, C: 0, D: 0, E: 0 };
  rows.forEach((item) => { if (item.category in counts) counts[item.category] += 1; });
  $("categorySummary").innerHTML = [
    `<span class="summary-chip">Total: ${rows.length}</span>`,
    ...Object.entries(counts).map(([cat, count]) => `<span class="summary-chip cat-${cat}">${cat}: ${count}</span>`),
  ].join("");
}

function setEditMode(enabled) {
  state.editMode = enabled;
  document.body.classList.toggle("edit-mode", enabled);
  document.querySelectorAll("[data-editable], [data-row-editable]").forEach((field) => { field.disabled = !enabled; });
  document.querySelectorAll(".edit-only").forEach((element) => { element.hidden = !enabled; });
  $("editModeBadge").textContent = enabled ? "Mode edit aktif" : "Mode lihat";
  $("editToggleButton").textContent = enabled ? "Selesai edit" : "Belum benar — Edit data";
}

$("editToggleButton").addEventListener("click", () => setEditMode(!state.editMode));

$("addRowButton").addEventListener("click", () => {
  const rows = collectRows();
  const numbers = rows.map((item) => Number(item.row_number)).filter(Number.isFinite);
  const next = numbers.length ? Math.max(...numbers) + 1 : 1;
  const row = createRow({ row_number: next, element_tag: `STR-${String(next).padStart(3, "0")}` });
  $("elementRows").appendChild(row);
  row.querySelectorAll("[data-row-editable]").forEach((field) => { field.disabled = false; });
  updateSummary();
  updateWarnings();
  row.scrollIntoView({ behavior: "smooth", block: "center" });
});

$("addMissingButton").addEventListener("click", () => {
  const missing = missingNumbers(collectRows());
  if (!missing.length) {
    showToast("Tidak ada nomor elemen yang hilang.", "info");
    return;
  }
  missing.forEach((number) => {
    const row = createRow({ row_number: number, element_tag: `STR-${String(number).padStart(3, "0")}` });
    $("elementRows").appendChild(row);
    row.querySelectorAll("[data-row-editable]").forEach((field) => { field.disabled = false; });
  });
  const sorted = [...$("elementRows").children].sort((a, b) => Number(a.querySelector(".row-no").value) - Number(b.querySelector(".row-no").value));
  sorted.forEach((row) => $("elementRows").appendChild(row));
  updateSummary();
  updateWarnings();
  showToast(`Baris ${missing.join(", ")} ditambahkan. Lengkapi nama, kategori, dan temuannya.`, "success", 6500);
});

$("confirmSaveButton").addEventListener("click", async () => {
  const structured = collectStructured();
  const issues = reviewIssues(structured);
  if (!structured.metadata.equipment_id || !structured.metadata.inspector || !structured.elements.length) {
    setEditMode(true);
    updateWarnings();
    showToast("Lengkapi Equipment ID, inspektor, dan minimal satu elemen.", "error");
    return;
  }
  if (issues.length) {
    const proceed = window.confirm(`Masih ada data yang perlu diperiksa:\n\n- ${issues.join("\n- ")}\n\nTetap simpan ke SQLite?`);
    if (!proceed) {
      setEditMode(true);
      return;
    }
  }

  const jobId = Number($("reviewJobId").value);
  const button = $("confirmSaveButton");
  const oldText = button.textContent;
  button.disabled = true;
  button.textContent = "Menyimpan…";
  try {
    await api(`/api/scans/${jobId}/result`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(structured),
    });
    const response = await api(`/api/scans/${jobId}/confirm`, { method: "POST" });
    closeModal("verificationModal");
    $("savedInspectionId").textContent = response.inspection_id ?? "—";
    openModal("successModal");
    setProcess("COMPLETED", "Data berhasil disimpan", "Hasil verifikasi sudah masuk ke SQLite.", `Inspection ID ${response.inspection_id}`);
    await loadInspections();
  } catch (error) {
    showToast(error.message, "error", 9000);
  } finally {
    button.disabled = false;
    button.textContent = oldText;
  }
});

async function loadInspections() {
  const container = $("inspectionList");
  try {
    const rows = await api("/api/inspections?limit=20");
    if (!Array.isArray(rows) || !rows.length) {
      container.className = "inspection-list empty-state";
      container.textContent = "Belum ada inspeksi tersimpan.";
      return;
    }
    container.className = "inspection-list";
    container.innerHTML = rows.map((item) => `
      <div class="inspection-item">
        <div class="inspection-main">
          <strong>#${escapeHtml(item.id)} — ${escapeHtml(item.equipment_tag || "-")} · ${escapeHtml(item.equipment_name || "")}</strong>
          <small>${escapeHtml(item.inspector || "-")} • ${escapeHtml(item.inspection_date || "-")} • ${escapeHtml(item.method || "-")} • ${escapeHtml(item.status || "-")}</small>
        </div>
        <div class="inspection-actions">
          <span class="condition-chip cat-${escapeHtml(item.overall_condition || "A")}">${escapeHtml(item.overall_condition || "-")}</span>
          <button class="btn btn-light btn-small detail-button" type="button" data-id="${escapeHtml(item.id)}">Lihat detail</button>
        </div>
      </div>
    `).join("");
    container.querySelectorAll(".detail-button").forEach((button) => button.addEventListener("click", () => openDetail(button.dataset.id)));
  } catch (error) {
    container.className = "inspection-list empty-state";
    container.textContent = `Gagal membaca SQLite: ${error.message}`;
  }
}

async function openDetail(id) {
  try {
    const data = await api(`/api/inspections/${id}`);
    const inspection = data.inspection || {};
    const equipment = data.equipment || {};
    const inspector = data.inspector || {};
    $("detailTitle").textContent = `Inspeksi #${inspection.id ?? id}`;
    $("detailContent").innerHTML = `
      <div class="detail-grid">
        <div class="detail-box"><span>Equipment ID</span><strong>${escapeHtml(equipment.tag_number || "—")}</strong></div>
        <div class="detail-box"><span>Nama Equipment</span><strong>${escapeHtml(equipment.equipment_description || "—")}</strong></div>
        <div class="detail-box"><span>Inspektor</span><strong>${escapeHtml(inspector.display_name || inspector.username || "—")}</strong></div>
        <div class="detail-box"><span>Tanggal</span><strong>${escapeHtml(inspection.inspection_date || "—")}</strong></div>
        <div class="detail-box"><span>Metode</span><strong>${escapeHtml(inspection.inspection_method || "—")}</strong></div>
        <div class="detail-box"><span>Kondisi</span><strong>${escapeHtml(inspection.overall_condition || "—")}</strong></div>
      </div>
      <div class="table-scroll">
        <table class="review-table">
          <thead><tr><th>Tag</th><th>Nama Elemen</th><th>Kategori</th><th>Temuan</th></tr></thead>
          <tbody>${(data.elements || []).map((item) => `
            <tr>
              <td>${escapeHtml(item.element_tag || "—")}</td>
              <td>${escapeHtml(item.element_name || "—")}</td>
              <td><span class="summary-chip cat-${escapeHtml(item.category || "A")}">${escapeHtml(item.category || "—")}</span></td>
              <td>${escapeHtml(item.findings || "—")}</td>
            </tr>`).join("")}
          </tbody>
        </table>
      </div>
    `;
    openModal("detailModal");
  } catch (error) {
    showToast(error.message, "error");
  }
}

$("refreshInspections").addEventListener("click", loadInspections);

async function initialize() {
  const online = await checkBackend();
  if (online) await loadInspections();
}

window.addEventListener("beforeunload", releaseFileUrl);
initialize();
