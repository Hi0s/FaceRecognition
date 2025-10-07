from functools import wraps
from typing import Any, Callable

from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect
from django.urls import reverse


def admin_required(view_func: Callable[[HttpRequest, Any], HttpResponse]):
    @wraps(view_func)
    def _wrapped_view(request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        employee_id = request.session.get('employee_id')
        if not employee_id or not request.session.get('is_admin'):
            return redirect(f"{reverse('checkin:login')}?next={request.path}")
        return view_func(request, *args, **kwargs)

    return _wrapped_view
