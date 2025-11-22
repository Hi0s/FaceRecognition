import json
from datetime import timedelta
from math import isclose
from django import forms as django_forms
from django.contrib import messages
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.views.decorators.csrf import csrf_exempt

from .decorators import admin_required
from .forms import CheckInForm, EmployeeForm, LoginForm
from .models import CheckInHistory, Employee
from .services.face_encoder import encode_image_file
from .services.faiss_index import face_index

#to-do add a late for work to record

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
    employees = Employee.objects.all().order_by('-is_admin', 'employee_id')
    form = EmployeeForm(request.POST or None)

    if request.method == 'POST' and form.is_valid():
        try:
            form.save()
        except django_forms.ValidationError as exc:
            for message in exc.messages:
                form.add_error(None, message)
        else:
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
        try:
            form.save()
        except django_forms.ValidationError as exc:
            for message in exc.messages:
                form.add_error(None, message)
        else:
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
        face_index.remove_id(employee.employee_id)
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
    date_input = request.GET.get('date')

    if employee_id:
        history_qs = history_qs.filter(employee__employee_id__icontains=employee_id)
    if check_type in {'in', 'out'}:
        history_qs = history_qs.filter(check_type=check_type)

    date_input = parse_date(date_input) if date_input else None
    if date_input:
        history_qs = history_qs.filter(created_at=date_input)

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
        'date': date_input or '',
    }
    return render(request, 'checkin/history.html', context)


def _calculate_work_duration(records) -> timedelta:
    ordered_records = sorted(records, key=lambda item: item.created_at)
    total = timedelta()
    current_check_in = None

    for record in ordered_records:
        timestamp = timezone.localtime(record.created_at)
        if record.check_type == 'in':
            current_check_in = timestamp
        elif record.check_type == 'out' and current_check_in is not None:
            if timestamp > current_check_in:
                total += timestamp - current_check_in
            current_check_in = None

    return total


@admin_required
def workdays_view(request: HttpRequest) -> HttpResponse:
    employee_query = request.GET.get('employee', '').strip()
    start_input = request.GET.get('start')
    end_input = request.GET.get('end')

    today = timezone.localdate()
    default_start = today - timedelta(days=6)
    default_end = today

    start_date = parse_date(start_input) if start_input else default_start
    end_date = parse_date(end_input) if end_input else default_end

    if start_date and end_date and end_date < start_date:
        start_date, end_date = end_date, start_date

    history_qs = CheckInHistory.objects.select_related('employee')

    if employee_query:
        history_qs = history_qs.filter(employee__employee_id__icontains=employee_query)
    if start_date:
        history_qs = history_qs.filter(created_at__date__gte=start_date)
    if end_date:
        history_qs = history_qs.filter(created_at__date__lte=end_date)

    history_qs = history_qs.order_by('employee__employee_name', 'created_at')

    grouped = {}
    for record in history_qs:
        local_dt = timezone.localtime(record.created_at)
        workday = local_dt.date()
        key = (record.employee_id, workday)
        entry = grouped.setdefault(
            key,
            {
                'employee': record.employee,
                'date': workday,
                'records': [],
            },
        )
        entry['records'].append(record)

    workday_rows = []
    for entry in grouped.values():
        total_duration = _calculate_work_duration(entry['records'])
        hours = total_duration.total_seconds() / 3600
        if hours > 8.0 + 1e-3:
            badge = 'bg-primary'
            status = 'Above 8 hours'
        elif isclose(hours, 8.0, abs_tol=0.01):
            badge = 'bg-success'
            status = 'Exactly 8 hours'
        else:
            badge = 'bg-danger'
            status = 'Below 8 hours'
        records_sorted = sorted(entry['records'], key=lambda r: r.created_at)
        first_in = next((r for r in records_sorted if r.check_type == 'in'), None)

        if first_in:
            late = first_in.is_late
        else:
            late = False
        workday_rows.append(
            {
                'employee': entry['employee'],
                'date': entry['date'],
                'hours': hours,
                'hours_display': f"{hours:.2f}",
                'status': status,
                'late':late,
                'badge_class': badge,
                'records': sorted(entry['records'], key=lambda item: item.created_at),
            },
        )

    workday_rows.sort(
        key=lambda item: (-item['date'].toordinal(), item['employee'].employee_name.lower()),
    )

    context = {
        'workday_rows': workday_rows,
        'employee_query': employee_query,
        'start_date': start_date,
        'end_date': end_date,
        'employees': Employee.objects.all().order_by('employee_name'),
        'active_nav': 'workdays',
    }
    return render(request, 'checkin/workdays.html', context)

@csrf_exempt
def face_match_api(request: HttpRequest) -> JsonResponse:
    if request.method != 'POST':
        return JsonResponse({'detail': 'Method not allowed.'}, status=405)

    image_file = request.FILES.get('image')
    if not image_file:
        return JsonResponse({'detail': 'No image file provided.'}, status=400)

    try:
        image_bytes = image_file.read()
        embedding_array = encode_image_file(image_bytes=image_bytes, employee_id=0, recognize=True)
    except Exception as exc:
        print('Exception content', exc)
        return JsonResponse({'detail': 'Unable to process provided data.'}, status=400)

    embedding_vector = embedding_array.flatten().astype('float32')
    try:
        results = face_index.search(embedding_vector, k=5)
    except Exception:
        return JsonResponse({'detail': 'Search failed.'}, status=500)

    threshold = 0.4
    matches = []
    best_employee = None
    best_distance = None
    best_name = None

    for idx, distance in results:
        print(f"Search result: idx={idx}, distance={distance:.4f}")
        if idx == -1 or distance > threshold:
            continue
        employee_id = idx // 100 if idx >= 0 else None
        employee_name = None
        if employee_id is not None:
            try:
                employee = Employee.objects.get(employee_id=employee_id)
            except Employee.DoesNotExist:
                employee = None
            if employee:
                employee_name = employee.employee_name
                matches.append(
                    {
                        'employee_id': employee_id,
                        'distance': distance,
                        'employee_name': employee_name,
                    }
                )
                if best_employee is None:
                    best_employee = employee
                    best_distance = distance
                    best_name = employee_name

    if best_employee is None:
        return JsonResponse({'employee_id': None, 'distance': None, 'matches': []}, status=200)

    form = CheckInForm(data={'employee': str(best_employee.pk)})
    if not form.is_valid():
        return JsonResponse({'detail': 'Unable to record check-in.', 'errors': form.errors}, status=400)

    form.save()

    print(f"Matched employee ID {best_employee.employee_id} "
          f"({best_employee.employee_name}) with distance {best_distance:.4f}.")
    return JsonResponse(
        {
            'employee_id': best_employee.employee_id,
            'distance': best_distance,
            'employee_name': best_name,
            'action': form.performed_action,
            'message': form.get_success_message(),
        },
        status=200,
    )
