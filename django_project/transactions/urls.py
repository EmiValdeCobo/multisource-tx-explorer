from django.urls import path
from transactions import views

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    # Upload
    path("upload/", views.upload_json, name="upload_json"),
    # Runs
    path("runs/", views.run_list, name="run_list"),
    path("runs/<int:pk>/", views.run_detail, name="run_detail"),
    path("runs/<int:pk>/delete/", views.run_delete, name="run_delete"),
    path("runs/<int:pk>/download/json/", views.run_download_json, name="run_download_json"),
    path("runs/<int:pk>/download/csv/", views.run_download_csv, name="run_download_csv"),
    # Transactions
    path("transactions/", views.transaction_list, name="transaction_list"),
    path("transactions/<int:pk>/", views.transaction_detail, name="transaction_detail"),
    # Errors
    path("errors/", views.error_list, name="error_list"),
    # Global downloads
    path("download/json/", views.download_json, name="download_json"),
    path("download/csv/", views.download_csv, name="download_csv"),
]
