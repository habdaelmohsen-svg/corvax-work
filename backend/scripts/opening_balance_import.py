#!/usr/bin/env python3
"""Validated opening-balance migration tool.

CSV columns: company_code,account_code,debit,credit,branch_code,cost_center_code,description
Dry-run is the default. `--apply` posts one balanced journal per company through the
same system posting service and writes immutable source/report hashes.
"""
from __future__ import annotations
import argparse, csv, hashlib, json, sys
from collections import defaultdict
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path

BACKEND=Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
from sqlalchemy import select
from app.db import SessionLocal
from app.models import Account, Branch, Company, CostCenter, User
from app.services.posting import create_posted_journal

Q=Decimal("0.01")


def decimal(value: str, row: int, field: str) -> Decimal:
    try: result=Decimal((value or "0").strip()).quantize(Q)
    except InvalidOperation as exc: raise ValueError(f"row {row}: invalid {field}") from exc
    if result < 0: raise ValueError(f"row {row}: {field} cannot be negative")
    return result


def load(path: Path) -> list[dict]:
    rows=[]
    with path.open(newline='', encoding='utf-8-sig') as handle:
        reader=csv.DictReader(handle)
        required={"company_code","account_code","debit","credit"}
        if not required.issubset(set(reader.fieldnames or [])):
            raise ValueError(f"Missing columns: {sorted(required-set(reader.fieldnames or []))}")
        for number, raw in enumerate(reader, start=2):
            debit=decimal(raw.get("debit",""), number, "debit"); credit=decimal(raw.get("credit",""), number, "credit")
            if (debit > 0) == (credit > 0): raise ValueError(f"row {number}: exactly one of debit/credit must be positive")
            rows.append({"row":number,"company_code":raw["company_code"].strip(),"account_code":raw["account_code"].strip(),
                         "debit":debit,"credit":credit,"branch_code":(raw.get("branch_code") or "").strip(),
                         "cost_center_code":(raw.get("cost_center_code") or "").strip(),
                         "description":(raw.get("description") or "Opening balance").strip()})
    if not rows: raise ValueError("CSV contains no data rows")
    return rows


def main() -> None:
    ap=argparse.ArgumentParser(); ap.add_argument("csv", type=Path); ap.add_argument("--posting-date", type=date.fromisoformat, required=True)
    ap.add_argument("--apply", action="store_true"); ap.add_argument("--user-id", type=int); ap.add_argument("--report", type=Path, default=Path("docs/operations/evidence/opening_balance_import.json"))
    args=ap.parse_args(); source_hash=hashlib.sha256(args.csv.read_bytes()).hexdigest(); rows=load(args.csv)
    totals=defaultdict(lambda:{"debit":Decimal("0"),"credit":Decimal("0")})
    for row in rows: totals[row["company_code"]]["debit"]+=row["debit"]; totals[row["company_code"]]["credit"]+=row["credit"]
    errors=[f"{code}: debit {v['debit']} != credit {v['credit']}" for code,v in totals.items() if v["debit"] != v["credit"] or v["debit"] <= 0]
    journal_numbers=[]
    with SessionLocal() as db:
        user=db.get(User,args.user_id) if args.user_id else None
        if args.apply and not user: errors.append("--user-id must identify an existing user when --apply is used")
        resolved=[]
        for row in rows:
            company=db.scalar(select(Company).where(Company.code==row["company_code"],Company.active.is_(True)))
            if not company: errors.append(f"row {row['row']}: company not found"); continue
            account=db.scalar(select(Account).where(Account.company_id==company.id,Account.code==row["account_code"],Account.posting_allowed.is_(True)))
            if not account: errors.append(f"row {row['row']}: posting account not found"); continue
            branch=None; cc=None
            if row["branch_code"]:
                branch=db.scalar(select(Branch).where(Branch.company_id==company.id,Branch.code==row["branch_code"],Branch.active.is_(True)))
                if not branch: errors.append(f"row {row['row']}: branch not found")
            if row["cost_center_code"]:
                cc=db.scalar(select(CostCenter).where(CostCenter.company_id==company.id,CostCenter.code==row["cost_center_code"],CostCenter.active.is_(True)))
                if not cc: errors.append(f"row {row['row']}: cost center not found")
            resolved.append((company,row,account,branch,cc))
        if errors:
            db.rollback()
        elif args.apply:
            groups=defaultdict(list)
            for company,row,account,branch,cc in resolved:
                groups[company.id].append({"account_id":account.id,"debit":row["debit"],"credit":row["credit"],
                                           "branch_id":branch.id if branch else None,"cost_center_id":cc.id if cc else None,
                                           "description":row["description"]})
            for company_id,lines in groups.items():
                entry=create_posted_journal(db,company_id=company_id,user_id=user.id,posting_date=args.posting_date,
                                            reference=f"MIG-OPEN-{source_hash[:12]}",description="Validated opening balance migration",lines=lines)
                journal_numbers.append(entry.number)
            db.commit()
    report={"status":"FAILED" if errors else ("APPLIED" if args.apply else "VALIDATED"),"source_sha256":source_hash,
            "posting_date":str(args.posting_date),"row_count":len(rows),"companies":{k:{x:str(y) for x,y in v.items()} for k,v in totals.items()},
            "journals":journal_numbers,"errors":errors}
    args.report.parent.mkdir(parents=True,exist_ok=True); args.report.write_text(json.dumps(report,indent=2,ensure_ascii=False))
    print(json.dumps(report,indent=2,ensure_ascii=False))
    if errors: raise SystemExit(2)

if __name__ == "__main__": main()
