from django.urls import path

from schoolmenu import views

urlpatterns = [
    path("", views.index, name="index"),
    path("calendar/settings/", views.calendar_settings, name="calendar_settings"),
    path("calendar/<str:token>.ics", views.calendar_ics, name="calendar_feed"),
    path("foods/<int:food_id>/", views.detail, name="detail"),
    path("foods/<int:food_id>/thumbnail/", views.thumbnail, name="thumbnail"),
    path("foods/<int:food_id>/preference/", views.preference, name="preference"),
    path("foods/<int:food_id>/exclusion/", views.exclusion, name="exclusion"),
    path("sack-lunch/", views.sack_lunch, name="sack_lunch"),
    path("health/live", views.live, name="live"),
    path("health/ready", views.ready, name="ready"),
]
