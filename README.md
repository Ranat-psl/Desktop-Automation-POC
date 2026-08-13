# Desktop Automation POC

Minimal Day-1 scaffold for a Windows desktop automation framework using Python, pytest, and pywinauto.

## Goals covered in this scaffold
- Modular framework structure
- pywinauto adapter boundary
- Playback engine for action lists
- Basic assertion helpers
- Recorder and AI integration extension points (stubs)
- pytest-based execution model
- Report folder and CI-friendly command pattern

## Quick start
1. Use the existing venv interpreter:
   - c:/ProjectRelated/Desktop-Automation-POC/.venv/Scripts/python.exe
2. Run tests:
   - c:/ProjectRelated/Desktop-Automation-POC/.venv/Scripts/python.exe -m pytest
3. Optional HTML report (requires pytest-html package if you choose to add it later):
   - c:/ProjectRelated/Desktop-Automation-POC/.venv/Scripts/python.exe -m pytest --html=reports/report.html --self-contained-html

## Current scope
- This is a POC scaffold, intentionally minimal.
- No real desktop app automation run is included in Day-1 tests.
- Recorder modules are placeholders for next iteration.
- Sensitive action approval gate is included as a policy boundary.
