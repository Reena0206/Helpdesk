"""Ticket trend data for the dashboard chart (raised vs. resolved over a time range)."""

from datetime import date, datetime, time, timedelta

from django.utils import timezone

RANGE_CHOICES = [
    ('today', 'Today'),
    ('2d', 'Last 2 days'),
    ('7d', 'Last 7 days'),
    ('30d', 'Last 30 days'),
    ('custom', 'Custom range'),
]
DEFAULT_RANGE = '7d'
MAX_CUSTOM_DAYS = 366


class RangeError(ValueError):
    pass


def _parse_date(value, name):
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError):
        raise RangeError(f'Please choose a valid "{name}" date.')


def _midnight(d):
    return timezone.make_aware(datetime.combine(d, time.min))


def build_trend(tickets, key=DEFAULT_RANGE, start=None, end=None):
    """
    Count tickets raised and resolved in each bucket of the chosen range.

    today  → 24 hourly buckets        2d   → 16 three-hour buckets
    7d/30d → daily buckets            custom → daily (≤ 62 days) or weekly buckets
    """
    today = timezone.localdate()

    if key == 'today':
        buckets = [_midnight(today) + timedelta(hours=h) for h in range(24)]
        size, label_fmt, title = timedelta(hours=1), '%H:%M', 'Today, by hour'
    elif key == '2d':
        first = _midnight(today - timedelta(days=1))
        buckets = [first + timedelta(hours=3 * i) for i in range(16)]
        size, label_fmt, title = timedelta(hours=3), '%a %H:%M', 'Last 2 days, every 3 hours'
    elif key in ('7d', '30d'):
        days = 7 if key == '7d' else 30
        buckets = [_midnight(today - timedelta(days=i)) for i in range(days - 1, -1, -1)]
        size, label_fmt, title = timedelta(days=1), '%d %b', f'Last {days} days'
    elif key == 'custom':
        d_from, d_to = _parse_date(start, 'From'), _parse_date(end, 'To')
        if d_from > d_to:
            raise RangeError('"From" must be on or before "To".')
        if d_to > today:
            raise RangeError('"To" cannot be in the future.')
        span = (d_to - d_from).days + 1
        if span > MAX_CUSTOM_DAYS:
            raise RangeError(f'Please choose a range of at most {MAX_CUSTOM_DAYS} days.')
        step = 1 if span <= 62 else 7
        buckets = [_midnight(d_from + timedelta(days=i)) for i in range(0, span, step)]
        size = timedelta(days=step)
        label_fmt = '%d %b' if step == 1 else 'Wk %d %b'
        title = f'{d_from:%d %b %Y} – {d_to:%d %b %Y}' + ('' if step == 1 else ', by week')
    else:
        raise RangeError('Unknown range.')

    range_start = buckets[0]
    range_end = buckets[-1] + size
    if key == 'custom':
        range_end = min(range_end, _midnight(_parse_date(end, 'To') + timedelta(days=1)))

    def count(field):
        counts = [0] * len(buckets)
        times = tickets.filter(**{f'{field}__gte': range_start, f'{field}__lt': range_end}).values_list(field, flat=True)
        for t in times:
            index = int((t - range_start) / size)
            if 0 <= index < len(counts):
                counts[index] += 1
        return counts

    created, resolved = count('created_at'), count('resolved_at')

    # Same-length window immediately before, for the "vs previous period" comparison.
    length = range_end - range_start
    prev_start = range_start - length

    def total_before(field):
        return tickets.filter(**{f'{field}__gte': prev_start, f'{field}__lt': range_start}).count()

    days = round(length / timedelta(days=1))
    prev_label = {'today': 'yesterday'}.get(key, f'previous {days} day{"s" if days != 1 else ""}')

    return {
        'range': key,
        'title': title,
        'labels': [timezone.localtime(b).strftime(label_fmt) for b in buckets],
        'created': created,
        'resolved': resolved,
        'total_created': sum(created),
        'total_resolved': sum(resolved),
        'prev_created': total_before('created_at'),
        'prev_resolved': total_before('resolved_at'),
        'prev_label': prev_label,
    }


# --- Team performance -------------------------------------------------------

