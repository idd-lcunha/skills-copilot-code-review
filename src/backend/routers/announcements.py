"""
Announcement endpoints for the High School Management System API
"""

from datetime import date, datetime
from typing import Any, Dict, List, Optional, Tuple
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from ..database import announcements_collection, teachers_collection

router = APIRouter(
    prefix="/announcements",
    tags=["announcements"]
)


class AnnouncementPayload(BaseModel):
    """Payload for announcement create and update operations."""

    message: str
    expires_at: str
    starts_at: Optional[str] = None


def _parse_iso_date(value: str, field_name: str) -> date:
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid date format for {field_name}. Use YYYY-MM-DD."
        ) from exc


def _validate_teacher(teacher_username: Optional[str]) -> Dict[str, Any]:
    if not teacher_username:
        raise HTTPException(status_code=401, detail="Authentication required")

    teacher = teachers_collection.find_one({"_id": teacher_username})
    if not teacher:
        raise HTTPException(status_code=401, detail="Invalid teacher credentials")

    return teacher


def _validate_payload(payload: AnnouncementPayload) -> Tuple[str, str, Optional[str]]:
    message = payload.message.strip()
    if not message:
        raise HTTPException(status_code=422, detail="Message is required")

    expires_date = _parse_iso_date(payload.expires_at, "expires_at")

    starts_at = payload.starts_at.strip() if payload.starts_at else None
    if starts_at:
        starts_date = _parse_iso_date(starts_at, "starts_at")
        if starts_date > expires_date:
            raise HTTPException(
                status_code=422,
                detail="starts_at cannot be later than expires_at"
            )

    return message, expires_date.isoformat(), starts_at


def _serialize_announcement(doc: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": str(doc.get("_id")),
        "message": doc.get("message", ""),
        "starts_at": doc.get("starts_at"),
        "expires_at": doc.get("expires_at"),
        "created_at": doc.get("created_at")
    }


@router.get("", response_model=List[Dict[str, Any]])
def get_active_announcements() -> List[Dict[str, Any]]:
    """Get active announcements visible to all users.

    Active means:
    - expires_at is today or later
    - starts_at is not set OR starts_at is today or earlier
    """
    today = date.today().isoformat()

    query = {
        "expires_at": {"$gte": today},
        "$or": [
            {"starts_at": {"$exists": False}},
            {"starts_at": None},
            {"starts_at": ""},
            {"starts_at": {"$lte": today}}
        ]
    }

    docs = announcements_collection.find(query).sort([
        ("expires_at", 1),
        ("created_at", -1)
    ])

    return [_serialize_announcement(doc) for doc in docs]


@router.get("/manage", response_model=List[Dict[str, Any]])
def get_all_announcements(teacher_username: Optional[str] = Query(None)) -> List[Dict[str, Any]]:
    """Get all announcements for management UI (authentication required)."""
    _validate_teacher(teacher_username)

    docs = announcements_collection.find({}).sort([
        ("expires_at", 1),
        ("created_at", -1)
    ])

    return [_serialize_announcement(doc) for doc in docs]


@router.post("", response_model=Dict[str, Any])
def create_announcement(
    payload: AnnouncementPayload,
    teacher_username: Optional[str] = Query(None)
) -> Dict[str, Any]:
    """Create a new announcement (authentication required)."""
    _validate_teacher(teacher_username)
    message, expires_at, starts_at = _validate_payload(payload)

    doc = {
        "_id": uuid4().hex,
        "message": message,
        "expires_at": expires_at,
        "starts_at": starts_at,
        "created_at": datetime.utcnow().replace(microsecond=0).isoformat()
    }

    announcements_collection.insert_one(doc)
    return _serialize_announcement(doc)


@router.put("/{announcement_id}", response_model=Dict[str, Any])
def update_announcement(
    announcement_id: str,
    payload: AnnouncementPayload,
    teacher_username: Optional[str] = Query(None)
) -> Dict[str, Any]:
    """Update an existing announcement (authentication required)."""
    _validate_teacher(teacher_username)
    message, expires_at, starts_at = _validate_payload(payload)

    result = announcements_collection.update_one(
        {"_id": announcement_id},
        {
            "$set": {
                "message": message,
                "expires_at": expires_at,
                "starts_at": starts_at
            }
        }
    )

    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Announcement not found")

    updated = announcements_collection.find_one({"_id": announcement_id})
    if not updated:
        raise HTTPException(status_code=404, detail="Announcement not found")

    return _serialize_announcement(updated)


@router.delete("/{announcement_id}", response_model=Dict[str, str])
def delete_announcement(
    announcement_id: str,
    teacher_username: Optional[str] = Query(None)
) -> Dict[str, str]:
    """Delete an announcement (authentication required)."""
    _validate_teacher(teacher_username)

    result = announcements_collection.delete_one({"_id": announcement_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Announcement not found")

    return {"message": "Announcement deleted successfully"}
