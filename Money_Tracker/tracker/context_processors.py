import re
from datetime import date

from .models import Budget


def budget_alerts(request):
    if not request.user.is_authenticated:
        return {'budget_alerts': []}

    month_year = request.GET.get('month', '')
    if not re.fullmatch(r'\d{4}-(0[1-9]|1[0-2])', month_year):
        month_year = date.today().strftime('%Y-%m')

    seen_alerts = set(request.session.get('seen_budget_alerts', []))
    new_alerts = []
    budgets = Budget.objects.filter(
        user=request.user,
        month_year=month_year,
    ).select_related('category')

    for budget in budgets:
        alert_level = budget.alert_level()
        if alert_level == 'normal':
            continue

        threshold = 100 if alert_level == 'danger' else 80
        alert_key = f'{budget.pk}:{month_year}:{threshold}'
        if alert_key in seen_alerts:
            continue

        seen_alerts.add(alert_key)
        new_alerts.append({
            'category': budget.category.name,
            'usage_percent': budget.calculate_usage_ratio() * 100,
            'alert_level': alert_level,
            'threshold': threshold,
        })

    if new_alerts:
        request.session['seen_budget_alerts'] = sorted(seen_alerts)[-100:]

    return {'budget_alerts': new_alerts}