TEAM_PERIODS = [('7d', 'Last 7 days'), ('30d', 'Last 30 days'), ('90d', 'Last 90 days'), ('all', 'All time')]
TEAM_SORTS = [('workload', 'Workload'), ('resolved', 'Most resolved'), ('rating', 'Best rated'), ('name', 'Name')]


def staff_users():
    """Everyone who can work on tickets: agents, admins and superusers."""
    from django.contrib.auth.models import User
    from django.db.models import Q
    from .models import UserProfile
    return User.objects.filter(
        Q(is_superuser=True) | Q(profile__role__in=[UserProfile.ROLE_AGENT, UserProfile.ROLE_ADMIN]),
        is_active=True,
    ).distinct()


def team_stats(period='30d', search='', sort='workload'):
    """
    One row per agent with workload and performance figures.

    Workload numbers (active, on hold, overdue) are always "right now";
    resolved, rating, resolution time and coins earned cover the chosen period.
    """
    from django.db.models import Avg, Count, Max, Q, Sum
    from .models import Ticket, TicketActivity, Transaction

    today = timezone.localdate()
    since = None if period == 'all' else _midnight(today - timedelta(days={'7d': 7, '30d': 30, '90d': 90}.get(period, 30) - 1))
    in_period = (lambda field: Q(**{f'{field}__gte': since})) if since else (lambda field: Q(**{f'{field}__isnull': False}))

    users = staff_users().select_related('profile')
    if search:
        users = users.filter(Q(first_name__icontains=search) | Q(last_name__icontains=search)
                             | Q(username__icontains=search) | Q(email__icontains=search)
                             | Q(profile__department__icontains=search))
    active = Q(tickets_assigned__status__in=Ticket.ACTIVE_STATUSES)
    users = users.annotate(
        active_n=Count('tickets_assigned', filter=active, distinct=True),
        on_hold_n=Count('tickets_assigned', filter=Q(tickets_assigned__status=Ticket.STATUS_ON_HOLD), distinct=True),
        overdue_n=Count('tickets_assigned', filter=active & Q(tickets_assigned__due_date__lt=today), distinct=True),
        urgent_n=Count('tickets_assigned', filter=active & Q(tickets_assigned__priority=Ticket.PRIORITY_URGENT), distinct=True),
        resolved_n=Count('tickets_assigned', filter=in_period('tickets_assigned__resolved_at'), distinct=True),
        rating_avg=Avg('tickets_assigned__rating', filter=in_period('tickets_assigned__closed_at')),
        rating_n=Count('tickets_assigned__rating', filter=in_period('tickets_assigned__closed_at')),
    )
    agents = list(users)
    ids = [a.pk for a in agents]

    # Average time from "raised" to "resolved" (computed in Python: portable across databases).
    durations = {}
    resolved_q = Ticket.objects.filter(assigned_to_id__in=ids, resolved_at__isnull=False)
    if since:
        resolved_q = resolved_q.filter(resolved_at__gte=since)
    for agent_id, created, resolved in resolved_q.values_list('assigned_to_id', 'created_at', 'resolved_at'):
        durations.setdefault(agent_id, []).append(resolved - created)

    earned_q = Transaction.objects.filter(kind=Transaction.KIND_REWARD, receiver_id__in=ids)
    if since:
        earned_q = earned_q.filter(created_at__gte=since)
    earned = dict(earned_q.values_list('receiver_id').annotate(s=Sum('amount')))
    last_seen = dict(TicketActivity.objects.filter(actor_id__in=ids).values_list('actor_id').annotate(m=Max('created_at')))

    max_load = max([a.active_n for a in agents] + [1])
    for a in agents:
        spans = durations.get(a.pk)
        a.avg_resolution = sum(spans, timedelta()) / len(spans) if spans else None
        a.coins_earned = earned.get(a.pk, 0)
        a.last_active = last_seen.get(a.pk)
        a.load_pct = round(100 * a.active_n / max_load)

    sort_keys = {
        'workload': lambda a: (-a.active_n, -a.overdue_n, (a.get_full_name() or a.username).lower()),
        'resolved': lambda a: (-a.resolved_n, (a.get_full_name() or a.username).lower()),
        'rating': lambda a: (-(a.rating_avg or 0), -a.rating_n, (a.get_full_name() or a.username).lower()),
        'name': lambda a: (a.get_full_name() or a.username).lower(),
    }
    agents.sort(key=sort_keys.get(sort, sort_keys['workload']))
    return agents
