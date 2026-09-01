from django.contrib import admin
from django.contrib.auth.models import User
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from import_export import resources, fields
from import_export.admin import ImportExportModelAdmin
from import_export.widgets import ForeignKeyWidget
from .models import Profile, Job, CheckInRecord, SystemSettings, WorkLocation

# ==========================
# Resource Classes for Import/Export
# ==========================

class UserResource(resources.ModelResource):
    """Resource for importing/exporting Users with their Profile data"""
    
    role = fields.Field(
        column_name='role',
        attribute='profile',
        widget=ForeignKeyWidget(Profile, 'role')
    )
    phone = fields.Field(
        column_name='phone',
        attribute='profile',
        widget=ForeignKeyWidget(Profile, 'phone')
    )
    department = fields.Field(
        column_name='department',
        attribute='profile',
        widget=ForeignKeyWidget(Profile, 'department')
    )
    
    class Meta:
        model = User
        fields = (
            'id', 'username', 'email', 'first_name', 'last_name', 
            'is_active', 'is_staff', 'is_superuser', 'date_joined',
            'role', 'phone', 'department'
        )
        export_order = ('id', 'username', 'email', 'first_name', 'last_name', 
                       'role', 'phone', 'department', 'is_active')
        import_id_fields = ('id',)

    def dehydrate_role(self, user):
        return user.profile.role if hasattr(user, 'profile') else ''
    
    def dehydrate_phone(self, user):
        return user.profile.phone if hasattr(user, 'profile') else ''
    
    def dehydrate_department(self, user):
        return user.profile.department if hasattr(user, 'profile') else ''


class ProfileResource(resources.ModelResource):
    """Resource for importing/exporting Profiles"""
    
    username = fields.Field(
        column_name='username',
        attribute='user',
        widget=ForeignKeyWidget(User, 'username')
    )
    
    class Meta:
        model = Profile
        fields = (
            'id', 'username', 'role', 'phone', 
            'department', 'joined_date'
        )
        export_order = ('id', 'username', 'role', 'phone', 
                       'department', 'joined_date')
        import_id_fields = ('id',)


class WorkLocationResource(resources.ModelResource):
    """Resource for importing/exporting Work Locations"""
    
    created_by_username = fields.Field(
        column_name='created_by_username',
        attribute='created_by',
        widget=ForeignKeyWidget(User, 'username')
    )
    
    class Meta:
        model = WorkLocation
        fields = (
            'id', 'name', 'address', 'lat', 'lng', 
            'geofence_radius', 'created_by_username', 'created_at'
        )
        export_order = ('id', 'name', 'address', 'lat', 'lng', 
                       'geofence_radius', 'created_by_username')
        import_id_fields = ('id',)


class JobResource(resources.ModelResource):
    """Resource for importing/exporting Jobs"""
    
    assigned_staff = fields.Field(
        column_name='assigned_staff',
        attribute='assigned_staff',
        widget=ForeignKeyWidget(User, 'username')
    )
    requested_by_username = fields.Field(
        column_name='requested_by_username',
        attribute='requested_by',
        widget=ForeignKeyWidget(User, 'username')
    )
    
    class Meta:
        model = Job
        # Remove widgets entirely - use default serialization
        fields = (
            'id', 'code', 'title', 'description', 'instructions_json',
            'site_name', 'address', 'lat', 'lng', 'geofence_radius',
            'assigned_staff', 'start_time', 'end_time', 'date',
            'require_selfie', 'require_checkout', 'status',
            'is_adhoc', 'requested_by_username', 'created_at'
        )
        export_order = (
            'id', 'code', 'title', 'site_name', 'address',
            'lat', 'lng', 'geofence_radius', 'assigned_staff',
            'date', 'start_time', 'end_time', 'status'
        )
        import_id_fields = ('id',)


