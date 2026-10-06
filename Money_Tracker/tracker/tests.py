from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.forms import AuthenticationForm
from django.test import TestCase
from django.urls import reverse

from .forms import BudgetForm, CategoryForm, ExpenseForm, RegistrationForm
from .models import Budget, Category, Expense


class BudgetAlertLogicTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username='demo',
            email='demo@example.com',
            password='secret123'
        )
        self.category = Category.objects.create(
            user=self.user,
            name='Food',
            description='Meals and groceries'
        )

    def test_budget_remaining_and_warning_percent(self):
        budget = Budget.objects.create(
            user=self.user,
            category=self.category,
            month_year='2026-10',
            monthly_limit=Decimal('200.00')
        )
        self.assertEqual(budget.remaining_budget(), Decimal('200.00'))
        self.assertEqual(budget.alert_level(), 'normal')

        budget.current_spent = Decimal('160.00')
        self.assertEqual(budget.calculate_usage_ratio(), Decimal('0.80'))
        self.assertEqual(budget.alert_level(), 'warning')

    def test_budget_danger_at_or_above_100_percent(self):
        budget = Budget.objects.create(
            user=self.user,
            category=self.category,
            month_year='2026-10',
            monthly_limit=Decimal('100.00')
        )
        budget.current_spent = Decimal('100.00')
        self.assertEqual(budget.calculate_usage_ratio(), Decimal('1.00'))
        self.assertEqual(budget.alert_level(), 'danger')


class ExpenseTrackerWorkflowTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.user = user_model.objects.create_user(
            username='owner', email='owner@example.com', password='Valid-pass-123'
        )
        self.other_user = user_model.objects.create_user(
            username='other', email='other@example.com', password='Valid-pass-123'
        )
        self.category = Category.objects.create(user=self.user, name='Food')
        self.unbudgeted_category = Category.objects.create(user=self.user, name='Travel')
        self.other_category = Category.objects.create(user=self.other_user, name='Private')
        self.client.force_login(self.user)

    def test_invalid_month_filters_fall_back_without_server_error(self):
        for url in ('dashboard', 'expenses', 'reports'):
            response = self.client.get(reverse(url), {'month': 'not-a-month'})
            self.assertEqual(response.status_code, 200)

    def test_invalid_quick_add_keeps_form_errors_visible(self):
        response = self.client.post(reverse('expenses_create'), {
            'amount': '0',
            'date': '2026-10-06',
            'category': self.category.pk,
            'notes': '',
            'return_to': 'dashboard',
            'month': '2026-10',
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Expense amount must be greater than zero.')

    def test_empty_account_gets_category_options_and_can_add_expense(self):
        user = get_user_model().objects.create_user(
            username='new-owner', email='new-owner@example.com', password='Valid-pass-123'
        )
        self.client.force_login(user)

        response = self.client.get(reverse('expenses'))
        category_field = response.context['form'].fields['category']
        self.assertGreater(category_field.queryset.count(), 0)
        self.assertContains(response, 'Food')

        category = category_field.queryset.get(name='Food')
        response = self.client.post(reverse('expenses_create'), {
            'amount': '18.50',
            'date': '2026-10-06',
            'category': category.pk,
            'notes': 'Starter category option',
            'return_to': 'expenses',
            'month': '2026-10',
        })
        self.assertRedirects(response, reverse('expenses'))
        self.assertTrue(Expense.objects.filter(user=user, category=category).exists())

    def test_expense_create_edit_and_delete(self):
        response = self.client.post(reverse('expenses_create'), {
            'amount': '25.50',
            'date': '2026-10-06',
            'category': self.category.pk,
            'notes': 'Lunch',
            'return_to': 'expenses',
            'month': '2026-10',
        })
        self.assertRedirects(response, reverse('expenses'))
        expense = Expense.objects.get(user=self.user)

        response = self.client.post(reverse('expense_edit', args=[expense.pk]), {
            'amount': '30.00',
            'date': '2026-10-06',
            'category': self.category.pk,
            'notes': 'Updated lunch',
        })
        self.assertRedirects(response, reverse('expenses'))
        expense.refresh_from_db()
        self.assertEqual(expense.amount, Decimal('30.00'))
        self.assertEqual(expense.notes, 'Updated lunch')

        response = self.client.post(reverse('expense_delete', args=[expense.pk]))
        self.assertRedirects(response, reverse('expenses'))
        self.assertFalse(Expense.objects.filter(pk=expense.pk).exists())

    def test_expense_edit_cannot_access_another_users_data(self):
        expense = Expense.objects.create(
            user=self.other_user,
            category=self.other_category,
            amount=Decimal('12.00'),
            date='2026-10-06',
        )
        response = self.client.get(reverse('expense_edit', args=[expense.pk]))
        self.assertEqual(response.status_code, 404)

    def test_category_create_edit_and_delete(self):
        response = self.client.post(reverse('categories'), {
            'name': 'Utilities',
            'description': 'Monthly services',
        })
        self.assertRedirects(response, reverse('categories'))
        category = Category.objects.get(user=self.user, name='Utilities')

        response = self.client.post(reverse('category_edit', args=[category.pk]), {
            'name': 'Home utilities',
            'description': 'Updated description',
        })
        self.assertRedirects(response, reverse('categories'))
        category.refresh_from_db()
        self.assertEqual(category.name, 'Home utilities')

        response = self.client.post(reverse('category_delete', args=[category.pk]))
        self.assertRedirects(response, reverse('categories'))
        self.assertFalse(Category.objects.filter(pk=category.pk).exists())

    def test_empty_category_management_page_stays_empty_and_can_add_one(self):
        Category.objects.filter(user=self.user).delete()
        response = self.client.get(reverse('categories'))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context['categories'].exists())

        response = self.client.post(reverse('categories'), {
            'name': 'Custom category',
            'description': '',
        })
        self.assertRedirects(response, reverse('categories'))
        self.assertTrue(Category.objects.filter(user=self.user, name='Custom category').exists())

    def test_budget_edit_and_delete(self):
        budget = Budget.objects.create(
            user=self.user,
            category=self.category,
            month_year='2026-10',
            monthly_limit=Decimal('100.00'),
        )
        response = self.client.post(reverse('budget_edit', args=[budget.pk]), {
            'category': self.category.pk,
            'month_year': '2026-10',
            'monthly_limit': '250.00',
        })
        self.assertRedirects(response, reverse('budgets'))
        budget.refresh_from_db()
        self.assertEqual(budget.monthly_limit, Decimal('250.00'))

        response = self.client.post(reverse('budget_delete', args=[budget.pk]))
        self.assertRedirects(response, reverse('budgets'))
        self.assertFalse(Budget.objects.filter(pk=budget.pk).exists())

    def test_report_includes_unbudgeted_expense_categories(self):
        Expense.objects.create(
            user=self.user,
            category=self.unbudgeted_category,
            amount=Decimal('42.75'),
            date='2026-10-06',
        )
        response = self.client.get(reverse('reports'), {'month': '2026-10'})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Travel')
        self.assertEqual(response.context['total_spent'], Decimal('42.75'))

    def test_dashboard_remaining_counts_only_budgeted_category_spending(self):
        Budget.objects.create(
            user=self.user,
            category=self.category,
            month_year='2026-10',
            monthly_limit=Decimal('100.00'),
        )
        Expense.objects.create(
            user=self.user,
            category=self.category,
            amount=Decimal('25.00'),
            date='2026-10-06',
        )
        Expense.objects.create(
            user=self.user,
            category=self.unbudgeted_category,
            amount=Decimal('50.00'),
            date='2026-10-06',
        )
        response = self.client.get(reverse('dashboard'), {'month': '2026-10'})
        self.assertEqual(response.context['total_spent'], Decimal('75.00'))
        self.assertEqual(response.context['total_remaining'], Decimal('75.00'))

    def test_duplicate_budget_is_rejected_by_form(self):
        Budget.objects.create(
            user=self.user,
            category=self.category,
            month_year='2026-10',
            monthly_limit=Decimal('100.00'),
        )
        response = self.client.post(reverse('budgets'), {
            'category': self.category.pk,
            'month_year': '2026-10',
            'monthly_limit': '200.00',
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'A budget already exists for this category and month.')
        self.assertEqual(Budget.objects.filter(user=self.user).count(), 1)

    def test_login_honors_safe_next_and_logout_requires_post(self):
        self.client.logout()
        response = self.client.post(reverse('login') + '?next=/reports/', {
            'username': 'owner',
            'password': 'Valid-pass-123',
            'next': '/reports/',
        })
        self.assertRedirects(response, '/reports/')
        self.assertEqual(self.client.get(reverse('logout')).status_code, 405)
        self.assertRedirects(self.client.post(reverse('logout')), reverse('login'))


class FormFieldValidationTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.user = user_model.objects.create_user(
            username='form-owner', email='form-owner@example.com', password='Valid-pass-123'
        )
        self.other_user = user_model.objects.create_user(
            username='form-other', email='form-other@example.com', password='Valid-pass-123'
        )
        self.category = Category.objects.create(user=self.user, name='Food')
        self.other_category = Category.objects.create(user=self.other_user, name='Private')

    def test_login_and_registration_required_fields(self):
        login_form = AuthenticationForm(data={})
        self.assertIn('username', login_form.errors)
        self.assertIn('password', login_form.errors)

        registration_form = RegistrationForm(data={})
        for field in ('username', 'email', 'password1', 'password2'):
            with self.subTest(field=field):
                self.assertIn(field, registration_form.errors)

    def test_category_name_is_required_and_description_is_optional(self):
        self.assertIn('name', CategoryForm(data={'name': '', 'description': ''}).errors)
        self.assertTrue(CategoryForm(data={'name': 'Utilities', 'description': ''}).is_valid())

    def test_budget_fields_validate_category_month_and_limit(self):
        valid_data = {
            'category': self.category.pk,
            'month_year': '2026-10',
            'monthly_limit': '200.00',
        }
        self.assertTrue(BudgetForm(self.user, data=valid_data).is_valid())

        invalid_data = (
            ('category', {**valid_data, 'category': ''}),
            ('category', {**valid_data, 'category': self.other_category.pk}),
            ('month_year', {**valid_data, 'month_year': '2026-13'}),
            ('monthly_limit', {**valid_data, 'monthly_limit': '0'}),
        )
        for field, data in invalid_data:
            with self.subTest(field=field, value=data[field]):
                self.assertIn(field, BudgetForm(self.user, data=data).errors)

    def test_expense_fields_validate_amount_date_category_and_optional_notes(self):
        valid_data = {
            'amount': '12.50',
            'date': '2026-10-06',
            'category': self.category.pk,
            'notes': '',
        }
        self.assertTrue(ExpenseForm(self.user, data=valid_data).is_valid())

        invalid_data = (
            ('amount', {**valid_data, 'amount': '0'}),
            ('date', {**valid_data, 'date': ''}),
            ('category', {**valid_data, 'category': ''}),
            ('category', {**valid_data, 'category': self.other_category.pk}),
        )
        for field, data in invalid_data:
            with self.subTest(field=field, value=data[field]):
                self.assertIn(field, ExpenseForm(self.user, data=data).errors)

    def test_tabs_render_forms_and_new_users_get_categories(self):
        self.client.force_login(self.user)
        for route in ('dashboard', 'categories', 'budgets', 'expenses', 'reports'):
            with self.subTest(route=route):
                self.assertEqual(self.client.get(reverse(route)).status_code, 200)

        new_user = get_user_model().objects.create_user(
            username='fresh-owner', email='fresh-owner@example.com', password='Valid-pass-123'
        )
        self.client.force_login(new_user)
        response = self.client.get(reverse('budgets'))
        self.assertGreater(response.context['form'].fields['category'].queryset.count(), 0)
        self.assertContains(response, 'Food')

    def test_registration_creates_starter_categories(self):
        response = self.client.post(reverse('register'), {
            'username': 'fresh-account',
            'email': 'fresh-account@example.com',
            'password1': 'Green-River-458!',
            'password2': 'Green-River-458!',
        })
        self.assertRedirects(response, reverse('dashboard'))
        user = get_user_model().objects.get(username='fresh-account')
        self.assertEqual(user.categories.count(), 7)


class BudgetWarningPopupTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username='alert-owner', password='Valid-pass-123'
        )
        self.category = Category.objects.create(user=self.user, name='Food')
        self.budget = Budget.objects.create(
            user=self.user,
            category=self.category,
            month_year='2026-10',
            monthly_limit=Decimal('100.00'),
        )
        self.client.force_login(self.user)

    def _add_expense(self, amount):
        Expense.objects.create(
            user=self.user,
            category=self.category,
            amount=Decimal(amount),
            date='2026-10-06',
        )

    def test_popup_appears_at_80_percent_once_and_again_at_100_percent(self):
        self._add_expense('79.00')
        response = self.client.get(reverse('dashboard'), {'month': '2026-10'})
        self.assertNotContains(response, 'budgetAlertModal')

        response = self.client.post(reverse('expenses_create'), {
            'amount': '1.00',
            'date': '2026-10-06',
            'category': self.category.pk,
            'notes': '',
            'return_to': 'expenses',
            'month': '2026-10',
        }, follow=True)
        self.assertContains(response, 'budgetAlertModal')
        self.assertContains(response, "You've used 80% of your Food budget. Please use your money carefully.")

        response = self.client.get(reverse('expenses'), {'month': '2026-10'})
        self.assertNotContains(response, 'budgetAlertModal')

        self._add_expense('20.00')
        response = self.client.get(reverse('reports'), {'month': '2026-10'})
        self.assertContains(response, 'budgetAlertModal')
        self.assertContains(response, "You've used 100% of your Food budget.")
