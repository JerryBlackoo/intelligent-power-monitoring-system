const els = {
  roleShells: document.querySelectorAll("[data-role-shell]"),
  monitorShell: document.querySelector("#monitorShell"),
  inspectorShell: document.querySelector("#inspectorShell"),
  adminShell: document.querySelector("#adminShell"),
  nodePill: document.querySelector("#nodePill"),
  nodeText: document.querySelector("#nodeText"),
  edgeLiveMeta: document.querySelector("#edgeLiveMeta"),
  frame: document.querySelector("#frame"),
  emptyFrame: document.querySelector("#emptyFrame"),
  inferenceFrame: document.querySelector("#inferenceFrame"),
  emptyInferenceFrame: document.querySelector("#emptyInferenceFrame"),
  edgeRecordsBody: document.querySelector("#edgeRecordsBody"),
  inspectorRecordsBody: document.querySelector("#inspectorRecordsBody"),
  alertsBody: document.querySelector("#alertsBody"),
  alertsMeta: document.querySelector("#alertsMeta"),
  edgeRecordsView: document.querySelector("#edgeRecordsView"),
  inspectorRecordsView: document.querySelector("#inspectorRecordsView"),
  recordTabs: document.querySelectorAll("[data-record-view]"),
  edgeRecordCount: document.querySelector("#edgeRecordCount"),
  inspectorRecordCount: document.querySelector("#inspectorRecordCount"),
  pendingRecordCount: document.querySelector("#pendingRecordCount"),
  generatedReportForm: document.querySelector("#generatedReportForm"),
  generatedReportStart: document.querySelector("#generatedReportStart"),
  generatedReportEnd: document.querySelector("#generatedReportEnd"),
  generatedReportDevice: document.querySelector("#generatedReportDevice"),
  generatedReportFormat: document.querySelector("#generatedReportFormat"),
  generatedReportSubmit: document.querySelector("#generatedReportSubmit"),
  generatedReportState: document.querySelector("#generatedReportState"),
  generatedReportResult: document.querySelector("#generatedReportResult"),
  generatedReportsBody: document.querySelector("#generatedReportsBody"),
  recordsPageInfo: document.querySelector("#recordsPageInfo"),
  prevRecordsPage: document.querySelector("#prevRecordsPage"),
  nextRecordsPage: document.querySelector("#nextRecordsPage"),
  refreshBtn: document.querySelector("#refreshBtn"),
  deviceModalBackdrop: document.querySelector("#deviceModalBackdrop"),
  deviceModalTitle: document.querySelector("#deviceModalTitle"),
  deviceModalMeta: document.querySelector("#deviceModalMeta"),
  deviceModalClose: document.querySelector("#deviceModalClose"),
  deviceList: document.querySelector("#deviceList"),
  userAvatars: document.querySelectorAll("[data-user-avatar]"),
  userNames: document.querySelectorAll("[data-user-name]"),
  userRoles: document.querySelectorAll("[data-user-role]"),
  logoutBtns: document.querySelectorAll("[data-logout]"),
  adminHomeBtn: document.querySelector("#adminHomeBtn"),
  loginScreen: document.querySelector("#loginScreen"),
  loginForm: document.querySelector("#loginForm"),
  loginUsername: document.querySelector("#loginUsername"),
  loginPassword: document.querySelector("#loginPassword"),
  loginError: document.querySelector("#loginError"),
  loginSubmit: document.querySelector("#loginSubmit"),
  inspectorNavItems: document.querySelectorAll("[data-inspector-view]"),
  inspectorPanels: document.querySelectorAll("[data-inspector-panel]"),
  reportForm: document.querySelector("#reportForm"),
  reportFile: document.querySelector("#reportFile"),
  selectedFileName: document.querySelector("#selectedFileName"),
  uploadState: document.querySelector("#uploadState"),
  uploadCount: document.querySelector("#uploadCount"),
  uploadList: document.querySelector("#uploadList"),
  reportInspectorName: document.querySelector("#reportInspectorName"),
  reportDevice: document.querySelector("#reportDevice"),
  reportRecord: document.querySelector("#reportRecord"),
  reportStatus: document.querySelector("#reportStatus"),
  reportNote: document.querySelector("#reportNote"),
  agentGreeting: document.querySelector("#agentGreeting"),
  agentForm: document.querySelector("#agentForm"),
  agentInput: document.querySelector("#agentInput"),
  agentImage: document.querySelector("#agentImage"),
  agentAttachmentName: document.querySelector("#agentAttachmentName"),
  chatThread: document.querySelector("#chatThread"),
  newChatBtn: document.querySelector("#newChatBtn"),
  adminMonitorBtn: document.querySelector("#adminMonitorBtn"),
  adminUserCount: document.querySelector("#adminUserCount"),
  adminNodeCount: document.querySelector("#adminNodeCount"),
  adminAlertCount: document.querySelector("#adminAlertCount"),
  adminReportCount: document.querySelector("#adminReportCount"),
  adminUsersBody: document.querySelector("#adminUsersBody"),
  adminNodesBody: document.querySelector("#adminNodesBody"),
};

