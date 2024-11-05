from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.models import User
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.conf import settings
from django.http import HttpResponse, JsonResponse
from django.utils import timezone
from django.db.models.functions import TruncSecond
from zoneinfo import ZoneInfo
from reportlab.pdfgen import canvas
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph
from .models import Product, Order, Leave, ProductStatusHistory, Loan
from .forms import ProductForm, OrderForm,  LeaveForm, LoanForm
from .decorators import auth_users, allowed_users, can_edit_user_data, leave_manager_only
from django.contrib.admin.views.decorators import staff_member_required
from django.core.paginator import Paginator
from django.db.models import Q, Count, Sum, Avg, Min, Max
from reportlab.platypus import Image, Spacer
import os
from django.template.loader import get_template
from xhtml2pdf import pisa
from .forms import LeaveForm, LeaveResponseForm, LeaveUpdateForm, LoanUpdateForm
from django.core.mail import send_mail
from datetime import timedelta
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from .decorators import can_manage_leave
from django.contrib.auth.decorators import permission_required
from django.contrib.auth.decorators import user_passes_test
from django.db.models import Sum, Count
from django.core.exceptions import ValidationError
from django.core.cache import cache


import logging
logger = logging.getLogger(__name__)



wat_timezone = ZoneInfo("Africa/Lagos")


# Add the custom permission check here
def is_staff_member(user):
    return user.is_staff or user.groups.filter(name='Staff').exists()


@login_required(login_url='user-login')
def index(request):
    # Product Statistics
    product = Product.objects.all()
    product_count = product.count()
    
    # Order Statistics
    order = Order.objects.all()
    order_count = order.count()
    
    # User Statistics
    customer = User.objects.filter(groups=2, is_active=True)
    customer_count = customer.count()
    
    # Role-based statistics
    if request.user.is_superuser or request.user.groups.filter(name='Leave Manager').exists():
        # Admin/Manager view
        pending_leaves = Leave.objects.filter(status='Pending').order_by('-applied_date')
        pending_leaves_count = pending_leaves.count()
        staff_count = Leave.objects.all().count()  # Total leave requests for admin view
        
        pending_loans = Loan.objects.filter(status='Pending').order_by('-applied_date')
        pending_loans_count = pending_loans.count()
    else:
        # Regular user view
        pending_leaves = Leave.objects.filter(
            user=request.user,
            status='Pending'
        ).order_by('-applied_date')
        pending_leaves_count = pending_leaves.count()
        staff_count = Leave.objects.filter(user=request.user).count()  # All user's leave requests
        
        pending_loans = Loan.objects.filter(
            user=request.user,
            status='Pending'
        ).order_by('-applied_date')
        pending_loans_count = pending_loans.count()

    context = {
        'product': product,
        'product_count': product_count,
        'order_count': order_count,
        'customer_count': customer_count,
        'staff_count': staff_count,
        'pending_leaves': pending_leaves[:5],
        'pending_leaves_count': pending_leaves_count,
        'pending_loans': pending_loans[:5],
        'pending_loans_count': pending_loans_count,
    }
    
    return render(request, 'dashboard/index.html', context)











@login_required
@permission_required('dashboard.view_product', raise_exception=True)
def products(request):
    # Initialize form with user
    form = ProductForm(user=request.user)
    
    if request.method == 'POST':
        form = ProductForm(request.POST, request.FILES, user=request.user)
        if form.is_valid():
            product = form.save(commit=False)
            product.created_by = request.user
            product.calculate_total()
            
            # Handle image upload
            if 'image' in request.FILES:
                product.image = request.FILES['image']
                
            product.save()
            messages.success(request, f'Job Order {product.job_order} has been added and is pending approval')
            return redirect('dashboard-products')

    # Get search and filter parameters
    search_query = request.GET.get('search', '')
    filter_status = request.GET.get('status', '')
    
    # Base queryset
    products = Product.objects.annotate(
        local_date_created=TruncSecond('date_created', tzinfo=wat_timezone)
    ).order_by('-local_date_created')
    
    # Apply filters if present
    if search_query:
        products = products.filter(
            Q(job_order__icontains=search_query) |
            Q(organization_name__icontains=search_query) |
            Q(job_title__icontains=search_query)
        )
    
    if filter_status:
        products = products.filter(approval_status=filter_status)
    
    # Pagination
    paginator = Paginator(products, 10)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    context = {
        'products': page_obj,
        'form': form,
        'customer_count': User.objects.filter(groups=2).count(),
        'product_count': products.count(),
        'order_count': Order.objects.count(),
    }
    
    return render(request, 'dashboard/products.html', context)



@login_required(login_url='user-login')
@permission_required('dashboard.can_approve_jobs', raise_exception=True)
def approve_product(request, product_id):
    product = get_object_or_404(Product, id=product_id)
    action = request.POST.get('action')
    
    if action in ['approve', 'pending', 'deny']:
        product.approval_status = action
        product.approved_by = request.user
        product.save()
        
        # Log the status change
        ProductStatusHistory.objects.create(
            product=product,
            status=action,
            updated_by=request.user
        )
        
        return JsonResponse({
            'success': True,
            'message': f'Product status updated to {action}'
        })
    
    return JsonResponse({
        'success': False,
        'message': 'Invalid action specified'
    })








@login_required
@permission_required('dashboard.add_product', raise_exception=True)
def product_detail(request, pk):
    product = get_object_or_404(Product, id=pk)
    
    if request.method == 'POST':
        form = ProductForm(
            data=request.POST,
            files=request.FILES,
            instance=product,
            user=request.user
        )
        if form.is_valid():
            # Handle image update
            if 'image' in request.FILES:
                product.image = request.FILES['image']
            elif 'image-clear' in request.POST and not request.FILES.get('image'):
                product.image = None
            
            # Save form and update product
            instance = form.save(commit=False)
            instance.calculate_total()
            instance.calculate_cycle_time()
            instance.save()
            
            messages.success(request, 'Product updated successfully!')
            return redirect('dashboard-products')
    else:
        form = ProductForm(instance=product, user=request.user)

    context = {
        'product': product,
        'form': form,
        'page_title': f'Edit Product: {product.job_order}',
        'can_edit': request.user.has_perm('dashboard.change_product')
    }
    return render(request, 'dashboard/products_detail.html', context)



