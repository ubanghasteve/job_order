from django.http import HttpResponse
from django.shortcuts import redirect
from django.core.exceptions import PermissionDenied
from functools import wraps
from django.contrib import messages

def auth_users(view_func):
    def wrapper(request, *args, **kwargs):
        if request.user.is_authenticated:
            return redirect('dashboard-index')
        else:
            return view_func(request, *args, **kwargs)
    return wrapper


def allowed_users(allowed_roles=[]):
    def decorators(view_func):
        def wrapper(request, *args, **kwargs):
            group = None
            if request.user.groups.exists():
                group = request.user.groups.all()[0].name
            if group in allowed_roles:
                return view_func(request, *args, **kwargs)
            else:
                return HttpResponse('You are not authorized to view this page. <a href="/index/">Click here to go back to dashboard</a>')
        return wrapper
    return decorators



def can_edit_user_data(view_func):
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if request.user.groups.filter(name='SuperAdmin').exists():
            return view_func(request, *args, **kwargs)
        if request.method == 'GET':
            return view_func(request, *args, **kwargs)
        raise PermissionDenied
    return wrapper


def leave_manager_only(view_func):
    def wrapper_function(request, *args, **kwargs):       
        if request.user.groups.filter(name__in=['Superuser', 'Leave Manager']).exists():
            return view_func(request, *args, **kwargs)
        messages.error(request, 'You are not authorized to view this page.')
        return redirect('dashboard-index')
    return wrapper_function


def can_manage_leave(view_func):
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if request.user.groups.filter(name__in=['Leave', 'Admin', 'SuperAdmin']).exists():
            return view_func(request, *args, **kwargs)
        messages.error(request, 'You need leave management permissions to perform this action.')
        return redirect('dashboard-index')
    return wrapper