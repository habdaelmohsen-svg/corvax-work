import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
APP = (ROOT / "frontend/src/App.tsx").read_text(encoding="utf-8")
SHELL = (ROOT / "frontend/src/dashboard/Shell.tsx").read_text(encoding="utf-8")
ASSISTANT = (
    ROOT / "frontend/src/components/ai-assistant/CorvaxAiAssistant.tsx"
).read_text(encoding="utf-8")
HOST = (
    ROOT / "frontend/src/components/ai-assistant/CorvaxAiAssistantHost.tsx"
).read_text(encoding="utf-8")
CSS = (
    ROOT / "frontend/src/styles/rc27_4_ai_assistant_h5.css"
).read_text(encoding="utf-8")

# One launcher only, mounted in the authenticated dashboard header directly
# beside the global search. The former App-level floating host must stay removed.
assert APP.count("CorvaxAiAssistantHost") == 0
assert SHELL.count("<CorvaxAiAssistantHost lang={lang}/>") == 1
search_position = SHELL.index('className="global-search"')
launcher_position = SHELL.index("<CorvaxAiAssistantHost lang={lang}/>")
actions_position = SHELL.index('className="header-actions"')
assert search_position < launcher_position < actions_position

# Keep the existing security contract: authenticated bearer request, company
# scope, explicit read-only context and the same read-only API endpoint.
assert "readOnly: true" in HOST
assert "Authorization: `Bearer ${token}`" in HOST
assert "'/api/v1/ai-assistant/messages'" in HOST
assert "company_id: companyId" in HOST
assert "branch_id: context.branchId ?? null" in HOST

# Keyboard/dialog accessibility and focus restoration are release invariants.
assert 'aria-haspopup="dialog"' in ASSISTANT
assert 'aria-controls="corvax-ai-panel"' in ASSISTANT
assert 'role="dialog"' in ASSISTANT
assert 'aria-modal="true"' in ASSISTANT
assert "event.key === 'Escape'" in ASSISTANT
assert "launcherRef.current?.focus()" in ASSISTANT

# The launcher participates in header layout; only the panel/backdrop may be
# viewport-fixed. Mobile keeps one compact launcher and no floating duplicate.
launcher_css = CSS.split(".corvax-ai-launcher {", 1)[1].split("}", 1)[0]
assert "position: fixed" not in launcher_css
assert "position: absolute" not in launcher_css
assert "position: relative" in launcher_css
assert ".corvax-ai {\n  display: contents;" in CSS
assert ".corvax-ai-backdrop {" in CSS and "position: fixed;" in CSS
assert ".corvax-ai-panel {" in CSS
assert "@media (max-width: 820px)" in CSS
assert ".corvax-ai-launcher__copy { display: none; }" in CSS
assert len(re.findall(r"(?m)^\s*\.corvax-ai-launcher \{", CSS)) == 2

print("CORVAX AI ASSISTANT HEADER LAUNCHER: PASS")
