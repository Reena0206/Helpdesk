from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login, logout
from django.contrib import messages
from .forms import *
from .models import *
from django.contrib.auth.views import PasswordChangeView
from django.urls import path
from django.utils import timezone
from django.shortcuts import get_object_or_404
from django.db.models import Q

# Base Page View

def basepage(request):
    if request.user.is_authenticated:
        taskdata = TaskDetail.objects.all()
        return render(request, 'base.html',{'taskdata':taskdata})
    else:
        messages.success(request,"You must have to login to see task!")
        return redirect('login')    
    

# Login View
def loginpage(request):
    if request.method == 'POST':
        form = LoginForm(request.POST)
        if form.is_valid():
            username = form.cleaned_data['username']
            password = form.cleaned_data['password']
            user = authenticate(request, username=username, password=password)
            if user is not None:
                login(request, user)
                messages.success(request, "Congrats on login")
                return redirect('base')  # Replace 'home' with your basepage URL name
            else:
                messages.error(request, "We couldn't find an account with that username. Try another, or get a new account!")
        # Render login page with form (including errors if any)
                return render(request, 'login.html', {'form': form})
    else:
        form = LoginForm()
        return render(request, 'login.html', {'form': form})

#Logout
def logoutpage(request):
    logout(request)
    messages.success(request,"You have been logout successfully")
    return redirect('login')

#RegisterView
def registerpage(request):
    if request.method == 'POST':
        Register_form = RegisterForm(request.POST)
        UserProfile_form = UserProfileForm(request.POST)
        
        if Register_form.is_valid() and UserProfile_form.is_valid():
            Registerform = Register_form.save()
            User_Profile = UserProfile_form.save(commit=False)
            Address = UserProfile_form.cleaned_data['Address']
            City = UserProfile_form.cleaned_data['City']
            State = UserProfile_form.cleaned_data['State']
            profile = UserProfile(user=Registerform ,Address=Address,City=City,State=State)
            profile.save()
            messages.success(request,'You have been Register Successfully')
            return redirect('login')
        else:
            messages.error(request,"You have not enter coreect data")
            return redirect('register')
    else:
        Register_form = RegisterForm()
        UserProfile_form = UserProfileForm()
        return render(request, 'register.html', {'Register_form':Register_form,'UserProfile_form':UserProfile_form})     
    
#Change Password
# def Change_Password(request):
    # if request.method == 'POST':
    #     fm =PasswordChangeForm(user=request.user,data=request.POST)
    #     if fm.is_valid():
    #         fm.save()
    #         update_session_auth_hash(request,fm.user)
    #         messages.success(request,'Your Password has been changed successfully!')
    #         return redirect('login')
    # else:
    #     fm = PasswordChangeForm(user=request.user)
    # return render(request,'Change_Password.html',{'fm':fm})

#User_Profile
def User_Profile(request):
    if request.user.is_authenticated:
        user = request.user
        ProfileDatas = UserProfile.objects.filter(user=user)
        AccountDatas = Account.objects.filter(account_holder=user)

        return render(request, 'userprofile.html', {
            'ProfileDatas': ProfileDatas,
            'AccountDatas': AccountDatas,
        })
    else:
        messages.success(request, "You must log in to see your profile!")
        return redirect('login')
    

#Update_Profile
def update_profile(request,pk):
    if request.user.is_authenticated:
        ProfileDatas = UserProfile.objects.get(id = pk)
        form = UserProfileForm(request.POST or None,instance=ProfileDatas)
        if form.is_valid():
            form.save()
            messages.success(request,"profile updated successfully")
            return redirect('profile')
        return render(request,'Update_profile.html',{'form':form})
    else:
        messages.success(request,"You must have to login to update profile!")
        return redirect('login')

#Task Creation function
def TaskDetails(request):
    if request.user.is_authenticated:
        if request.method == 'POST':
            form = TaskDetailForm(request.POST)
            if form.is_valid():
                Task = form.save(commit=False)
                Task.task_created_by = request.user
                
                Task.save()
                messages.success(request,"task created successfully")
            else:
                print(form.errors)
            return redirect('base')
        else:
            form = TaskDetailForm()
            return render(request,'TaskDetail.html',{'form':form})
    else:
        messages.success(request,"You must have to login to create task")
        return redirect('login')
        

#TaskInfo
def TaskInfo(request,pk):
    if request.user.is_authenticated:
        taskinfo = TaskDetail.objects.get(id=pk)
        return render(request,'taskinfo.html',{'taskinfo':taskinfo})

    else:
        messages.success(request,"You must have to login to see task!")
        return redirect('login') 


#Update_Task
def update_task(request,pk):
    if request.user.is_authenticated:
        TaskDatas = TaskDetail.objects.get(id = pk)
        form = TaskDetailForm(request.POST or None,instance=TaskDatas)
        if form.is_valid():
            form.save()
            messages.success(request,"task updated successfully")
            return redirect('base')
        return render(request,'Update_Task.html',{'form':form})
    else:
        messages.success(request,"You must have to login to update task!")
        return redirect('login')

#Delete_Task
def delete_task(request,pk):
    if request.user.is_authenticated:
        TaskDatas = TaskDetail.objects.get(id = pk)
        TaskDatas.delete()
        messages.success(request,"task deleted successfully")
        return redirect('base')
    else:
        messages.success(request,"You must have to login to delete task!")
        return redirect('login')
    
