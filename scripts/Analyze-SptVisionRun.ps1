[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$ConfigPath,

    [Parameter(Mandatory = $true)]
    [string]$RunPath
)

$ErrorActionPreference = "Stop"
$PluginRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$ToolsRoot = Join-Path $PluginRoot "tools"
$PythonExe = Join-Path $PluginRoot ".venv\Scripts\python.exe"

if (-not (Test-Path -LiteralPath $PythonExe -PathType Leaf)) {
    throw "Plugin venv not found. Run Start-SptVisionTest.ps1 once first."
}

$env:PYTHONPATH = $ToolsRoot
& $PythonExe -m spt_vision_tester.main analyze --config (Resolve-Path -LiteralPath $ConfigPath).Path --run (Resolve-Path -LiteralPath $RunPath).Path
exit $LASTEXITCODE
