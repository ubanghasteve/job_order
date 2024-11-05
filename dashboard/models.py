import random
import string
from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from django.contrib.humanize.templatetags.humanize import intcomma
from django.contrib.auth.models import Group, Permission
from django.core.exceptions import ValidationError


CATEGORY = (
    ('Stationary', 'Stationary'),
    ('Electronics', 'Electronics'),
    ('Food', 'Food'),
    ('BOPP', 'BOPP'),
)

DEPARTMENT_CHOICES = [
    ('IT', 'Information Technology'),
    ('HR', 'Human Resources'),
    ('FIN', 'Finance'),
    ('OPS', 'Operations'),
    ('MKT', 'Marketing')
]

class Profile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='dashboard_profile')
    department = models.CharField(max_length=100, choices=DEPARTMENT_CHOICES)
    
    class Meta:
        verbose_name = 'User Profile'
        verbose_name_plural = 'User Profiles'
        ordering = ['user__username']
        

    def __str__(self):
        return f"{self.user.username}'s Profile"

def generate_submission_id():
    chars = string.ascii_uppercase + string.digits
    return ''.join(random.choice(chars) for _ in range(10))

def generate_job_order():
    prefix = 'JO'
    random_number = random.randint(1000, 9999)
    year = timezone.now().strftime('%y')
    return f"{prefix}-{random_number}-{year}"

class Product(models.Model):
    # Basic Information
    name = models.CharField(max_length=100, null=True)
    category = models.CharField(choices=CATEGORY, max_length=50, null=True)
    job_order = models.CharField(max_length=50, unique=True, default=generate_job_order)
    submission_id = models.CharField(max_length=50, null=True, blank=True, default=generate_submission_id)
    
    # Customer Information
    organization_name = models.CharField(max_length=200, null=True, blank=True)
    address = models.TextField(null=True, blank=True)
    contact_number = models.CharField(max_length=20, null=True, blank=True)
    
    # Product Details
    print_product = models.CharField(max_length=100, null=True, blank=True)
    colors = models.CharField(max_length=100, null=True, blank=True)
    order_info = models.TextField(null=True, blank=True)
    size = models.CharField(max_length=50, null=True, blank=True)
    micron = models.CharField(max_length=50, null=True, blank=True)
    job_title = models.CharField(max_length=100, null=True, blank=True)
    image = models.ImageField(upload_to='product_images/', null=True, blank=True)
    
    # Pricing and Quantity
    price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    quantity = models.PositiveIntegerField(null=True)
    order_quantity = models.PositiveIntegerField(null=True, blank=True)
    total = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    
    # Dates and Timeline
    date_created = models.DateTimeField(default=timezone.now)
    estimated_delivery_date = models.DateField(null=True, blank=True)
    actual_delivery_date = models.DateField(null=True, blank=True)
    cycle_time = models.DurationField(null=True, blank=True)
    production_status_date = models.DateTimeField(auto_now=True)
    
    # Status and Tracking
    APPROVAL_CHOICES = (
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    )
    approval_status = models.CharField(max_length=10, choices=APPROVAL_CHOICES, default='pending')
    production_status = models.TextField(null=True, blank=True)
    
    # User Relations
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='created_products')
    approved_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='approved_products')
    updated_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='product_updates')

    class Meta:
        ordering = ['-date_created']
        permissions = [
            ("can_approve_jobs", "Can approve job orders"),
            ("can_view_all_jobs", "Can view all job orders"),
            ("can_export_jobs", "Can export job orders"),
            ("can_manage_production", "Can manage production status"),
            ("view_dashboard", "Can view dashboard"),
            ("manage_leave", "Can manage leave requests"),
            ("can_export_products", "Can export products"),
            ("can_export_leaves", "Can export leaves"),
        ]
        
        
        
        
    def is_overdue(self):
        if self.estimated_delivery_date and not self.actual_delivery_date:
            return timezone.now().date() > self.estimated_delivery_date
        return False

    def get_status_display(self):
        return dict(self.APPROVAL_CHOICES)[self.approval_status]

    def days_until_delivery(self):
        if self.estimated_delivery_date:
            return (self.estimated_delivery_date - timezone.now().date()).days
        return None  
    
    
    

    def __str__(self):
        return f"{self.job_order} - {self.organization_name}"

    def save(self, *args, **kwargs):
        if not self.submission_id:
            self.submission_id = generate_submission_id()
        if not self.job_order:
            self.job_order = generate_job_order()
        self.calculate_total()
        self.calculate_cycle_time()
        super().save(*args, **kwargs)

    def calculate_total(self):
        if self.price is not None and self.order_quantity is not None:
            self.total = self.price * self.order_quantity

    def calculate_cycle_time(self):
        if self.estimated_delivery_date and self.actual_delivery_date:
            self.cycle_time = self.actual_delivery_date - self.estimated_delivery_date
        else:
            self.cycle_time = None

    def formatted_price(self):
        return f"₦{intcomma('{:.2f}'.format(self.price))}" if self.price else ''

    def formatted_total(self):
        return f"₦{intcomma('{:.2f}'.format(self.total))}" if self.total else ''

    
    
    
    
    
    
