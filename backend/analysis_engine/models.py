from django.db import models
from django.utils import timezone


class analysis_state(models.Model):
    id = models.IntegerField(primary_key=True, default=1)
    current_sem_week = models.IntegerField(default=0)
    current_global_week = models.IntegerField(default=0)
    current_semester = models.IntegerField(default=1)
    last_updated_at = models.DateTimeField(auto_now=True)

    def save(self, *args, **kwargs):
        self.id = 1  # Ensure singleton
        super().save(*args, **kwargs)

 
    def __str__(self):
        return f"Analysis at sem_week={self.current_sem_week}, semester={self.current_semester}"
    

class weekly_metrics(models.Model):
    id=models.AutoField(primary_key=True)
    student_id=models.CharField(max_length=10)
    class_id=models.CharField(max_length=20)
    semester=models.IntegerField()
    sem_week=models.IntegerField()
    computed_at=models.DateTimeField(auto_now_add=True)
    effort_score=models.DecimalField(max_digits=5, decimal_places=2, null=True)
    library_visits_w=models.IntegerField(default=0)
    book_borrows_w=models.IntegerField(default=0)
    assn_quality_avg=models.DecimalField(max_digits=5, decimal_places=2, null=True)
    assn_plagiarism_max=models.DecimalField(max_digits=5, decimal_places=2, null=True)
    att_rate_recent=models.DecimalField(max_digits=5, decimal_places=4, null=True)
    quiz_submit_rate_recent=models.DecimalField(max_digits=5, decimal_places=4, null=True)
    quiz_avg_pct=models.DecimalField(max_digits=5, decimal_places=2, null=True)
    assn_avg_pct=models.DecimalField(max_digits=5, decimal_places=2, null=True)
    midterm_score_pct=models.DecimalField(max_digits=5, decimal_places=2, null=True)
    weight_m=models.DecimalField(max_digits=4, decimal_places=2, default=0.4)  
    weight_n=models.DecimalField(max_digits=4, decimal_places=2, default=0)
    weight_p=models.DecimalField(max_digits=4, decimal_places=2, default=0)
    academic_performance=models.DecimalField(max_digits=5, decimal_places=2, null=True)
    risk_of_failing=models.DecimalField(max_digits=5, decimal_places=2, null=True)
    recent_quiz_avg_pct=models.DecimalField(max_digits=5, decimal_places=2, null=True)
    midterm_pct=models.DecimalField(max_digits=5, decimal_places=2, null=True)
    endterm_pct=models.DecimalField(max_digits=5, decimal_places=2, null=True)
    quiz_trend=models.DecimalField(max_digits=6, decimal_places=3, null=True)

    def __str__(self):
        return f"Metrics for student {self.student_id} in class {self.class_id} at sem {self.semester} week {self.sem_week}"

  
class weekly_flags(models.Model):
    id=models.AutoField(primary_key=True)
    student_id=models.CharField(max_length=10)
    class_id=models.CharField(max_length=20)
    semester=models.IntegerField()
    sem_week=models.IntegerField()
    computed_at=models.DateTimeField(auto_now_add=True)
    risk_tier=models.CharField(max_length=40)
    urgency_score=models.IntegerField()
    escalation_level=models.IntegerField(default=0)
    archetype=models.CharField(max_length=50)
    diagnosis=models.TextField()

    class Meta:
        indexes = [
        models.Index(fields=['class_id', 'semester', 'sem_week'], name='idx_wf_class_sem_week'),
        models.Index(fields=['student_id'], name='idx_wf_student'),
    ]
    
    def __str__(self):
        return f"Flags for student {self.student_id} in class {self.class_id} at sem {self.semester} week {self.sem_week}"


class pre_sem_watchlist(models.Model):
    id=models.BigAutoField(primary_key=True)
    student_id=models.CharField(max_length=20)
    class_id=models.CharField(max_length=20)
    target_semester=models.IntegerField()
    computed_at=models.DateTimeField(auto_now_add=True)
    risk_probability_pct=models.DecimalField(max_digits=5, decimal_places=2)
    escalation_level=models.IntegerField(default=0)
    max_plagiarism=models.DecimalField(max_digits=5, decimal_places=2, default=0)
    att_rate_hist=models.DecimalField(max_digits=5, decimal_places=4)
    assn_rate_hist=models.DecimalField(max_digits=5, decimal_places=4)
    exam_avg_hist=models.DecimalField(max_digits=5, decimal_places=2)
    hard_subject_count=models.IntegerField(default=0)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['student_id', 'target_semester'], name='uq_psw')]
        indexes=[models.Index(fields=['class_id', 'target_semester'], name='idx_psw_class')]

    def __str__(self):
        return f"Pre-sem watchlist for student {self.student_id} in class {self.class_id} for semester {self.target_semester}"
    


class intervention_log(models.Model):
    id=models.BigAutoField(primary_key=True)
    student_id=models.CharField(max_length=10)
    semester=models.IntegerField()
    sem_week=models.IntegerField()
    logged_at=models.DateTimeField(auto_now_add=True)
    escalation_level=models.IntegerField(default=1)
    trigger_diagnosis=models.TextField()
    advisor_notified=models.BooleanField(default=False)
    notes=models.TextField()

    class Meta:
        indexes=[models.Index(fields=['student_id'], name='idx_il_student'),
        models.Index(fields=['semester', 'sem_week'], name='idx_il_sem_week')]

    def __str__(self):
        return f"Intervention log for student {self.student_id} at sem {self.semester} week {self.sem_week} with escalation level {self.escalation_level}"


class subject_difficulty(models.Model):
    subject_id=models.CharField(max_length=20)
    semester=models.IntegerField()
    computed_at=models.DateTimeField(auto_now_add=True)
    total_students=models.IntegerField()
    students_passed=models.IntegerField()
    pass_rate=models.DecimalField(max_digits=5, decimal_places=4)
    difficulty_label=models.CharField(max_length=20)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['subject_id', 'semester'], name='uq_sd')]

    def __str__(self):
        return f"Difficulty for subject {self.subject_id} in semester {self.semester}: {self.difficulty_label} with pass rate {self.pass_rate}"
    

class event_log(models.Model):
    id=models.BigAutoField(primary_key=True)
    event_type=models.CharField(max_length=50)
    triggered_at=models.DateTimeField(auto_now_add=True)
    client_week=models.IntegerField(null=True)
    analysis_week=models.IntegerField(null=True)
    semester=models.IntegerField(null=True)
    status=models.CharField(max_length=10, default='ok')
    error_message=models.TextField(null=True)
    duration_ms=models.IntegerField(null=True)

    def __str__(self):
        return f"Event {self.event_type} triggered at {self.triggered_at} with status {self.status}"
    

