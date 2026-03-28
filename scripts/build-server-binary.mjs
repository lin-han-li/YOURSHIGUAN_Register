import fs from "node:fs";
import path from "node:path";

import {
  assertTargetMatchesHost,
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
const specPath = path.join(projectRoot, release.spec);
const distDir = path.join(projectRoot, "dist", "bin", target);
const workDir = path.join(projectRoot, "build", "pyinstaller", target);
const metaDir = path.join(projectRoot, "dist", "meta");
const tempDir = path.join(projectRoot, "build", "release-temp", target);

ensureEmptyDir(distDir);
ensureEmptyDir(workDir);
ensureDir(metaDir);
ensureEmptyDir(tempDir);

const executableName =
  target === "win"
    ? path.parse(normalizeWindowsExeName(release.windowsExecutableName)).name
    : release.binaryName;

let versionFile = "";
if (target === "win") {
  const versionNumbers = versionParts(pkg.version);
  versionFile = path.join(tempDir, "windows-version-info.txt");
  writeFile(
    versionFile,
    `VSVersionInfo(
  ffi=FixedFileInfo(
    filevers=(${versionNumbers.join(", ")}),
    prodvers=(${versionNumbers.join(", ")}),
    mask=0x3f,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0)
  ),
  kids=[
    StringFileInfo(
      [
        StringTable(
          '040904B0',
          [
            StringStruct('CompanyName', '${release.publisher}'),
            StringStruct('FileDescription', '${release.appName}'),
            StringStruct('FileVersion', '${pkg.version}'),
            StringStruct('InternalName', '${executableName}'),
            StringStruct('OriginalFilename', '${normalizeWindowsExeName(release.windowsExecutableName)}'),
            StringStruct('ProductName', '${release.appName}'),
            StringStruct('ProductVersion', '${pkg.version}')
          ]
        )
      ]
    ),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])
  ]
)`,
  );
}

run("python", [
  "-m",
  "PyInstaller",
  "--noconfirm",
  "--clean",
  "--distpath",
  distDir,
  "--workpath",
  workDir,
  specPath,
], {
  env: {
    PYI_EXECUTABLE_NAME: executableName,
    PYI_VERSION_FILE: versionFile,
  },
});

const binaryPath = path.join(
  distDir,
  target === "win"
    ? normalizeWindowsExeName(release.windowsExecutableName)
    : release.binaryName,
);

if (!fs.existsSync(binaryPath)) {
  throw new Error(`Expected built binary not found: ${binaryPath}`);
}

const manifestPath = path.join(metaDir, `${target}.json`);
const manifest = {
  target,
  version: pkg.version,
  binaryPath,
  executableName: path.basename(binaryPath),
  appName: release.appName,
  appSlug: release.appSlug,
};

writeFile(manifestPath, `${JSON.stringify(manifest, null, 2)}\n`);
console.log(`Built ${target} binary: ${binaryPath}`);