class CheckInRecordResource(resources.ModelResource):
    """Resource for importing/exporting CheckIn Records"""
    
    username = fields.Field(
        column_name='username',
        attribute='user',
        widget=ForeignKeyWidget(User, 'username')
    )
    job_code = fields.Field(
        column_name='job_code',
        attribute='job',
        widget=ForeignKeyWidget(Job, 'code')
    )
    reviewed_by_username = fields.Field(
        column_name='reviewed_by_username',
        attribute='reviewed_by',
        widget=ForeignKeyWidget(User, 'username')
    )
    
    class Meta:
        model = CheckInRecord
        # Remove widgets entirely - use default serialization
        fields = (
            'id', 'username', 'job_code', 'timestamp',
            'check_in_lat', 'check_in_lng', 'accuracy',
            'distance_from_center', 'is_inside_geofence',
            'is_emergency', 'emergency_reason', 'status',
            'status_notes', 'reviewed_by_username', 'reviewed_at',
            'check_out_timestamp', 'check_out_lat', 'check_out_lng',
            'check_out_accuracy', 'check_out_notes', 'duration_minutes'
        )
        export_order = (
            'id', 'username', 'job_code', 'timestamp',
            'check_in_lat', 'check_in_lng', 'accuracy',
            'is_inside_geofence', 'status', 'duration_minutes'
        )
        import_id_fields = ('id',)


class SystemSettingsResource(resources.ModelResource):
    """Resource for importing/exporting System Settings"""
    
    class Meta:
        model = SystemSettings
        # Remove widgets entirely - use default serialization
        fields = (
            'id', 'company_name', 'default_geofence_radius',
            'max_allowed_gps_accuracy', 'strict_geofence_camera_lock',
            'working_hours_start', 'working_hours_end', 
            'late_tolerance_minutes'
        )
        export_order = (
            'id', 'company_name', 'default_geofence_radius',
            'max_allowed_gps_accuracy', 'working_hours_start', 
            'working_hours_end', 'late_tolerance_minutes'
        )
        import_id_fields = ('id',)


# ==========================
# Admin Classes with Import/Export
# ==========================

class ProfileInline(admin.StackedInline):
    model = Profile
    can_delete = False
    verbose_name_plural = 'Profile'


class UserAdmin(ImportExportModelAdmin):
    resource_class = UserResource
    inlines = [ProfileInline]
    list_display = ('username', 'email', 'first_name', 'last_name', 'get_role', 'is_staff', 'is_active')
    list_filter = ('profile__role', 'is_staff', 'is_active')
    search_fields = ('username', 'email', 'first_name', 'last_name')
    
    def get_role(self, instance):
        return instance.profile.role if hasattr(instance, 'profile') else '—'
    get_role.short_description = 'Role'

admin.site.unregister(User)
admin.site.register(User, UserAdmin)


@admin.register(Profile)
class ProfileAdmin(ImportExportModelAdmin):
    resource_class = ProfileResource
    list_display = ('user', 'role', 'phone', 'department', 'joined_date')
    list_filter = ('role', 'department')
    search_fields = ('user__username', 'user__email', 'phone', 'department')
    raw_id_fields = ('user',)


@admin.register(WorkLocation)
class WorkLocationAdmin(ImportExportModelAdmin):
    resource_class = WorkLocationResource
    list_display = ('name', 'address', 'lat', 'lng', 'geofence_radius', 'created_by', 'created_at')
    list_filter = ('created_by',)
    search_fields = ('name', 'address')
    raw_id_fields = ('created_by',)


@admin.register(Job)
class JobAdmin(ImportExportModelAdmin):
    resource_class = JobResource
    list_display = ('code', 'title', 'site_name', 'date', 'start_time', 'end_time', 'status')
    list_filter = ('status', 'date', 'is_adhoc')
    search_fields = ('code', 'title', 'site_name', 'address')
    filter_horizontal = ('assigned_staff',)
    raw_id_fields = ('requested_by',)
    readonly_fields = ('created_at',)


@admin.register(CheckInRecord)
class CheckInRecordAdmin(ImportExportModelAdmin):
    resource_class = CheckInRecordResource
    list_display = ('user', 'job', 'timestamp', 'is_inside_geofence', 'status', 'check_out_timestamp')
    list_filter = ('status', 'is_inside_geofence', 'timestamp', 'is_emergency')
    search_fields = ('user__username', 'job__title', 'job__code')
    readonly_fields = ('timestamp',)
    raw_id_fields = ('user', 'job', 'reviewed_by')


@admin.register(SystemSettings)
class SystemSettingsAdmin(ImportExportModelAdmin):
    resource_class = SystemSettingsResource
    list_display = ('company_name', 'default_geofence_radius', 'max_allowed_gps_accuracy', 
                   'working_hours_start', 'working_hours_end')
    list_editable = ('default_geofence_radius', 'max_allowed_gps_accuracy')