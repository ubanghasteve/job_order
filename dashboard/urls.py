from django.urls import path
from . import views
from .views import export_products_pdf

urlpatterns = [
    # Dashboard
    path('index/', views.index, name='dashboard-index'),
    
    # Products
    path('products/', views.products, name='dashboard-products'),
    path('products/delete/<int:pk>/', views.product_delete, name='dashboard-products-delete'),
    path('products/detail/<int:pk>/', views.product_detail, name='dashboard-products-detail'),
    path('products/edit/<int:pk>/', views.product_edit, name='dashboard-products-edit'),
    path('products/<int:pk>/', views.product_detail, name='dashboard-products-detail'),
    path('product/<int:product_id>/approve/', views.approve_product, name='approve-product'),
    path('product-view/<str:job_id>/', views.product_view, name='product-view'),
    path('update-production-status/', views.update_production_status, name='update-production-status'),
    
    # Customers
    path('customers/', views.customers, name='dashboard-customers'),
    path('customers/detial/<int:pk>/', views.customer_detail, name='dashboard-customer-detail'),
    
    # Orders
    path('order/', views.order, name='dashboard-order'),
    path('order/edit/<int:pk>/', views.order_edit, name='order-edit'),
    path('order/delete/<int:pk>/', views.order_delete, name='order-delete'),
    
    # Leave Management
    path('apply-leave/', views.apply_leave, name='apply-leave'),
    path('leave-history/', views.leave_history, name='leave-history'),
    path('manage-leaves/', views.manage_leaves, name='manage-leaves'),
    path('update-leave-status/<int:pk>/', views.update_leave_status, name='update-leave-status'),
    path('staff-dashboard/', views.staff_dashboard, name='staff-dashboard'),
    path('admin_leave_dashboard/', views.admin_leave_dashboard, name='admin_leave_dashboard'),
    
    # Export Functions
    path('export-products-pdf/', export_products_pdf, name='export-products-pdf'),
    path('export-orders-pdf/', views.export_products_pdf, name='export-orders-pdf'),
    path('export-single-product/<str:job_id>/', views.export_single_product_pdf, name='export-single-product'),
    path('export-product-view/<str:job_id>/', views.export_product_view_pdf, name='export-product-view-pdf'),
    path('export-leaves-pdf/', views.export_leaves_pdf, name='export-leaves-pdf'),
    path('export-all-leaves-pdf/', views.export_all_leaves_pdf, name='export-all-leaves-pdf'),
    path('delete-status-history/<int:status_id>/', views.delete_status_history, name='delete-status-history'),

    # Export Functions
    
    path('loan/request/', views.loan_request, name='loan-request'),
    path('loans/', views.loan_list, name='loan-list'),
    path('loan/<int:pk>/', views.loan_detail, name='loan-detail'),
    path('loan/<int:pk>/update/', views.loan_update, name='loan-update'),
    path('loan/<int:pk>/delete/', views.loan_delete, name='loan-delete'),
    path('my-loans/', views.my_loans, name='my-loans'),
    path('pending-loans/', views.pending_loans, name='pending-loans'),


]
