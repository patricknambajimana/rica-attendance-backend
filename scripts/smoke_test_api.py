"""Hit every public API route against a live database via Flask's test client."""
from __future__ import annotations

import csv
import io
import sys
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import create_app

ADMIN_IDENTIFIER = "admin"
ADMIN_PASSWORD = "ChangeMe123!"
CSV_COLUMNS = [
    "No.",
    "Person ID",
    "Name",
    "Department",
    "Position",
    "Gender",
    "Date",
    "Week",
    "Timetable",
    "Check-in",
    "Check-out",
    "Work",
    "OT",
    "Attended",
    "Late",
    "Early",
    "Absent",
    "Leave",
    "Status",
    "Records",
]


def _csv_bytes(rows: list[dict]) -> bytes:
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=CSV_COLUMNS)
    writer.writeheader()
    writer.writerows(rows)
    return buf.getvalue().encode("utf-8")


class Checker:
    def __init__(self, client):
        self.client = client
        self.token = None
        self.failed: list[str] = []
        self.passed = 0

    def auth_headers(self, token=None):
        tok = token if token is not None else self.token
        return {"Authorization": f"Bearer {tok}"} if tok else {}

    def check(self, method: str, path: str, expected: int | tuple[int, ...], **kwargs):
        if "headers" not in kwargs and self.token:
            kwargs["headers"] = self.auth_headers()
        fn = getattr(self.client, method.lower())
        resp = fn(path, **kwargs)
        allowed = expected if isinstance(expected, tuple) else (expected,)
        ok = resp.status_code in allowed
        if ok:
            self.passed += 1
            print(f"  OK  {resp.status_code} {method:6} {path}")
        else:
            self.failed.append(f"{method} {path} -> {resp.status_code} (expected {allowed}): {resp.get_data(as_text=True)[:400]}")
            print(f"  FAIL {resp.status_code} {method:6} {path}  {resp.get_data(as_text=True)[:240]}")
        return resp


