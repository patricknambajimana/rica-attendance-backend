from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class UploadResultOut(BaseModel):
    batchId: str
    filename: str
    rowCount: int
    insertedCount: int
    duplicateCount: int
    anomalyCount: int


class AttendanceBatchOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    filename: str
    uploadedById: str
    rowCount: int
    insertedCount: int
    duplicateCount: int
    anomalyCount: int
    createdAt: datetime


class AnomalyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    attendanceRawId: str
    batchId: str
    type: str
    message: str
    resolved: bool
    resolvedById: Optional[str] = None
    resolvedAt: Optional[datetime] = None
    createdAt: datetime


class AttendanceEditIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    check_in: Optional[str] = None
    check_out: Optional[str] = None
    work_min: Optional[int] = None
    ot_min: Optional[int] = None
    attended_min: Optional[int] = None
    late_min: Optional[int] = None
    early_min: Optional[int] = None
    absent_min: Optional[int] = None
    leave_min: Optional[int] = None
    status: Optional[str] = Field(default=None, max_length=20)
    notes: Optional[str] = Field(default=None, max_length=2000)
    resolve_anomalies: bool = True
    promote_to_final: bool = True


class ResolveAnomalyIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    note: Optional[str] = Field(default=None, max_length=2000)


class LeaveCreateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    employee_id: str
    leave_type: Literal["ANNUAL", "SICK", "BUSINESS_TRIP", "MATERNITY", "PATERNITY", "UNPAID"]
    start_date: str = Field(description="YYYY-MM-DD")
    end_date: str = Field(description="YYYY-MM-DD")
    reason: Optional[str] = Field(default=None, max_length=2000)


class DepartmentCreateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=120)
    office: Optional[str] = Field(default=None, max_length=120)


class DepartmentUpdateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Optional[str] = Field(default=None, min_length=1, max_length=120)
    office: Optional[str] = Field(default=None, max_length=120)


class ShiftCreateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=80)
    start_time: str = Field(min_length=4, max_length=8)
    end_time: str = Field(min_length=4, max_length=8)
    work_minutes: int = Field(gt=0, le=24 * 60)


class ShiftUpdateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Optional[str] = Field(default=None, min_length=1, max_length=80)
    start_time: Optional[str] = Field(default=None, min_length=4, max_length=8)
    end_time: Optional[str] = Field(default=None, min_length=4, max_length=8)
    work_minutes: Optional[int] = Field(default=None, gt=0, le=24 * 60)
    is_active: Optional[bool] = None


class HolidayCreateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    date: str = Field(description="YYYY-MM-DD")
    name: str = Field(min_length=1, max_length=120)
    is_recurring: bool = False
