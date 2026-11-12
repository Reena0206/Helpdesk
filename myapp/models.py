import os

from django.conf import settings
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone

ALLOWED_ATTACHMENT_EXTENSIONS = {
    '.png', '.jpg', '.jpeg', '.gif', '.pdf', '.txt', '.log', '.csv',
    '.doc', '.docx', '.xls', '.xlsx', '.zip',
}


def validate_attachment(file):
    ext = os.path.splitext(file.name)[1].lower()
    if ext not in ALLOWED_ATTACHMENT_EXTENSIONS:
        raise ValidationError(
            f'Unsupported file type "{ext}". Allowed: {", ".join(sorted(ALLOWED_ATTACHMENT_EXTENSIONS))}'
        )
    limit = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024
    if file.size > limit:
        raise ValidationError(f'File too large. Maximum size is {settings.MAX_UPLOAD_SIZE_MB} MB.')


# --- Users ------------------------------------------------------------------

class UserProfile(models.Model):
    ROLE_CUSTOMER = 'customer'
    ROLE_AGENT = 'agent'
    ROLE_ADMIN = 'admin'
    ROLE_CHOICES = [
        (ROLE_CUSTOMER, 'Customer'),
        (ROLE_AGENT, 'Support Agent'),
        (ROLE_ADMIN, 'Administrator'),
    ]

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default=ROLE_CUSTOMER)
    phone = models.CharField(max_length=20, blank=True)
    department = models.CharField(max_length=100, blank=True)
    address = models.CharField(max_length=200, blank=True)
    city = models.CharField(max_length=100, blank=True)
    state = models.CharField(max_length=100, blank=True)

    def __str__(self):
        return f'{self.user.username} ({self.get_role_display()})'

    @property
    def is_admin(self):
        return self.role == self.ROLE_ADMIN or self.user.is_superuser

    @property
    def is_staff_member(self):
        """Agents and admins can work on tickets."""
        return self.role in (self.ROLE_AGENT, self.ROLE_ADMIN) or self.user.is_superuser


# --- Tickets ----------------------------------------------------------------

class Category(models.Model):
    name = models.CharField(max_length=100, unique=True)
    description = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ['name']
        verbose_name_plural = 'categories'

    def __str__(self):
        return self.name


