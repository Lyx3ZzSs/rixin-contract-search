from json import JSONDecodeError
from typing import Any
from urllib.parse import unquote_to_bytes, urlsplit

import httpx
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.config import settings
from app.models import QmdCandidateSnippet, ScreeningTask


class QmdUnavailable(RuntimeError):
    pass


class QmdResult(BaseModel):
    file: str
    docid: str | None = None
    title: str | None = None
    score: float | None = None
    snippet: str | None = None
    text: str | None = None
    line: int | None = None
    page_number: int | None = None
    raw: dict[str, Any] = Field(default_factory=dict)


class QmdClient:
    def __init__(self, url: str | None = None, timeout: float = 60.0):
        self.url = (url or settings.QMD_MCP_URL).rstrip("/")
        self.timeout = timeout
        self._session_id: str | None = None
        self._next_id = 1

    def status(self) -> dict[str, Any]:
        payload = self._call_tool("status", {})
        structured = payload.get("structuredContent")
        if isinstance(structured, dict):
            return structured
        text = extract_text(payload)
        return {"text": text, "collections": parse_status_collections(text)}

    def query(self, query_text: str, collections: list[str], limit: int) -> list[QmdResult]:
        payload = self._call_tool(
            "query",
            {
                "query": query_text,
                "collections": collections,
                "limit": limit,
            },
        )
        structured = payload.get("structuredContent")
        raw_results = structured.get("results", []) if isinstance(structured, dict) else []
        results = []
        for item in raw_results:
            if not isinstance(item, dict):
                continue
            results.append(
                QmdResult(
                    file=str(item.get("file") or ""),
                    docid=item.get("docid"),
                    title=item.get("title"),
                    score=item.get("score"),
                    snippet=item.get("snippet"),
                    text=item.get("text"),
                    line=item.get("line"),
                    page_number=item.get("page_number"),
                    raw=item,
                )
            )
        return results

    def list_tools(self) -> list[str]:
        if self._session_id is None:
            self._initialize()
        response = self._post(
            {
                "jsonrpc": "2.0",
                "id": self._allocate_id(),
                "method": "tools/list",
                "params": {},
            }
        )
        result = response.get("result")
        if not isinstance(result, dict):
            raise QmdUnavailable("qmd MCP tools/list returned an invalid response")
        tools = result.get("tools")
        if not isinstance(tools, list):
            raise QmdUnavailable("qmd MCP tools/list returned invalid tools")
        return [
            item.get("name")
            for item in tools
            if (
                isinstance(item, dict)
                and isinstance(item.get("name"), str)
                and item.get("name")
            )
        ]

    def doc_toc(self, document_uri: str) -> dict[str, Any]:
        return self._deep_read_tool(
            "doc_toc",
            {"document_uri": validate_qmd_document_uri(document_uri)},
        )

    def doc_grep(self, document_uri: str, pattern: str) -> dict[str, Any]:
        return self._deep_read_tool(
            "doc_grep",
            {"document_uri": validate_qmd_document_uri(document_uri), "pattern": pattern},
        )

    def doc_read(
        self,
        document_uri: str,
        page: int | None = None,
        anchor: str | None = None,
        window: int = 2,
    ) -> dict[str, Any]:
        return self._deep_read_tool(
            "doc_read",
            {
                "document_uri": validate_qmd_document_uri(document_uri),
                "page": page,
                "anchor": anchor,
                "window": window,
            },
        )

    def doc_query(self, document_uri: str, question: str) -> dict[str, Any]:
        return self._deep_read_tool(
            "doc_query",
            {"document_uri": validate_qmd_document_uri(document_uri), "question": question},
        )

    def doc_elements(
        self,
        document_uri: str,
        page: int | None = None,
        anchor: str | None = None,
    ) -> dict[str, Any]:
        return self._deep_read_tool(
            "doc_elements",
            {
                "document_uri": validate_qmd_document_uri(document_uri),
                "page": page,
                "anchor": anchor,
            },
        )

    def document_preview(self, document_uri: str) -> dict[str, Any]:
        safe_uri = validate_qmd_document_uri(document_uri)
        payload = self.doc_toc(safe_uri)
        structured = payload.get("structuredContent")
        if isinstance(structured, dict):
            toc = structured.get("toc")
            document_title = clean_optional_string(structured.get("title"))
            collection = clean_optional_string(structured.get("collection"))
            summary = clean_optional_string(structured.get("summary"))
            open_url = structured.get("open_url")
            download_url = structured.get("download_url")
            open_url = open_url.strip() if isinstance(open_url, str) else None
            download_url = download_url.strip() if isinstance(download_url, str) else None
            open_url = open_url or None
            download_url = download_url or None
            return {
                "document_uri": safe_uri,
                "document_title": document_title,
                "collection": collection,
                "toc": toc if isinstance(toc, list) else [],
                "summary": summary,
                "can_open": open_url is not None,
                "can_download": download_url is not None,
                "open_url": open_url,
                "download_url": download_url,
            }
        text = extract_text(payload)
        return {
            "document_uri": safe_uri,
            "document_title": None,
            "collection": None,
            "toc": [],
            "summary": text or None,
            "can_open": False,
            "can_download": False,
            "open_url": None,
            "download_url": None,
        }

    def _deep_read_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        return self._call_tool(name, arguments)

    def _call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        if self._session_id is None:
            self._initialize()
        response = self._post(
            {
                "jsonrpc": "2.0",
                "id": self._allocate_id(),
                "method": "tools/call",
                "params": {"name": name, "arguments": arguments},
            }
        )
        result = response.get("result")
        if not isinstance(result, dict):
            raise QmdUnavailable(f"qmd MCP tool {name} returned an invalid response")
        if result.get("isError"):
            raise QmdUnavailable(extract_text(result) or f"qmd MCP tool {name} failed")
        return result

    def _initialize(self) -> None:
        response = self._post(
            {
                "jsonrpc": "2.0",
                "id": self._allocate_id(),
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "contract-screening-agent", "version": "0.1.0"},
                },
            },
            include_session=False,
            capture_session=True,
        )
        if "result" not in response:
            raise QmdUnavailable("qmd MCP initialize failed")
        self._post(
            {
                "jsonrpc": "2.0",
                "method": "notifications/initialized",
                "params": {},
            },
            expect_response=False,
        )

    def _post(self, payload: dict[str, Any], include_session: bool = True, capture_session: bool = False, expect_response: bool = True) -> dict[str, Any]:
        headers = {
            "Accept": "application/json, text/event-stream",
            "Content-Type": "application/json",
        }
        if include_session and self._session_id:
            headers["Mcp-Session-Id"] = self._session_id
        try:
            with httpx.Client(timeout=self.timeout, trust_env=False) as client:
                response = client.post(self.url, json=payload, headers=headers)
        except httpx.HTTPError as exc:
            raise QmdUnavailable(f"Unable to reach qmd MCP: {exc}") from exc
        if capture_session:
            self._session_id = response.headers.get("mcp-session-id") or response.headers.get("Mcp-Session-Id")
        if response.status_code >= 400:
            raise QmdUnavailable(f"qmd MCP returned HTTP {response.status_code}: {response.text[:300]}")
        if not response.content:
            if not expect_response:
                return {}
            raise QmdUnavailable(f"qmd MCP returned empty response from {self.url} with HTTP {response.status_code}")
        try:
            data = response.json()
        except JSONDecodeError as exc:
            raise QmdUnavailable(f"qmd MCP returned non-JSON response from {self.url} with HTTP {response.status_code}: {response.text[:300]}") from exc
        if isinstance(data, list):
            data = data[0] if data else {}
        if not isinstance(data, dict):
            raise QmdUnavailable("qmd MCP returned non-object JSON")
        if data.get("error"):
            raise QmdUnavailable(str(data["error"]))
        return data

    def _allocate_id(self) -> int:
        value = self._next_id
        self._next_id += 1
        return value


