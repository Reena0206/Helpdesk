"""
Event types for the ticket activity log.

Activity messages are written by ``services.py`` and always start with one of the
prefixes below, so the type can be derived from the message without a schema change.
"""

from django.db.models import Q

# key, label, Bootstrap icon, tone (see .tone-* in app.css), message prefixes
KINDS = [
    ('created', 'Ticket created', 'bi-plus-lg', 'primary', ['Ticket created']),
    ('assigned', 'Assigned / taken', 'bi-person-check', 'violet', ['Took the ticket', 'Assigned to']),
    ('reply', 'Reply', 'bi-chat-left-text', 'info', ['Added a reply']),
    ('note', 'Internal note', 'bi-sticky', 'warning', ['Added an internal note']),
    ('hold', 'Put on hold', 'bi-pause-fill', 'warning', ['Put on hold']),
    ('resumed', 'Resumed', 'bi-play-fill', 'info', ['Resumed']),
    ('resolved', 'Resolved', 'bi-check2-circle', 'success', ['Marked as resolved']),
    ('reopened', 'Reopened', 'bi-arrow-counterclockwise', 'danger', ['Reopened']),
    ('closed', 'Closed', 'bi-lock', 'slate', ['Closed']),
    ('released', 'Released', 'bi-box-arrow-left', 'slate', ['Released']),
    ('edited', 'Edited', 'bi-pencil', 'slate', ['Edited']),
]
KIND_CHOICES = [(k, label) for k, label, *_ in KINDS]
_BY_KEY = {k[0]: k for k in KINDS}
_OTHER = {'key': 'other', 'label': 'Update', 'icon': 'bi-dot', 'tone': 'slate'}


def kind_of(message):
    """Return {'key', 'label', 'icon', 'tone'} for an activity message."""
    for key, label, icon, tone, prefixes in KINDS:
        if any(message.startswith(p) for p in prefixes):
            return {'key': key, 'label': label, 'icon': icon, 'tone': tone}
    return _OTHER


def kind_q(key):
    """Q object matching activities of the given type."""
    q = Q()
    for prefix in _BY_KEY[key][4]:
        q |= Q(message__startswith=prefix)
    return q
