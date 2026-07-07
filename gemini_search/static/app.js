const form = document.querySelector("#runtimeForm");
const statusText = document.querySelector("#statusText");
const output = document.querySelector("#output");
const elapsedText = document.querySelector("#elapsedText");
const pageTitle = document.querySelector("#pageTitle");

let contentState = {};

const titles = {
  overview: "Overview",
  crawl: "Content Acquisition",
  topics: "Topic Management",
  assets: "Research Assets",
  content: "Content Pipeline",
  governance: "Review & Publish",
  workflows: "n8n Workflows",
  runtime: "Runtime Settings",
  test: "API Test Bench",
};

function headers() {
  const token = localStorage.getItem("adminToken") || "";
  const result = { "Content-Type": "application/json" };
  if (token) result.Authorization = `Bearer ${token}`;
  return result;
}

async function api(path, options = {}) {
  const res = await fetch(path, {
    ...options,
    headers: { ...headers(), ...(options.headers || {}) },
  });
  const text = await res.text();
  let data;
  try {
    data = text ? JSON.parse(text) : {};
  } catch {
    data = { raw: text };
  }
  if (res.status === 401) {
    const token = prompt("ADMIN_TOKEN");
    if (token) {
      localStorage.setItem("adminToken", token);
      return api(path, options);
    }
  }
  if (!res.ok) throw new Error(data.error || data.message || `HTTP ${res.status}`);
  return data;
}

function setOutput(value) {
  output.textContent = typeof value === "string" ? value : JSON.stringify(value, null, 2);
}

function setBusy(busy) {
  document.querySelectorAll("button").forEach((button) => {
    button.disabled = busy;
  });
}

function fillForm(config) {
  form.search_provider.value = config.search_provider || "scrapling";
  form.gemini_api_key.value = config.gemini_api_key || "";
  form.gemini_model.value = config.gemini_model || "gemini-2.5-flash";
  form.brave_api_key.value = config.brave_api_key || "";
  form.tavily_api_key.value = config.tavily_api_key || "";
  form.tavily_search_depth.value = config.tavily_search_depth || "basic";
  form.scrape_backend.value = config.scrape_backend || "scrapling";
  form.headless.checked = config.headless === true;
  form.proxy_server.value = config.proxy_server || "";
  form.web_chat_provider.value = config.web_chat_provider || "disabled";
  form.web_chat_backend.value = config.web_chat_backend || "playwright";
  form.web_chat_headless.checked = config.web_chat_headless === true;
  form.web_chat_profile_dir.value = config.web_chat_profile_dir || "";
}

function text(value) {
  if (value === null || value === undefined || value === "") return "-";
  return String(value);
}

function short(value, max = 74) {
  const str = text(value);
  return str.length > max ? `${str.slice(0, max - 1)}...` : str;
}

function status(value) {
  return `<span class="status">${text(value)}</span>`;
}

function table(target, rows, columns) {
  const el = document.querySelector(target);
  if (!rows || rows.length === 0) {
    el.innerHTML = `<div class="empty">No records</div>`;
    return;
  }
  const head = columns.map((col) => `<th>${col.label}</th>`).join("");
  const body = rows
    .map((row) => {
      const cells = columns
        .map((col) => {
          const value = typeof col.value === "function" ? col.value(row) : row[col.value];
          return `<td>${value}</td>`;
        })
        .join("");
      return `<tr>${cells}</tr>`;
    })
    .join("");
  el.innerHTML = `<div class="table-wrap"><table><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table></div>`;
}

function renderMetrics(summary = {}) {
  const metrics = [
    ["Crawl Sites", summary.crawl_sites],
    ["Queued URLs", summary.queued_urls],
    ["Pages", summary.crawl_pages],
    ["Embeddings", summary.embeddings],
    ["Topics", summary.topics],
    ["Research Assets", summary.research_assets],
    ["Content Items", summary.content_items],
    ["Publications", summary.publications],
  ];
  document.querySelector("#metricGrid").innerHTML = metrics
    .map(([label, value]) => `<div class="metric"><span>${label}</span><strong>${value || 0}</strong></div>`)
    .join("");
}

