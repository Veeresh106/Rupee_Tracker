import re
from decimal import Decimal

from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User

from .models import Budget, Category, Expense


class CategoryForm(forms.ModelForm):
    class Meta:
        model = Category
        fields = ['name', 'description']
        widgets = {
            'description': forms.Textarea(attrs={'rows': 3}),
        }


class BudgetForm(forms.ModelForm):
    month_year = forms.CharField(
        max_length=7,
        help_text='Use YYYY-MM format.',
        widget=forms.DateInput(attrs={'type': 'month'})
    )

    class Meta:
        model = Budget
        fields = ['category', 'month_year', 'monthly_limit']
        widgets = {
            'monthly_limit': forms.NumberInput(attrs={'step': '0.01', 'min': '0.01'}),
        }

    def __init__(self, user, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        self.fields['category'].queryset = Category.objects.filter(user=user)

    def clean_month_year(self):
        month_year = self.cleaned_data['month_year']
        if not re.fullmatch(r'\d{4}-\d{2}', month_year):
            raise forms.ValidationError('Please enter the month in YYYY-MM format.')
        year, month = map(int, month_year.split('-'))
        if not (1 <= month <= 12):
            raise forms.ValidationError('The month must be between 01 and 12.')
        return f'{year:04d}-{month:02d}'

    def clean_monthly_limit(self):
        limit = self.cleaned_data['monthly_limit']
        if limit <= Decimal('0.00'):
            raise forms.ValidationError('Budget limit must be greater than zero.')
        return limit

    def clean(self):
        cleaned_data = super().clean()
        category = cleaned_data.get('category')
        month_year = cleaned_data.get('month_year')
        if category and month_year:
            existing = Budget.objects.filter(
                user=self.user,
                category=category,
                month_year=month_year,
            )
            if self.instance.pk:
                existing = existing.exclude(pk=self.instance.pk)
            if existing.exists():
                raise forms.ValidationError('A budget already exists for this category and month.')
        return cleaned_data


class ExpenseForm(forms.ModelForm):
    class Meta:
        model = Expense
        fields = ['amount', 'date', 'category', 'notes']
        widgets = {
            'date': forms.DateInput(attrs={'type': 'date'}),
            'notes': forms.Textarea(attrs={'rows': 3}),
        }

    def __init__(self, user, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        self.fields['category'].queryset = Category.objects.filter(user=user)

    def clean_amount(self):
        amount = self.cleaned_data['amount']
        if amount <= Decimal('0.00'):
            raise forms.ValidationError('Expense amount must be greater than zero.')
        return amount

    def save(self, commit=True):
        expense = super().save(commit=False)
        expense.user = self.user
        if commit:
            expense.save()
        return expense


class RegistrationForm(UserCreationForm):
    email = forms.EmailField(required=True)

    class Meta:
        model = User
        fields = ['username', 'email', 'password1', 'password2']
