from django.contrib.auth import views as auth_views
from django.urls import path, reverse_lazy

from . import views
from .forms import LoginForm, StyledPasswordChangeForm, StyledPasswordResetForm, StyledSetPasswordForm

urlpatterns = [
    path('', views.dashboard, name='dashboard'),

    # Tickets
    path('tickets/', views.ticket_list, name='ticket_list'),
    path('tickets/new/', views.ticket_create, name='ticket_create'),
    path('tickets/<int:pk>/', views.ticket_detail, name='ticket_detail'),
    path('tickets/<int:pk>/edit/', views.ticket_edit, name='ticket_edit'),
    path('tickets/<int:pk>/delete/', views.ticket_delete, name='ticket_delete'),
    path('tickets/<int:pk>/comment/', views.ticket_comment, name='ticket_comment'),
    path('tickets/<int:pk>/<str:action>/', views.ticket_action, name='ticket_action'),

    # Profile, wallet, users
    path('profile/', views.profile, name='profile'),
    path('profile/edit/', views.profile_edit, name='profile_edit'),
    path('wallet/', views.wallet, name='wallet'),
    path('wallet/topup/', views.wallet_topup, name='wallet_topup'),
    path('users/', views.user_list, name='user_list'),
    path('activity/', views.activity_log, name='activity_log'),
    path('team/', views.team, name='team'),
    path('dashboard/trend/', views.dashboard_trend, name='dashboard_trend'),
    path('users/<int:pk>/role/', views.user_set_role, name='user_set_role'),

    # Auth
    path('register/', views.register, name='register'),
    path('login/', auth_views.LoginView.as_view(
        template_name='accounts/login.html', authentication_form=LoginForm, redirect_authenticated_user=True,
    ), name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('password-change/', auth_views.PasswordChangeView.as_view(
        template_name='password/password_change_form.html', form_class=StyledPasswordChangeForm,
        success_url=reverse_lazy('password_change_done'),
    ), name='password_change'),
    path('password-change/done/', auth_views.PasswordChangeDoneView.as_view(
        template_name='password/password_change_done.html',
    ), name='password_change_done'),
    path('password-reset/', auth_views.PasswordResetView.as_view(
        template_name='password/password_reset_form.html', form_class=StyledPasswordResetForm,
    ), name='password_reset'),
    path('password-reset/done/', auth_views.PasswordResetDoneView.as_view(
        template_name='password/password_reset_done.html',
    ), name='password_reset_done'),
    path('password-reset/<uidb64>/<token>/', auth_views.PasswordResetConfirmView.as_view(
        template_name='password/password_reset_confirm.html', form_class=StyledSetPasswordForm,
    ), name='password_reset_confirm'),
    path('password-reset/complete/', auth_views.PasswordResetCompleteView.as_view(
        template_name='password/password_reset_complete.html',
    ), name='password_reset_complete'),
]
