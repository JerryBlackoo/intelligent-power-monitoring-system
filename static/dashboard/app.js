const els = {
  loginScreen: document.querySelector("#loginScreen"),
  loginForm: document.querySelector("#loginForm"),
  loginUsername: document.querySelector("#loginUsername"),
  loginPassword: document.querySelector("#loginPassword"),
  loginError: document.querySelector("#loginError"),
  loginSubmit: document.querySelector("#loginSubmit"),
  userAvatar: document.querySelector("#userAvatar"),
  userName: document.querySelector("#userName"),
  userRole: document.querySelector("#userRole"),
  logoutBtn: document.querySelector("#logoutBtn"),
  navItems: document.querySelectorAll("[data-inspector-view]"),
  viewPanels: document.querySelectorAll("[data-view-panel]"),
  agentGreeting: document.querySelector("#agentGreeting"),
  agentForm: document.querySelector("#agentForm"),
  agentInput: document.querySelector("#agentInput"),
  agentImage: document.querySelector("#agentImage"),
  agentAttachmentName: document.querySelector("#agentAttachmentName"),
  chatThread: document.querySelector("#chatThread"),
  newChatBtn: document.querySelector("#newChatBtn"),
  suggestionButtons: document.querySelectorAll("[data-prompt]"),
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
};

const SESSION_KEY = "power_inspection_user";

let currentUser = null;
let uploadCount = 0;
let selectedAgentImageDataUrl = null;

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

function roleLabel(role) {
  const labels = {
    monitor: "监控员",
    inspector: "巡检员",
    admin: "管理员",
  };
  return labels[role] || role || "--";
}

function setUserDisplay(user) {
  const username = user?.username || "--";
  els.userName.textContent = username;
  els.userRole.textContent = roleLabel(user?.role);
  els.userAvatar.textContent = username.charAt(0).toUpperCase();
  els.reportInspectorName.textContent = username;
  els.agentGreeting.textContent = `嗨，${username}。开始现场问答`;
}

function showLogin(message = "") {
  currentUser = null;
  document.body.classList.add("auth-locked");
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
    if (user.role !== "inspector") {
      throw new Error("请使用巡检员账号登录");
    }
    currentUser = user;
    localStorage.setItem(SESSION_KEY, JSON.stringify(user));
    setUserDisplay(user);
    hideLogin();
    els.loginPassword.value = "";
    setInspectorView("agent");
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
  showLogin("已退出登录");
}

function setInspectorView(view) {
  els.navItems.forEach((item) => {
    const active = item.dataset.inspectorView === view;
    item.classList.toggle("active", active);
    item.setAttribute("aria-selected", active ? "true" : "false");
  });
  els.viewPanels.forEach((panel) => {
    const active = panel.dataset.viewPanel === view;
    panel.classList.toggle("active", active);
    panel.hidden = !active;
  });
  if (view === "agent") {
    window.setTimeout(() => els.agentInput.focus(), 0);
  }
}

function addChatMessage(type, text) {
  const article = document.createElement("article");
  article.className = `chat-message ${type}`;
  const avatar = document.createElement("span");
  const content = document.createElement("p");
  avatar.textContent = type === "user" ? "我" : "AI";
  content.textContent = text;
  article.append(avatar, content);
  els.chatThread.appendChild(article);
  els.chatThread.scrollTop = els.chatThread.scrollHeight;
  return article;
}

function collectChatHistory() {
  return Array.from(els.chatThread.querySelectorAll(".chat-message"))
    .slice(-8)
    .map((item) => ({
      role: item.classList.contains("user") ? "user" : "assistant",
      content: item.querySelector("p")?.textContent || "",
    }))
    .filter((item) => item.content);
}

async function handleAgentSubmit(event) {
  event.preventDefault();
  const text = els.agentInput.value.trim();
  if (!text) {
    return;
  }
  const history = collectChatHistory();
  addChatMessage("user", text);
  els.agentInput.value = "";
  const pending = addChatMessage("assistant", "正在分析巡检数据...");
  try {
    const result = await api("/api/agent/chat", {
      method: "POST",
      body: JSON.stringify({
        message: text,
        history,
        image_data_url: selectedAgentImageDataUrl,
      }),
    });
    const toolText = Array.isArray(result.tool_calls) && result.tool_calls.length
      ? `\n\n调用工具：${result.tool_calls.map((tool) => tool.name).join("、")}`
      : "";
    pending.querySelector("p").textContent = `${result.reply || "Agent 暂无回复"}${toolText}`;
  } catch (error) {
    pending.querySelector("p").textContent = error.message || "Agent 请求失败";
  } finally {
    clearAgentAttachment();
  }
}

