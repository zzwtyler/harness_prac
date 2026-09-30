const elements = {
  projectContextInput: document.querySelector("#project-context-input"),
  contextCount: document.querySelector("#context-count"),
  contextPreview: document.querySelector("#context-preview"),
  restoreContext: document.querySelector("#restore-context"),
  taskInput: document.querySelector("#task-input"),
  characterCount: document.querySelector("#character-count"),
  submitButton: document.querySelector("#submit-button"),
  buttonLabel: document.querySelector(".button-label"),
  stageSelect: document.querySelector("#stage-select"),
  stageDescription: document.querySelector("#stage-description"),
  modelSelect: document.querySelector("#model-select"),
  decisionModelSelect: document.querySelector("#decision-model-select"),
  fallbackModelSelect: document.querySelector("#fallback-model-select"),
  confidenceThreshold: document.querySelector("#confidence-threshold"),
  cascadeToggle: document.querySelector("#cascade-enabled"),
  systemPrompt: document.querySelector("#system-prompt"),
  thinkingToggle: document.querySelector("#thinking-toggle"),
  resetPrompt: document.querySelector("#reset-prompt"),
  settingsRail: document.querySelector(".settings-rail"),
  mobileSettingsButton: document.querySelector("#mobile-settings-button"),
  retryStatus: document.querySelector("#retry-status"),
  statusDot: document.querySelector("#status-dot"),
  connectionStatus: document.querySelector("#connection-status"),
  pageHeadline: document.querySelector("#page-headline"),
  pageIntro: document.querySelector("#page-intro"),
  schemaCount: document.querySelector("#schema-count"),
  composerTitle: document.querySelector("#composer-title"),
  exampleButtons: document.querySelector("#example-buttons"),
  outputTitle: document.querySelector("#output-title"),
  resultEmptyCopy: document.querySelector("#result-empty-copy"),
  errorNotice: document.querySelector("#error-notice"),
  errorMessage: document.querySelector("#error-message"),
  thinkingEmpty: document.querySelector("#thinking-empty"),
  thinkingOutput: document.querySelector("#thinking-output"),
  thinkingStatus: document.querySelector("#thinking-status"),
  thinkingLive: document.querySelector("#thinking-live"),
  resultEmpty: document.querySelector("#result-empty"),
  resultStatus: document.querySelector("#result-status"),
  streamingOutput: document.querySelector("#streaming-output"),
  rawStream: document.querySelector("#raw-stream"),
  structuredResult: document.querySelector("#structured-result"),
  structuredFields: document.querySelector("#structured-fields"),
  rawOutput: document.querySelector("#raw-output"),
  copyButton: document.querySelector("#copy-button"),
  clearButton: document.querySelector("#clear-button"),
  metricsOutput: document.querySelector("#metrics-output"),
  processFill: document.querySelector("#process-fill"),
  processSteps: [...document.querySelectorAll(".process-step")],
  toast: document.querySelector("#toast"),
};

const DEFAULT_PROJECT_CONTEXT = `项目名称：拾光咖啡（虚构练习项目）
行业与业务：一家有三家门店的本地咖啡品牌，经营咖啡、茶饮和烘焙产品，提供到店消费、自取和企业团体订单。顾客通过网页提交咨询，店长也会提出运营需求。
Harness 参与的岗位：门店客服与运营助理。先识别顾客或店长的主要意图，再为相应岗位生成答复草稿、处理单或分析简报；实际订单变更、退款、库存确认和对外承诺由员工执行。
典型需求：顾客询问门店地址与营业时间、按口味和忌口选饮品、修改自取订单、为公司活动订 20 杯咖啡、反馈服务问题、查询会员权益；店长要求制定促销活动或分析上周销售。
建议 intent：store_info、menu_advice、order_support、group_order、complaint、membership_help、campaign_brief、sales_analysis；无法归类时用 other_request，多项独立诉求用 multi_intent。
对应回答类型：门店事实答复、菜单推荐分析、订单处理单、团体订单线索单、客诉分级单、会员规则核查单、活动策划简报、经营分析简报；多项诉求先拆分，其他诉求生成澄清记录。
资料边界：门店档案、菜单/过敏原、订单状态、会员规则和销售报表是未来可接入的数据源；当前项目并未提供真实业务数据。回答不得编造价格、营业时间、库存、订单结果或会员政策；缺少关键资料时列出待查字段和下一步。`;
const PROJECT_CONTEXT_STORAGE_KEY = "harness.projectContext.v1";

