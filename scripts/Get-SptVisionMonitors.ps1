[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$PluginRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$ToolsRoot = Join-Path $PluginRoot "tools"
$PythonExe = Join-Path $PluginRoot ".venv\Scripts\python.exe"

if (-not (Test-Path -LiteralPath $PythonExe -PathType Leaf)) {
    throw "The plugin Python environment is not initialized. Run a server-only smoke test once, then retry."
}

$env:PYTHONPATH = $ToolsRoot
& $PythonExe -m spt_vision_tester.main monitors
exit $LASTEXITCODE