const SESSION_KEY = "power_inspection_user";
const ALLOWED_ROLES = ["monitor", "inspector", "admin"];

const recordsState = {
  page: 1,
  pageSize: 8,
  total: 0,
  totalPages: 1,
  view: "edge",
};

let currentEdgeNode = null;
let currentUser = null;
let activeShellRole = null;
let uploadCount = 0;
let selectedAgentImageDataUrl = null;
let chatHistory = [];

async function api(path, options = {}) {
  const headers = options.body instanceof FormData
    ? { ...(options.headers || {}) }
    : { "Content-Type": "application/json", ...(options.headers || {}) };
  const response = await fetch(path, {
    headers,
    ...options,
  });
  const body = await response.json();
  if (!response.ok || body.code >= 400) {
    throw new Error(body.message || body.detail || `请求失败：${path}`);
  }
  return body.data;
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function roleHome(user) {
  return user?.role === "admin" ? "admin" : user?.role || "monitor";
}

function toDateTimeLocalValue(date) {
  const pad = (value) => String(value).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

function fromDateTimeLocalValue(value) {
  if (!value) {
    return "";
  }
  return value.replace("T", " ") + ":00";
}

function setDefaultGeneratedReportRange() {
  if (els.generatedReportStart.value && els.generatedReportEnd.value) {
    return;
  }
  const end = new Date();
  const start = new Date(end.getTime() - 24 * 60 * 60 * 1000);
  els.generatedReportStart.value = toDateTimeLocalValue(start);
  els.generatedReportEnd.value = toDateTimeLocalValue(end);
}

function showRoleShell(role) {
  activeShellRole = role;
  els.roleShells.forEach((shell) => {
    shell.classList.toggle("hidden", shell.dataset.roleShell !== role);
  });
  els.adminHomeBtn.classList.toggle("hidden", currentUser?.role !== "admin" || role === "admin");
}

async function refreshActiveShell() {
  if (!currentUser) {
    return;
  }
  if (activeShellRole === "monitor") {
    await refreshDashboard();
  } else if (activeShellRole === "inspector") {
    await refreshInspectorWorkspace();
  } else if (activeShellRole === "admin") {
    await refreshAdminWorkspace();
  }
}

function statusLabel(value) {
  const labels = {
    normal: "正常",
    pending_review: "待复核",
    warning: "一般告警",
    critical: "严重告警",
    failed: "失败",
  };
  return labels[value] || value || "--";
}

function roleLabel(role) {
  const labels = {
    monitor: "监控员",
    inspector: "巡检员",
    admin: "管理员",
  };
  return labels[role] || role || "--";
}

function tag(value) {
  return `<span class="tag ${value || "normal"}">${statusLabel(value)}</span>`;
}

function actionButton(label, action, id, disabled = false) {
  return `<button class="table-action-btn" type="button" data-action="${action}" data-id="${id}" ${disabled ? "disabled" : ""}>${label}</button>`;
}

function recordFile(record) {
  if (!record.inspection_file_uri) {
    return `<span class="muted-cell">待上传</span>`;
  }
  const label = record.inspection_file_name || "查看文件";
  return `<a class="file-link" href="${record.inspection_file_uri}" target="_blank" rel="noopener">${label}</a>`;
}

function handleStatusLabel(value) {
  const labels = {
    pending: "待处理",
    reviewing: "复核中",
    resolved: "已处理",
    closed: "已关闭",
  };
  return labels[value] || value || "待处理";
}

function handleTag(value) {
  const statusClass = {
    pending: "pending_review",
    reviewing: "warning",
    resolved: "normal",
    closed: "normal",
  }[value] || "pending_review";
  return `<span class="tag ${statusClass}">${handleStatusLabel(value)}</span>`;
}

function recordAdvice(record) {
  const advice = record.agent_advice;
  if (!advice) {
    return `<span class="muted-cell">等待 Agent 分析</span>`;
  }
  return `<span class="advice-cell" title="${advice}">${advice}</span>`;
}

function setNode(node) {
  currentEdgeNode = node || null;
  const dot = els.nodePill.querySelector(".dot");
  dot.className = "dot";
  if (!node) {
    dot.classList.add("dot-muted");
    els.nodeText.textContent = "等待边缘节点";
    els.nodePill.disabled = true;
    els.nodePill.title = "暂无边缘节点";
    return;
  }
  dot.classList.add(node.status === "online" ? "dot-online" : "dot-muted");
  els.nodeText.textContent = `${node.node_id} · ${node.status}`;
  els.nodePill.disabled = false;
  els.nodePill.title = "查看设备列表";
}

function renderDeviceList(devices) {
  if (!devices.length) {
    els.deviceList.innerHTML = `<div class="device-empty">该边缘节点暂无设备记录</div>`;
    return;
  }

  els.deviceList.innerHTML = devices.map((device) => `
    <article class="device-item">
      <div class="device-item-head">
        <strong>${device.device_id}</strong>
        <div class="device-item-actions">
          ${tag(device.latest_status)}
          <button class="device-start-btn" type="button" data-device-start="${device.device_id}">启动巡检</button>
        </div>
      </div>
      <div class="device-item-meta">
        <span>最近巡检：${device.last_inspected_at || "--"}</span>
        <span>巡检次数：${device.record_count ?? 0}</span>
      </div>
    </article>
  `).join("");
}

function openDeviceModal() {
  if (!currentEdgeNode) {
    return;
  }

  els.deviceModalTitle.textContent = "设备列表";
  els.deviceModalMeta.textContent = `node: ${currentEdgeNode.node_id} · status: ${currentEdgeNode.status}`;
  els.deviceList.textContent = "加载中...";
  els.deviceModalBackdrop.classList.remove("hidden");
  els.deviceModalBackdrop.setAttribute("aria-hidden", "false");
  document.body.style.overflow = "hidden";
  els.deviceModalClose.focus();

  api("/api/edge/nodes")
    .then((nodes) => {
      const node = (nodes || []).find((item) => item.node_id === currentEdgeNode.node_id);
      renderDeviceList(node?.devices || []);
    })
    .catch((error) => {
      els.deviceList.innerHTML = `<div class="device-empty">${error.message || "设备列表加载失败"}</div>`;
    });
}

async function startDeviceInspection(deviceId, button) {
  const originalText = button.textContent;
  button.disabled = true;
  button.textContent = "下发中";
  try {
    const command = await api(`/api/devices/${encodeURIComponent(deviceId)}/start`, {
      method: "POST",
      body: JSON.stringify({ source: "monitor", once: true }),
    });
    button.textContent = "已下发";
    els.deviceModalMeta.textContent = `command: ${command.command_id} · ${command.status} · node: ${command.node_id}`;
    window.setTimeout(() => {
      button.disabled = false;
      button.textContent = originalText;
    }, 1600);
  } catch (error) {
    button.disabled = false;
    button.textContent = "下发失败";
    els.deviceModalMeta.textContent = error.message || "命令下发失败";
    window.setTimeout(() => {
      button.textContent = originalText;
    }, 1800);
  }
}

function closeDeviceModal() {
  els.deviceModalBackdrop.classList.add("hidden");
  els.deviceModalBackdrop.setAttribute("aria-hidden", "true");
  document.body.style.overflow = "";
  if (!els.nodePill.disabled) {
    els.nodePill.focus();
  }
}

function clearDetectionBoxes(container) {
  container.querySelectorAll(".detection-box").forEach((box) => box.remove());
}

function computeContainLayout(containerWidth, containerHeight, imageWidth, imageHeight) {
  const containerRatio = containerWidth / containerHeight;
  const imageRatio = imageWidth / imageHeight;
  if (imageRatio >= containerRatio) {
    const displayWidth = containerWidth;
    const displayHeight = containerWidth / imageRatio;
    return {
      offsetX: 0,
      offsetY: (containerHeight - displayHeight) / 2,
      displayWidth,
      displayHeight,
    };
  }
  const displayHeight = containerHeight;
  const displayWidth = containerHeight * imageRatio;
  return {
    offsetX: (containerWidth - displayWidth) / 2,
    offsetY: 0,
    displayWidth,
    displayHeight,
  };
}

function loadImageSize(src) {
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.onload = () => resolve({ width: img.naturalWidth, height: img.naturalHeight });
    img.onerror = () => reject(new Error(`failed to load image: ${src}`));
    img.src = src;
  });
}

