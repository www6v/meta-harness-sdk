"""Lightweight response objects that mimic Anthropic SDK model attribute access."""

from __future__ import annotations

from typing import Any, Iterable, Iterator, Sequence


class APIObject:
    """Dict wrapper with ``.id`` / ``["id"]`` access (Anthropic SDK shape)."""

    def __init__(self, data: dict[str, Any] | None = None, **extra: Any) -> None:
        raw = dict(data or {})
        raw.update(extra)
        # CMA FileMetadata uses mime_type; OMA wire uses media_type.
        if "media_type" in raw and "mime_type" not in raw:
            raw["mime_type"] = raw["media_type"]
        if "mime_type" in raw and "media_type" not in raw:
            raw["media_type"] = raw["mime_type"]
        object.__setattr__(self, "_data", raw)

    def __getattr__(self, name: str) -> Any:
        data = object.__getattribute__(self, "_data")
        if name in data:
            return data[name]
        raise AttributeError(f"{type(self).__name__!s} has no attribute {name!r}")

    def __setattr__(self, name: str, value: Any) -> None:
        if name == "_data":
            object.__setattr__(self, name, value)
            return
        self._data[name] = value

    def __getitem__(self, key: str) -> Any:
        return self._data[key]

    def __contains__(self, key: object) -> bool:
        return key in self._data

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)

    def keys(self):
        return self._data.keys()

    def items(self):
        return self._data.items()

    def values(self):
        return self._data.values()

    def model_dump(self) -> dict[str, Any]:
        return dict(self._data)

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump()

    def __repr__(self) -> str:
        return f"{type(self).__name__}({self._data!r})"


class SyncPage(Sequence[APIObject]):
    """Iterable page mirroring Anthropic ``SyncPageCursor`` enough for ``for x in list()``."""

    def __init__(
        self,
        data: Iterable[dict[str, Any] | APIObject],
        *,
        has_more: bool = False,
        first_id: str | None = None,
        last_id: str | None = None,
        next_page: str | None = None,
    ) -> None:
        items: list[APIObject] = []
        for item in data:
            items.append(item if isinstance(item, APIObject) else APIObject(item))
        self.data = items
        self.has_more = has_more
        self.first_id = first_id
        self.last_id = last_id
        self.next_page = next_page

    def __iter__(self) -> Iterator[APIObject]:
        return iter(self.data)

    def __len__(self) -> int:
        return len(self.data)

    def __repr__(self) -> str:
        return f"SyncPage(data={self.data!r}, has_more={self.has_more!r})"

    def get(self, key: str, default: Any = None) -> Any:
        """Dict-compat for older call sites using ``page.get(\"data\")``."""
        mapping = {
            "data": self.data,
            "has_more": self.has_more,
            "first_id": self.first_id,
            "last_id": self.last_id,
            "next_page": self.next_page,
        }
        return mapping.get(key, default)

    def __getitem__(self, index):  # type: ignore[override]
        if isinstance(index, str):
            value = self.get(index)
            if value is None and index not in (
                "data", "has_more", "first_id", "last_id", "next_page"
            ):
                raise KeyError(index)
            return value
        return self.data[index]


def wrap(data: dict[str, Any] | None) -> APIObject:
    return APIObject(data or {})


def wrap_page(payload: dict[str, Any]) -> SyncPage:
    rows = payload.get("data") or []
    return SyncPage(
        rows,
        has_more=bool(payload.get("has_more", False)),
        first_id=payload.get("first_id"),
        last_id=payload.get("last_id"),
        next_page=payload.get("next_page"),
    )


def wrap_response(response: Any) -> APIObject:
    """Parse JSON body and attach ``_request_id`` from response headers."""
    from .._exceptions import raise_for_status
    from .._http import request_id_from

    raise_for_status(response)
    obj = wrap(response.json() if response.content else {})
    rid = request_id_from(response)
    if rid is not None:
        obj._request_id = rid
    return obj


def wrap_page_response(response: Any) -> SyncPage:
    from .._exceptions import raise_for_status

    raise_for_status(response)
    return wrap_page(response.json() if response.content else {"data": []})