@login_required(login_url='user-login')
@allowed_users(allowed_roles=['Admin'])
def customers(request):
    customer = User.objects.filter(groups=2)
    customer_count = customer.count()
    product = Product.objects.all()
    product_count = product.count()
    order = Order.objects.all()
    order_count = order.count()
    context = {
        'customer': customer,
        'customer_count': customer_count,
        'product_count': product_count,
        'order_count': order_count,
    }
    return render(request, 'dashboard/customers.html', context)

@login_required(login_url='user-login')
@allowed_users(allowed_roles=['Admin'])
def customer_detail(request, pk):
    customer = User.objects.filter(groups=2)
    customer_count = customer.count()
    product = Product.objects.all()
    product_count = product.count()
    order = Order.objects.all()
    order_count = order.count()
    customers = get_object_or_404(User, id=pk)
    context = {
        'customers': customers,
        'customer_count': customer_count,
        'product_count': product_count,
        'order_count': order_count,
    }
    return render(request, 'dashboard/customers_detail.html', context)

@login_required
@permission_required('dashboard.change_product', raise_exception=True)
def product_edit(request, pk):
    item = get_object_or_404(Product, id=pk)
    if request.method == 'POST':
        form = ProductForm(request.POST, instance=item)
        if form.is_valid():
            form.save()
            return redirect('dashboard-products')
    else:
        form = ProductForm(instance=item)
    context = {
        'form': form,
        'item': item,
        'approval_status': item.approval_status,
    }
    return render(request, 'dashboard/products_edit.html', context)

@login_required
@permission_required('dashboard.delete_product', raise_exception=True)
def product_delete(request, pk):
    item = get_object_or_404(Product, id=pk)
    if request.method == 'POST':
        item.delete()
        return redirect('dashboard-products')
    context = {
        'item': item
    }
    return render(request, 'dashboard/products_delete.html', context)

@login_required
@permission_required('dashboard.view_order', raise_exception=True)
def order(request):
    if request.user.groups.filter(name='Admin').exists():
        order = Order.objects.annotate(local_date_created=TruncSecond('date_created', tzinfo=wat_timezone)).order_by('-local_date_created')
    else:
        order = Order.objects.filter(customer=request.user).annotate(local_date_created=TruncSecond('date_created', tzinfo=wat_timezone)).order_by('-local_date_created')
   
    order_count = order.count()
    customer = User.objects.filter(groups=2)
    customer_count = customer.count()
    product = Product.objects.all()
    product_count = product.count()

    context = {
        'order': order,
        'customer_count': customer_count,
        'product_count': product_count,
        'order_count': order_count,
    }
    return render(request, 'dashboard/order.html', context)

@login_required
@permission_required('dashboard.change_order', raise_exception=True)
def order_edit(request, pk):
    order = get_object_or_404(Order, id=pk)
    if request.method == 'POST':
        form = OrderForm(request.POST, instance=order)
        if form.is_valid():
            form.save()
            return redirect('dashboard-order')
    else:
        form = OrderForm(instance=order)
    context = {
        'form': form,
        'order': order,
    }
    return render(request, 'dashboard/order_edit.html', context)
@login_required
@permission_required('dashboard.delete_order', raise_exception=True)
def order_delete(request, pk):
    order = get_object_or_404(Order, id=pk)
    if request.method == 'POST':
        order.delete()
        return redirect('dashboard-order')
    context = {
        'item': order
    }
    return render(request, 'dashboard/order_delete.html', context)




@login_required
@permission_required('dashboard.can_export_products', raise_exception=True)
def export_products_pdf(request):
    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = 'attachment; filename="products.pdf"'

    doc = SimpleDocTemplate(response, pagesize=landscape(A4), leftMargin=15, rightMargin=15, topMargin=25, bottomMargin=25)
    elements = []

    styles = getSampleStyleSheet()
    title_style = styles['Title']
    title_style.fontSize = 14
    title_style.spaceAfter = 30
    elements.append(Paragraph("City prints Product Records", title_style))

    products = Product.objects.all().order_by('-date_created')
   
    para_style = ParagraphStyle(
        'Normal',
        fontSize=7,
        leading=8,
        wordWrap='CJK',
        alignment=1,
        encoding='utf-8'
    )
   
    header_style = ParagraphStyle(
        'Header',
        fontSize=8,
        leading=9,
        fontName='Helvetica-Bold',
        alignment=1,
        encoding='utf-8'
    )

    headers = ['S/N', 'Date', 'Job Order Number', 'Job Name', 'Address', 'Contact', 'Package type/ Product', 'Colors', 
              'Cutting/ Pouching', 'Thickness / Width', 'Sealing Type', 'Delivery qty', 'Price (NGN)', 'Qty (Kg)', 'Total (NGN)', 
              'Est. Del', 'Act. Del', 'Cycle Time', 'Sub ID', 'Status', 'Created By', 'Approved By', 'Production Status']
    
   
    data = [[Paragraph(header, header_style) for header in headers]]

    for index, product in enumerate(products, start=1):
        price = str(product.formatted_price()).replace('₦', 'NGN ')
        total = str(product.formatted_total()).replace('₦', 'NGN ')
       
        row_data = [
            str(index),
            product.date_created.strftime('%d/%m/%y') if product.date_created else '',
            Paragraph(str(product.job_order), para_style),
            Paragraph(str(product.organization_name), para_style),
            Paragraph(str(product.address), para_style),
            Paragraph(str(product.contact_number), para_style),
            Paragraph(str(product.print_product), para_style),
            Paragraph(str(product.colors), para_style),
            Paragraph(str(product.order_info), para_style),
            Paragraph(str(product.size), para_style),
            Paragraph(str(product.micron), para_style),
            Paragraph(str(product.job_title), para_style),
            Paragraph(price, para_style),
            str(product.order_quantity),
            Paragraph(total, para_style),
            product.estimated_delivery_date.strftime('%d/%m/%y') if product.estimated_delivery_date else '',
            product.actual_delivery_date.strftime('%d/%m/%y') if product.actual_delivery_date else '',
            Paragraph(str(product.cycle_time), para_style) if product.cycle_time else '',
            Paragraph(str(product.submission_id), para_style),
            Paragraph(str(product.approval_status), para_style),
            Paragraph(str(product.created_by.username), para_style) if product.created_by else '',
            Paragraph(str(product.approved_by.username), para_style) if product.approved_by else '',
            Paragraph(str(product.production_status), para_style) if product.production_status else ''
        ]
        data.append(row_data)

    col_widths = [
        0.2*inch,   # S/N
        0.4*inch,   # Date
        0.4*inch,   # Job Order
        0.7*inch,   # Organization
        0.7*inch,   # Address
        0.5*inch,   # Contact
        0.6*inch,   # Package type/ Product
        0.4*inch,   # Colors
        0.6*inch,   # Cutting/ Pouch Bag
        0.35*inch,  # Printing Substrate/ Micron
        0.35*inch,  # Sealing Type
        0.5*inch,   # Job Title
        0.45*inch,  # Price
        0.3*inch,   # Qty
        0.45*inch,  # Total
        0.4*inch,   # Est. Del
        0.4*inch,   # Act. Del
        0.4*inch,   # Cycle Time
        0.4*inch,   # Sub ID
        0.4*inch,   # Status
        0.45*inch,  # Created By
        0.45*inch,  # Approved By
        0.6*inch    # Production Status
    ]

    table_style = TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 8),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('LEFTPADDING', (0, 0), (-1, -1), 3),
        ('RIGHTPADDING', (0, 0), (-1, -1), 3),
        ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
        ('TEXTCOLOR', (0, 1), (-1, -1), colors.black),
        ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 1), (-1, -1), 7),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ])

    table = Table(data, repeatRows=1, colWidths=col_widths)
    table.setStyle(table_style)
    elements.append(table)
   
    doc.build(elements)
    return response



