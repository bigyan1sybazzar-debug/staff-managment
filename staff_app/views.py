from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import User
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.db.models import Q, Sum
import json
import math
import datetime
from .models import Profile, Job, CheckInRecord, SystemSettings, WorkLocation, JobAssignment


def haversine_distance(lat1, lng1, lat2, lng2):
    """Return distance in metres between two GPS points."""
    R = 6371000
    d_lat = math.radians(lat2 - lat1)
    d_lng = math.radians(lng2 - lng1)
    a = (math.sin(d_lat / 2) ** 2
         + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2))
         * math.sin(d_lng / 2) ** 2)
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def parse_client_captured_at(request):
    """
    Parse the 'selfie_captured_at' field sent by the browser (ISO 8601 string,
    set at the exact moment the photo was taken client-side). Falls back to
    the current server time if it's missing or malformed, so this never
    blocks a check-in/check-out.
    """
    raw = request.POST.get('selfie_captured_at')
    if not raw:
        return timezone.now()
    dt = parse_datetime(raw)
    if dt is None:
        return timezone.now()
    if timezone.is_naive(dt):
        dt = timezone.make_aware(dt, timezone.utc)
    return dt


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
    user = request.user

    active_job_ids = JobAssignment.objects.filter(
        staff=user, granted_start__lte=today, granted_end__gte=today
    ).values_list('job_id', flat=True)

    all_assigned = Job.objects.filter(id__in=active_job_ids)
    
    today_jobs_raw = all_assigned.filter(date=today).order_by('start_time')
    
    user_checkins = CheckInRecord.objects.filter(user=user)
    active_checkins = {}
    completed_checkins = {}

    for ci in user_checkins:
        if ci.check_out_timestamp is None:
            active_checkins[ci.job_id] = ci
        else:
            completed_checkins[ci.job_id] = ci

    def annotate(queryset):
        jobs = list(queryset)
        for job in jobs:
            job.active_checkin = active_checkins.get(job.pk)
            job.completed_checkin = completed_checkins.get(job.pk)
        return jobs

    annotated_jobs = annotate(today_jobs_raw)
    
    # ── Separate into active and completed ──
    active_today_jobs = []
    completed_today_jobs = []
    
    for job in annotated_jobs:
        if job.completed_checkin and job.completed_checkin.check_out_timestamp is not None:
            completed_today_jobs.append(job)
        else:
            active_today_jobs.append(job)
    
    completed_today_jobs.sort(key=lambda j: j.completed_checkin.check_out_timestamp if j.completed_checkin else j.date)
    
    # ── Upcoming jobs ──
    upcoming_jobs = all_assigned.filter(date__gt=today).order_by('date', 'start_time')
    upcoming_jobs = annotate(upcoming_jobs)

    # ── History ──
    thirty_days_ago = timezone.now() - datetime.timedelta(days=30)
    history_checkins = CheckInRecord.objects.filter(
        user=user,
        timestamp__gte=thirty_days_ago
    ).order_by('-timestamp').select_related('job')
    
    completed_qs = CheckInRecord.objects.filter(
        user=user, 
        status='COMPLETED', 
        duration_minutes__isnull=False,
        timestamp__gte=thirty_days_ago
    )
    total_completed_minutes = completed_qs.aggregate(total=Sum('duration_minutes'))['total'] or 0
    hours, minutes = divmod(int(total_completed_minutes), 60)
    total_completed_display = f"{hours}h {minutes}m"

    context = {
        'today': today,
        'active_today_jobs': active_today_jobs,      # ← NEW: Active jobs
        'completed_today_jobs': completed_today_jobs, # ← NEW: Completed jobs
        'upcoming_jobs': upcoming_jobs,
        'total_assigned': all_assigned.count(),
        'my_checkins': history_checkins,
        'total_completed_minutes': total_completed_minutes,
        'total_completed_display': total_completed_display,
        'completed_jobs_count': completed_qs.count(),
    }
    return render(request, 'staff_dashboard.html', context)

