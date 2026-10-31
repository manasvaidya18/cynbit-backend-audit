"""
Offset and Keyset/Cursor-Based Pagination Architecture.

Demonstrates:
1. Offset-based pagination with strict limit/offset validation.
2. Maximum page size enforcement to protect memory & database.
3. Stable deterministic ordering to prevent missing/duplicate items.
4. Total count, pagination metadata (has_next, has_previous, next_offset).
5. Detailed explanation of when Cursor pagination is preferable.

Independent reference implementation for Cynbit Backend Technical Audit.
"""

import base64
from typing import Any, Dict, Generic, List, Optional, TypeVar
from fastapi import FastAPI, HTTPException, Query, status
from pydantic import BaseModel, Field

T = TypeVar("T")


# --- Pagination Schemas ---
class PageMetadata(BaseModel):
    """Metadata describing pagination boundaries and state."""
    total_count: int = Field(..., description="Total items available in the dataset")
    limit: int = Field(..., description="Maximum items per page requested")
    offset: int = Field(..., description="Number of items skipped from beginning")
    current_page: int = Field(..., description="1-indexed current page number")
    total_pages: int = Field(..., description="Total available pages")
    has_next: bool = Field(..., description="Whether subsequent pages exist")
    has_previous: bool = Field(..., description="Whether preceding pages exist")
    next_offset: Optional[int] = Field(default=None, description="Offset for next page")
    prev_offset: Optional[int] = Field(default=None, description="Offset for previous page")


class PaginatedResponse(BaseModel, Generic[T]):
    """Standardized offset-based pagination response envelope."""
    success: bool = True
    items: List[T]
    pagination: PageMetadata


class ItemModel(BaseModel):
    """Example entity item."""
    id: int
    title: str
    category: str
    created_at: str


# --- Cursor-Based Pagination Schemas ---
class CursorPaginationMetadata(BaseModel):
    limit: int
    next_cursor: Optional[str] = None
    has_more: bool


class CursorPaginatedResponse(BaseModel, Generic[T]):
    """Standardized keyset/cursor-based response envelope."""
    success: bool = True
    items: List[T]
    pagination: CursorPaginationMetadata


# --- In-Memory Mock Dataset with 150 Stable Records ---
MOCK_DATABASE = [
    {
        "id": i,
        "title": f"Threat Intelligence Briefing #{i}",
        "category": "Malware Analysis" if i % 2 == 0 else "Vulnerability Advisory",
        "created_at": f"2026-11-01T01:{i%60:02d}:00Z"
    }
    for i in range(1, 151)
]

# Ensure stable ordering by primary key
MOCK_DATABASE.sort(key=lambda x: x["id"])


# --- Standalone Reusable Pagination Helper ---
def paginate_records(
    records: List[Dict[str, Any]],
    offset: int = 0,
    limit: int = 20,
    max_limit: int = 100
) -> PaginatedResponse[Dict[str, Any]]:
    """
    Apply pagination and metadata calculation to a stably ordered sequence.
    
    Guarantees:
    - offset >= 0
    - 1 <= limit <= max_limit
    - Stable ordering
    - Consistent navigation offsets
    """
    if offset < 0:
        raise ValueError("Offset must be greater than or equal to 0.")
    if limit < 1:
        raise ValueError("Limit must be greater than or equal to 1.")
    if limit > max_limit:
        raise ValueError(f"Limit exceeds maximum allowed page size of {max_limit}.")

    total_count = len(records)
    # Perform offset-based slicing
    sliced_items = records[offset : offset + limit]

    total_pages = (total_count + limit - 1) // limit if total_count > 0 else 1
    current_page = (offset // limit) + 1

    has_next = (offset + limit) < total_count
    has_previous = offset > 0

    next_offset = (offset + limit) if has_next else None
    prev_offset = max(0, offset - limit) if has_previous else None

    meta = PageMetadata(
        total_count=total_count,
        limit=limit,
        offset=offset,
        current_page=current_page,
        total_pages=total_pages,
        has_next=has_next,
        has_previous=has_previous,
        next_offset=next_offset,
        prev_offset=prev_offset
    )

    return PaginatedResponse(items=sliced_items, pagination=meta)


# --- Cursor Helper Functions ---
def encode_cursor(item_id: int) -> str:
    """Encode an item ID into a URL-safe opaque cursor string."""
    return base64.urlsafe_b64encode(str(item_id).encode("utf-8")).decode("utf-8")


def decode_cursor(cursor_str: str) -> Optional[int]:
    """Decode a cursor string back into the boundary item ID."""
    try:
        raw = base64.urlsafe_b64decode(cursor_str.encode("utf-8")).decode("utf-8")
        return int(raw)
    except Exception:
        return None


# --- FastAPI Endpoint Application ---
app = FastAPI(
    title="Cynbit Pagination Reference API",
    description="Demonstrates bounded offset pagination and stable keyset ordering."
)


@app.get(
    "/api/items",
    response_model=PaginatedResponse[ItemModel],
    summary="List items with offset-based pagination",
    responses={
        422: {"description": "Validation error for limit/offset parameters"}
    }
)
def get_items(
    limit: int = Query(default=20, ge=1, le=100, description="Items per page (1-100)"),
    offset: int = Query(default=0, ge=0, description="Items to skip (>=0)")
):
    """
    Returns a paginated list of items.
    
    Guarantees:
    - Default page size: 20
    - Maximum page size enforced by FastAPI/Pydantic: 100
    - Negative offset/limit rejected automatically with HTTP 422
    - Stable ordering: always sorted deterministically by primary key (id ASC)
    """
    try:
        return paginate_records(MOCK_DATABASE, offset=offset, limit=limit, max_limit=100)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


"""
===============================================================================
ARCHITECTURAL GUIDANCE: OFFSET VS. CURSOR (KEYSET) PAGINATION
===============================================================================

1. When Offset Pagination is Appropriate:
   - Small to moderate datasets (< 100,000 rows).
   - Administrative dashboards where jumping to an arbitrary page number
     (e.g., "Jump to Page 14") is an explicit business requirement.
   - Datasets with infrequent insertions or updates during reads.

2. When Cursor (Keyset) Pagination is Essential:
   - High-throughput append-only tables (Audit logs, threat feeds, activity streams).
   - Large tables (> 500,000 rows): As OFFSET increases (e.g. OFFSET 200000 LIMIT 20),
     SQL databases must read, parse, and discard 200,000 index tuples before
     returning 20 rows. This causes the famous "OFFSET performance cliff".
   - Rapidly mutating streams: If a new record is inserted at row 1 while a user
     is navigating between pages, an offset-based query will shift rows down,
     causing the client to see duplicate items or skip records ("phantom reads").
   - Keyset queries use: `WHERE id > :last_seen_id ORDER BY id ASC LIMIT 20`
     which utilizes B-Tree indexes for instantaneous O(1) query execution.
===============================================================================
"""


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8004)