@login_required(login_url='user-login')
def export_single_product_pdf(request, job_id):
    from reportlab.platypus import Image, Spacer
    import os
    
    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="job_order_{job_id}.pdf"'

    doc = SimpleDocTemplate(response, pagesize=landscape(A4), leftMargin=15, rightMargin=15, topMargin=25, bottomMargin=25)
    elements = []

    styles = getSampleStyleSheet()
    title_style = styles['Title']
    title_style.fontSize = 14
    title_style.spaceAfter = 30
    elements.append(Paragraph(f"City prints Job Order #{job_id}", title_style))

    product = get_object_or_404(Product, job_order=job_id)

    if product.image:
        try:
            img_path = product.image.path
            img = Image(img_path, width=4*inch, height=3*inch)
            elements.append(img)
            elements.append(Spacer(1, 12))
        except Exception as e:
            print(f"Error loading image: {e}")

    para_style = ParagraphStyle(
        'Normal',
        fontSize=7,
        leading=8,
        wordWrap='CJK',
        alignment=1,
        encoding='utf-8'
    )
    
    header_style = ParagraphStyle(
        'Header',
        fontSize=8,
        leading=9,
        fontName='Helvetica-Bold',
        alignment=1,
        encoding='utf-8'
    )

    headers = ['S/N', 'Date', 'Job Order Number', 'Job Name', 'Address', 'Contact', 'Package type/ Product', 'Colors', 
              'Cutting/ Pouching', 'Thickness / Width', 'Sealing Type', 'Delivery qty', 'Price (NGN)', 'Qty (Kg)', 'Total (NGN)', 
              'Est. Del', 'Act. Del', 'Cycle Time', 'Sub ID', 'Status', 'Created By', 'Approved By', 'Production Status']
    
    data = [[Paragraph(header, header_style) for header in headers]]

    price = str(product.formatted_price()).replace('₦', 'NGN ')
    total = str(product.formatted_total()).replace('₦', 'NGN ')
    
    row_data = [
        '1',
        product.date_created.strftime('%d/%m/%y') if product.date_created else '',
        Paragraph(str(product.job_order), para_style),
        Paragraph(str(product.organization_name), para_style),
        Paragraph(str(product.address), para_style),
        Paragraph(str(product.contact_number), para_style),
        Paragraph(str(product.print_product), para_style),
        Paragraph(str(product.colors), para_style),
        Paragraph(str(product.order_info), para_style),
        Paragraph(str(product.size), para_style),
        Paragraph(str(product.micron), para_style),
        Paragraph(str(product.job_title), para_style),
        Paragraph(price, para_style),
        str(product.order_quantity),
        Paragraph(total, para_style),
        product.estimated_delivery_date.strftime('%d/%m/%y') if product.estimated_delivery_date else '',
        product.actual_delivery_date.strftime('%d/%m/%y') if product.actual_delivery_date else '',
        Paragraph(str(product.cycle_time), para_style) if product.cycle_time else '',
        Paragraph(str(product.submission_id), para_style),
        Paragraph(str(product.approval_status), para_style),
        Paragraph(str(product.created_by.username), para_style) if product.created_by else '',
        Paragraph(str(product.approved_by.username), para_style) if product.approved_by else ''
    ]
    data.append(row_data)

    col_widths = [
        0.2*inch,   # S/N
        0.4*inch,   # Date
        0.4*inch,   # Job Order
        0.7*inch,   # Organization
        0.7*inch,   # Address
        0.5*inch,   # Contact
        0.6*inch,   # Package type/ Product
        0.4*inch,   # Colors
        0.6*inch,   # Cutting/ Pouch Bag
        0.35*inch,  # Printing Substrate/ Micron
        0.35*inch,  # Sealing Type
        0.5*inch,   # Job Title
        0.45*inch,  # Price
        0.3*inch,   # Qty
        0.45*inch,  # Total
        0.4*inch,   # Est. Del
        0.4*inch,   # Act. Del
        0.4*inch,   # Cycle Time
        0.4*inch,   # Sub ID
        0.4*inch,   # Status
        0.45*inch,  # Created By
        0.45*inch,  # Approved By
        0.6*inch    # Production Status
    ]

    table_style = TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 8),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('LEFTPADDING', (0, 0), (-1, -1), 3),
        ('RIGHTPADDING', (0, 0), (-1, -1), 3),
        ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
        ('TEXTCOLOR', (0, 1), (-1, -1), colors.black),
        ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 1), (-1, -1), 7),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ])

    table = Table(data, repeatRows=1, colWidths=col_widths)
    table.setStyle(table_style)
    elements.append(table)
    
    doc.build(elements)
    return response


@login_required(login_url='user-login')
def product_view(request, job_id):
    product = get_object_or_404(Product, job_order=job_id)
    
    if request.method == 'POST':
        new_status = request.POST.get('production_status')
        if new_status:
            # Update main product status
            product.production_status = new_status
            product.production_status_date = timezone.now()
            product.updated_by = request.user
            product.save()
            
            # Create new status history entry         
            ProductStatusHistory.objects.create(
                product=product,
                status=new_status,
                updated_by=request.user
            )
            
            messages.success(request, 'Production status updated successfully!')
            return redirect('product-view', job_id=job_id)

    form = ProductForm(instance=product)
    
    # Get status history for display
    status_history = product.status_history.all().select_related('updated_by').order_by('-created_at')
    
    context = {
        'product': product,
        'form': form,
        'status_history': status_history
    }
    return render(request, 'dashboard/product_view.html', context)


