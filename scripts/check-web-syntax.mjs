import fs from "node:fs";
import os from "node:os";
import path from "node:path";

import { ensureEmptyDir, parseArgs, projectRoot, run, writeFile } from "./_shared.mjs";

const args = parseArgs(process.argv.slice(2));
const scanRoot = path.resolve(projectRoot, args.root || ".");
const tempRoot = path.join(projectRoot, "build", "check-web-syntax");

const skippedDirectories = new Set([
  ".git",
  "accounts",
  "artifacts",
  "build",
  "codex_tokens",
  "dist",
  "node_modules",
  "__pycache__",
]);

const htmlExtensions = new Set([".html", ".htm"]);
const sourceExtensions = new Set([".py", ".js", ".mjs", ".cjs", ".jsx", ".ts", ".tsx"]);
const jsExtensions = new Set([".js", ".mjs", ".cjs"]);

function walk(dirPath, files = []) {
  for (const entry of fs.readdirSync(dirPath, { withFileTypes: true })) {
    if (entry.isDirectory()) {
      if (!skippedDirectories.has(entry.name)) {
        walk(path.join(dirPath, entry.name), files);
      }
      continue;
    }
    files.push(path.join(dirPath, entry.name));
  }
  return files;
}

function findInlineScripts(contents) {
  const blocks = [];
  const regex = /<script\b([^>]*)>([\s\S]*?)<\/script>/gi;
  let match = regex.exec(contents);
  while (match) {
    const attrs = match[1] || "";
    const scriptBody = match[2] || "";
    const hasSrc = /\bsrc\s*=/.test(attrs);
    const explicitType = attrs.match(/\btype\s*=\s*["']([^"']+)["']/i);
    const typeValue = explicitType ? explicitType[1].trim().toLowerCase() : "";
    const isJavaScript =
      !typeValue ||
      typeValue === "text/javascript" ||
      typeValue === "application/javascript" ||
      typeValue === "module";

    if (!hasSrc && isJavaScript && scriptBody.trim()) {
      blocks.push(scriptBody);
    }

    match = regex.exec(contents);
  }
  return blocks;
}

ensureEmptyDir(tempRoot);

const files = walk(scanRoot);
const applicationHtmlFiles = files.filter((filePath) => htmlExtensions.has(path.extname(filePath).toLowerCase()));
const embeddedSourceFiles = files.filter((filePath) => {
  const relativePath = path.relative(projectRoot, filePath);
  if (relativePath.startsWith(`scripts${path.sep}`)) {
    return false;
  }
  if (!sourceExtensions.has(path.extname(filePath).toLowerCase())) {
    return false;
  }
  const contents = fs.readFileSync(filePath, "utf8");
  return contents.includes("<script") || contents.includes("<html");
});
const javaScriptFiles = files.filter((filePath) => jsExtensions.has(path.extname(filePath).toLowerCase()));

if (applicationHtmlFiles.length === 0 && embeddedSourceFiles.length === 0) {
  console.log("No application HTML files or embedded inline scripts were found.");
} else {
  let blockIndex = 0;
  for (const filePath of [...applicationHtmlFiles, ...embeddedSourceFiles]) {
    const contents = fs.readFileSync(filePath, "utf8");
    const blocks = findInlineScripts(contents);
    for (const block of blocks) {
      const tempFile = path.join(tempRoot, `inline-script-${blockIndex}.mjs`);
      blockIndex += 1;
      writeFile(tempFile, `${block}\n`);
      run("node", ["--check", tempFile]);
    }
    console.log(`Checked inline scripts in ${path.relative(projectRoot, filePath)}`);
  }
}

for (const filePath of javaScriptFiles) {
  run("node", ["--check", filePath]);
  console.log(`Checked JS syntax: ${path.relative(projectRoot, filePath)}`);
}

const buildSentinel = path.join(tempRoot, `.ok-${Date.now()}-${os.platform()}`);
writeFile(buildSentinel, "ok\n");
console.log("Web syntax check completed.");
