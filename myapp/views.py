import csv
from datetime import datetime, time, timedelta

from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db.models import Avg, Case, Count, F, IntegerField, Q, Value, When
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from . import services
from .activity import kind_of, kind_q
from .reports import (
    DEFAULT_RANGE, RANGE_CHOICES, TEAM_PERIODS, TEAM_SORTS, RangeError, build_trend, staff_users, team_stats,
)
from .forms import (
    ActivityFilterForm, AssignForm, CloseForm, CommentForm, HoldForm, ProfileUpdateForm, RegisterForm, ReopenForm,
    ResolveForm, RoleForm, TicketFilterForm, TicketForm, TopUpForm, UserUpdateForm,
)
from .models import Ticket, TicketActivity, Transaction, UserProfile
from .permissions import (
    available_actions, can_comment, can_delete, can_edit, can_view, get_profile, get_wallet,
    is_admin, is_staff_member,
)


def admin_required(view):
    @login_required
    def wrapper(request, *args, **kwargs):
        if not is_admin(request.user):
            raise PermissionDenied
        return view(request, *args, **kwargs)
    wrapper.__name__ = view.__name__
    return wrapper


def staff_required(view):
    @login_required
    def wrapper(request, *args, **kwargs):
        if not is_staff_member(request.user):
            raise PermissionDenied
        return view(request, *args, **kwargs)
    wrapper.__name__ = view.__name__
    return wrapper


def visible_tickets(user):
    qs = Ticket.objects.select_related('created_by', 'assigned_to', 'category')
    return qs if is_staff_member(user) else qs.filter(created_by=user)


def get_ticket_for(user, pk):
    ticket = get_object_or_404(Ticket.objects.select_related('created_by', 'assigned_to', 'category'), pk=pk)
    if not can_view(user, ticket):
        raise Http404  # Don't reveal that the ticket exists.
    return ticket


# --- Auth -------------------------------------------------------------------

