[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$ConfigPath,

    [string]$ScenarioPath,
    [string]$CustomScenarioPath,
    [switch]$ServerOnly,
    [switch]$LaunchClient,
    [switch]$UseComputer,
    [switch]$CollectLogs,
    [switch]$AnalyzeLogs,
    [switch]$AutoRaid,
    [switch]$AutoRaidNoAi,
    [switch]$ComputerUseSession
)

$ErrorActionPreference = "Stop"
$PluginRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$ToolsRoot = Join-Path $PluginRoot "tools"
$VenvRoot = Join-Path $PluginRoot ".venv"
$PythonExe = Join-Path $VenvRoot "Scripts\python.exe"
$Requirements = Join-Path $ToolsRoot "requirements.txt"
$RequireScenarioSchema = $false

if ($AutoRaid -and $AutoRaidNoAi) {
    throw "Choose only one built-in raid mode: -AutoRaid or -AutoRaidNoAi."
}

if ($ComputerUseSession -and ($ServerOnly -or $ScenarioPath -or $CustomScenarioPath -or $AutoRaid -or $AutoRaidNoAi)) {
    throw "-ComputerUseSession cannot be combined with server-only, scenario, or AutoRaid modes."
}

if ($CustomScenarioPath -and ($ScenarioPath -or $AutoRaid -or $AutoRaidNoAi)) {
    throw "-CustomScenarioPath cannot be combined with -ScenarioPath, -AutoRaid, or -AutoRaidNoAi."
}

if ($CustomScenarioPath -and $ServerOnly) {
    throw "-CustomScenarioPath cannot be combined with -ServerOnly. Use the server-only command first, then run the scenario."
}

if ($CustomScenarioPath) {
    $ScenarioPath = $CustomScenarioPath
    $RequireScenarioSchema = $true
}

if ($ComputerUseSession) {
    $LaunchClient = $true
    $UseComputer = $true
}

if ($AutoRaid) {
    if (-not $ScenarioPath) {
        $ScenarioPath = Join-Path $PluginRoot "config\scenarios\auto-offline-raid-smoke-test.json"
    }
    $LaunchClient = $true
    $UseComputer = $true
    $CollectLogs = $true
    $AnalyzeLogs = $true
}

if ($AutoRaidNoAi) {
    if (-not $ScenarioPath) {
        $ScenarioPath = Join-Path $PluginRoot "config\scenarios\auto-offline-raid-no-ai-smoke-test.json"
    }
    $LaunchClient = $true
    $UseComputer = $true
    $CollectLogs = $true
    $AnalyzeLogs = $true
}

function Find-Python {
    $candidates = @("python", "py")
    foreach ($candidate in $candidates) {
        $cmd = Get-Command $candidate -ErrorAction SilentlyContinue
        if ($cmd) { return $cmd.Source }
    }
    throw "Python was not found on PATH. Install Python 3.10+ or add it to PATH."
}

if (-not (Test-Path -LiteralPath $PythonExe -PathType Leaf)) {
    $SystemPython = Find-Python
    & $SystemPython -m venv $VenvRoot
}

& $PythonExe -c "import mss, psutil, pyautogui, pygetwindow, win32api; from PIL import Image" 2>$null
$DependenciesReady = $LASTEXITCODE -eq 0

if (-not $DependenciesReady) {
    Write-Host "Installing missing Python dependencies..."
    & $PythonExe -m pip install -r $Requirements | Out-Host
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Default PyPI install failed; retrying with the Tsinghua mirror."
        & $PythonExe -m pip install -i https://pypi.tuna.tsinghua.edu.cn/simple --trusted-host pypi.tuna.tsinghua.edu.cn -r $Requirements | Out-Host
        if ($LASTEXITCODE -ne 0) {
            throw "Failed to install Python requirements. Check network/proxy settings or install tools/requirements.txt manually."
        }
    }
}

$env:PYTHONPATH = $ToolsRoot
$ResolvedScenarioPath = $null
if ($ScenarioPath) {
    $ResolvedScenarioPath = (Resolve-Path -LiteralPath $ScenarioPath).Path
}

if ($RequireScenarioSchema) {
    Write-Host "Validating custom scenario before any SPT process is launched..."
    & $PythonExe -m spt_vision_tester.scenario_validator --scenario $ResolvedScenarioPath
    if ($LASTEXITCODE -ne 0) {
        throw "Custom scenario validation failed. No SPT process was launched."
    }
}

$argsList = @(
    "-m", "spt_vision_tester.main",
    "run",
    "--config", (Resolve-Path -LiteralPath $ConfigPath).Path
)

if ($ResolvedScenarioPath) { $argsList += @("--scenario", $ResolvedScenarioPath) }
if ($RequireScenarioSchema) { $argsList += "--require-scenario-schema" }
if ($ServerOnly) { $argsList += "--server-only" }
if ($LaunchClient) { $argsList += "--launch-client" }
if ($UseComputer) { $argsList += "--use-computer" }
if ($CollectLogs) { $argsList += "--collect-logs" }
if ($AnalyzeLogs) { $argsList += "--analyze-logs" }
if ($ComputerUseSession) { $argsList += "--computer-use-session" }

Write-Host ""
Write-Host "SPT vision test starting"
Write-Host "  Config: $ConfigPath"
Write-Host "  Scenario: $ScenarioPath"
Write-Host "  CustomScenario: $RequireScenarioSchema"
Write-Host "  ServerOnly: $ServerOnly"
Write-Host "  LaunchClient: $LaunchClient"
Write-Host "  UseComputer: $UseComputer"
Write-Host "  AutoRaid: $AutoRaid"
Write-Host "  AutoRaidNoAi: $AutoRaidNoAi"
Write-Host "  ComputerUseSession: $ComputerUseSession"
Write-Host ""

& $PythonExe @argsList
$exitCode = $LASTEXITCODE
Write-Host ""
Write-Host "SPT vision test finished with exit code $exitCode"
exit $exitCode
