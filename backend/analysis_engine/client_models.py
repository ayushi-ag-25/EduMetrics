# ============================================================
#  analysis_engine/client_models.py
#
#  Unmanaged models for the CLIENT database (edumetrics_client).
#  Django will NEVER create, migrate, or modify these tables.
#  They already exist on the college's server — these are just
#  Python descriptions so the ORM can query them.
#
#  All models use:
#      class Meta:
#          managed  = False   ← Django never touches the table
#          app_label = 'analysis_engine'
#          db_table  = '<actual MySQL table name>'
#
#  To query these, Django automatically routes to 'client_db'
#  because of the router in routers.py.
# ============================================================

from django.db import models


# ── 1. CLASSES ────────────────────────────────────────────────
class ClientClass(models.Model):
    class_id        = models.CharField(max_length=20, primary_key=True)
    name            = models.CharField(max_length=60)
    semester        = models.IntegerField()
    year_of_study   = models.IntegerField()
    section         = models.CharField(max_length=5, default='A')
    branch          = models.CharField(max_length=20, default='CSE')
    batch_start_year = models.IntegerField(null=True)
    academic_year   = models.CharField(max_length=12, null=True)
    total_students  = models.IntegerField(null=True)
    # Your sim has odd_sem / even_sem columns too — add if needed:
    # odd_sem         = models.IntegerField(null=True)
    # even_sem        = models.IntegerField(null=True)

    class Meta:
        managed  = False
        app_label = 'analysis_engine'
        db_table  = 'classes'

    def __str__(self):
        return self.name


# ── 2. ADVISORS ───────────────────────────────────────────────
class ClientAdvisor(models.Model):
    advisor_id  = models.CharField(max_length=10, primary_key=True)
    name        = models.CharField(max_length=80)
    email       = models.CharField(max_length=100)
    class_id    = models.CharField(max_length=20, null=True)  # raw FK, not a relation

    class Meta:
        managed  = False
        app_label = 'analysis_engine'
        db_table  = 'advisors'

    def __str__(self):
        return self.name


# ── 3. STUDENTS ───────────────────────────────────────────────
class ClientStudent(models.Model):
    student_id   = models.CharField(max_length=10, primary_key=True)
    class_id     = models.CharField(max_length=20)
    advisor_id   = models.CharField(max_length=10, null=True)
    name         = models.CharField(max_length=80)
    roll_number  = models.IntegerField()
    gender       = models.CharField(max_length=1, null=True)
    email        = models.CharField(max_length=100, null=True)
    parent_email = models.CharField(max_length=100, null=True)
    phone        = models.CharField(max_length=15, null=True)
    archetype    = models.CharField(max_length=30, default='consistent_avg')

    class Meta:
        managed  = False
        app_label = 'analysis_engine'
        db_table  = 'students'

    def __str__(self):
        return f"{self.name} ({self.student_id})"


# ── 4. SUBJECTS ───────────────────────────────────────────────
class ClientSubject(models.Model):
    subject_id   = models.CharField(max_length=15, primary_key=True)
    subject_name = models.CharField(max_length=80)
    semester     = models.IntegerField()
    credits      = models.IntegerField(default=4)
    difficulty   = models.CharField(max_length=10, default='Medium')
    subject_type = models.CharField(max_length=20, default='Core')

    class Meta:
        managed  = False
        app_label = 'analysis_engine'
        db_table  = 'subjects'

    def __str__(self):
        return self.subject_name


# ── 5. CLASS_SUBJECTS ─────────────────────────────────────────
class ClientClassSubject(models.Model):
    # Composite PK — Django doesn't support composite PKs natively.
    # Use this model read-only; don't try to .save() it.
    id           = models.AutoField(primary_key=True)  # dummy PK for Django
    class_id     = models.CharField(max_length=20)
    subject_id   = models.CharField(max_length=15)
    teacher_name = models.CharField(max_length=80, null=True)

    class Meta:
        managed  = False
        app_label = 'analysis_engine'
        db_table  = 'class_subjects'


# ── 6. SIM STATE ──────────────────────────────────────────────
class ClientSimState(models.Model):
    id           = models.IntegerField(primary_key=True, default=1)
    current_week = models.IntegerField()
    semester_start = models.DateField()
    last_updated = models.DateTimeField(auto_now=True)
    # Add sim_year if your version of sim_state has it:
    # sim_year     = models.IntegerField(null=True)

    class Meta:
        managed  = False
        app_label = 'analysis_engine'
        db_table  = 'sim_state'


# ── 7. ATTENDANCE ─────────────────────────────────────────────
class ClientAttendance(models.Model):
    id             = models.BigAutoField(primary_key=True)
    student_id     = models.CharField(max_length=10)
    class_id       = models.CharField(max_length=20)
    subject_id     = models.CharField(max_length=15)
    week           = models.IntegerField()
    week_date      = models.DateField()
    lectures_held  = models.IntegerField(default=3)
    present        = models.IntegerField(null=True)
    absent         = models.IntegerField(null=True)
    late           = models.IntegerField(null=True)
    attendance_pct = models.DecimalField(max_digits=5, decimal_places=2, null=True)

    class Meta:
        managed  = False
        app_label = 'analysis_engine'
        db_table  = 'attendance'


