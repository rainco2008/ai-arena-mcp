import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { getSharedDatabase, closeSharedDatabase } from "../node_modules/n8n-mcp/dist/database/shared-database.js";
import { WorkflowValidator } from "../node_modules/n8n-mcp/dist/services/workflow-validator.js";
import { EnhancedConfigValidator } from "../node_modules/n8n-mcp/dist/services/enhanced-config-validator.js";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(__dirname, "..");
const workflowDir = path.resolve(root, process.argv[2] || "workflows/n8n");
const dbPath = path.resolve(root, "node_modules/n8n-mcp/data/nodes.db");

function collectJsonFiles(dir) {
  const entries = fs.readdirSync(dir, { withFileTypes: true });
  const files = [];
  for (const entry of entries) {
    const fullPath = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      files.push(...collectJsonFiles(fullPath));
    } else if (entry.isFile() && entry.name.endsWith(".json")) {
      files.push(fullPath);
    }
  }
  return files.sort();
}

const state = await getSharedDatabase(dbPath);
try {
  const validator = new WorkflowValidator(state.repository, EnhancedConfigValidator);
  const files = collectJsonFiles(workflowDir);
  const results = [];
  for (const file of files) {
    const workflow = JSON.parse(fs.readFileSync(file, "utf8"));
    const validation = await validator.validateWorkflow(workflow, {
      validateNodes: true,
      validateConnections: true,
      validateExpressions: true,
      profile: "runtime",
    });
    results.push({
      file: path.relative(root, file).replaceAll("\\", "/"),
      name: workflow.name || path.basename(file),
      valid: validation.valid,
      errors: validation.errors,
      warnings: validation.warnings,
      statistics: validation.statistics,
      suggestions: validation.suggestions,
    });
  }
  const summary = {
    ok: results.every((result) => result.valid),
    workflowCount: results.length,
    invalidCount: results.filter((result) => !result.valid).length,
    warningCount: results.reduce((total, result) => total + result.warnings.length, 0),
    results,
  };
  console.log(JSON.stringify(summary, null, 2));
  if (!summary.ok) {
    process.exitCode = 1;
  }
} finally {
  await closeSharedDatabase();
}
