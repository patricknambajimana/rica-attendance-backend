from datetime import datetime, timezone

from flask import Blueprint, g, jsonify, request, send_file

from ..schemas.attendance import AttendanceBatchOut, AttendanceEditIn, ResolveAnomalyIn, UploadResultOut
from ..services import attendance_service
from ..utils.decorators import auth_required
from ..utils.errors import AppError

bp = Blueprint("attendance", __name__, url_prefix="/api/attendance")


# ============================================================
# UPLOAD
# ============================================================

@bp.post("/upload")
@auth_required("ADMIN")
def upload_attendance():
    """Upload a fingerprint device daily export (.xls/.xlsx/.csv). Admin only.
    ---
    tags: [Attendance]
    consumes: [multipart/form-data]
    parameters:
      - in: formData
        name: file
        type: file
        required: true
    responses:
      201:
        description: Batch created with import counts
    """
    if "file" not in request.files:
        raise AppError("No file provided (expected multipart field 'file')", 400)

    file = request.files["file"]
    if not file.filename:
        raise AppError("No file selected", 400)

    result = attendance_service.import_attendance_file(file.filename, file.read(), g.user.id)
    return jsonify(UploadResultOut(**result).model_dump()), 201


# ============================================================
# BATCHES
# ============================================================

@bp.get("/batches")
@auth_required("ADMIN", "DIRECTOR")
def list_batches():
    """List attendance import batches, most recent first
    ---
    tags: [Attendance]
    security: [{Bearer: []}]
    parameters:
      - in: query
        name: take
        type: integer
        default: 50
    responses:
      200: {description: List of import batches}
    """
    take = int(request.args.get("take", 50))
    batches = attendance_service.list_batches(limit=take)
    return jsonify([AttendanceBatchOut.model_validate(b).model_dump(mode="json") for b in batches])


@bp.delete("/batches/<batch_id>")
@auth_required("ADMIN")
def delete_batch(batch_id: str):
    """Permanently delete an uploaded batch and everything that came from it. ADMIN only, no age/verified restriction.
    ---
    tags: [Attendance]
    security: [{Bearer: []}]
    parameters:
      - in: path
        name: batch_id
        type: string
        required: true
    responses:
      200:
        description: Batch and its raw/final/anomaly rows deleted, with counts. Not reversible.
      404: {description: Batch not found}
    """
    result = attendance_service.delete_batch(batch_id, g.user)
    return jsonify(result)


# ============================================================
# DAILY ATTENDANCE (TABLE-FRIENDLY, for the dashboard)
# ============================================================

@bp.get("/daily")
@auth_required("ADMIN", "HOD", "DIRECTOR")
def daily_attendance():
    """Get all employees' daily attendance as a flat table, ready to render on the dashboard.
    HOD is limited to their own department, same as every other attendance endpoint.
    ---
    tags: [Attendance]
    security: [{Bearer: []}]
    parameters:
      - in: query
        name: batch_id
        type: string
        description: Filter by a specific upload batch
      - in: query
        name: department_id
        type: string
        description: ADMIN/DIRECTOR only — HOD is always locked to their own department
      - in: query
        name: office
        type: string
      - in: query
        name: from
        type: string
        description: YYYY-MM-DD
      - in: query
        name: to
        type: string
        description: YYYY-MM-DD
      - in: query
        name: status
        type: string
      - in: query
        name: unverified
        type: boolean
        default: false
        description: If true, only rows HR has not yet verified/edited
      - in: query
        name: search
        type: string
        description: Search by name or Person ID
      - in: query
        name: all
        type: boolean
        default: false
        description: If true, ignore pagination and return every matching row (capped at 100,000)
      - in: query
        name: take
        type: integer
        default: 5000
      - in: query
        name: skip
        type: integer
        default: 0
    responses:
      200:
        description: Table-ready attendance data (columns, rows, summary, pagination)
    """
    fetch_all = request.args.get("all", "false").lower() == "true"
    if fetch_all:
        take, skip = 100_000, 0
    else:
        take = int(request.args.get("take", 5000))
        skip = int(request.args.get("skip", 0))

    result = attendance_service.get_daily_attendance_table(
        g.user,
        batch_id=request.args.get("batch_id"),
        department_id=request.args.get("department_id"),
        office=request.args.get("office"),
        date_from=request.args.get("from"),
        date_to=request.args.get("to"),
        status=request.args.get("status"),
        unverified_only=request.args.get("unverified", "false").lower() == "true",
        search=request.args.get("search"),
        take=take,
        skip=skip,
    )
    result["pagination"]["all"] = fetch_all
    return jsonify(result)


@bp.get("/raw/<raw_id>")
@auth_required("ADMIN", "HOD", "DIRECTOR")
def get_raw(raw_id: str):
    """Get a single raw attendance row by id
    ---
    tags: [Attendance]
    security: [{Bearer: []}]
    parameters:
      - in: path
        name: raw_id
        type: string
        required: true
    responses:
      200: {description: The raw attendance row}
      404: {description: Not found}
    """
    return jsonify(attendance_service.serialize_raw(attendance_service.get_raw_record(raw_id, g.user)))


