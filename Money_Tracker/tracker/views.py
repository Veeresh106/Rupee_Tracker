from datetime import date
from decimal import Decimal
import re

from django.contrib import messages
from django.contrib.auth import login, logout, REDIRECT_FIELD_NAME
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import AuthenticationForm
from django.db.models import Sum
from django.db.models.deletion import ProtectedError
from django.views.decorators.http import require_POST
from django.utils.http import url_has_allowed_host_and_scheme
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from .forms import BudgetForm, CategoryForm, ExpenseForm, RegistrationForm
from .models import Budget, Category, Expense

DEFAULT_CATEGORY_NAMES = (
    'Food',
    'Transport',
    'Bills',
    'Shopping',
    'Health',
    'Entertainment',
    'Other',
)


def _ensure_default_categories(user):
    if not Category.objects.filter(user=user).exists():
        Category.objects.bulk_create([
            Category(user=user, name=name) for name in DEFAULT_CATEGORY_NAMES
        ])


def _selected_month(request):
    month_year = request.GET.get('month') or request.POST.get('month')
    if month_year and re.fullmatch(r'\d{4}-\d{2}', month_year):
        year, month = map(int, month_year.split('-'))
        if 1 <= month <= 12:
            return f'{year:04d}-{month:02d}'
    return date.today().strftime('%Y-%m')


def home_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
    return render(request, 'tracker/home.html')


def register_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard')

    if request.method == 'POST':
        form = RegistrationForm(request.POST)
        if form.is_valid():
            user = form.save()
            _ensure_default_categories(user)
            login(request, user)
            messages.success(request, 'Your account was created successfully.')
            return redirect('dashboard')
    else:
        form = RegistrationForm()
    return render(request, 'tracker/register.html', {'form': form})


def login_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard')

    if request.method == 'POST':
        form = AuthenticationForm(request, data=request.POST)
        if form.is_valid():
            user = form.get_user()
            login(request, user)
            messages.success(request, 'Welcome back!')
            next_url = request.POST.get(REDIRECT_FIELD_NAME) or request.GET.get(REDIRECT_FIELD_NAME)
            if next_url and url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}):
                return redirect(next_url)
            return redirect('dashboard')
    else:
        form = AuthenticationForm()
    return render(request, 'tracker/login.html', {'form': form})


@login_required
@require_POST
def logout_view(request):
    logout(request)
    messages.info(request, 'You have been logged out.')
    return redirect('login')


@login_required
def dashboard(request):
    _ensure_default_categories(request.user)
    month_year = _selected_month(request)
    year, month = map(int, month_year.split('-'))

    categories = Category.objects.filter(user=request.user).order_by('name')
    budgets = Budget.objects.filter(user=request.user, month_year=month_year).select_related('category')
    month_expenses = Expense.objects.filter(user=request.user, date__year=year, date__month=month)
    recent_expenses = month_expenses.order_by('-date', '-created_at')[:5]

    total_spent = month_expenses.aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
    total_budget = sum((budget.monthly_limit for budget in budgets), Decimal('0.00'))
    budgeted_spent = sum((budget.current_spent for budget in budgets), Decimal('0.00'))
    total_remaining = total_budget - budgeted_spent

    budget_rows = []
    for budget in budgets:
        usage_ratio = budget.calculate_usage_ratio() * 100
        budget_rows.append({
            'object': budget,
            'spent': budget.current_spent,
            'remaining': budget.remaining_budget(),
            'usage_ratio': usage_ratio,
            'alert_level': budget.alert_level(),
            'badge_class': budget.badge_class(),
        })

    context = {
        'month': month_year,
        'categories': categories,
        'budgets': budgets,
        'recent_expenses': recent_expenses,
        'budget_rows': budget_rows,
        'total_spent': total_spent,
        'total_budget': total_budget,
        'total_remaining': total_remaining,
        'expense_form': ExpenseForm(request.user),
        'category_form': CategoryForm(),
        'budget_form': BudgetForm(request.user),
    }
    return render(request, 'tracker/dashboard.html', context)


