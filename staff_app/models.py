from django.db import models
from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver

# ==========================
# User Profile & Roles
# ==========================
class Profile(models.Model):
    ROLE_CHOICES = [
        ('STAFF', 'Staff'),
        ('ADMIN', 'Admin'),
        ('SUPER_ADMIN', 'Super Admin'),
    ]
    
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='STAFF')
    phone = models.CharField(max_length=20, blank=True, null=True)
    avatar = models.ImageField(upload_to='avatars/', blank=True, null=True)
    department = models.CharField(max_length=100, blank=True, null=True)
    joined_date = models.DateField(auto_now_add=True)

    def __str__(self):
        return f"{self.user.username} ({self.role})"

@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    if created:
        Profile.objects.create(user=instance)

@receiver(post_save, sender=User)
def save_user_profile(sender, instance, **kwargs):
    if not hasattr(instance, 'profile'):
        Profile.objects.create(user=instance)
    instance.profile.save()


# ==========================
# Job & Work Site Model
# ==========================
class Job(models.Model):
    STATUS_CHOICES = [
        ('UPCOMING', 'Upcoming'),
        ('CHECKED_IN', 'Checked In'),
        ('PENDING_APPROVAL', 'Pending Approval'),
        ('APPROVED', 'Approved'),
        ('REJECTED', 'Rejected'),
        ('COMPLETED', 'Completed'),
    ]

    title = models.CharField(max_length=200)
    code = models.CharField(max_length=50, unique=True)
    description = models.TextField(blank=True, null=True)
    instructions_json = models.TextField(default='[]', help_text='JSON list of instructions')
    
    # Location fields
    site_name = models.CharField(max_length=200)
    address = models.TextField()
    lat = models.FloatField()
    lng = models.FloatField()
    geofence_radius = models.IntegerField(default=75) # in meters

    assigned_staff = models.ManyToManyField(User, related_name='assigned_jobs', blank=True)
    
    start_time = models.TimeField()
    end_time = models.TimeField()
    date = models.DateField()
    
    require_selfie = models.BooleanField(default=True)
    require_checkout = models.BooleanField(default=True)
    status = models.CharField(max_length=30, choices=STATUS_CHOICES, default='UPCOMING')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.code} - {self.title}"

    @property
    def instructions_list(self):
        import json
        try:
            return json.loads(self.instructions_json)
        except:
            return []


# ==========================
# Check-in & Check-out Logs
# ==========================
class CheckInRecord(models.Model):
    STATUS_CHOICES = [
        ('PENDING_APPROVAL', 'Pending Approval'),
        ('APPROVED', 'Approved'),
        ('REJECTED', 'Rejected'),
        ('AWAITING_SELFIE', 'Awaiting Selfie'),
        ('COMPLETED', 'Completed'),
        ('REUPLOAD_REQUESTED', 'Re-upload Requested'),
    ]

    job = models.ForeignKey(Job, on_delete=models.CASCADE, related_name='checkins')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='checkins')
    timestamp = models.DateTimeField(auto_now_add=True)
    
    check_in_lat = models.FloatField()
    check_in_lng = models.FloatField()
    accuracy = models.FloatField() # GPS accuracy in meters
    distance_from_center = models.FloatField() # meters from geofence center
    is_inside_geofence = models.BooleanField(default=True)
    selfie = models.ImageField(upload_to='selfies/checkin/', blank=True, null=True)
    
    status = models.CharField(max_length=30, choices=STATUS_CHOICES, default='PENDING_APPROVAL')
    status_notes = models.TextField(blank=True, null=True)
    
    reviewed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='reviewed_checkins')
    reviewed_at = models.DateTimeField(blank=True, null=True)
    
    # Check-out fields
    check_out_timestamp = models.DateTimeField(blank=True, null=True)
    check_out_lat = models.FloatField(blank=True, null=True)
    check_out_lng = models.FloatField(blank=True, null=True)
    check_out_accuracy = models.FloatField(blank=True, null=True)
    check_out_notes = models.TextField(blank=True, null=True)
    check_out_selfie = models.ImageField(upload_to='selfies/checkout/', blank=True, null=True)
    duration_minutes = models.IntegerField(blank=True, null=True)

    def __str__(self):
        return f"{self.user.username} checked in for {self.job.title} on {self.timestamp.date()}"


# ==========================
# System Settings Model
# ==========================
class SystemSettings(models.Model):
    default_geofence_radius = models.IntegerField(default=75) # in meters
    max_allowed_gps_accuracy = models.IntegerField(default=40) # in meters
    strict_geofence_camera_lock = models.BooleanField(default=True)
    working_hours_start = models.TimeField(default="08:00")
    working_hours_end = models.TimeField(default="18:00")
    late_tolerance_minutes = models.IntegerField(default=15)
    company_name = models.CharField(max_length=200, default="Staff Tracker")
    company_logo = models.ImageField(upload_to='company/', blank=True, null=True)

    def __str__(self):
        return self.company_name

    @classmethod
    def get_settings(cls):
        settings, created = cls.objects.get_or_create(id=1)
        return settings
