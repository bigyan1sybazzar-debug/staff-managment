from django.urls import path
from . import views

urlpatterns = [
    path("", views.dashboard_view, name="dashboard"),
    path("my-dashboard/", views.staff_dashboard_view, name="staff_dashboard"),
    path("login/", views.login_view, name="login"),
    path("logout/", views.logout_view, name="logout"),
    path("staff/", views.staff_list_view, name="staff_list"),
    path("staff/add/", views.staff_create_view, name="staff_create"),
    path("staff/<int:pk>/edit/", views.staff_update_view, name="staff_update"),
    path("staff/<int:pk>/delete/", views.staff_delete_view, name="staff_delete"),
    
    # Jobs CRUD
    path("jobs/", views.job_list_view, name="job_list"),
    path("jobs/add/", views.job_create_view, name="job_create"),
    path("jobs/<int:pk>/edit/", views.job_update_view, name="job_update"),
    path("jobs/<int:pk>/delete/", views.job_delete_view, name="job_delete"),
    path("jobs/adhoc/add/", views.adhoc_job_create_view, name="adhoc_job_create"),
    path("api/work-locations/", views.work_locations_api, name="work_locations_api"),
    path("profile/documents/upload/", views.profile_documents_upload_view, name="profile_documents_upload"),
    path("history/", views.history_view, name="history"),
    path("map/", views.map_view, name="map_view"),

    # Check-In / Check-Out
    path("checkin/<int:job_pk>/", views.checkin_view, name="checkin"),
    path("checkout/<int:record_pk>/", views.checkout_view, name="checkout"),

    # Settings & Backup
    path("settings/backup/", views.backup_settings_view, name="backup_settings"),
    path("settings/backup/export/", views.export_backup_view, name="export_backup"),
    path("settings/backup/import/", views.import_backup_view, name="import_backup"),

    # API endpoints
    path("api/staff-locations/", views.staff_locations_api, name="staff_locations_api"),
    path("api/log-location/", views.log_location_api, name="log_location_api"),
]
