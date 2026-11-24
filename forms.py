from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.password_validation import validate_password


class CheckoutForm(forms.Form):
    customer_name = forms.CharField(label="Full name", max_length=120)
    customer_email = forms.EmailField(label="Email", max_length=190)
    customer_phone = forms.CharField(label="Phone", max_length=40, required=False)
    address = forms.CharField(label="Address", max_length=190)
    city = forms.CharField(label="City", max_length=100)
    state = forms.CharField(label="State / region", max_length=100, required=False)
    postcode = forms.CharField(label="Postcode", max_length=20)
    country = forms.CharField(label="Country", max_length=100)
    notes = forms.CharField(label="Order notes", max_length=1000, required=False, widget=forms.Textarea(attrs={"rows": 3}))
    payment_method = forms.ChoiceField(label="Payment method", widget=forms.RadioSelect)

    def __init__(self, *args, methods: dict[str, str], **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["payment_method"].choices = list(methods.items())


class TrackForm(forms.Form):
    number = forms.CharField(label="Order number", max_length=40, help_text="For example DS-2026-000001")
    email = forms.EmailField(label="Email used at checkout")


class EmailLoginForm(AuthenticationForm):
    username = forms.CharField(label="Email", widget=forms.EmailInput(attrs={"autofocus": True}))


class RegisterForm(forms.Form):
    name = forms.CharField(label="Full name", max_length=120)
    email = forms.EmailField(label="Email", max_length=150)
    password1 = forms.CharField(label="Password", widget=forms.PasswordInput)
    password2 = forms.CharField(label="Confirm password", widget=forms.PasswordInput)

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()

        if get_user_model().objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("An account with this email already exists.")

        return email

    def clean(self):
        cleaned = super().clean()
        password1, password2 = cleaned.get("password1"), cleaned.get("password2")

        if password1 and password2 and password1 != password2:
            self.add_error("password2", "The two passwords do not match.")
        elif password1:
            try:
                validate_password(password1)
            except forms.ValidationError as error:
                self.add_error("password1", error)

        return cleaned

    def save(self):
        email = self.cleaned_data["email"]

        return get_user_model().objects.create_user(
            username=email,
            email=email,
            password=self.cleaned_data["password1"],
            first_name=self.cleaned_data["name"],
        )


class AccountForm(forms.Form):
    name = forms.CharField(label="Full name", max_length=120)
    email = forms.EmailField(label="Email", max_length=150)
    password1 = forms.CharField(
        label="New password", required=False, widget=forms.PasswordInput, help_text="Leave blank to keep the current one"
    )
    password2 = forms.CharField(label="Confirm new password", required=False, widget=forms.PasswordInput)

    def __init__(self, *args, user, **kwargs):
        self.user = user
        kwargs.setdefault("initial", {"name": user.first_name, "email": user.email})
        super().__init__(*args, **kwargs)

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        taken = get_user_model().objects.filter(email__iexact=email).exclude(pk=self.user.pk)

        if taken.exists():
            raise forms.ValidationError("Another account already uses this email.")

        return email

    def clean(self):
        cleaned = super().clean()
        password1, password2 = cleaned.get("password1"), cleaned.get("password2")

        if password1 or password2:
            if password1 != password2:
                self.add_error("password2", "The two passwords do not match.")
            else:
                try:
                    validate_password(password1, self.user)
                except forms.ValidationError as error:
                    self.add_error("password1", error)

        return cleaned

    def save(self):
        user = self.user
        user.first_name = self.cleaned_data["name"]
        user.email = self.cleaned_data["email"]
        user.username = user.email

        if self.cleaned_data.get("password1"):
            user.set_password(self.cleaned_data["password1"])

        user.save()

        return user