function renderFrameImage(container, emptyStateEl, record) {
  clearDetectionBoxes(container);
  const imageUri = record?.image_uri;
  container.classList.toggle("has-evidence", Boolean(imageUri));
  container.style.backgroundImage = imageUri ? `url("${imageUri}")` : "";
  emptyStateEl.style.display = imageUri ? "none" : "block";
}

async function renderFrameWithDetections(container, emptyStateEl, record) {
  renderFrameImage(container, emptyStateEl, record);
  const imageUri = record?.image_uri;
  const detections = Array.isArray(record?.detections) ? record.detections : [];

  if (!imageUri || detections.length === 0) {
    return;
  }

  try {
    const { width: imageWidth, height: imageHeight } = await loadImageSize(imageUri);
    const { offsetX, offsetY, displayWidth, displayHeight } = computeContainLayout(
      container.clientWidth,
      container.clientHeight,
      imageWidth,
      imageHeight,
    );
    const scaleX = displayWidth / imageWidth;
    const scaleY = displayHeight / imageHeight;

    for (const detection of detections) {
      const [x, y, width, height] = detection.bbox;
      const box = document.createElement("div");
      box.className = `detection-box ${detection.status}`;
      box.style.left = `${offsetX + x * scaleX}px`;
      box.style.top = `${offsetY + y * scaleY}px`;
      box.style.width = `${width * scaleX}px`;
      box.style.height = `${height * scaleY}px`;
      box.innerHTML = `<span>${detection.label} ${(detection.confidence * 100).toFixed(0)}%</span>`;
      container.appendChild(box);
    }
  } catch (error) {
    console.error(error);
  }
}