let stages = [];
let currentStage = null;
let rawResult = "";
let isGenerating = false;
let availableModelNames = new Set();
let modelRolesReady = false;
let toastTimeout;

function setProcess(stage) {
  const names = ["input", "thinking", "output"];
  const activeIndex = Math.max(0, names.indexOf(stage));
  elements.processSteps.forEach((step, index) => {
    step.classList.toggle("is-active", index === activeIndex);
    step.classList.toggle("is-complete", index < activeIndex);
    if (index === activeIndex) step.setAttribute("aria-current", "step");
    else step.removeAttribute("aria-current");
  });
  elements.processFill.style.transform = `scaleX(${activeIndex / (names.length - 1)})`;
}

function setLoading(loading) {
  isGenerating = loading;
  elements.submitButton.disabled = loading || !currentStage || !modelRolesReady;
  elements.stageSelect.disabled = loading;
  elements.modelSelect.disabled = loading;
  elements.decisionModelSelect.disabled = loading;
  elements.fallbackModelSelect.disabled = loading;
  elements.confidenceThreshold.disabled = loading;
  elements.cascadeToggle.disabled = loading;
  elements.buttonLabel.textContent = loading ? "正在运行…" : currentStage?.actionLabel || "运行当前阶段";
}

function updateCharacterCount() {
  elements.characterCount.textContent = `${elements.taskInput.value.length.toLocaleString("zh-CN")} / 20,000`;
}

function updateContext() {
  elements.contextCount.textContent = `${elements.projectContextInput.value.length.toLocaleString("zh-CN")} / 8,000`;
  updateContextPreview();
  try { window.localStorage.setItem(PROJECT_CONTEXT_STORAGE_KEY, elements.projectContextInput.value); }
  catch (_error) { /* The field still works when browser storage is unavailable. */ }
}

function updateContextPreview() {
  const name = elements.projectContextInput.value.trim().split("\n")[0].replace(/^项目名称[：:]\s*/, "");
  elements.contextPreview.textContent = name ? `${name.slice(0, 32)} · 已提供上下文` : "未填写 · 仅发送当前任务";
}

function loadContext() {
  let saved = null;
  try { saved = window.localStorage.getItem(PROJECT_CONTEXT_STORAGE_KEY); }
  catch (_error) { /* Use the bundled example when browser storage is unavailable. */ }
  elements.projectContextInput.value = saved === null ? DEFAULT_PROJECT_CONTEXT : saved;
  elements.contextCount.textContent = `${elements.projectContextInput.value.length.toLocaleString("zh-CN")} / 8,000`;
  updateContextPreview();
}

function showToast(message) {
  window.clearTimeout(toastTimeout);
  elements.toast.textContent = message;
  elements.toast.classList.add("is-visible");
  toastTimeout = window.setTimeout(() => elements.toast.classList.remove("is-visible"), 2400);
}

function showError(message) {
  elements.errorMessage.textContent = message;
  elements.errorNotice.classList.remove("is-hidden");
  elements.resultStatus.textContent = "运行失败";
  elements.thinkingStatus.textContent = "已停止";
  elements.thinkingLive.classList.remove("is-live");
}

function clearError() {
  elements.errorNotice.classList.add("is-hidden");
  elements.errorMessage.textContent = "";
}

