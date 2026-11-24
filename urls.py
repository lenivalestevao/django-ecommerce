from django.contrib.auth import views as auth_views
from django.urls import path, reverse_lazy

from . import views

urlpatterns = [
    # Storefront
    path("", views.home, name="home"),
    path("shop/", views.shop_index, name="shop"),
    path("category/<slug:slug>/", views.shop_index, name="category"),
    path("product/<slug:slug>/", views.product_detail, name="product"),
    # Cart
    path("cart/", views.cart_detail, name="cart"),
    path("cart/add/<slug:slug>/", views.cart_add, name="cart_add"),
    path("cart/update/<slug:slug>/", views.cart_update, name="cart_update"),
    path("cart/remove/<slug:slug>/", views.cart_remove, name="cart_remove"),
    path("cart/coupon/", views.coupon_apply, name="coupon_apply"),
    path("cart/coupon/remove/", views.coupon_remove, name="coupon_remove"),
    # Checkout and orders
    path("checkout/", views.checkout, name="checkout"),
    path("orders/<str:number>/", views.order_detail, name="order"),
    path("orders/<str:number>/pay/", views.order_pay, name="order_pay"),
    path("track/", views.track, name="track"),
    # Payments
    path("payment/<str:number>/return/", views.payment_return, name="payment_return"),
    path("payment/<str:number>/cancel/", views.payment_cancel, name="payment_cancel"),
    path("payment/webhook/<str:gateway>/", views.payment_webhook, name="payment_webhook"),
    # Accounts
    path("login/", views.ShopLoginView.as_view(), name="login"),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("register/", views.register, name="register"),
    path("account/", views.account, name="account"),
    path(
        "password-reset/",
        auth_views.PasswordResetView.as_view(
            template_name="shop/auth/password_reset.html",
            email_template_name="shop/auth/password_reset_email.txt",
            subject_template_name="shop/auth/password_reset_subject.txt",
            success_url=reverse_lazy("password_reset_done"),
        ),
        name="password_reset",
    ),
    path(
        "password-reset/done/",
        auth_views.PasswordResetDoneView.as_view(template_name="shop/auth/password_reset_done.html"),
        name="password_reset_done",
    ),
    path(
        "reset/<uidb64>/<token>/",
        auth_views.PasswordResetConfirmView.as_view(
            template_name="shop/auth/password_reset_confirm.html",
            success_url=reverse_lazy("password_reset_complete"),
        ),
        name="password_reset_confirm",
    ),
    path(
        "reset/done/",
        auth_views.PasswordResetCompleteView.as_view(template_name="shop/auth/password_reset_complete.html"),
        name="password_reset_complete",
    ),
    # Staff
    path("dashboard/", views.dashboard, name="dashboard"),
]