@bp.patch("/raw/<raw_id>")
@auth_required("ADMIN")
def edit_raw(raw_id: str):
    """Correct punches/minutes/notes, resolve anomalies, and promote to attendance_final
    ---
    tags: [Attendance]
    security: [{Bearer: []}]
    parameters:
      - in: path
        name: raw_id
        type: string
        required: true
      - in: body
        name: body
        schema:
          type: object
          properties:
            check_in: {type: string}
            check_out: {type: string}
            work_min: {type: integer}
            ot_min: {type: integer}
            attended_min: {type: integer}
            late_min: {type: integer}
            early_min: {type: integer}
            absent_min: {type: integer}
            leave_min: {type: integer}
            status: {type: string}
            notes: {type: string}
            resolve_anomalies: {type: boolean, default: true}
            promote_to_final: {type: boolean, default: true}
    responses:
      200: {description: Updated attendance row}
    """
    body = AttendanceEditIn.model_validate(request.get_json(silent=True) or {})
    updated = attendance_service.edit_and_verify(raw_id, g.user, body)
    return jsonify(attendance_service.serialize_raw(updated))


# ============================================================
# ANOMALIES
# ============================================================

@bp.get("/anomalies")
@auth_required("ADMIN")
def list_anomalies():
    """HR review queue. Defaults to unresolved anomalies
    ---
    tags: [Attendance]
    security: [{Bearer: []}]
    parameters:
      - in: query
        name: batch_id
        type: string
      - in: query
        name: resolved
        type: boolean
        description: Defaults to false (unresolved only) if omitted
      - in: query
        name: take
        type: integer
        default: 200
    responses:
      200: {description: List of anomalies}
    """
    resolved_arg = request.args.get("resolved")
    resolved = resolved_arg.lower() == "true" if resolved_arg is not None else False

    items = attendance_service.list_anomalies(
        g.user,
        batch_id=request.args.get("batch_id"),
        resolved=resolved,
        take=int(request.args.get("take", 200)),
    )
    return jsonify([attendance_service.serialize_anomaly(a) for a in items])


@bp.post("/anomalies/<anomaly_id>/resolve")
@auth_required("ADMIN")
def resolve_anomaly(anomaly_id: str):
    """Mark an anomaly as resolved, with an optional note
    ---
    tags: [Attendance]
    security: [{Bearer: []}]
    parameters:
      - in: path
        name: anomaly_id
        type: string
        required: true
      - in: body
        name: body
        schema:
          type: object
          properties:
            note: {type: string}
    responses:
      200: {description: Updated anomaly}
    """
    body = ResolveAnomalyIn.model_validate(request.get_json(silent=True) or {})
    item = attendance_service.resolve_anomaly(anomaly_id, g.user, body.note)
    return jsonify(attendance_service.serialize_anomaly(item))


# ============================================================
# FINAL RECORDS (with pagination)
# ============================================================

@bp.get("/final")
@auth_required("ADMIN", "HOD", "DIRECTOR")
def list_final():
    """List finalized (verified) attendance records
    ---
    tags: [Attendance]
    security: [{Bearer: []}]
    parameters:
      - in: query
        name: department_id
        type: string
      - in: query
        name: office
        type: string
      - in: query
        name: from
        type: string
        description: YYYY-MM-DD
      - in: query
        name: to
        type: string
        description: YYYY-MM-DD
      - in: query
        name: take
        type: integer
        default: 200
      - in: query
        name: skip
        type: integer
        default: 0
    responses:
      200: {description: List of finalized attendance records}
    """
    result = attendance_service.list_final_records_paginated(
        g.user,
        department_id=request.args.get("department_id"),
        office=request.args.get("office"),
        date_from=request.args.get("from"),
        date_to=request.args.get("to"),
        take=int(request.args.get("take", 200)),
        skip=int(request.args.get("skip", 0)),
    )
    return jsonify(
        {
            "records": [attendance_service.serialize_raw(r) for r in result["records"]],
            "pagination": {
                "total": result["total"],
                "page": result["page"],
                "page_size": result["page_size"],
                "total_pages": result["total_pages"],
                "has_next": result["page"] < result["total_pages"],
                "has_prev": result["page"] > 1,
            },
        }
    )


# ============================================================
# EXPORT TO EXCEL
# ============================================================

@bp.get("/export")
@auth_required("ADMIN", "HOD", "DIRECTOR")
def export_attendance():
    """Export attendance records to Excel, filtered the same way as /raw. HOD limited to own department
    ---
    tags: [Attendance]
    security: [{Bearer: []}]
    parameters:
      - in: query
        name: batch_id
        type: string
      - in: query
        name: department_id
        type: string
      - in: query
        name: office
        type: string
      - in: query
        name: from
        type: string
      - in: query
        name: to
        type: string
      - in: query
        name: status
        type: string
    responses:
      200:
        description: Excel file with attendance records
    """
    output = attendance_service.export_to_excel(
        g.user,
        batch_id=request.args.get("batch_id"),
        department_id=request.args.get("department_id"),
        office=request.args.get("office"),
        date_from=request.args.get("from"),
        date_to=request.args.get("to"),
        status=request.args.get("status"),
    )
    filename = f"attendance_export_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.xlsx"
    return send_file(
        output,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        as_attachment=True,
        download_name=filename,
    )


# ============================================================
# DASHBOARD STATS
# ============================================================

@bp.get("/stats")
@auth_required("ADMIN", "HOD", "DIRECTOR")
def attendance_stats():
    """Get attendance statistics for dashboard cards. HOD limited to own department
    ---
    tags: [Attendance]
    security: [{Bearer: []}]
    responses:
      200: {description: Statistics for dashboard cards}
    """
    stats = attendance_service.get_attendance_stats(g.user)
    return jsonify(stats)