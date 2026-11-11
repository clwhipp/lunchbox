from django.urls import path

from schoolmenu import views

urlpatterns = [
    path("", views.index, name="index"),
    path("foods/<int:food_id>/", views.detail, name="detail"),
    path("foods/<int:food_id>/thumbnail/", views.thumbnail, name="thumbnail"),
    path("foods/<int:food_id>/preference/", views.preference, name="preference"),
    path("sack-lunch/", views.sack_lunch, name="sack_lunch"),
    path("health/live", views.live, name="live"),
    path("health/ready", views.ready, name="ready"),
]