@require_http_methods(["POST"])
@login_required(login_url='user-login')
def delete_status_history(request, status_id):
    try:
        status = ProductStatusHistory.objects.get(id=status_id)
        product = status.product
        status.delete()
        
        # Get latest status after deletion
        latest_status = ProductStatusHistory.objects.filter(
            product=product
        ).order_by('-created_at').first()
        
        if latest_status:
            product.production_status = latest_status.status
            product.production_status_date = latest_status.created_at
        else:
            product.production_status = None
            product.production_status_date = None
            
        product.save()
        
        return JsonResponse({
            'success': True,
            'message': 'Status deleted successfully'
        })
    except ProductStatusHistory.DoesNotExist:
        return JsonResponse({
            'success': False,
            'message': 'Status not found'
        }, status=404)
    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': str(e)
        }, status=500)



@login_required
def update_production_status(request):
    if request.method == 'POST':
        product_id = request.POST.get('product_id')
        status = request.POST.get('status')
        try:
            product = Product.objects.get(id=product_id)
            product.production_status = status
            product.updated_by = request.user
            product.production_status_date = timezone.now()
            product.save()
            
            print(f"Debug - Updated by: {request.user.username}")  # Debug line
            
            return JsonResponse({
                'status': 'success',
                'date': timezone.localtime(product.production_status_date).strftime("%Y-%m-%d %H:%M:%S"),
                'updated_by': request.user.username
            })
        except Product.DoesNotExist:
            return JsonResponse({'status': 'error'}, status=404)
    return JsonResponse({'status': 'error'}, status=400)






def export_product_view_pdf(request, job_id):
    product = get_object_or_404(Product, job_order=job_id)
    template_path = 'dashboard/product_view_pdf.html'
    
    context = {
        'product': product,
        'image_url': request.build_absolute_uri(product.image.url) if product.image else None,
        'base_url': request.build_absolute_uri('/')
    }
    
    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="{product.job_order}_details.pdf"'
    
    template = get_template(template_path)
    html = template.render(context)
    
    pisa_status = pisa.CreatePDF(
        html, 
        dest=response,
        link_callback=fetch_resources,
        encoding='utf-8'
    )
    
    return response if not pisa_status.err else HttpResponse('PDF generation error')

def fetch_resources(uri, rel):
    """
    Convert HTML URIs to absolute system paths for PDF generation
    """
    if uri.startswith(settings.MEDIA_URL):
        path = os.path.join(settings.MEDIA_ROOT, uri.replace(settings.MEDIA_URL, ""))
    elif uri.startswith(settings.STATIC_URL):
        path = os.path.join(settings.STATIC_ROOT, uri.replace(settings.STATIC_URL, ""))
    elif uri.startswith("http://") or uri.startswith("https://"):
        path = uri
    else:
        path = os.path.join(settings.STATIC_ROOT, uri)

    return path


@login_required
@permission_required('dashboard.can_export_products', raise_exception=True)
def export_leaves_pdf(request):
    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = 'attachment; filename="leave_history.pdf"'

    doc = SimpleDocTemplate(response, pagesize=landscape(A4), leftMargin=15, rightMargin=15, topMargin=25, bottomMargin=25)
    elements = []

    styles = getSampleStyleSheet()
    title_style = styles['Title']
    title_style.fontSize = 14
    title_style.spaceAfter = 30
    elements.append(Paragraph("Leave History Report", title_style))

    leaves = Leave.objects.filter(user=request.user).order_by('-applied_date')
   
    headers = ['Leave Type', 'Start Date', 'End Date', 'Status', 'Applied Date']
    data = [[leave.leave_type, leave.start_date, leave.end_date, leave.status, leave.applied_date.strftime('%Y-%m-%d')] 
            for leave in leaves]
    
    data.insert(0, headers)
    table = Table(data)
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 14),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
        ('TEXTCOLOR', (0, 1), (-1, -1), colors.black),
        ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 1), (-1, -1), 12),
        ('GRID', (0, 0), (-1, -1), 1, colors.black)
    ]))
    
    elements.append(table)
    doc.build(elements)
    return response


@login_required(login_url='user-login')
@allowed_users(allowed_roles=['Admin'])
def export_all_leaves_pdf(request):
    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = 'attachment; filename="all_leaves.pdf"'

    doc = SimpleDocTemplate(response, pagesize=landscape(A4), leftMargin=15, rightMargin=15, topMargin=25, bottomMargin=25)
    elements = []

    styles = getSampleStyleSheet()
    title_style = styles['Title']
    title_style.fontSize = 14
    title_style.spaceAfter = 30
    elements.append(Paragraph("All Leave Requests Report", title_style))

    leaves = Leave.objects.all().order_by('-applied_date')
   
    headers = ['Staff', 'Leave Type', 'Start Date', 'End Date', 'Status', 'Applied Date', 'Approved By']
    data = [[
        leave.user.username,
        leave.leave_type,
        leave.start_date,
        leave.end_date,
        leave.status,
        leave.applied_date.strftime('%Y-%m-%d'),
        leave.approved_by.username if leave.approved_by else '-'
    ] for leave in leaves]
    
    data.insert(0, headers)
    table = Table(data)
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 12),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
        ('TEXTCOLOR', (0, 1), (-1, -1), colors.black),
        ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 1), (-1, -1), 10),
        ('GRID', (0, 0), (-1, -1), 1, colors.black)
    ]))
    
    elements.append(table)
    doc.build(elements)
    return response


@login_required
@permission_required('dashboard.view_leave', raise_exception=True)
def leave_history(request):
    leaves = Leave.objects.filter(user=request.user)
    
    # Filter by date range
    start_date = request.GET.get('start_date')
    end_date = request.GET.get('end_date')
    status = request.GET.get('status')
    leave_type = request.GET.get('leave_type')

    if start_date:
        leaves = leaves.filter(start_date__gte=start_date)
    if end_date:
        leaves = leaves.filter(end_date__lte=end_date)
    if status:
        leaves = leaves.filter(status=status)
    if leave_type:
        leaves = leaves.filter(leave_type=leave_type)

    context = {
        'leaves': leaves,
        'statuses': Leave.STATUS,
        'leave_types': Leave.LEAVE_TYPES,
    }
    return render(request, 'dashboard/leave_history.html', context)



