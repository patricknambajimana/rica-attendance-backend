-- CreateEnum
CREATE TYPE "AnomalyType" AS ENUM ('MISSING_PUNCH', 'STATUS_MISMATCH', 'NEGATIVE_VALUE', 'ABSENT_INCONSISTENCY');

-- CreateTable
CREATE TABLE "password_reset_tokens" (
    "id" TEXT NOT NULL,
    "user_id" TEXT NOT NULL,
    "token_hash" TEXT NOT NULL,
    "expires_at" TIMESTAMP(3) NOT NULL,
    "used_at" TIMESTAMP(3),
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "password_reset_tokens_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "employees" (
    "id" TEXT NOT NULL,
    "person_id" TEXT NOT NULL,
    "full_name" TEXT NOT NULL,
    "department_id" TEXT,
    "position" TEXT,
    "gender" TEXT,
    "is_active" BOOLEAN NOT NULL DEFAULT true,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "employees_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "attendance_batches" (
    "id" TEXT NOT NULL,
    "filename" TEXT NOT NULL,
    "uploaded_by_id" TEXT NOT NULL,
    "row_count" INTEGER NOT NULL DEFAULT 0,
    "inserted_count" INTEGER NOT NULL DEFAULT 0,
    "duplicate_count" INTEGER NOT NULL DEFAULT 0,
    "anomaly_count" INTEGER NOT NULL DEFAULT 0,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "attendance_batches_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "attendance_raw" (
    "id" TEXT NOT NULL,
    "batch_id" TEXT NOT NULL,
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
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "attendance_raw_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "anomalies" (
    "id" TEXT NOT NULL,
    "batch_id" TEXT NOT NULL,
    "attendance_raw_id" TEXT NOT NULL,
    "type" "AnomalyType" NOT NULL,
    "message" TEXT NOT NULL,
    "resolved" BOOLEAN NOT NULL DEFAULT false,
    "resolved_by_id" TEXT,
    "resolved_at" TIMESTAMP(3),
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "anomalies_pkey" PRIMARY KEY ("id")
);

-- CreateIndex
CREATE UNIQUE INDEX "password_reset_tokens_token_hash_key" ON "password_reset_tokens"("token_hash");

-- CreateIndex
CREATE UNIQUE INDEX "employees_person_id_key" ON "employees"("person_id");

-- CreateIndex
CREATE UNIQUE INDEX "attendance_raw_employee_id_date_key" ON "attendance_raw"("employee_id", "date");

-- AddForeignKey
ALTER TABLE "password_reset_tokens" ADD CONSTRAINT "password_reset_tokens_user_id_fkey" FOREIGN KEY ("user_id") REFERENCES "users"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "employees" ADD CONSTRAINT "employees_department_id_fkey" FOREIGN KEY ("department_id") REFERENCES "departments"("id") ON DELETE SET NULL ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "attendance_batches" ADD CONSTRAINT "attendance_batches_uploaded_by_id_fkey" FOREIGN KEY ("uploaded_by_id") REFERENCES "users"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "attendance_raw" ADD CONSTRAINT "attendance_raw_batch_id_fkey" FOREIGN KEY ("batch_id") REFERENCES "attendance_batches"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "attendance_raw" ADD CONSTRAINT "attendance_raw_employee_id_fkey" FOREIGN KEY ("employee_id") REFERENCES "employees"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "anomalies" ADD CONSTRAINT "anomalies_batch_id_fkey" FOREIGN KEY ("batch_id") REFERENCES "attendance_batches"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "anomalies" ADD CONSTRAINT "anomalies_attendance_raw_id_fkey" FOREIGN KEY ("attendance_raw_id") REFERENCES "attendance_raw"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "anomalies" ADD CONSTRAINT "anomalies_resolved_by_id_fkey" FOREIGN KEY ("resolved_by_id") REFERENCES "users"("id") ON DELETE SET NULL ON UPDATE CASCADE;
