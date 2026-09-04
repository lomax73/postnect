from django.urls import path

from . import views

urlpatterns = [
    path('users/', views.InternalUserListView.as_view(), name='internal-user-list'),
    path('users/<int:pk>/', views.InternalUserDetailView.as_view(), name='internal-user-detail'),
]
