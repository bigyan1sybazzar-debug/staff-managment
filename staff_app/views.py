from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import User
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.db.models import Q
import json
import math
from .models import Profile, Job, CheckInRecord, SystemSettings


def haversine_distance(lat1, lng1, lat2, lng2):
    """Return distance in metres between two GPS points."""
    R = 6371000
    d_lat = math.radians(lat2 - lat1)
    d_lng = math.radians(lng2 - lng1)
    a = (math.sin(d_lat / 2) ** 2
         + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2))
         * math.sin(d_lng / 2) ** 2)
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

# ==========================
# Authentication Views
# ==========================
def login_view(request):
    if request.user.is_authenticated:
        if hasattr(request.user, 'profile') and request.user.profile.role == 'STAFF':
            return redirect('staff_dashboard')
        return redirect('dashboard')
        
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        
        user = authenticate(request, username=username, password=password)
        if user is not None:
            if user.is_active:
                login(request, user)
                messages.success(request, f"Welcome back, {user.username}!")
                # Route by role
                if hasattr(user, 'profile') and user.profile.role == 'STAFF':
                    return redirect('staff_dashboard')
                return redirect('dashboard')
            else:
                messages.error(request, "This account has been disabled.")
        else:
            messages.error(request, "Invalid username or password.")
            
    return render(request, 'login.html')

def logout_view(request):
    logout(request)
    messages.info(request, "You have been logged out.")
    return redirect('login')


# ==========================
# Dashboard View
# ==========================
@login_required
def dashboard_view(request):
    # Redirect plain staff to their own dashboard
    if hasattr(request.user, 'profile') and request.user.profile.role == 'STAFF':
        return redirect('staff_dashboard')
    today = timezone.now().date()
    
    # Calculate stats
    total_staff_count = User.objects.filter(profile__role='STAFF').count()
    active_jobs = Job.objects.filter(date=today)
    active_jobs_count = active_jobs.count()
    
    checked_in_count = CheckInRecord.objects.filter(
        timestamp__date=today, 
        check_out_timestamp__isnull=True
    ).count()
    
    pending_approvals_count = CheckInRecord.objects.filter(
        status='PENDING_APPROVAL'
    ).count()
    
    recent_checkins = CheckInRecord.objects.all().order_by('-timestamp')[:5]

    context = {
        'total_staff_count': total_staff_count,
        'active_jobs_count': active_jobs_count,
        'checked_in_count': checked_in_count,
        'pending_approvals_count': pending_approvals_count,
        'active_jobs': active_jobs,
        'recent_checkins': recent_checkins,
    }
    return render(request, 'dashboard.html', context)


# ==========================
# Staff User Dashboard
# ==========================
@login_required
def staff_dashboard_view(request):
    today = timezone.now().date()
    user  = request.user

    all_assigned  = Job.objects.filter(assigned_staff=user)
    today_jobs    = all_assigned.filter(date=today).order_by('start_time')
    upcoming_jobs = all_assigned.filter(date__gt=today).order_by('date', 'start_time')

    # Map job_id -> active CheckInRecord (checked-in but not yet checked-out)
    active_checkins = {}
    for ci in CheckInRecord.objects.filter(user=user, check_out_timestamp__isnull=True):
        active_checkins[ci.job_id] = ci

    # Attach active check-in info to each job
    def annotate(queryset):
        jobs = list(queryset)
        for job in jobs:
            job.active_checkin = active_checkins.get(job.pk)
        return jobs

    context = {
        'today':          today,
        'today_jobs':     annotate(today_jobs),
        'upcoming_jobs':  annotate(upcoming_jobs),
        'total_assigned': all_assigned.count(),
    }
    return render(request, 'staff_dashboard.html', context)


