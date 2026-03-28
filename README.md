# YOURSHIGUAN Register Release Guide

This project is a Python desktop CLI packaged with PyInstaller. It is not an Electron app. The release layer added here uses `package.json` and `scripts/*.mjs` only as orchestration so Windows, Linux, and macOS can follow one stable release flow without forcing cross-OS builds.

## Release Model

- Windows packages are built on Windows only.
- Linux packages are built on Linux only.
- macOS packages are built on macOS only.
- GitHub tag builds upload all three platform artifacts to one Release.
- Runtime data is written to a user data directory when the app is frozen, so Linux and macOS installers do not break by trying to write into the installation directory.

## Local Setup

Install build dependencies in the repository root:

```powershell
python -m pip install -r requirements-build.txt
npm install
```

## Windows Local Build

Run the full local verification gate:

```powershell
npm run verify:desktop
```

Build the Windows binary and installer on a Windows host:

```powershell
npm run dist:win
```

Artifacts are written to:

- `artifacts/win/`
- `dist/bin/win/`

## Why Linux And macOS Must Use Native Runners

PyInstaller bundles platform-native libraries from the current machine, including `curl_cffi` and Python extension modules. A Windows build contains `.dll/.pyd`, so it cannot safely be reused for Linux or macOS packages. The GitHub Actions workflow therefore rebuilds the binary on each native runner:

- Windows: `exe + Inno Setup installer`
- Linux: `PyInstaller binary + .deb + .tar.gz`
- macOS: `PyInstaller binary + unsigned .pkg + .zip`

## GitHub Actions

The workflow lives at `.github/workflows/build-desktop.yml`.

Triggers:

- `workflow_dispatch`
- `push` tags matching `v*`

What it does:

1. Installs Node and Python dependencies.
2. Runs `npm run verify:desktop`.
3. Builds only the package that matches the native runner.
4. Uploads artifacts for each platform.
5. On tag builds, creates or updates a GitHub Release with all artifacts attached.

## Windows Release Push

Use the helper script from Windows after bumping the version in `package.json`:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/release-cross-platform.ps1
```

The script:

1. Runs `npm run verify:desktop`
2. Runs `npm run dist:win`
3. Commits the current project and workflow changes
4. Pushes the current branch
5. Creates and pushes tag `v<package.json version>`

It expects `YOURSHIGUAN` itself to be an independent git repository with `origin` set to `https://github.com/lin-han-li/YOURSHIGUAN_Register.git`.

## End-User Installation

- Windows: download the `*_win_x64_setup.exe` installer and run it.
- Linux: install the `.deb` with `sudo apt install ./<file>.deb`, or unpack the `.tar.gz` if you want a portable bundle.
- macOS: install the unsigned `.pkg` with `sudo installer -pkg <file>.pkg -target /`. Because the package is unsigned and not notarized, Gatekeeper may require an explicit trust override before first launch.

## Current Gaps

These release changes intentionally focus on stable packaging first. The following are still future work:

- Windows code signing
- macOS signing and notarization
- Linux RPM output
- Automatic update delivery
- Repository-specific release notes templating
