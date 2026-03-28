import { spawnSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import os from "node:os";
import { fileURLToPath } from "node:url";

const scriptFile = fileURLToPath(import.meta.url);

export const scriptsDir = path.dirname(scriptFile);
export const projectRoot = path.resolve(scriptsDir, "..");
export const repoRoot = projectRoot;

export function parseArgs(argv) {
  const args = {};
  for (let index = 0; index < argv.length; index += 1) {
    const token = argv[index];
    if (!token.startsWith("--")) {
      continue;
    }
    const key = token.slice(2);
    const next = argv[index + 1];
    if (!next || next.startsWith("--")) {
      args[key] = true;
      continue;
    }
    args[key] = next;
    index += 1;
  }
  return args;
}

export function readPackageJson() {
  const packageJsonPath = path.join(projectRoot, "package.json");
  return JSON.parse(fs.readFileSync(packageJsonPath, "utf8"));
}

export function currentTarget() {
  switch (os.platform()) {
    case "win32":
      return "win";
    case "linux":
      return "linux";
    case "darwin":
      return "mac";
    default:
      throw new Error(`Unsupported host platform: ${os.platform()}`);
  }
}

export function assertTargetMatchesHost(target) {
  const host = currentTarget();
  if (target !== host) {
    throw new Error(
      `Refusing to build target "${target}" on host "${host}". Use a native ${target} runner instead.`,
    );
  }
}

export function run(command, args, options = {}) {
  const windowsShellCommands = new Set(["npm", "npx"]);
  const resolvedCommand =
    process.platform === "win32" &&
    windowsShellCommands.has(command) &&
    !path.extname(command) &&
    !command.includes(path.sep)
      ? `${command}.cmd`
      : command;

  const spawnOptions = {
    cwd: options.cwd ?? projectRoot,
    env: { ...process.env, ...(options.env ?? {}) },
    stdio: options.captureOutput ? "pipe" : "inherit",
    encoding: "utf8",
  };

  const result =
    process.platform === "win32" && resolvedCommand.toLowerCase().endsWith(".cmd")
      ? spawnSync(
          [resolvedCommand, ...args]
            .map((part) => {
              const text = String(part);
              if (!/[\s"]/u.test(text)) {
                return text;
              }
              return `"${text.replace(/"/g, '\\"')}"`;
            })
            .join(" "),
          {
            ...spawnOptions,
            shell: true,
          },
        )
      : spawnSync(resolvedCommand, args, spawnOptions);

  if (result.error) {
    throw result.error;
  }

  if (result.status !== 0) {
    const rendered = [resolvedCommand, ...args].join(" ");
    const details = options.captureOutput
      ? `\nstdout:\n${result.stdout || ""}\nstderr:\n${result.stderr || ""}`
      : "";
    throw new Error(`Command failed (${result.status}): ${rendered}${details}`);
  }

  return result;
}

export function ensureEmptyDir(targetDir) {
  fs.rmSync(targetDir, { recursive: true, force: true });
  fs.mkdirSync(targetDir, { recursive: true });
}

export function ensureDir(targetDir) {
  fs.mkdirSync(targetDir, { recursive: true });
}

export function writeFile(targetPath, contents) {
  ensureDir(path.dirname(targetPath));
  fs.writeFileSync(targetPath, contents, "utf8");
}

export function copyFile(sourcePath, destinationPath, mode = null) {
  ensureDir(path.dirname(destinationPath));
  fs.copyFileSync(sourcePath, destinationPath);
  if (mode !== null) {
    fs.chmodSync(destinationPath, mode);
  }
}

export function versionParts(version) {
  const numeric = String(version)
    .split(".")
    .slice(0, 4)
    .map((part) => Number.parseInt(part, 10))
    .filter((part) => Number.isFinite(part));
  while (numeric.length < 4) {
    numeric.push(0);
  }
  return numeric.slice(0, 4);
}

export function architectureForDeb(arch = process.arch) {
  switch (arch) {
    case "x64":
      return "amd64";
    case "arm64":
      return "arm64";
    default:
      throw new Error(`Unsupported Debian architecture: ${arch}`);
  }
}

export function archiveBaseName(target, pkg, release) {
  const archMap = {
    win: process.arch === "arm64" ? "arm64" : "x64",
    linux: process.arch === "arm64" ? "arm64" : "x64",
    mac: process.arch === "arm64" ? "arm64" : "x64",
  };
  return `${release.appSlug}_${pkg.version}_${target}_${archMap[target]}`;
}

export function normalizeWindowsExeName(name) {
  return name.toLowerCase().endsWith(".exe") ? name : `${name}.exe`;
}
