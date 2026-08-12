"""Static acceptance guard for the R9.3 user-facing remediation."""
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def main() -> None:
    assistant = read("frontend/src/components/ai-assistant/CorvaxAiAssistant.tsx")
    assert 'role="dialog"' in assistant
    assert '<aside className="corvax-ai-panel"' not in assistant
    assert '<nav className="corvax-ai-tabs"' not in assistant

    shell = read("frontend/src/dashboard/Shell.tsx")
    assert "page-back-button" in shell and "corvaxFromHash" in shell
    assert "apiVersion" in shell and "R9.3" in shell

    journals = read("frontend/src/dashboard/manualJournalsPage.tsx")
    assert "printBusinessDocument" in journals and "printJournal(j)" in journals
    assert "openingMode" in journals and "cash_flow_kind='OPENING_BALANCE'" in journals
    assert "j.status==='PENDING_APPROVAL'" in journals

    reports = read("frontend/src/dashboard/reportsCenterPage.tsx")
    assert "printBusinessDocument" in reports
    assert "[companyId,ar]" in reports
    assert "beneficiary_name_en" in reports and "warehouse_name_en" in reports
    assert "Add company logo" in reports and "/logo" in reports

    printer = read("frontend/src/dashboard/printDocument.ts")
    assert "@page{size:A4" in printer and "company-logo" in printer
    assert 'dir="${dir}"' in printer

    assets = read("frontend/src/dashboard/financeRealPages.tsx")
    assert "initialize-opening-value" in assets
    assert "DRAFT_UNVALUED" in assets
    assert "Opening equity offset account" in assets
    assert "rebuild schedule" in assets

    navigation = read("frontend/src/dashboard/navigation.tsx")
    assert "key: 'openingBalances'" in navigation
    assert "مسح الحركات والقيم التجريبية" in navigation
    assert "key: 'transactions'" not in navigation
    routes = read("frontend/src/dashboard/routes.tsx")
    assert "transactions:<ManualJournalsPage" in routes

    print("verify_r93_usability: PASSED")


if __name__ == "__main__":
    main()
