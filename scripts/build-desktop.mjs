import fs from "node:fs";
import path from "node:path";

import {
  architectureForDeb,
  archiveBaseName,
  assertTargetMatchesHost,
  copyFile,
  currentTarget,
  ensureDir,
  ensureEmptyDir,
  normalizeWindowsExeName,
  parseArgs,
  projectRoot,
  readPackageJson,
  run,
  versionParts,
  writeFile,
} from "./_shared.mjs";

const args = parseArgs(process.argv.slice(2));
const target = args.target || currentTarget();

assertTargetMatchesHost(target);

const pkg = readPackageJson();
const release = pkg.desktopRelease;
const artifactRoot = path.join(projectRoot, "artifacts", target);
const buildRoot = path.join(projectRoot, "build", "packages", target);
const metaPath = path.join(projectRoot, "dist", "meta", `${target}.json`);

if (!args["skip-build"]) {
  run(process.execPath, [path.join(projectRoot, "scripts", "build-server-binary.mjs"), "--target", target]);
}

if (!fs.existsSync(metaPath)) {
  throw new Error(`Build manifest missing: ${metaPath}`);
}

ensureEmptyDir(artifactRoot);
ensureEmptyDir(buildRoot);

const manifest = JSON.parse(fs.readFileSync(metaPath, "utf8"));
const artifactBase = archiveBaseName(target, pkg, release);

function writeArtifactManifest(files) {
  const summary = {
    target,
    version: pkg.version,
    files,
  };
  writeFile(path.join(artifactRoot, "artifact-manifest.json"), `${JSON.stringify(summary, null, 2)}\n`);
}

function buildWindowsPackage() {
  const setupScript = path.join(projectRoot, release.windowsInstallerScript);
  const portablePath = path.join(artifactRoot, `${artifactBase}_portable.exe`);
  copyFile(manifest.binaryPath, portablePath);

  const candidatePaths = [
    process.env.ISCC_PATH,
    "D:\\Inno Setup 6\\ISCC.exe",
    path.join(process.env["ProgramFiles(x86)"] || "", "Inno Setup 6", "ISCC.exe"),
    path.join(process.env.ProgramFiles || "", "Inno Setup 6", "ISCC.exe"),
  ].filter(Boolean);

  const isccPath = candidatePaths.find((candidate) => fs.existsSync(candidate));
  if (!isccPath) {
    throw new Error("ISCC.exe not found. Install Inno Setup 6 or set ISCC_PATH.");
  }

  const setupBaseName = `${artifactBase}_setup`;
  run(isccPath, [
    `/DMyAppVersion=${pkg.version}`,
    `/DMyAppPublisher=${release.publisher}`,
    `/DMyAppPublisherURL=${release.publisherUrl}`,
    `/DMyAppSupportURL=${release.supportUrl}`,
    `/DMyAppExeName=${normalizeWindowsExeName(release.windowsExecutableName)}`,
    `/DMySourceExePath=${manifest.binaryPath}`,
    `/DMyOutputDir=${artifactRoot}`,
    `/DMyOutputBaseFilename=${setupBaseName}`,
    setupScript,
  ]);

  const setupPath = path.join(artifactRoot, `${setupBaseName}.exe`);
  if (!fs.existsSync(setupPath)) {
    throw new Error(`Expected Windows installer not found: ${setupPath}`);
  }

  writeArtifactManifest([portablePath, setupPath]);
}

