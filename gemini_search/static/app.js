const form = document.querySelector("#runtimeForm");
const statusText = document.querySelector("#statusText");
const output = document.querySelector("#output");
const elapsedText = document.querySelector("#elapsedText");

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
  form.search_provider.value = config.search_provider || "google_ai_mode";
  form.gemini_api_key.value = config.gemini_api_key || "";
  form.gemini_model.value = config.gemini_model || "gemini-2.5-flash";
  form.brave_api_key.value = config.brave_api_key || "";
  form.tavily_api_key.value = config.tavily_api_key || "";
  form.tavily_search_depth.value = config.tavily_search_depth || "basic";
  form.browser_backend.value = config.browser_backend || "playwright";
  form.channel.value = config.channel || "chrome";
  form.headless.checked = config.headless === true;
  form.user_data_dir.value = config.user_data_dir || "profiles/default";
  form.proxy_server.value = config.proxy_server || "";
  form.cdp_url.value = config.cdp_url || "";
}

async function refresh() {
  const [health, runtime] = await Promise.all([
    api("/api/health"),
    api("/api/runtime"),
  ]);
  fillForm(runtime);
  const state = health.ok ? "running" : "not ready";
  statusText.textContent = `Provider: ${health.search_provider || runtime.search_provider} | Browser: ${health.backend || runtime.browser_backend} | ${state}`;
  if (health.last_error) setOutput({ last_error: health.last_error });
}

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
    browser_backend: form.browser_backend.value,
    channel: form.channel.value,
    headless: form.headless.checked,
    user_data_dir: form.user_data_dir.value,
    proxy_server: form.proxy_server.value,
    cdp_url: form.cdp_url.value,
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