# ==========================
# Ad-hoc Job Request (staff self-add, pending admin approval)
# ==========================
@login_required
def adhoc_job_create_view(request):
    if request.method != 'POST':
        return redirect('staff_dashboard')
    try:
        title       = request.POST.get('title', '').strip()
        date        = request.POST.get('date')
        start_time  = request.POST.get('start_time')
        notes       = request.POST.get('notes', '').strip()
        lat_in      = float(request.POST.get('lat', 0) or 0)
        lng_in      = float(request.POST.get('lng', 0) or 0)

        location_id       = request.POST.get('location_id', '').strip()
        new_location_name = request.POST.get('new_location_name', '').strip()
        new_location_addr = request.POST.get('new_location_address', '').strip()

        if not title or not date or not start_time:
            return JsonResponse({'ok': False, 'error': 'Please fill in Job Title, Date, and Start Time.'}, status=400)

        # Resolve the location: either an existing saved one, or create a new one now
        if location_id:
            try:
                location = WorkLocation.objects.get(pk=location_id)
            except WorkLocation.DoesNotExist:
                return JsonResponse({'ok': False, 'error': 'Selected location was not found.'}, status=400)
        elif new_location_name:
            location = WorkLocation.objects.create(
                name=new_location_name,
                address=new_location_addr,
                lat=lat_in,
                lng=lng_in,
                geofence_radius=SystemSettings.get_settings().default_geofence_radius,
                created_by=request.user,
            )
        else:
            return JsonResponse({'ok': False, 'error': 'Please choose a location or add a new one.'}, status=400)

        # No end time required from the staff — assume a standard 8-hour shift
        start_dt = datetime.datetime.strptime(start_time, '%H:%M')
        end_dt = start_dt + datetime.timedelta(hours=8)
        end_time = end_dt.time() if end_dt.day == start_dt.day else datetime.time(23, 59)

        settings_obj = SystemSettings.get_settings()
        code = f"ADHOC-{timezone.now().strftime('%Y%m%d%H%M%S')}"

        job = Job.objects.create(
            title=title,
            code=code,
            description=notes,
            site_name=location.name,
            address=location.address or location.name,
            lat=location.lat,
            lng=location.lng,
            geofence_radius=location.geofence_radius or settings_obj.default_geofence_radius,
            start_time=start_time,
            end_time=end_time,
            date=date,
            require_selfie=True,
            require_checkout=True,
            status='PENDING_APPROVAL',
            is_adhoc=True,
            requested_by=request.user,
        )
        # Self-added jobs need a grant window too — default to 30 days
        # since there's no admin choosing a duration here.
        grant_start = timezone.now().date()
        JobAssignment.objects.update_or_create(
            job=job, staff=request.user,
            defaults={
                'duration_label': '30_DAYS',
                'granted_start': grant_start,
                'granted_end': JobAssignment.compute_end_date('30_DAYS', grant_start),
                'granted_by': request.user,
            }
        )

        return JsonResponse({'ok': True, 'job_pk': job.pk})
    except Exception as e:
        return JsonResponse({'ok': False, 'error': str(e)}, status=400)


# ==========================
# Saved Locations API (shared dropdown: Job form + staff Add Manually form)
# ==========================
@login_required
def work_locations_api(request):
    locations = WorkLocation.objects.all().values('id', 'name', 'address', 'lat', 'lng', 'geofence_radius')
    return JsonResponse({'locations': list(locations)})


# ==========================
# Staff Profile Document Uploads
# ==========================
@login_required
def profile_documents_upload_view(request):
    if request.method == 'POST':
        profile = request.user.profile

        # Profile Avatar (with auto-sync to photo_document)
        avatar = request.FILES.get('avatar')
        if avatar:
            profile.avatar = avatar
            # Also update photo_document to match (sync)
            profile.photo_document = avatar

        # Photo ID Document - if uploaded separately, sync to avatar if avatar is empty
        photo_doc = request.FILES.get('photo_document')
        if photo_doc:
            profile.photo_document = photo_doc
            # If no avatar was uploaded in this request and avatar is empty, use photo_doc as avatar
            if not avatar and not profile.avatar:
                profile.avatar = photo_doc

        # Other documents
        visa = request.FILES.get('visa_document')
        passport = request.FILES.get('passport_document')
        other = request.FILES.get('other_document')

        if visa:
            profile.visa_document = visa
        if passport:
            profile.passport_document = passport
        if other:
            profile.other_document = other

        profile.save()
        messages.success(request, "Documents uploaded successfully.")

    return redirect('/my-dashboard/#profile')