class ProductStatusHistory(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='status_history')
    status = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    is_active = models.BooleanField(default=True)
    priority = models.IntegerField(default=0)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Production Status History'
        verbose_name_plural = 'Production Status Histories'
        indexes = [
            models.Index(fields=['created_at', 'is_active']),
        ]
        
        
    def __str__(self):
        return f"Status update for {self.product.job_order} at {self.created_at}"
    
    def save(self, *args, **kwargs):
        # Update the parent product's status
        if self.is_active:
            self.product.production_status = self.status
            self.product.production_status_date = self.created_at
            self.product.updated_by = self.updated_by
            self.product.save()
        super().save(*args, **kwargs)
        
        

    
    
    

class Order(models.Model):
    # Your existing Order model code remains unchanged
    product = models.ForeignKey(Product, on_delete=models.CASCADE, null=True)
    customer = models.ForeignKey(User, on_delete=models.CASCADE, null=True)
    order_quantity = models.PositiveIntegerField(null=True)
    total_price = models.DecimalField(max_digits=10, decimal_places=2, null=True)
    date_created = models.DateTimeField(default=timezone.now)
    estimated_delivery_date = models.DateField(null=True)
    actual_delivery_date = models.DateField(null=True, blank=True)
    cycle_time = models.DurationField(null=True, blank=True)
    order_status = models.CharField(max_length=50, null=True)
    additional_notes = models.TextField(blank=True)
    
    
    
    ORDER_STATUS = (
        ('pending', 'Pending'),
        ('processing', 'Processing'),
        ('shipped', 'Shipped'),
        ('delivered', 'Delivered'),
        ('cancelled', 'Cancelled'),
    )
    
    order_status = models.CharField(max_length=50, choices=ORDER_STATUS, default='pending')

    def is_completed(self):
        return self.order_status == 'delivered'

    def can_be_cancelled(self):
        return self.order_status in ['pending', 'processing']
    
    

    def __str__(self):
        return f'{self.date_created} - {self.customer} - {self.product.job_order}'

    def save(self, *args, **kwargs):
        if self.product and self.order_quantity:
            self.total_price = self.product.price * self.order_quantity
        if self.estimated_delivery_date and self.actual_delivery_date:
            self.cycle_time = self.actual_delivery_date - self.estimated_delivery_date
        super().save(*args, **kwargs)

    def formatted_total_price(self):
        return f"₦{intcomma('{:.2f}'.format(self.total_price))}" if self.total_price else ''
    
    

class Leave(models.Model):
    LEAVE_TYPES = (
        ('Annual', 'Annual Leave'),
        ('Sick', 'Sick Leave'),
        ('Personal', 'Personal Leave'),
        ('Maternity', 'Maternity Leave'),
        ('Paternity', 'Paternity Leave'),
        ('Parental', 'Parental Leave'),
        ('Bereavement', 'Bereavement Leave'),
        ('Compassionate', 'Compassionate Leave'),
        ('Study', 'Study/Educational Leave'),
        ('Sabbatical', 'Sabbatical Leave'),
        ('Unpaid', 'Unpaid Leave'),
        ('Jury Duty', 'Jury Duty Leave'),
        ('Military', 'Military Leave'),
        ('Public Service', 'Public Service Leave'),
        ('Religious', 'Religious Leave'),
        ('Casual', 'Casual Leave'),
        ('Compensatory', 'Compensatory Leave'),
        ('Medical', 'Medical/Mental Health Leave'),
        ('Marriage', 'Marriage Leave'),
        ('Voting', 'Voting Leave'),
        ('Emergency', 'Emergency Leave'),
        ('Other', 'Other')
    )

    
    STATUS = (
        ('Pending', 'Pending'),
        ('Approved', 'Approved'),
        ('Rejected', 'Rejected')
    )
    
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    leave_type = models.CharField(max_length=20, choices=LEAVE_TYPES)
    start_date = models.DateField()
    end_date = models.DateField()
    reason = models.TextField()
    status = models.CharField(max_length=10, choices=STATUS, default='Pending')
    applied_date = models.DateTimeField(auto_now_add=True)
    approved_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='approved_leaves')
    response_date = models.DateTimeField(null=True, blank=True)
    response_message = models.TextField(null=True, blank=True)
    admin_response = models.TextField(null=True, blank=True)
    
    
    
    
    def clean(self):
        if self.start_date > self.end_date:
            raise ValidationError("End date must be after start date")
        if self.start_date < timezone.now().date():
            raise ValidationError("Start date cannot be in the past")

    def duration(self):
        return (self.end_date - self.start_date).days + 1

    def __str__(self):
        return f"{self.user.username} - {self.leave_type} - {self.status}"
    
    
    class Meta:
        indexes = [
            models.Index(fields=['status']),
            models.Index(fields=['applied_date']),
            models.Index(fields=['user']),
        ]
    


