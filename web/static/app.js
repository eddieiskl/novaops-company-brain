const form = document.querySelector("#chatForm");
const input = document.querySelector("#messageInput");
const messages = document.querySelector("#messages");
const checklist = document.querySelector("#checklist");
const evidenceList = document.querySelector("#evidenceList");
const blockedList = document.querySelector("#blockedList");
const retrieverModeButtons = Array.from(document.querySelectorAll("[data-mode]"));
const retrieverDetail = document.querySelector("#retrieverDetail");
const dashboardTab = document.querySelector("#dashboardTab");
const chatTab = document.querySelector("#chatTab");
const dashboardView = document.querySelector("#dashboardView");
const chatView = document.querySelector("#chatView");
const dashboardTitle = document.querySelector("#dashboardTitle");
const refreshDashboard = document.querySelector("#refreshDashboard");
const metricGrid = document.querySelector("#metricGrid");
const dashboardSystems = document.querySelector("#dashboardSystems");
const dashboardEquipment = document.querySelector("#dashboardEquipment");
const dashboardPolicy = document.querySelector("#dashboardPolicy");
const turnTrace = document.querySelector("#turnTrace");
const threadLabel = document.querySelector("#threadLabel");

const threadId = `maya-ui-${crypto.randomUUID().slice(0, 8)}`;
threadLabel.textContent = threadId;
const seedTurns = [
  "Who is Maya and when does she start?",
  "Which systems does Maya need on day one?",
  "What is currently blocking her onboarding?",
  "Is a Webex seat available for Maya?"
];
let nextTurn = 1;
let retrieverMode = "memory";
let latestDashboard = null;

function addMessage(role, text) {
  const node = document.createElement("article");
  node.className = `message ${role}`;
  node.textContent = text;
  messages.appendChild(node);
  messages.scrollTop = messages.scrollHeight;
}

function renderChecklist(data) {
  const groups = [
    ["Systems", data.systems],
    ["Equipment", data.equipment],
    ["Policy", data.policy_requirements]
  ];
  checklist.innerHTML = groups.map(([label, items]) => `
    <div class="group">
      <h3>${label}</h3>
      ${items.map(item => `
        <div class="item">
          <span class="status">${item.status}</span>
          <strong>${item.name}</strong>
          <p>${item.detail}</p>
        </div>
      `).join("")}
    </div>
  `).join("");

  blockedList.innerHTML = data.blocked_items.map(item => `<li>${item.name}: ${item.status}</li>`).join("");
}

function renderDashboard(snapshot) {
  latestDashboard = snapshot;
  dashboardTitle.textContent = `${snapshot.employee.name} / ${snapshot.employee.role}`;
  const readiness = snapshot.readiness;
  metricGrid.innerHTML = [
    ["Total", readiness.total_items],
    ["Ready", readiness.ready_or_planned],
    ["Blocked", readiness.blocked],
    ["Finance", readiness.finance_required],
    ["Handoffs", snapshot.handoffs.length]
  ].map(([label, value]) => `
    <article class="metric">
      <span>${label}</span>
      <strong>${value}</strong>
    </article>
  `).join("");

  dashboardSystems.innerHTML = renderCompactItems(snapshot.systems);
  dashboardEquipment.innerHTML = renderCompactItems(snapshot.equipment);
  dashboardPolicy.innerHTML = renderCompactItems(snapshot.policy_requirements);
  blockedList.innerHTML = snapshot.blocked_items.map(item => `<li>${item.name}: ${item.status}</li>`).join("");
  evidenceList.innerHTML = snapshot.evidence_sources.slice(0, 10).map(source => `<li>${source.source_path}</li>`).join("");
  turnTrace.innerHTML = snapshot.turns.map(turn => `
    <div class="trace-row">
      <span>${turn.turn}</span>
      <strong>${turn.intent}</strong>
      <em>${turn.tool_calls.length ? turn.tool_calls.join(", ") : "no tools"}</em>
    </div>
  `).join("");
  renderChecklist({
    systems: snapshot.systems,
    equipment: snapshot.equipment,
    policy_requirements: snapshot.policy_requirements,
    blocked_items: snapshot.blocked_items
  });
}

function renderCompactItems(items) {
  return items.map(item => `
    <article class="compact-item">
      <span class="status">${item.status}</span>
      <strong>${item.name}</strong>
      <p>${item.detail}</p>
    </article>
  `).join("");
}

