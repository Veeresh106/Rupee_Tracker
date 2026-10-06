from decimal import Decimal, ROUND_HALF_UP

from django.conf import settings
from django.db import models
from django.db.models import Sum


class Category(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='categories')
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


class Budget(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='budgets')
    category = models.ForeignKey(Category, on_delete=models.CASCADE, related_name='budgets')
    month_year = models.CharField(max_length=7)
    monthly_limit = models.DecimalField(max_digits=10, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-month_year', 'category__name']
        unique_together = ('user', 'category', 'month_year')

    def __str__(self):
        return f'{self.category.name} ({self.month_year})'

    @property
    def current_spent(self):
        if hasattr(self, '_current_spent_override'):
            return self._current_spent_override
        year, month = map(int, self.month_year.split('-'))
        total = Expense.objects.filter(
            user=self.user,
            category=self.category,
            date__year=year,
            date__month=month,
        ).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
        return total

    @current_spent.setter
    def current_spent(self, value):
        self._current_spent_override = Decimal(str(value))

    def calculate_usage_ratio(self):
        if self.monthly_limit == 0:
            return Decimal('0.00')
        ratio = self.current_spent / self.monthly_limit
        return ratio.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

    def remaining_budget(self):
        return self.monthly_limit - self.current_spent

    def alert_level(self):
        ratio = self.calculate_usage_ratio()
        if ratio >= Decimal('1.00'):
            return 'danger'
        if ratio >= Decimal('0.80'):
            return 'warning'
        return 'normal'

    def badge_class(self):
        return {
            'normal': 'success',
            'warning': 'warning',
            'danger': 'danger',
        }[self.alert_level()]


class Expense(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='expenses')
    category = models.ForeignKey(Category, on_delete=models.PROTECT, related_name='expenses')
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    date = models.DateField()
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-date', '-created_at']

    def __str__(self):
        return f'{self.category.name} - {self.amount}'
