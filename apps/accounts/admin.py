from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import PointHistory, User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    """Admin configuration for User model."""
    
    list_display = ('email', 'name', 'status', 'is_verified', 'is_staff', 'point_balance', 'created_at')
    list_filter = ('status', 'is_verified', 'is_staff', 'is_active', 'created_at')
    search_fields = ('email', 'name')
    ordering = ('-created_at',)
    
    fieldsets = (
        (None, {'fields': ('email', 'password')}),
        ('Personal info', {'fields': ('name', 'is_verified')}),
        ('Account status', {'fields': ('status', 'is_active', 'is_staff')}),
        ('Points', {'fields': ('point_balance', 'point_last_updated_at')}),
        ('Permissions', {'fields': ('groups', 'user_permissions')}),
        ('Important dates', {'fields': ('last_login', 'created_at', 'updated_at')}),
    )
    
    readonly_fields = ('created_at', 'updated_at', 'last_login', 'point_balance', 'point_last_updated_at')
    
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('email', 'name', 'password1', 'password2'),
        }),
    )


@admin.register(PointHistory)
class PointHistoryAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'transaction_type', 'amount', 'balance_after', 'reason_code', 'created_at')
    list_filter = ('transaction_type', 'reason_code', 'created_at')
    search_fields = ('user__email', 'reason_code', 'reference_id', 'idempotency_key')
    readonly_fields = [field.name for field in PointHistory._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