@login_required
def expenses_list(request):
    _ensure_default_categories(request.user)
    month_year = _selected_month(request)
    year, month = map(int, month_year.split('-'))
    categories = Category.objects.filter(user=request.user).order_by('name')
    expenses = Expense.objects.filter(
        user=request.user, date__year=year, date__month=month
    ).select_related('category')
    selected_category = request.GET.get('category', '')
    if selected_category.isdigit() and categories.filter(pk=selected_category).exists():
        expenses = expenses.filter(category_id=selected_category)
    form = ExpenseForm(request.user)
    if request.method == 'POST':
        form = ExpenseForm(request.user, request.POST)
        if form.is_valid():
            expense = form.save()
            messages.success(request, f'Expense of {expense.amount} saved successfully.')
            return redirect('expenses')
    return render(request, 'tracker/expenses.html', {
        'expenses': expenses,
        'form': form,
        'month': month_year,
        'categories': categories,
        'selected_category': selected_category,
    })


@login_required
def expenses_create(request):
    if request.method == 'POST':
        _ensure_default_categories(request.user)
        form = ExpenseForm(request.user, request.POST)
        if form.is_valid():
            expense = form.save()
            messages.success(request, f'Expense of {expense.amount} saved successfully.')
            destination = reverse('expenses' if request.POST.get('return_to') == 'expenses' else 'dashboard')
            return redirect(f'{destination}?month={expense.date:%Y-%m}')

        month_year = _selected_month(request)
        if request.POST.get('return_to') == 'expenses':
            year, month = map(int, month_year.split('-'))
            expenses = Expense.objects.filter(
                user=request.user, date__year=year, date__month=month
            ).select_related('category')
            return render(request, 'tracker/expenses.html', {
                'expenses': expenses,
                'form': form,
                'month': month_year,
                'categories': Category.objects.filter(user=request.user).order_by('name'),
                'selected_category': '',
            })

        year, month = map(int, month_year.split('-'))
        categories = Category.objects.filter(user=request.user).order_by('name')
        budgets = Budget.objects.filter(
            user=request.user, month_year=month_year
        ).select_related('category')
        month_expenses = Expense.objects.filter(
            user=request.user, date__year=year, date__month=month
        )
        total_spent = month_expenses.aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
        total_budget = sum((budget.monthly_limit for budget in budgets), Decimal('0.00'))
        budgeted_spent = sum((budget.current_spent for budget in budgets), Decimal('0.00'))
        budget_rows = [{
            'object': budget,
            'spent': budget.current_spent,
            'remaining': budget.remaining_budget(),
            'usage_ratio': budget.calculate_usage_ratio() * 100,
            'alert_level': budget.alert_level(),
        } for budget in budgets]
        return render(request, 'tracker/dashboard.html', {
            'month': month_year,
            'categories': categories,
            'budgets': budgets,
            'recent_expenses': month_expenses.order_by('-date', '-created_at')[:5],
            'budget_rows': budget_rows,
            'total_spent': total_spent,
            'total_budget': total_budget,
            'total_remaining': total_budget - budgeted_spent,
            'expense_form': form,
            'category_form': CategoryForm(),
            'budget_form': BudgetForm(request.user),
        })

    return redirect('dashboard')


@login_required
def expense_delete(request, pk):
    expense = get_object_or_404(Expense, pk=pk, user=request.user)
    if request.method == 'POST':
        expense.delete()
        messages.success(request, 'Expense deleted successfully.')
    return redirect('expenses')


@login_required
def expense_edit(request, pk):
    expense = get_object_or_404(Expense, pk=pk, user=request.user)
    if request.method == 'POST':
        form = ExpenseForm(request.user, request.POST, instance=expense)
        if form.is_valid():
            form.save()
            messages.success(request, 'Expense updated successfully.')
            return redirect('expenses')
    else:
        form = ExpenseForm(request.user, instance=expense)
    return render(request, 'tracker/expense_form.html', {'form': form, 'expense': expense})


