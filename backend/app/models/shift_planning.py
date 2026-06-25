"""Schichtplanung (shift planning) models — Issue #305.

Pure planning artefact: these tables describe *who stands where, when* across a
weekly template. They are intentionally **decoupled** from the time-tracking /
ArbZG calculation model — no Soll/Ist hours, no break or rest-time validation,
no vacation/overtime side effects.

Five tenant-scoped tables (RLS ``tenant_isolation`` policy, see migration 053):

* ``locations``         — Standorte (CRUD entity).
* ``workstations``      — Arbeitsplätze, optionally tied to a location.
* ``shift_plans``       — named weekly templates ("Normalzustand", …); multiple
  may be ``is_active`` at once (Default off, gated behind the feature flag).
* ``shift_slots``       — workstation × weekday × time window with optional
  minimum staffing.
* ``shift_assignments`` — employees assigned to a slot (≥1 per slot).

The feature itself is gated by the tenant setting ``shift_planning_enabled``
(Default False) and is only reachable for admins to toggle.
"""
from sqlalchemy import (
    Column,
    String,
    Text,
    Integer,
    SmallInteger,
    Time,
    Boolean,
    DateTime,
    ForeignKey,
    UniqueConstraint,
    Index,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import uuid

from app.database import Base


class Location(Base):
    """Standort — an optional grouping for workstations (e.g. Hauptstelle, Filiale)."""

    __tablename__ = "locations"
    __table_args__ = (
        UniqueConstraint("tenant_id", "name", name="uq_tenant_location_name"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True)
    name = Column(String(255), nullable=False)
    sort_order = Column(Integer, nullable=False, default=0, server_default="0")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    workstations = relationship("Workstation", back_populates="location")

    def __repr__(self):
        return f"<Location(name={self.name})>"


class Workstation(Base):
    """Arbeitsplatz — a place to be staffed (Tresen, Labor, Springer, …).

    ``location_id`` is nullable → a workstation without a location is "global".
    The colour is used by the weekly grid in the frontend.
    """

    __tablename__ = "workstations"
    __table_args__ = (
        UniqueConstraint("tenant_id", "name", name="uq_tenant_workstation_name"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True)
    location_id = Column(
        UUID(as_uuid=True),
        ForeignKey("locations.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    name = Column(String(255), nullable=False)
    color = Column(String(7), nullable=True)  # Hex #RRGGBB for the grid block
    sort_order = Column(Integer, nullable=False, default=0, server_default="0")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    location = relationship("Location", back_populates="workstations")

    def __repr__(self):
        return f"<Workstation(name={self.name})>"


class ShiftPlan(Base):
    """Schicht-Wochenplan — a named weekly template.

    ``is_active`` is a plain flag; **multiple plans may be active at once**
    (e.g. one per location). The dashboard resolves a user's "today" view as the
    union of their assignments across all active plans.
    """

    __tablename__ = "shift_plans"
    __table_args__ = (
        UniqueConstraint("tenant_id", "name", name="uq_tenant_shift_plan_name"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    is_active = Column(Boolean, nullable=False, default=False, server_default="false")
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    # ORM-side cascade (no passive_deletes): deleting a plan deletes its slots
    # even on SQLite test DBs that run with FK enforcement off. The DB-level
    # ON DELETE CASCADE (migration 053) remains as belt-and-suspenders.
    slots = relationship(
        "ShiftSlot",
        back_populates="plan",
        cascade="all, delete-orphan",
    )

    def __repr__(self):
        return f"<ShiftPlan(name={self.name}, active={self.is_active})>"


class ShiftSlot(Base):
    """Zeitslot — one workstation staffed for a weekday/time window in a plan.

    ``weekday`` follows ``date.weekday()`` (0=Monday … 6=Sunday). ``min_staff``
    drives the soft under-staffing warning (0 = no minimum).
    """

    __tablename__ = "shift_slots"
    __table_args__ = (
        Index("ix_shift_slots_plan_weekday", "tenant_id", "shift_plan_id", "weekday"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True)
    shift_plan_id = Column(
        UUID(as_uuid=True),
        ForeignKey("shift_plans.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    workstation_id = Column(
        UUID(as_uuid=True),
        ForeignKey("workstations.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    weekday = Column(SmallInteger, nullable=False)  # 0=Mon … 6=Sun
    start_time = Column(Time, nullable=False)
    end_time = Column(Time, nullable=False)
    min_staff = Column(SmallInteger, nullable=False, default=0, server_default="0")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    plan = relationship("ShiftPlan", back_populates="slots")
    workstation = relationship("Workstation")
    assignments = relationship(
        "ShiftAssignment",
        back_populates="slot",
        cascade="all, delete-orphan",
    )

    def __repr__(self):
        return f"<ShiftSlot(weekday={self.weekday}, {self.start_time}–{self.end_time})>"


class ShiftAssignment(Base):
    """Zuweisung — an employee staffed into a slot. ≥1 employee per slot."""

    __tablename__ = "shift_assignments"
    __table_args__ = (
        UniqueConstraint("tenant_id", "shift_slot_id", "user_id", name="uq_tenant_slot_user"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True)
    shift_slot_id = Column(
        UUID(as_uuid=True),
        ForeignKey("shift_slots.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    slot = relationship("ShiftSlot", back_populates="assignments")
    user = relationship("User")

    def __repr__(self):
        return f"<ShiftAssignment(slot={self.shift_slot_id}, user={self.user_id})>"
