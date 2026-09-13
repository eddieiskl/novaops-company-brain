const viewOrder = ["story", "system", "security", "proof", "live"];
const views = Array.from(document.querySelectorAll("[data-showcase-view]"));
const navItems = Array.from(document.querySelectorAll("[data-view]"));
const viewCounter = document.querySelector("#viewCounter");
const mayaFrame = document.querySelector("#mayaFrame");

const fallback = {
  release_commit: "lesson-13",
  metrics: [
    { label: "Workflows", value: "4 / 4", note: "Required + optional" },
    { label: "Tests", value: "87 / 87", note: "Full suite" },
    { label: "Evaluation", value: "33 / 33", note: "Optional-inclusive" },
    { label: "Deterministic", value: "243 × 1.0", note: "Binding scores" },
    { label: "Security", value: "16 / 16", note: "Live guard cases" }
  ],
  workflows: [
    { name: "Maya", domain: "HR onboarding", proof: "Cited retrieval and a read-only access handoff.", boundary: "Chat cannot grant access or expose manager-only evidence." },
    { name: "Webex", domain: "IT operations", proof: "Durable approval state, reused records, and replay safety.", boundary: "A write releases only after a recorded, assigned approval." },
    { name: "Vendor", domain: "CRM extraction", proof: "One forced-tool call with schema validation and focused follow-up.", boundary: "Missing required fields stay missing; the model cannot invent them." },
    { name: "Renewal", domain: "Contract renewal", proof: "Persistent schedule, proposal, outbox, audit, and notifications.", boundary: "Only an exact approved proposal can create exactly-once effects." }
  ],
  control_chain: ["Retrieve", "Validate", "Authorize", "Execute", "Observe", "Evaluate"],
  security_metrics: [
    { label: "Guard decisions", value: "16 / 16", note: "Exact live decisions" },
    { label: "Attacks allowed", value: "0 / 8", note: "Frozen attack set" },
    { label: "Durable changes", value: "0", note: "Across blocked cases" },
    { label: "Index restored", value: "634 / 634", note: "Owned poison removed" }
  ],
  proof: [
    { label: "Pytest", value: "87 / 87", note: "Reliability and durability" },
    { label: "Golden records", value: "33 / 33", note: "Required + optional" },
    { label: "API scores", value: "243", note: "Every result is 1.0" },
    { label: "Advisory judge", value: "0.897", note: "99 separate scores" },
    { label: "GitHub Actions", value: "Passed", note: "41-second CI run" }
  ],
  evidence: [
    { claim: "Grounded answers", source: "Citations and permission-filtered retrieval", kind: "Binding" },
    { claim: "Durable approval", source: "Restart and resume tests plus SQLite state", kind: "Binding" },
    { claim: "Exactly-once effects", source: "Replayed renewal events and idempotent outbox", kind: "Binding" },
    { claim: "Observable behavior", source: "33 indexed traces and 42 tool observations", kind: "Trace" },
    { claim: "Safe deployment", source: "Three non-root images, health checks, local Compose", kind: "Packaging" },
    { claim: "Poison resistance", source: "Source manifest, semantic guard, quarantine, and exact cleanup", kind: "Security" }
  ]
};

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function showView(requested, updateHash = true) {
  const view = viewOrder.includes(requested) ? requested : "story";
  for (const section of views) section.classList.toggle("active", section.dataset.showcaseView === view);
  for (const item of navItems) item.classList.toggle("active", item.dataset.view === view);
  viewCounter.textContent = `${String(viewOrder.indexOf(view) + 1).padStart(2, "0")} / 05`;
  if (view === "live" && !mayaFrame.src) mayaFrame.src = "/maya.html?v=20260913";
  if (updateHash && location.hash !== `#${view}`) history.replaceState(null, "", `#${view}`);
  document.title = `${view === "story" ? "NovaOps Company Brain" : `${view[0].toUpperCase()}${view.slice(1)} · NovaOps`} · Project Showcase`;
}