@login_required
def categories_list(request):
    categories = Category.objects.filter(user=request.user)
    if request.method == 'POST':
        form = CategoryForm(request.POST)
        if form.is_valid():
            category = form.save(commit=False)
            category.user = request.user
            category.save()
            messages.success(request, 'Category created successfully.')
            return redirect('categories')
    else:
        form = CategoryForm()
    return render(request, 'tracker/categories.html', {'categories': categories, 'form': form})


@login_required
def category_edit(request, pk):
    category = get_object_or_404(Category, pk=pk, user=request.user)
    if request.method == 'POST':
        form = CategoryForm(request.POST, instance=category)
        if form.is_valid():
            form.save()
            messages.success(request, 'Category updated successfully.')
            return redirect('categories')
    else:
        form = CategoryForm(instance=category)
    return render(request, 'tracker/category_form.html', {'form': form, 'category': category})


@login_required
def category_delete(request, pk):
    category = get_object_or_404(Category, pk=pk, user=request.user)
    if request.method == 'POST':
        try:
            category.delete()
            messages.success(request, 'Category deleted successfully.')
        except ProtectedError:
            messages.error(request, 'This category has existing expenses and cannot be deleted.')
    return redirect('categories')


@login_required
def budgets_list(request):
    _ensure_default_categories(request.user)
    month_year = _selected_month(request)
    budgets = Budget.objects.filter(
        user=request.user, month_year=month_year
    ).select_related('category')
    if request.method == 'POST':
        form = BudgetForm(request.user, request.POST)
        if form.is_valid():
            budget = form.save(commit=False)
            budget.user = request.user
            budget.save()
            messages.success(request, 'Budget saved successfully.')
            return redirect('budgets')
    else:
        form = BudgetForm(request.user)
    return render(request, 'tracker/budgets.html', {
        'budgets': budgets,
        'form': form,
        'month': month_year,
    })


@login_required
def budget_edit(request, pk):
    budget = get_object_or_404(Budget, pk=pk, user=request.user)
    if request.method == 'POST':
        form = BudgetForm(request.user, request.POST, instance=budget)
        if form.is_valid():
            budget = form.save(commit=False)
            budget.user = request.user
            budget.save()
            messages.success(request, 'Budget updated successfully.')
            return redirect('budgets')
    else:
        form = BudgetForm(request.user, instance=budget)
    return render(request, 'tracker/budget_form.html', {'form': form, 'budget': budget})


@login_required
def budget_delete(request, pk):
    budget = get_object_or_404(Budget, pk=pk, user=request.user)
    if request.method == 'POST':
        budget.delete()
        messages.success(request, 'Budget deleted successfully.')
    return redirect('budgets')


@login_required
def reports_view(request):
    month_year = _selected_month(request)
    month_expenses = Expense.objects.filter(user=request.user, date__month=int(month_year[5:7]), date__year=int(month_year[:4]))
    palette = ['#3b82f6', '#10b981', '#f59e0b', '#f43f5e', '#8b5cf6', '#14b8a6']
    swatch_classes = ['bg-primary', 'bg-success', 'bg-warning', 'bg-danger', 'bg-secondary', 'bg-info']
    category_totals = [
        {
            'name': row['category__name'],
            'spent': row['spent'],
            'color': palette[index % len(palette)],
            'swatch_class': swatch_classes[index % len(swatch_classes)],
        }
        for index, row in enumerate(
            month_expenses.values('category__name').annotate(spent=Sum('amount')).order_by('category__name')
        )
    ]

    if not category_totals:
        category_totals = [{
            'name': 'No data',
            'spent': Decimal('0.00'),
            'color': '#dbeafe',
            'swatch_class': 'bg-secondary',
        }]

    context = {
        'month': month_year,
        'category_totals': category_totals,
        'chart_data': {
            'labels': [item['name'] for item in category_totals],
            'amounts': [float(item['spent']) for item in category_totals],
            'colors': [item['color'] for item in category_totals],
        },
        'total_spent': month_expenses.aggregate(total=Sum('amount'))['total'] or Decimal('0.00'),
        'month_expenses': month_expenses.order_by('-date')[:10],
    }
    return render(request, 'tracker/reports.html', context)
