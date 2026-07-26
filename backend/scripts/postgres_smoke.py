#!/usr/bin/env python3
"""Non-destructive PostgreSQL readiness smoke with JSON evidence."""
from __future__ import annotations
import argparse, json, os, time
from pathlib import Path
from sqlalchemy import create_engine, text

EXPECTED_HEAD='e19400000001'

def main()->int:
 p=argparse.ArgumentParser(); p.add_argument('--url',default=os.getenv('DATABASE_URL')); p.add_argument('--evidence',default='docs/operations/evidence/postgres_smoke.json'); a=p.parse_args()
 if not a.url or not a.url.startswith(('postgresql://','postgres://','postgresql+psycopg://')): raise SystemExit('A PostgreSQL DATABASE_URL is required')
 url=a.url.replace('postgres://','postgresql+psycopg://',1) if a.url.startswith('postgres://') else a.url.replace('postgresql://','postgresql+psycopg://',1)
 started=time.perf_counter(); checks={}; status='PASSED'
 try:
  engine=create_engine(url,pool_pre_ping=True)
  with engine.begin() as c:
   checks['server_version']=c.scalar(text('show server_version'))
   checks['database']=c.scalar(text('select current_database()'))
   checks['migration_head']=c.scalar(text('select version_num from alembic_version'))
   checks['public_table_count']=c.scalar(text("select count(*) from information_schema.tables where table_schema='public'"))
   checks['invalid_indexes']=c.scalar(text("select count(*) from pg_index where not indisvalid"))
   checks['ungranted_fk_constraints']=c.scalar(text("select count(*) from pg_constraint where contype='f' and not convalidated"))
   c.execute(text('create temporary table corvax_smoke(id integer primary key, value text) on commit drop'))
   c.execute(text("insert into corvax_smoke values (1,'ok')")); checks['transaction_roundtrip']=c.scalar(text('select value from corvax_smoke where id=1'))
   checks['advisory_lock']=bool(c.scalar(text('select pg_try_advisory_xact_lock(18700000001)')))
  if checks['migration_head']!=EXPECTED_HEAD or checks['invalid_indexes'] or checks['ungranted_fk_constraints'] or checks['transaction_roundtrip']!='ok': status='FAILED'
 except Exception as exc:
  status='FAILED'; checks['error']=str(exc)
 evidence={'scope':'POSTGRESQL_STAGING_SMOKE','status':status,'expected_migration_head':EXPECTED_HEAD,'checks':checks,'duration_seconds':round(time.perf_counter()-started,3)}
 out=Path(a.evidence); out.parent.mkdir(parents=True,exist_ok=True); out.write_text(json.dumps(evidence,indent=2,ensure_ascii=False)); print(json.dumps(evidence,indent=2,ensure_ascii=False)); return 0 if status=='PASSED' else 1
if __name__=='__main__': raise SystemExit(main())