# ==========================
# Check-In View
# ==========================
@login_required
def checkin_view(request, job_pk):
    job = get_object_or_404(Job, pk=job_pk, assigned_staff=request.user)
    if request.method == 'POST':
        try:
            print("--- CHECK-IN POST ---")
            print("POST data:", request.POST)
            print("FILES data:", request.FILES)
            
            lat      = float(request.POST.get('lat', 0))
            lng      = float(request.POST.get('lng', 0))
            accuracy = float(request.POST.get('accuracy', 0))
            selfie   = request.FILES.get('selfie')

            distance   = haversine_distance(job.lat, job.lng, lat, lng)
            is_inside  = distance <= job.geofence_radius

            record = CheckInRecord.objects.create(
                job=job,
                user=request.user,
                check_in_lat=lat,
                check_in_lng=lng,
                accuracy=accuracy,
                distance_from_center=round(distance, 1),
                is_inside_geofence=is_inside,
                selfie=selfie,
                status='PENDING_APPROVAL',
            )
            print("Created check-in record ID:", record.id, "Selfie:", record.selfie)
            messages.success(request, f"Checked in to '{job.title}' successfully!")
        except Exception as e:
            print("Check-in error:", str(e))
            messages.error(request, f"Check-in failed: {e}")
    return redirect('staff_dashboard')


# ==========================
# Check-Out View
# ==========================
@login_required
def checkout_view(request, record_pk):
    record = get_object_or_404(CheckInRecord, pk=record_pk, user=request.user)
    if request.method == 'POST':
        try:
            print("--- CHECK-OUT POST ---")
            print("POST data:", request.POST)
            print("FILES data:", request.FILES)

            lat      = float(request.POST.get('lat', 0))
            lng      = float(request.POST.get('lng', 0))
            accuracy = float(request.POST.get('accuracy', 0))
            selfie   = request.FILES.get('selfie')

            now      = timezone.now()
            duration = int((now - record.timestamp).total_seconds() / 60)

            record.check_out_timestamp = now
            record.check_out_lat       = lat
            record.check_out_lng       = lng
            record.check_out_accuracy  = accuracy
            record.duration_minutes    = duration
            if selfie:
                record.check_out_selfie = selfie
            record.status = 'COMPLETED'
            record.save()
            print("Updated check-out record ID:", record.id, "Checkout selfie:", record.check_out_selfie)
            messages.success(request, f"Checked out from '{record.job.title}'! Duration: {duration} min.")
        except Exception as e:
            print("Check-out error:", str(e))
            messages.error(request, f"Check-out failed: {e}")
    return redirect('staff_dashboard')


# ==========================
# Staff CRUD Views
# ==========================
@login_required
def staff_list_view(request):
    # Search and Filter
    search_query = request.GET.get('search', '')
    role_filter = request.GET.get('role', '')
    status_filter = request.GET.get('status', '')
    
    members = User.objects.all().exclude(is_superuser=True)
    
    if search_query:
        members = members.filter(
            Q(username__icontains=search_query) |
            Q(first_name__icontains=search_query) |
            Q(last_name__icontains=search_query) |
            Q(email__icontains=search_query) |
            Q(profile__department__icontains=search_query)
        )
        
    if role_filter:
        members = members.filter(profile__role=role_filter)
        
    if status_filter:
        is_active = True if status_filter == 'active' else False
        members = members.filter(is_active=is_active)
        
    context = {
        'staff_members': members.order_by('username')
    }
    return render(request, 'staff_list.html', context)

@login_required
def staff_create_view(request):
    if request.method == 'POST':
        username = request.POST.get('username')
        email = request.POST.get('email')
        password = request.POST.get('password')
        first_name = request.POST.get('first_name', '')
        last_name = request.POST.get('last_name', '')
        
        phone = request.POST.get('phone', '')
        department = request.POST.get('department', '')
        role = request.POST.get('role', 'STAFF')
        avatar = request.FILES.get('avatar')
        is_active = False if request.POST.get('is_active') == 'off' else True
        
        if User.objects.filter(username=username).exists():
            messages.error(request, "Username already exists.")
            return render(request, 'staff_form.html', {'form_type': 'create'})
            
        # Create User
        user = User.objects.create_user(
            username=username, 
            email=email, 
            password=password,
            first_name=first_name,
            last_name=last_name,
            is_active=is_active
        )
        
        # Profile is created automatically by signal, just update it
        profile = user.profile
        profile.phone = phone
        profile.department = department
        profile.role = role
        if avatar:
            profile.avatar = avatar
        profile.save()
        
        messages.success(request, f"Staff member '{username}' created successfully!")
        return redirect('staff_list')
        
    return render(request, 'staff_form.html', {'form_type': 'create'})