# ==========================
# Check-In View
# ==========================
@login_required
def checkin_view(request, job_pk):
    if request.method != 'POST':
        return redirect('staff_dashboard')
    try:
        job = Job.objects.get(pk=job_pk)
    except Job.DoesNotExist:
        return JsonResponse({'ok': False, 'error': f'Job #{job_pk} not found'}, status=404)
    
    # 🔴 FIXED: Server-side validation - Prevent check-in for upcoming jobs
    today = timezone.now().date()
    if job.date > today:
        return JsonResponse({'ok': False, 'error': 'This job is scheduled for a future date. You cannot check in yet.'}, status=400)
    
    try:
        lat      = float(request.POST.get('lat', 0))
        lng      = float(request.POST.get('lng', 0))
        accuracy = float(request.POST.get('accuracy', 0))
        selfie   = request.FILES.get('selfie')
        is_emergency = request.POST.get('is_emergency') == '1'
        emergency_reason = request.POST.get('emergency_reason', '').strip()

        distance  = haversine_distance(job.lat, job.lng, lat, lng)
        is_inside = distance <= job.geofence_radius

        # Exact moment the selfie was taken on the device (auto-captured client-side).
        # Only set when a selfie was actually provided.
        selfie_captured_at = parse_client_captured_at(request) if selfie else None

        record = CheckInRecord.objects.create(
            job=job,
            user=request.user,
            check_in_lat=lat,
            check_in_lng=lng,
            accuracy=accuracy,
            distance_from_center=round(distance, 1),
            is_inside_geofence=is_inside,
            selfie=selfie,
            selfie_captured_at=selfie_captured_at,
            is_emergency=is_emergency,
            emergency_reason=emergency_reason if is_emergency else '',
            status='PENDING_APPROVAL',
        )
        return JsonResponse({'ok': True, 'record_pk': record.id, 'job_pk': job.pk})
    except Exception as e:
        return JsonResponse({'ok': False, 'error': str(e)}, status=400)


