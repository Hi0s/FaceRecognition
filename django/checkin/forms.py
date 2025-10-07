from django import forms
from django.contrib.auth.hashers import check_password, make_password
from django.utils import timezone

from .models import CheckInHistory, Employee


class LoginForm(forms.Form):
    employee_id = forms.CharField(label='Employee ID', max_length=32)
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
        if not self.instance.pk:
            self.fields['password'].required = True
        for name, field in self.fields.items():
            css = field.widget.attrs.get('class', '')
            field.widget.attrs['class'] = f"{css} form-control".strip()
        self.fields['is_admin'].widget.attrs['class'] = 'form-check-input'

    def save(self, commit=True):
        employee = super().save(commit=False)
        password = self.cleaned_data.get('password')
        if password:
            employee.password = make_password(password)
        if commit:
            employee.save()
        return employee


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