# ── 8. ASSIGNMENT DEFINITIONS ─────────────────────────────────
class ClientAssignmentDefinition(models.Model):
    assignment_id = models.CharField(max_length=15, primary_key=True)
    class_id      = models.CharField(max_length=20)
    subject_id    = models.CharField(max_length=15)
    title         = models.CharField(max_length=120)
    assigned_week = models.IntegerField()
    due_week      = models.IntegerField()
    max_marks     = models.IntegerField(default=10)
    # Add semester if your version has it:
    # semester      = models.IntegerField(null=True)

    class Meta:
        managed  = False
        app_label = 'analysis_engine'
        db_table  = 'assignment_definitions'


# ── 9. ASSIGNMENT SUBMISSIONS ─────────────────────────────────
class ClientAssignmentSubmission(models.Model):
    id              = models.BigAutoField(primary_key=True)
    assignment_id   = models.CharField(max_length=15)
    student_id      = models.CharField(max_length=10)
    class_id        = models.CharField(max_length=20)
    status          = models.CharField(max_length=15, default='pending')
    submission_date = models.DateTimeField(null=True)
    latency_hours   = models.DecimalField(max_digits=6, decimal_places=1, null=True)
    marks_obtained  = models.DecimalField(max_digits=5, decimal_places=2, null=True)
    quality_pct     = models.DecimalField(max_digits=5, decimal_places=2, null=True)
    plagiarism_pct  = models.DecimalField(max_digits=5, decimal_places=2, default=0)

    class Meta:
        managed  = False
        app_label = 'analysis_engine'
        db_table  = 'assignment_submissions'


# ── 10. QUIZ DEFINITIONS ──────────────────────────────────────
class ClientQuizDefinition(models.Model):
    quiz_id        = models.CharField(max_length=15, primary_key=True)
    class_id       = models.CharField(max_length=20)
    subject_id     = models.CharField(max_length=15)
    title          = models.CharField(max_length=100)
    scheduled_week = models.IntegerField()
    quiz_date      = models.DateField(null=True)
    max_marks      = models.IntegerField(default=10)
    duration_mins  = models.IntegerField(default=20)
    # Add semester if your version has it:
    # semester       = models.IntegerField(null=True)

    class Meta:
        managed  = False
        app_label = 'analysis_engine'
        db_table  = 'quiz_definitions'


# ── 11. QUIZ SUBMISSIONS ──────────────────────────────────────
class ClientQuizSubmission(models.Model):
    id             = models.BigAutoField(primary_key=True)
    quiz_id        = models.CharField(max_length=15)
    student_id     = models.CharField(max_length=10)
    class_id       = models.CharField(max_length=20)
    attempted      = models.BooleanField(default=False)
    attempt_date   = models.DateTimeField(null=True)
    marks_obtained = models.DecimalField(max_digits=5, decimal_places=2, null=True)
    score_pct      = models.DecimalField(max_digits=5, decimal_places=2, null=True)

    class Meta:
        managed  = False
        app_label = 'analysis_engine'
        db_table  = 'quiz_submissions'


# ── 12. LIBRARY VISITS ────────────────────────────────────────
class ClientLibraryVisit(models.Model):
    id              = models.BigAutoField(primary_key=True)
    student_id      = models.CharField(max_length=10)
    class_id        = models.CharField(max_length=20)
    week            = models.IntegerField()
    week_date       = models.DateField(null=True)
    physical_visits = models.IntegerField(default=0)
    # Add semester if your version has it:
    # semester        = models.IntegerField(null=True)

    class Meta:
        managed  = False
        app_label = 'analysis_engine'
        db_table  = 'library_visits'


# ── 13. BOOK BORROWS ──────────────────────────────────────────
class ClientBookBorrow(models.Model):
    borrow_id   = models.CharField(max_length=15, primary_key=True)
    student_id  = models.CharField(max_length=10)
    class_id    = models.CharField(max_length=20)
    book_title  = models.CharField(max_length=120, null=True)
    borrow_date = models.DateField(null=True)
    return_date = models.DateField(null=True)
    borrow_week = models.IntegerField(null=True)
    return_week = models.IntegerField(null=True)
    # Add semester if your version has it:
    # semester    = models.IntegerField(null=True)

    class Meta:
        managed  = False
        app_label = 'analysis_engine'
        db_table  = 'book_borrows'


# ── 14. EXAM SCHEDULE ─────────────────────────────────────────
class ClientExamSchedule(models.Model):
    schedule_id    = models.CharField(max_length=15, primary_key=True)
    class_id       = models.CharField(max_length=20)
    subject_id     = models.CharField(max_length=15)
    exam_type      = models.CharField(max_length=15)
    scheduled_week = models.IntegerField()
    exam_date      = models.DateField(null=True)
    max_marks      = models.IntegerField(default=50)
    duration_mins  = models.IntegerField(default=120)
    # Add semester if your version has it:
    # semester       = models.IntegerField(null=True)

    class Meta:
        managed  = False
        app_label = 'analysis_engine'
        db_table  = 'exam_schedule'


# ── 15. EXAM RESULTS ──────────────────────────────────────────
class ClientExamResult(models.Model):
    id             = models.BigAutoField(primary_key=True)
    schedule_id    = models.CharField(max_length=15)
    student_id     = models.CharField(max_length=10)
    class_id       = models.CharField(max_length=20)
    marks_obtained = models.DecimalField(max_digits=5, decimal_places=2, null=True)
    max_marks      = models.IntegerField(null=True)
    score_pct      = models.DecimalField(max_digits=5, decimal_places=2, null=True)
    pass_fail      = models.CharField(max_length=1, null=True)
    grade          = models.CharField(max_length=5, null=True)
    result_date    = models.DateField(null=True)

    class Meta:
        managed  = False
        app_label = 'analysis_engine'
        db_table  = 'exam_results'
