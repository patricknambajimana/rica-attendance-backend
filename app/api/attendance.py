from flask import Blueprint, g, jsonify, request

from ..schemas.attendance import AttendanceBatchOut, AttendanceEditIn, ResolveAnomalyIn, UploadResultOut
from ..services import attendance_service
from ..utils.decorators import auth_required
from ..utils.errors import AppError

bp = Blueprint("attendance", __name__, url_prefix="/api/attendance")


@bp.post("/upload")
@auth_required("ADMIN")
def upload_attendance():
    """
    Upload a fingerprint device daily export (.xls/.xlsx/.csv). Admin only.
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


@bp.get("/batches")
@auth_required("ADMIN", "DIRECTOR")
def list_batches():
    """List attendance import batches, most recent first
    ---
    tags: [Attendance]
    security: [{Bearer: []}]
    responses:
      200: {description: List of import batches}
    """
    batches = attendance_service.list_batches()
    return jsonify([AttendanceBatchOut.model_validate(b).model_dump(mode="json") for b in batches])


@bp.get("/raw")
@auth_required("ADMIN", "HOD", "DIRECTOR")
def list_raw():
    """List raw imported attendance rows. HOD is limited to their department
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
      - in: query
        name: take
        type: integer
        default: 200
      - in: query
        name: skip
        type: integer
        default: 0
    responses:
      200: {description: List of raw attendance rows}
    """
    records = attendance_service.list_raw_records(
        g.user,
        batch_id=request.args.get("batch_id"),
        department_id=request.args.get("department_id"),
        office=request.args.get("office"),
        date_from=request.args.get("from"),
        date_to=request.args.get("to"),
        status=request.args.get("status"),
        unverified_only=request.args.get("unverified", "false").lower() == "true",
        take=int(request.args.get("take", 200)),
        skip=int(request.args.get("skip", 0)),
    )
    return jsonify([attendance_service.serialize_raw(r) for r in records])


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
    responses:
      200: {description: List of anomalies}
    """
    resolved_arg = request.args.get("resolved")
    resolved = None
    if resolved_arg is not None:
        resolved = resolved_arg.lower() == "true"
    else:
        resolved = False
    items = attendance_service.list_anomalies(
        g.user,
        batch_id=request.args.get("batch_id"),
        resolved=resolved,
    )
    return jsonify([attendance_service.serialize_anomaly(a) for a in items])


@bp.get("/batches/<batch_id>/anomalies")
@auth_required("ADMIN")
def list_batch_anomalies(batch_id: str):
    """List anomalies for one import batch
    ---
    tags: [Attendance]
    security: [{Bearer: []}]
    parameters:
      - in: path
        name: batch_id
        type: string
        required: true
      - in: query
        name: resolved
        type: boolean
        default: false
    responses:
      200: {description: List of anomalies for the batch}
    """
    show_resolved = request.args.get("resolved", "false").lower() == "true"
    items = attendance_service.list_anomalies(
        g.user, batch_id=batch_id, resolved=True if show_resolved else False
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
    records = attendance_service.list_final_records(
        g.user,
        department_id=request.args.get("department_id"),
        office=request.args.get("office"),
        date_from=request.args.get("from"),
        date_to=request.args.get("to"),
        take=request.args.get("take", 200),
        skip=request.args.get("skip", 0),
    )
    return jsonify([attendance_service.serialize_raw(r) for r in records])