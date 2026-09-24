# rica-attendance-backend

The RICA Attendance Tracking & Management System is a centralized web-based application designed to streamline biometric data processing, automate daily attendance verification, and eliminate manual spreadsheet tracking. Built with Python, Flask, and PostgreSQL, this backend server automates the ingestion of raw 20-column Excel logs exported from fingerprint devices across RICA offices, runs an automated anomaly detection engine to identify missing punches or status mismatches, and facilitates multi-tier verification for HR and management. Furthermore, the API powers automated generation of simplified daily reports for the Executive Director, calculates performance metrics (Attendance % and Punctuality %), and provides strict Role-Based Access Control (RBAC) across administrative, departmental, and unit-level scopes.


rica-attendance-backend/
├── schema.prisma             # Database schema, enums & relations
├── app/
│   ├── __init__.py           # App Factory (Registers Flask, Flasgger, Blueprints)
│   ├── config.py             # Environment configurations
│   ├── db.py                 # Prisma Client Singleton Instance
│   │
│   ├── api/                  # Blueprint Route Handlers (Controller Layer)
│   │   ├── auth.py           # User Authentication (Login, Refresh)
│   │   ├── imports.py        # 20-Column Excel Data Import
│   │   ├── verification.py   # Anomaly Checks & HR Verification
│   │   ├── reports.py        # 8-Column Director Report & Monthly KPIs
│   │   └── leaves.py         # Leave Applications & Management
│   │
│   ├── services/             # Core Business Logic (Service Layer)
│   │   ├── excel_parser.py   # Pandas Excel Parsing Engine
│   │   ├── anomaly_engine.py # Rule-based Anomaly Checker
│   │   └── kpi_engine.py     # Attendance & Punctuality Formula Calculations
│   │
│   └── utils/                # Utility Modules & Middleware
│       ├── decorators.py     # Role-Based Access Control (RBAC) Decorators
│       └── audit.py          # Action Audit Logging
│
├── .env                      # Database URL & Secret Keys
├── requirements.txt          # Dependencies
└── run.py                    # Entry Point File