function renderEdgeRecords(records) {
  if (!records.length) {
    els.edgeRecordsBody.innerHTML = `<tr><td colspan="8">暂无边缘设备巡检记录</td></tr>`;
    return;
  }
  els.edgeRecordsBody.innerHTML = records.map((record) => `
    <tr>
      <td>${record.record_id}</td>
      <td>${record.node_id || "-"}</td>
      <td>${record.device_id || "-"}</td>
      <td>${record.model_version || "-"}</td>
      <td>
        <span class="metric-pair">
          <strong>${record.detection_count ?? 0}</strong>
          <span>/</span>
          <strong class="${Number(record.alert_count || 0) > 0 ? "alert-count" : ""}">${record.alert_count ?? 0}</strong>
        </span>
      </td>
      <td>${record.inspected_at}</td>
      <td>${tag(record.overall_status)}</td>
      <td>
        ${Number(record.active_alert_count || 0) > 0
          ? actionButton("解除告警", "resolve-record-alerts", record.record_id)
          : `<span class="muted-cell">无活跃告警</span>`}
      </td>
    </tr>
  `).join("");
}

function renderInspectorRecords(records) {
  if (!records.length) {
    els.inspectorRecordsBody.innerHTML = `<tr><td colspan="8">暂无巡检员现场记录</td></tr>`;
    return;
  }
  els.inspectorRecordsBody.innerHTML = records.map((record) => `
    <tr>
      <td>${record.record_id}</td>
      <td>${record.device_id || "-"}</td>
      <td>${record.staff_name || "待录入"}</td>
      <td>${record.inspected_at}</td>
      <td>${handleTag(record.handle_status)}</td>
      <td>${recordAdvice(record)}</td>
      <td>${recordFile(record)}</td>
      <td>
        ${record.handle_status === "resolved"
          ? `<span class="muted-cell">已完成</span>`
          : actionButton("处理完毕", "complete-record", record.record_id)}
      </td>
    </tr>
  `).join("");
}

function renderAlerts(alerts) {
  els.alertsMeta.textContent = `${alerts.length} 条活跃告警`;
  if (!alerts.length) {
    els.alertsBody.innerHTML = `<tr><td colspan="6">暂无活跃告警</td></tr>`;
    return;
  }
  els.alertsBody.innerHTML = alerts.map((alert) => `
    <tr>
      <td>${alert.alert_id}</td>
      <td>${alert.device_id || "-"}</td>
      <td>${tag(alert.level)}</td>
      <td><span class="description-cell" title="${alert.description || ""}">${alert.description || "-"}</span></td>
      <td>${alert.created_at || "-"}</td>
      <td>${actionButton("解除告警", "resolve-alert", alert.alert_id)}</td>
    </tr>
  `).join("");
}

function renderRecordSummary(records, total) {
  const inspectorReady = records.filter((record) => record.inspection_file_uri || record.agent_advice || record.handle_status !== "pending").length;
  const pending = records.filter((record) => !record.handle_status || record.handle_status === "pending").length;
  els.edgeRecordCount.textContent = String(total || records.length || 0);
  els.inspectorRecordCount.textContent = String(inspectorReady);
  els.pendingRecordCount.textContent = String(pending);
}

function reportSummaryText(summary) {
  if (!summary || typeof summary !== "object") {
    return "0";
  }
  return String(summary.record_count ?? 0);
}

function renderGeneratedReports(reports) {
  if (!reports.length) {
    els.generatedReportsBody.innerHTML = `<tr><td colspan="6">暂无生成报表</td></tr>`;
    return;
  }
  els.generatedReportsBody.innerHTML = reports.map((report) => {
    const fileName = report.file_uri ? report.file_uri.split("/").pop() : report.report_id;
    return `
      <tr>
        <td>${escapeHtml(report.report_id)}</td>
        <td>${escapeHtml(report.device_id || "全部设备")}</td>
        <td>${escapeHtml((report.format || "html").toUpperCase())}</td>
        <td>${escapeHtml(reportSummaryText(report.summary))}</td>
        <td>${escapeHtml(report.generated_at || "-")}</td>
        <td>
          ${report.file_uri
            ? `<a class="file-link" href="${escapeHtml(report.file_uri)}" target="_blank" rel="noopener">打开</a>
               <a class="file-link export-link" href="${escapeHtml(report.file_uri)}" download="${escapeHtml(fileName)}">下载</a>`
            : `<span class="muted-cell">无文件</span>`}
        </td>
      </tr>
    `;
  }).join("");
}