@login_required(login_url='user-login')
@allowed_users(allowed_roles=['Admin'])
def manage_leaves(request):
    leaves_list = Leave.objects.all().order_by('-applied_date')
    
    # Get filter parameters
    start_date = request.GET.get('start_date')
    end_date = request.GET.get('end_date')
    leave_type = request.GET.get('leave_type')
    status = request.GET.get('status')
    query = request.GET.get('q')
    
    # Apply filters
    if start_date:
        leaves_list = leaves_list.filter(start_date__gte=start_date)
    if end_date:
        leaves_list = leaves_list.filter(end_date__lte=end_date)
    if leave_type:
        leaves_list = leaves_list.filter(leave_type=leave_type)
    if status:
        leaves_list = leaves_list.filter(status=status)
    if query:
        leaves_list = leaves_list.filter(
            Q(user__username__icontains=query) |
            Q(reason__icontains=query)
        )
    
    # Pagination
    paginator = Paginator(leaves_list, 10)
    page = request.GET.get('page')
    leaves = paginator.get_page(page)
    
    # Get choices for dropdowns
    leave_types = Leave.LEAVE_TYPES
    statuses = Leave.STATUS
    
    context = {
        'leaves': leaves,
        'leave_types': leave_types,
        'statuses': statuses,
    }
    return render(request, 'dashboard/manage_leaves.html', context)


@login_required
@permission_required('dashboard.add_leave', raise_exception=True)
def apply_leave(request):
    if request.method == 'POST':
        form = LeaveForm(request.POST)
        if form.is_valid():
            leave = form.save(commit=False)
            leave.user = request.user
            leave.save()
            messages.success(request, 'Leave request submitted successfully')
            return redirect('leave-history')
    else:
        form = LeaveForm()
    
    context = {'form': form}
    return render(request, 'dashboard/apply_leave.html', context)

@login_required(login_url='user-login')
def leave_history(request):
    leaves = Leave.objects.filter(user=request.user).order_by('-applied_date')
    context = {'leaves': leaves}
    return render(request, 'dashboard/leave_history.html', context)


@login_required
@permission_required('dashboard.add_leave', raise_exception=True)
def manage_leaves(request):
    # Get search query
    query = request.GET.get('q', '')
    
    # Filter leaves based on search
    leaves_list = Leave.objects.all().order_by('-applied_date')
    if query:
        leaves_list = leaves_list.filter(
            Q(user__username__icontains=query) |
            Q(leave_type__icontains=query) |
            Q(status__icontains=query) |
            Q(reason__icontains=query)
        )
    
    # Pagination
    paginator = Paginator(leaves_list, 10)  # Show 10 items per page
    page = request.GET.get('page')
    leaves = paginator.get_page(page)
    
    context = {
        'leaves': leaves,
        'query': query,
    }
    return render(request, 'dashboard/manage_leaves.html', context)


@login_required
@permission_required('dashboard.add_leave', raise_exception=True)
def update_leave_status(request, pk):
    leave_request = Leave.objects.get(id=pk)
    if request.method == 'POST':
        form = LeaveUpdateForm(request.POST, instance=leave_request)
        if form.is_valid():
            leave = form.save(commit=False)
            leave.approved_by = request.user
            leave.save()
            messages.success(request, 'Leave status updated successfully')
            return redirect('manage-leaves')
    else:
        form = LeaveUpdateForm(instance=leave_request)
    return render(request, 'dashboard/update_leave_status.html', {'form': form, 'leave': leave_request})


def send_leave_notification(leave_request):
    if leave_request.status == 'Approved':
        subject = 'Leave Request Approved'
        message = f'Your {leave_request.leave_type} leave request from {leave_request.start_date} to {leave_request.end_date} has been approved.'
    elif leave_request.status == 'Rejected':
        subject = 'Leave Request Rejected'
        message = f'Your {leave_request.leave_type} leave request from {leave_request.start_date} to {leave_request.end_date} has been rejected.'
    
    send_mail(
        subject,
        message,
        settings.EMAIL_HOST_USER,
        [leave_request.user.email],
        fail_silently=False,
    )


@login_required(login_url='user-login')
@user_passes_test(is_staff_member)
def staff_dashboard(request):
    user_leaves = Leave.objects.filter(user=request.user)
    pending_leaves = user_leaves.filter(status='Pending').count()
    approved_leaves = user_leaves.filter(status='Approved').count()
    rejected_leaves = user_leaves.filter(status='Rejected').count()
    
    context = {
        'pending_leaves': pending_leaves,
        'approved_leaves': approved_leaves,
        'rejected_leaves': rejected_leaves,
        'recent_leaves': user_leaves.order_by('-applied_date')[:5]
    }
    return render(request, 'dashboard/staff_dashboard.html', context)



