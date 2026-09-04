from django.test import TestCase, Client
from django.contrib.auth.models import User
from django.utils import timezone
import datetime
from .models import Job, JobAssignment, CheckInRecord, Profile

class JobGrantAccessTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.staff_user = User.objects.create_user(username='teststaff', password='password123')
        self.staff_user.profile.role = 'STAFF'
        self.staff_user.profile.save()

        self.today = timezone.now().date()
        self.past_date = self.today - datetime.timedelta(days=2)

        # Job created 2 days ago
        self.job = Job.objects.create(
            title="Past Job Multi Day Access",
            code="JOB-GRANT-15",
            site_name="Test Site",
            address="123 Main St",
            lat=27.7000,
            lng=85.3000,
            geofence_radius=100,
            start_time=datetime.time(9, 0),
            end_time=datetime.time(17, 0),
            date=self.past_date
        )

        # Grant access for 15 days starting from past_date
        self.grant_end = JobAssignment.compute_end_date('15_DAYS', self.past_date)
        JobAssignment.objects.create(
            job=self.job,
            staff=self.staff_user,
            duration_label='15_DAYS',
            granted_start=self.past_date,
            granted_end=self.grant_end
        )

    def test_past_job_visible_in_staff_dashboard_during_grant_period(self):
        """Job created 2 days ago with 15-day grant must appear in active_today_jobs today."""
        self.client.login(username='teststaff', password='password123')
        response = self.client.get('/my-dashboard/')
        self.assertEqual(response.status_code, 200)
        
        active_today_jobs = response.context['active_today_jobs']
        self.assertEqual(len(active_today_jobs), 1)
        self.assertEqual(active_today_jobs[0].id, self.job.id)

    def test_daily_recheckin_after_previous_day_checkout(self):
        """Checking out yesterday should not block re-checking in today."""
        # Create a checkin/checkout record from 2 days ago
        past_timestamp = timezone.now() - datetime.timedelta(days=2)
        record = CheckInRecord.objects.create(
            job=self.job,
            user=self.staff_user,
            check_in_lat=27.7000,
            check_in_lng=85.3000,
            accuracy=10.0,
            distance_from_center=5.0,
            is_inside_geofence=True,
            check_out_timestamp=past_timestamp + datetime.timedelta(hours=8),
            status='APPROVED'
        )
        CheckInRecord.objects.filter(pk=record.pk).update(timestamp=past_timestamp)

        self.client.login(username='teststaff', password='password123')
        response = self.client.get('/my-dashboard/')
        self.assertEqual(response.status_code, 200)

        # Job should be in active_today_jobs for re-checkin today, NOT completed_today_jobs
        active_today_jobs = response.context['active_today_jobs']
        completed_today_jobs = response.context['completed_today_jobs']
        self.assertEqual(len(active_today_jobs), 1)
        self.assertEqual(len(completed_today_jobs), 0)

    def test_checkin_allowed_today(self):
        """Staff should be able to check in today during grant period."""
        self.client.login(username='teststaff', password='password123')
        response = self.client.post(f'/checkin/{self.job.id}/', {
            'lat': 27.7000,
            'lng': 85.3000,
            'accuracy': 5.0
        })
        self.assertEqual(response.status_code, 200)
        json_data = response.json()
        self.assertTrue(json_data.get('ok'))


class BackupRestoreTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.admin_user = User.objects.create_superuser(username='adminbackup', email='admin@example.com', password='adminpassword')
        self.admin_user.profile.role = 'SUPER_ADMIN'
        self.admin_user.profile.save()

    def test_admin_can_export_backup(self):
        """Super Admin can export full JSON database backup."""
        self.client.login(username='adminbackup', password='adminpassword')
        response = self.client.get('/settings/backup/export/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        self.assertIn('attachment; filename="stafftracker_backup_', response['Content-Disposition'])
        
        # Verify response body is valid JSON
        import json
        content = response.content.decode('utf-8')
        data = json.loads(content)
        self.assertIsInstance(data, list)