function populateGeneratedReportDevices(devices) {
  const current = els.generatedReportDevice.value;
  populateSelect(
    els.generatedReportDevice,
    devices || [],
    "device_id",
    (device) => `${device.device_id} · ${device.online_status || "unknown"}`,
    "全部设备",
  );
  if (current) {
    els.generatedReportDevice.value = current;
  }
}

function showGeneratedReportResult(report) {
  const fileName = report.file_uri ? report.file_uri.split("/").pop() : report.report_id;
  els.generatedReportResult.innerHTML = `
    <span>最新生成</span>
    <strong>${escapeHtml(report.report_id)} · ${escapeHtml((report.format || "html").toUpperCase())}</strong>
    <div class="generated-report-actions">
      <a class="file-link" href="${escapeHtml(report.file_uri)}" target="_blank" rel="noopener">打开报表</a>
      <a class="file-link" href="${escapeHtml(report.file_uri)}" download="${escapeHtml(fileName)}">下载导出</a>
    </div>
  `;
}

async function refreshReportCenter() {
  setDefaultGeneratedReportRange();
  const [devices, reports] = await Promise.all([
    api("/api/devices"),
    api("/api/reports?limit=20"),
  ]);
  populateGeneratedReportDevices(devices || []);
  renderGeneratedReports(reports || []);
}

async function handleGeneratedReport(event) {
  event.preventDefault();
  const startTime = fromDateTimeLocalValue(els.generatedReportStart.value);
  const endTime = fromDateTimeLocalValue(els.generatedReportEnd.value);
  if (!startTime || !endTime) {
    els.generatedReportState.textContent = "请选择时间范围";
    return;
  }

  const originalText = els.generatedReportSubmit.textContent;
  els.generatedReportSubmit.disabled = true;
  els.generatedReportSubmit.textContent = "生成中";
  els.generatedReportState.textContent = "生成中";
  try {
    const report = await api("/api/reports", {
      method: "POST",
      body: JSON.stringify({
        start_time: startTime,
        end_time: endTime,
        device_id: els.generatedReportDevice.value || null,
        format: els.generatedReportFormat.value || "html",
        include_images: true,
      }),
    });
    els.generatedReportState.textContent = "生成完成";
    showGeneratedReportResult(report);
    await refreshReportCenter();
  } catch (error) {
    els.generatedReportState.textContent = error.message || "生成失败";
  } finally {
    els.generatedReportSubmit.disabled = false;
    els.generatedReportSubmit.textContent = originalText;
  }
}

function setRecordView(view) {
  recordsState.view = view;
  const showEdge = view === "edge";
  els.edgeRecordsView.hidden = !showEdge;
  els.inspectorRecordsView.hidden = showEdge;
  els.edgeRecordsView.classList.toggle("active", showEdge);
  els.inspectorRecordsView.classList.toggle("active", !showEdge);
  els.recordTabs.forEach((tab) => {
    const active = tab.dataset.recordView === view;
    tab.classList.toggle("active", active);
    tab.setAttribute("aria-selected", active ? "true" : "false");
  });
}

function updateRecordsPagination(total) {
  recordsState.total = total || 0;
  recordsState.totalPages = Math.max(1, Math.ceil(recordsState.total / recordsState.pageSize));
  recordsState.page = Math.min(Math.max(recordsState.page, 1), recordsState.totalPages);
  els.recordsPageInfo.textContent = `第 ${recordsState.page} / ${recordsState.totalPages} 页 · 共 ${recordsState.total} 条`;
  els.prevRecordsPage.disabled = recordsState.page <= 1;
  els.nextRecordsPage.disabled = recordsState.page >= recordsState.totalPages;
}

async function refreshDashboard() {
  if (!currentUser) {
    return;
  }

  const [latest, records, alerts] = await Promise.all([
    api("/api/status/latest"),
    api(`/api/records?page=${recordsState.page}&page_size=${recordsState.pageSize}`),
    api("/api/alerts/active"),
  ]);

  setNode(latest.edge_node);
  const record = latest.latest_record;
  const edgeNode = latest.edge_node?.node_id || record?.node_id || "--";
  const edgeDevice = record?.device_id || "--";
  els.edgeLiveMeta.textContent = `node: ${edgeNode} · device: ${edgeDevice}`;
  renderFrameImage(els.frame, els.emptyFrame, record);
  await renderFrameWithDetections(els.inferenceFrame, els.emptyInferenceFrame, record);
  const recordItems = records.items || [];
  renderEdgeRecords(recordItems);
  renderInspectorRecords(recordItems);
  renderAlerts(alerts || []);
  renderRecordSummary(recordItems, records.total);
  updateRecordsPagination(records.total);
  await refreshReportCenter();
}