function resetChat() {
  els.chatThread.innerHTML = `
    <article class="chat-message assistant">
      <span>AI</span>
      <p>我可以协助整理巡检记录、解释告警原因、生成处理建议。</p>
    </article>
  `;
  els.agentInput.value = "";
  clearAgentAttachment();
  els.agentInput.focus();
}

function setSelectedFile(file) {
  els.selectedFileName.textContent = file ? file.name : "选择巡检报告文件";
  els.uploadState.textContent = file ? "已选择文件" : "待上传";
}

async function handleReportSubmit(event) {
  event.preventDefault();
  const file = els.reportFile.files[0];
  if (!file) {
    els.uploadState.textContent = "请选择文件";
    return;
  }

  const form = new FormData();
  form.append("file", file);
  form.append("handler", currentUser?.username || "inspector");
  form.append("handle_status", els.reportStatus.value);
  if (els.reportDevice.value.trim()) {
    form.append("device_id", els.reportDevice.value.trim());
  }
  if (els.reportRecord.value.trim()) {
    form.append("record_id", els.reportRecord.value.trim());
  }
  if (els.reportNote.value.trim()) {
    form.append("note", els.reportNote.value.trim());
  }

  els.uploadState.textContent = "上传中";
  els.reportForm.querySelector("#reportSubmit").disabled = true;
  try {
    const response = await fetch("/api/reports/upload", { method: "POST", body: form });
    const body = await response.json();
    if (!response.ok || body.code >= 400) {
      throw new Error(body.message || body.detail || "Report 上传失败");
    }
    appendUploadedReport(body.data);
    els.reportForm.reset();
    setSelectedFile(null);
    els.uploadState.textContent = "上传完成";
  } catch (error) {
    els.uploadState.textContent = error.message || "上传失败";
  } finally {
    els.reportForm.querySelector("#reportSubmit").disabled = false;
  }
}

function appendUploadedReport(report) {
  uploadCount += 1;
  els.uploadCount.textContent = String(uploadCount);
  if (uploadCount === 1) {
    els.uploadList.innerHTML = "";
  }
  const item = document.createElement("article");
  item.className = "upload-item";
  const title = document.createElement("strong");
  const meta = document.createElement("span");
  const note = document.createElement("span");
  title.textContent = report.file_name || report.report_id;
  meta.textContent = `设备：${report.device_id || "--"} · 记录：${report.record_id || "--"} · ${report.generated_at || ""}`;
  note.textContent = report.summary?.note || "已写入后端 reports 表";
  item.append(title, meta, note);
  els.uploadList.prepend(item);
}

function clearAgentAttachment() {
  selectedAgentImageDataUrl = null;
  els.agentImage.value = "";
  els.agentAttachmentName.textContent = "";
  els.agentAttachmentName.classList.add("hidden");
}

function readAgentImage(file) {
  if (!file) {
    clearAgentAttachment();
    return;
  }
  const reader = new FileReader();
  reader.onload = () => {
    selectedAgentImageDataUrl = String(reader.result || "");
    els.agentAttachmentName.textContent = `已选择图片：${file.name}`;
    els.agentAttachmentName.classList.remove("hidden");
  };
  reader.readAsDataURL(file);
}

function boot() {
  const sessionUser = loadSessionUser();
  if (!sessionUser || sessionUser.role !== "inspector") {
    showLogin();
    return;
  }
  currentUser = sessionUser;
  setUserDisplay(sessionUser);
  hideLogin();
  setInspectorView("agent");
}

els.loginForm.addEventListener("submit", (event) => handleLogin(event));
els.logoutBtn.addEventListener("click", () => handleLogout());
els.navItems.forEach((item) => {
  item.addEventListener("click", () => setInspectorView(item.dataset.inspectorView));
});
els.agentForm.addEventListener("submit", (event) => handleAgentSubmit(event));
els.newChatBtn.addEventListener("click", () => resetChat());
els.suggestionButtons.forEach((button) => {
  button.addEventListener("click", () => {
    els.agentInput.value = button.dataset.prompt;
    els.agentInput.focus();
  });
});
els.agentImage.addEventListener("change", () => readAgentImage(els.agentImage.files[0]));
els.reportFile.addEventListener("change", () => setSelectedFile(els.reportFile.files[0]));
els.reportForm.addEventListener("submit", (event) => handleReportSubmit(event));

boot();
