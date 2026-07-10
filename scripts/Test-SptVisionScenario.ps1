[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$ScenarioPath
)

$ErrorActionPreference = "Stop"
$PluginRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$ToolsRoot = Join-Path $PluginRoot "tools"
$VenvPython = Join-Path $PluginRoot ".venv\Scripts\python.exe"

if (Test-Path -LiteralPath $VenvPython -PathType Leaf) {
    $PythonExe = $VenvPython
} else {
    $PythonCommand = Get-Command python -ErrorAction SilentlyContinue
    if (-not $PythonCommand) {
        $PythonCommand = Get-Command py -ErrorAction SilentlyContinue
    }
    if (-not $PythonCommand) {
        throw "Python was not found on PATH. Install Python 3.10+ or run Start-SptVisionTest.ps1 once."
    }
    $PythonExe = $PythonCommand.Source
}

$ResolvedScenarioPath = (Resolve-Path -LiteralPath $ScenarioPath).Path
$env:PYTHONPATH = $ToolsRoot

& $PythonExe -m spt_vision_tester.scenario_validator --scenario $ResolvedScenarioPath
exit $LASTEXITCODE
