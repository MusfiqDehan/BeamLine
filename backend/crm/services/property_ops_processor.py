from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
import logging
from typing import Any
import uuid
from django.conf import settings
from django.core.mail import EmailMessage
from django.utils import timezone
from common.email_backend import AuditedEmailBackend
from common.middleware import get_current_tenant
from common.tenancy import Organization
from crm.models import (
    ChecklistTemplate,
    ConstructionProject,
    Contact,
    EmailCommunicationLog,
    GuestServiceUpsell,
    MaterialOrder,
    ProjectCost,
    PropertyProfile,
    PropertyWorkOrder,
    ReservationTurn,
)
from integrations.models import PaymentTransaction

logger = logging.getLogger(__name__)


DEFAULT_TURNOVER_CHECKLIST_ITEMS: list[dict[str, Any]] = [
    {
        "id": "step-1",
        "room_area": "Entry & Smart Access",
        "instruction": "Verify smart lock battery >= 50%, test guest PIN code, and ensure entryway lighting & welcome tablet are active.",
        "requires_photo": True,
        "is_critical": True,
    },
    {
        "id": "step-2",
        "room_area": "Kitchen & Dining",
        "instruction": "Sanitize stone countertops, inspect inside refrigerator/oven, restock Nespresso pods & artisan welcome basket.",
        "requires_photo": True,
        "is_critical": True,
    },
    {
        "id": "step-3",
        "room_area": "Primary Suite & Linens",
        "instruction": "Hospitality triple-sheet bed staging, fluff pillows, check closets for forgotten guest items, and verify fresh bath robes.",
        "requires_photo": True,
        "is_critical": True,
    },
    {
        "id": "step-4",
        "room_area": "Bathrooms & Amenities",
        "instruction": "Disinfect glass enclosures, polish brass fixtures, replenish luxury toiletries, and fold spa towels to brand standard.",
        "requires_photo": False,
        "is_critical": True,
    },
    {
        "id": "step-5",
        "room_area": "Patio, Pool & HVAC",
        "instruction": "Set smart thermostat to 71F welcome eco-mode, inspect patio lounge cushions, and check pool/spa cover safety latch.",
        "requires_photo": True,
        "is_critical": False,
    },
]

DEFAULT_INSPECTION_CHECKLIST_ITEMS: list[dict[str, Any]] = [
    {
        "id": "insp-1",
        "room_area": "Life Safety & Security",
        "instruction": "Confirm smoke/CO detectors green status, fire extinguisher pressure gauge, and smart-lock deadbolt alignment.",
        "requires_photo": True,
        "is_critical": True,
    },
    {
        "id": "insp-2",
        "room_area": "Staging & Hospitality Standard",
        "instruction": "Verify 5-star bed symmetry, zero streaks on mirrors/glass, Wi-Fi speed check, and printed house guide placement.",
        "requires_photo": True,
        "is_critical": True,
    },
    {
        "id": "insp-3",
        "room_area": "Mechanical & Curb Appeal",
        "instruction": "Check water pressure, HVAC air filter condition, exterior landscape lighting, and trash bin enclosure.",
        "requires_photo": False,
        "is_critical": False,
    },
]

DEFAULT_WARRANTY_CHECKLIST_ITEMS: list[dict[str, Any]] = [
    {
        "id": "war-1",
        "room_area": "Envelope & Millwork",
        "instruction": "Inspect custom cabinetry alignment, window caulking seals, and hardwood expansion joints post-handoff.",
        "requires_photo": True,
        "is_critical": True,
    },
    {
        "id": "war-2",
        "room_area": "MEP & Smart Home Systems",
        "instruction": "Test radiant floor heating zones, tankless water heater purge valve, and Lutron lighting scenes.",
        "requires_photo": True,
        "is_critical": True,
    },
]