function renderEvidence(result) {
  const sources = new Map();
  for (const chunk of result.retrieved || []) {
    sources.set(chunk.chunk_id, `${chunk.source_path}`);
  }
  const groups = [
    result.checklist.systems || [],
    result.checklist.equipment || [],
    result.checklist.policy_requirements || [],
    result.checklist.blocked_items || []
  ];
  for (const group of groups) {
    for (const item of group) {
      for (const citation of item.evidence || []) {
        sources.set(citation.chunk_id, citation.source_path);
      }
    }
  }
  evidenceList.innerHTML = Array.from(sources.values()).slice(0, 8).map(source => `<li>${source}</li>`).join("");
}

async function send(message) {
  addMessage("user", message);
  input.value = "";
  const response = await fetch("/api/chat", {
    method: "POST",
    headers: {"content-type": "application/json"},
    body: JSON.stringify({
      thread_id: threadId,
      turn: nextTurn,
      caller: {employee_id: "E004", user_group: "UG_HR"},
      message
    })
  });
  const payload = await response.json();
  if (!payload.ok) {
    addMessage("agent", payload.error || "Request failed.");
    return;
  }
  updateRetriever(payload.retriever);
  nextTurn += 1;
  addMessage("agent", payload.result.answer);
  renderChecklist(payload.result.checklist);
  renderEvidence(payload.result);
}

function updateRetriever(retriever, notice = "") {
  if (!retriever) return;
  retrieverMode = retriever.mode;
  updateRetrieverModeButtons(retrieverMode);
  const rows = [
    runtimeRow("Retriever", retriever.detail),
    runtimeRow("Answer", retriever.answer_detail || "Using deterministic answer templates."),
    runtimeRow("Webex", retriever.webex_detail || "Using deterministic fake Webex handoff port."),
    runtimeRow("Retrieval trust", retriever.retrieval_security_detail || "Application-owned source manifest is enforced.")
  ];
  if (notice) rows.push(runtimeRow("Notice", notice));
  retrieverDetail.replaceChildren(...rows);
}

function updateRetrieverModeButtons(mode) {
  for (const button of retrieverModeButtons) {
    const selected = button.dataset.mode === mode;
    button.classList.toggle("active", selected);
    button.setAttribute("aria-pressed", String(selected));
  }
}

function runtimeRow(label, value) {
  const row = document.createElement("div");
  row.className = "runtime-row";
  const name = document.createElement("strong");
  name.textContent = label;
  const detail = document.createElement("span");
  detail.textContent = value;
  row.append(name, detail);
  return row;
}

async function loadRetriever() {
  const response = await fetch("/api/retriever");
  const payload = await response.json();
  if (payload.ok) updateRetriever(payload.retriever);
}

async function loadDashboard() {
  const response = await fetch("/api/dashboard");
  const payload = await response.json();
  if (!payload.ok) {
    addMessage("agent", payload.error || "Could not load dashboard.");
    return;
  }
  updateRetriever(payload.retriever);
  renderDashboard(payload.dashboard);
}

async function setRetriever(requested) {
  for (const button of retrieverModeButtons) button.disabled = true;
  try {
    const response = await fetch("/api/retriever", {
      method: "POST",
      headers: {"content-type": "application/json"},
      body: JSON.stringify({mode: requested})
    });
    const payload = await response.json();
    if (!payload.ok) {
      updateRetriever(payload.retriever, payload.error || "Could not change retriever mode.");
      return;
    }
    updateRetriever(payload.retriever);
    nextTurn = 1;
    messages.innerHTML = "";
    addSeeds();
    loadDashboard();
  } catch (error) {
    updateRetriever({mode: retrieverMode, detail: "Using deterministic in-memory retrieval."}, String(error));
  } finally {
    for (const button of retrieverModeButtons) button.disabled = false;
  }
}

form.addEventListener("submit", event => {
  event.preventDefault();
  const message = input.value.trim();
  if (message) send(message);
});

for (const button of retrieverModeButtons) {
  button.addEventListener("click", () => {
    setRetriever(button.dataset.mode);
  });
}

dashboardTab.addEventListener("click", () => showView("dashboard"));
chatTab.addEventListener("click", () => showView("chat"));
refreshDashboard.addEventListener("click", loadDashboard);

function showView(view) {
  const showingDashboard = view === "dashboard";
  dashboardView.classList.toggle("hidden", !showingDashboard);
  chatView.classList.toggle("hidden", showingDashboard);
  dashboardTab.classList.toggle("active", showingDashboard);
  chatTab.classList.toggle("active", !showingDashboard);
}

function addSeeds() {
  for (const turn of seedTurns) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "seed";
    button.textContent = turn;
    button.addEventListener("click", () => send(turn));
    messages.appendChild(button);
  }
}

addSeeds();
loadRetriever();
loadDashboard();