function render(data) {
  document.querySelector("#releaseCommit").textContent = data.release_commit;
  document.querySelector("#storyMetrics").innerHTML = data.metrics.map(metric => `
    <article><span>${escapeHtml(metric.label)}</span><strong>${escapeHtml(metric.value)}</strong><small>${escapeHtml(metric.note)}</small></article>
  `).join("");
  document.querySelector("#workflowGrid").innerHTML = data.workflows.map((workflow, index) => `
    <article class="workflow-card">
      <span class="workflow-index">0${index + 1}</span>
      <div>
        <h3>${escapeHtml(workflow.name)}</h3>
        <p class="workflow-domain">${escapeHtml(workflow.domain)}</p>
        <p class="workflow-proof">${escapeHtml(workflow.proof)}</p>
        <div class="workflow-boundary"><b>Hard boundary</b>${escapeHtml(workflow.boundary)}</div>
      </div>
    </article>
  `).join("");
  document.querySelector("#controlChain").innerHTML = data.control_chain.map(step => `<li>${escapeHtml(step)}</li>`).join("");
  document.querySelector("#securityMetrics").innerHTML = data.security_metrics.map(metric => `
    <article><span>${escapeHtml(metric.label)}</span><strong>${escapeHtml(metric.value)}</strong><small>${escapeHtml(metric.note)}</small></article>
  `).join("");
  document.querySelector("#proofGrid").innerHTML = data.proof.map(item => `
    <article class="proof-card"><span>${escapeHtml(item.label)}</span><strong>${escapeHtml(item.value)}</strong><small>${escapeHtml(item.note)}</small></article>
  `).join("");
  document.querySelector("#evidenceRows").innerHTML = data.evidence.map(item => `
    <article class="evidence-row"><strong>${escapeHtml(item.claim)}</strong><p>${escapeHtml(item.source)}</p><span class="evidence-tag">${escapeHtml(item.kind)}</span></article>
  `).join("");
}

async function runSecurityProbe(message) {
  const output = document.querySelector("#securityResult");
  const buttons = Array.from(document.querySelectorAll("[data-security-probe]"));
  for (const button of buttons) button.disabled = true;
  output.innerHTML = "<p>Running the boundary check…</p>";
  try {
    const response = await fetch("/api/security-demo", {
      method: "POST",
      headers: {"content-type": "application/json"},
      body: JSON.stringify({message})
    });
    const payload = await response.json();
    if (!payload.ok) throw new Error(payload.error || "Security check failed.");
    const result = payload.result;
    const guard = result.guard || {};
    const tools = result.tool_sequence.length ? result.tool_sequence.join(", ") : "None";
    const delta = result.durable_access_requests_after - result.durable_access_requests_before;
    output.innerHTML = `
      <div class="result-verdict ${escapeHtml(guard.decision)}"><span>${escapeHtml(guard.category)}</span><strong>${escapeHtml(guard.decision)}</strong></div>
      <dl>
        <div><dt>Reason</dt><dd>${escapeHtml(guard.reason)}</dd></div>
        <div><dt>Workflow status</dt><dd>${escapeHtml(result.status)} · ${escapeHtml(result.scope)}</dd></div>
        <div><dt>Tools reached</dt><dd>${escapeHtml(tools)}</dd></div>
        <div><dt>Durable write delta</dt><dd>${escapeHtml(delta)}</dd></div>
      </dl>
      <p class="probe-answer">${escapeHtml(result.answer)}</p>
    `;
  } catch (error) {
    output.innerHTML = `<p>${escapeHtml(error.message || error)}</p>`;
  } finally {
    for (const button of buttons) button.disabled = false;
  }
}

for (const item of navItems) item.addEventListener("click", () => showView(item.dataset.view));
for (const item of document.querySelectorAll("[data-view-target]")) item.addEventListener("click", () => showView(item.dataset.viewTarget));
for (const item of document.querySelectorAll("[data-security-probe]")) item.addEventListener("click", () => runSecurityProbe(item.dataset.securityProbe));

document.addEventListener("keydown", event => {
  if (!(["ArrowLeft", "ArrowRight"].includes(event.key)) || event.target.matches("input, textarea, button")) return;
  const current = viewOrder.indexOf(location.hash.slice(1));
  const direction = event.key === "ArrowRight" ? 1 : -1;
  const next = Math.min(viewOrder.length - 1, Math.max(0, (current < 0 ? 0 : current) + direction));
  showView(viewOrder[next]);
});

window.addEventListener("hashchange", () => showView(location.hash.slice(1), false));

render(fallback);
showView(location.hash.slice(1), false);

fetch("/api/showcase")
  .then(response => {
    if (!response.ok) throw new Error(`Showcase request failed: ${response.status}`);
    return response.json();
  })
  .then(render)
  .catch(() => render(fallback));
