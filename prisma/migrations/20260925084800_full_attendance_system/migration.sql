-- AlterTable
ALTER TABLE "departments" ADD COLUMN IF NOT EXISTS "office" TEXT,
ADD COLUMN IF NOT EXISTS "updated_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP;

-- CreateEnum
DO $$ BEGIN
    CREATE TYPE "LeaveType" AS ENUM ('ANNUAL', 'SICK', 'BUSINESS_TRIP', 'MATERNITY', 'PATERNITY', 'UNPAID');
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;

-- AlterTable
ALTER TABLE "attendance_raw" ADD COLUMN IF NOT EXISTS "notes" TEXT,
ADD COLUMN IF NOT EXISTS "verified_at" TIMESTAMP(3),
ADD COLUMN IF NOT EXISTS "verified_by_id" TEXT,
ADD COLUMN IF NOT EXISTS "updated_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP;

-- CreateTable
CREATE TABLE IF NOT EXISTS "shifts" (
    "id" TEXT NOT NULL,
    "name" TEXT NOT NULL,
    "start_time" TEXT NOT NULL,
    "end_time" TEXT NOT NULL,
    "work_minutes" INTEGER NOT NULL,
    "is_active" BOOLEAN NOT NULL DEFAULT true,
    "created_by_id" TEXT,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "shifts_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE IF NOT EXISTS "attendance_final" (
    "id" TEXT NOT NULL,
    "attendance_raw_id" TEXT,
    "employee_id" TEXT NOT NULL,
    "row_no" INTEGER,
    "date" TIMESTAMP(3) NOT NULL,
    "week" TEXT,
    "timetable" TEXT,
    "check_in" TEXT,
    "check_out" TEXT,
    "work_min" INTEGER NOT NULL DEFAULT 0,
    "ot_min" INTEGER NOT NULL DEFAULT 0,
    "attended_min" INTEGER NOT NULL DEFAULT 0,
    "late_min" INTEGER NOT NULL DEFAULT 0,
    "early_min" INTEGER NOT NULL DEFAULT 0,
    "absent_min" INTEGER NOT NULL DEFAULT 0,
    "leave_min" INTEGER NOT NULL DEFAULT 0,
    "status" TEXT NOT NULL,
    "records" TEXT,
    "notes" TEXT,
    "verified_by_id" TEXT NOT NULL,
    "verified_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "attendance_final_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE IF NOT EXISTS "leaves" (
    "id" TEXT NOT NULL,
    "employee_id" TEXT NOT NULL,
    "leave_type" "LeaveType" NOT NULL,
    "start_date" TIMESTAMP(3) NOT NULL,
    "end_date" TIMESTAMP(3) NOT NULL,
    "reason" TEXT,
    "created_by_id" TEXT NOT NULL,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "leaves_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE IF NOT EXISTS "holidays" (
    "id" TEXT NOT NULL,
    "date" TIMESTAMP(3) NOT NULL,
    "name" TEXT NOT NULL,
    "is_recurring" BOOLEAN NOT NULL DEFAULT false,
    "created_by_id" TEXT,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "holidays_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE IF NOT EXISTS "audit_logs" (
    "id" TEXT NOT NULL,
    "user_id" TEXT,
    "action" TEXT NOT NULL,
    "entity_type" TEXT,
    "entity_id" TEXT,
    "delta" JSONB,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "audit_logs_pkey" PRIMARY KEY ("id")
);

CREATE UNIQUE INDEX IF NOT EXISTS "shifts_name_key" ON "shifts"("name");
CREATE UNIQUE INDEX IF NOT EXISTS "attendance_final_attendance_raw_id_key" ON "attendance_final"("attendance_raw_id");
CREATE UNIQUE INDEX IF NOT EXISTS "attendance_final_employee_id_date_key" ON "attendance_final"("employee_id", "date");
CREATE UNIQUE INDEX IF NOT EXISTS "holidays_date_key" ON "holidays"("date");
CREATE INDEX IF NOT EXISTS "employees_department_id_idx" ON "employees"("department_id");
CREATE INDEX IF NOT EXISTS "attendance_raw_date_idx" ON "attendance_raw"("date");
CREATE INDEX IF NOT EXISTS "attendance_raw_batch_id_idx" ON "attendance_raw"("batch_id");
CREATE INDEX IF NOT EXISTS "attendance_final_date_idx" ON "attendance_final"("date");
CREATE INDEX IF NOT EXISTS "anomalies_resolved_created_at_idx" ON "anomalies"("resolved", "created_at");
CREATE INDEX IF NOT EXISTS "leaves_employee_id_start_date_end_date_idx" ON "leaves"("employee_id", "start_date", "end_date");
CREATE INDEX IF NOT EXISTS "audit_logs_action_created_at_idx" ON "audit_logs"("action", "created_at");
CREATE INDEX IF NOT EXISTS "audit_logs_user_id_created_at_idx" ON "audit_logs"("user_id", "created_at");

DO $$ BEGIN
    ALTER TABLE "attendance_raw" ADD CONSTRAINT "attendance_raw_verified_by_id_fkey" FOREIGN KEY ("verified_by_id") REFERENCES "users"("id") ON DELETE SET NULL ON UPDATE CASCADE;
EXCEPTION WHEN duplicate_object THEN null; END $$;

DO $$ BEGIN
    ALTER TABLE "shifts" ADD CONSTRAINT "shifts_created_by_id_fkey" FOREIGN KEY ("created_by_id") REFERENCES "users"("id") ON DELETE SET NULL ON UPDATE CASCADE;
EXCEPTION WHEN duplicate_object THEN null; END $$;

DO $$ BEGIN
    ALTER TABLE "attendance_final" ADD CONSTRAINT "attendance_final_attendance_raw_id_fkey" FOREIGN KEY ("attendance_raw_id") REFERENCES "attendance_raw"("id") ON DELETE SET NULL ON UPDATE CASCADE;
EXCEPTION WHEN duplicate_object THEN null; END $$;

DO $$ BEGIN
    ALTER TABLE "attendance_final" ADD CONSTRAINT "attendance_final_employee_id_fkey" FOREIGN KEY ("employee_id") REFERENCES "employees"("id") ON DELETE RESTRICT ON UPDATE CASCADE;
EXCEPTION WHEN duplicate_object THEN null; END $$;

DO $$ BEGIN
    ALTER TABLE "attendance_final" ADD CONSTRAINT "attendance_final_verified_by_id_fkey" FOREIGN KEY ("verified_by_id") REFERENCES "users"("id") ON DELETE RESTRICT ON UPDATE CASCADE;
EXCEPTION WHEN duplicate_object THEN null; END $$;

DO $$ BEGIN
    ALTER TABLE "leaves" ADD CONSTRAINT "leaves_employee_id_fkey" FOREIGN KEY ("employee_id") REFERENCES "employees"("id") ON DELETE RESTRICT ON UPDATE CASCADE;
EXCEPTION WHEN duplicate_object THEN null; END $$;

DO $$ BEGIN
    ALTER TABLE "leaves" ADD CONSTRAINT "leaves_created_by_id_fkey" FOREIGN KEY ("created_by_id") REFERENCES "users"("id") ON DELETE RESTRICT ON UPDATE CASCADE;
EXCEPTION WHEN duplicate_object THEN null; END $$;

DO $$ BEGIN
    ALTER TABLE "holidays" ADD CONSTRAINT "holidays_created_by_id_fkey" FOREIGN KEY ("created_by_id") REFERENCES "users"("id") ON DELETE SET NULL ON UPDATE CASCADE;
EXCEPTION WHEN duplicate_object THEN null; END $$;

DO $$ BEGIN
    ALTER TABLE "audit_logs" ADD CONSTRAINT "audit_logs_user_id_fkey" FOREIGN KEY ("user_id") REFERENCES "users"("id") ON DELETE SET NULL ON UPDATE CASCADE;
EXCEPTION WHEN duplicate_object THEN null; END $$;
