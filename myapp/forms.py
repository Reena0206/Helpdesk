from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User
from .models import UserProfile, TaskDetail, Account, user_comment
from django.contrib.auth.forms import PasswordChangeForm

# LoginForm
class LoginForm(forms.Form):
    username = forms.CharField(
        label='Username',
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Enter your username'})
    )
    password = forms.CharField(
        label='Password',
        widget=forms.PasswordInput(attrs={'class': 'form-control', 'placeholder': 'Enter your password'})
    )

# RegisterForm
class RegisterForm(UserCreationForm):
    first_name = forms.CharField(
        label='First Name',
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Enter your first name'})
    )
    last_name = forms.CharField(
        label='Last Name',
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Enter your last name'})
    )
    username = forms.CharField(
        label='Username',
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Enter your username'})
    )
    email = forms.EmailField(
        label='Email Address',
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Enter your email address'})
    )
    password1 = forms.CharField(
        label='Password',
        widget=forms.PasswordInput(attrs={'class': 'form-control', 'placeholder': 'Enter your password'})
    )
    password2 = forms.CharField(
        label='Confirm Password',
        widget=forms.PasswordInput(attrs={'class': 'form-control', 'placeholder': 'Confirm your password'})
    )

    class Meta:
        model = User
        fields = ('first_name', 'last_name', 'username', 'email', 'password1', 'password2')

# UserProfileForm
class UserProfileForm(forms.ModelForm):
    Address = forms.CharField(
        label='Address',
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Enter your address'})
    )
    City = forms.CharField(
        label='City',
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Enter your city'})
    )
    State = forms.CharField(
        label='State',
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Enter your state'})
    )

    class Meta:
        model = UserProfile
        fields = ('Address', 'City', 'State')

# CustomPasswordChangeForm
class CustomPasswordChangeForm(PasswordChangeForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['old_password'].widget.attrs.update({'placeholder': 'Enter your current password'})
        self.fields['new_password1'].widget.attrs.update({'placeholder': 'Enter a new password'})
        self.fields['new_password2'].widget.attrs.update({'placeholder': 'Confirm your new password'})

# TaskDetailForm
class TaskDetailForm(forms.ModelForm):
    task_title = forms.CharField(
        label='Task Title',
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Enter the task title'})
    )
    task_description = forms.CharField(
        label='Task Description',
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Enter the task description'})
    )
    task_due_date = forms.DateField(
        label="Task Due Date",
        widget=forms.DateInput(attrs={'class': 'form-control', 'placeholder': 'YYYY-MM-DD'},
                               format='%Y-%m-%d')  # Define the date format here
    )
    task_reward = forms.IntegerField(
        label="Task Reward",
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Enter the task reward'})
    )

    class Meta:
        model = TaskDetail
        fields = ('task_title', 'task_description', 'task_due_date', 'task_reward')

# AccountDetailsForm
class AccountDetailsForm(forms.ModelForm):
    account_holder = forms.ModelChoiceField(
        label='Account Holder',
        queryset=User.objects.all(),
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    account_balance = forms.IntegerField(
        label='Account Balance',
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Enter the account balance'})
    )

    class Meta:
        model = Account
        fields = ('account_holder', 'account_balance')


# user_comment Form
class UserCommentForm(forms.ModelForm):
    class Meta:
        model = user_comment
        fields = ('reopen_comment', 'closing_comment','textfile')
        widgets= {
            'reopen_comment': forms.Textarea(attrs={'row':3,'cols':20}),
            'closing_comment': forms.Textarea(attrs={'row':3,'cols':20}),

        }