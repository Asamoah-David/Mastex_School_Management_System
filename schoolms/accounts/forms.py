from django import forms
from django.contrib.auth.forms import PasswordResetForm
from django.contrib.auth import get_user_model

User = get_user_model()


class SecurePasswordResetForm(PasswordResetForm):
    """
    Secure password reset form with full validation to prevent:
    - Inactive users from resetting passwords
    - Users from inactive schools from resetting
    - Locked out users from bypassing lockout via password reset
    - Email enumeration/probing attacks
    """
    
    def clean_email(self):
        email = self.cleaned_data['email']
        return email.lower().strip()
    
    def get_users(self, email):
        """
        Override to only return valid, active users who can reset their password.
        This prevents inactive users, locked out users, and users from inactive schools.
        """
        active_users = User.objects.filter(
            email__iexact=email,
            is_active=True,
        )
        
        # Filter out users who shouldn't be able to reset password
        valid_users = []
        for user in active_users:
            # Check if user is locked out
            if hasattr(user, 'is_locked_out') and user.is_locked_out():
                continue
            
            # Check if user's school is active (skip for superusers/super_admins)
            if hasattr(user, 'school') and user.school:
                if not user.is_superuser and user.role != 'super_admin':
                    if not user.school.is_active:
                        continue
            
            valid_users.append(user)
        
        return valid_users
    
    def save(self, domain=None, use_https=False, token_generator=None, request=None, **kwargs):
        """
        Override to send emails only to valid users.
        Shows the same success message for all inputs to prevent email probing.
        """
        email = self.cleaned_data['email']
        users = self.get_users(email)
        
        # Even if no valid users found, show the same success message
        # This prevents attackers from knowing which emails are registered
        if not users:
            # Still return a success-like response to prevent enumeration
            return
        
        # Send password reset email to valid users only
        for user in users:
            user.set_password_reset_token()
        
        # Use Django's built-in email sending
        super().save(domain=domain, use_https=use_https, 
                     token_generator=token_generator, request=request, **kwargs)


class PasswordResetConfirmForm(forms.Form):
    """
    Custom form for password reset confirmation with additional validation.
    """
    new_password1 = forms.CharField(
        label="New Password",
        widget=forms.PasswordInput(attrs={'class': 'form-control', 'placeholder': 'Enter new password'}),
        min_length=8,
    )
    new_password2 = forms.CharField(
        label="Confirm New Password",
        widget=forms.PasswordInput(attrs={'class': 'form-control', 'placeholder': 'Confirm new password'}),
        min_length=8,
    )
    
    def clean(self):
        cleaned_data = super().clean()
        password1 = cleaned_data.get('new_password1')
        password2 = cleaned_data.get('new_password2')
        
        if password1 and password2:
            if password1 != password2:
                raise forms.ValidationError("Passwords don't match.")
            
            # Basic password strength check
            if len(password1) < 8:
                raise forms.ValidationError("Password must be at least 8 characters.")
        
        return cleaned_data