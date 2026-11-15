from django.contrib.auth import views as auth_views
from django.urls import path

from . import views, views_line

app_name = "accounts"

urlpatterns = [
    path("login/", auth_views.LoginView.as_view(template_name="accounts/login.html"), name="login"),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("signup/", views.SignUpView.as_view(), name="signup"),
    path("profile/", views.ProfileView.as_view(), name="profile"),
    path("line/", views_line.LineLinkView.as_view(), name="line_link"),
    path("password/", views.PasswordChange.as_view(), name="password_change"),
    path("users/", views.UserListView.as_view(), name="user_list"),
    path("users/<int:pk>/edit/", views.UserEditView.as_view(), name="user_edit"),
]
