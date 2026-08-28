from django.contrib import admin
from django.contrib.auth.models import User
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import Profile, Job, CheckInRecord, SystemSettings

# ==========================
# User & Profile Inline Admin
# ==========================
class ProfileInline(admin.StackedInline):
    model = Profile
    can_delete = False
    verbose_name_plural = 'Profile'

class UserAdmin(BaseUserAdmin):
    inlines = [ProfileInline]
    list_display = ('username', 'email', 'first_name', 'last_name', 'get_role', 'is_staff', 'is_active')
    list_filter = ('profile__role', 'is_staff', 'is_active')

    def get_role(self, instance):
        return instance.profile.role
    get_role.short_description = 'Role'

admin.site.unregister(User)
admin.site.register(User, UserAdmin)


# ==========================
# Job Admin
# ==========================
@admin.register(Job)
class JobAdmin(admin.ModelAdmin):
    list_display = ('code', 'title', 'site_name', 'date', 'start_time', 'end_time', 'status')
    list_filter = ('status', 'date')
    search_fields = ('code', 'title', 'site_name', 'address')
    filter_horizontal = ('assigned_staff',)


# ==========================
# CheckInRecord Admin
# ==========================
@admin.register(CheckInRecord)
class CheckInRecordAdmin(admin.ModelAdmin):
    list_display = ('user', 'job', 'timestamp', 'is_inside_geofence', 'status', 'check_out_timestamp')
    list_filter = ('status', 'is_inside_geofence', 'timestamp')
    search_fields = ('user__username', 'job__title', 'job__code')
    readonly_fields = ('timestamp',)


# ==========================
# SystemSettings Admin
# ==========================
@admin.register(SystemSettings)
class SystemSettingsAdmin(admin.ModelAdmin):
    list_display = ('company_name', 'default_geofence_radius', 'max_allowed_gps_accuracy', 'working_hours_start', 'working_hours_end')
