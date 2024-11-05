from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.models import User
from .models import Product, Order, Leave, Loan, ProductStatusHistory

@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ('job_order', 'organization_name', 'created_by', 'date_created')
    list_filter = ('created_by', 'date_created')
    search_fields = ('job_order', 'organization_name', 'created_by__username')
    readonly_fields = ('created_by',)

    def save_model(self, request, obj, form, change):
        if not obj.pk:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)

@admin.register(Leave)
class LeaveAdmin(admin.ModelAdmin):
    list_display = ('user', 'leave_type', 'start_date', 'end_date', 'status', 'approved_by')
    list_filter = ('status', 'leave_type', 'start_date')
    search_fields = ('user__username', 'leave_type')
    readonly_fields = ('applied_date',)
    
    def save_model(self, request, obj, form, change):
        if not obj.pk:
            obj.approved_by = request.user
        super().save_model(request, obj, form, change)

@admin.register(Loan)
class LoanAdmin(admin.ModelAdmin):
    list_display = ('user', 'loan_type', 'amount', 'status', 'applied_date', 'approved_by')
    list_filter = ('status', 'loan_type', 'applied_date')
    search_fields = ('user__username', 'loan_type')
    readonly_fields = ('applied_date',)

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser

    def save_model(self, request, obj, form, change):
        if not obj.pk:
            obj.approved_by = request.user
        super().save_model(request, obj, form, change)

class CustomUserAdmin(UserAdmin):
    list_display = ('username', 'email', 'first_name', 'last_name', 'get_groups')
    list_filter = ('groups', 'is_active', 'is_staff')
    
    def get_groups(self, obj):
        return ", ".join([group.name for group in obj.groups.all()])
    get_groups.short_description = 'Groups'

@admin.register(ProductStatusHistory)
class ProductStatusHistoryAdmin(admin.ModelAdmin):
    list_display = ['product', 'status', 'created_at', 'updated_by', 'is_active']
    list_filter = ['is_active', 'created_at', 'updated_by']
    search_fields = ['product__job_order', 'status']
    ordering = ['-created_at']
               
    def has_delete_permission(self, request, obj=None):
        return True

admin.site.unregister(User)
admin.site.register(User, CustomUserAdmin)
admin.site.register(Order)