def main() -> int:
    app = create_app()
    app.config["TESTING"] = True
    app.config["DEBUG"] = True
    suffix = uuid4().hex[:8]
    dept_name = f"QA Dept {suffix}"
    person_id = f"P{suffix}"

    with app.test_client() as client:
        c = Checker(client)

        print("\n== Health ==")
        c.check("GET", "/health", 200)

        print("\n== Auth (unauthenticated) ==")
        c.check("POST", "/api/auth/login", 401, json={"identifier": "nobody", "password": "wrongpass1"})
        c.check("GET", "/api/auth/me", 401, headers={})
        login = c.check("POST", "/api/auth/login", 200, json={"identifier": ADMIN_IDENTIFIER, "password": ADMIN_PASSWORD})
        if login.status_code != 200:
            print("Cannot continue without admin login. Seed with: python scripts/seed_admin.py")
            return 1
        body = login.get_json()
        c.token = body["access_token"]
        refresh_token = body["refresh_token"]

        c.check("GET", "/api/auth/me", 200)
        forgot = c.check("POST", "/api/auth/forgot-password", 200, json={"identifier": ADMIN_IDENTIFIER})

        print("\n== Catalog ==")
        created_dept = c.check("POST", "/api/departments", 201, json={"name": dept_name, "office": "Kigali"})
        dept_id = created_dept.get_json()["id"] if created_dept.status_code == 201 else None
        c.check("GET", "/api/departments", 200)
        if dept_id:
            c.check("PATCH", f"/api/departments/{dept_id}", 200, json={"office": "Huye"})
        c.check("GET", "/api/employees", 200)
        shift = c.check(
            "POST",
            "/api/shifts",
            201,
            json={"name": f"Day {suffix}", "start_time": "08:00", "end_time": "17:00", "work_minutes": 480},
        )
        shift_id = shift.get_json()["id"] if shift.status_code == 201 else None
        c.check("GET", "/api/shifts", 200)
        if shift_id:
            c.check("PATCH", f"/api/shifts/{shift_id}", 200, json={"is_active": True})
        holiday = c.check(
            "POST",
            "/api/holidays",
            201,
            json={"date": "2026-07-04", "name": f"QA Holiday {suffix}", "is_recurring": False},
        )
        holiday_id = holiday.get_json()["id"] if holiday.status_code == 201 else None
        c.check("GET", "/api/holidays", 200)

        print("\n== Users ==")
        hod = c.check(
            "POST",
            "/api/users",
            201,
            json={
                "email": f"hod.{suffix}@rica.local",
                "username": f"hod{suffix}",
                "full_name": "QA Head",
                "temp_password": "TempPass1!",
                "role": "HOD",
                "department_id": dept_id,
            },
        )
        hod_id = hod.get_json()["id"] if hod.status_code == 201 else None
        users = c.check("GET", "/api/users", 200)
        if hod_id:
            c.check("GET", f"/api/users/{hod_id}", 200)
            c.check("PATCH", f"/api/users/{hod_id}", 200, json={"full_name": "QA Head Updated"})

        print("\n== Attendance ==")
        csv_data = _csv_bytes(
            [
                {
                    "No.": "1",
                    "Person ID": person_id,
                    "Name": "QA Employee",
                    "Department": dept_name,
                    "Position": "Officer",
                    "Gender": "F",
                    "Date": "2026-09-01",
                    "Week": "Mon",
                    "Timetable": "08:00-17:00",
                    "Check-in": "08:02",
                    "Check-out": "17:01",
                    "Work": "480",
                    "OT": "0",
                    "Attended": "479",
                    "Late": "2",
                    "Early": "0",
                    "Absent": "0",
                    "Leave": "0",
                    "Status": "W",
                    "Records": "2",
                },
                {
                    "No.": "2",
                    "Person ID": person_id,
                    "Name": "QA Employee",
                    "Department": dept_name,
                    "Position": "Officer",
                    "Gender": "F",
                    "Date": "2026-09-02",
                    "Week": "Tue",
                    "Timetable": "08:00-17:00",
                    "Check-in": "-",
                    "Check-out": "-",
                    "Work": "480",
                    "OT": "0",
                    "Attended": "0",
                    "Late": "0",
                    "Early": "0",
                    "Absent": "0",
                    "Leave": "0",
                    "Status": "A",
                    "Records": "0",
                },
            ]
        )
        upload = c.check(
            "POST",
            "/api/attendance/upload",
            201,
            data={"file": (io.BytesIO(csv_data), f"qa-{suffix}.csv")},
            content_type="multipart/form-data",
        )
        batch_id = upload.get_json().get("batchId") if upload.status_code == 201 else None
        c.check("GET", "/api/attendance/batches", 200)
        raw_list = c.check("GET", "/api/attendance/raw", 200)
        raw_id = None
        anomaly_id = None
        if raw_list.status_code == 200:
            rows = raw_list.get_json()
            if rows:
                raw_id = rows[0]["id"]
        if raw_id:
            c.check("GET", f"/api/attendance/raw/{raw_id}", 200)
            c.check(
                "PATCH",
                f"/api/attendance/raw/{raw_id}",
                200,
                json={"notes": "verified in smoke test", "promote_to_final": True, "resolve_anomalies": True},
            )
        c.check("GET", "/api/attendance/anomalies", 200)
        if batch_id:
            batch_anoms = c.check("GET", f"/api/attendance/anomalies?batch_id={batch_id}", 200)
            if batch_anoms.status_code == 200 and batch_anoms.get_json():
                anomaly_id = batch_anoms.get_json()[0]["id"]
            c.check("GET", f"/api/attendance/batches/{batch_id}/anomalies", 200)
        if anomaly_id:
            c.check("POST", f"/api/attendance/anomalies/{anomaly_id}/resolve", 200, json={"note": "ok"})
        c.check("GET", "/api/attendance/final", 200)

        print("\n== Leaves ==")
        employees = client.get("/api/employees", headers=c.auth_headers())
        employee_id = None
        if employees.status_code == 200:
            for emp in employees.get_json():
                if emp.get("person_id") == person_id:
                    employee_id = emp["id"]
                    break
        if employee_id:
            c.check(
                "POST",
                "/api/leaves",
                201,
                json={
                    "employee_id": employee_id,
                    "leave_type": "ANNUAL",
                    "start_date": "2026-09-03",
                    "end_date": "2026-09-03",
                    "reason": "smoke test",
                },
            )
        c.check("GET", "/api/leaves", 200)

        print("\n== Reports ==")
        c.check("GET", "/api/reports/daily?date=2026-09-01", 200)
        c.check("GET", "/api/reports/daily?date=2026-09-01&format=csv", 200)
        c.check("GET", "/api/reports/monthly?year=2026&month=9", 200)
        c.check("GET", "/api/reports/quarterly?year=2026&quarter=3", 200)
        c.check("GET", "/api/reports/yearly?year=2026", 200)
        c.check("GET", "/api/reports/kpis?year=2026&month=9", 200)

        print("\n== Audit ==")
        c.check("GET", "/api/audit-logs", 200)

        print("\n== Auth (refresh / logout) ==")
        refresh = c.check(
            "POST",
            "/api/auth/refresh",
            200,
            headers={"Authorization": f"Bearer {refresh_token}"},
        )
        if refresh.status_code == 200:
            c.token = refresh.get_json()["access_token"]
        c.check("POST", "/api/auth/logout", 200, json={"refresh_token": refresh_token})
        c.check("GET", "/api/auth/me", 401)

        if holiday_id:
            # Re-login to delete holiday created for this run.
            login2 = client.post("/api/auth/login", json={"identifier": ADMIN_IDENTIFIER, "password": ADMIN_PASSWORD})
            if login2.status_code == 200:
                c.token = login2.get_json()["access_token"]
                c.check("DELETE", f"/api/holidays/{holiday_id}", 200)

        print("\n== Summary ==")
        print(f"Passed: {c.passed}")
        print(f"Failed: {len(c.failed)}")
        for item in c.failed:
            print(f"  - {item}")
        return 1 if c.failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