def register(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
    form = RegisterForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        user = form.save()
        login(request, user)
        messages.success(request, f'Welcome, {user.first_name}! Your account has been created.')
        return redirect('dashboard')
    return render(request, 'accounts/register.html', {'form': form})


@require_POST
def logout_view(request):
    logout(request)
    messages.success(request, 'You have been logged out.')
    return redirect('login')


# --- Dashboard --------------------------------------------------------------

# Doughnut chart + legend colours (soft tones, readable in light and dark themes).
STATUS_CHART_COLORS = {
    Ticket.STATUS_OPEN: '#528bff',
    Ticket.STATUS_IN_PROGRESS: '#9b8afb',
    Ticket.STATUS_ON_HOLD: '#fdb022',
    Ticket.STATUS_RESOLVED: '#32d583',
    Ticket.STATUS_CLOSED: '#98a2b3',
    Ticket.STATUS_REOPENED: '#f97066',
}

@login_required
def dashboard(request):
    user = request.user
    staff = is_staff_member(user)
    tickets = visible_tickets(user)
    today = timezone.localdate()

    counts = dict(tickets.values_list('status').annotate(n=Count('id')))
    total = sum(counts.values())
    status_cards = [
        {'key': key, 'label': label, 'count': counts.get(key, 0), 'color': STATUS_CHART_COLORS[key],
         'pct': round(100 * counts.get(key, 0) / total) if total else 0}
        for key, label in Ticket.STATUS_CHOICES
    ]
    active = tickets.filter(status__in=Ticket.ACTIVE_STATUSES)

    context = {
        'status_cards': status_cards,
        'status_chart': {
            'labels': [c['label'] for c in status_cards],
            'colors': [c['color'] for c in status_cards],
            'data': [c['count'] for c in status_cards],
        },
        'trend': build_trend(tickets, DEFAULT_RANGE),
        'trend_ranges': RANGE_CHOICES,
        'default_range': DEFAULT_RANGE,
        'total': tickets.count(),
        'active_count': active.count(),
        'overdue_count': active.filter(due_date__lt=today).count(),
        'resolved_count': tickets.filter(status__in=[Ticket.STATUS_RESOLVED, Ticket.STATUS_CLOSED]).count(),
        'recent_tickets': tickets[:6],
        'awaiting_me': tickets.filter(created_by=user, status=Ticket.STATUS_RESOLVED)[:5],
        'wallet': get_wallet(user),
    }
    if staff:
        agents = team_stats(period='all')
        active_total = context['active_count']
        by_priority = dict(active.values_list('priority').annotate(n=Count('id')))
        priority_counts = [
            {
                'key': key, 'label': label, 'count': by_priority.get(key, 0),
                'pct': round(100 * by_priority.get(key, 0) / active_total) if active_total else 0,
                'overdue': active.filter(priority=key, due_date__lt=today).count(),
            }
            for key, label in reversed(Ticket.PRIORITY_CHOICES)  # urgent first
        ]
        ratings = Ticket.objects.filter(rating__isnull=False).aggregate(avg=Avg('rating'), n=Count('id'))
        context.update({
            'unassigned_count': active.filter(assigned_to__isnull=True).count(),
            'my_queue': active.filter(assigned_to=user).order_by(F('due_date').asc(nulls_last=True))[:6],
            'my_queue_count': active.filter(assigned_to=user).count(),
            'priority_counts': priority_counts,
            'avg_rating': ratings['avg'],
            'rating_count': ratings['n'],
            'recent_activity': TicketActivity.objects.select_related('ticket', 'actor')[:7],
            'agents': agents[:4],
            'agents_total': len(agents),
        })
    return render(request, 'dashboard.html', context)


@login_required
def dashboard_trend(request):
    """JSON data for the dashboard chart when the user changes the range."""
    try:
        data = build_trend(
            visible_tickets(request.user), request.GET.get('range', DEFAULT_RANGE),
            request.GET.get('from'), request.GET.get('to'),
        )
    except RangeError as exc:
        return JsonResponse({'error': str(exc)}, status=400)
    return JsonResponse(data)


# --- Team -------------------------------------------------------------------

@staff_required
def team(request):
    period = request.GET.get('period') if request.GET.get('period') in dict(TEAM_PERIODS) else '30d'
    sort = request.GET.get('sort') if request.GET.get('sort') in dict(TEAM_SORTS) else 'workload'
    search = request.GET.get('q', '').strip()
    agents = team_stats(period=period, search=search, sort=sort)

    rated = [a for a in agents if a.rating_n]
    rating_total = sum(a.rating_n for a in rated)
    spans = [a.avg_resolution for a in agents if a.avg_resolution]
    summary = {
        'agents': len(agents),
        'active': sum(a.active_n for a in agents),
        'unassigned': Ticket.objects.filter(status__in=Ticket.ACTIVE_STATUSES, assigned_to__isnull=True).count(),
        'overdue': sum(a.overdue_n for a in agents),
        'resolved': sum(a.resolved_n for a in agents),
        'rating': (sum(a.rating_avg * a.rating_n for a in rated) / rating_total) if rating_total else None,
        'rating_n': rating_total,
        'avg_resolution': (sum(spans, timedelta()) / len(spans)) if spans else None,
    }
    return render(request, 'team/list.html', {
        'agents': agents, 'summary': summary, 'period': period, 'sort': sort, 'q': search,
        'periods': TEAM_PERIODS, 'sorts': TEAM_SORTS, 'period_label': dict(TEAM_PERIODS)[period],
    })


# --- Activity log -----------------------------------------------------------

@login_required
def activity_log(request):
    user = request.user
    staff = is_staff_member(user)
    activities = TicketActivity.objects.select_related('ticket', 'actor')
    if not staff:
        # Customers see the history of their own tickets, without staff-only notes.
        activities = activities.filter(ticket__created_by=user).exclude(kind_q('note'))

    form = ActivityFilterForm(request.GET or None, staff=staff)
    if form.is_valid():
        data = form.cleaned_data
        q = data.get('q')
        if q:
            cond = Q(message__icontains=q) | Q(ticket__title__icontains=q)
            digits = q.upper().replace('HD-', '').strip()
            if digits.isdigit():
                cond |= Q(ticket_id=int(digits))
            activities = activities.filter(cond)
        if data.get('kind'):
            activities = activities.filter(kind_q(data['kind']))
        if data.get('actor'):
            activities = activities.filter(actor=data['actor'])
        if data.get('date_from'):
            activities = activities.filter(created_at__gte=timezone.make_aware(datetime.combine(data['date_from'], time.min)))
        if data.get('date_to'):
            activities = activities.filter(created_at__lt=timezone.make_aware(datetime.combine(data['date_to'] + timedelta(days=1), time.min)))

    if staff and request.GET.get('export') == 'csv':
        return export_activity_csv(activities)

    today = timezone.localdate()
    base = TicketActivity.objects.all() if staff else TicketActivity.objects.filter(ticket__created_by=user)
    stats = {
        'today': base.filter(created_at__gte=timezone.make_aware(datetime.combine(today, time.min))).count(),
        'week': base.filter(created_at__gte=timezone.make_aware(datetime.combine(today - timedelta(days=6), time.min))).count(),
        'resolved_week': base.filter(kind_q('resolved'), created_at__gte=timezone.make_aware(datetime.combine(today - timedelta(days=6), time.min))).count(),
        'closed_week': base.filter(kind_q('closed'), created_at__gte=timezone.make_aware(datetime.combine(today - timedelta(days=6), time.min))).count(),
    }

    page = Paginator(activities, 30).get_page(request.GET.get('page'))
    query = request.GET.copy()
    query.pop('page', None)
    query.pop('export', None)
    return render(request, 'activity/list.html', {
        'form': form, 'page': page, 'query': query.urlencode(), 'stats': stats,
        'has_filters': any(request.GET.get(k) for k in ('q', 'kind', 'actor', 'date_from', 'date_to')),
    })


def export_activity_csv(activities):
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="helpdesk-activity-{timezone.localdate():%Y%m%d}.csv"'
    writer = csv.writer(response)
    writer.writerow(['Time', 'Ticket', 'Ticket title', 'User', 'Event', 'Details'])
    for a in activities.iterator():
        writer.writerow([
            timezone.localtime(a.created_at).strftime('%Y-%m-%d %H:%M'), a.ticket.number, a.ticket.title,
            (a.actor.get_full_name() or a.actor.username) if a.actor else 'System',
            kind_of(a.message)['label'], a.message,
        ])
    return response


# --- Tickets ----------------------------------------------------------------

PRIORITY_ORDER = Case(
    When(priority=Ticket.PRIORITY_URGENT, then=Value(0)),
    When(priority=Ticket.PRIORITY_HIGH, then=Value(1)),
    When(priority=Ticket.PRIORITY_MEDIUM, then=Value(2)),
    default=Value(3),
    output_field=IntegerField(),
)
SORTS = {
    'newest': ['-created_at'],
    'oldest': ['created_at'],
    'updated': ['-updated_at'],
    'priority': [PRIORITY_ORDER, '-created_at'],
    'due': [F('due_date').asc(nulls_last=True), '-created_at'],
}


@login_required
def ticket_list(request):
    user = request.user
    staff = is_staff_member(user)
    form = TicketFilterForm(request.GET or None, staff=staff)
    tickets = visible_tickets(user)
    status = sort = ''

    if form.is_valid():
        data = form.cleaned_data
        q = data.get('q')
        if q:
            cond = Q(title__icontains=q) | Q(description__icontains=q)
            digits = q.upper().replace('HD-', '').strip()
            if digits.isdigit():
                cond |= Q(pk=int(digits))
            tickets = tickets.filter(cond)
        scope = data.get('scope')
        if scope == 'mine':
            tickets = tickets.filter(created_by=user)
        elif scope == 'assigned':
            tickets = tickets.filter(assigned_to=user)
        elif scope == 'unassigned':
            tickets = tickets.filter(assigned_to__isnull=True, status__in=Ticket.ACTIVE_STATUSES)
        elif scope == 'overdue':
            tickets = tickets.filter(due_date__lt=timezone.localdate(), status__in=Ticket.ACTIVE_STATUSES)
        if data.get('priority'):
            tickets = tickets.filter(priority=data['priority'])
        if data.get('category'):
            tickets = tickets.filter(category=data['category'])
        status = data.get('status') or ''
        sort = data.get('sort') or ''

    assignee = None
    if staff and request.GET.get('assignee', '').isdigit():
        assignee = staff_users().filter(pk=int(request.GET['assignee'])).first()
        if assignee:
            tickets = tickets.filter(assigned_to=assignee)

    # Status tabs show counts for the current filters (before the status filter itself).
    counts = dict(tickets.values_list('status').annotate(n=Count('id')))
    base_query = request.GET.copy()
    for key in ('status', 'page'):
        base_query.pop(key, None)
    tabs = [
        {'key': '', 'label': 'All', 'count': sum(counts.values())},
        {'key': 'active', 'label': 'Active', 'count': sum(counts.get(s, 0) for s in Ticket.ACTIVE_STATUSES)},
    ] + [{'key': k, 'label': label, 'count': counts.get(k, 0)} for k, label in Ticket.STATUS_CHOICES]

    if status == 'active':
        tickets = tickets.filter(status__in=Ticket.ACTIVE_STATUSES)
    elif status:
        tickets = tickets.filter(status=status)
    tickets = tickets.order_by(*SORTS.get(sort, SORTS['newest']))

    page = Paginator(tickets, 15).get_page(request.GET.get('page'))
    query = request.GET.copy()
    query.pop('page', None)
    has_filters = any(request.GET.get(k) for k in ('q', 'priority', 'category', 'scope', 'sort', 'assignee'))
    return render(request, 'tickets/list.html', {
        'form': form, 'page': page, 'query': query.urlencode(), 'tabs': tabs,
        'current_status': status, 'base_qs': base_query.urlencode(), 'has_filters': has_filters, 'assignee': assignee,
    })


@login_required
def ticket_create(request):
    form = TicketForm(request.POST or None, request.FILES or None, user=request.user)
    if request.method == 'POST' and form.is_valid():
        ticket = services.create_ticket(form.save(commit=False), request.user)
        messages.success(request, f'Ticket {ticket.number} has been raised. Our team will pick it up soon.')
        return redirect('ticket_detail', pk=ticket.pk)
    return render(request, 'tickets/form.html', {'form': form, 'title': 'Raise a new ticket'})


@login_required
def ticket_detail(request, pk):
    ticket = get_ticket_for(request.user, pk)
    staff = is_staff_member(request.user)
    comments = ticket.comments.select_related('author__profile')
    if not staff:
        comments = comments.filter(is_internal=False)
    actions = available_actions(request.user, ticket)
    return render(request, 'tickets/detail.html', {
        'ticket': ticket,
        'comments': comments,
        'activities': ticket.activities.select_related('actor'),
        'actions': actions,
        'can_edit': can_edit(request.user, ticket),
        'can_delete': can_delete(request.user, ticket),
        'can_comment': can_comment(request.user, ticket),
        'comment_form': CommentForm(staff=staff),
        'assign_form': AssignForm(ticket=ticket, initial={'agent': ticket.assigned_to}) if 'assign' in actions else None,
        'resolve_form': ResolveForm(),
        'hold_form': HoldForm(),
        'reopen_form': ReopenForm(),
        'close_form': CloseForm(),
    })


@login_required
def ticket_edit(request, pk):
    ticket = get_ticket_for(request.user, pk)
    if not can_edit(request.user, ticket):
        messages.error(request, 'This ticket can no longer be edited.')
        return redirect('ticket_detail', pk=pk)
    form = TicketForm(request.POST or None, request.FILES or None, instance=ticket, user=request.user)
    if request.method == 'POST' and form.is_valid():
        changed = ', '.join(form.changed_data)
        form.save()
        if changed:
            services.log_activity(ticket, request.user, f'Edited ticket ({changed})')
        messages.success(request, 'Ticket updated.')
        return redirect('ticket_detail', pk=pk)
    return render(request, 'tickets/form.html', {'form': form, 'ticket': ticket, 'title': f'Edit {ticket.number}'})


@login_required
def ticket_delete(request, pk):
    ticket = get_ticket_for(request.user, pk)
    if not can_delete(request.user, ticket):
        messages.error(request, 'Only open, unassigned tickets can be deleted.')
        return redirect('ticket_detail', pk=pk)
    if request.method == 'POST':
        number = ticket.number
        ticket.delete()
        messages.success(request, f'Ticket {number} deleted.')
        return redirect('ticket_list')
    return render(request, 'tickets/confirm_delete.html', {'ticket': ticket})


@login_required
@require_POST
def ticket_action(request, pk, action):
    ticket = get_ticket_for(request.user, pk)
    user = request.user
    try:
        if action == 'take':
            services.take(ticket, user)
            messages.success(request, f'You are now working on {ticket.number}.')
        elif action == 'assign':
            form = AssignForm(request.POST, ticket=ticket)
            if not form.is_valid():
                raise services.WorkflowError('Please choose an agent.')
            agent = form.cleaned_data['agent']
            services.assign(ticket, user, agent)
            messages.success(request, f'{ticket.number} assigned to {agent.get_full_name() or agent.username}.')
        elif action == 'release':
            services.release(ticket, user)
            messages.info(request, f'{ticket.number} returned to the open queue.')
        elif action == 'hold':
            form = HoldForm(request.POST)
            services.hold(ticket, user, form.data.get('reason', '').strip())
            messages.info(request, f'{ticket.number} is on hold.')
        elif action == 'resume':
            services.resume(ticket, user)
            messages.success(request, f'Work resumed on {ticket.number}.')
        elif action == 'resolve':
            services.resolve(ticket, user, request.POST.get('resolution', ''))
            messages.success(request, f'{ticket.number} marked as resolved. The requester will be asked to confirm.')
        elif action == 'reopen':
            services.reopen(ticket, user, request.POST.get('reason', ''))
            messages.warning(request, f'{ticket.number} has been reopened.')
        elif action == 'close':
            form = CloseForm(request.POST)
            if not form.is_valid():
                raise services.WorkflowError('Invalid rating.')
            services.close(ticket, user, form.cleaned_data['rating'], form.cleaned_data['feedback'])
            messages.success(request, f'{ticket.number} closed. Thank you for your feedback!')
        else:
            raise Http404
    except services.WorkflowError as exc:
        messages.error(request, str(exc))
    return redirect('ticket_detail', pk=pk)


@login_required
@require_POST
def ticket_comment(request, pk):
    ticket = get_ticket_for(request.user, pk)
    if not can_comment(request.user, ticket):
        messages.error(request, 'Comments are closed for this ticket.')
        return redirect('ticket_detail', pk=pk)
    form = CommentForm(request.POST, request.FILES, staff=is_staff_member(request.user))
    if form.is_valid():
        comment = services.add_comment(ticket, request.user, form.save(commit=False))
        messages.success(request, 'Internal note added.' if comment.is_internal else 'Reply posted.')
    else:
        errors = '; '.join(e for errs in form.errors.values() for e in errs)
        messages.error(request, f'Could not post comment: {errors}')
    return redirect(reverse('ticket_detail', args=[pk]) + '#conversation')


# --- Profile & wallet -------------------------------------------------------

@login_required
def profile(request):
    user = request.user
    raised = Ticket.objects.filter(created_by=user)
    stats = {
        'raised': raised.count(),
        'open': raised.filter(status__in=Ticket.ACTIVE_STATUSES).count(),
        'closed': raised.filter(status=Ticket.STATUS_CLOSED).count(),
    }
    if is_staff_member(user):
        handled = Ticket.objects.filter(assigned_to=user)
        stats.update({
            'assigned': handled.filter(status__in=Ticket.ACTIVE_STATUSES).count(),
            'resolved': handled.filter(status__in=[Ticket.STATUS_RESOLVED, Ticket.STATUS_CLOSED]).count(),
            'rating': handled.filter(rating__isnull=False).aggregate(v=Avg('rating'))['v'],
        })
    return render(request, 'accounts/profile.html', {
        'profile': get_profile(user), 'wallet': get_wallet(user), 'stats': stats,
    })


@login_required
def profile_edit(request):
    user_form = UserUpdateForm(request.POST or None, instance=request.user)
    profile_form = ProfileUpdateForm(request.POST or None, instance=get_profile(request.user))
    if request.method == 'POST' and user_form.is_valid() and profile_form.is_valid():
        user_form.save()
        profile_form.save()
        messages.success(request, 'Profile updated.')
        return redirect('profile')
    return render(request, 'accounts/profile_edit.html', {'user_form': user_form, 'profile_form': profile_form})


@login_required
def wallet(request):
    user = request.user
    transactions = Transaction.objects.filter(Q(sender=user) | Q(receiver=user)).select_related('sender', 'receiver', 'ticket')
    page = Paginator(transactions, 20).get_page(request.GET.get('page'))
    return render(request, 'wallet/wallet.html', {'wallet': get_wallet(user), 'page': page})


@admin_required
def wallet_topup(request):
    form = TopUpForm(request.POST or None, initial={'user': request.GET.get('user')})
    if request.method == 'POST' and form.is_valid():
        target = form.cleaned_data['user']
        w = services.top_up(target, form.cleaned_data['amount'], request.user, form.cleaned_data['note'])
        messages.success(request, f'Added {form.cleaned_data["amount"]} coins to {target.username}. New balance: {w.balance}.')
        return redirect('user_list')
    return render(request, 'wallet/topup.html', {'form': form})


# --- User management (admin) -----------------------------------------------

@admin_required
def user_list(request):
    users = User.objects.select_related('profile', 'wallet').annotate(
        raised=Count('tickets_created', distinct=True),
        handling=Count('tickets_assigned', filter=Q(tickets_assigned__status__in=Ticket.ACTIVE_STATUSES), distinct=True),
    ).order_by('profile__role', 'username')
    role_counts = dict(UserProfile.objects.values_list('role').annotate(n=Count('id')))
    return render(request, 'accounts/user_list.html', {
        'users': users, 'roles': UserProfile.ROLE_CHOICES, 'role_counts': role_counts,
    })


@admin_required
@require_POST
def user_set_role(request, pk):
    target = get_object_or_404(User, pk=pk)
    form = RoleForm(request.POST)
    if not form.is_valid():
        messages.error(request, 'Invalid role.')
    elif target == request.user and form.cleaned_data['role'] != UserProfile.ROLE_ADMIN:
        messages.error(request, 'You cannot remove your own admin role.')
    else:
        p = get_profile(target)
        p.role = form.cleaned_data['role']
        p.save()
        messages.success(request, f'{target.username} is now {p.get_role_display()}.')
    return redirect('user_list')
