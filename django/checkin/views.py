import json
from django import forms as django_forms
from django.contrib import messages
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.dateparse import parse_date
from django.views.decorators.csrf import csrf_exempt

from .decorators import admin_required
from .forms import CheckInForm, EmployeeForm, LoginForm
from .models import CheckInHistory, Employee
from .services.face_encoder import encode_image_file
from .services.faiss_index import face_index


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
        employee.delete()
        face_index.remove_id(employee.employee_id)
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

    threshold = 0.45
    matches = []
    best_employee = None
    best_distance = None
    best_name = None

    for idx, distance in results:
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