@login_required
@permission_required('dashboard.view_dashboard', raise_exception=True)
def admin_leave_dashboard(request):
    # Get user statistics with role-based filtering
    total_staff = User.objects.filter(is_active=True).count()
    staff_on_leave = User.objects.filter(leave__status='Approved', 
                                       leave__start_date__lte=timezone.now(),
                                       leave__end_date__gte=timezone.now()).distinct().count()
    
    # Get leave statistics with optimized queries
    total_leaves = Leave.objects.select_related('user').all()
    pending_leaves = total_leaves.filter(status='Pending')
    approved_leaves = total_leaves.filter(status='Approved')
    rejected_leaves = total_leaves.filter(status='Rejected')
    
    # Calculate monthly statistics
    current_month = timezone.now().month
    monthly_leaves = total_leaves.filter(applied_date__month=current_month)
    
    # Calculate leave types distribution
    leave_by_type = {
        'Annual': total_leaves.filter(leave_type='Annual').count(),
        'Sick': total_leaves.filter(leave_type='Sick').count(),
        'Personal': total_leaves.filter(leave_type='Personal').count(),
        'Maternity': total_leaves.filter(leave_type='Maternity').count(),
        'Paternity': total_leaves.filter(leave_type='Paternity').count(),
        'Parental': total_leaves.filter(leave_type='Parental').count(),
        'Bereavement': total_leaves.filter(leave_type='Bereavement').count(),
        'Compassionate': total_leaves.filter(leave_type='Compassionate').count(),
        'Study': total_leaves.filter(leave_type='Study').count(),
        'Sabbatical': total_leaves.filter(leave_type='Sabbatical').count(),
        'Unpaid': total_leaves.filter(leave_type='Unpaid').count(),
        'Jury Duty': total_leaves.filter(leave_type='Jury Duty').count(),
        'Military': total_leaves.filter(leave_type='Military').count(),
        'Public Service': total_leaves.filter(leave_type='Public Service').count(),
        'Religious': total_leaves.filter(leave_type='Religious').count(),
        'Casual': total_leaves.filter(leave_type='Casual').count(),
        'Compensatory': total_leaves.filter(leave_type='Compensatory').count(),
        'Medical': total_leaves.filter(leave_type='Medical').count(),
        'Marriage': total_leaves.filter(leave_type='Marriage').count(),
        'Voting': total_leaves.filter(leave_type='Voting').count(),
        'Emergency': total_leaves.filter(leave_type='Emergency').count(),
        'Other': total_leaves.filter(leave_type='Other').count(),
    }

    
    # Get recent leave requests with user details
    recent_requests = pending_leaves.select_related('user').order_by('-applied_date')[:5]
    
    # Calculate department-wise leave statistics
    department_stats = total_leaves.values('user__dashboard_profile__department')\
        .annotate(total=Count('id'))\
        .order_by('-total')
    
    context = {
        # Staff Statistics
        'total_staff': total_staff,
        'staff_on_leave': staff_on_leave,
        'available_staff': total_staff - staff_on_leave,
        
        # Leave Counts
        'total_leaves': total_leaves.count(),
        'pending_leaves': pending_leaves.count(),
        'approved_leaves': approved_leaves.count(),
        'rejected_leaves': rejected_leaves.count(),
        
        # Monthly Statistics
        'monthly_leaves': monthly_leaves.count(),
        'monthly_approved': monthly_leaves.filter(status='Approved').count(),
        'monthly_rejected': monthly_leaves.filter(status='Rejected').count(),
        
        # Distribution and Analysis
        'leave_by_type': leave_by_type,
        'department_stats': department_stats,
        'recent_requests': recent_requests,
        
        # Metrics
        'leave_approval_rate': round((approved_leaves.count() / total_leaves.count() * 100), 2) 
                              if total_leaves.count() > 0 else 0,
        'average_response_time': calculate_average_response_time(total_leaves),
    }
    
    return render(request, 'dashboard/admin_leave_dashboard.html', context)

def calculate_average_response_time(leaves):
    responded_leaves = leaves.exclude(status='Pending')\
                           .exclude(response_date__isnull=True)
    
    if not responded_leaves:
        return 0
        
    total_response_time = sum(
        (leave.response_date - leave.applied_date).days 
        for leave in responded_leaves
    )
    return round(total_response_time / responded_leaves.count(), 1)


@login_required(login_url='user-login')
@leave_manager_only
def leave_dashboard(request):
    total_users = User.objects.count()
    pending_leaves = Leave.objects.filter(status='Pending').count()
    approved_leaves = Leave.objects.filter(status='Approved').count()
    rejected_leaves = Leave.objects.filter(status='Rejected').count()
    
    context = {
        'total_users': total_users,
        'pending_leaves': pending_leaves,
        'approved_leaves': approved_leaves,
        'rejected_leaves': rejected_leaves,
    }
    return render(request, 'dashboard/leave_dashboard.html', context)



def process_leave(request, leave_id):
    leave = get_object_or_404(Leave, id=leave_id)
    if request.method == 'POST':
        form = LeaveResponseForm(request.POST, instance=leave)
        if form.is_valid():
            form.save()
            return redirect('leave_list')
    else:
        form = LeaveResponseForm(instance=leave)
    return render(request, 'process_leave.html', {'form': form, 'leave': leave})

        

def user_dashboard(request):
    recent_leaves = Leave.objects.filter(user=request.user).order_by('-created_at')
    return render(request, 'user_dashboard.html', {'recent_leaves': recent_leaves})














@login_required(login_url='user-login')
def loan_request(request):
    if request.method == 'POST':
        form = LoanForm(request.POST)
        if form.is_valid():
            loan = form.save(commit=False)
            loan.user = request.user
            loan.applied_date = timezone.now()
            loan.save()
            logger.info(f"Loan request created by {request.user.username} - ID: {loan.id}")
            messages.success(request, 'Your loan application has been submitted successfully')
            return redirect('loan-list')
    else:
        form = LoanForm()
    context = {
        'form': form,
        'title': 'Request Loan'
    }
    return render(request, 'dashboard/loan_form.html', context)


@login_required(login_url='user-login')
def loan_list(request):
    if request.user.is_superuser or request.user.groups.filter(name='Finance').exists():
        loans = Loan.objects.all().select_related('user', 'approved_by').order_by('id')
    else:
        loans = Loan.objects.filter(user=request.user).select_related('user', 'approved_by').order_by('id')
    
    context = {
        'loans': loans,
        'title': 'Loan Applications'
    }
    return render(request, 'dashboard/loan_list.html', context)




@login_required(login_url='user-login')
def loan_detail(request, pk):
    loan = get_object_or_404(Loan, id=pk)
    
    # Check if user has permission to view this loan
    if not (request.user == loan.user or 
            request.user.is_superuser or 
            request.user.groups.filter(name='Finance').exists()):
        messages.error(request, 'You do not have permission to view this loan.')
        return redirect('loan-list')

    if request.method == 'POST' and (request.user.is_superuser or 
                                   request.user.groups.filter(name='Finance').exists()):
        status = request.POST.get('status')
        response_message = request.POST.get('response_message')
        
        loan.status = status
        loan.response_message = response_message
        loan.response_date = timezone.now()
        loan.approved_by = request.user
        loan.save()
        
        messages.success(request, f'Loan application has been {status}')
        return redirect('loan-list')
    
    context = {
        'loan': loan,
        'title': 'Loan Detail'
    }
    return render(request, 'dashboard/loan_detail.html', context)







@login_required
def loan_update(request, pk):
    loan = Loan.objects.get(id=pk)
    if request.user != loan.user and not request.user.groups.filter(name__in=['Superuser', 'Finance']).exists():
        messages.error(request, 'You are not authorized to update this loan application')
        return redirect('loan-list')
    
    if request.method == 'POST':
        form = LoanForm(request.POST, instance=loan)
        if form.is_valid():
            form.save()
            messages.success(request, 'Loan application updated successfully')
            return redirect('loan-list')
    else:
        form = LoanForm(instance=loan)
    
    context = {
        'form': form,
        'title': 'Update Loan'
    }
    return render(request, 'dashboard/loan_form.html', context)



