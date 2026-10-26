from django.contrib.admin.views.decorators import staff_member_required
from django.http import FileResponse, Http404

from .models import ProfessionalProfile


@staff_member_required
def private_identity_document(request, user_id):
    try:
        profile = ProfessionalProfile.objects.get(user_id=user_id)
    except ProfessionalProfile.DoesNotExist as exc:
        raise Http404 from exc
    if not profile.identity_document:
        raise Http404
    file_handle = profile.identity_document.open("rb")
    return FileResponse(
        file_handle, as_attachment=True, filename=profile.identity_document.name.rsplit("/", 1)[-1]
    )