class Loan(models.Model):
    LOAN_TYPES = (
        ('Salary_Advance', 'Salary Advance'),
        ('Personal_Loan', 'Personal Loan'),
        ('Emergency_Loan', 'Emergency Loan'),
        ('Education_Loan', 'Education Loan'),
        ('Medical_Loan', 'Medical Loan'),
        ('Housing_Loan', 'Housing Loan'),
        ('Vehicle_Loan', 'Vehicle Loan'),
        ('Business_Loan', 'Business Loan'),
        ('Travel_Loan', 'Travel Loan'),
        ('Wedding_Loan', 'Wedding Loan'),
        ('Debt_Consolidation', 'Debt Consolidation Loan'),
        ('Home_Improvement', 'Home Improvement Loan'),
        ('Short_Term', 'Short Term Loan'),
        ('Long_Term', 'Long Term Loan'),
        ('Other', 'Other')
    )
    

    STATUS = (
        ('Pending', 'Pending'),
        ('Approved', 'Approved'),
        ('Rejected', 'Rejected')
    )

    id = models.AutoField(primary_key=True)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    loan_type = models.CharField(max_length=20, choices=LOAN_TYPES)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    start_date = models.DateField()
    end_date = models.DateField()
    reason = models.TextField()
    status = models.CharField(max_length=10, choices=STATUS, default='Pending')
    applied_date = models.DateTimeField(auto_now_add=True)
    approved_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='approved_loans')
    response_date = models.DateTimeField(null=True, blank=True)
    response_message = models.TextField(null=True, blank=True)
    admin_response = models.TextField(null=True, blank=True)
    
    
    def clean(self):
        if self.start_date > self.end_date:
            raise ValidationError("End date must be after start date")
        if self.amount <= 0:
            raise ValidationError("Loan amount must be greater than zero")

    def loan_duration(self):
        return (self.end_date - self.start_date).days
    
    

    def __str__(self):
        return f"{self.user.username} - {self.loan_type} - {self.status}"



    class Meta:
        ordering = ['id']
        indexes = [
            models.Index(fields=['status']),
            models.Index(fields=['applied_date']),
            models.Index(fields=['user']),
        ]






# Define custom permission groups
PERMISSION_GROUPS = [
    'Admin',
    'SuperAdmin', 
    'Manager',
    'Staff',
    'Leave',
    'Customer',
    'Production',
    'Sales',
    'Quality Control',
    'Inventory',
    'Finance'
    'Loan'
]

# Create function to set up permission groups









def create_permission_groups():
    for group_name in PERMISSION_GROUPS:
        group, created = Group.objects.get_or_create(name=group_name)
        
        # Assign specific permissions based on group
        if group_name == 'Production':
            permissions = Permission.objects.filter(
                codename__in=['add_product', 'change_product', 'view_product']
            )
            group.permissions.add(*permissions)
            
        elif group_name == 'Sales':
            permissions = Permission.objects.filter(
                codename__in=['add_order', 'change_order', 'view_order']
            )
            group.permissions.add(*permissions)
            
            
         # Add loan-specific permissions
        if group_name == 'Finance':
            permissions = Permission.objects.filter(
                codename__in=['add_loan', 'change_loan', 'view_loan', 'delete_loan']
            )
            group.permissions.add(*permissions)
            
        
        # Add more group-specific permissions as needed
        














