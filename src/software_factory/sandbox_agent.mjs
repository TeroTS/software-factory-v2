// Read task and Copilot bearer from stdin; run exact-model Pi with temporary private configuration, then remove it.
import { mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { spawnSync } from "node:child_process";

const payload = JSON.parse(readFileSync(0, "utf8"));
const directory = mkdtempSync(join(tmpdir(), "factory-pi-"));
let exit = 1;
try {
  writeFileSync(
    join(directory, "auth.json"),
    JSON.stringify({
      "github-copilot": { type: "api_key", key: payload.bearer },
    }),
    { mode: 0o600 },
  );
  writeFileSync(
    join(directory, "models.json"),
    JSON.stringify({
      providers: { "github-copilot": { baseUrl: payload.endpoint } },
    }),
    { mode: 0o600 },
  );
  const env = {
    ...process.env,
    PI_CODING_AGENT_DIR: directory,
    PI_OFFLINE: "1",
    PI_TELEMETRY: "0",
  };
  const flags = [
    "--no-extensions",
    "--no-mcp",
    "--no-skills",
    "--no-prompt-templates",
    "--no-themes",
    "--no-approve",
    "--offline",
    "--no-session",
  ];
  const catalog = spawnSync("pi", [...flags, "--list-models", payload.model], {
    env,
    encoding: "utf8",
  });
  const available =
    catalog.status === 0 &&
    // Match each catalog row by exact provider/model identity, without fuzzy fallback.
    catalog.stdout.split("\n").some((line) => {
      const columns = line.trim().split(/\s+/);
      return columns[0] === "github-copilot" && columns[1] === payload.model;
    });
  if (!available) {
    console.error("configured Copilot model is unavailable");
  } else {
    const prompt =
      "Implement the issue in this repository without clarification questions. " +
      "Use only the task snapshot and repository contents; do not retrieve issue comments, attachments, or linked pages. " +
      "Add meaningful tests. Do not publish, commit, or push; the host handles publication after verification.\n" +
      "Task snapshot:\n" +
      JSON.stringify(payload.snapshot);
    const result = spawnSync(
      "pi",
      [
        ...flags,
        "--print",
        "--provider",
        "github-copilot",
        "--model",
        payload.model,
        "--tools",
        "read,bash,edit,write",
      ],
      { env, input: prompt, stdio: ["pipe", "inherit", "inherit"] },
    );
    exit = result.status ?? 1;
  }
} finally {
  rmSync(directory, { recursive: true, force: true });
}
process.exitCode = exit;