@login_required
def staff_update_view(request, pk):
    member = get_object_or_404(User, pk=pk)

    if request.method == 'POST':
        # ── Password-only path (triggered from the Staff Directory modal) ──
        if request.POST.get('pw_only') == '1':
            new_password     = request.POST.get('new_password', '').strip()
            confirm_password = request.POST.get('confirm_password', '').strip()
            if new_password and new_password == confirm_password:
                member.set_password(new_password)
                member.save()
                messages.success(request, f"Password for '{member.username}' updated successfully!")
            else:
                messages.error(request, "Passwords do not match — password was NOT changed.")
            return redirect('staff_list')

        # ── Full profile edit path ──
        member.email      = request.POST.get('email')
        member.first_name = request.POST.get('first_name', '')
        member.last_name  = request.POST.get('last_name', '')
        member.is_active  = True if request.POST.get('is_active') == 'on' else False

        # Handle optional password change from the edit form
        new_password     = request.POST.get('new_password', '').strip()
        confirm_password = request.POST.get('confirm_password', '').strip()
        if new_password:
            if new_password == confirm_password:
                member.set_password(new_password)
                messages.success(request, f"Password for '{member.username}' has been updated.")
            else:
                messages.error(request, "Passwords do not match. Profile info was saved but password was NOT changed.")

        member.save()

        # Profile details
        profile = member.profile
        profile.phone      = request.POST.get('phone', '')
        profile.department = request.POST.get('department', '')
        profile.role       = request.POST.get('role', 'STAFF')

        avatar = request.FILES.get('avatar')
        if avatar:
            profile.avatar = avatar

        profile.save()
        messages.success(request, f"Staff profile updated successfully!")
        return redirect('staff_list')

    context = {
        'member': member,
        'form_type': 'update'
    }
    return render(request, 'staff_form.html', context)


@login_required
def staff_delete_view(request, pk):
    member = get_object_or_404(User, pk=pk)
    username = member.username
    member.delete()
    messages.success(request, f"Staff member '{username}' deleted successfully.")
    return redirect('staff_list')


# ==========================
# History & Detail Views
# ==========================
@login_required
def history_view(request):
    # Check if checking details (AJAX API call)
    is_api = request.GET.get('api')
    record_id = request.GET.get('id')
    
    if is_api and record_id:
        record = get_object_or_404(CheckInRecord, id=record_id)
        data = {
            'id': record.id,
            'user_name': record.user.get_full_name() or record.user.username,
            'job_title': record.job.title,
            'job_code': record.job.code,
            'site_name': record.job.site_name,
            'site_lat': record.job.lat,
            'site_lng': record.job.lng,
            'geofence_radius': record.job.geofence_radius,
            'check_in_lat': record.check_in_lat,
            'check_in_lng': record.check_in_lng,
            'accuracy': record.accuracy,
            'distance_from_center': record.distance_from_center,
            'is_inside_geofence': record.is_inside_geofence,
            'selfie_url': record.selfie.url if record.selfie else None,
            'status': record.status,
            'status_notes': record.status_notes,
            'checkout_selfie_url': record.check_out_selfie.url if record.check_out_selfie else None,
            'checkout_notes': record.check_out_notes,
        }
        return JsonResponse(data)
        
    # Check if updating status
    action = request.GET.get('action')
    if action == 'update_status' and record_id:
        record = get_object_or_404(CheckInRecord, id=record_id)
        if request.method == 'POST':
            record.status = request.POST.get('new_status')
            record.status_notes = request.POST.get('status_notes')
            record.reviewed_by = request.user
            record.reviewed_at = timezone.now()
            record.save()
            messages.success(request, "Check-in status updated successfully.")
            return redirect('history')

    # Basic page listing
    checkins = CheckInRecord.objects.all().order_by('-timestamp')
    
    # Apply filters
    user_filter = request.GET.get('user')
    job_filter = request.GET.get('job')
    status_filter = request.GET.get('status')
    date_filter = request.GET.get('date')
    
    if user_filter:
        checkins = checkins.filter(user_id=user_filter)
    if job_filter:
        checkins = checkins.filter(job_id=job_filter)
    if status_filter:
        checkins = checkins.filter(status=status_filter)
    if date_filter:
        checkins = checkins.filter(timestamp__date=date_filter)

    staff_list = User.objects.filter(profile__role='STAFF')
    jobs_list = Job.objects.all()

    context = {
        'checkins': checkins,
        'staff_list': staff_list,
        'jobs_list': jobs_list,
    }
    return render(request, 'history.html', context)


