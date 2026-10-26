from pathlib import Path

from django.conf import settings
from django.core.files.storage import FileSystemStorage


class PrivateIdentityStorage(FileSystemStorage):
    def __init__(self, *args, **kwargs):
        super().__init__(location=Path(settings.BASE_DIR) / "private_uploads", base_url=None)

    def url(self, name):
        user_id = Path(name).parts[0]
        return f"/private-identity/{user_id}/"