def _instantiate_checklist(items_schema: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Converts template steps into trackable work-order verification checklist items."""
    instantiated: list[dict[str, Any]] = []
    for idx, item in enumerate(items_schema or [], start=1):
        instantiated.append(
            {
                "id": item.get("id") or f"step-{idx}",
                "room_area": item.get("room_area") or "General Property",
                "instruction": item.get("instruction") or "Complete inspection step",
                "requires_photo": bool(item.get("requires_photo", False)),
                "is_critical": bool(item.get("is_critical", True)),
                "completed": bool(item.get("completed", False)),
                "photo_url": item.get("photo_url", ""),
                "flagged_defect": bool(item.get("flagged_defect", False)),
                "defect_notes": item.get("defect_notes", ""),
                "completed_at": item.get("completed_at"),
            }
        )
    return instantiated


class PropertyOperationsEngine:
    """
    Core service coordinating Property Profiles, Same-Day Turnovers, Guided Photo Checklists,
    Auto-Escalation to Maintenance/ProjectCost, and Guest Experience Service Revenue Upsells.
    """

    @staticmethod
    def resolve_org(organization: Organization | None = None) -> Organization | None:
        return organization or get_current_tenant() or Organization.objects.filter(slug="kevin").first()

    @classmethod
    def _send_ops_notification(
        cls,
        organization: Organization | None,
        subject: str,
        body: str,
        recipient: str = "",
        related_cost: ProjectCost | None = None,
    ) -> EmailCommunicationLog:
        """Logs and dispatches property operations alerts through AuditedEmailBackend."""
        org = cls.resolve_org(organization)
        to_addr = (
            recipient
            or (org.executive_recipient_email if org and org.executive_recipient_email else "")
            or getattr(settings, "NOTIFICATION_RECIPIENT_EMAIL", "")
            or "ops-automation@crm.musfiqdehan.com"
        )
        from_addr = getattr(
            settings, "DEFAULT_FROM_EMAIL", "BeamLine Property Ops <ops-automation@crm.musfiqdehan.com>"
        )

        # In automated test / offline environments avoid blocking SMTP socket calls;
        # create audit log cleanly if SMTP is not explicitly configured.
        headers = {"X-Direction": "Property Ops Alert"}
        if related_cost:
            headers["X-Related-Cost-Id"] = str(related_cost.id)

        try:
            from integrations.services.resolver import IntegrationResolver

            smtp_state = IntegrationResolver.get_smtp_state(organization=org)
            has_smtp = bool(
                smtp_state.get("host") and smtp_state.get("username") and smtp_state.get("password")
            )
        except Exception:
            has_smtp = False

        if has_smtp:
            msg = EmailMessage(
                subject=subject[:255],
                body=body,
                from_email=from_addr,
                to=[to_addr],
                headers=headers,
            )
            AuditedEmailBackend().send_messages([msg])
            return EmailCommunicationLog.all_objects.filter(subject=subject[:255]).first()

        return EmailCommunicationLog.all_objects.create(
            organization=org,
            subject=subject[:255],
            sender=from_addr[:255],
            recipient=to_addr[:255],
            direction="Property Ops Alert",
            status="Logged (Property Ops)",
            body_preview=body[:2000],
            related_cost=related_cost,
        )

    @classmethod
    def ensure_default_templates_and_seed(cls, organization: Organization | None = None) -> None:
        """
        Idempotently provisions default guided ChecklistTemplates and rich initial
        Property Operations demo data for an organization if it has no properties yet.
        """
        org = cls.resolve_org(organization)
        if not org:
            return

        # 1. Ensure standard checklist templates exist
        if not ChecklistTemplate.all_objects.filter(organization=org).exists():
            ChecklistTemplate.all_objects.create(
                organization=org,
                name="Luxury STR Turnover Clean & Stage",
                category=ChecklistTemplate.WorkCategory.TURNOVER_CLEAN,
                description="Full hospitality turnover checklist with mandatory kitchen, primary suite, and smart-lock photo verification.",
                estimated_duration_minutes=150,
                requires_supervisor_signoff=True,
                items_schema=DEFAULT_TURNOVER_CHECKLIST_ITEMS,
            )
            ChecklistTemplate.all_objects.create(
                organization=org,
                name="50-Point Pre-Arrival Hospitality Inspection",
                category=ChecklistTemplate.WorkCategory.PRE_ARRIVAL_INSPECTION,
                description="Supervisor quality & safety walkthrough executed 2 hours prior to VIP guest arrival.",
                estimated_duration_minutes=45,
                requires_supervisor_signoff=True,
                items_schema=DEFAULT_INSPECTION_CHECKLIST_ITEMS,
            )
            ChecklistTemplate.all_objects.create(
                organization=org,
                name="Estate Preventative & Warranty Care",
                category=ChecklistTemplate.WorkCategory.WARRANTY_WALKTHROUGH,
                description="Post-construction warranty & luxury estate preventative care inspection.",
                estimated_duration_minutes=90,
                requires_supervisor_signoff=True,
                items_schema=DEFAULT_WARRANTY_CHECKLIST_ITEMS,
            )

        if PropertyProfile.all_objects.filter(organization=org).exists():
            return

        # Only seed rich demo properties for the flagship 'kevin' workspace or if projects exist
        if org.slug != "kevin":
            return

        turnover_tpl = ChecklistTemplate.all_objects.filter(
            organization=org, category=ChecklistTemplate.WorkCategory.TURNOVER_CLEAN
        ).first()
        inspection_tpl = ChecklistTemplate.all_objects.filter(
            organization=org, category=ChecklistTemplate.WorkCategory.PRE_ARRIVAL_INSPECTION
        ).first()
        warranty_tpl = ChecklistTemplate.all_objects.filter(
            organization=org, category=ChecklistTemplate.WorkCategory.WARRANTY_WALKTHROUGH
        ).first()

        owner_contact = Contact.all_objects.filter(organization=org).first()
        closeout_project = (
            ConstructionProject.all_objects.filter(organization=org)
            .order_by("-created_at")
            .first()
        )

        now = timezone.now()

        prop_1 = PropertyProfile.all_objects.create(
            organization=org,
            code="PROP-101",
            name="Oakridge Cliffside Villa",
            property_type=PropertyProfile.PropertyType.LUXURY_ESTATE,
            readiness_status=PropertyProfile.ReadinessStatus.DIRTY_TURN_NEEDED,
            address="742 Oakridge Crest Way, Malibu, CA 90265",
            bedrooms=5,
            bathrooms=Decimal("5.5"),
            max_guests=10,
            nightly_rate=Decimal("1450.00"),
            management_fee_percent=Decimal("22.00"),
            smart_lock_code="7842#",
            wifi_network="Oakridge_VIP_5G",
            access_instructions="Gate code #4410. August Smart Lock auto-rotates 2 hours prior to arrival.",
            owner_contact=owner_contact,
            source_project=closeout_project,
            default_cleaner="Elena Rostova (Lead Hospitality Tech)",
            default_inspector="Marcus Vance (Quality Inspector)",
            supplies_status="Stocked at Par",
            latest_operational_note="Same-day turnover scheduled: VIP arrival at 4:00 PM.",
        )

        prop_2 = PropertyProfile.all_objects.create(
            organization=org,
            code="PROP-102",
            name="Harborview Penthouse Suite",
            property_type=PropertyProfile.PropertyType.SHORT_TERM_RENTAL,
            readiness_status=PropertyProfile.ReadinessStatus.VERIFIED_READY,
            address="180 Marina Promenade, Penthouse B, Newport Beach, CA",
            bedrooms=3,
            bathrooms=Decimal("3.0"),
            max_guests=6,
            nightly_rate=Decimal("780.00"),
            management_fee_percent=Decimal("20.00"),
            smart_lock_code="9104#",
            wifi_network="HarborPenthouse",
            access_instructions="Concierge key fob in lockbox #2B; elevator code 8891.",
            owner_contact=owner_contact,
            default_cleaner="Sofia Chen (Hospitality Lead)",
            default_inspector="Marcus Vance (Quality Inspector)",
            supplies_status="Stocked at Par",
            last_verified_at=now - timedelta(hours=3),
            latest_operational_note="Verified 100% photo QA compliance for tonight's check-in.",
        )

        prop_3 = PropertyProfile.all_objects.create(
            organization=org,
            code="PROP-103",
            name="Crestwood Alpine Chalet",
            property_type=PropertyProfile.PropertyType.WARRANTY_RESIDENCE,
            readiness_status=PropertyProfile.ReadinessStatus.PENDING_INSPECTION,
            address="95 Timberline Ridge Rd, Aspen, CO 81611",
            bedrooms=4,
            bathrooms=Decimal("4.5"),
            max_guests=8,
            nightly_rate=Decimal("1120.00"),
            management_fee_percent=Decimal("18.00"),
            smart_lock_code="3318#",
            wifi_network="Crestwood_Chalet",
            access_instructions="Heated driveway sensor active; smart lock synced with PMS.",
            owner_contact=owner_contact,
            default_cleaner="Elena Rostova (Lead Hospitality Tech)",
            default_inspector="Kevin Founder (Executive QA)",
            supplies_status="Low Linens Alert",
            latest_operational_note="Post-build warranty inspection & hot tub chemistry calibration queued.",
        )

        res_1 = ReservationTurn.all_objects.create(
            organization=org,
            property_profile=prop_1,
            confirmation_code="ABNB-94821",
            guest_name="Sophia & Daniel Laurent",
            guest_email="laurent.family@example.com",
            guest_phone="+1-310-555-0148",
            guests_count=6,
            channel=ReservationTurn.Channel.AIRBNB,
            stay_status=ReservationTurn.StayStatus.UPCOMING,
            check_in_at=now + timedelta(hours=4),
            check_out_at=now + timedelta(days=4),
            next_guest_check_in_at=now + timedelta(days=4, hours=5),
            is_same_day_turn=True,
            reservation_total=Decimal("5800.00"),
            special_requests="Requested heated infinity pool (84F) and early check-in at 2:00 PM if verified ready.",
        )

        res_2 = ReservationTurn.all_objects.create(
            organization=org,
            property_profile=prop_2,
            confirmation_code="VIP-77310",
            guest_name="Dr. Julian Mercer",
            guest_email="j.mercer@example.com",
            guest_phone="+1-949-555-0192",
            guests_count=2,
            channel=ReservationTurn.Channel.DIRECT_VIP,
            stay_status=ReservationTurn.StayStatus.UPCOMING,
            check_in_at=now + timedelta(days=1),
            check_out_at=now + timedelta(days=5),
            is_same_day_turn=False,
            reservation_total=Decimal("3120.00"),
            special_requests="Stock kitchen with sparkling water and organic espresso beans.",
        )

        # Seed work orders
        wo_1_items = _instantiate_checklist(turnover_tpl.items_schema if turnover_tpl else DEFAULT_TURNOVER_CHECKLIST_ITEMS)
        wo_1_items[0]["completed"] = True
        wo_1_items[0]["photo_url"] = "https://cdn.musfiqdehan.com/beamline/demo/smart-lock-verified.jpg"
        wo_1 = PropertyWorkOrder.all_objects.create(
            organization=org,
            code="WO-2026-101",
            title="Same-Day Turnover Clean & Staging — Oakridge Cliffside Villa",
            property_profile=prop_1,
            reservation=res_1,
            template=turnover_tpl,
            work_type=PropertyWorkOrder.WorkType.TURNOVER_CLEAN,
            priority=PropertyWorkOrder.Priority.URGENT_SAME_DAY,
            status=PropertyWorkOrder.WorkStatus.IN_PROGRESS,
            assigned_to="Elena Rostova (Lead Hospitality Tech)",
            scheduled_start_at=now - timedelta(minutes=30),
            must_complete_by=now + timedelta(hours=3),
            checklist_items=wo_1_items,
            estimated_cost=Decimal("285.00"),
            billable_to=PropertyWorkOrder.BillableScope.OPERATOR,
            field_notes="Departure clean started on time; laundry cycle 1 complete.",
        )

        wo_2_items = _instantiate_checklist(inspection_tpl.items_schema if inspection_tpl else DEFAULT_INSPECTION_CHECKLIST_ITEMS)
        for item in wo_2_items:
            item["completed"] = True
            item["completed_at"] = (now - timedelta(hours=3)).isoformat()
            if item["requires_photo"]:
                item["photo_url"] = "https://cdn.musfiqdehan.com/beamline/demo/suite-verified.jpg"
        PropertyWorkOrder.all_objects.create(
            organization=org,
            code="WO-2026-102",
            title="50-Point Pre-Arrival Inspection — Harborview Penthouse Suite",
            property_profile=prop_2,
            reservation=res_2,
            template=inspection_tpl,
            work_type=PropertyWorkOrder.WorkType.QUALITY_INSPECTION,
            priority=PropertyWorkOrder.Priority.HIGH,
            status=PropertyWorkOrder.WorkStatus.VERIFIED_COMPLETE,
            assigned_to="Marcus Vance (Quality Inspector)",
            scheduled_start_at=now - timedelta(hours=5),
            must_complete_by=now - timedelta(hours=2),
            completed_at=now - timedelta(hours=3),
            verified_by="Marcus Vance (Quality Inspector)",
            verified_at=now - timedelta(hours=3),
            verification_score=100,
            checklist_items=wo_2_items,
            verification_photos=["https://cdn.musfiqdehan.com/beamline/demo/suite-verified.jpg"],
            estimated_cost=Decimal("95.00"),
            billable_to=PropertyWorkOrder.BillableScope.OPERATOR,
            field_notes="100% pass. Smart lock code 9104# tested & confirmed.",
        )

        wo_3_items = _instantiate_checklist(warranty_tpl.items_schema if warranty_tpl else DEFAULT_WARRANTY_CHECKLIST_ITEMS)
        PropertyWorkOrder.all_objects.create(
            organization=org,
            code="WO-2026-103",
            title="Post-Build Warranty & HVAC Calibration — Crestwood Alpine Chalet",
            property_profile=prop_3,
            template=warranty_tpl,
            work_type=PropertyWorkOrder.WorkType.PREVENTATIVE_MAINTENANCE,
            priority=PropertyWorkOrder.Priority.MEDIUM,
            status=PropertyWorkOrder.WorkStatus.PENDING_VERIFICATION,
            assigned_to="Kevin Founder (Executive QA)",
            scheduled_start_at=now + timedelta(hours=2),
            must_complete_by=now + timedelta(days=1),
            checklist_items=wo_3_items,
            estimated_cost=Decimal("240.00"),
            billable_to=PropertyWorkOrder.BillableScope.WARRANTY,
            field_notes="Awaiting technician HVAC seal photo upload.",
        )

        # Seed guest experience upsells
        GuestServiceUpsell.all_objects.create(
            organization=org,
            property_profile=prop_1,
            reservation=res_1,
            service_name="Early Check-In (+2 Hours) & Heated Infinity Pool",
            category=GuestServiceUpsell.ServiceCategory.ARRIVAL_DEPARTURE,
            guest_name="Sophia & Daniel Laurent",
            price=Decimal("225.00"),
            operator_commission_percent=Decimal("40.00"),
            currency=org.currency or "USD",
            status=GuestServiceUpsell.UpsellStatus.REQUESTED,
            notes="Guest requested 2:00 PM early arrival + 84F pool heating via pre-arrival portal.",
        )

        tx_paid = PaymentTransaction.objects.create(
            organization=org,
            provider_key="stripe",
            scope=PaymentTransaction.Scope.GUEST_UPSELL,
            status=PaymentTransaction.Status.SUCCEEDED,
            amount=Decimal("180.00"),
            currency=org.currency or "USD",
            external_transaction_id=f"ch_upsell_{uuid.uuid4().hex[:10]}",
            customer_email="j.mercer@example.com",
            description="VIP Espresso & Artisan Kitchen Pre-Stock — PROP-102",
            is_sandbox=True,
        )
        GuestServiceUpsell.all_objects.create(
            organization=org,
            property_profile=prop_2,
            reservation=res_2,
            service_name="VIP Artisan Kitchen & Espresso Pre-Stock",
            category=GuestServiceUpsell.ServiceCategory.CONCIERGE,
            guest_name="Dr. Julian Mercer",
            price=Decimal("180.00"),
            operator_commission_percent=Decimal("35.00"),
            currency=org.currency or "USD",
            status=GuestServiceUpsell.UpsellStatus.PAID_SCHEDULED,
            payment_transaction=tx_paid,
            fulfillment_work_order=wo_1,
            notes="Paid via Stripe checkout; concierge stock items staged.",
        )

    @classmethod
    def promote_project_to_property(
        cls,
        project: ConstructionProject,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        One-click Construction Closeout -> Managed Property Operations handoff.
        Creates a PropertyProfile linked to the ConstructionProject and schedules
        the initial post-build warranty & hospitality readiness work order.
        """
        payload = payload or {}
        org = cls.resolve_org(project.organization)
        cls.ensure_default_templates_and_seed(org)

        # Generate unique property code per organization
        base_code = f"PROP-{project.code}".upper()[:28]
        code = base_code
        counter = 1
        while PropertyProfile.all_objects.filter(organization=org, code=code).exists():
            counter += 1
            code = f"{base_code[:24]}-{counter}"

        owner_contact = None
        first_opp = project.opportunities.select_related("contact").first()
        if first_opp and first_opp.contact:
            owner_contact = first_opp.contact

        prop_type = payload.get("property_type") or PropertyProfile.PropertyType.WARRANTY_RESIDENCE
        prop_name = (payload.get("name") or "").strip() or f"{project.name} (Managed Residence)"

        prop = PropertyProfile.all_objects.create(
            organization=org,
            code=code,
            name=prop_name,
            property_type=prop_type,
            readiness_status=PropertyProfile.ReadinessStatus.PENDING_INSPECTION,
            address=payload.get("address") or project.site_address or "Custom Residence Site",
            bedrooms=int(payload.get("bedrooms") or 4),
            bathrooms=Decimal(str(payload.get("bathrooms") or "3.5")),
            max_guests=int(payload.get("max_guests") or 8),
            nightly_rate=Decimal(str(payload.get("nightly_rate") or "850.00")),
            management_fee_percent=Decimal(str(payload.get("management_fee_percent") or "20.00")),
            smart_lock_code=payload.get("smart_lock_code") or "5290#",
            owner_contact=owner_contact,
            source_project=project,
            default_inspector=project.project_manager or "Marcus Vance (Quality Inspector)",
            latest_operational_note=f"Promoted from Construction Project {project.code} ({project.phase}).",
        )

        tpl = (
            ChecklistTemplate.all_objects.filter(
                organization=org,
                category=ChecklistTemplate.WorkCategory.WARRANTY_WALKTHROUGH,
            ).first()
            or ChecklistTemplate.all_objects.filter(organization=org).first()
        )
        checklist = _instantiate_checklist(
            tpl.items_schema if tpl else DEFAULT_WARRANTY_CHECKLIST_ITEMS
        )
        now = timezone.now()
        wo = PropertyWorkOrder.all_objects.create(
            organization=org,
            code=f"WO-{uuid.uuid4().hex[:6].upper()}",
            title=f"Post-Build Handoff & Readiness Walkthrough — {prop.name}",
            property_profile=prop,
            template=tpl,
            work_type=PropertyWorkOrder.WorkType.QUALITY_INSPECTION,
            priority=PropertyWorkOrder.Priority.HIGH,
            status=PropertyWorkOrder.WorkStatus.DISPATCHED,
            assigned_to=prop.default_inspector,
            scheduled_start_at=now + timedelta(hours=2),
            must_complete_by=now + timedelta(days=2),
            checklist_items=checklist,
            estimated_cost=Decimal("250.00"),
            billable_to=PropertyWorkOrder.BillableScope.WARRANTY,
            field_notes=f"Auto-scheduled during closeout handoff from {project.code}.",
        )

        cls._send_ops_notification(
            organization=org,
            subject=f"[PROPERTY HANDOFF] {prop.code} Promoted from {project.code}",
            body=(
                f"Construction Project {project.code} ({project.name}) has been promoted into Property Operations.\n"
                f"Managed Property: {prop.code} - {prop.name}\n"
                f"Initial Readiness Work Order: {wo.code} assigned to {wo.assigned_to}.\n"
            ),
            recipient=owner_contact.email if owner_contact and owner_contact.email else "",
        )

        return {"property": prop, "initial_work_order": wo}

    @classmethod
    def schedule_turnover_for_reservation(
        cls,
        reservation: ReservationTurn,
        auto_notify: bool = True,
    ) -> PropertyWorkOrder:
        """
        Automatically creates a guided Turnover Clean work order for a reservation
        and detects back-to-back same-day turnaround SLAs.
        """
        prop = reservation.property_profile
        org = cls.resolve_org(reservation.organization or prop.organization)
        cls.ensure_default_templates_and_seed(org)

        tpl = (
            ChecklistTemplate.all_objects.filter(
                organization=org, category=ChecklistTemplate.WorkCategory.TURNOVER_CLEAN
            ).first()
            or ChecklistTemplate.all_objects.filter(organization=org).first()
        )
        checklist = _instantiate_checklist(
            tpl.items_schema if tpl else DEFAULT_TURNOVER_CHECKLIST_ITEMS
        )

        priority = (
            PropertyWorkOrder.Priority.URGENT_SAME_DAY
            if reservation.is_same_day_turn
            else PropertyWorkOrder.Priority.HIGH
        )
        start_at = reservation.check_out_at
        due_at = (
            reservation.next_guest_check_in_at
            or (reservation.check_out_at + timedelta(hours=4))
        )

        wo = PropertyWorkOrder.all_objects.create(
            organization=org,
            code=f"WO-{uuid.uuid4().hex[:6].upper()}",
            title=f"{'Urgent Same-Day ' if reservation.is_same_day_turn else ''}Turnover Clean — {prop.name} ({reservation.confirmation_code})",
            property_profile=prop,
            reservation=reservation,
            template=tpl,
            work_type=PropertyWorkOrder.WorkType.TURNOVER_CLEAN,
            priority=priority,
            status=PropertyWorkOrder.WorkStatus.DISPATCHED,
            assigned_to=prop.default_cleaner,
            scheduled_start_at=start_at,
            must_complete_by=due_at,
            checklist_items=checklist,
            estimated_cost=Decimal("260.00") if reservation.is_same_day_turn else Decimal("195.00"),
            billable_to=PropertyWorkOrder.BillableScope.OPERATOR,
            field_notes=(
                f"Auto-dispatched from {reservation.channel} stay ({reservation.guest_name}). "
                f"Special requests: {reservation.special_requests or 'Standard hospitality setup'}."
            ),
        )

        if prop.readiness_status == PropertyProfile.ReadinessStatus.VERIFIED_READY:
            prop.readiness_status = PropertyProfile.ReadinessStatus.DIRTY_TURN_NEEDED
            prop.latest_operational_note = f"Turnover {wo.code} dispatched for {reservation.guest_name}."
            prop.save()

        if auto_notify:
            cls._send_ops_notification(
                organization=org,
                subject=f"[{'URGENT TURN' if reservation.is_same_day_turn else 'TURNOVER SCHEDULED'}] {prop.code} - {wo.code}",
                body=(
                    f"Property: {prop.code} ({prop.name})\n"
                    f"Reservation: {reservation.confirmation_code} ({reservation.channel})\n"
                    f"Assigned To: {wo.assigned_to}\n"
                    f"SLA Must Complete By: {due_at.isoformat()}\n"
                    f"Checklist Steps: {len(checklist)} guided items with photo verification.\n"
                ),
            )
        return wo

    @classmethod
    def verify_work_order(
        cls,
        work_order: PropertyWorkOrder,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Executes proof-of-work verification on a PropertyWorkOrder:
        - Persists checklist items & R2 verification photo URLs
        - Enforces required critical steps & photo verification gate (unless force_override=True)
        - Auto-escalates flagged defects to a Damage Repair work order, Maintenance Hold, and ProjectCost
        - Flips clean properties to Verified Ready
        - Optionally triggers a MaterialOrder if low supplies are reported
        """
        payload = payload or {}
        org = cls.resolve_org(work_order.organization)
        prop = work_order.property_profile

        submitted_items = payload.get("checklist_items")
        if isinstance(submitted_items, list) and submitted_items:
            items = _instantiate_checklist(submitted_items)
        else:
            items = _instantiate_checklist(work_order.checklist_items or [])

        photos = list(work_order.verification_photos or [])
        for p in payload.get("verification_photos") or []:
            if isinstance(p, str) and p.strip() and p.strip() not in photos:
                photos.append(p.strip())
        for item in items:
            if item.get("photo_url") and item["photo_url"] not in photos:
                photos.append(item["photo_url"])

        # Detect any flagged defects across items or top-level flag
        flagged_items = [it for it in items if it.get("flagged_defect")]
        has_defect = bool(flagged_items) or bool(payload.get("flagged_defect"))
        force_override = bool(payload.get("force_override", False))

        # Proof-of-work verification gate when attempting clean sign-off
        if not has_defect and not force_override:
            missing_critical = [
                it["room_area"]
                for it in items
                if it.get("is_critical", True) and not it.get("completed", False)
            ]
            if missing_critical:
                raise ValueError(
                    f"Cannot verify completion: critical checklist items incomplete in {', '.join(missing_critical)}."
                )
            missing_photos = [
                it["room_area"]
                for it in items
                if it.get("requires_photo", False)
                and not it.get("photo_url")
                and not photos
            ]
            if missing_photos:
                raise ValueError(
                    f"Photo proof-of-work is required before verification for: {', '.join(missing_photos)}."
                )

        total_count = len(items)
        completed_count = sum(1 for it in items if it.get("completed"))
        score = int(round((completed_count / total_count) * 100)) if total_count else 100

        now = timezone.now()
        verifier = (payload.get("verified_by") or prop.default_inspector or "Quality Supervisor").strip()
        field_notes = (payload.get("field_notes") or work_order.field_notes or "").strip()

        work_order.checklist_items = items
        work_order.verification_photos = photos
        work_order.verification_score = score
        work_order.field_notes = field_notes
        work_order.completed_at = work_order.completed_at or now
        work_order.verified_by = verifier
        work_order.verified_at = now

        escalated_work_order: PropertyWorkOrder | None = None
        created_cost: ProjectCost | None = None
        created_material_order: MaterialOrder | None = None

        if has_defect:
            defect_summary = payload.get("defect_summary") or "; ".join(
                f"{it['room_area']}: {it.get('defect_notes') or it['instruction']}"
                for it in flagged_items
            ) or "Property defect flagged during verification inspection."

            work_order.status = PropertyWorkOrder.WorkStatus.FLAGGED_ISSUE
            work_order.save()

            prop.readiness_status = PropertyProfile.ReadinessStatus.MAINTENANCE_HOLD
            prop.latest_operational_note = f"MAINTENANCE HOLD: {defect_summary[:240]}"
            prop.save()

            repair_cost_amount = Decimal(str(payload.get("estimated_repair_cost") or "325.00"))
            repair_vendor = (payload.get("repair_vendor") or "Apex Rapid Property Maintenance").strip()
            billable_scope = (
                payload.get("billable_to")
                or PropertyWorkOrder.BillableScope.PROPERTY_OWNER
            )

            created_cost = ProjectCost.all_objects.create(
                organization=org,
                title=f"Property Repair ({prop.code}) — {defect_summary[:120]}",
                supplier=repair_vendor,
                document_reference=f"DEFECT-{work_order.code}-{uuid.uuid4().hex[:4].upper()}",
                project=prop.source_project,
                invoice_date=now.date(),
                event_timestamp=now,
                amount=repair_cost_amount,
                currency=org.currency if org else "USD",
                payment_status=ProjectCost.PaymentStatus.UNPAID,
                payment_due_date=now.date() + timedelta(days=7),
                needs_clarification=True,
                clarification_notes=(
                    f"Auto-escalated from Property Work Order {work_order.code} ({prop.name}). "
                    f"Billing attribution: {billable_scope}. Issue: {defect_summary}"
                ),
            )

            escalated_work_order = PropertyWorkOrder.all_objects.create(
                organization=org,
                code=f"WO-RPR-{uuid.uuid4().hex[:5].upper()}",
                title=f"Defect Repair: {prop.name} — {defect_summary[:80]}",
                property_profile=prop,
                reservation=work_order.reservation,
                work_type=PropertyWorkOrder.WorkType.DAMAGE_REPAIR,
                priority=PropertyWorkOrder.Priority.URGENT_SAME_DAY,
                status=PropertyWorkOrder.WorkStatus.DISPATCHED,
                assigned_to=repair_vendor,
                scheduled_start_at=now,
                must_complete_by=now + timedelta(hours=3),
                checklist_items=_instantiate_checklist(
                    [
                        {
                            "id": "rpr-1",
                            "room_area": flagged_items[0]["room_area"] if flagged_items else "Affected Area",
                            "instruction": f"Resolve flagged defect: {defect_summary}",
                            "requires_photo": True,
                            "is_critical": True,
                        }
                    ]
                ),
                verification_photos=photos,
                estimated_cost=repair_cost_amount,
                billable_to=billable_scope,
                linked_cost=created_cost,
                field_notes=f"Escalated automatically from {work_order.code}.",
            )

            cls._send_ops_notification(
                organization=org,
                subject=f"[MAINTENANCE HOLD] Defect Flagged at {prop.code} ({work_order.code})",
                body=(
                    f"Property {prop.code} ({prop.name}) placed on MAINTENANCE HOLD.\n"
                    f"Flagged Issue: {defect_summary}\n"
                    f"Auto-Created Repair Work Order: {escalated_work_order.code}\n"
                    f"Linked Cost Record: {created_cost.document_reference} (${created_cost.amount})\n"
                ),
                related_cost=created_cost,
            )
        else:
            work_order.status = PropertyWorkOrder.WorkStatus.VERIFIED_COMPLETE
            work_order.save()

            prop.readiness_status = PropertyProfile.ReadinessStatus.VERIFIED_READY
            prop.last_verified_at = now
            prop.latest_operational_note = f"Verified Ready ({score}% QA) by {verifier}."
            prop.save()

        # Optional automated restock trigger via existing MaterialOrder procurement
        if payload.get("supplies_low"):
            prop.supplies_status = "Restock Ordered"
            prop.save()
            target_project = prop.source_project or ConstructionProject.all_objects.filter(organization=org).first()
            if target_project:
                created_material_order = MaterialOrder.all_objects.create(
                    organization=org,
                    item_name=f"Hospitality Linen & Amenity Restock Pack ({prop.code})",
                    project=target_project,
                    supplier="Standard Hospitality Supply Co.",
                    order_reference=f"SUP-{prop.code}-{uuid.uuid4().hex[:4].upper()}",
                    status=MaterialOrder.OrderStatus.ORDERED,
                    quantity_description="2x Luxury Bath/Bed Kits & Welcome Basket",
                    unit_cost_total=Decimal("145.00"),
                    order_date=now.date(),
                    expected_delivery_date=now.date() + timedelta(days=2),
                    delivery_notes=f"Auto-triggered during {work_order.code} inspection.",
                )
                work_order.linked_material_order = created_material_order
                work_order.save()

        return {
            "work_order": work_order,
            "property": prop,
            "escalated_work_order": escalated_work_order,
            "created_cost": created_cost,
            "created_material_order": created_material_order,
            "has_defect": has_defect,
        }

    @classmethod
    def fulfill_guest_upsell(
        cls,
        upsell: GuestServiceUpsell,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Monetizes a GuestServiceUpsell by recording a PaymentTransaction (GUEST_UPSELL),
        spawning a concierge PropertyWorkOrder, and sending guest & field notifications.
        """
        payload = payload or {}
        org = cls.resolve_org(upsell.organization or upsell.property_profile.organization)
        prop = upsell.property_profile
        provider_key = (payload.get("provider_key") or "stripe").lower()
        now = timezone.now()

        tx = upsell.payment_transaction
        if not tx:
            tx = PaymentTransaction.objects.create(
                organization=org,
                provider_key=provider_key,
                scope=PaymentTransaction.Scope.GUEST_UPSELL,
                status=PaymentTransaction.Status.SUCCEEDED,
                amount=upsell.price,
                currency=upsell.currency or (org.currency if org else "USD"),
                external_transaction_id=f"upsell_{uuid.uuid4().hex[:12]}",
                customer_email=(
                    upsell.reservation.guest_email
                    if upsell.reservation and upsell.reservation.guest_email
                    else "guest@hospitality.example.com"
                ),
                description=f"Guest Experience: {upsell.service_name} ({prop.code})",
                is_sandbox=True,
                completed_at=now,
            )

        wo = upsell.fulfillment_work_order
        if not wo:
            due_at = (
                upsell.reservation.check_in_at
                if upsell.reservation and upsell.reservation.check_in_at > now
                else now + timedelta(hours=3)
            )
            wo = PropertyWorkOrder.all_objects.create(
                organization=org,
                code=f"WO-VIP-{uuid.uuid4().hex[:5].upper()}",
                title=f"Guest Experience: {upsell.service_name} — {prop.name}",
                property_profile=prop,
                reservation=upsell.reservation,
                work_type=PropertyWorkOrder.WorkType.GUEST_CONCIERGE,
                priority=PropertyWorkOrder.Priority.HIGH,
                status=PropertyWorkOrder.WorkStatus.DISPATCHED,
                assigned_to=prop.default_cleaner,
                scheduled_start_at=now,
                must_complete_by=due_at,
                checklist_items=_instantiate_checklist(
                    [
                        {
                            "id": "vip-1",
                            "room_area": "Guest Experience Delivery",
                            "instruction": f"Prepare and verify '{upsell.service_name}' for {upsell.guest_name or 'VIP Guest'}.",
                            "requires_photo": True,
                            "is_critical": True,
                        }
                    ]
                ),
                estimated_cost=(upsell.price * Decimal("0.55")).quantize(Decimal("0.01")),
                billable_to=PropertyWorkOrder.BillableScope.GUEST_UPSELL,
                field_notes=f"Auto-dispatched upon {provider_key.upper()} payment ({tx.external_transaction_id}).",
            )

        mark_fulfilled = bool(payload.get("mark_fulfilled", False))
        upsell.payment_transaction = tx
        upsell.fulfillment_work_order = wo
        upsell.status = (
            GuestServiceUpsell.UpsellStatus.FULFILLED
            if mark_fulfilled
            else GuestServiceUpsell.UpsellStatus.PAID_SCHEDULED
        )
        upsell.save()

        cls._send_ops_notification(
            organization=org,
            subject=f"[SERVICE REVENUE +${upsell.price}] {upsell.service_name} @ {prop.code}",
            body=(
                f"Guest Experience Add-On Confirmed & Paid ({provider_key.upper()})\n"
                f"Property: {prop.code} - {prop.name}\n"
                f"Service: {upsell.service_name} (${upsell.price} {upsell.currency})\n"
                f"Transaction ID: {tx.external_transaction_id}\n"
                f"Dispatched Field Work Order: {wo.code} -> {wo.assigned_to}\n"
            ),
            recipient=tx.customer_email,
        )

        return {
            "upsell": upsell,
            "payment_transaction": tx,
            "work_order": wo,
        }

    @classmethod
    def run_automation_scenario(
        cls,
        scenario: str,
        organization: Organization | None = None,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Executes end-to-end Breezeway-style property operations automation scenarios
        from n8n webhooks or the interactive workspace simulator.
        """
        payload = payload or {}
        org = cls.resolve_org(organization)
        cls.ensure_default_templates_and_seed(org)

        prop = PropertyProfile.all_objects.filter(organization=org).first()
        if not prop:
            prop = PropertyProfile.all_objects.create(
                organization=org,
                code=f"PROP-{uuid.uuid4().hex[:4].upper()}",
                name="Coastal Horizon Villa",
                property_type=PropertyProfile.PropertyType.SHORT_TERM_RENTAL,
                readiness_status=PropertyProfile.ReadinessStatus.VERIFIED_READY,
            )

        now = timezone.now()

        if scenario == "same_day_turnover":
            res = ReservationTurn.all_objects.create(
                organization=org,
                property_profile=prop,
                confirmation_code=f"ABNB-{uuid.uuid4().hex[:5].upper()}",
                guest_name=payload.get("guest_name") or "Claire & Marcus Sterling",
                guest_email="sterling.vip@example.com",
                guests_count=4,
                channel=ReservationTurn.Channel.AIRBNB,
                stay_status=ReservationTurn.StayStatus.CHECKED_OUT,
                check_in_at=now - timedelta(days=3),
                check_out_at=now,
                next_guest_check_in_at=now + timedelta(hours=4),
                is_same_day_turn=True,
                reservation_total=Decimal("2950.00"),
                special_requests="Back-to-back VIP turnover: prioritize suite staging & smart-lock rotation.",
            )
            wo = cls.schedule_turnover_for_reservation(res)
            return {
                "scenario": scenario,
                "scenario_label": "Automated Same-Day STR Turnover & SLA Dispatch",
                "status_outcome": "VERIFIED_OR_DISPATCHED_CLEANLY",
                "property": prop,
                "reservation": res,
                "work_order": wo,
                "summary": f"Detected back-to-back turnover on {prop.code}; auto-scheduled {wo.code} with {len(wo.checklist_items)} photo-verified steps.",
            }

        if scenario == "inspection_defect_escalation":
            wo = (
                PropertyWorkOrder.all_objects.filter(
                    organization=org, property_profile=prop
                )
                .exclude(status=PropertyWorkOrder.WorkStatus.VERIFIED_COMPLETE)
                .first()
            )
            if not wo:
                tpl = ChecklistTemplate.all_objects.filter(organization=org).first()
                wo = PropertyWorkOrder.all_objects.create(
                    organization=org,
                    code=f"WO-{uuid.uuid4().hex[:6].upper()}",
                    title=f"Pre-Arrival Inspection — {prop.name}",
                    property_profile=prop,
                    template=tpl,
                    work_type=PropertyWorkOrder.WorkType.QUALITY_INSPECTION,
                    priority=PropertyWorkOrder.Priority.URGENT_SAME_DAY,
                    status=PropertyWorkOrder.WorkStatus.IN_PROGRESS,
                    checklist_items=_instantiate_checklist(
                        tpl.items_schema if tpl else DEFAULT_INSPECTION_CHECKLIST_ITEMS
                    ),
                )

            items = _instantiate_checklist(wo.checklist_items or DEFAULT_INSPECTION_CHECKLIST_ITEMS)
            if items:
                items[0]["completed"] = True
                items[0]["photo_url"] = "https://cdn.musfiqdehan.com/beamline/demo/defect-thermostat.jpg"
                items[0]["flagged_defect"] = True
                items[0]["defect_notes"] = "Smart patio sliding latch misaligned & smart thermostat offline."

            result = cls.verify_work_order(
                wo,
                {
                    "checklist_items": items,
                    "verification_photos": ["https://cdn.musfiqdehan.com/beamline/demo/defect-thermostat.jpg"],
                    "defect_summary": "Smart patio door latch misaligned & smart thermostat offline before VIP arrival.",
                    "estimated_repair_cost": "340.00",
                    "repair_vendor": "Coastal Smart Home & Locksmith",
                    "billable_to": PropertyWorkOrder.BillableScope.PROPERTY_OWNER,
                    "verified_by": "Marcus Vance (Quality Inspector)",
                },
            )
            return {
                "scenario": scenario,
                "scenario_label": "Field Photo Verification -> Defect Escalation & Cost Capture",
                "status_outcome": "FLAGGED_MAINTENANCE_HOLD",
                "property": result["property"],
                "work_order": result["escalated_work_order"],
                "created_cost": result["created_cost"],
                "summary": (
                    f"Flagged defect on {prop.code}: placed on Maintenance Hold, dispatched repair "
                    f"{result['escalated_work_order'].code}, and recorded owner-billable cost."
                ),
            }

        if scenario == "guest_upsell_monetization":
            upsell = GuestServiceUpsell.all_objects.create(
                organization=org,
                property_profile=prop,
                service_name="Early Check-In + Heated Spa & Champagne Welcome",
                category=GuestServiceUpsell.ServiceCategory.CONCIERGE,
                guest_name="VIP Incoming Guest",
                price=Decimal("245.00"),
                operator_commission_percent=Decimal("40.00"),
                currency=org.currency if org else "USD",
                status=GuestServiceUpsell.UpsellStatus.REQUESTED,
                notes="Automated upsell accepted via digital guest guide.",
            )
            fulfilled = cls.fulfill_guest_upsell(upsell, {"provider_key": "stripe"})
            return {
                "scenario": scenario,
                "scenario_label": "Guest Experience Upsell Checkout & Concierge Dispatch",
                "status_outcome": "VERIFIED_OR_DISPATCHED_CLEANLY",
                "property": prop,
                "upsell": fulfilled["upsell"],
                "work_order": fulfilled["work_order"],
                "payment_transaction": fulfilled["payment_transaction"],
                "summary": (
                    f"Captured $245.00 guest service revenue on {prop.code} via Stripe and "
                    f"auto-dispatched concierge work order {fulfilled['work_order'].code}."
                ),
            }

        raise ValueError(
            f"Unsupported scenario '{scenario}'. Choose 'same_day_turnover', "
            "'inspection_defect_escalation', or 'guest_upsell_monetization'."
        )
