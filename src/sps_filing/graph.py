"""A thin Microsoft Graph client for the mail-to-SharePoint path.

Only the calls this job needs, with paging handled. Authentication is a
managed identity in Azure and a developer sign-in locally, both via
DefaultAzureCredential.
"""

from __future__ import annotations

import datetime as _dt
import logging
from typing import Any, Iterator

import httpx
from azure.identity import DefaultAzureCredential

GRAPH = "https://graph.microsoft.com/v1.0"
SCOPE = "https://graph.microsoft.com/.default"
#: Graph accepts a simple PUT below 4 MB; anything larger needs a session.
SIMPLE_UPLOAD_LIMIT = 4 * 1024 * 1024

log = logging.getLogger(__name__)


class GraphError(RuntimeError):
    def __init__(self, response: httpx.Response) -> None:
        self.status_code = response.status_code
        super().__init__(f"{response.status_code} {response.request.url}: {response.text[:500]}")


class GraphClient:
    def __init__(self, credential=None, timeout: float = 60.0) -> None:
        self._credential = credential or DefaultAzureCredential()
        self._client = httpx.Client(timeout=timeout)
        self._token: str | None = None
        self._expires_on: float = 0.0

    # -- plumbing ---------------------------------------------------------
    def _headers(self) -> dict[str, str]:
        now = _dt.datetime.now(_dt.timezone.utc).timestamp()
        if self._token is None or now >= self._expires_on - 300:
            token = self._credential.get_token(SCOPE)
            self._token, self._expires_on = token.token, token.expires_on
        return {"Authorization": f"Bearer {self._token}"}

    def request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        if not url.startswith("http"):
            url = f"{GRAPH}{url}"
        headers = {**self._headers(), **kwargs.pop("headers", {})}
        response = self._client.request(method, url, headers=headers, **kwargs)
        if response.status_code >= 400:
            raise GraphError(response)
        return response

    def get_json(self, url: str, **kwargs: Any) -> dict:
        return self.request("GET", url, **kwargs).json()

    def paged(self, url: str, **kwargs: Any) -> Iterator[dict]:
        while url:
            payload = self.get_json(url, **kwargs)
            yield from payload.get("value", [])
            url = payload.get("@odata.nextLink", "")
            kwargs.pop("params", None)  # nextLink already carries the query

    def close(self) -> None:
        self._client.close()

    # -- mail -------------------------------------------------------------
    def list_inbox_messages(
        self, mailbox: str, since: _dt.datetime, until: _dt.datetime | None = None
    ) -> Iterator[dict]:
        clauses = [f"receivedDateTime ge {since.astimezone(_dt.timezone.utc):%Y-%m-%dT%H:%M:%SZ}"]
        if until is not None:
            clauses.append(f"receivedDateTime le {until.astimezone(_dt.timezone.utc):%Y-%m-%dT%H:%M:%SZ}")
        params = {
            "$filter": " and ".join(clauses),
            "$select": "id,subject,from,receivedDateTime,internetMessageId,hasAttachments",
            "$orderby": "receivedDateTime asc",
            "$top": "50",
        }
        yield from self.paged(
            f"/users/{mailbox}/mailFolders/inbox/messages", params=params
        )

    def list_attachments(self, mailbox: str, message_id: str) -> list[dict]:
        return list(self.paged(f"/users/{mailbox}/messages/{message_id}/attachments"))

    def message_mime(self, mailbox: str, message_id: str) -> bytes:
        """The raw .eml, for reports that arrive as a link rather than a file."""
        return self.request("GET", f"/users/{mailbox}/messages/{message_id}/$value").content

    # -- sharepoint -------------------------------------------------------
    def site_id(self, hostname: str, site_path: str) -> str:
        return self.get_json(f"/sites/{hostname}:{site_path}")["id"]

    def drive_id(self, site_id: str, library_name: str) -> str:
        for drive in self.paged(f"/sites/{site_id}/drives"):
            if drive.get("name") == library_name:
                return drive["id"]
        raise GraphError_missing(library_name)

    def list_items(self, site_id: str, list_name: str) -> Iterator[dict]:
        params = {"$expand": "fields", "$top": "500"}
        for item in self.paged(f"/sites/{site_id}/lists/{list_name}/items", params=params):
            yield item.get("fields", {})

    def find_item_by_path(self, drive_id: str, path: str) -> dict | None:
        try:
            return self.get_json(f"/drives/{drive_id}/root:{_encode(path)}")
        except GraphError as exc:
            if exc.status_code == 404:
                return None
            raise

    def item_fields(self, drive_id: str, item_id: str) -> dict:
        payload = self.get_json(
            f"/drives/{drive_id}/items/{item_id}/listItem", params={"$expand": "fields"}
        )
        return payload.get("fields", {})

    def upload(self, drive_id: str, path: str, content: bytes) -> dict:
        """Create or replace a file, creating any missing folders on the way."""
        if len(content) < SIMPLE_UPLOAD_LIMIT:
            return self.request(
                "PUT",
                f"/drives/{drive_id}/root:{_encode(path)}:/content",
                content=content,
                headers={"Content-Type": "application/octet-stream"},
            ).json()
        return self._upload_session(drive_id, path, content)

    def _upload_session(self, drive_id: str, path: str, content: bytes) -> dict:
        session = self.request(
            "POST",
            f"/drives/{drive_id}/root:{_encode(path)}:/createUploadSession",
            json={"item": {"@microsoft.graph.conflictBehavior": "replace"}},
        ).json()
        url, chunk, total = session["uploadUrl"], 5 * 1024 * 1024, len(content)
        for start in range(0, total, chunk):
            end = min(start + chunk, total) - 1
            response = self._client.put(
                url,
                content=content[start : end + 1],
                headers={
                    "Content-Length": str(end - start + 1),
                    "Content-Range": f"bytes {start}-{end}/{total}",
                },
                timeout=300.0,
            )
            if response.status_code >= 400:
                raise GraphError(response)
            if response.status_code in (200, 201):
                return response.json()
        raise RuntimeError("upload session ended without a completed item")

    def set_fields(self, drive_id: str, item_id: str, fields: dict) -> None:
        self.request(
            "PATCH", f"/drives/{drive_id}/items/{item_id}/listItem/fields", json=fields
        )


def GraphError_missing(library: str) -> RuntimeError:  # noqa: N802
    return RuntimeError(f"no drive named {library!r} on that site")


def _encode(path: str) -> str:
    """Graph path addressing: keep the slashes, escape everything else."""
    from urllib.parse import quote

    return quote(path if path.startswith("/") else f"/{path}", safe="/")
