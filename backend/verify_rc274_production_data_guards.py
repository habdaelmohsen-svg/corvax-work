from pathlib import Path

src = Path(__file__).resolve().parents[1] / 'frontend' / 'src' / 'dashboard' / 'operationsPages.tsx'
text = src.read_text(encoding='utf-8')

for forbidden in ["2026-07-12", "2026-07-13", "2026-07-20", "2026-07-30", "2026-07-01", "2026-07-31", "2026-08-11", "2027-07-12", "2027-01-12"]:
    assert forbidden not in text, f'hard-coded operational date remains: {forbidden}'

assert "DEMO_ACTIONS_ENABLED&&<div><button disabled={busy} onClick={()=>run('sale')}" in text
assert "DEMO_ACTIONS_ENABLED&&<div><button disabled={busy} onClick={()=>run('purchase')}" in text
assert 'function currentMonthBounds()' in text
assert 'order_date:isoDate()' in text
assert 'due_date:addDaysIso(30)' in text
print('RC27.4 production data guards: PASS')