function buildLinuxPackage() {
  const packageRoot = path.join(buildRoot, "deb-root");
  const portableRoot = path.join(buildRoot, "portable", release.appSlug);
  const installRoot = path.join(packageRoot, "opt", release.appSlug);
  const binaryInstallPath = path.join(installRoot, release.binaryName);
  const wrapperPath = path.join(packageRoot, "usr", "bin", release.appSlug);
  const docPath = path.join(packageRoot, "usr", "share", "doc", release.appSlug, "README.txt");
  const controlPath = path.join(packageRoot, "DEBIAN", "control");

  ensureEmptyDir(packageRoot);
  ensureEmptyDir(portableRoot);

  copyFile(manifest.binaryPath, binaryInstallPath, 0o755);
  writeFile(
    wrapperPath,
    `#!/usr/bin/env sh
exec "/opt/${release.appSlug}/${release.binaryName}" "$@"
`,
  );
  fs.chmodSync(wrapperPath, 0o755);
  copyFile(path.join(projectRoot, "README.md"), docPath);
  copyFile(manifest.binaryPath, path.join(portableRoot, release.binaryName), 0o755);
  copyFile(path.join(projectRoot, "README.md"), path.join(portableRoot, "README.txt"));

  const control = [
    `Package: ${release.appSlug}`,
    `Version: ${pkg.version}`,
    "Section: utils",
    "Priority: optional",
    `Architecture: ${architectureForDeb(process.arch)}`,
    `Maintainer: ${release.linuxMaintainer}`,
    `Description: ${release.appName} packaged with PyInstaller.`,
    " This package installs the native Linux build and a small launcher script.",
  ].join("\n");
  writeFile(controlPath, `${control}\n`);

  const debPath = path.join(artifactRoot, `${artifactBase}.deb`);
  run("dpkg-deb", ["--build", packageRoot, debPath]);

  const tarPath = path.join(artifactRoot, `${artifactBase}.tar.gz`);
  run("tar", ["-czf", tarPath, "-C", path.join(buildRoot, "portable"), release.appSlug]);

  writeArtifactManifest([debPath, tarPath]);
}

function buildMacPackage() {
  const packageRoot = path.join(buildRoot, "pkg-root");
  const portableRoot = path.join(buildRoot, "portable", release.appSlug);
  const libRoot = path.join(packageRoot, "usr", "local", "lib", release.appSlug);
  const binaryInstallPath = path.join(libRoot, release.binaryName);
  const wrapperPath = path.join(packageRoot, "usr", "local", "bin", release.appSlug);
  const docPath = path.join(packageRoot, "usr", "local", "share", "doc", release.appSlug, "README.txt");

  ensureEmptyDir(packageRoot);
  ensureEmptyDir(portableRoot);

  copyFile(manifest.binaryPath, binaryInstallPath, 0o755);
  writeFile(
    wrapperPath,
    `#!/usr/bin/env sh
exec "/usr/local/lib/${release.appSlug}/${release.binaryName}" "$@"
`,
  );
  fs.chmodSync(wrapperPath, 0o755);
  copyFile(path.join(projectRoot, "README.md"), docPath);
  copyFile(manifest.binaryPath, path.join(portableRoot, release.binaryName), 0o755);
  copyFile(path.join(projectRoot, "README.md"), path.join(portableRoot, "README.txt"));

  const pkgPath = path.join(artifactRoot, `${artifactBase}_unsigned.pkg`);
  run("pkgbuild", [
    "--root",
    packageRoot,
    "--identifier",
    release.bundleIdentifier,
    "--version",
    pkg.version,
    "--install-location",
    "/",
    pkgPath,
  ]);

  const signingIdentity = process.env.APPLE_SIGNING_IDENTITY;
  let finalPkgPath = pkgPath;
  if (signingIdentity) {
    const signedPkgPath = path.join(artifactRoot, `${artifactBase}.pkg`);
    run("productsign", ["--sign", signingIdentity, pkgPath, signedPkgPath]);
    finalPkgPath = signedPkgPath;
  }

  const zipPath = path.join(artifactRoot, `${artifactBase}.zip`);
  run("ditto", ["-c", "-k", "--keepParent", path.join(buildRoot, "portable", release.appSlug), zipPath]);

  writeArtifactManifest([finalPkgPath, zipPath]);
}

switch (target) {
  case "win":
    buildWindowsPackage();
    break;
  case "linux":
    buildLinuxPackage();
    break;
  case "mac":
    buildMacPackage();
    break;
  default:
    throw new Error(`Unsupported target: ${target}`);
}

console.log(`Built ${target} desktop artifacts in ${artifactRoot}`);
