from flask import Blueprint, Response, g, jsonify, request

from ..services import report_service
from ..utils.decorators import auth_required
from ..utils.errors import AppError

bp = Blueprint("reports", __name__, url_prefix="/api/reports")


def _wants_csv() -> bool:
    return request.args.get("format", "json").lower() == "csv"


def _csv(filename: str, body: str):
    return Response(
        body,
        mimetype="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@bp.get("/daily")
@auth_required("ADMIN", "HOD", "DIRECTOR")
def daily_report():
    """Director daily report (8 columns from spec 3.2)
    ---
    tags: [Reports]
    security: [{Bearer: []}]
    parameters:
      - in: query
        name: date
        type: string
        required: true
        description: YYYY-MM-DD
      - in: query
        name: department_id
        type: string
      - in: query
        name: office
        type: string
      - in: query
        name: format
        type: string
        enum: [json, csv]
        default: json
    responses:
      200: {description: Daily report, JSON or CSV download}
      400: {description: Missing required 'date' parameter}
    """
    report_date = request.args.get("date")
    if not report_date:
        raise AppError("Query parameter 'date' (YYYY-MM-DD) is required", 400)
    payload = report_service.daily_report(
        g.user,
        report_date,
        request.args.get("department_id"),
        request.args.get("office"),
    )
    if _wants_csv():
        csv_body = report_service.records_to_csv(payload["rows"], report_service.DIRECTOR_COLUMNS)
        return _csv(f"daily-report-{report_date}.csv", csv_body)
    return jsonify(payload)


@bp.get("/monthly")
@auth_required("ADMIN", "HOD", "DIRECTOR")
def monthly_report():
    """Attendance report for a calendar month
    ---
    tags: [Reports]
    security: [{Bearer: []}]
    parameters:
      - in: query
        name: year
        type: integer
        required: true
      - in: query
        name: month
        type: integer
        required: true
        description: 1-12
      - in: query
        name: department_id
        type: string
      - in: query
        name: office
        type: string
      - in: query
        name: format
        type: string
        enum: [json, csv]
        default: json
    responses:
      200: {description: Monthly report, JSON or CSV download}
      400: {description: Missing/invalid year or month}
    """
    year = int(request.args.get("year") or 0)
    month = int(request.args.get("month") or 0)
    if not (year and 1 <= month <= 12):
        raise AppError("Query parameters year and month (1-12) are required", 400)
    date_from, date_to = report_service.month_bounds(year, month)
    payload = report_service.period_report(
        g.user, date_from, date_to, request.args.get("department_id"), request.args.get("office")
    )
    if _wants_csv():
        cols = list(payload["rows"][0].keys()) if payload["rows"] else ["date", "name", "status"]
        return _csv(
            f"monthly-report-{year}-{month:02d}.csv",
            report_service.records_to_csv(payload["rows"], cols),
        )
    return jsonify(payload)


@bp.get("/quarterly")
@auth_required("ADMIN", "HOD", "DIRECTOR")
def quarterly_report():
    """Attendance report for a calendar quarter
    ---
    tags: [Reports]
    security: [{Bearer: []}]
    parameters:
      - in: query
        name: year
        type: integer
        required: true
      - in: query
        name: quarter
        type: integer
        required: true
        description: 1-4
      - in: query
        name: department_id
        type: string
      - in: query
        name: office
        type: string
    responses:
      200: {description: Quarterly report}
    """
    year = int(request.args.get("year") or 0)
    quarter = int(request.args.get("quarter") or 0)
    date_from, date_to = report_service.quarter_bounds(year, quarter)
    return jsonify(
        report_service.period_report(
            g.user, date_from, date_to, request.args.get("department_id"), request.args.get("office")
        )
    )


@bp.get("/yearly")
@auth_required("ADMIN", "HOD", "DIRECTOR")
def yearly_report():
    """Attendance report for a calendar year
    ---
    tags: [Reports]
    security: [{Bearer: []}]
    parameters:
      - in: query
        name: year
        type: integer
        required: true
      - in: query
        name: department_id
        type: string
      - in: query
        name: office
        type: string
    responses:
      200: {description: Yearly report}
      400: {description: Missing/invalid year}
    """
    year = int(request.args.get("year") or 0)
    if year < 2000:
        raise AppError("Query parameter year is required", 400)
    date_from, date_to = report_service.year_bounds(year)
    return jsonify(
        report_service.period_report(
            g.user, date_from, date_to, request.args.get("department_id"), request.args.get("office")
        )
    )


@bp.get("/kpis")
@auth_required("ADMIN", "HOD", "DIRECTOR")
def kpis():
    """Attendance % and punctuality % with spec 5.4 rating bands
    ---
    tags: [Reports]
    security: [{Bearer: []}]
    parameters:
      - in: query
        name: from
        type: string
        description: YYYY-MM-DD (used with 'to')
      - in: query
        name: to
        type: string
        description: YYYY-MM-DD (used with 'from')
      - in: query
        name: year
        type: integer
      - in: query
        name: month
        type: integer
        description: 1-12, used with 'year'
      - in: query
        name: quarter
        type: integer
        description: 1-4, used with 'year'
      - in: query
        name: department_id
        type: string
      - in: query
        name: office
        type: string
    responses:
      200: {description: Attendance and punctuality KPIs}
      400: {description: No valid date range could be resolved from the parameters}
    """
    date_from = request.args.get("from")
    date_to = request.args.get("to")
    year = request.args.get("year")
    month = request.args.get("month")
    quarter = request.args.get("quarter")

    if year and month:
        date_from, date_to = report_service.month_bounds(int(year), int(month))
    elif year and quarter:
        date_from, date_to = report_service.quarter_bounds(int(year), int(quarter))
    elif year and not date_from:
        date_from, date_to = report_service.year_bounds(int(year))

    if not date_from or not date_to:
        raise AppError("Provide from & to (YYYY-MM-DD), or year[+month|quarter]", 400)

    return jsonify(
        report_service.performance_kpis(
            g.user, date_from, date_to, request.args.get("department_id"), request.args.get("office")
        )
    )