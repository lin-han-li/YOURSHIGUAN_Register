import fs from "node:fs";
import path from "node:path";

import { projectRoot } from "./_shared.mjs";
import { parse } from "yaml";

const workflowPath = path.join(projectRoot, ".github", "workflows", "build-desktop.yml");

if (!fs.existsSync(workflowPath)) {
  throw new Error(`Workflow file not found: ${workflowPath}`);
}

const workflow = parse(fs.readFileSync(workflowPath, "utf8"));
const triggers = workflow.on || workflow["on"];

if (!triggers || !("workflow_dispatch" in triggers)) {
  throw new Error("Workflow must expose workflow_dispatch.");
}

const pushTags = triggers.push?.tags || [];
if (!pushTags.includes("v*")) {
  throw new Error('Workflow push trigger must include tags: ["v*"].');
}

const matrixInclude = workflow.jobs?.build?.strategy?.matrix?.include || [];
const expectedTargets = new Map([
  ["windows-latest", "win"],
  ["ubuntu-latest", "linux"],
  ["macos-latest", "mac"],
]);

for (const [osName, target] of expectedTargets.entries()) {
  const found = matrixInclude.some((item) => item.os === osName && item.target === target);
  if (!found) {
    throw new Error(`Workflow matrix is missing ${osName}/${target}.`);
  }
}

const buildSteps = workflow.jobs?.build?.steps || [];
const uploadStep = buildSteps.find((step) => String(step.uses || "").startsWith("actions/upload-artifact"));
if (!uploadStep) {
  throw new Error("Workflow must upload build artifacts.");
}

const uploadPath = String(uploadStep.with?.path || "");
if (!uploadPath.includes("artifacts/${{ matrix.target }}/**")) {
  throw new Error(`Unexpected upload artifact path: ${uploadPath}`);
}

const releaseJob = workflow.jobs?.release;
if (!releaseJob) {
  throw new Error("Workflow must define a release job.");
}

const releaseSteps = releaseJob.steps || [];
const releaseAction = releaseSteps.find((step) => String(step.uses || "").startsWith("softprops/action-gh-release"));
if (!releaseAction) {
  throw new Error("Release job must publish assets to GitHub Releases.");
}

const releaseFiles = String(releaseAction.with?.files || "");
for (const expectedPattern of ["release-artifacts/**/*.exe", "release-artifacts/**/*.deb", "release-artifacts/**/*.tar.gz", "release-artifacts/**/*.pkg", "release-artifacts/**/*.zip"]) {
  if (!releaseFiles.includes(expectedPattern)) {
    throw new Error(`Release files glob is missing ${expectedPattern}.`);
  }
}

console.log(`Workflow checks passed for ${path.relative(projectRoot, workflowPath)}`);
