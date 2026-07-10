# Multi-Monitor Mode

SPT Vision Tester can bind local SPT windows to one connected display. This keeps screenshots, percentage coordinates, and window placement away from the other monitors, but it does not create a separate Windows input desktop.

## What is isolated

- The configured SPT window is moved to and checked against one target monitor.
- A run stops when the window does not meet the configured monitor-coverage threshold.
- Percentage clicks are calculated inside the verified SPT window.
- Computer Use window capture can inspect the SPT window while it is occluded and without activating it.
- Python fallback screenshots are bounded to the SPT window rectangle and never intentionally capture the full desktop.

## What is not isolated

- Windows has one foreground window for the interactive desktop.
- Computer Use and the Python runner use injected system input.
- A click or key action activates SPT even when it is on another monitor.
- User typing during that short activation can reach SPT, and an SPT key can interrupt the user's active app.
- A second monitor does not provide a second keyboard focus or mouse pointer.

Use a VM, a separate interactive Windows session, or another machine when true simultaneous input is required.

## Enumerate displays

Initialize the plugin once with a server-only smoke test, then run:

```powershell
.\scripts\Get-SptVisionMonitors.ps1
```

The output orders displays as follows:

1. The Windows primary display.
2. Remaining connected displays in the order returned by Windows.

Record both `index` and `device_name`. Configuring both lets the plugin detect display reordering instead of silently selecting the wrong screen.

## Configuration

```json
{
  "TargetMonitorIndex": 2,
  "TargetMonitorDeviceName": "\\\\.\\DISPLAY1",
  "MoveTargetWindowToMonitor": true,
  "RequireTargetWindowOnMonitor": true,
  "TargetMonitorMinCoverage": 0.95,
  "TargetWindowPlacement": "preserve",
  "CooperativeDesktopMode": true,
  "UserIdleSecondsBeforeInput": 1.5,
  "MaxUserIdleWaitSeconds": 30.0,
  "RestoreUserFocusAfterInput": true,
  "RestoreCursorAfterInput": true
}
```

`TargetWindowPlacement` accepts:

- `preserve`: retain the current size when possible, clamp it to the target working area, and center it.
- `working-area`: fill the target area excluding the taskbar.
- `full-monitor`: fill the complete monitor bounds.

## Computer Use session

Start only the local SPT server and launcher and prepare the target window:

```powershell
.\scripts\Start-SptVisionTest.ps1 `
  -ConfigPath .\config\spt-vision-config.json `
  -ComputerUseSession -CollectLogs -AnalyzeLogs
```

The command returns the target PID, bounds, monitor identity, coverage, and an explicit `inputIsolation: false` marker. It does not click the launcher.

Codex should then:

1. Select the SPT launcher window returned by Computer Use app discovery.
2. Confirm its process path belongs to configured `SptRoot` and is not an official launcher.
3. Use window-level snapshots for passive observation.
4. Use only window-relative input after target-monitor placement succeeds.
5. Re-run `Move-SptWindowToTargetMonitor.ps1` when the launcher creates the game client window.
6. Stop when the user changes focus during an input burst or the monitor check fails.
7. Collect artifacts and stop only PIDs recorded by the plugin.

## Cooperative desktop mode

Before each injected action, the runner waits until Windows input has been quiet for `UserIdleSecondsBeforeInput`. Input produced by the preceding plugin action is ignored for this check. If user activity continues for `MaxUserIdleWaitSeconds`, the scenario stops.

After an action, the runner restores the prior foreground window and cursor only if they still match the plugin's expected state. If the user has already changed focus or moved the cursor, the plugin keeps the user's new state and stops before sending another action.

Cooperative mode reduces contention but cannot eliminate the small activation interval around each click or key. Avoid continuous automated movement while actively typing or using the mouse in another app.