function resetOutput({ keepTask = true } = {}) {
  rawResult = "";
  elements.thinkingOutput.textContent = "";
  elements.rawStream.textContent = "";
  elements.rawOutput.textContent = "";
  elements.structuredFields.replaceChildren();
  elements.thinkingEmpty.classList.remove("is-hidden");
  elements.resultEmpty.classList.remove("is-hidden");
  elements.streamingOutput.classList.add("is-hidden");
  elements.structuredResult.classList.add("is-hidden");
  elements.thinkingStatus.textContent = "等待任务";
  elements.resultStatus.textContent = "等待结构化输出";
  elements.thinkingLive.classList.remove("is-live");
  elements.copyButton.disabled = true;
  elements.metricsOutput.textContent = "尚未生成";
  clearError();
  setProcess("input");
  if (!keepTask) {
    elements.taskInput.value = "";
    updateCharacterCount();
    elements.taskInput.focus();
  }
}

function fieldLetter(index) {
  return index < 26 ? String.fromCharCode(65 + index) : String(index + 1);
}

function schemaType(schema = {}) {
  if (schema.type) return schema.type;
  const nonNull = (schema.anyOf || []).find((item) => item.type !== "null");
  return nonNull?.type || "unknown";
}

function humanValue(value) {
  if (value === null || value === undefined || value === "") return "—";
  if (typeof value === "boolean") return value ? "是" : "否";
  if (typeof value === "object") return JSON.stringify(value, null, 2);
  return String(value);
}

function makeSimpleList(values, ordered = false) {
  const list = document.createElement(ordered ? "ol" : "ul");
  const items = Array.isArray(values) ? values : [];
  (items.length ? items : ["暂无内容"]).forEach((value) => {
    const item = document.createElement("li");
    item.textContent = humanValue(value);
    if (!items.length) item.className = "empty-list-item";
    list.append(item);
  });
  return list;
}

function makeObjectList(values, itemSchema = {}, parentKey = "") {
  const container = document.createElement("div");
  container.className = "object-list";
  const items = Array.isArray(values) ? values : [];
  if (!items.length) {
    const empty = document.createElement("p");
    empty.className = "empty-list-item";
    empty.textContent = "暂无内容";
    container.append(empty);
    return container;
  }
  items.forEach((value, index) => {
    const article = document.createElement("article");
    const marker = document.createElement("span");
    marker.className = "object-index";
    marker.textContent = String(index + 1).padStart(2, "0");
    const details = document.createElement("dl");
    Object.entries(itemSchema.properties || value || {}).forEach(([key, schema]) => {
      const term = document.createElement("dt");
      term.textContent = currentStage?.nestedFieldLabels?.[`${parentKey}.${key}`] || schema?.title || key;
      const detail = document.createElement("dd");
      detail.textContent = humanValue(value?.[key]);
      details.append(term, detail);
    });
    article.append(marker, details);
    container.append(article);
  });
  return container;
}

function renderStructuredResult(text) {
  const result = parseStructuredResult(text);
  const properties = currentStage?.schema?.properties || {};
  elements.structuredFields.replaceChildren();

  Object.entries(properties).forEach(([key, schema], index) => {
    const presentation = currentStage?.presentation?.[key] || schemaType(schema);
    const section = document.createElement("section");
    section.className = `result-field field-${presentation}`;
    const heading = document.createElement("div");
    heading.className = "field-title";
    const marker = document.createElement("span");
    marker.textContent = fieldLetter(index);
    const title = document.createElement("h3");
    title.textContent = currentStage?.fieldLabels?.[key] || schema.title || key;
    const meta = document.createElement("em");
    meta.textContent = Array.isArray(result[key]) ? String(result[key].length).padStart(2, "0") : key.toUpperCase();
    heading.append(marker, title, meta);
    section.append(heading);

    if (presentation === "primary") {
      const value = document.createElement("p");
      value.className = "primary-value";
      value.textContent = humanValue(result[key]);
      section.append(value);
    } else if (presentation === "code") {
      const value = document.createElement("code");
      value.className = "code-value";
      value.textContent = humanValue(result[key]);
      section.append(value);
    } else if (presentation === "object-list") {
      section.append(makeObjectList(result[key], schema.items, key));
    } else if (presentation === "ordered-list") {
      section.append(makeSimpleList(result[key], true));
    } else if (schemaType(schema) === "array" || presentation === "list") {
      section.append(makeSimpleList(result[key]));
    } else {
      const value = document.createElement("p");
      value.className = "plain-value";
      value.textContent = typeof result[key] === "object" ? JSON.stringify(result[key], null, 2) : humanValue(result[key]);
      section.append(value);
    }
    elements.structuredFields.append(section);
  });

  elements.rawOutput.textContent = JSON.stringify(result, null, 2);
  elements.streamingOutput.classList.add("is-hidden");
  elements.structuredResult.classList.remove("is-hidden");
  elements.copyButton.disabled = false;
}