# ==========================
# Tracking Map Views
# ==========================
@login_required
def map_view(request):
    return render(request, 'map_view.html')

@login_required
def staff_locations_api(request):
    # Return JSON of today's active check-ins on map
    today = timezone.now().date()
    records = CheckInRecord.objects.filter(timestamp__date=today, check_out_timestamp__isnull=True)
    
    locations = []
    for r in records:
        locations.append({
            'id': r.id,
            'name': r.user.get_full_name() or r.user.username,
            'department': r.user.profile.department,
            'lat': r.check_in_lat,
            'lng': r.check_in_lng,
            'accuracy': r.accuracy,
            'distance_from_center': r.distance_from_center,
            'is_inside_geofence': r.is_inside_geofence,
            'site_name': r.job.site_name,
            'site_lat': r.job.lat,
            'site_lng': r.job.lng,
            'geofence_radius': r.job.geofence_radius,
            'status': r.get_status_display()
        })
        
    return JsonResponse({'locations': locations})


# ==========================
# Simulated Check-In API
# ==========================
@csrf_exempt
def log_location_api(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            user_id = data.get('userId')
            job_id = data.get('jobId')
            lat = float(data.get('lat'))
            lng = float(data.get('lng'))
            accuracy = float(data.get('accuracy', 10))
            is_inside = data.get('isInsideGeofence', True)
            distance = float(data.get('distanceFromCenter', 0))
            
            user = get_object_or_404(User, id=user_id)
            job = get_object_or_404(Job, id=job_id)
            
            # Create a check-in record
            record = CheckInRecord.objects.create(
                job=job,
                user=user,
                check_in_lat=lat,
                check_in_lng=lng,
                accuracy=accuracy,
                distance_from_center=distance,
                is_inside_geofence=is_inside,
                status='PENDING_APPROVAL'
            )
            
            return JsonResponse({'status': 'success', 'recordId': record.id})
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=400)
            
    return JsonResponse({'status': 'error', 'message': 'Only POST method allowed'}, status=405)


# ==========================
# Job CRUD Views
# ==========================
@login_required
def job_list_view(request):
    search_query = request.GET.get('search', '')
    status_filter = request.GET.get('status', '')
    
    jobs = Job.objects.all()
    if search_query:
        jobs = jobs.filter(
            Q(title__icontains=search_query) |
            Q(code__icontains=search_query) |
            Q(site_name__icontains=search_query) |
            Q(address__icontains=search_query)
        )
        
    if status_filter:
        jobs = jobs.filter(status=status_filter)
        
    context = {
        'jobs': jobs.order_by('-date', 'start_time')
    }
    return render(request, 'job_list.html', context)

