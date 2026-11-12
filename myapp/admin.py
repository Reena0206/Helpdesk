from django.contrib import admin

from .models import Account, Category, Ticket, TicketActivity, TicketComment, Transaction, UserProfile


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ['user', 'role', 'department', 'phone', 'city', 'state']
    list_filter = ['role']
    search_fields = ['user__username', 'user__email', 'user__first_name', 'user__last_name']


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ['name', 'description']
    search_fields = ['name']


class TicketCommentInline(admin.TabularInline):
    model = TicketComment
    extra = 0
    fields = ['author', 'body', 'is_internal', 'attachment', 'created_at']
    readonly_fields = ['created_at']


class TicketActivityInline(admin.TabularInline):
    model = TicketActivity
    extra = 0
    fields = ['actor', 'message', 'created_at']
    readonly_fields = ['actor', 'message', 'created_at']
    can_delete = False


@admin.register(Ticket)
class TicketAdmin(admin.ModelAdmin):
    list_display = ['number', 'title', 'status', 'priority', 'category', 'created_by', 'assigned_to',
                    'due_date', 'reward', 'rating', 'created_at']
    list_filter = ['status', 'priority', 'category']
    search_fields = ['title', 'description', 'created_by__username', 'assigned_to__username']
    readonly_fields = ['created_at', 'updated_at', 'resolved_at', 'closed_at']
    inlines = [TicketCommentInline, TicketActivityInline]
    date_hierarchy = 'created_at'


@admin.register(Account)
class AccountAdmin(admin.ModelAdmin):
    list_display = ['user', 'balance']
    search_fields = ['user__username']


@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = ['id', 'kind', 'sender', 'receiver', 'amount', 'ticket', 'note', 'created_at']
    list_filter = ['kind']
