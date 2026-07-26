from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
UI = (ROOT / 'frontend/src/dashboard/ui.tsx').read_text(encoding='utf-8')
FINANCE = (ROOT / 'frontend/src/dashboard/financePages.tsx').read_text(encoding='utf-8')
CSS = (ROOT / 'frontend/src/styles/dashboard.css').read_text(encoding='utf-8')

assert 'vs last month' not in UI, 'KPI still forces English comparison text'
assert '<span>SAR</span>' not in UI, 'KPI still forces SAR on non-monetary values'
assert 'aria-label="More options"' not in UI, 'Panel still exposes an inert options button'
assert "JSON.stringify(c.details||{})" not in FINANCE, 'Close controls still expose raw JSON'
assert 'renderControlDetails(c.details,ar)' in FINANCE, 'Friendly close-control details missing'
assert "لا توجد بيانات متاحة" in UI and 'No data available' in UI, 'Bilingual empty state missing'
assert '.table-empty' in CSS, 'Empty-table visual state missing'
assert "ar?'مكتمل':'Done'" in UI, 'Checklist bilingual status missing'
print('CORVAX RC27.2 UI QUALITY: PASS')