async function runTableAction(button) {
  const { action, id } = button.dataset;
  const originalText = button.textContent;
  const operatorName = currentUser?.username || "monitor";
  button.disabled = true;
  button.textContent = "处理中";
  try {
    if (action === "resolve-alert") {
      await api(`/api/alerts/${encodeURIComponent(id)}/resolve`, {
        method: "POST",
        body: JSON.stringify({ reviewer: operatorName, remark: "监控员解除告警" }),
      });
    } else if (action === "resolve-record-alerts") {
      await api(`/api/records/${encodeURIComponent(id)}/alerts/resolve`, { method: "POST" });
    } else if (action === "complete-record") {
      await api(`/api/records/${encodeURIComponent(id)}/complete`, {
        method: "POST",
        body: JSON.stringify({ handler: operatorName, remark: "监控员确认处理完毕", close_alerts: true }),
      });
    }
    button.textContent = "已完成";
    await refreshDashboard();
  } catch (error) {
    console.error(error);
    button.disabled = false;
    button.textContent = "失败";
    window.setTimeout(() => {
      button.textContent = originalText;
    }, 1400);
  }
}

function setInspectorView(view) {
  els.inspectorNavItems.forEach((item) => {
    item.classList.toggle("active", item.dataset.inspectorView === view);
  });
  els.inspectorPanels.forEach((panel) => {
    panel.classList.toggle("active", panel.dataset.inspectorPanel === view);
  });
}

function populateSelect(select, items, valueKey, labelFn, placeholder) {
  select.innerHTML = `<option value="">${placeholder}</option>${items.map((item) => (
    `<option value="${escapeHtml(item[valueKey])}">${escapeHtml(labelFn(item))}</option>`
  )).join("")}`;
}

async function refreshInspectorWorkspace() {
  const [devices, records] = await Promise.all([
    api("/api/devices"),
    api("/api/records?page=1&page_size=30"),
  ]);
  populateSelect(
    els.reportDevice,
    devices || [],
    "device_id",
    (device) => `${device.device_id} · ${device.online_status || "unknown"}`,
    "不指定设备",
  );
  populateSelect(
    els.reportRecord,
    records.items || [],
    "record_id",
    (record) => `${record.record_id} · ${record.device_id || "-"} · ${record.inspected_at}`,
    "不关联记录",
  );
}

function renderUploadItem(report) {
  const link = report.file_uri
    ? `<a class="file-link" href="${escapeHtml(report.file_uri)}" target="_blank" rel="noopener">${escapeHtml(report.file_name || report.report_id)}</a>`
    : escapeHtml(report.file_name || report.report_id);
  const item = document.createElement("article");
  item.className = "upload-item";
  item.innerHTML = `
    <strong>${link}</strong>
    <span>${escapeHtml(report.report_id)} · ${escapeHtml(report.device_id || "未指定设备")}</span>
  `;
  els.uploadList.prepend(item);
}

async function handleReportUpload(event) {
  event.preventDefault();
  const file = els.reportFile.files?.[0];
  if (!file) {
    els.uploadState.textContent = "请选择文件";
    return;
  }

  const formData = new FormData();
  formData.append("file", file);
  formData.append("handler", currentUser?.username || "");
  formData.append("handle_status", els.reportStatus.value || "reviewing");
  if (els.reportDevice.value) {
    formData.append("device_id", els.reportDevice.value);
  }
  if (els.reportRecord.value) {
    formData.append("record_id", els.reportRecord.value);
  }
  if (els.reportNote.value.trim()) {
    formData.append("note", els.reportNote.value.trim());
  }

  els.uploadState.textContent = "上传中";
  try {
    const report = await api("/api/reports/upload", { method: "POST", body: formData });
    uploadCount += 1;
    els.uploadCount.textContent = String(uploadCount);
    els.uploadState.textContent = "上传完成";
    renderUploadItem(report);
    els.reportForm.reset();
    els.selectedFileName.textContent = "选择巡检报告文件";
    await refreshInspectorWorkspace();
  } catch (error) {
    els.uploadState.textContent = error.message || "上传失败";
  }
}

function appendChatMessage(role, content) {
  const row = document.createElement("article");
  row.className = `chat-message ${role}`;
  row.innerHTML = `
    <span>${role === "user" ? "我" : "AI"}</span>
    <p>${escapeHtml(content)}</p>
  `;
  els.chatThread.appendChild(row);
  els.chatThread.scrollTop = els.chatThread.scrollHeight;
}