def configured_collections() -> list[str]:
    return [item.strip() for item in settings.QMD_COLLECTIONS.split(",") if item.strip()]


def ensure_collections_available(status: dict[str, Any], expected: list[str]) -> None:
    collections = status.get("collections", [])
    names = set()
    if isinstance(collections, list):
        for item in collections:
            if isinstance(item, dict) and item.get("name"):
                names.add(str(item["name"]))
            elif isinstance(item, str):
                names.add(item)
    missing = [name for name in expected if name not in names]
    if missing:
        raise QmdUnavailable(f"qmd collections not found: {', '.join(missing)}")


def extract_text(payload: dict[str, Any]) -> str:
    content = payload.get("content", [])
    if not isinstance(content, list):
        return ""
    parts = []
    for item in content:
        if isinstance(item, dict) and item.get("type") == "text":
            parts.append(str(item.get("text") or ""))
    return "\n".join(parts).strip()


def parse_status_collections(text: str) -> list[dict[str, Any]]:
    collections = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("- "):
            name = stripped[2:].split(":", 1)[0].strip()
            if name:
                collections.append({"name": name})
    return collections


def validate_qmd_document_uri(document_uri: str) -> str:
    value = document_uri.strip()
    if any(ord(char) < 0x20 or ord(char) == 0x7F for char in value):
        raise QmdUnavailable("qmd document URI contains an unsafe control character")
    try:
        parsed = urlsplit(value)
    except ValueError as exc:
        raise QmdUnavailable("qmd document URI is malformed") from exc
    if parsed.scheme != "qmd":
        raise QmdUnavailable("qmd document URI must start with qmd://")
    if not parsed.netloc:
        raise QmdUnavailable("qmd document URI requires a collection")
    if not parsed.path or parsed.path == "/":
        raise QmdUnavailable("qmd document URI requires a document path")
    if parsed.query or parsed.fragment:
        raise QmdUnavailable("qmd document URI must not include query or fragment")
    decoded_collection = strict_percent_decode(parsed.netloc)
    if (
        "\x00" in value
        or decoded_collection in {".", ".."}
        or "\x00" in decoded_collection
        or "/" in decoded_collection
        or "\\" in decoded_collection
        or "@" in decoded_collection
        or ":" in decoded_collection
    ):
        raise QmdUnavailable("qmd document URI contains an unsafe path segment")

    segments = parsed.path.split("/")[1:]
    for segment in segments:
        decoded = strict_percent_decode(segment)
        if (
            decoded in {"", ".", ".."}
            or "\x00" in decoded
            or "/" in decoded
            or "\\" in decoded
        ):
            raise QmdUnavailable("qmd document URI contains an unsafe path segment")
    return value


