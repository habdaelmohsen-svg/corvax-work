"""Focused acceptance guard for CORVAX R9.4 reporting and assistant fixes."""
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def main() -> None:
    assistant = read("frontend/src/components/ai-assistant/CorvaxAiAssistant.tsx")
    assert "createPortal" in assistant and "document.body" in assistant
    assert "backdrop-filter" in assistant and "containing block" in assistant

    engine = read("frontend/src/dashboard/financialStatementEngine.ts")
    assert "fetchComparativeStatements" in engine
    assert "previous:" in engine and "priorYear:" in engine
    assert "variancePercent" in engine and "Same period last year" in read(
        "frontend/src/dashboard/comparativeStatementTable.tsx"
    )
    assert "toISOString" not in engine
    assert "getFullYear" in engine and "currentYearStart" in engine

    reports = read("frontend/src/dashboard/reportsCenterPage.tsx")
    finance = read("frontend/src/dashboard/financePages.tsx")
    for source in (reports, finance):
        assert "fetchComparativeStatements" in source
        assert "ComparativeStatementTable" in source
    assert "Current quarter" in reports and "Custom period" in reports
    assert "rowKinds" in reports and "Add company logo" in reports

    printer = read("frontend/src/dashboard/printDocument.ts")
    assert "@page{size:A4 ${orientation};margin:0}" in printer
    assert "data-kind" in printer and "print-page-footer" in printer
    assert "Prepared by" in printer and "company-logo" in printer

    shell = read("frontend/src/dashboard/Shell.tsx")
    config = read("backend/app/core/config.py")
    assert "R9.4" in shell
    assert "rc27.4-r9.4" in config
    assert "seed_demo_data: bool = False" in config
    assert "SEED_DEMO_DATA=false" in read("backend/.env.example")
    assert 'SEED_DEMO_DATA: "false"' in read("docker-compose.yml")

    reset_page = read("frontend/src/dashboard/dataResetPage.tsx")
    assert "uat-reset-preview-result" in reset_page
    assert "dryRunResult" in reset_page
    assert "rows_that_would_be_deleted" in reset_page
    assert "لم يتم حذف أي بيانات حتى الآن" in reset_page
    assert "scrollIntoView" in reset_page

    print("verify_r94_reporting_assistant: PASSED")


if __name__ == "__main__":
    main()