class Ticket(models.Model):
    STATUS_OPEN = 'open'
    STATUS_IN_PROGRESS = 'in_progress'
    STATUS_ON_HOLD = 'on_hold'
    STATUS_RESOLVED = 'resolved'
    STATUS_CLOSED = 'closed'
    STATUS_REOPENED = 'reopened'
    STATUS_CHOICES = [
        (STATUS_OPEN, 'Open'),
        (STATUS_IN_PROGRESS, 'In Progress'),
        (STATUS_ON_HOLD, 'On Hold'),
        (STATUS_RESOLVED, 'Resolved'),
        (STATUS_CLOSED, 'Closed'),
        (STATUS_REOPENED, 'Reopened'),
    ]
    ACTIVE_STATUSES = (STATUS_OPEN, STATUS_IN_PROGRESS, STATUS_ON_HOLD, STATUS_REOPENED)

    PRIORITY_LOW = 'low'
    PRIORITY_MEDIUM = 'medium'
    PRIORITY_HIGH = 'high'
    PRIORITY_URGENT = 'urgent'
    PRIORITY_CHOICES = [
        (PRIORITY_LOW, 'Low'),
        (PRIORITY_MEDIUM, 'Medium'),
        (PRIORITY_HIGH, 'High'),
        (PRIORITY_URGENT, 'Urgent'),
    ]

    STATUS_BADGES = {
        STATUS_OPEN: 'primary',
        STATUS_IN_PROGRESS: 'info',
        STATUS_ON_HOLD: 'warning',
        STATUS_RESOLVED: 'success',
        STATUS_CLOSED: 'secondary',
        STATUS_REOPENED: 'danger',
    }
    PRIORITY_BADGES = {
        PRIORITY_LOW: 'secondary',
        PRIORITY_MEDIUM: 'info',
        PRIORITY_HIGH: 'warning',
        PRIORITY_URGENT: 'danger',
    }

    title = models.CharField(max_length=150)
    description = models.TextField()
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True, blank=True, related_name='tickets')
    priority = models.CharField(max_length=10, choices=PRIORITY_CHOICES, default=PRIORITY_MEDIUM)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_OPEN)

    created_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='tickets_created')
    assigned_to = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name='tickets_assigned'
    )

    due_date = models.DateField(null=True, blank=True)
    reward = models.PositiveIntegerField(
        default=0, help_text='Coins paid to the agent when the requester closes the ticket.'
    )
    attachment = models.FileField(upload_to='ticket_attachments/', blank=True, validators=[validate_attachment])

    resolution = models.TextField(blank=True)
    rating = models.PositiveSmallIntegerField(
        null=True, blank=True, validators=[MinValueValidator(1), MaxValueValidator(5)]
    )
    feedback = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    closed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.number} - {self.title}'

    @property
    def number(self):
        return f'HD-{self.pk:05d}' if self.pk else 'HD-NEW'

    @property
    def is_active(self):
        return self.status in self.ACTIVE_STATUSES

    @property
    def is_overdue(self):
        return bool(self.due_date and self.is_active and self.due_date < timezone.localdate())

    @property
    def due_hint(self):
        """Short relative description of the due date for active tickets, e.g. 'in 3 days'."""
        if not self.due_date or not self.is_active:
            return ''
        days = (self.due_date - timezone.localdate()).days
        if days == 0:
            return 'due today'
        if days == 1:
            return 'tomorrow'
        if days > 1:
            return f'in {days} days'
        return f'overdue by {-days} day{"s" if days != -1 else ""}'

    @property
    def stage(self):
        """Position in the 4-step progress bar: Raised, Being worked on, Resolved, Closed."""
        return {
            self.STATUS_OPEN: 0,
            self.STATUS_RESOLVED: 2,
            self.STATUS_CLOSED: 3,
        }.get(self.status, 1)

    @property
    def status_badge(self):
        return self.STATUS_BADGES.get(self.status, 'secondary')

    @property
    def priority_badge(self):
        return self.PRIORITY_BADGES.get(self.priority, 'secondary')

    @property
    def attachment_name(self):
        return os.path.basename(self.attachment.name) if self.attachment else ''


class TicketComment(models.Model):
    ticket = models.ForeignKey(Ticket, on_delete=models.CASCADE, related_name='comments')
    author = models.ForeignKey(User, on_delete=models.CASCADE, related_name='ticket_comments')
    body = models.TextField()
    is_internal = models.BooleanField(
        default=False, help_text='Internal notes are visible to support staff only.'
    )
    attachment = models.FileField(upload_to='comment_attachments/', blank=True, validators=[validate_attachment])
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        return f'Comment by {self.author} on {self.ticket.number}'

    @property
    def attachment_name(self):
        return os.path.basename(self.attachment.name) if self.attachment else ''


class TicketActivity(models.Model):
    ticket = models.ForeignKey(Ticket, on_delete=models.CASCADE, related_name='activities')
    actor = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='ticket_activities')
    message = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name_plural = 'ticket activities'

    def __str__(self):
        return f'{self.ticket.number}: {self.message}'


# --- Wallet -----------------------------------------------------------------

class Account(models.Model):
    """Coin wallet. Requesters can offer coin rewards that are paid to the agent on close."""

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='wallet')
    balance = models.PositiveIntegerField(default=0)

    def __str__(self):
        return f'{self.user.username}: {self.balance} coins'


class Transaction(models.Model):
    KIND_TOPUP = 'topup'
    KIND_REWARD = 'reward'
    KIND_CHOICES = [
        (KIND_TOPUP, 'Top-up'),
        (KIND_REWARD, 'Ticket reward'),
    ]

    kind = models.CharField(max_length=10, choices=KIND_CHOICES)
    sender = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='sent_transactions')
    receiver = models.ForeignKey(User, on_delete=models.CASCADE, related_name='received_transactions')
    amount = models.PositiveIntegerField()
    ticket = models.ForeignKey(Ticket, on_delete=models.SET_NULL, null=True, blank=True, related_name='transactions')
    note = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.get_kind_display()}: {self.amount} to {self.receiver}'
