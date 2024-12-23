from django.contrib import admin
from .models import UserProfile, TaskDetail, my_cart, Account, transaction,user_comment
# Register your models here.

#UserProfile Admin
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ['Address','City','State']

admin.site.register(UserProfile,UserProfileAdmin)

#Task Details
class TaskDetailsAdmin(admin.ModelAdmin):
    list_display = ['id','task_title','task_created_by','task_closed_by','task_created_on','task_closed_on','task_description','task_due_date','task_reward','task_holder','task_status']

admin.site.register(TaskDetail,TaskDetailsAdmin)

#my_cart Details
class my_cartAdmin(admin.ModelAdmin):
    list_display = ['id','user','task','task_count']

admin.site.register(my_cart,my_cartAdmin)

#Account Admin
class AccountAdmin(admin.ModelAdmin):
    list_display = ['id','account_holder','account_balance']

admin.site.register(Account,AccountAdmin)


#Transaction Admin
class transactionAdmin(admin.ModelAdmin):
    list_display = ['id','sender','receiver','amount','timestamp']
admin.site.register(transaction,transactionAdmin)

#User_comment
class user_commentAdmin(admin.ModelAdmin):
    list_display = ['id','user','task','reopen_comment','closing_comment','textfile']
admin.site.register(user_comment,user_commentAdmin)