function renderContentFactory() {
  renderMetrics(contentState.summary || {});
  table("#recentRunsTable", contentState.recent_runs, [
    { label: "Domain", value: (r) => short(r.domain) },
    { label: "Kind", value: (r) => status(r.kind) },
    { label: "Status", value: (r) => status(r.status) },
    { label: "Discovered", value: "discovered_count" },
    { label: "Fetched", value: "fetched_count" },
    { label: "Started", value: (r) => short(r.started_at, 24) },
  ]);
  table("#sitesTable", contentState.sites, [
    { label: "Domain", value: (r) => short(r.domain) },
    { label: "Base URL", value: (r) => short(r.base_url) },
    { label: "Status", value: (r) => status(r.status) },
    { label: "Discovered", value: (r) => short(r.last_discovered_at, 24) },
    { label: "Crawled", value: (r) => short(r.last_crawled_at, 24) },
  ]);
  table("#urlsTable", contentState.urls, [
    { label: "Domain", value: (r) => short(r.domain) },
    { label: "URL", value: (r) => short(r.url, 92) },
    { label: "Source", value: "source" },
    { label: "Status", value: (r) => status(r.status) },
    { label: "Attempts", value: "attempts" },
  ]);
  table("#pagesTable", contentState.pages, [
    { label: "Title", value: (r) => short(r.title) },
    { label: "Status", value: "http_status" },
    { label: "Quality", value: "quality_score" },
    { label: "Summary", value: "summary_model" },
    { label: "Fetched", value: (r) => short(r.fetched_at, 24) },
  ]);
  table("#topicsTable", contentState.topics, [
    { label: "Keyword", value: (r) => short(r.keyword) },
    { label: "Source", value: "source" },
    { label: "Intent", value: "intent" },
    { label: "Priority", value: "priority" },
    { label: "Status", value: (r) => status(r.status) },
    { label: "Updated", value: (r) => short(r.updated_at, 24) },
  ]);
  table("#assetsTable", contentState.assets, [
    { label: "Topic", value: (r) => short(r.keyword) },
    { label: "Title", value: (r) => short(r.title) },
    { label: "URL", value: (r) => short(r.url, 82) },
    { label: "Reliability", value: "reliability" },
    { label: "Collected", value: (r) => short(r.collected_at, 24) },
  ]);
  table("#contentTable", contentState.content_items, [
    { label: "Topic", value: (r) => short(r.keyword) },
    { label: "Title", value: (r) => short(r.seo_title) },
    { label: "Channel", value: "channel" },
    { label: "Status", value: (r) => status(r.status) },
    { label: "Updated", value: (r) => short(r.updated_at, 24) },
  ]);
  table("#reviewsTable", contentState.reviews, [
    { label: "Title", value: (r) => short(r.seo_title) },
    { label: "Reviewer", value: "reviewer" },
    { label: "Decision", value: (r) => status(r.decision) },
    { label: "Created", value: (r) => short(r.created_at, 24) },
  ]);
  table("#publicationsTable", contentState.publications, [
    { label: "Title", value: (r) => short(r.seo_title) },
    { label: "Channel", value: "channel" },
    { label: "Status", value: (r) => status(r.status) },
    { label: "URL", value: (r) => short(r.url, 72) },
  ]);
  table("#metricsTable", contentState.metrics, [
    { label: "Title", value: (r) => short(r.seo_title) },
    { label: "Channel", value: "channel" },
    { label: "Impressions", value: "impressions" },
    { label: "Clicks", value: "clicks" },
    { label: "Conversions", value: "conversions" },
    { label: "Engagement", value: "engagement" },
  ]);
  table("#workflowsTable", contentState.workflows, [
    { label: "Workflow", value: (r) => short(r.name) },
    { label: "File", value: "file" },
  ]);
}

async function refresh() {
  const [health, runtime, content] = await Promise.all([
    api("/api/health"),
    api("/api/runtime"),
    api("/api/content-factory/overview"),
  ]);
  contentState = content;
  fillForm(runtime);
  renderContentFactory();
  const state = health.ok ? "running" : "not ready";
  const dbState = content.ready ? "content DB ready" : "content DB not initialized";
  statusText.textContent = `Search: ${health.search_provider || runtime.search_provider} | Scraper: ${health.backend || runtime.scrape_backend} | Ask: ${health.web_chat_provider || runtime.web_chat_provider || "disabled"} | ${state} | ${dbState}`;
  if (health.last_error) setOutput({ last_error: health.last_error });
}

