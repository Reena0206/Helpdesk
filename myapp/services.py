"""
Ticket workflow.

    Open ──take/assign──► In Progress ◄──resume── On Hold
      ▲                     │    └────hold────────►┘
      └────release──────────┤
                            ▼
                         Resolved ──close──► Closed (reward paid, rating saved)
                            │
                          reopen
                            ▼
                         Reopened ──resolve / take / assign──► ...

Every change is validated against ``permissions.available_actions`` and
recorded in the ticket's activity log.
"""

import logging

from django.conf import settings
from django.core.mail import send_mail
from django.db import transaction as db_transaction
from django.utils import timezone

from .models import Account, Ticket, TicketActivity, TicketComment, Transaction
from .permissions import available_actions, get_wallet, is_staff_member

logger = logging.getLogger(__name__)


class WorkflowError(Exception):
    """Raised when a ticket action is not allowed or cannot be completed."""


def _display(user):
    return (user.get_full_name() or user.username) if user else 'System'


def log_activity(ticket, actor, message):
    return TicketActivity.objects.create(ticket=ticket, actor=actor, message=message)


def notify(users, subject, body):
    """Email the given users. Uses the console backend unless SMTP is configured."""
    recipients = sorted({u.email for u in users if u and u.email})
    if not recipients:
        return
    try:
        send_mail(f'[HelpDesk] {subject}', body, settings.DEFAULT_FROM_EMAIL, recipients, fail_silently=False)
    except Exception:  # Email problems must never break the helpdesk itself.
        logger.exception('Could not send notification email')


def _require(actor, ticket, action):
    if action not in available_actions(actor, ticket):
        raise WorkflowError(f'You cannot "{action}" ticket {ticket.number} in its current state.')


# --- Actions ----------------------------------------------------------------

def create_ticket(ticket, actor):
    ticket.created_by = actor
    ticket.status = Ticket.STATUS_OPEN
    ticket.save()
    log_activity(ticket, actor, 'Ticket created')
    return ticket


def assign(ticket, actor, agent):
    _require(actor, ticket, 'assign')
    if not is_staff_member(agent):
        raise WorkflowError(f'{agent.username} is not a support agent.')
    if agent.pk == ticket.created_by_id:
        raise WorkflowError('A ticket cannot be assigned to the person who raised it.')
    ticket.assigned_to = agent
    if ticket.status in (Ticket.STATUS_OPEN, Ticket.STATUS_REOPENED):
        ticket.status = Ticket.STATUS_IN_PROGRESS
    ticket.save()
    if agent == actor:
        log_activity(ticket, actor, 'Took the ticket')
    else:
        log_activity(ticket, actor, f'Assigned to {_display(agent)}')
        notify([agent], f'{ticket.number} assigned to you', f'"{ticket.title}" has been assigned to you by {_display(actor)}.')
    notify([ticket.created_by], f'{ticket.number} is being worked on',
           f'{_display(agent)} is now working on your ticket "{ticket.title}".')


def take(ticket, actor):
    _require(actor, ticket, 'take')
    assign(ticket, actor, actor)


def release(ticket, actor):
    _require(actor, ticket, 'release')
    previous = ticket.assigned_to
    ticket.assigned_to = None
    ticket.status = Ticket.STATUS_OPEN
    ticket.save()
    log_activity(ticket, actor, f'Released ticket (was assigned to {_display(previous)})')


def hold(ticket, actor, reason=''):
    _require(actor, ticket, 'hold')
    ticket.status = Ticket.STATUS_ON_HOLD
    ticket.save()
    log_activity(ticket, actor, 'Put on hold' + (f': {reason}' if reason else ''))
    notify([ticket.created_by], f'{ticket.number} is on hold',
           f'Your ticket "{ticket.title}" is on hold.' + (f'\n\nReason: {reason}' if reason else ''))


def resume(ticket, actor):
    _require(actor, ticket, 'resume')
    ticket.status = Ticket.STATUS_IN_PROGRESS
    ticket.save()
    log_activity(ticket, actor, 'Resumed work')


