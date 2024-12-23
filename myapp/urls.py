from django.contrib import admin
from django.urls import path, include
from .import views
from django.contrib.auth import views as auth_views
from django.urls import reverse_lazy
from django.contrib.auth.views import PasswordChangeView, PasswordChangeDoneView
from .forms import CustomPasswordChangeForm

urlpatterns = [
    path('base/', views.basepage,name='base'),
    path('login/', views.loginpage,name='login'),
    path('logout/', views.logoutpage,name='logout'),
    path('register/', views.registerpage,name='register'),
    path('password_reset/', auth_views.PasswordResetView.as_view(template_name='password_reset_form.html'),name='password_reset'),
    path('password_reset_done/', auth_views.PasswordResetDoneView.as_view(template_name='password_reset_done.html'),name='password_reset_done'),
    path('password_reset_confirm/<uidb64>/<token>/', auth_views.PasswordResetConfirmView.as_view(template_name='password_reset_confirm.html'),name='password_reset_confirm'),
    path('password_reset_complete/', auth_views.PasswordResetCompleteView.as_view(template_name='password_reset_complete.html'),name='password_reset_complete'),
    # path('ChangePassword/',views.Change_Password,name='ChangePassword'),
    path('password_change/', PasswordChangeView.as_view(form_class=CustomPasswordChangeForm), name='password_change'),
    path('password_change_done/', auth_views.PasswordChangeDoneView.as_view(), name='password_change_done'),
    path('profile/',views.User_Profile,name='profile'),
    path('update_profile/<int:pk>',views.update_profile,name='update_profile'),
    path('taskdetails/',views.TaskDetails,name='taskdetails'),
    path('taskinfo/<int:pk>',views.TaskInfo,name='taskinfo'),
    path('update_task/<int:pk>',views.update_task,name='update_task'),
    path('delete_task/<int:pk>',views.delete_task,name='delete_task'),
    path('accept_task/<int:pk>',views.accept_task,name='accept_task'),
    path('my_cart',views.my_carts,name='my_cart'),
    path('remove_task/<int:pk>',views.remove_task,name='remove_task'),
    path('closed_task/<int:pk>',views.closed_task,name='closed_task'),
    path('reopen_task/<int:pk>',views.reopen_task,name='reopen_task'),
    path('resolved_task/<int:pk>',views.resolved_task,name='resolved_task'),
    path('accounts/',views.AccountDetails,name='accounts'),
    path('transactions/',views.transactions,name='transactions'),












    
    




    
]
