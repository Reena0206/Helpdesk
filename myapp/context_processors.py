from pathlib import Path

from django.conf import settings
from django.utils import timezone

from .models import Ticket
from .permissions import get_profile, get_wallet, is_admin, is_staff_member

# Shown on the login page in DEBUG mode (created by `manage.py seed_demo`).
DEMO_ACCOUNTS = [
    ('admin', 'Site Admin', 'Admin', 'Admin@123'),
    ('priya', 'Priya Sharma', 'Agent', 'Demo@1234'),
    ('rahul', 'Rahul Verma', 'Agent', 'Demo@1234'),
    ('anita', 'Anita Desai', 'Customer', 'Demo@1234'),
    ('vikram', 'Vikram Singh', 'Customer', 'Demo@1234'),
    ('neha', 'Neha Gupta', 'Customer', 'Demo@1234'),
]


STATIC_DIR = Path(__file__).resolve().parent / 'static' / 'myapp'


def asset_version():
    """Changes whenever app.css / app.js change, so browsers never use a stale cached copy."""
    try:
        return str(int(max((STATIC_DIR / name).stat().st_mtime for name in ('app.css', 'app.js'))))
    except OSError:
        return '1'


def user_role(request):
    """Role flags and sidebar counters available to every template."""
    context = {'show_demo_accounts': settings.DEBUG, 'asset_version': asset_version()}
    if settings.DEBUG:
        context['demo_accounts'] = DEMO_ACCOUNTS
    user = getattr(request, 'user', None)
    if not user or not user.is_authenticated:
        return context

    staff = is_staff_member(user)
    active = Ticket.objects.filter(status__in=Ticket.ACTIVE_STATUSES)
    nav_counts = {
        'my_active': active.filter(created_by=user).count(),
        'awaiting_me': Ticket.objects.filter(created_by=user, status=Ticket.STATUS_RESOLVED).count(),
    }
    if staff:
        nav_counts.update({
            'queue': active.filter(assigned_to=user).count(),
            'unassigned': active.filter(assigned_to__isnull=True).count(),
            'overdue': active.filter(due_date__lt=timezone.localdate()).count(),
        })
    context.update({
        'is_staff_member': staff,
        'is_admin_user': is_admin(user),
        'current_profile': get_profile(user),
        'nav_wallet': get_wallet(user),
        'nav_counts': nav_counts,
    })
    return context