function parseStructuredResult(text) {
  const trimmed = text.trim();
  try { return JSON.parse(trimmed); } catch (_error) {
    return JSON.parse(trimmed.replace(/^```(?:json)?\s*/i, "").replace(/\s*```$/, ""));
  }
}

function formatMetrics(metrics = {}) {
  const duration = metrics.durationNs ? `${(metrics.durationNs / 1e9).toFixed(1)}s` : "—";
  return `${duration} · 输入 ${metrics.promptTokens ?? "—"} tokens · 输出 ${metrics.outputTokens ?? "—"} tokens`;
}

async function readErrorResponse(response) {
  try { const data = await response.json(); return data.error || `请求失败（HTTP ${response.status}）`; }
  catch (_error) { return `请求失败（HTTP ${response.status}）`; }
}

function applyStage(stage, { preservePrompt = false } = {}) {
  currentStage = stage;
  elements.stageDescription.textContent = stage.description;
  elements.pageHeadline.textContent = stage.headline;
  elements.pageIntro.textContent = stage.intro;
  elements.schemaCount.textContent = `${Object.keys(stage.schema?.properties || {}).length} FIELDS`;
  elements.composerTitle.textContent = stage.inputLabel;
  elements.taskInput.placeholder = stage.inputPlaceholder;
  elements.outputTitle.textContent = stage.outputTitle;
  elements.resultEmptyCopy.textContent = `生成完成后，${stage.title}的结构化字段会在这里组成一张可检查的清样。`;
  elements.buttonLabel.textContent = stage.actionLabel;
  if (!preservePrompt) elements.systemPrompt.value = stage.systemPrompt;
  elements.exampleButtons.replaceChildren();
  (stage.examples || []).forEach((example) => {
    const button = document.createElement("button");
    button.type = "button";
    button.textContent = example.label;
    button.addEventListener("click", () => {
      elements.taskInput.value = example.value;
      updateCharacterCount();
      elements.taskInput.focus();
    });
    elements.exampleButtons.append(button);
  });
  resetOutput({ keepTask: true });
  setLoading(false);
}

async function loadStages({ preserveSelection = true } = {}) {
  const selectedId = preserveSelection ? elements.stageSelect.value : "";
  const response = await fetch("/api/stages", { cache: "no-store" });
  if (!response.ok) throw new Error(await readErrorResponse(response));
  const data = await response.json();
  stages = data.stages || [];
  if (!stages.length) throw new Error("没有找到可用的 Harness stage");
  elements.stageSelect.replaceChildren();
  stages.forEach((stage) => {
    const option = document.createElement("option");
    option.value = stage.id;
    option.textContent = stage.title;
    elements.stageSelect.append(option);
  });
  const selected = stages.find((stage) => stage.id === selectedId) || stages[0];
  elements.stageSelect.value = selected.id;
  applyStage(selected);
}

