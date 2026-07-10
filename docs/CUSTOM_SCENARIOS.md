# Custom Scenarios

Custom scenarios are versioned JSON documents that describe a bounded sequence of local SPT UI actions. The plugin validates the whole document before it starts the SPT server, launcher, or client.

## Safety model

- Only the documented action allowlist is executable.
- Scenario JSON cannot run shell commands, scripts, executables, arbitrary paths, text entry, or clipboard operations.
- Scenario limits can only tighten `ScenarioMaxSeconds` and `MaxInputActions` from local config.
- Input still requires `AllowComputerUse=true`, `AllowKeyboardMouseInput=true`, and the `-UseComputer` switch.
- Client launch still requires `AllowClientLaunch=true` and the `-LaunchClient` switch.
- Raid navigation additionally requires `AllowRaidAutomation=true` in config and `allowRaidAutomation=true` in the scenario.
- The foreground window must belong to an allowed process under the configured local `SptRoot`.
- Unknown actions, fields, keys, conditions, or out-of-range values stop validation.

Never use a scenario with official Escape from Tarkov, Battlestate Launcher, an online session, account/login/payment screens, or unrelated desktop apps.

## Version 1 format

Start from `examples/custom-scenario.example.json`:

```json
{
  "$schema": "../config/scenarios/spt-vision-scenario.schema.json",
  "schemaVersion": 1,
  "name": "custom-launcher-focus-check",
  "description": "Launch the local SPT launcher, exercise bounded keyboard navigation, and collect evidence.",
  "requiresComputerUse": true,
  "requiresKeyboardMouseInput": true,
  "requiresClientLaunch": true,
  "allowRaidAutomation": false,
  "maxSeconds": 120,
  "maxInputActions": 4,
  "steps": [
    { "action": "wait", "condition": "wait_for_window", "timeoutSeconds": 90 },
    { "action": "focus_target_window" },
    { "action": "screenshot", "label": "before" },
    { "action": "press", "key": "tab" },
    { "action": "wait", "seconds": 1 },
    { "action": "press", "key": "tab" },
    { "action": "screenshot", "label": "after" },
    { "action": "collect_logs" },
    { "action": "analyze_logs" }
  ]
}
```

`maxInputActions` counts each key in `press_sequence` separately. It also counts focus, click, hold, and mouse-movement actions. Screenshots, waits, log collection, and analysis do not consume the input budget.

## Action allowlist

| Action | Required fields | Purpose |
| --- | --- | --- |
| `focus_target_window` | none | Focus and verify an allowed local SPT window. |
| `screenshot` | optional `label` | Capture target-window evidence. |
| `press` | `key` | Press one allowlisted key. |
| `press_sequence` | `keys` | Press 1-20 allowlisted keys with optional `intervalSeconds`. |
| `hold` | `key`, `seconds` | Hold an allowlisted key for at most 10 seconds. |
| `move_mouse_relative` | integer `x`, `y` | Move at most 1000 pixels per axis. |
| `click_center` | none | Click the current pointer position after foreground verification. |
| `click_window_percent` | `xPercent`, `yPercent` | Click a normalized target-window coordinate from 0 to 1. |
| `double_click_window_percent` | `xPercent`, `yPercent` | Double-click a normalized target-window coordinate. |
| `wait` | `seconds`, or `condition` fields | Wait while continuing denied-process checks. |
| `collect_logs` | none | Copy configured recent logs into the current run. |
| `analyze_logs` | none | Generate `analysis.md` and `analysis.json`. |

Wait conditions are `wait_for_window` with `timeoutSeconds`, plus `wait_for_stable_image`, `wait_for_log_quiet`, and `wait_for_seconds` with `seconds`. Each wait is capped at 300 seconds.

## Validate without launching SPT

```powershell
.\scripts\Test-SptVisionScenario.ps1 -ScenarioPath .\examples\custom-scenario.example.json
```

The command returns JSON containing requirements, action counts, estimated input actions, and validation errors. It does not start any process.

## Run a custom scenario

Run the included launcher example:

```powershell
.\scripts\Start-SptVisionTest.ps1 `
  -ConfigPath .\config\spt-vision-config.json `
  -CustomScenarioPath .\examples\custom-scenario.example.json `
  -LaunchClient -UseComputer -CollectLogs -AnalyzeLogs
```

If the scenario declares `requiresClientLaunch=true`, also pass `-LaunchClient`. The local config must explicitly allow every requested capability.

## Build a raid scenario

Copy one of the tested built-ins instead of starting from a blank file:

- Normal local offline raid: `config/scenarios/auto-offline-raid-smoke-test.json`
- Local offline raid with AI amount set to none and bosses disabled: `config/scenarios/auto-offline-raid-no-ai-smoke-test.json`

Keep `allowRaidAutomation=true` only for a reviewed local offline route. Percentage coordinates depend on resolution, UI scale, language, game version, and mods. Capture screenshots around every calibrated click and test a server-only run first.

## Sharing checklist

1. Remove absolute paths, usernames, profile identifiers, tokens, and screenshots containing private data.
2. Validate the scenario with `Test-SptVisionScenario.ps1`.
3. Review every click and key against the intended screen.
4. Keep duration and input budgets as small as practical.
5. State the SPT version, language, resolution, UI scale, map, and expected start screen.
6. Tell users whether they must manually enter a raid or enable automated raid navigation.

Treat third-party scenario files as untrusted instructions. Validation limits what they can express, but it cannot prove that a valid click coordinate is appropriate for the UI currently visible.