def resolve(ticket, actor, resolution):
    _require(actor, ticket, 'resolve')
    if not resolution.strip():
        raise WorkflowError('Please describe how the issue was resolved.')
    ticket.status = Ticket.STATUS_RESOLVED
    ticket.resolution = resolution.strip()
    ticket.resolved_at = timezone.now()
    ticket.save()
    log_activity(ticket, actor, 'Marked as resolved')
    notify([ticket.created_by], f'{ticket.number} has been resolved',
           f'Your ticket "{ticket.title}" was resolved.\n\nResolution:\n{ticket.resolution}\n\n'
           'Please log in to close it, or reopen it if the problem is not fixed.')


def reopen(ticket, actor, reason):
    _require(actor, ticket, 'reopen')
    if not reason.strip():
        raise WorkflowError('Please explain why the ticket is being reopened.')
    ticket.status = Ticket.STATUS_REOPENED
    ticket.resolved_at = None
    ticket.save()
    TicketComment.objects.create(ticket=ticket, author=actor, body=f'Reopened: {reason.strip()}')
    log_activity(ticket, actor, 'Reopened the ticket')
    notify([ticket.assigned_to], f'{ticket.number} was reopened', f'"{ticket.title}" was reopened.\n\nReason: {reason}')


def close(ticket, actor, rating=None, feedback=''):
    """Close a resolved ticket, save the rating and pay the reward to the agent."""
    _require(actor, ticket, 'close')
    with db_transaction.atomic():
        ticket = Ticket.objects.select_for_update().get(pk=ticket.pk)
        if ticket.status != Ticket.STATUS_RESOLVED:
            raise WorkflowError('Only resolved tickets can be closed.')

        agent = ticket.assigned_to
        paid = 0
        if ticket.reward and agent and agent.pk != ticket.created_by_id:
            get_wallet(ticket.created_by)
            get_wallet(agent)
            payer = Account.objects.select_for_update().get(user=ticket.created_by)
            payee = Account.objects.select_for_update().get(user=agent)
            if payer.balance < ticket.reward:
                raise WorkflowError(
                    f'{_display(ticket.created_by)} has {payer.balance} coins but the reward is '
                    f'{ticket.reward}. Top up the wallet before closing.'
                )
            payer.balance -= ticket.reward
            payee.balance += ticket.reward
            payer.save()
            payee.save()
            Transaction.objects.create(
                kind=Transaction.KIND_REWARD, sender=ticket.created_by, receiver=agent,
                amount=ticket.reward, ticket=ticket, note=f'Reward for {ticket.number}',
            )
            paid = ticket.reward

        ticket.status = Ticket.STATUS_CLOSED
        ticket.closed_at = timezone.now()
        ticket.rating = rating
        ticket.feedback = feedback.strip()
        ticket.save()

        message = 'Closed the ticket'
        if rating:
            message += f' (rated {rating}/5)'
        if paid:
            message += f'; paid {paid} coins to {_display(agent)}'
        log_activity(ticket, actor, message)

    notify([agent], f'{ticket.number} closed', f'"{ticket.title}" was closed by {_display(actor)}.'
           + (f' You received {paid} coins.' if paid else ''))
    return ticket


def add_comment(ticket, actor, comment):
    comment.ticket = ticket
    comment.author = actor
    if not is_staff_member(actor):
        comment.is_internal = False
    comment.save()
    if comment.is_internal:
        log_activity(ticket, actor, 'Added an internal note')
    else:
        log_activity(ticket, actor, 'Added a reply')
        others = [ticket.created_by, ticket.assigned_to]
        notify([u for u in others if u and u != actor], f'New reply on {ticket.number}',
               f'{_display(actor)} wrote on "{ticket.title}":\n\n{comment.body}')
    return comment


def top_up(user, amount, actor, note=''):
    if amount <= 0:
        raise WorkflowError('Amount must be positive.')
    with db_transaction.atomic():
        get_wallet(user)
        wallet = Account.objects.select_for_update().get(user=user)
        wallet.balance += amount
        wallet.save()
        Transaction.objects.create(
            kind=Transaction.KIND_TOPUP, sender=None, receiver=user, amount=amount,
            note=note or f'Top-up by {_display(actor)}',
        )
    return wallet
