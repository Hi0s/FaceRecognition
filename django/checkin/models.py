from django.db import models
from django.utils import timezone


class Employee(models.Model):
    GENDER_CHOICES = [
        ('male', 'Male'),
        ('female', 'Female'),
        ('other', 'Other'),
    ]

    employee_id = models.CharField(max_length=32, unique=True)
    employee_name = models.CharField(max_length=255)
    employee_birth = models.DateField()
    employee_gender = models.CharField(max_length=10, choices=GENDER_CHOICES)
    is_admin = models.BooleanField(default=False)
    password = models.CharField(max_length=128)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'tbl_employee'
        ordering = ['employee_name']

    def __str__(self) -> str:
        return f"{self.employee_name} ({self.employee_id})"


class CheckInHistory(models.Model):
    CHECK_TYPE_CHOICES = [
        ('in', 'Check In'),
        ('out', 'Check Out'),
    ]

    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='checkins')
    check_type = models.CharField(max_length=3, choices=CHECK_TYPE_CHOICES)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = 'tbl_checkin_history'
        ordering = ['-created_at']

    def __str__(self) -> str:
        return f"{self.employee} - {self.get_check_type_display()} @ {self.created_at:%Y-%m-%d %H:%M}"
