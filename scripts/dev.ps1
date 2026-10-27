<#
UGEKAZNA - Windows buyruqlari (Makefile bilan bir xil nomlar; ro'yxat: scripts\dev.ps1 help).
Foydalanish:
  powershell -ExecutionPolicy Bypass -File scripts\dev.ps1 <target> [-Version 1.0.0] [-Purpose pii]
      [-Username admin] [-FullName "Administrator"]
Bash skriptlari Git Bash (Git for Windows) orqali, qolganlari to'g'ridan-to'g'ri docker compose.
Prod target'lari (prod-up, backup, restore-test, monitor) - faqat Linux host'da: make <target>.
#>
param(
    [Parameter(Position = 0)][string]$Target = "help",
    [string]$Version = "",
    [string]$Purpose = "",
    [string]$Username = "",
    [string]$FullName = ""
)
$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)

function Get-GitBash {
    $candidates = @(
        "$env:ProgramFiles\Git\bin\bash.exe",
        "${env:ProgramFiles(x86)}\Git\bin\bash.exe",
        "$env:LOCALAPPDATA\Programs\Git\bin\bash.exe"
    )
    foreach ($candidate in $candidates) {
        if (Test-Path $candidate) { return $candidate }
    }
    throw "Git Bash topilmadi (Git for Windows o'rnatilgan bo'lishi kerak)"
}

function Invoke-Bash([string]$Script, [string[]]$Arguments = @()) {
    $bash = Get-GitBash
    & $bash $Script @Arguments
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}

function Invoke-Docker([string[]]$Arguments) {
    & docker @Arguments
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}

if (-not $Version) { $Version = (& git describe --tags --always --dirty).Trim() }
$Dev = @("compose", "-f", "deploy/compose.yml")
$Test = @("compose", "-f", "deploy/compose.test.yml", "run", "--rm", "test")
$Node = @("compose", "-f", "deploy/compose.frontend.yml", "run", "--rm", "node")
$Cli = $Dev + @("run", "--rm", "-T", "migrate", "python", "-m", "app.cli")

switch ($Target) {
    "help" {
        Get-Content -Encoding UTF8 Makefile | Select-String -Pattern '^([a-z0-9-]+):.*## (.*)$' | ForEach-Object {
            "  {0,-16} {1}" -f $_.Matches[0].Groups[1].Value, $_.Matches[0].Groups[2].Value
        }
    }
    "secrets" { & python scripts/gen_secrets.py; if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE } }
    "build" { Invoke-Docker ($Dev + @("build")) }
    "up" { Invoke-Docker ($Dev + @("up", "-d")) }
    "down" { Invoke-Docker ($Dev + @("down")) }
    "logs" { Invoke-Docker ($Dev + @("logs", "-f", "--tail=100")) }
    "web" { Invoke-Docker ($Dev + @("up", "-d", "--build", "caddy")) }
    "create-admin" { Invoke-Docker ($Cli + @("create-admin", "--username", $Username, "--full-name", $FullName)) }
    "seed-synthetic" {
        Invoke-Docker ($Dev + @("exec", "-T", "worker", "python", "-m", "app.cli", "etl-run", "--source", "synthetic", "--mode", "full"))
    }
    "audit-verify" { Invoke-Docker ($Cli + @("audit-verify")) }
    "rotate-keys" { Invoke-Docker ($Cli + @("rotate-key", "--purpose", $Purpose)) }
    "ops-check" { Invoke-Docker ($Dev + @("exec", "-T", "worker", "python", "-m", "app.cli", "ops-check")) }
    "test" { Invoke-Docker ($Test + @("pytest")) }
    "lint" { Invoke-Docker ($Test + @("ruff", "check", "app", "tests", "tools")) }
    "typecheck" { Invoke-Docker ($Test + @("mypy", "app", "tools")) }
    "check" { Invoke-Bash "scripts/check.sh" }
    "check-backend" { Invoke-Bash "scripts/check_backend.sh" }
    "check-frontend" { Invoke-Bash "scripts/check_frontend.sh" }
    "check-repo" { Invoke-Bash "scripts/check_repo.sh" }
    "hooks" { & git config core.hooksPath .githooks }
    "fe-install" { Invoke-Docker ($Node + @("npm", "ci")) }
    "fe-check" { Invoke-Docker ($Node + @("npm", "run", "check")) }
    "e2e" { Invoke-Bash "scripts/e2e.sh" }
    "pin-images" { Invoke-Bash "scripts/pin_images.sh" }
    "scan" { Invoke-Bash "scripts/scan.sh" @($Version) }
    "release" { Invoke-Bash "scripts/release.sh" @($Version) }
    "prod-config" { Invoke-Bash "scripts/prod_config.sh" }
    "test-caddy" { Invoke-Bash "scripts/tests/caddy_prod_test.sh" }
    "db-smoke" { Invoke-Bash "scripts/tests/db_image_smoke.sh" }
    "backup-selftest" { Invoke-Bash "scripts/backup_selftest.sh" }
    "load-test" { Invoke-Bash "scripts/load_test.sh" }
    default {
        Write-Error "Noma'lum target: $Target (ro'yxat: scripts\dev.ps1 help)"
        exit 2
    }
}
