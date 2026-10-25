"""Regression for HTTP 400 observed in the isolated real Blob drill."""

import pytest

from company_lens.events.blob_store import BlobRequestError, MemoryBlob, _put_immutable


def test_private_read_uses_origin_body_and_its_etag():
    from company_lens.events.blob_store import HttpBlobTransport

    class Response:
        status_code = 200
        content = b'{"generation":1}'
        def __init__(self):
            self.headers = {"etag": '"origin-etag"'}

    class Session:
        def get(self, url, **kwargs):
            assert kwargs["headers"]["Accept-Encoding"] == "identity"
            assert url == "https://example.private.blob.vercel-storage.com/commit.json?cache=0"
            return Response()

    transport = HttpBlobTransport("test-only", session=Session())
    assert transport.read_url(
        "https://example.private.blob.vercel-storage.com/commit.json"
    ) == (Response.content, '"origin-etag"')


class ExistingPath400(MemoryBlob):
    def put(self, pathname, body, *, if_match, overwrite):
        if self.get_prefix(pathname) and not overwrite:
            raise BlobRequestError(400, pathname)
        return super().put(pathname, body, if_match=if_match, overwrite=overwrite)


def test_existing_identical_object_is_reused_after_http_400():
    blob = ExistingPath400()
    first = _put_immutable(blob, "checkpoint.json", b'{"version":1}')
    second = _put_immutable(blob, "checkpoint.json", b'{"version":1}')
    assert second["url"] == first["url"]


def test_existing_different_object_is_never_overwritten_after_http_400():
    blob = ExistingPath400()
    first = _put_immutable(blob, "checkpoint.json", b'{"version":1}')
    with pytest.raises(BlobRequestError):
        _put_immutable(blob, "checkpoint.json", b'{"version":2}')
    assert blob.read_url(first["url"])[0] == b'{"version":1}'


def test_other_http_400_is_not_treated_as_success():
    class InvalidRequest(MemoryBlob):
        def put(self, pathname, body, *, if_match, overwrite):
            raise BlobRequestError(400, pathname)

    with pytest.raises(BlobRequestError) as caught:
        _put_immutable(InvalidRequest(), "checkpoint.json", b"{}")
    assert caught.value.status == 400
