import json

from django import forms
from django.contrib.auth.hashers import check_password, make_password
from django.db import transaction
from django.utils import timezone

from .models import CheckInHistory, Employee
from .services.face_enrollment import register_employee_faces


class LoginForm(forms.Form):
    employee_id = forms.IntegerField(label='Employee ID')
    password = forms.CharField(widget=forms.PasswordInput)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            existing_classes = field.widget.attrs.get('class', '')
            field.widget.attrs['class'] = f"{existing_classes} form-control".strip()

    def clean(self):
        cleaned = super().clean()
        employee_id = cleaned.get('employee_id')
        password = cleaned.get('password')

        if employee_id and password:
            try:
                employee = Employee.objects.get(employee_id=employee_id, is_admin=True)
            except Employee.DoesNotExist as exc:
                raise forms.ValidationError('Invalid credentials or not authorized.') from exc

            if not check_password(password, employee.password):
                raise forms.ValidationError('Invalid credentials or not authorized.')

            cleaned['employee'] = employee
        return cleaned


class EmployeeForm(forms.ModelForm):
    password = forms.CharField(
        widget=forms.PasswordInput,
        required=False,
        help_text='Leave blank to keep the current password.',
    )
    face_captures = forms.CharField(widget=forms.HiddenInput, required=False)

    class Meta:
        model = Employee
        fields = [
            'employee_id',
            'employee_name',
            'employee_birth',
            'employee_gender',
            'is_admin',
            'password',
        ]
        widgets = {
            'employee_birth': forms.DateInput(attrs={'type': 'date'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._pending_face_captures: list[str] = []
        if not self.instance.pk:
            self.fields['password'].required = True
        for name, field in self.fields.items():
            if isinstance(field.widget, forms.HiddenInput):
                continue
            css = field.widget.attrs.get('class', '')
            field.widget.attrs['class'] = f"{css} form-control".strip()
        self.fields['is_admin'].widget.attrs['class'] = 'form-check-input'
        self.fields['face_captures'].required = not self.instance.pk

    def save(self, commit=True):
        employee = super().save(commit=False)
        password = self.cleaned_data.get('password')
        if password:
            employee.password = make_password(password)
        self._pending_face_captures = []
        captures = self.cleaned_data.get('face_captures') or []

        if commit:
            with transaction.atomic():
                employee.save()
                if captures:
                    try:
                        register_employee_faces(employee.employee_id, captures)
                    except ValueError as exc:
                        raise forms.ValidationError(str(exc)) from exc
        else:
            self._pending_face_captures = captures
        return employee

    def clean_face_captures(self):
        raw_value = self.cleaned_data.get('face_captures')
        if not raw_value:
            if self.instance.pk:
                return []
            raise forms.ValidationError('Capture three face images before saving.')

        try:
            parsed = json.loads(raw_value)
        except json.JSONDecodeError as exc:
            raise forms.ValidationError('Face capture data is invalid.') from exc

        if not isinstance(parsed, list):
            raise forms.ValidationError('Face capture data is invalid.')

        sanitized = [value for value in parsed if isinstance(value, str) and value.strip()]
        if len(sanitized) != 3:
            raise forms.ValidationError('All three face poses are required.')

        return sanitized


class CheckInForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.performed_action = None
        css = self.fields['employee'].widget.attrs.get('class', '')
        self.fields['employee'].widget.attrs['class'] = f"{css} form-select".strip()

    class Meta:
        model = CheckInHistory
        fields = ['employee']

    def save(self, commit=True):
        employee = self.cleaned_data['employee']
        today = timezone.localdate()
        now = timezone.now()

        checkin_qs = CheckInHistory.objects.filter(
            employee=employee,
            created_at__date=today,
            check_type='in',
        )
        checkout_qs = CheckInHistory.objects.filter(
            employee=employee,
            created_at__date=today,
            check_type='out',
        )

        existing_checkin = checkin_qs.order_by('-created_at').first()
        existing_checkout = checkout_qs.order_by('-created_at').first()

        if not existing_checkin:
            record = CheckInHistory(
                employee=employee,
                check_type='in',
                created_at=now,
            )
            if commit:
                record.save()
            self.performed_action = 'checkin_created'
        elif not existing_checkout:
            record = CheckInHistory(
                employee=employee,
                check_type='out',
                created_at=now,
            )
            if commit:
                record.save()
            self.performed_action = 'checkout_created'
        else:
            record = existing_checkout
            record.created_at = now
            if commit:
                record.save(update_fields=['created_at'])
            self.performed_action = 'checkout_updated'

        self.instance = record
        return record

    def get_success_message(self) -> str:
        mapping = {
            'checkin_created': 'Check-in recorded for today.',
            'checkout_created': 'Check-out recorded for today.',
            'checkout_updated': 'Check-out time updated.',
        }
        return mapping.get(self.performed_action, 'Check history updated.')
