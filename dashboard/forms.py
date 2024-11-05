from django import forms
from .models import Product, Order, Loan
from django.contrib.auth.models import User
from .models import Leave

class ProductForm(forms.ModelForm):
    class Meta:
        model = Product
        exclude = ['approved_by', 'approval_status', 'created_by', 'updated_by', 'production_status', 'name', 'category', 'estimated_delivery_date', 'actual_delivery_date',]
        labels = {
            'print_product': 'Package type/ Product',
            'order_info': 'Cutting/ Pouching',
            'size': 'Thickness / Width',
            'micron': 'Sealing Type',
            'price': 'Price (₦)',  # Added Naira symbol to price label
            'total': 'Total (₦)',   # Added Naira symbol to total label
            'order_quantity': 'Order quantity (kg)',
            'job_order': 'Job Order Number',
            'job_title': 'Delivery Qty',
            'organization_name': 'Job name',
            'colors': 'No: of Colors / Color Names',
        }
        
        
        fields = [
            'job_order',
            'organization_name',
            'address',
            'contact_number',
            'print_product',
            'colors',
            'order_info',
            'size',
            'micron',
            'job_title',
            'price',
            'order_quantity',
            'estimated_delivery_date',
            'actual_delivery_date',
            'image'
        ]
        
        
        
        widgets = {
            'image': forms.ClearableFileInput(attrs={
                'accept': 'image/*',
                'class': 'form-control',
                'id': 'id_image'
            }),
            'price': forms.NumberInput(attrs={
                'id': 'id_price',
                'step': '0.01',
                'class': 'form-control'
            }),
            'order_quantity': forms.NumberInput(attrs={
                'id': 'id_order_quantity',
                'class': 'form-control'
            }),
            'total': forms.NumberInput(attrs={
                'readonly': True,
                'id': 'id_total',
                'required': False,
                'class': 'form-control'
            })
        }

    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        super(ProductForm, self).__init__(*args, **kwargs)
        
        # Make image field not required
        self.fields['image'].required = False
        
        # Update field labels
        self.fields['print_product'].label = 'Package type/ Product'
        self.fields['order_info'].label = 'Cutting/ Pouching'
        self.fields['size'].label = 'Thickness / Width'
        self.fields['micron'].label = 'Sealing Type'
        
        if user and user.is_superuser:
            self.fields['approval_status'] = forms.ChoiceField(
                choices=[('pending', 'Pending'), ('approve', 'Approve'), ('deny', 'Deny')],
                required=True,
                widget=forms.Select(attrs={'class': 'form-control'})
            )
            self.fields['approved_by'] = forms.ModelChoiceField(
                queryset=User.objects.filter(is_superuser=True),
                required=False,
                widget=forms.Select(attrs={'class': 'form-control'})
            )
            self.fields['created_by'] = forms.ModelChoiceField(
                queryset=User.objects.all(),
                required=False,
                widget=forms.Select(attrs={'class': 'form-control'})
            )
            
       
       
       
       
            
    def clean_price(self):
        price = self.cleaned_data.get('price')
        if price and price <= 0:
            raise forms.ValidationError("Price must be greater than zero")
        return price

    def clean_order_quantity(self):
        quantity = self.cleaned_data.get('order_quantity')
        if quantity and quantity <= 0:
            raise forms.ValidationError("Quantity must be greater than zero")
        return quantity        
    
    
    
    
    

    def clean(self):
        cleaned_data = super().clean()
        price = cleaned_data.get('price')
        quantity = cleaned_data.get('order_quantity')
        if price and quantity:
            cleaned_data['total'] = price * quantity
        return cleaned_data

class OrderForm(forms.ModelForm):
    class Meta:
        model = Order
        fields = ['product', 'order_quantity', 'order_status']






class LeaveForm(forms.ModelForm):
    
    duration = forms.IntegerField(disabled=True, required=False)
    
    def clean(self):
        cleaned_data = super().clean()
        start_date = cleaned_data.get('start_date')
        end_date = cleaned_data.get('end_date')
        
        if start_date and end_date:
            if start_date > end_date:
                raise forms.ValidationError("End date must be after start date")
            
            # Calculate duration
            duration = (end_date - start_date).days + 1
            cleaned_data['duration'] = duration
            
            # Check maximum leave duration
            if duration > 30:
                raise forms.ValidationError("Leave duration cannot exceed 30 days")
        
        return cleaned_data
    
    
    class Meta:
        model = Leave
        fields = ['leave_type', 'start_date', 'end_date', 'reason']
        widgets = {
            'start_date': forms.DateInput(attrs={'type': 'date'}),
            'end_date': forms.DateInput(attrs={'type': 'date'}),
        }





