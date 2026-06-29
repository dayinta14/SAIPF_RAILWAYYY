"use strict";

const dashboardState = {
  charts: {},
  optionsLoaded: false,
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
  const number = Number(value || 0);
  return `${number.toFixed(2)}%`;
}

function formatDate(value) {
  if (!value) return "—";

  const date = new Date(`${value}T00:00:00`);

  if (Number.isNaN(date.getTime())) return value;

  return new Intl.DateTimeFormat("id-ID", {
    day: "2-digit",
    month: "short",
    year: "numeric",
  }).format(date);
}

function formatDateTime(value) {
  if (!value) return "—";

  const date = new Date(value);

  if (Number.isNaN(date.getTime())) return value;

  return new Intl.DateTimeFormat("id-ID", {
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

function statusClass(value) {
  const normalized = normalizeStatus(value).toLowerCase().replaceAll("_", "-");

  if (normalized === "completed") return "status-pill-completed";
  if (normalized === "failed") return "status-pill-failed";
  if (normalized === "needs-review") return "status-pill-needs-review";

  return "";
}

function setConnection(online, text) {
  const box = $("dashboardConnection");

  box.className = `connection ${
    online ? "connection-online" : "connection-offline"
  }`;

  $("dashboardConnectionText").textContent = text;
}

function showDashboardToast(message, type = "info", duration = 4500) {
  const toast = document.createElement("div");
  toast.className = `toast toast-${type}`;
  toast.textContent = message;
  $("dashboardToastContainer").appendChild(toast);

  window.setTimeout(() => toast.remove(), duration);
}

async function api(path, options = {}) {
  const response = await fetch(path, options);
  const text = await response.text();

  let body = null;

  if (text) {
    try {
      body = JSON.parse(text);
    } catch {
      body = text;
    }
  }

  if (!response.ok) {
    const detail = body?.detail || body || `HTTP ${response.status}`;

    throw new Error(
      typeof detail === "string"
        ? detail
        : JSON.stringify(detail)
    );
  }

  return body;
}

function buildQuery() {
  const params = new URLSearchParams();

  const values = {
    date_from: $("filterDateFrom").value,
    date_to: $("filterDateTo").value,
    plant_id: $("filterPlant").value,
    section: $("filterSection").value,
    equipment_type: $("filterEquipmentType").value,
    overall_condition: $("filterCondition").value,
    status: $("filterStatus").value,
  };

  Object.entries(values).forEach(([key, value]) => {
    if (value) params.set(key, value);
  });

  return params.toString();
}

function populateSelect(selectId, values, emptyLabel) {
  const select = $(selectId);
  const current = select.value;

  select.innerHTML = `<option value="">${escapeHtml(emptyLabel)}</option>`;

  (values || []).forEach((value) => {
    select.add(new Option(value, value));
  });

  if ([...select.options].some((option) => option.value === current)) {
    select.value = current;
  }
}

function fillFilterOptions(options) {
  populateSelect("filterPlant", options.plants, "Semua plant");
  populateSelect("filterSection", options.sections, "Semua section");
  populateSelect(
    "filterEquipmentType",
    options.equipment_types,
    "Semua tipe"
  );
  populateSelect("filterStatus", options.statuses, "Semua status");
}

function setKpi(summary) {
  $("kpiTotalScans").textContent = summary.total_scans ?? 0;
  $("kpiTotalInspections").textContent = summary.total_inspections ?? 0;
  $("kpiTotalEquipment").textContent = summary.total_equipment ?? 0;
  $("kpiCriticalEquipment").textContent = summary.critical_equipment ?? 0;
  $("kpiCriticalFindings").textContent = summary.critical_findings ?? 0;
  $("kpiPendingReview").textContent = summary.pending_review ?? 0;
  $("kpiThisMonth").textContent = summary.inspections_this_month ?? 0;
  $("kpiReliability").textContent = formatPercent(summary.average_reliability);
}

function destroyChart(key) {
  if (dashboardState.charts[key]) {
    dashboardState.charts[key].destroy();
  }
}

function createChart(key, canvasId, config) {
  destroyChart(key);

  dashboardState.charts[key] = new Chart(
    document.getElementById(canvasId),
    config
  );
}

function renderCharts(data) {
  const condition = data.inspection_condition_distribution || {};
  const element = data.element_category_distribution || {};
  const status = data.scan_status_distribution || {};
  const monthly = data.monthly_inspection_trend || [];

  createChart("condition", "conditionChart", {
    type: "doughnut",
    data: {
      labels: ["A", "B", "C", "D", "E"],
      datasets: [{
        data: ["A", "B", "C", "D", "E"].map(
          (key) => condition[key] || 0
        ),
        backgroundColor: [
          "#168348",
          "#1d67b1",
          "#d89a00",
          "#ef7c20",
          "#b42318",
        ],
        borderWidth: 0,
        hoverOffset: 5,
      }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: {
          position: "bottom",
        },
      },
    },
  });

  createChart("monthly", "monthlyChart", {
    type: "line",
    data: {
      labels: monthly.map((item) => item.month),
      datasets: [{
        label: "Total inspeksi",
        data: monthly.map((item) => item.total),
        borderColor: "#1d67b1",
        backgroundColor: "rgba(29, 103, 177, .13)",
        fill: true,
        tension: .32,
        pointRadius: 4,
      }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      scales: {
        y: {
          beginAtZero: true,
          ticks: {
            precision: 0,
          },
        },
      },
    },
  });

  createChart("element", "elementChart", {
    type: "bar",
    data: {
      labels: ["A", "B", "C", "D", "E"],
      datasets: [{
        label: "Jumlah elemen",
        data: ["A", "B", "C", "D", "E"].map(
          (key) => element[key] || 0
        ),
        backgroundColor: [
          "#168348",
          "#1d67b1",
          "#d89a00",
          "#ef7c20",
          "#b42318",
        ],
        borderRadius: 8,
      }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      scales: {
        y: {
          beginAtZero: true,
          ticks: {
            precision: 0,
          },
        },
      },
      plugins: {
        legend: {
          display: false,
        },
      },
    },
  });

  createChart("scanStatus", "scanStatusChart", {
    type: "bar",
    data: {
      labels: Object.keys(status),
      datasets: [{
        label: "Jumlah scan",
        data: Object.values(status),
        backgroundColor: "#148b83",
        borderRadius: 8,
      }],
    },
    options: {
      indexAxis: "y",
      responsive: true,
      maintainAspectRatio: false,
      scales: {
        x: {
          beginAtZero: true,
          ticks: {
            precision: 0,
          },
        },
      },
      plugins: {
        legend: {
          display: false,
        },
      },
    },
  });
}

function renderCriticalTable(rows) {
  const tbody = $("criticalTableBody");
  $("criticalCountBadge").textContent = `${rows.length} data`;

  if (!rows.length) {
    tbody.innerHTML = `
      <tr>
        <td colspan="8">
          <div class="dashboard-empty">
            Tidak ada equipment kritis pada filter ini.
          </div>
        </td>
      </tr>
    `;
    return;
  }

  tbody.innerHTML = rows.map((item) => `
    <tr>
      <td><strong>${escapeHtml(item.tag_number || "—")}</strong></td>
      <td>${escapeHtml(item.equipment_name || "—")}</td>
      <td>
        ${escapeHtml(item.plant_id || "—")}
        <br>
        <small>${escapeHtml(item.section || "—")}</small>
      </td>
      <td>${escapeHtml(formatDate(item.inspection_date))}</td>
      <td>
        <span class="condition-chip cat-${escapeHtml(item.overall_condition || "E")}">
          ${escapeHtml(item.overall_condition || "—")}
        </span>
      </td>
      <td>${escapeHtml(item.critical_findings ?? 0)}</td>
      <td>
        <span class="status-pill ${statusClass(item.status)}">
          ${escapeHtml(item.status || "—")}
        </span>
      </td>
      <td>
        <button
          class="btn btn-light btn-small critical-detail-button"
          type="button"
          data-id="${escapeHtml(item.inspection_id)}"
        >
          Detail
        </button>
      </td>
    </tr>
  `).join("");

  tbody.querySelectorAll(".critical-detail-button").forEach((button) => {
    button.addEventListener("click", () => openInspectionDetail(button.dataset.id));
  });
}

function renderRecentInspections(rows) {
  const container = $("recentInspectionList");

  if (!rows.length) {
    container.innerHTML = `
      <div class="dashboard-empty">
        Belum ada inspeksi pada filter ini.
      </div>
    `;
    return;
  }

  container.innerHTML = rows.map((item) => `
    <div class="dashboard-list-item">
      <div class="dashboard-list-main">
        <strong>
          #${escapeHtml(item.id)}
          · ${escapeHtml(item.equipment_tag || "—")}
          · ${escapeHtml(item.equipment_name || "")}
        </strong>
        <small>
          ${escapeHtml(item.inspector || "—")}
          · ${escapeHtml(formatDate(item.inspection_date))}
          · ${escapeHtml(item.method || "—")}
          · ${escapeHtml(item.plant_id || "—")}
        </small>
      </div>
      <div class="dashboard-list-side">
        <span class="condition-chip cat-${escapeHtml(item.overall_condition || "A")}">
          ${escapeHtml(item.overall_condition || "—")}
        </span>
        <button
          class="btn btn-light btn-small inspection-detail-button"
          type="button"
          data-id="${escapeHtml(item.id)}"
        >
          Detail
        </button>
      </div>
    </div>
  `).join("");

  container.querySelectorAll(".inspection-detail-button").forEach((button) => {
    button.addEventListener("click", () => openInspectionDetail(button.dataset.id));
  });
}

function renderRecentScans(rows) {
  const container = $("recentScanList");

  if (!rows.length) {
    container.innerHTML = `
      <div class="dashboard-empty">
        Belum ada riwayat scan.
      </div>
    `;
    return;
  }

  container.innerHTML = rows.map((item) => `
    <div class="dashboard-list-item">
      <div class="dashboard-list-main">
        <strong>
          Job #${escapeHtml(item.id)}
          · ${escapeHtml(item.original_filename || "—")}
        </strong>
        <small>
          ${escapeHtml(item.selected_engine || "Belum dipilih")}
          · ${formatPercent(item.estimated_reliability || 0)}
          · ${escapeHtml(formatDateTime(item.created_at))}
        </small>
      </div>
      <div class="dashboard-list-side">
        <span class="status-pill ${statusClass(item.status)}">
          ${escapeHtml(item.status || "—")}
        </span>
      </div>
    </div>
  `).join("");
}

function openModal() {
  const modal = $("dashboardDetailModal");
  modal.classList.add("open");
  modal.setAttribute("aria-hidden", "false");
  document.body.style.overflow = "hidden";
}

function closeModal() {
  const modal = $("dashboardDetailModal");
  modal.classList.remove("open");
  modal.setAttribute("aria-hidden", "true");
  document.body.style.overflow = "";
}

$("closeDashboardDetail").addEventListener("click", closeModal);

document.querySelectorAll("[data-close-dashboard-modal]").forEach((item) => {
  item.addEventListener("click", closeModal);
});

async function openInspectionDetail(id) {
  try {
    const data = await api(`/api/inspections/${id}`);
    const inspection = data.inspection || {};
    const equipment = data.equipment || {};
    const inspector = data.inspector || {};

    $("dashboardDetailTitle").textContent = `Inspeksi #${inspection.id || id}`;

    $("dashboardDetailContent").innerHTML = `
      <div class="dashboard-detail-summary">
        <div>
          <span>Equipment ID</span>
          <strong>${escapeHtml(equipment.tag_number || "—")}</strong>
        </div>
        <div>
          <span>Nama Equipment</span>
          <strong>${escapeHtml(equipment.equipment_description || "—")}</strong>
        </div>
        <div>
          <span>Inspektor</span>
          <strong>${escapeHtml(inspector.display_name || inspector.username || "—")}</strong>
        </div>
        <div>
          <span>Tanggal</span>
          <strong>${escapeHtml(formatDate(inspection.inspection_date))}</strong>
        </div>
        <div>
          <span>Metode</span>
          <strong>${escapeHtml(inspection.inspection_method || "—")}</strong>
        </div>
        <div>
          <span>Kondisi</span>
          <strong>${escapeHtml(inspection.overall_condition || "—")}</strong>
        </div>
      </div>

      <div class="dashboard-table-wrap">
        <table class="dashboard-table">
          <thead>
            <tr>
              <th>Tag</th>
              <th>Nama Elemen</th>
              <th>Kategori</th>
              <th>Temuan</th>
            </tr>
          </thead>
          <tbody>
            ${(data.elements || []).map((item) => `
              <tr>
                <td>${escapeHtml(item.element_tag || "—")}</td>
                <td>${escapeHtml(item.element_name || "—")}</td>
                <td>
                  <span class="condition-chip cat-${escapeHtml(item.category || "A")}">
                    ${escapeHtml(item.category || "—")}
                  </span>
                </td>
                <td>${escapeHtml(item.findings || "—")}</td>
              </tr>
            `).join("")}
          </tbody>
        </table>
      </div>
    `;

    openModal();
  } catch (error) {
    showDashboardToast(error.message, "error", 7000);
  }
}

async function loadDashboard() {
  const query = buildQuery();
  const url = query ? `/api/dashboard?${query}` : "/api/dashboard";

  setConnection(false, "Memuat dashboard…");

  try {
    const data = await api(url);

    setConnection(true, "Dashboard terhubung");
    setKpi(data.summary || {});

    if (!dashboardState.optionsLoaded) {
      fillFilterOptions(data.filter_options || {});
      dashboardState.optionsLoaded = true;
    }

    renderCharts(data);
    renderCriticalTable(data.critical_equipment || []);
    renderRecentInspections(data.recent_inspections || []);
    renderRecentScans(data.recent_scans || []);
  } catch (error) {
    setConnection(false, "Dashboard gagal dimuat");
    showDashboardToast(error.message, "error", 8000);
  }
}

$("dashboardFilterForm").addEventListener("submit", (event) => {
  event.preventDefault();
  loadDashboard();
});

$("resetFilter").addEventListener("click", () => {
  $("dashboardFilterForm").reset();
  loadDashboard();
});

$("refreshDashboard").addEventListener("click", loadDashboard);

loadDashboard();