function resetAgentChat() {
  chatHistory = [];
  selectedAgentImageDataUrl = null;
  els.agentImage.value = "";
  els.agentAttachmentName.textContent = "";
  els.agentAttachmentName.classList.add("hidden");
  els.chatThread.innerHTML = "";
  appendChatMessage("assistant", "我是现场巡检 Agent，可以结合系统记录、告警和图片做分析。");
}

async function handleAgentChat(event) {
  event.preventDefault();
  const message = els.agentInput.value.trim();
  if (!message && !selectedAgentImageDataUrl) {
    return;
  }
  const outgoing = message || "请分析这张现场图片";
  els.agentInput.value = "";
  appendChatMessage("user", outgoing);
  const pending = document.createElement("article");
  pending.className = "chat-message assistant pending";
  pending.innerHTML = `<span>AI</span><p>分析中...</p>`;
  els.chatThread.appendChild(pending);

  try {
    const result = await api("/api/agent/chat", {
      method: "POST",
      body: JSON.stringify({
        message: outgoing,
        history: chatHistory,
        image_data_url: selectedAgentImageDataUrl,
      }),
    });
    pending.remove();
    const reply = result.reply || "未返回内容";
    appendChatMessage("assistant", reply);
    chatHistory.push({ role: "user", content: outgoing }, { role: "assistant", content: reply });
    selectedAgentImageDataUrl = null;
    els.agentImage.value = "";
    els.agentAttachmentName.classList.add("hidden");
  } catch (error) {
    pending.remove();
    appendChatMessage("assistant", error.message || "Agent 暂时不可用");
  }
}

function handleAgentImageChange() {
  const file = els.agentImage.files?.[0];
  if (!file) {
    return;
  }
  const reader = new FileReader();
  reader.onload = () => {
    selectedAgentImageDataUrl = reader.result;
    els.agentAttachmentName.textContent = file.name;
    els.agentAttachmentName.classList.remove("hidden");
  };
  reader.readAsDataURL(file);
}

function renderAdminUsers(users) {
  if (!users.length) {
    els.adminUsersBody.innerHTML = `<tr><td colspan="4">暂无用户</td></tr>`;
    return;
  }
  els.adminUsersBody.innerHTML = users.map((user) => `
    <tr>
      <td>${escapeHtml(user.username)}</td>
      <td>${escapeHtml(roleLabel(user.role))}</td>
      <td>${escapeHtml(user.status || "-")}</td>
      <td>${escapeHtml(user.created_at || "-")}</td>
    </tr>
  `).join("");
}

function renderAdminNodes(nodes) {
  if (!nodes.length) {
    els.adminNodesBody.innerHTML = `<tr><td colspan="4">暂无边缘节点</td></tr>`;
    return;
  }
  els.adminNodesBody.innerHTML = nodes.map((node) => `
    <tr>
      <td>${escapeHtml(node.node_id)}</td>
      <td>${escapeHtml(node.status || "-")}</td>
      <td>${escapeHtml(node.model_version || "-")}</td>
      <td>${escapeHtml((node.devices || []).length)}</td>
    </tr>
  `).join("");
}

async function refreshAdminWorkspace() {
  const [users, nodes, alerts, reports] = await Promise.all([
    api("/api/users/list"),
    api("/api/edge/nodes"),
    api("/api/alerts/active"),
    api("/api/reports?limit=50"),
  ]);
  els.adminUserCount.textContent = String((users || []).length);
  els.adminNodeCount.textContent = String((nodes || []).length);
  els.adminAlertCount.textContent = String((alerts || []).length);
  els.adminReportCount.textContent = String((reports || []).length);
  renderAdminUsers(users || []);
  renderAdminNodes(nodes || []);
}

function setUserDisplay(user) {
  const username = user?.username || "--";
  els.userNames.forEach((item) => {
    item.textContent = username;
  });
  els.userRoles.forEach((item) => {
    item.textContent = roleLabel(user?.role);
  });
  els.userAvatars.forEach((item) => {
    item.textContent = (user?.username || "U").charAt(0).toUpperCase();
  });
  els.reportInspectorName.textContent = username;
  els.agentGreeting.textContent = `现场智能问答 · ${username}`;
}

function showLogin(message = "") {
  currentUser = null;
  activeShellRole = null;
  document.body.classList.add("auth-locked");
  els.roleShells.forEach((shell) => shell.classList.add("hidden"));
  els.loginScreen.classList.remove("hidden");
  els.loginScreen.setAttribute("aria-hidden", "false");
  els.loginError.textContent = message;
  setUserDisplay(null);
  window.setTimeout(() => els.loginUsername.focus(), 0);
}

function hideLogin() {
  document.body.classList.remove("auth-locked");
  els.loginScreen.classList.add("hidden");
  els.loginScreen.setAttribute("aria-hidden", "true");
}

