from django import forms
from django.contrib.auth.forms import (
    AuthenticationForm, PasswordChangeForm, PasswordResetForm, SetPasswordForm, UserCreationForm,
)
from django.contrib.auth.models import User
from django.db.models import Q
from django.utils import timezone

from .activity import KIND_CHOICES
from .models import Category, Ticket, TicketComment, UserProfile
from .permissions import get_wallet


class BootstrapMixin:
    """Adds Bootstrap classes to every widget."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            widget = field.widget
            if isinstance(widget, (forms.CheckboxInput,)):
                css = 'form-check-input'
            elif isinstance(widget, (forms.Select, forms.SelectMultiple)):
                css = 'form-select'
            else:
                css = 'form-control'
            widget.attrs['class'] = f"{widget.attrs.get('class', '')} {css}".strip()

    def full_clean(self):
        super().full_clean()
        for name in self.errors:
            if name in self.fields:
                widget = self.fields[name].widget
                widget.attrs['class'] = f"{widget.attrs.get('class', '')} is-invalid".strip()


# --- Accounts ---------------------------------------------------------------

class LoginForm(BootstrapMixin, AuthenticationForm):
    pass


class RegisterForm(BootstrapMixin, UserCreationForm):
    first_name = forms.CharField(max_length=150)
    last_name = forms.CharField(max_length=150)
    email = forms.EmailField()
    phone = forms.CharField(max_length=20, required=False)
    department = forms.CharField(max_length=100, required=False)
    address = forms.CharField(max_length=200, required=False)
    city = forms.CharField(max_length=100, required=False)
    state = forms.CharField(max_length=100, required=False)

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ('first_name', 'last_name', 'username', 'email')

    def clean_email(self):
        email = self.cleaned_data['email'].lower()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError('An account with this email already exists.')
        return email

    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data['email']
        user.first_name = self.cleaned_data['first_name']
        user.last_name = self.cleaned_data['last_name']
        if commit:
            user.save()  # signal creates profile + wallet
            profile = user.profile
            for name in ('phone', 'department', 'address', 'city', 'state'):
                setattr(profile, name, self.cleaned_data.get(name, ''))
            profile.save()
        return user


class UserUpdateForm(BootstrapMixin, forms.ModelForm):
    email = forms.EmailField()

    class Meta:
        model = User
        fields = ('first_name', 'last_name', 'email')

    def clean_email(self):
        email = self.cleaned_data['email'].lower()
        if User.objects.filter(email__iexact=email).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError('Another account already uses this email.')
        return email


class ProfileUpdateForm(BootstrapMixin, forms.ModelForm):
    class Meta:
        model = UserProfile
        fields = ('phone', 'department', 'address', 'city', 'state')


class StyledPasswordChangeForm(BootstrapMixin, PasswordChangeForm):
    pass


class StyledPasswordResetForm(BootstrapMixin, PasswordResetForm):
    pass


class StyledSetPasswordForm(BootstrapMixin, SetPasswordForm):
    pass


# --- Tickets ----------------------------------------------------------------

class TicketForm(BootstrapMixin, forms.ModelForm):
    class Meta:
        model = Ticket
        fields = ('title', 'category', 'priority', 'description', 'due_date', 'reward', 'attachment')
        widgets = {
            'description': forms.Textarea(attrs={'rows': 6, 'placeholder': 'Describe the problem, steps to reproduce, and what you expected.'}),
            'due_date': forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d'),
            'title': forms.TextInput(attrs={'placeholder': 'Short summary of the issue'}),
        }
        help_texts = {
            'reward': 'Optional. Coins from your wallet paid to the agent when you close the ticket.',
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        self.fields['category'].empty_label = '— Select category —'
        self.fields['category'].required = True
        # Only the requester can offer their own coins.
        owner = self.instance.created_by if self.instance.pk else user
        if owner != user:
            self.fields.pop('reward')
        elif user is not None:
            self.fields['reward'].help_text += f' Your balance: {get_wallet(user).balance} coins.'

    def clean_due_date(self):
        due = self.cleaned_data.get('due_date')
        if due and due < timezone.localdate() and (not self.instance.pk or due != self.instance.due_date):
            raise forms.ValidationError('Due date cannot be in the past.')
        return due

    def clean_reward(self):
        reward = self.cleaned_data.get('reward') or 0
        if reward and self.user is not None and reward > get_wallet(self.user).balance:
            raise forms.ValidationError(f'You only have {get_wallet(self.user).balance} coins in your wallet.')
        return reward


class CommentForm(BootstrapMixin, forms.ModelForm):
    class Meta:
        model = TicketComment
        fields = ('body', 'attachment', 'is_internal')
        widgets = {'body': forms.Textarea(attrs={'rows': 3, 'placeholder': 'Write a reply...'})}
        labels = {'body': 'Reply', 'is_internal': 'Internal note (only visible to support staff)'}

    def __init__(self, *args, staff=False, **kwargs):
        super().__init__(*args, **kwargs)
        if not staff:
            self.fields.pop('is_internal')


class AssignForm(BootstrapMixin, forms.Form):
    agent = forms.ModelChoiceField(queryset=User.objects.none(), label='Assign to', empty_label='— Select agent —')

    def __init__(self, *args, ticket=None, **kwargs):
        super().__init__(*args, **kwargs)
        qs = User.objects.filter(
            Q(is_superuser=True) | Q(profile__role__in=[UserProfile.ROLE_AGENT, UserProfile.ROLE_ADMIN]),
            is_active=True,
        ).distinct().order_by('first_name', 'username')
        if ticket is not None:
            qs = qs.exclude(pk=ticket.created_by_id)
        self.fields['agent'].queryset = qs
        self.fields['agent'].label_from_instance = lambda u: u.get_full_name() or u.username


class ResolveForm(BootstrapMixin, forms.Form):
    resolution = forms.CharField(widget=forms.Textarea(attrs={'rows': 3}), label='Resolution summary')


class HoldForm(BootstrapMixin, forms.Form):
    reason = forms.CharField(required=False, max_length=200, label='Reason (optional)',
                             widget=forms.TextInput(attrs={'placeholder': 'e.g. Waiting for replacement part'}))


class ReopenForm(BootstrapMixin, forms.Form):
    reason = forms.CharField(widget=forms.Textarea(attrs={'rows': 3}), label='Why is the issue not fixed?')


class CloseForm(BootstrapMixin, forms.Form):
    RATING_CHOICES = [('', 'No rating')] + [(str(i), f'{i} ★') for i in range(5, 0, -1)]
    rating = forms.TypedChoiceField(choices=RATING_CHOICES, coerce=int, empty_value=None, required=False,
                                    label='How satisfied are you?')
    feedback = forms.CharField(required=False, widget=forms.Textarea(attrs={'rows': 2}), label='Feedback (optional)')


class TicketFilterForm(BootstrapMixin, forms.Form):
    SCOPE_CHOICES = [
        ('all', 'All tickets'),
        ('mine', 'Raised by me'),
        ('assigned', 'Assigned to me'),
        ('unassigned', 'Unassigned'),
        ('overdue', 'Overdue'),
    ]
    q = forms.CharField(required=False, label='Search',
                        widget=forms.TextInput(attrs={'placeholder': 'Search number, title or description'}))
    scope = forms.ChoiceField(choices=SCOPE_CHOICES, required=False)
    status = forms.ChoiceField(choices=[('', 'Any status'), ('active', 'Active (not resolved/closed)')] + Ticket.STATUS_CHOICES, required=False)
    priority = forms.ChoiceField(choices=[('', 'Any priority')] + Ticket.PRIORITY_CHOICES, required=False)
    category = forms.ModelChoiceField(queryset=Category.objects.all(), required=False, empty_label='Any category')
    SORT_CHOICES = [
        ('newest', 'Newest first'),
        ('oldest', 'Oldest first'),
        ('updated', 'Recently updated'),
        ('priority', 'Highest priority'),
        ('due', 'Due date'),
    ]
    sort = forms.ChoiceField(choices=SORT_CHOICES, required=False)

    def __init__(self, *args, staff=False, **kwargs):
        super().__init__(*args, **kwargs)
        if not staff:
            self.fields['scope'].choices = [('mine', 'Raised by me'), ('overdue', 'Overdue')]


# --- Admin tools ------------------------------------------------------------

class ActivityFilterForm(BootstrapMixin, forms.Form):
    q = forms.CharField(required=False, widget=forms.TextInput(attrs={'placeholder': 'Search ticket number, title or event…'}))
    kind = forms.ChoiceField(choices=[('', 'All events')] + KIND_CHOICES, required=False)
    actor = forms.ModelChoiceField(queryset=User.objects.none(), required=False, empty_label='Anyone')
    date_from = forms.DateField(required=False, widget=forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d'))
    date_to = forms.DateField(required=False, widget=forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d'))

    def __init__(self, *args, staff=False, **kwargs):
        super().__init__(*args, **kwargs)
        if staff:
            self.fields['actor'].queryset = User.objects.filter(ticket_activities__isnull=False).distinct().order_by('first_name', 'username')
            self.fields['actor'].label_from_instance = lambda u: u.get_full_name() or u.username
        else:
            self.fields.pop('actor')
            self.fields['kind'].choices = [c for c in self.fields['kind'].choices if c[0] != 'note']

    def clean(self):
        data = super().clean()
        if data.get('date_from') and data.get('date_to') and data['date_from'] > data['date_to']:
            raise forms.ValidationError('"From" date must be on or before the "To" date.')
        return data


class TopUpForm(BootstrapMixin, forms.Form):
    user = forms.ModelChoiceField(queryset=User.objects.filter(is_active=True).order_by('username'))
    amount = forms.IntegerField(min_value=1, max_value=100000)
    note = forms.CharField(required=False, max_length=200)


class RoleForm(forms.Form):
    role = forms.ChoiceField(choices=UserProfile.ROLE_CHOICES)
