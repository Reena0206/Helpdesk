from django.db import models
from django.contrib.auth.models import User
# Create your models here.
#UserProfile Model
class UserProfile(models.Model):
    user =models.OneToOneField(User,on_delete=models.CASCADE,null=True)
    Address = models.CharField(max_length=100)
    City = models.CharField(max_length=100)
    State =models.CharField(max_length=100)

#Task Detail
class TaskDetail(models.Model):
    task_title = models.CharField(max_length=100)
    task_created_by = models.ForeignKey(User,related_name='created_by',on_delete=models.CASCADE,null=True)
    task_closed_by = models.ForeignKey(User,related_name='closed_by',on_delete=models.CASCADE,null=True)
    task_created_on = models.DateField(auto_now_add=True,null=True)
    task_closed_on = models.DateField(null=True)
    task_description = models.CharField(max_length=300)
    task_due_date = models.DateField()
    task_reward = models.IntegerField()
    task_holder = models.CharField(max_length=100,null=True)
    choice = [('Open','Open'),('Inprocess','Inprocess'),('Pending','Pending'),('Closed','Closed'),('Reopen','Reopen'),('Resolved','Resolved')]
    task_status = models.CharField(max_length=100,choices=choice,default='Open')

#MyCart
class my_cart(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    task = models.ForeignKey(TaskDetail, on_delete=models.CASCADE)  # Add this line
    task_count = models.IntegerField(default=1)

#Account Model
class Account(models.Model):
    account_holder = models.OneToOneField(User,on_delete=models.CASCADE)
    account_balance = models.IntegerField()

#transaction_model
class transaction(models.Model):
    sender = models.ForeignKey(User,related_name='sender',on_delete=models.CASCADE,null=True)
    receiver = models.ForeignKey(User,related_name='receiver',on_delete=models.CASCADE,null=True)
    amount = models.IntegerField()
    timestamp = models.DateTimeField(auto_now_add=True,null=True)

#user_comment model
class user_comment(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    task = models.ForeignKey(TaskDetail, on_delete=models.CASCADE)  # Add this line
    reopen_comment = models.TextField(null=True)
    closing_comment = models.TextField(null=True)
    textfile = models.FileField(upload_to='acccepted_attachment/',null=True)





