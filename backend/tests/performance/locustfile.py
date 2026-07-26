"""CORVAX production-like load profile.

Run only against a disposable staging environment:
  locust -f backend/tests/performance/locustfile.py --host https://staging.example
Credentials come from CORVAX_LOAD_USER / CORVAX_LOAD_PASSWORD.
"""
import os
from locust import HttpUser, between, task


class CorvaxUser(HttpUser):
    wait_time = between(0.5, 2.0)

    def on_start(self):
        response = self.client.post("/api/v1/auth/login", json={
            "email": os.environ["CORVAX_LOAD_USER"],
            "password": os.environ["CORVAX_LOAD_PASSWORD"],
        }, name="auth/login")
        response.raise_for_status()
        self.headers = {"Authorization": f"Bearer {response.json()['access_token']}"}
        self.company_id = int(os.getenv("CORVAX_LOAD_COMPANY_ID", "1"))

    @task(6)
    def dashboard(self):
        self.client.get(f"/api/v1/finance-completion/dashboard?company_id={self.company_id}", headers=self.headers, name="enterprise/dashboard")

    @task(4)
    def trial_balance(self):
        self.client.get(f"/api/v1/finance/trial-balance?company_id={self.company_id}", headers=self.headers, name="finance/trial-balance")

    @task(2)
    def audit_chain(self):
        self.client.get(f"/api/v1/audit-logs?company_id={self.company_id}&limit=50", headers=self.headers, name="audit/list")

    @task(1)
    def module_summary(self):
        self.client.get("/api/v1/modules/summary", headers=self.headers, name="modules/summary")
