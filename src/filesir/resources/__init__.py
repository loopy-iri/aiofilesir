"""Resource façades for the Files.ir async client."""
from __future__ import annotations

from .auth import AuthResource
from .files import FilesResource
from .folders import FoldersResource
from .links import ShareableLinksResource
from .sharing import SharingResource
from .starring import StarringResource
from .storage import StorageResource
from .tags import TagsResource
from .workspaces import WorkspacesResource

__all__ = [
    "AuthResource",
    "FilesResource",
    "FoldersResource",
    "ShareableLinksResource",
    "SharingResource",
    "StarringResource",
    "StorageResource",
    "TagsResource",
    "WorkspacesResource",
]