function taskPayload(task) {
  const payload = { task };
  if (task.startsWith("crawl-")) {
    payload.base_url = document.querySelector("#crawlUrlInput").value;
    payload.discover_limit = document.querySelector("#discoverLimitInput").value;
    payload.process_limit = document.querySelector("#processLimitInput").value;
    payload.limit = task === "crawl-process" ? payload.process_limit : payload.discover_limit;
  }
  if (task === "discover") {
    payload.seeds = document.querySelector("#seedInput")?.value || "";
  }
  return payload;
}

async function runTask(task) {
  setBusy(true);
  elapsedText.textContent = "running...";
  try {
    const data = await api("/api/content-factory/task", {
      method: "POST",
      body: JSON.stringify(taskPayload(task)),
    });
    elapsedText.textContent = `${data.elapsed_ms} ms`;
    setOutput(data.stdout || data);
    await refresh();
  } catch (error) {
    setOutput({ error: error.message });
  } finally {
    setBusy(false);
  }
}

document.querySelectorAll(".nav-item").forEach((item) => {
  item.addEventListener("click", () => {
    document.querySelectorAll(".nav-item").forEach((nav) => nav.classList.remove("active"));
    document.querySelectorAll(".view").forEach((view) => view.classList.remove("active"));
    item.classList.add("active");
    document.querySelector(`#view-${item.dataset.view}`).classList.add("active");
    pageTitle.textContent = titles[item.dataset.view] || "Console";
  });
});

document.querySelectorAll("[data-task]").forEach((button) => {
  button.addEventListener("click", () => runTask(button.dataset.task));
});

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  setBusy(true);
  elapsedText.textContent = "restarting...";
  const body = {
    search_provider: form.search_provider.value,
    gemini_api_key: form.gemini_api_key.value,
    gemini_model: form.gemini_model.value,
    brave_api_key: form.brave_api_key.value,
    tavily_api_key: form.tavily_api_key.value,
    tavily_search_depth: form.tavily_search_depth.value,
    scrape_backend: form.scrape_backend.value,
    headless: form.headless.checked,
    proxy_server: form.proxy_server.value,
    web_chat_provider: form.web_chat_provider.value,
    web_chat_backend: form.web_chat_backend.value,
    web_chat_headless: form.web_chat_headless.checked,
    web_chat_profile_dir: form.web_chat_profile_dir.value,
  };
  try {
    const data = await api("/api/runtime", {
      method: "PUT",
      body: JSON.stringify(body),
    });
    setOutput(data);
    await refresh();
  } catch (error) {
    setOutput({ error: error.message });
  } finally {
    elapsedText.textContent = "";
    setBusy(false);
  }
});

document.querySelector("#restartBtn").addEventListener("click", async () => {
  setBusy(true);
  elapsedText.textContent = "restarting...";
  try {
    setOutput(await api("/api/runtime/restart", { method: "POST", body: "{}" }));
    await refresh();
  } catch (error) {
    setOutput({ error: error.message });
  } finally {
    elapsedText.textContent = "";
    setBusy(false);
  }
});

document.querySelector("#testBtn").addEventListener("click", async () => {
  setBusy(true);
  elapsedText.textContent = "running...";
  setOutput("");
  const started = performance.now();
  try {
    const data = await api("/api/test", {
      method: "POST",
      body: JSON.stringify({
        prompt: document.querySelector("#promptInput").value,
        timeout_ms: Number(document.querySelector("#timeoutInput").value || 45000),
      }),
    });
    elapsedText.textContent = `${data.elapsed_ms} ms`;
    setOutput(data.answer || data);
  } catch (error) {
    elapsedText.textContent = `${Math.round(performance.now() - started)} ms`;
    setOutput({ error: error.message });
  } finally {
    setBusy(false);
  }
});

document.querySelector("#modelsBtn").addEventListener("click", async () => {
  setBusy(true);
  try {
    setOutput(await api("/v1/models"));
  } catch (error) {
    setOutput({ error: error.message });
  } finally {
    setBusy(false);
  }
});

document.querySelector("#refreshBtn").addEventListener("click", () => {
  refresh().catch((error) => setOutput({ error: error.message }));
});

refresh().catch((error) => {
  statusText.textContent = "not ready";
  setOutput({ error: error.message });
});
