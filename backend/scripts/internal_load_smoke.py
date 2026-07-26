#!/usr/bin/env python3
"""Concurrent HTTP smoke/load check for a disposable CORVAX environment.

This is an internal readiness check, not a substitute for production-like
PostgreSQL stress, soak, or penetration testing.
"""
from __future__ import annotations
import argparse, concurrent.futures, json, math, statistics, time
from pathlib import Path
import httpx


def pct(values: list[float], q: float) -> float:
    if not values: return 0.0
    xs=sorted(values); pos=max(0, min(len(xs)-1, math.ceil(q*len(xs))-1)); return xs[pos]


def main() -> int:
    p=argparse.ArgumentParser()
    p.add_argument('--host', default='http://127.0.0.1:8765')
    p.add_argument('--email', default='admin@corvaxplatform.com')
    p.add_argument('--password', default='Corvax@123')
    p.add_argument('--requests', type=int, default=400)
    p.add_argument('--concurrency', type=int, default=20)
    p.add_argument('--evidence', default='docs/operations/evidence/internal_load_smoke.json')
    a=p.parse_args()
    with httpx.Client(base_url=a.host, timeout=20.0) as c:
        login=c.post('/api/v1/auth/login', json={'email':a.email,'password':a.password})
        login.raise_for_status(); token=login.json()['access_token']
    headers={'Authorization':f'Bearer {token}'}
    paths=['/health','/api/v1/modules/summary','/api/v1/finance-completion/dashboard?company_id=1','/api/v1/finance/trial-balance?company_id=1']
    started=time.perf_counter(); timings=[]; failures=[]; status_counts={}
    def hit(i:int):
        path=paths[i%len(paths)]; t=time.perf_counter()
        try:
            with httpx.Client(base_url=a.host, timeout=20.0, headers=headers) as c:
                r=c.get(path)
            ms=(time.perf_counter()-t)*1000
            return path,r.status_code,ms,None if r.status_code<500 else r.text[:200]
        except Exception as exc:
            return path,0,(time.perf_counter()-t)*1000,str(exc)
    with concurrent.futures.ThreadPoolExecutor(max_workers=a.concurrency) as ex:
        for path,status,ms,error in ex.map(hit, range(a.requests)):
            timings.append(ms); status_counts[str(status)]=status_counts.get(str(status),0)+1
            if error or status>=400: failures.append({'path':path,'status':status,'error':error})
    elapsed=time.perf_counter()-started
    evidence={
      'scope':'INTERNAL_DISPOSABLE_SQLITE_SMOKE','status':'PASSED' if not failures else 'FAILED',
      'requests':a.requests,'concurrency':a.concurrency,'duration_seconds':round(elapsed,3),
      'throughput_rps':round(a.requests/elapsed,2),'latency_ms':{
        'mean':round(statistics.mean(timings),2),'p50':round(pct(timings,.50),2),
        'p95':round(pct(timings,.95),2),'p99':round(pct(timings,.99),2),'max':round(max(timings),2)},
      'status_counts':status_counts,'failure_count':len(failures),'failure_samples':failures[:10],
      'limitations':['Not PostgreSQL','Not production infrastructure','Not a soak or stress test','No real customer data']}
    out=Path(a.evidence); out.parent.mkdir(parents=True,exist_ok=True); out.write_text(json.dumps(evidence,indent=2,ensure_ascii=False))
    print(json.dumps(evidence,indent=2,ensure_ascii=False))
    return 0 if evidence['status']=='PASSED' else 1
if __name__=='__main__': raise SystemExit(main())
