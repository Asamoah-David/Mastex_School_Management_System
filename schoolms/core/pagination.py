"""Reusable pagination helper for all list views."""
from django.core.paginator import Paginator


def paginate(request, queryset, per_page=25):
    """Paginate a queryset and return a Page object.

    The returned object supports iteration, .has_previous, .has_next,
    .paginator.page_range, etc. — everything Django templates expect.
    Query-string parameter ``page`` controls the current page.
    """
    paginator = Paginator(queryset, per_page)
    page_number = request.GET.get("page")
    return paginator.get_page(page_number)
