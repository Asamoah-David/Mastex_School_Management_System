from .signals import set_current_user


class AuditUserMiddleware:
    """
    Captures the authenticated user into thread-local storage so that
    Django signals (pre_save, post_save, post_delete) can attribute
    changes to the user who made them.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, "user", None)
        if user and getattr(user, "is_authenticated", False):
            set_current_user(user)
        else:
            set_current_user(None)

        response = self.get_response(request)

        # Clear to avoid leaking user across requests in the same thread
        set_current_user(None)
        return response
