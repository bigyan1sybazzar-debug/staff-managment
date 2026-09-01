"""
Django management command: seeds 5 staff users and 5 jobs (with staff
assignments + access-grant durations) for local testing.

USAGE:
1. Place this file at:
     staff_app/management/commands/seed_demo_data.py
   (create the 'management' and 'commands' folders if they don't exist,
   each needs an empty __init__.py inside it too — see step 2)

2. Folder structure needed:
     staff_app/
       management/
         __init__.py          <- empty file
         commands/
           __init__.py         <- empty file
           seed_demo_data.py   <- this file

3. Run:
     python manage.py seed_demo_data

Safe to re-run — uses get_or_create/update_or_create so it won't create
duplicates if you run it more than once.
"""

import datetime
from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from django.utils import timezone
from staff_app.models import Job, JobAssignment


class Command(BaseCommand):
    help = "Seed 5 staff users and 5 jobs with assignments for testing."

    def handle(self, *args, **options):
        today = timezone.now().date()

        # ── 5 Staff Users ──
        staff_data = [
            {"username": "staff1", "first_name": "Alice", "last_name": "Sharma", "dept": "Security"},
            {"username": "staff2", "first_name": "Bikash", "last_name": "Thapa", "dept": "Maintenance"},
            {"username": "staff3", "first_name": "Chitra", "last_name": "Gurung", "dept": "Sales"},
            {"username": "staff4", "first_name": "Deepak", "last_name": "Rai", "dept": "Security"},
            {"username": "staff5", "first_name": "Elina", "last_name": "Karki", "dept": "Cleaning"},
        ]

        staff_users = []
        for i, s in enumerate(staff_data, start=1):
            user, created = User.objects.get_or_create(
                username=s["username"],
                defaults={
                    "email": f"{s['username']}@example.com",
                    "first_name": s["first_name"],
                    "last_name": s["last_name"],
                    "is_active": True,
                },
            )
            if created:
                user.set_password("password123")
                user.save()
            # Profile auto-created via signal — just fill it in
            profile = user.profile
            profile.role = "STAFF"
            profile.department = s["dept"]
            profile.phone = f"98{i:08d}"
            profile.save()
            staff_users.append(user)
            self.stdout.write(self.style.SUCCESS(
                f"{'Created' if created else 'Found'} user: {user.username} / password123"
            ))

        # ── 5 Jobs (Kathmandu-area coordinates) ──
        job_data = [
            {
                "code": "JOB-001", "title": "Warehouse Night Guard",
                "site_name": "Thimi Warehouse A", "address": "Thimi, Bhaktapur, Nepal",
                "lat": 27.6789, "lng": 85.3958, "radius": 100,
                "start": "20:00", "duration": "30_DAYS",
            },
            {
                "code": "JOB-002", "title": "Office Reception Desk",
                "site_name": "Kathmandu HQ Reception", "address": "New Baneshwor, Kathmandu, Nepal",
                "lat": 27.6900, "lng": 85.3436, "radius": 50,
                "start": "09:00", "duration": "15_DAYS",
            },
            {
                "code": "JOB-003", "title": "Retail Store Floor Staff",
                "site_name": "Patan Retail Outlet", "address": "Patan Durbar Square Area, Lalitpur, Nepal",
                "lat": 27.6727, "lng": 85.3245, "radius": 60,
                "start": "10:00", "duration": "3_MONTHS",
            },
            {
                "code": "JOB-004", "title": "Construction Site Supervisor",
                "site_name": "Bouddha Building Site", "address": "Boudhanath, Kathmandu, Nepal",
                "lat": 27.7215, "lng": 85.3620, "radius": 150,
                "start": "07:30", "duration": "6_MONTHS",
            },
            {
                "code": "JOB-005", "title": "Event Setup Crew",
                "site_name": "Bhrikutimandap Event Hall", "address": "Bhrikutimandap, Kathmandu, Nepal",
                "lat": 27.7016, "lng": 85.3140, "radius": 80,
                "start": "06:00", "duration": "CUSTOM",
            },
        ]

        for idx, j in enumerate(job_data):
            start_dt = datetime.datetime.strptime(j["start"], "%H:%M")
            end_dt = start_dt + datetime.timedelta(hours=8)
            end_time = end_dt.time() if end_dt.day == start_dt.day else datetime.time(23, 59)

            job, created = Job.objects.get_or_create(
                code=j["code"],
                defaults={
                    "title": j["title"],
                    "description": f"Demo seeded job — {j['title']}.",
                    "site_name": j["site_name"],
                    "address": j["address"],
                    "lat": j["lat"],
                    "lng": j["lng"],
                    "geofence_radius": j["radius"],
                    "start_time": start_dt.time(),
                    "end_time": end_time,
                    "date": today + datetime.timedelta(days=idx),  # spread across upcoming days
                    "require_selfie": True,
                    "require_checkout": True,
                    "status": "UPCOMING",
                },
            )
            self.stdout.write(self.style.SUCCESS(
                f"{'Created' if created else 'Found'} job: {job.code} — {job.title}"
            ))

            # Assign 1-2 staff members to each job with a grant window
            assignees = [staff_users[idx % 5], staff_users[(idx + 1) % 5]]
            for staff_user in assignees:
                if j["duration"] == "CUSTOM":
                    granted_end = today + datetime.timedelta(days=45)
                else:
                    granted_end = JobAssignment.compute_end_date(j["duration"], today)

                JobAssignment.objects.update_or_create(
                    job=job, staff=staff_user,
                    defaults={
                        "duration_label": j["duration"],
                        "granted_start": today,
                        "granted_end": granted_end,
                    },
                )
                self.stdout.write(
                    f"    → granted {staff_user.username} access until {granted_end}"
                )

        self.stdout.write(self.style.SUCCESS(
            "\nDone. 5 staff users (password: password123) and 5 jobs seeded."
        ))
