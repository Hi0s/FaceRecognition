from django.contrib import messages
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from .decorators import admin_required
from .forms import CheckInForm, EmployeeForm, LoginForm
from .models import CheckInHistory, Employee


def login_view(request: HttpRequest) -> HttpResponse:
    if request.session.get('employee_id') and request.session.get('is_admin'):
        return redirect('checkin:employee_list')

    form = LoginForm(request.POST or None)
    if request.method == 'POST':
        if form.is_valid():
            employee = form.cleaned_data['employee']
            request.session['employee_id'] = employee.employee_id
            request.session['employee_name'] = employee.employee_name
            request.session['is_admin'] = employee.is_admin
            messages.success(request, f"Welcome back, {employee.employee_name}!")
            next_url = request.GET.get('next') or reverse('checkin:employee_list')
            return redirect(next_url)
        messages.error(request, 'Unable to sign in with the provided credentials.')

    return render(request, 'checkin/login.html', {'form': form})


def logout_view(request: HttpRequest) -> HttpResponse:
    request.session.flush()
    return redirect('checkin:login')


@admin_required
def employee_list(request: HttpRequest) -> HttpResponse:
    employees = Employee.objects.all().order_by('-is_admin', 'employee_name')
    form = EmployeeForm(request.POST or None)

    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Employee created successfully.')
        return redirect('checkin:employee_list')

    context = {
        'employees': employees,
        'form': form,
        'active_nav': 'employees',
    }
    return render(request, 'checkin/employee_list.html', context)


@admin_required
def employee_edit(request: HttpRequest, pk: int) -> HttpResponse:
    employee = get_object_or_404(Employee, pk=pk)
    form = EmployeeForm(request.POST or None, instance=employee)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Employee updated successfully.')
        return redirect('checkin:employee_list')

    context = {
        'form': form,
        'employee': employee,
        'active_nav': 'employees',
    }
    return render(request, 'checkin/employee_edit.html', context)


@admin_required
def employee_delete(request: HttpRequest, pk: int) -> HttpResponse:
    employee = get_object_or_404(Employee, pk=pk)
    if request.method == 'POST':
        employee.delete()
        messages.success(request, 'Employee deleted successfully.')
        return redirect('checkin:employee_list')
    context = {'employee': employee, 'active_nav': 'employees'}
    return render(request, 'checkin/employee_confirm_delete.html', context)


@admin_required
def history_view(request: HttpRequest) -> HttpResponse:
    history_qs = CheckInHistory.objects.select_related('employee')
    employee_id = request.GET.get('employee')
    check_type = request.GET.get('check_type')

    if employee_id:
        history_qs = history_qs.filter(employee__employee_id__icontains=employee_id)
    if check_type in {'in', 'out'}:
        history_qs = history_qs.filter(check_type=check_type)

    form = CheckInForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, form.get_success_message())
        return redirect('checkin:history')

    context = {
        'history_items': list(history_qs[:200]),
        'history_total_count': history_qs.count(),
        'form': form,
        'employees': Employee.objects.all(),
        'active_nav': 'history',
    }
    return render(request, 'checkin/history.html', context)