async function generate() {
  if (isGenerating || !currentStage) return;
  if (!modelRolesReady) { showToast("请安装缺失的角色模型，或明确选择已安装的替代模型。"); return; }
  const message = elements.taskInput.value.trim();
  const threshold = Number(elements.confidenceThreshold.value);
  if (!Number.isFinite(threshold) || threshold < 0 || threshold > 1 || elements.confidenceThreshold.value === "") {
    elements.confidenceThreshold.focus(); showToast("阈值必须为 0 至 1 的数值。"); return;
  }
  if (!message) { elements.taskInput.focus(); showToast("请先输入当前阶段需要的内容"); return; }
  resetOutput({ keepTask: true });
  setLoading(true);
  setProcess("thinking");
  elements.thinkingEmpty.classList.add("is-hidden");
  elements.thinkingStatus.textContent = "正在读取 reasoning tokens";
  elements.thinkingLive.classList.add("is-live");
  elements.resultEmpty.classList.add("is-hidden");
  elements.streamingOutput.classList.remove("is-hidden");
  elements.resultStatus.textContent = "等待最终 JSON";

  try {
    const response = await fetch("/api/run", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        stageId: currentStage.id, message, projectContext: elements.projectContextInput.value.trim(), model: elements.modelSelect.value,
        decisionModel: elements.decisionModelSelect.value,
        fallbackModel: elements.fallbackModelSelect.value, confidenceThreshold: threshold,
        cascadeEnabled: elements.cascadeToggle.checked,
        systemPrompt: elements.systemPrompt.value, think: elements.thinkingToggle.checked,
      }),
    });
    if (!response.ok) throw new Error(await readErrorResponse(response));
    if (!response.body) throw new Error("浏览器没有提供可读取的响应流。");
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    let sawThinking = false;
    while (true) {
      const { value, done } = await reader.read();
      buffer += decoder.decode(value || new Uint8Array(), { stream: !done });
      const lines = buffer.split("\n");
      buffer = done ? "" : lines.pop() || "";
      for (const line of lines) {
        if (!line.trim()) continue;
        const event = JSON.parse(line);
        if (event.type === "thinking") {
          sawThinking = true;
          elements.thinkingOutput.textContent += event.text;
          elements.thinkingOutput.scrollTop = elements.thinkingOutput.scrollHeight;
        } else if (event.type === "content") {
          if (!rawResult) {
            setProcess("output");
            elements.thinkingLive.classList.remove("is-live");
            elements.thinkingStatus.textContent = sawThinking ? "思考完成" : "模型未返回独立思考内容";
            elements.resultStatus.textContent = "正在接收结构化输出";
          }
          rawResult += event.text;
          elements.rawStream.textContent = rawResult;
        } else if (event.type === "done") elements.metricsOutput.textContent = formatMetrics(event.metrics);
        else if (event.type === "error") throw new Error(event.error || "模型流发生错误。");
      }
      if (done) break;
    }
    if (!rawResult.trim()) throw new Error("模型没有返回最终内容。");
    renderStructuredResult(rawResult);
    elements.resultStatus.textContent = "JSON 已通过前端解析";
    elements.thinkingStatus.textContent = sawThinking ? "思考完成" : "未启用独立思考";
    setProcess("output");
  } catch (error) { showError(error instanceof Error ? error.message : String(error)); }
  finally { setLoading(false); elements.thinkingLive.classList.remove("is-live"); }
}

function populateRoleModelSelect(select, models, requestedModel) {
  select.replaceChildren();
  models.forEach((model) => {
    const option = document.createElement("option");
    option.value = model.name; option.textContent = model.name; select.append(option);
  });
  const installed = models.some((model) => model.name === requestedModel);
  if (!installed) {
    const missing = document.createElement("option");
    missing.value = requestedModel; missing.textContent = `${requestedModel} · 未安装`;
    missing.disabled = true; select.append(missing);
  }
  select.value = requestedModel;
  return installed;
}

function areModelRolesReady(names, detail, decision, fallback, cascadeEnabled) {
  return names.has(detail) && names.has(decision) && (!cascadeEnabled || names.has(fallback));
}

