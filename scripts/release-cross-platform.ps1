param(
    [switch]$SkipVerify,
    [switch]$SkipWindowsBuild
)

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectDir = Resolve-Path (Join-Path $ScriptDir "..")
$RepoRoot = git -C $ProjectDir rev-parse --show-toplevel 2>$null
if (-not $RepoRoot) {
    throw "YOURSHIGUAN is not initialized as an independent git repository yet. Run 'git init -b main' inside $ProjectDir and add the dedicated origin remote first."
}
$RepoRoot = (Resolve-Path $RepoRoot).Path
$ProjectDirPath = (Resolve-Path $ProjectDir).Path
if ($RepoRoot -ne $ProjectDirPath) {
    throw "release-cross-platform.ps1 must run inside the dedicated YOURSHIGUAN git repository. Current git root: $RepoRoot"
}

$PackageJsonPath = Join-Path $ProjectDir "package.json"
$PackageJson = Get-Content $PackageJsonPath -Raw | ConvertFrom-Json
$Version = $PackageJson.version
$TagName = "v$Version"
$ExpectedOrigin = $PackageJson.repository.url

git -C $RepoRoot remote get-url origin *> $null
if ($LASTEXITCODE -ne 0) {
    throw "Git remote 'origin' is not configured yet. Add the GitHub repository remote before running release-cross-platform.ps1."
}
$CurrentOrigin = (git -C $RepoRoot remote get-url origin).Trim()
if ($CurrentOrigin -ne $ExpectedOrigin) {
    throw "Git remote 'origin' points to '$CurrentOrigin' but this project expects '$ExpectedOrigin'."
}

if (-not $SkipVerify) {
    npm --prefix $ProjectDir run verify:desktop
}

if (-not $SkipWindowsBuild) {
    npm --prefix $ProjectDir run dist:win
}

git -C $RepoRoot add -- .

$HasChanges = git -C $RepoRoot diff --cached --quiet
if ($LASTEXITCODE -ne 0) {
    git -C $RepoRoot commit -m "release: YOURSHIGUAN v$Version"
}

git -C $RepoRoot push origin HEAD

git -C $RepoRoot rev-parse $TagName *> $null
if ($LASTEXITCODE -eq 0) {
    throw "Tag $TagName already exists locally. Bump package.json version before releasing again."
}

git -C $RepoRoot tag -a $TagName -m "YOURSHIGUAN release $Version"
git -C $RepoRoot push origin $TagName

Write-Host "Pushed branch and tag $TagName. GitHub Actions will build Linux and macOS on native runners."
