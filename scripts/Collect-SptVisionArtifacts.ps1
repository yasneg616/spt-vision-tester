[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$ConfigPath,

    [string]$RunPath,
    [switch]$Zip
)

$ErrorActionPreference = "Stop"
$PluginRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$ToolsRoot = Join-Path $PluginRoot "tools"
$PythonExe = Join-Path $PluginRoot ".venv\Scripts\python.exe"

if (-not (Test-Path -LiteralPath $PythonExe -PathType Leaf)) {
    throw "Plugin venv not found. Run Start-SptVisionTest.ps1 once first."
}

$env:PYTHONPATH = $ToolsRoot
$argsList = @("-m", "spt_vision_tester.main", "collect", "--config", (Resolve-Path -LiteralPath $ConfigPath).Path)
if ($RunPath) { $argsList += @("--run", (Resolve-Path -LiteralPath $RunPath).Path) }
& $PythonExe @argsList
$exitCode = $LASTEXITCODE

if ($Zip) {
    $config = Get-Content -Raw -LiteralPath $ConfigPath | ConvertFrom-Json
    $root = if ($RunPath) { (Resolve-Path -LiteralPath $RunPath).Path } else { Join-Path (Get-Location).Path $config.ArtifactsRoot }
    $latest = if (Test-Path -LiteralPath $root -PathType Container) {
        Get-ChildItem -LiteralPath $root -Directory | Sort-Object LastWriteTimeUtc -Descending | Select-Object -First 1
    }
    if ($latest) {
        $zipPath = "$($latest.FullName).zip"
        Compress-Archive -Path (Join-Path $latest.FullName "*") -DestinationPath $zipPath -Force
        Write-Host "Artifact zip: $zipPath"
    }
}

exit $exitCode