def clean_optional_string(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    value = value.strip()
    return value or None


def strict_percent_decode(value: str) -> str:
    for index, char in enumerate(value):
        if char != "%":
            continue
        escape = value[index + 1 : index + 3]
        if len(escape) != 2 or any(
            item not in "0123456789abcdefABCDEF" for item in escape
        ):
            raise QmdUnavailable("qmd document URI contains invalid percent encoding")
    try:
        return unquote_to_bytes(value).decode("utf-8")
    except UnicodeDecodeError as exc:
        raise QmdUnavailable("qmd document URI contains invalid percent encoding") from exc


def normalize_qmd_file(file_value: str, fallback_collection: str) -> tuple[str, str, str]:
    value = file_value.strip()
    if value.startswith("qmd://"):
        validate_qmd_document_uri(value)
        without_scheme = value[len("qmd://") :]
    else:
        without_scheme = value
    parts = without_scheme.split("/", 1)
    if len(parts) == 2 and parts[0]:
        collection, path = parts[0], parts[1]
    else:
        collection, path = fallback_collection, without_scheme
    document_uri = validate_qmd_document_uri(f"qmd://{collection}/{path}")
    return collection, path, document_uri


def persist_qmd_results(
    session: Session,
    task: ScreeningTask,
    condition_id: str,
    query_text: str,
    results: list[QmdResult | dict[str, Any]],
    fallback_collection: str,
) -> int:
    count = 0
    for raw_result in results:
        result = raw_result if isinstance(raw_result, QmdResult) else QmdResult(**raw_result, raw=raw_result)
        snippet = (result.snippet or result.text or "").strip()
        if not snippet or not result.file:
            continue
        collection, document_path, document_uri = normalize_qmd_file(result.file, fallback_collection)
        row = QmdCandidateSnippet(
            task_id=task.id,
            document_uri=document_uri,
            document_path=document_path,
            document_title=result.title,
            collection=collection,
            query_text=query_text,
            condition_id=condition_id,
            snippet_text=snippet,
            score=result.score,
            page_number=result.page_number if result.page_number and result.page_number > 0 else None,
            artifact_ref=document_uri,
            qmd_docid=result.docid,
            raw_result=result.raw or result.model_dump(),
            is_weak=len(snippet) < 4,
        )
        session.add(row)
        count += 1
    return count