@login_required
def loan_delete(request, pk):
    loan = get_object_or_404(Loan, id=pk)
    
    # Allow both superusers and Finance group members to delete loans
    if request.user.is_superuser or request.user.groups.filter(name='Finance').exists():
        if request.method == 'POST':
            loan.delete()
            messages.success(request, 'Loan application deleted successfully')
            return redirect('loan-list')
            
        context = {
            'loan': loan,
            'title': 'Delete Loan'
        }
        return render(request, 'dashboard/loan_delete.html', context)
    
    return redirect('dashboard-index')





def my_loans(request):
    loans = Loan.objects.filter(user=request.user)
    
    context = {
        'loans': loans,
        'title': 'My Loans',
        'total_loans': loans.count(),
        'pending_loans': loans.filter(status='Pending').count(),
        'approved_loans': loans.filter(status='Approved').count(),
        'rejected_loans': loans.filter(status='Rejected').count(),
    }
    
    return render(request, 'dashboard/my_loans.html', context)





@login_required
@user_passes_test(lambda u: u.is_superuser or u.groups.filter(name='Finance Manager').exists())
def pending_loans(request):
    loans = Loan.objects.filter(status='Pending').order_by('-applied_date')
    context = {
        'loans': loans,
        'title': 'Pending Loans'
    }
    return render(request, 'dashboard/pending_loans.html', context)









@login_required(login_url='user-login')
@permission_required(['dashboard.view_loan', 'dashboard.change_loan'], raise_exception=True)
def admin_loan_dashboard(request):
    # Cache key for dashboard statistics
    cache_key = f'loan_dashboard_stats_{request.user.id}'
    cached_stats = cache.get(cache_key)

    if cached_stats:
        return render(request, 'dashboard/admin_loan_dashboard.html', cached_stats)

    # Optimize queries with select_related and prefetch_related
    total_loans = Loan.objects.select_related('user', 'approved_by')\
                             .prefetch_related('user__groups', 'user__dashboard_profile')

    # Get user statistics with role-based filtering
    total_staff = User.objects.filter(is_active=True).count()
    current_time = timezone.now()
    staff_with_loans = User.objects.filter(
        loan__status='Approved',
        loan__start_date__lte=current_time,
        loan__end_date__gte=current_time
    ).distinct().count()

    # Get loan statistics with optimized queries
    pending_loans = total_loans.filter(status='Pending')
    approved_loans = total_loans.filter(status='Approved')
    rejected_loans = total_loans.filter(status='Rejected')

    # Calculate monthly and yearly statistics
    current_month = current_time.month
    current_year = current_time.year
    monthly_loans = total_loans.filter(
        applied_date__month=current_month,
        applied_date__year=current_year
    )

    # Calculate loan types distribution using annotation
    loan_types = dict(Loan.LOAN_TYPES)
    loan_by_type = {
        loan_type: total_loans.filter(loan_type=loan_type).count()
        for loan_type, _ in loan_types.items()
    }

    # Calculate financial metrics
    loan_amounts = total_loans.aggregate(
        total=Sum('amount'),
        approved=Sum('amount', filter=Q(status='Approved')),
        pending=Sum('amount', filter=Q(status='Pending'))
    )

    # Calculate department statistics with annotations
    department_stats = total_loans.values('user__dashboard_profile__department')\
        .annotate(
            total=Count('id'),
            total_amount=Sum('amount'),
            approved_count=Count('id', filter=Q(status='Approved'))
        ).order_by('-total')

    # Get recent loan requests with user details
    recent_requests = pending_loans.select_related('user')\
        .order_by('-applied_date')[:5]

    context = {
        # Staff Statistics
        'total_staff': total_staff,
        'staff_with_loans': staff_with_loans,
        'available_staff': total_staff - staff_with_loans,

        # Loan Counts
        'total_loans': total_loans.count(),
        'pending_loans': pending_loans.count(),
        'approved_loans': approved_loans.count(),
        'rejected_loans': rejected_loans.count(),

        # Monthly Statistics
        'monthly_loans': monthly_loans.count(),
        'monthly_approved': monthly_loans.filter(status='Approved').count(),
        'monthly_rejected': monthly_loans.filter(status='Rejected').count(),

        # Distribution and Analysis
        'loan_by_type': loan_by_type,
        'department_stats': department_stats,
        'recent_requests': recent_requests,

        # Financial Metrics
        'total_loan_amount': loan_amounts.get('total') or 0,
        'approved_loan_amount': loan_amounts.get('approved') or 0,
        'pending_loan_amount': loan_amounts.get('pending') or 0,

        # Performance Metrics
        'loan_approval_rate': calculate_loan_approval_rate(total_loans),
        'average_response_time': calculate_average_response_time(total_loans),
        
        # Additional Metrics
        'current_month': current_time.strftime('%B %Y'),
        'loan_types': loan_types,
    }

    # Cache the statistics for 1 hour
    cache.set(cache_key, context, 3600)

    return render(request, 'dashboard/admin_loan_dashboard.html', context)

def calculate_loan_approval_rate(loans):
    total_count = loans.count()
    if total_count == 0:
        return 0
    approved_count = loans.filter(status='Approved').count()
    return round((approved_count / total_count * 100), 2)





@login_required(login_url='user-login')
@permission_required('dashboard.view_loan', raise_exception=True)
def export_loans_pdf(request):
    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = 'attachment; filename="loan_history.pdf"'

    doc = SimpleDocTemplate(response, pagesize=landscape(A4), leftMargin=15, rightMargin=15, topMargin=25, bottomMargin=25)
    elements = []

    styles = getSampleStyleSheet()
    title_style = styles['Title']
    title_style.fontSize = 14
    title_style.spaceAfter = 30
    elements.append(Paragraph("Loan History Report", title_style))

    loans = Loan.objects.filter(user=request.user).order_by('-applied_date')
    
    headers = ['Loan Type', 'Amount', 'Start Date', 'End Date', 'Status', 'Applied Date']
    data = [[loan.loan_type, f"${loan.amount}", loan.start_date, loan.end_date, 
             loan.status, loan.applied_date.strftime('%Y-%m-%d')] for loan in loans]
    
    data.insert(0, headers)
    table = Table(data)
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 14),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
        ('TEXTCOLOR', (0, 1), (-1, -1), colors.black),
        ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 1), (-1, -1), 12),
        ('GRID', (0, 0), (-1, -1), 1, colors.black)
    ]))
    
    elements.append(table)
    doc.build(elements)
    return response

