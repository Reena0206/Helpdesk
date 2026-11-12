from django import template
from django.utils.html import format_html
from django.utils.safestring import mark_safe

from ..activity import kind_of

register = template.Library()

AVATAR_COLORS = ['#2563eb', '#0e7490', '#7a5af8', '#c11574', '#b54708', '#067647', '#4f46e5', '#475467']


@register.filter
def display_name(user):
    if not user:
        return 'System'
    return user.get_full_name() or user.username


@register.filter
def initials(user):
    if not user:
        return '?'
    parts = [p for p in (user.first_name, user.last_name) if p]
    if parts:
        return ''.join(p[0] for p in parts[:2]).upper()
    return user.username[:2].upper()


@register.simple_tag
def avatar(user, size='md'):
    """A coloured circle with the user's initials."""
    if not user:
        return format_html('<span class="avatar avatar-{} avatar-empty" title="Unassigned"><i class="bi bi-person"></i></span>', size)
    color = AVATAR_COLORS[sum(map(ord, user.username)) % len(AVATAR_COLORS)]
    return format_html(
        '<span class="avatar avatar-{}" style="--avatar-bg:{}" title="{}">{}</span>',
        size, color, display_name(user), initials(user),
    )


@register.inclusion_tag('partials/status_chip.html')
def status_chip(ticket):
    return {'key': ticket.status, 'label': ticket.get_status_display()}


@register.inclusion_tag('partials/priority_chip.html')
def priority_chip(ticket):
    return {'key': ticket.priority, 'label': ticket.get_priority_display()}


@register.filter
def stars(value):
    """Render a 1–5 rating as star icons."""
    try:
        value = int(value)
    except (TypeError, ValueError):
        return ''
    return format_html(
        '<span class="stars" title="{} out of 5">{}{}</span>', value,
        mark_safe('<i class="bi bi-star-fill"></i>' * max(0, min(value, 5))),
        mark_safe('<i class="bi bi-star"></i>' * max(0, 5 - value)),
    )


@register.filter
def short_duration(value):
    """timedelta → compact text: '2d 4h', '5h 10m', '12m'. Empty value → '—'."""
    if not value:
        return '—'
    minutes = int(value.total_seconds() // 60)
    days, rem = divmod(minutes, 60 * 24)
    hours, mins = divmod(rem, 60)
    if days:
        return f'{days}d {hours}h' if hours else f'{days}d'
    if hours:
        return f'{hours}h {mins}m' if mins else f'{hours}h'
    return f'{max(mins, 1)}m'


@register.filter
def activity_kind(message):
    """Event type for an activity message: {'key', 'label', 'icon', 'tone'}."""
    return kind_of(message or '')


@register.simple_tag
def priority_icon(key):
    icons = {'low': 'bi-chevron-down', 'medium': 'bi-dash-lg', 'high': 'bi-chevron-up', 'urgent': 'bi-chevron-double-up'}
    return icons.get(key, 'bi-dash')