class LeaveResponseForm(forms.ModelForm):
    class Meta:
        model = Leave
        fields = ['status', 'response_message']
        widgets = {
            'response_message': forms.Textarea(attrs={'rows': 4, 'placeholder': 'Enter response message'}),
            'status': forms.Select(choices=[
                ('approved', 'Approve'),
                ('denied', 'Deny'),
                ('pending', 'Pending')
            ])
        }







class LeaveUpdateForm(forms.ModelForm):
    response_message = forms.CharField(widget=forms.Textarea(attrs={'rows': 4}), required=False)
    
    class Meta:
        model = Leave
        fields = ['status', 'response_message']
        widgets = {
            'status': forms.Select(choices=[
                ('Pending', 'Pending'),
                ('Approved', 'Approved'),
                ('Rejected', 'Rejected')
            ])
        }





class LoanForm(forms.ModelForm):
    class Meta:
        model = Loan
        exclude = ['approved_by', 'status', 'applied_date', 'response_date', 'response_message', 'admin_response']
        
        labels = {
            'loan_type': 'Type of Loan / Salary Advance',
            'amount': 'Amount (₦)',
            'start_date': 'Start Date',
            'end_date': 'End Date',
            'reason': 'Purpose of Loan / Salary Advance',
        }
        
        fields = [
            'loan_type',
            'amount',
            'start_date',
            'end_date',
            'reason'
        ]
        
        widgets = {
            'amount': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01',
                'min': '0'
            }),
            'start_date': forms.DateInput(attrs={
                'type': 'date',
                'class': 'form-control'
            }),
            'end_date': forms.DateInput(attrs={
                'type': 'date',
                'class': 'form-control'
            }),
            'reason': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 4
            })
        }

    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        super(LoanForm, self).__init__(*args, **kwargs)
        
        if user and user.is_superuser:
            self.fields['status'] = forms.ChoiceField(
                choices=[('Pending', 'Pending'), ('Approved', 'Approved'), ('Rejected', 'Rejected')],
                required=True,
                widget=forms.Select(attrs={'class': 'form-control'})
            )
            self.fields['approved_by'] = forms.ModelChoiceField(
                queryset=User.objects.filter(is_superuser=True),
                required=False,
                widget=forms.Select(attrs={'class': 'form-control'})
            )
            
            
            
    def clean_amount(self):
        amount = self.cleaned_data.get('amount')
        if amount:
            if amount <= 0:
                raise forms.ValidationError("Loan amount must be greater than zero")
            if amount > 1000000:  # Example maximum amount
                raise forms.ValidationError("Loan amount cannot exceed ₦1,000,000")
        return amount
            

    def clean(self):
        cleaned_data = super().clean()
        start_date = cleaned_data.get('start_date')
        end_date = cleaned_data.get('end_date')
        
        if start_date and end_date and start_date > end_date:
            raise forms.ValidationError("End date cannot be before start date")
        return cleaned_data

class LoanResponseForm(forms.ModelForm):
    class Meta:
        model = Loan
        fields = ['status', 'response_message']
        widgets = {
            'response_message': forms.Textarea(attrs={
                'rows': 4, 
                'placeholder': 'Enter response message',
                'class': 'form-control'
            }),
            'status': forms.Select(
                choices=[
                    ('Approved', 'Approve'),
                    ('Rejected', 'Reject'),
                    ('Pending', 'Pending')
                ],
                attrs={'class': 'form-control'}
            )
        }

class LoanUpdateForm(forms.ModelForm):
    response_message = forms.CharField(
        widget=forms.Textarea(attrs={
            'rows': 4,
            'class': 'form-control'
        }), 
        required=False
    )
    
    class Meta:
        model = Loan
        fields = ['status', 'response_message']
        widgets = {
            'status': forms.Select(
                choices=[
                    ('Pending', 'Pending'),
                    ('Approved', 'Approved'),
                    ('Rejected', 'Rejected')
                ],
                attrs={'class': 'form-control'}
            )
        }


class BaseModelForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.update({'class': 'form-control'})
            
            
            
            
class OrderForm(BaseModelForm):
    def get_product_choices(self):
        return Product.objects.filter(approval_status='approved')
        
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['product'].queryset = self.get_product_choices()
          
            
            
            
            
            
            
            
            
            