# ==========================
# Check-Out View
# ==========================
@login_required
def checkout_view(request, record_pk):
    if request.method != 'POST':
        return redirect('staff_dashboard')
    try:
        record = CheckInRecord.objects.get(pk=record_pk, user=request.user)
    except CheckInRecord.DoesNotExist:
        return JsonResponse({'ok': False, 'error': f'Record #{record_pk} not found'}, status=404)
    try:
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
            # Exact moment the check-out selfie was taken on the device
            record.checkout_selfie_captured_at = parse_client_captured_at(request)
        record.status = 'PENDING_APPROVAL'
        record.save()
        return JsonResponse({'ok': True, 'record_pk': record.pk, 'job_pk': record.job_id, 'duration': duration})
    except Exception as e:
        return JsonResponse({'ok': False, 'error': str(e)}, status=400)


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
        
        # Document uploads
        visa_doc = request.FILES.get('visa_document')
        passport_doc = request.FILES.get('passport_document')
        photo_doc = request.FILES.get('photo_document')
        other_doc = request.FILES.get('other_document')
        
        if User.objects.filter(username=username).exists():
            messages.error(request, "Username already exists.")
            return render(request, 'staff_form.html', {
                'form_type': 'create',
                'page_title': 'Add Staff — StaffTracker',
                'page_heading': '👤 Add New Staff',
            })
            
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
        
        # If avatar is uploaded, use it
        if avatar:
            profile.avatar = avatar
            # Also set photo_document to the same image (sync)
            profile.photo_document = avatar
        # If no avatar but photo_doc is uploaded, use photo_doc as avatar
        elif photo_doc:
            profile.photo_document = photo_doc
            profile.avatar = photo_doc  # Auto-sync: photo_document becomes avatar
        
        # Handle other documents
        if visa_doc:
            profile.visa_document = visa_doc
        if passport_doc:
            profile.passport_document = passport_doc
        if other_doc:
            profile.other_document = other_doc
            
        profile.save()
        
        messages.success(request, f"Staff member '{username}' created successfully!")
        return redirect('staff_list')
        
    return render(request, 'staff_form.html', {
        'form_type': 'create',
        'page_title': 'Add Staff — StaffTracker',
        'page_heading': '👤 Add New Staff',
    })


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

        # ── Handle file uploads with auto-sync ──
        
        # 1. Profile Avatar - This is the primary profile photo
        avatar = request.FILES.get('avatar')
        if avatar:
            profile.avatar = avatar
            # When avatar is uploaded, also update photo_document to match
            profile.photo_document = avatar
        
        # 2. Photo ID Document - If uploaded separately, sync to avatar if avatar is empty
        photo_doc = request.FILES.get('photo_document')
        if photo_doc:
            profile.photo_document = photo_doc
            # If no avatar was uploaded in this request and avatar is empty, use photo_doc as avatar
            if not avatar and not profile.avatar:
                profile.avatar = photo_doc

        # 3. Other documents
        visa = request.FILES.get('visa_document')
        passport = request.FILES.get('passport_document')
        other_doc = request.FILES.get('other_document')

        if visa:
            profile.visa_document = visa
        if passport:
            profile.passport_document = passport
        if other_doc:
            profile.other_document = other_doc

        profile.save()
        messages.success(request, f"Staff profile updated successfully!")
        return redirect('staff_list')

    context = {
        'member': member,
        'form_type': 'update',
        'page_title': 'Update Staff — StaffTracker',
        'page_heading': '✏️ Edit Staff Profile',
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
            'selfie_captured_at': record.selfie_captured_at.isoformat() if record.selfie_captured_at else None,
            'is_emergency': record.is_emergency,
            'emergency_reason': record.emergency_reason,
            'status': record.status,
            'status_notes': record.status_notes,
            'checkout_selfie_url': record.check_out_selfie.url if record.check_out_selfie else None,
            'checkout_selfie_captured_at': record.checkout_selfie_captured_at.isoformat() if record.checkout_selfie_captured_at else None,
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

    # Staff members only ever see their own history; admins see everyone's
    # (still filterable by the 'user' dropdown below).
    is_staff_role = hasattr(request.user, 'profile') and request.user.profile.role == 'STAFF'
    if is_staff_role:
        checkins = checkins.filter(user=request.user)

    # Apply filters
    user_filter = request.GET.get('user')
    job_filter = request.GET.get('job')
    status_filter = request.GET.get('status')
    date_filter = request.GET.get('date')
    
    if user_filter and not is_staff_role:
        checkins = checkins.filter(user_id=user_filter)
    if job_filter:
        checkins = checkins.filter(job_id=job_filter)
    if status_filter:
        checkins = checkins.filter(status=status_filter)
    if date_filter:
        checkins = checkins.filter(timestamp__date=date_filter)

    staff_list = User.objects.filter(profile__role='STAFF')
    jobs_list = Job.objects.all()

    # ── Summary period filter (applies to the totals below, and to the
    # list itself, so "Weekly / 15 Days / Monthly / Custom" always means
    # exactly what's being summed) ──
    period = request.GET.get('period', '')
    period_start_raw = request.GET.get('period_start', '')
    period_end_raw = request.GET.get('period_end', '')

    today = timezone.now().date()
    period_start_date = None
    period_end_date = None

    if period == 'WEEKLY':
        period_start_date = today - datetime.timedelta(days=7)
        period_end_date = today
    elif period == '15_DAYS':
        period_start_date = today - datetime.timedelta(days=15)
        period_end_date = today
    elif period == 'MONTHLY':
        period_start_date = today - datetime.timedelta(days=30)
        period_end_date = today
    elif period == 'CUSTOM':
        if period_start_raw:
            try:
                period_start_date = datetime.datetime.strptime(period_start_raw, '%Y-%m-%d').date()
            except ValueError:
                period_start_date = None
        if period_end_raw:
            try:
                period_end_date = datetime.datetime.strptime(period_end_raw, '%Y-%m-%d').date()
            except ValueError:
                period_end_date = None

    if period_start_date:
        checkins = checkins.filter(timestamp__date__gte=period_start_date)
    if period_end_date:
        checkins = checkins.filter(timestamp__date__lte=period_end_date)

    # ── Completed-job duration totals ──
    # Sum of duration_minutes across all COMPLETED check-ins in the
    # currently filtered set (respects the staff-only restriction above).
    completed_qs = checkins.filter(status='COMPLETED', duration_minutes__isnull=False)
    total_completed_minutes = completed_qs.aggregate(total=Sum('duration_minutes'))['total'] or 0

    # Per-staff breakdown (only meaningful/shown for admins looking at everyone)
    completed_by_staff = completed_qs.values(
        'user__id', 'user__username', 'user__first_name', 'user__last_name'
    ).annotate(total_minutes=Sum('duration_minutes')).order_by('-total_minutes')

    def minutes_to_hm(total_minutes):
        hours, minutes = divmod(int(total_minutes), 60)
        return f"{hours}h {minutes}m"

    context = {
        'checkins': checkins,
        'staff_list': staff_list,
        'jobs_list': jobs_list,
        'is_staff_role': is_staff_role,
        'period': period,
        'period_start_raw': period_start_raw,
        'period_end_raw': period_end_raw,
        'total_completed_minutes': total_completed_minutes,
        'total_completed_display': minutes_to_hm(total_completed_minutes),
        'completed_jobs_count': completed_qs.count(),
        'completed_by_staff': [
            {**row, 'total_display': minutes_to_hm(row['total_minutes'])}
            for row in completed_by_staff
        ],
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

def compute_shift_end_time(start_time_str, hours=8):
    """Auto-assume a standard shift length since End Time is no longer collected from the form."""
    start_dt = datetime.datetime.strptime(start_time_str, '%H:%M')
    end_dt = start_dt + datetime.timedelta(hours=hours)
    if end_dt.day != start_dt.day:
        return datetime.time(23, 59)
    return end_dt.time()


def sync_work_location(name, address, lat, lng, geofence_radius, user):
    """
    Keep the shared location dropdown (used by both the Job form and the
    staff 'Add Manually' popup) in sync with whatever site a job is saved
    with, so admins don't have to manage locations separately.
    """
    if not name:
        return
    WorkLocation.objects.update_or_create(
        name=name,
        defaults={
            'address': address or '',
            'lat': lat,
            'lng': lng,
            'geofence_radius': geofence_radius,
            'created_by': user,
        }
    )


@login_required
def job_create_view(request):
    staff_members = User.objects.filter(profile__role='STAFF')
    work_locations = WorkLocation.objects.all()
    
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
        end_time = compute_shift_end_time(start_time)
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
            return render(request, 'job_form.html', {'staff_members': staff_members, 'work_locations': work_locations, 'form_type': 'create'})
            
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
        sync_work_location(site_name, address, lat, lng, geofence_radius, request.user)

        # ── Staff access duration (per-job grant window) ──
        duration_choice = request.POST.get('duration_choice', '30_DAYS')
        custom_end_raw = request.POST.get('custom_end_date', '')
        today = timezone.now().date()
        custom_end_date = None
        if custom_end_raw:
            try:
                custom_end_date = datetime.datetime.strptime(custom_end_raw, '%Y-%m-%d').date()
            except ValueError:
                custom_end_date = None
        granted_end = JobAssignment.compute_end_date(duration_choice, today, custom_end_date)

        assigned_staff_ids = request.POST.getlist('assigned_staff')
        for staff_id in assigned_staff_ids:
            JobAssignment.objects.update_or_create(
                job=job, staff_id=staff_id,
                defaults={
                    'duration_label': duration_choice,
                    'granted_start': today,
                    'granted_end': granted_end,
                    'granted_by': request.user,
                }
            )

        messages.success(request, f"Job '{code}' created and assigned successfully!")
        return redirect('job_list')
        
    return render(request, 'job_form.html', {'staff_members': staff_members, 'work_locations': work_locations, 'form_type': 'create'})

@login_required
def job_update_view(request, pk):
    job = get_object_or_404(Job, pk=pk)
    staff_members = User.objects.filter(profile__role='STAFF')
    work_locations = WorkLocation.objects.all()
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
        job.end_time = compute_shift_end_time(job.start_time)
        job.date = request.POST.get('date')
        
        job.require_selfie = True if request.POST.get('require_selfie') == 'on' else False
        job.require_checkout = True if request.POST.get('require_checkout') == 'on' else False
        job.status = request.POST.get('status', 'UPCOMING')
        
        instructions = request.POST.getlist('instructions')
        instructions = [inst for inst in instructions if inst.strip()]
        job.instructions_json = json.dumps(instructions)
        
        job.save()
        sync_work_location(job.site_name, job.address, job.lat, job.lng, job.geofence_radius, request.user)

        # ── Staff access duration (per-job grant window) ──
        duration_choice = request.POST.get('duration_choice', '30_DAYS')
        custom_end_raw = request.POST.get('custom_end_date', '')
        today = timezone.now().date()
        custom_end_date = None
        if custom_end_raw:
            try:
                custom_end_date = datetime.datetime.strptime(custom_end_raw, '%Y-%m-%d').date()
            except ValueError:
                custom_end_date = None
        granted_end = JobAssignment.compute_end_date(duration_choice, today, custom_end_date)

        new_assigned_staff_ids = request.POST.getlist('assigned_staff')

        # Remove grants for staff who were unchecked
        JobAssignment.objects.filter(job=job).exclude(staff_id__in=new_assigned_staff_ids).delete()

        # Create/refresh grants for currently checked staff — re-saving the
        # form re-grants access starting today for the chosen duration.
        for staff_id in new_assigned_staff_ids:
            JobAssignment.objects.update_or_create(
                job=job, staff_id=staff_id,
                defaults={
                    'duration_label': duration_choice,
                    'granted_start': today,
                    'granted_end': granted_end,
                    'granted_by': request.user,
                }
            )

        messages.success(request, f"Job '{job.code}' details updated successfully!")
        return redirect('job_list')

    existing_assignment = JobAssignment.objects.filter(job=job).order_by('-created_at').first()

    context = {
        'job': job,
        'staff_members': staff_members,
        'work_locations': work_locations,
        'assigned_staff_ids': assigned_staff_ids,
        'instructions': instructions,
        'existing_assignment': existing_assignment,
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