@login_required(login_url='user-login')
@permission_required(['dashboard.view_loan', 'dashboard.change_loan'], raise_exception=True)
def export_all_loans_pdf(request):
    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = 'attachment; filename="all_loans.pdf"'

    doc = SimpleDocTemplate(response, pagesize=landscape(A4), leftMargin=15, rightMargin=15, topMargin=25, bottomMargin=25)
    elements = []

    styles = getSampleStyleSheet()
    title_style = styles['Title']
    title_style.fontSize = 14
    title_style.spaceAfter = 30
    elements.append(Paragraph("All Loan Applications Report", title_style))

    loans = Loan.objects.all().order_by('-applied_date')
    
    headers = ['Staff', 'Loan Type', 'Amount', 'Start Date', 'End Date', 'Status', 'Applied Date', 'Approved By']
    data = [[
        loan.user.username,
        loan.loan_type,
        f"${loan.amount}",
        loan.start_date,
        loan.end_date,
        loan.status,
        loan.applied_date.strftime('%Y-%m-%d'),
        loan.approved_by.username if loan.approved_by else '-'
    ] for loan in loans]
    
    data.insert(0, headers)
    table = Table(data)
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 12),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
        ('TEXTCOLOR', (0, 1), (-1, -1), colors.black),
        ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 1), (-1, -1), 10),
        ('GRID', (0, 0), (-1, -1), 1, colors.black)
    ]))
    
    elements.append(table)
    doc.build(elements)
    return response

@login_required(login_url='user-login')
@permission_required('dashboard.view_loan', raise_exception=True)
def loan_history(request):
    loans = Loan.objects.filter(user=request.user)
    
    # Filter by date range
    start_date = request.GET.get('start_date')
    end_date = request.GET.get('end_date')
    status = request.GET.get('status')
    loan_type = request.GET.get('loan_type')

    if start_date:
        loans = loans.filter(start_date__gte=start_date)
    if end_date:
        loans = loans.filter(end_date__lte=end_date)
    if status:
        loans = loans.filter(status=status)
    if loan_type:
        loans = loans.filter(loan_type=loan_type)

    context = {
        'loans': loans,
        'statuses': Loan.STATUS,
        'loan_types': Loan.LOAN_TYPES,
    }
    return render(request, 'dashboard/loan_history.html', context)






@login_required(login_url='user-login')
@permission_required('dashboard.view_loan', raise_exception=True)
def manage_loans(request):
    loans_list = Loan.objects.all().order_by('-applied_date')
    loans = Loan.objects.all()
    search_query = request.GET.get('search')
    
    # Get filter parameters
    start_date = request.GET.get('start_date')
    end_date = request.GET.get('end_date')
    loan_type = request.GET.get('loan_type')
    status = request.GET.get('status')
    query = request.GET.get('q')
    
    # Apply filters
    if start_date:
        loans_list = loans_list.filter(start_date__gte=start_date)
    if end_date:
        loans_list = loans_list.filter(end_date__lte=end_date)
    if loan_type:
        loans_list = loans_list.filter(loan_type=loan_type)
    if status:
        loans_list = loans_list.filter(status=status)
    if query:
        loans_list = loans_list.filter(
            Q(user__username__icontains=query) |
            Q(reason__icontains=query)
        )
        
    if search_query:
        loans = loans.filter(
            Q(user__username__icontains=search_query) |
            Q(loan_type__icontains=search_query) |
            Q(reason__icontains=search_query)
        )
    
    # Pagination
    paginator = Paginator(loans_list, 10)
    page = request.GET.get('page')
    loans = paginator.get_page(page)
    
    context = {
        'loans': loans,
        'loan_types': Loan.LOAN_TYPES,
        'statuses': Loan.STATUS,
    }
    return render(request, 'dashboard/manage_loans.html', context)



@login_required(login_url='user-login')
@permission_required('dashboard.view_loan', raise_exception=True)
def update_loan_status(request, pk):
    loan_request = get_object_or_404(Loan, id=pk)
    if request.method == 'POST':
        form = LoanUpdateForm(request.POST, instance=loan_request)
        if form.is_valid():
            loan = form.save(commit=False)
            loan.approved_by = request.user
            loan.save()
            
            # Send notification to user
            send_loan_notification(loan)
            
            messages.success(request, 'Loan status updated successfully')
            return redirect('loan-list')  # Redirect to see all loans
    else:
        form = LoanUpdateForm(instance=loan_request)
    return render(request, 'dashboard/update_loan_status.html', {'form': form, 'loan': loan_request})



def send_loan_notification(loan_request):
    if loan_request.status == 'Approved':
        subject = 'Loan Application Approved'
        message = f'Your {loan_request.loan_type} loan application for ${loan_request.amount} has been approved.'
    elif loan_request.status == 'Rejected':
        subject = 'Loan Application Rejected'
        message = f'Your {loan_request.loan_type} loan application for ${loan_request.amount} has been rejected.'
    
    send_mail(
        subject,
        message,
        settings.EMAIL_HOST_USER,
        [loan_request.user.email],
        fail_silently=False,
    )



@login_required(login_url='user-login')
@permission_required('dashboard.view_loan', raise_exception=True)
def staff_loan_dashboard(request):
    user_loans = Loan.objects.filter(user=request.user)
    pending_loans = user_loans.filter(status='Pending').count()
    approved_loans = user_loans.filter(status='Approved').count()
    rejected_loans = user_loans.filter(status='Rejected').count()
    
    context = {
        'pending_loans': pending_loans,
        'approved_loans': approved_loans,
        'rejected_loans': rejected_loans,
        'recent_loans': user_loans.order_by('-applied_date')[:5]
    }
    return render(request, 'dashboard/staff_loan_dashboard.html', context)




@login_required(login_url='user-login')
@permission_required('dashboard.change_loan', raise_exception=True)
def bulk_update_loans(request):
    if request.method == 'POST':
        loan_ids = request.POST.getlist('loan_ids')
        action = request.POST.get('action')
        Loan.objects.filter(id__in=loan_ids).update(status=action)


@login_required(login_url='user-login')
@permission_required('dashboard.change_loan', raise_exception=True)
def update_loan_status_ajax(request, loan_id):
    loan = get_object_or_404(Loan, id=loan_id)
    loan.status = request.POST.get('status')
    loan.save()
    return JsonResponse({'status': 'success'})



@login_required(login_url='user-login')
@permission_required('dashboard.change_loan', raise_exception=True)
def process_loan(request, loan_id):
    try:

        loan = Loan.objects.get(id=loan_id)
        # Process loan
    except ValidationError as e:
        messages.error(request, str(e))
    except Exception as e:
        logger.error(f"Error processing loan {loan_id}: {str(e)}")
        messages.error(request, "An unexpected error occurred")





