function loadSessionUser() {
  try {
    return JSON.parse(localStorage.getItem(SESSION_KEY) || "null");
  } catch (error) {
    localStorage.removeItem(SESSION_KEY);
    return null;
  }
}

async function handleLogin(event) {
  event.preventDefault();
  const username = els.loginUsername.value.trim();
  const password = els.loginPassword.value;
  if (!username || !password) {
    els.loginError.textContent = "请输入用户名和密码";
    return;
  }

  const originalText = els.loginSubmit.textContent;
  els.loginSubmit.disabled = true;
  els.loginSubmit.textContent = "登录中";
  els.loginError.textContent = "";

  try {
    const user = await api("/api/auth/login", {
      method: "POST",
      body: JSON.stringify({ username, password }),
    });
    if (!ALLOWED_ROLES.includes(user.role)) {
      throw new Error("当前角色暂不支持登录");
    }
    currentUser = user;
    localStorage.setItem(SESSION_KEY, JSON.stringify(user));
    setUserDisplay(user);
    hideLogin();
    showRoleShell(roleHome(user));
    els.loginPassword.value = "";
    if (user.role === "inspector") {
      resetAgentChat();
      setInspectorView("report");
    }
    await refreshActiveShell();
  } catch (error) {
    localStorage.removeItem(SESSION_KEY);
    showLogin(error.message || "登录失败");
  } finally {
    els.loginSubmit.disabled = false;
    els.loginSubmit.textContent = originalText;
  }
}

function handleLogout() {
  localStorage.removeItem(SESSION_KEY);
  closeDeviceModal();
  chatHistory = [];
  selectedAgentImageDataUrl = null;
  showLogin("已退出登录");
}

function boot() {
  const sessionUser = loadSessionUser();
  if (!sessionUser || !ALLOWED_ROLES.includes(sessionUser.role)) {
    showLogin();
    return;
  }
  currentUser = sessionUser;
  setUserDisplay(sessionUser);
  hideLogin();
  showRoleShell(roleHome(sessionUser));
  if (sessionUser.role === "inspector") {
    resetAgentChat();
  }
  refreshActiveShell().catch((error) => console.error(error));
}

els.refreshBtn.addEventListener("click", () => refreshDashboard().catch((error) => console.error(error)));
els.nodePill.addEventListener("click", () => openDeviceModal());
els.deviceModalClose.addEventListener("click", () => closeDeviceModal());
els.deviceModalBackdrop.addEventListener("click", (event) => {
  if (event.target === els.deviceModalBackdrop) {
    closeDeviceModal();
  }
});
els.deviceList.addEventListener("click", (event) => {
  const button = event.target.closest("[data-device-start]");
  if (!button) {
    return;
  }
  startDeviceInspection(button.dataset.deviceStart, button);
});
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && !els.deviceModalBackdrop.classList.contains("hidden")) {
    closeDeviceModal();
  }
});
els.prevRecordsPage.addEventListener("click", () => {
  if (recordsState.page > 1) {
    recordsState.page -= 1;
    refreshDashboard().catch((error) => console.error(error));
  }
});
els.nextRecordsPage.addEventListener("click", () => {
  if (recordsState.page < recordsState.totalPages) {
    recordsState.page += 1;
    refreshDashboard().catch((error) => console.error(error));
  }
});
els.recordTabs.forEach((tab) => {
  tab.addEventListener("click", () => setRecordView(tab.dataset.recordView));
});
els.inspectorNavItems.forEach((item) => {
  item.addEventListener("click", () => setInspectorView(item.dataset.inspectorView));
});
document.addEventListener("click", (event) => {
  const button = event.target.closest("[data-action]");
  if (!button) {
    return;
  }
  runTableAction(button);
});
els.loginForm.addEventListener("submit", (event) => handleLogin(event));
els.logoutBtns.forEach((button) => {
  button.addEventListener("click", () => handleLogout());
});
els.generatedReportForm.addEventListener("submit", (event) => handleGeneratedReport(event));
els.reportForm.addEventListener("submit", (event) => handleReportUpload(event));
els.reportFile.addEventListener("change", () => {
  const file = els.reportFile.files?.[0];
  els.selectedFileName.textContent = file ? file.name : "选择巡检报告文件";
});
els.agentForm.addEventListener("submit", (event) => handleAgentChat(event));
els.agentImage.addEventListener("change", () => handleAgentImageChange());
els.newChatBtn.addEventListener("click", () => resetAgentChat());
els.adminMonitorBtn.addEventListener("click", () => {
  showRoleShell("monitor");
  refreshDashboard().catch((error) => console.error(error));
});
els.adminHomeBtn.addEventListener("click", () => {
  showRoleShell("admin");
  refreshAdminWorkspace().catch((error) => console.error(error));
});
window.addEventListener("resize", () => {
  if (currentUser && activeShellRole === "monitor") {
    refreshDashboard().catch(() => {});
  }
});

boot();
