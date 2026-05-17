"""Pydantic model round-trip and alias tests."""
from __future__ import annotations

from filesir.models import (
    FileEntry,
    NewUploadCompletedPart,
    NewUploadInitResponse,
    NewUploadNext,
    Page,
    Workspace,
    WorkspaceMember,
)


def test_file_entry_roundtrip_preserves_keys() -> None:
    payload = {
        "id": 7,
        "name": "image.png",
        "file_name": "raw_name",
        "file_size": 1234,
        "parent_id": 3,
        "workspace_id": 0,
        "type": "image",
        "created_at": "2021-02-23T14:42:38.000000Z",
    }
    entry = FileEntry.model_validate(payload)
    dumped = entry.model_dump(by_alias=True, exclude_none=True)
    for key, value in payload.items():
        assert dumped[key] == value


def test_completed_part_pascal_case_aliases() -> None:
    raw = {"PartNumber": 1, "ETag": '"abc"'}
    part = NewUploadCompletedPart.model_validate(raw)
    dumped = part.model_dump(by_alias=True)
    assert dumped == raw
    # Constructor by python attribute names also accepts these aliases via populate_by_name=True.
    part2 = NewUploadCompletedPart(PartNumber=2, ETag='"x"')
    assert part2.model_dump(by_alias=True) == {"PartNumber": 2, "ETag": '"x"'}


def test_new_upload_init_response_aliases() -> None:
    raw = {
        "status": "success",
        "uploadSessionId": "sid-1",
        "uploadMode": "s3-multipart",
        "partSize": 20971520,
        "next": None,
    }
    parsed = NewUploadInitResponse.model_validate(raw)
    dumped = parsed.model_dump(by_alias=True, exclude_none=True)
    for key in ("uploadSessionId", "uploadMode", "partSize"):
        assert dumped[key] == raw[key]


def test_new_upload_next_complete_url_alias() -> None:
    raw = {"method": "POST", "url": "https://x", "completeUrl": "https://x/complete"}
    parsed = NewUploadNext.model_validate(raw)
    dumped = parsed.model_dump(by_alias=True, exclude_none=True)
    assert dumped["completeUrl"] == raw["completeUrl"]


def test_workspace_member_with_model_type() -> None:
    raw = {
        "id": 1,
        "email": "a@b",
        "is_owner": False,
        "member_id": 1,
        "name": "Alice",
        "model_type": "member",
    }
    member = WorkspaceMember.model_validate(raw)
    assert member.model_type == "member"


def test_page_defaults() -> None:
    page: Page[Workspace] = Page(data=[])
    assert page.total is None and page.last_page is None
