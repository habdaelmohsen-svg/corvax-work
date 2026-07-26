from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
for rel in ('frontend/src/dashboard/financePages.tsx','frontend/src/dashboard/operationsPages.tsx'):
    text=(ROOT/rel).read_text()
    assert "import.meta.env.DEV && import.meta.env.VITE_ENABLE_DEMO_ACTIONS === 'true'" in text
    for marker in ('Run reconciliation demo','Run lease demo','Add demo asset','Run accrual cycle demo','Run procurement demo','Run production demo'):
        if marker in text:
            start=max(0,text.index(marker)-300)
            assert 'DEMO_ACTIONS_ENABLED' in text[start:text.index(marker)+len(marker)+80]
print('verify_demo_surface_hardening: PASSED')