@login_required
def job_create_view(request):
    staff_members = User.objects.filter(profile__role='STAFF')
    
    if request.method == 'POST':
        title = request.POST.get('title')
        code = request.POST.get('code')
        description = request.POST.get('description', '')
        site_name = request.POST.get('site_name')
        address = request.POST.get('address')
        lat = float(request.POST.get('lat', 0))
        lng = float(request.POST.get('lng', 0))
        geofence_radius = int(request.POST.get('geofence_radius', 75))
        
        start_time = request.POST.get('start_time')
        end_time = request.POST.get('end_time')
        date = request.POST.get('date')
        
        require_selfie = True if request.POST.get('require_selfie') == 'on' else False
        require_checkout = True if request.POST.get('require_checkout') == 'on' else False
        status = request.POST.get('status', 'UPCOMING')
        
        instructions = request.POST.getlist('instructions')
        # filter out empty instructions
        instructions = [inst for inst in instructions if inst.strip()]
        instructions_json = json.dumps(instructions)
        
        if Job.objects.filter(code=code).exists():
            messages.error(request, f"Job code '{code}' already exists.")
            return render(request, 'job_form.html', {'staff_members': staff_members, 'form_type': 'create'})
            
        job = Job.objects.create(
            title=title,
            code=code,
            description=description,
            instructions_json=instructions_json,
            site_name=site_name,
            address=address,
            lat=lat,
            lng=lng,
            geofence_radius=geofence_radius,
            start_time=start_time,
            end_time=end_time,
            date=date,
            require_selfie=require_selfie,
            require_checkout=require_checkout,
            status=status
        )
        
        assigned_staff_ids = request.POST.getlist('assigned_staff')
        if assigned_staff_ids:
            job.assigned_staff.set(User.objects.filter(id__in=assigned_staff_ids))
            
        messages.success(request, f"Job '{code}' created and assigned successfully!")
        return redirect('job_list')
        
    return render(request, 'job_form.html', {'staff_members': staff_members, 'form_type': 'create'})

@login_required
def job_update_view(request, pk):
    job = get_object_or_404(Job, pk=pk)
    staff_members = User.objects.filter(profile__role='STAFF')
    assigned_staff_ids = list(job.assigned_staff.values_list('id', flat=True))
    
    # Load instructions list
    instructions = job.instructions_list
    
    if request.method == 'POST':
        job.title = request.POST.get('title')
        job.description = request.POST.get('description', '')
        job.site_name = request.POST.get('site_name')
        job.address = request.POST.get('address')
        job.lat = float(request.POST.get('lat', 0))
        job.lng = float(request.POST.get('lng', 0))
        job.geofence_radius = int(request.POST.get('geofence_radius', 75))
        
        job.start_time = request.POST.get('start_time')
        job.end_time = request.POST.get('end_time')
        job.date = request.POST.get('date')
        
        job.require_selfie = True if request.POST.get('require_selfie') == 'on' else False
        job.require_checkout = True if request.POST.get('require_checkout') == 'on' else False
        job.status = request.POST.get('status', 'UPCOMING')
        
        instructions = request.POST.getlist('instructions')
        instructions = [inst for inst in instructions if inst.strip()]
        job.instructions_json = json.dumps(instructions)
        
        job.save()
        
        new_assigned_staff_ids = request.POST.getlist('assigned_staff')
        job.assigned_staff.set(User.objects.filter(id__in=new_assigned_staff_ids))
        
        messages.success(request, f"Job '{job.code}' details updated successfully!")
        return redirect('job_list')
        
    context = {
        'job': job,
        'staff_members': staff_members,
        'assigned_staff_ids': assigned_staff_ids,
        'instructions': instructions,
        'form_type': 'update'
    }
    return render(request, 'job_form.html', context)

@login_required
def job_delete_view(request, pk):
    job = get_object_or_404(Job, pk=pk)
    code = job.code
    job.delete()
    messages.success(request, f"Job '{code}' deleted successfully.")
    return redirect('job_list')

