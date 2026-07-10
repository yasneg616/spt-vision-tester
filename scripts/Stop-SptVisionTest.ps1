[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$ConfigPath
)

$ErrorActionPreference = "Stop"
$PluginRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$ToolsRoot = Join-Path $PluginRoot "tools"
$PythonExe = Join-Path $PluginRoot ".venv\Scripts\python.exe"

if (-not (Test-Path -LiteralPath $PythonExe -PathType Leaf)) {
    throw "Plugin venv not found. Run Start-SptVisionTest.ps1 once first, or create the venv manually."
}

$env:PYTHONPATH = $ToolsRoot
& $PythonExe -m spt_vision_tester.main stop --config (Resolve-Path -LiteralPath $ConfigPath).Path
exit $LASTEXITCODE