#Accept_Task
def accept_task(request,pk):
    if request.user.is_authenticated:
        current_user=request.user
        TaskDatas = TaskDetail.objects.get(id = pk)
        TaskDatas.task_status='Inprocess'
        TaskDatas.task_holder = str(current_user)
        TaskDatas.save()
        my_cart(user= current_user,task=TaskDatas).save()
        messages.success(request,"task accepted successfully")
        return redirect('base')
    else:
        messages.success(request,"You must have to login to accept task!")
        return redirect('login')
    
#my_cart
def my_carts(request):
    if request.user.is_authenticated:
        current_user=request.user
        cart = my_cart.objects.filter(user=current_user)
        return render(request,'my_cart.html',{'cart':cart})
        # messages.success(request,"task deleted successfully")
        # return redirect('base')
    else:
        messages.success(request,"You must have to login to view mycart task!")
        return redirect('login')
    
#remove_task
def remove_task(request,pk):
    if request.user.is_authenticated:
        TaskDatas = TaskDetail.objects.get(id = pk)
        TaskDatas.task_status='Open'
        TaskDatas.save()
        cart = my_cart.objects.filter(task=pk)
        cart.delete()
        messages.success(request,"task removed successfully")
        return redirect('base')
    else:
        messages.success(request,"You must have to login to accept task!")
        return redirect('login')


#closed_task
def closed_task(request,pk):
    if request.user.is_authenticated:
        current_user=request.user
        TaskDatas = TaskDetail.objects.get(id = pk)
        TaskDatas.task_status='Closed'
        TaskDatas.task_closed_by = current_user
        TaskDatas.task_closed_on = timezone.now()
        TaskDatas.save()
        cart = my_cart.objects.filter(task=pk)
        cart.delete()
        messages.success(request,"task closed successfully")
        return redirect('base')
    else:
        messages.success(request,"You must have to login to closed task!")
        return redirect('login')
    
#Reopen_Task
def reopen_task(request,pk):
    if request.user.is_authenticated:
        TaskDatas = TaskDetail.objects.get(id = pk)
        TaskDatas.task_status='Reopen'
        holder = User.objects.get(username= TaskDatas.task_closed_by)
        TaskDatas.save()
        my_cart(user= holder,task=TaskDatas).save()
        messages.success(request,"task reopen successfully")
        return redirect('base')
    else:
        messages.success(request,"You must have to login to reopen task!")
        return redirect('login')
    
#Resolved_Task
def resolved_task(request, pk):
    if request.user.is_authenticated:
        TaskDatas = TaskDetail.objects.get(id=pk)
        TaskDatas.task_status = 'Resolved'
        TaskDatas.save()

        # Fetch the creator and resolver accounts
        creator = get_object_or_404(Account, account_holder=TaskDatas.task_created_by)
        resolver = get_object_or_404(Account, account_holder=TaskDatas.task_closed_by)

        # Check if the creator has sufficient balance
        if creator.account_balance >= TaskDatas.task_reward:
            creator.account_balance -= TaskDatas.task_reward
            creator.save()
            resolver.account_balance += TaskDatas.task_reward
            resolver.save()

            # Log the transaction
            transaction.objects.create(
                sender=TaskDatas.task_created_by,
                receiver=TaskDatas.task_closed_by,
                amount=TaskDatas.task_reward
            )
        else:
            messages.error(request, "Insufficient balance to resolve the task.")
            return redirect('base')

        messages.success(request, "Task resolved successfully")
        return redirect('base')
    else:
        messages.error(request, "You must log in to resolve tasks!")
        return redirect('login')
    
#Update_Profile
def update_profile(request,pk):
    if request.user.is_authenticated:
        ProfileDatas = UserProfile.objects.get(id = pk)
        form = UserProfileForm(request.POST or None,instance=ProfileDatas)
        if form.is_valid():
            form.save()
            messages.success(request,"profile updated successfully")
            return redirect('profile')
        return render(request,'Update_profile.html',{'form':form})
    else:
        messages.success(request,"You must have to login to update profile!")
        return redirect('login')

#Account function
def AccountDetails(request):
    if request.user.is_authenticated:
        if request.method == 'POST':
            form = AccountDetailsForm(request.POST)
            if form.is_valid():
                form.save()
                messages.success(request,"coin added successfully")
            return redirect('base')
        else:
            form = AccountDetailsForm()
            return render(request,'account.html',{'form':form})
    else:
        messages.success(request,"You must have to login to create task")
        return redirect('login')
    
#AccountInfo function
# def AccountInfo(request):
#     if request.user.is_authenticated:
#         user = request.user
#         AccountDatas = Account.objects.filter(account_holder=user)
#         return render(request,'userprofile.html',{'AccountDatas':AccountDatas})
#     else:
#         messages.success(request,'you must have to login to see profile')
#         return redirect('login')


#transaction function
def transactions(request):
    if request.user.is_authenticated:
        user = request.user
        transactions = transaction.objects.filter(Q(sender=user)|Q(receiver=user))
        return render(request, 'transaction.html', {
            'transactions': transactions,
        })
    else:
        messages.success(request, "You must log in to see transactions!")
        return redirect('login')
