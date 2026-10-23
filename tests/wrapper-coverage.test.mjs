import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import test from "node:test";

test("Pi bridge success and failure behavior", () => {
  const result = spawnSync(
    "uv",
    ["run", "--frozen", "pytest", "tests/test_agent_wrapper.py", "-q"],
    { stdio: "inherit", env: process.env },
  );
  assert.equal(result.status, 0);
});