async function checkStatus() {
  let ollamaOnline = false;
  elements.statusDot.className = "status-dot is-checking";
  elements.connectionStatus.textContent = "正在检查 Ollama 与 stages…";
  elements.retryStatus.disabled = true;
  try {
    const [statusResponse] = await Promise.all([
      fetch("/api/status", { cache: "no-store" }),
      loadStages({ preserveSelection: true }),
    ]);
    const data = await statusResponse.json();
    if (!statusResponse.ok || !data.online) throw new Error(data.error || "Ollama 未连接");
    ollamaOnline = true;
    const currentModel = elements.modelSelect.value || "qwen3.5:4b";
    const currentDecisionModel = elements.decisionModelSelect.value || "tev1:4b";
    const currentFallbackModel = elements.fallbackModelSelect.value || "qwen3:8b";
    const models = data.models || [];
    availableModelNames = new Set(models.map((model) => model.name));
    const detailReady = populateRoleModelSelect(elements.modelSelect, models, currentModel);
    const decisionReady = populateRoleModelSelect(elements.decisionModelSelect, models, currentDecisionModel);
    const fallbackReady = populateRoleModelSelect(elements.fallbackModelSelect, models, currentFallbackModel);
    modelRolesReady = detailReady && decisionReady && (!elements.cascadeToggle.checked || fallbackReady);
    if (!modelRolesReady) throw new Error("角色模型缺失：请安装对应模型，或明确选择已安装的替代模型。");
    elements.statusDot.className = "status-dot is-online";
    elements.connectionStatus.textContent = `${stages.length} 个 stage · ${models.length} 个模型`;
  } catch (error) {
    modelRolesReady = false;
    if (!ollamaOnline) availableModelNames = new Set();
    elements.statusDot.className = "status-dot is-offline";
    elements.connectionStatus.textContent = ollamaOnline
      ? "Ollama 已连接 · 角色模型缺失"
      : currentStage ? "Stage 可用 · Ollama 未连接" : "服务未就绪";
    showToast(error instanceof Error ? error.message : String(error));
  } finally {
    elements.retryStatus.disabled = false;
    setLoading(false);
  }
}

elements.submitButton.addEventListener("click", generate);
elements.projectContextInput.addEventListener("input", updateContext);
elements.restoreContext.addEventListener("click", () => {
  elements.projectContextInput.value = DEFAULT_PROJECT_CONTEXT;
  updateContext();
  elements.projectContextInput.focus();
  showToast("已恢复示例项目背景");
});
elements.taskInput.addEventListener("input", updateCharacterCount);
elements.taskInput.addEventListener("keydown", (event) => {
  if ((event.metaKey || event.ctrlKey) && event.key === "Enter") { event.preventDefault(); generate(); }
});
elements.copyButton.addEventListener("click", async () => {
  if (!rawResult) return;
  try { await navigator.clipboard.writeText(rawResult.trim()); showToast("JSON 已复制到剪贴板"); }
  catch (_error) { showToast("无法访问剪贴板，请手动复制"); }
});
elements.clearButton.addEventListener("click", () => resetOutput({ keepTask: false }));
elements.retryStatus.addEventListener("click", checkStatus);
elements.stageSelect.addEventListener("change", () => {
  const stage = stages.find((item) => item.id === elements.stageSelect.value);
  if (stage) applyStage(stage);
});
[elements.modelSelect, elements.decisionModelSelect, elements.fallbackModelSelect, elements.cascadeToggle].forEach((select) => select.addEventListener("change", () => {
  modelRolesReady = areModelRolesReady(availableModelNames, elements.modelSelect.value,
    elements.decisionModelSelect.value, elements.fallbackModelSelect.value, elements.cascadeToggle.checked);
  if (modelRolesReady) {
    elements.statusDot.className = "status-dot is-online";
    elements.connectionStatus.textContent = "已明确选择所需角色模型";
  }
  setLoading(isGenerating);
}));
elements.resetPrompt.addEventListener("click", () => {
  if (currentStage) elements.systemPrompt.value = currentStage.systemPrompt;
  showToast("已恢复当前 Stage 的中文 System content");
});
elements.mobileSettingsButton.addEventListener("click", () => {
  const expanded = elements.mobileSettingsButton.getAttribute("aria-expanded") === "true";
  elements.mobileSettingsButton.setAttribute("aria-expanded", String(!expanded));
  elements.settingsRail.classList.toggle("is-expanded", !expanded);
});

updateCharacterCount();
loadContext();
elements.submitButton.disabled = true;
elements.stageSelect.disabled = true;
checkStatus();
