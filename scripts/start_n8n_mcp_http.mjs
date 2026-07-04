import { spawn } from "node:child_process";

const env = {
  ...process.env,
  N8N_MODE: process.env.N8N_MODE || "true",
  MCP_MODE: process.env.MCP_MODE || "http",
  N8N_API_URL: process.env.N8N_API_URL || "http://localhost:5678",
  WEBHOOK_SECURITY_MODE: process.env.WEBHOOK_SECURITY_MODE || "moderate",
  MCP_AUTH_TOKEN:
    process.env.N8N_MCP_AUTH_TOKEN ||
    process.env.MCP_AUTH_TOKEN ||
    "local-dev-n8n-mcp-token-change-me-123456",
  AUTH_TOKEN:
    process.env.N8N_MCP_AUTH_TOKEN ||
    process.env.AUTH_TOKEN ||
    process.env.MCP_AUTH_TOKEN ||
    "local-dev-n8n-mcp-token-change-me-123456",
  PORT: process.env.PORT || "3000",
  LOG_LEVEL: process.env.N8N_MCP_LOG_LEVEL || process.env.LOG_LEVEL || "info",
};

const child = spawn("node", ["node_modules/n8n-mcp/dist/http-server.js"], {
  env,
  stdio: "inherit",
  shell: process.platform === "win32",
});

child.on("exit", (code, signal) => {
  if (signal) {
    process.kill(process.pid, signal);
  }
  process.exit(code ?? 0);
});
