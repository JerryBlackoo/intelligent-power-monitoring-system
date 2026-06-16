const els = {
  nodePill: document.querySelector("#nodePill"),
  nodeText: document.querySelector("#nodeText"),
  overallStatus: document.querySelector("#overallStatus"),
  warningCount: document.querySelector("#warningCount"),
  criticalCount: document.querySelector("#criticalCount"),
  lastInspection: document.querySelector("#lastInspection"),
  modelVersion: document.querySelector("#modelVersion"),
  frame: document.querySelector("#frame"),
  emptyFrame: document.querySelector("#emptyFrame"),
  alertsBody: document.querySelector("#alertsBody"),
  recordsBody: document.querySelector("#recordsBody"),
  logBox: document.querySelector("#logBox"),
  refreshBtn: document.querySelector("#refreshBtn"),
  mockBtn: document.querySelector("#mockBtn"),
  reportBtn: document.querySelector("#reportBtn"),
  explainBtn: document.querySelector("#explainBtn"),
};

const mockPayload = {
  node_id: "atlas_01",
  device_id: "cabinet_01",
  captured_at: "2026-06-16 15:30:00",
  image_uri: "/images/rec_001.jpg",
  model_version: "yolov5s-power-v1",
  detections: [
    {
      label: "red_indicator",
      confidence: 0.91,
      bbox: [120, 80, 60, 40],
      status: "warning",
      description: "检测到红色告警指示灯",
    },
    {
      label: "meter",
      confidence: 0.87,
      bbox: [260, 100, 90, 90],
      status: "normal",
      description: "检测到仪表区域",
    },
  ],
};

function writeLog(message) {
  const time = new Date().toLocaleTimeString("zh-CN", { hour12: false });
  els.logBox.textContent = `[${time}] ${message}\n` + els.logBox.textContent;
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  const body = await response.json();
  if (!response.ok || body.code >= 400) {
    throw new Error(body.message || body.detail || `请求失败：${path}`);
  }
  return body.data;
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

function tag(value) {
  return `<span class="tag ${value || "normal"}">${statusLabel(value)}</span>`;
}

function setNode(node) {
  const dot = els.nodePill.querySelector(".dot");
  dot.className = "dot";
  if (!node) {
    dot.classList.add("dot-muted");
    els.nodeText.textContent = "等待边缘节点";
    return;
  }
  dot.classList.add(node.status === "online" ? "dot-online" : "dot-muted");
  els.nodeText.textContent = `${node.node_id} · ${node.status}`;
}

function clearDetections() {
  els.frame.querySelectorAll(".detection-box").forEach((box) => box.remove());
}

function drawDetections(record) {
  clearDetections();
  if (!record || !record.detections || record.detections.length === 0) {
    els.emptyFrame.style.display = "block";
    return;
  }
  els.emptyFrame.style.display = "none";
  const scaleX = els.frame.clientWidth / 640;
  const scaleY = els.frame.clientHeight / 420;
  for (const detection of record.detections) {
    const [x, y, width, height] = detection.bbox;
    const box = document.createElement("div");
    box.className = `detection-box ${detection.status}`;
    box.style.left = `${x * scaleX}px`;
    box.style.top = `${y * scaleY}px`;
    box.style.width = `${width * scaleX}px`;
    box.style.height = `${height * scaleY}px`;
    box.innerHTML = `<span>${detection.label} ${(detection.confidence * 100).toFixed(0)}%</span>`;
    els.frame.appendChild(box);
  }
}

function renderAlerts(alerts) {
  if (!alerts.length) {
    els.alertsBody.innerHTML = `<tr><td colspan="5">当前没有未关闭告警</td></tr>`;
    return;
  }
  els.alertsBody.innerHTML = alerts.map((alert) => `
    <tr>
      <td>${alert.alert_id}</td>
      <td>${alert.device_id || "-"}</td>
      <td>${tag(alert.level)}</td>
      <td>${alert.description}</td>
      <td>${alert.status}</td>
    </tr>
  `).join("");
}

function renderRecords(records) {
  if (!records.length) {
    els.recordsBody.innerHTML = `<tr><td colspan="5">暂无巡检记录</td></tr>`;
    return;
  }
  els.recordsBody.innerHTML = records.map((record) => `
    <tr>
      <td>${record.record_id}</td>
      <td>${record.device_id || "-"}</td>
      <td>${record.inspected_at}</td>
      <td>${tag(record.overall_status)}</td>
      <td>${record.alert_count}</td>
    </tr>
  `).join("");
}

async function refreshDashboard() {
  const [latest, alerts, records] = await Promise.all([
    api("/api/status/latest"),
    api("/api/alerts/active"),
    api("/api/records?page=1&page_size=8"),
  ]);

  setNode(latest.edge_node);
  const record = latest.latest_record;
  els.overallStatus.textContent = statusLabel(record?.overall_status);
  els.warningCount.textContent = latest.summary?.warning_count ?? 0;
  els.criticalCount.textContent = latest.summary?.critical_count ?? 0;
  els.lastInspection.textContent = record?.inspected_at || "--";
  els.modelVersion.textContent = `model: ${record?.model_version || latest.edge_node?.model_version || "--"}`;
  drawDetections(record);
  renderAlerts(alerts);
  renderRecords(records.items || []);
}

async function uploadMock() {
  await api("/api/edge/heartbeat", {
    method: "POST",
    body: JSON.stringify({
      node_id: "atlas_01",
      ip: "192.168.1.88",
      status: "online",
      model_version: "yolov5s-power-v1",
      timestamp: "2026-06-16 15:29:59",
    }),
  });
  const result = await api("/api/edge/inference", {
    method: "POST",
    body: JSON.stringify({ ...mockPayload, record_id: `rec_${Date.now()}` }),
  });
  writeLog(`已上传模拟推理，生成告警 ${result.alert_count} 条。`);
  await refreshDashboard();
}

async function generateReport() {
  const data = await api("/api/reports", {
    method: "POST",
    body: JSON.stringify({
      start_time: "2026-06-16 00:00:00",
      end_time: "2026-06-16 23:59:59",
      format: "html",
      include_images: true,
    }),
  });
  writeLog(`报告已生成：${data.file_uri}`);
  window.open(data.file_uri, "_blank");
}

async function explainFirstAlert() {
  const alerts = await api("/api/alerts/active");
  if (!alerts.length) {
    writeLog("当前没有可解释的告警。");
    return;
  }
  const advice = await api("/api/llm/explain", {
    method: "POST",
    body: JSON.stringify({ alert_id: alerts[0].alert_id }),
  });
  writeLog(`${advice.summary}\n处理建议：${advice.action_steps.join("；")}`);
}

els.refreshBtn.addEventListener("click", () => refreshDashboard().then(() => writeLog("数据已刷新。")).catch((error) => writeLog(error.message)));
els.mockBtn.addEventListener("click", () => uploadMock().catch((error) => writeLog(error.message)));
els.reportBtn.addEventListener("click", () => generateReport().catch((error) => writeLog(error.message)));
els.explainBtn.addEventListener("click", () => explainFirstAlert().catch((error) => writeLog(error.message)));
window.addEventListener("resize", () => refreshDashboard().catch(() => {}));

refreshDashboard().catch((error) => writeLog(error.message));
