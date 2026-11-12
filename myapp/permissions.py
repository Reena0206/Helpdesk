"""Who may do what. Views, templates and the workflow all use these rules."""

from .models import Account, Ticket, UserProfile


def get_profile(user):
    """Return the user's profile, creating it for users that predate the signal."""
    try:
        return user.profile
    except UserProfile.DoesNotExist:
        role = UserProfile.ROLE_ADMIN if user.is_superuser else UserProfile.ROLE_CUSTOMER
        profile, _ = UserProfile.objects.get_or_create(user=user, defaults={'role': role})
        return profile


def get_wallet(user):
    wallet, _ = Account.objects.get_or_create(user=user)
    return wallet


def is_admin(user):
    return user.is_authenticated and (user.is_superuser or get_profile(user).role == UserProfile.ROLE_ADMIN)


def is_staff_member(user):
    """Agents and admins handle tickets."""
    return user.is_authenticated and (user.is_superuser or get_profile(user).is_staff_member)


def can_view(user, ticket):
    return is_staff_member(user) or ticket.created_by_id == user.id


def can_edit(user, ticket):
    if ticket.status == Ticket.STATUS_CLOSED:
        return False
    if is_admin(user):
        return True
    return ticket.created_by_id == user.id and ticket.status == Ticket.STATUS_OPEN and ticket.assigned_to_id is None


def can_delete(user, ticket):
    if is_admin(user):
        return True
    return ticket.created_by_id == user.id and ticket.status == Ticket.STATUS_OPEN and ticket.assigned_to_id is None


def can_comment(user, ticket):
    return can_view(user, ticket) and ticket.status != Ticket.STATUS_CLOSED


def available_actions(user, ticket):
    """Return the set of workflow actions ``user`` may perform on ``ticket`` right now."""
    actions = set()
    if not user.is_authenticated:
        return actions

    staff = is_staff_member(user)
    admin = is_admin(user)
    is_creator = ticket.created_by_id == user.id
    is_assignee = ticket.assigned_to_id is not None and ticket.assigned_to_id == user.id
    S = Ticket

    if staff and not is_creator and ticket.assigned_to_id is None and ticket.status in (S.STATUS_OPEN, S.STATUS_REOPENED):
        actions.add('take')
    if staff and ticket.is_active:
        actions.add('assign')
    if (is_assignee or admin) and ticket.assigned_to_id is not None:
        if ticket.status in (S.STATUS_IN_PROGRESS, S.STATUS_ON_HOLD, S.STATUS_REOPENED):
            actions.update({'release', 'resolve'})
        if ticket.status in (S.STATUS_IN_PROGRESS, S.STATUS_REOPENED):
            actions.add('hold')
        if ticket.status == S.STATUS_ON_HOLD:
            actions.add('resume')
    if (is_creator or admin) and ticket.status == S.STATUS_RESOLVED:
        actions.update({'reopen', 'close'})
    return actions
