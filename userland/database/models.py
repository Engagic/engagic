"""
Userland Database Models

Simplified from motioncount - free tier only, no billing.
"""

from datetime import datetime
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, field


@dataclass
class User:
    """User profile (simplified from Customer)"""
    id: str
    name: str
    email: str
    created_at: datetime = field(default_factory=datetime.now)
    last_login: Optional[datetime] = None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "email": self.email,
            "created_at": self.created_at.isoformat(),
            "last_login": self.last_login.isoformat() if self.last_login else None
        }


@dataclass
class Alert:
    """Alert configuration (simplified from motioncount)"""
    id: str
    user_id: str
    name: str
    cities: List[str]  # city bananas
    criteria: Dict[str, Any]  # {"keywords": ["housing", "zoning"]}
    frequency: str = "weekly"  # weekly, daily
    active: bool = True
    created_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "name": self.name,
            "cities": self.cities,
            "criteria": self.criteria,
            "frequency": self.frequency,
            "active": self.active,
            "created_at": self.created_at.isoformat()
        }


@dataclass
class AlertMatch:
    """Result of matching an item to an alert"""
    id: str
    alert_id: str
    meeting_id: str
    item_id: Optional[str] = None  # None if meeting-level match
    match_type: str = "keyword"  # keyword, matter
    confidence: float = 0.0
    matched_criteria: Dict[str, Any] = field(default_factory=dict)
    notified: bool = False
    created_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "alert_id": self.alert_id,
            "meeting_id": self.meeting_id,
            "item_id": self.item_id,
            "match_type": self.match_type,
            "confidence": self.confidence,
            "matched_criteria": self.matched_criteria,
            "notified": self.notified,
            "created_at": self.created_at.isoformat()
        }
