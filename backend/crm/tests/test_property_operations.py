from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
import pytest
from django.utils import timezone
from rest_framework.test import APIClient
from common.tenancy import Organization
from crm.models import (
    ChecklistTemplate,
    ConstructionProject,
    Contact,
    EmailCommunicationLog,
    GuestServiceUpsell,
    MaterialOrder,
    Opportunity,
    ProjectCost,
    PropertyProfile,
    PropertyWorkOrder,
    ReservationTurn,
)
from integrations.models import PaymentTransaction
from integrations.providers import ProviderRegistry, load_builtin_providers


@pytest.fixture
def api_client() -> APIClient:
    return APIClient()


@pytest.mark.django_db
def test_pms_provider_registered_and_validates():
    load_builtin_providers()
    assert "pms_hospitality_sync" in ProviderRegistry.keys()
    provider = ProviderRegistry.get_instance("pms_hospitality_sync")
    assert provider is not None

    ok_fail, msg_fail, _ = provider.test_connection({}, {"pms_platform": "Guesty"})
    assert ok_fail is False
    assert "Missing PMS API Key" in msg_fail

    ok_pass, msg_pass, details = provider.test_connection(
        {"pms_api_key": "pms_live_12345"},
        {"pms_platform": "Guesty", "auto_schedule_turnovers": True},
    )
    assert ok_pass is True
    assert "Guesty" in msg_pass
    assert details["auto_schedule_turnovers"] is True


@pytest.mark.django_db
def test_property_ops_multi_tenant_isolation(api_client: APIClient):
    kevin_org = Organization.objects.get(slug="kevin")
    apex_org = Organization.objects.create(
        name="Apex Hospitality Group",
        slug="apex-stays",
        is_active=True,
    )

    k_prop = PropertyProfile.all_objects.create(
        organization=kevin_org,
        code="PROP-KEV1",
        name="Kevin Cliffside Residence",
        nightly_rate=Decimal("900.00"),
    )
    a_prop = PropertyProfile.all_objects.create(
        organization=apex_org,
        code="PROP-APX1",
        name="Apex Downtown Loft",
        nightly_rate=Decimal("320.00"),
    )

    PropertyWorkOrder.all_objects.create(
        organization=kevin_org,
        code="WO-KEV1",
        title="Kevin Villa Turnover",
        property_profile=k_prop,
    )
    PropertyWorkOrder.all_objects.create(
        organization=apex_org,
        code="WO-APX1",
        title="Apex Loft Inspection",
        property_profile=a_prop,
    )

    res_kevin = api_client.get("/api/v1/properties/", HTTP_X_TENANT_SLUG="kevin")
    assert res_kevin.status_code == 200
    kevin_codes = [p["code"] for p in res_kevin.json()["data"]["results"]]
    assert "PROP-KEV1" in kevin_codes
    assert "PROP-APX1" not in kevin_codes

    res_apex = api_client.get("/api/v1/work-orders/", HTTP_X_TENANT_SLUG="apex-stays")
    assert res_apex.status_code == 200
    apex_wos = [w["code"] for w in res_apex.json()["data"]["results"]]
    assert "WO-APX1" in apex_wos
    assert "WO-KEV1" not in apex_wos


@pytest.mark.django_db
def test_promote_construction_project_to_property(api_client: APIClient):
    kevin_org = Organization.objects.get(slug="kevin")
    contact = Contact.all_objects.create(
        organization=kevin_org,
        name="Elena & Marcus Homeowner",
        email="owner@luxuryestate.example.com",
    )
    project = ConstructionProject.all_objects.create(
        organization=kevin_org,
        code="PRJ-901",
        name="Pacific Palisades Glass Estate",
        phase=ConstructionProject.Phase.CLOSEOUT,
        status=ConstructionProject.Status.ON_TRACK,
        site_address="880 Sunset Crest Dr, Pacific Palisades, CA",
        project_manager="Marcus Vance (Lead PM)",
    )
    Opportunity.all_objects.create(
        organization=kevin_org,
        name="Pacific Palisades Build",
        contact=contact,
        linked_project=project,
        stage=Opportunity.Stage.WON,
    )

    res = api_client.post(
        f"/api/v1/properties/promote-from-project/{project.id}/",
        {"property_type": "Luxury Estate / Villa", "nightly_rate": "1650.00"},
        format="json",
        HTTP_X_TENANT_SLUG="kevin",
    )
    assert res.status_code == 201
    payload = res.json()["data"]
    assert payload["property"]["source_project_code"] == "PRJ-901"
    assert payload["property"]["owner_contact_name"] == "Elena & Marcus Homeowner"
    assert payload["property"]["address"] == "880 Sunset Crest Dr, Pacific Palisades, CA"
    assert payload["property"]["readiness_status"] == PropertyProfile.ReadinessStatus.PENDING_INSPECTION
    assert payload["initial_work_order"]["property_profile"] == payload["property"]["id"]
    assert len(payload["initial_work_order"]["checklist_items"]) >= 2


@pytest.mark.django_db
def test_reservation_auto_schedules_same_day_turnover(api_client: APIClient):
    kevin_org = Organization.objects.get(slug="kevin")
    prop = PropertyProfile.all_objects.create(
        organization=kevin_org,
        code="PROP-TURN1",
        name="Seaview Terrace Villa",
        readiness_status=PropertyProfile.ReadinessStatus.VERIFIED_READY,
    )
    now = timezone.now()
    res = api_client.post(
        "/api/v1/reservations/",
        {
            "property_profile": str(prop.id),
            "guest_name": "Noah Sterling",
            "guest_email": "noah@example.com",
            "channel": "Airbnb",
            "check_in_at": (now + timedelta(hours=5)).isoformat(),
            "check_out_at": (now + timedelta(days=3)).isoformat(),
            "is_same_day_turn": True,
            "reservation_total": "3200.00",
            "special_requests": "Pack n Play in Primary Suite",
        },
        format="json",
        HTTP_X_TENANT_SLUG="kevin",
    )
    assert res.status_code == 201
    res_data = res.json()["data"]
    assert res_data["work_orders_count"] == 1

    wo = PropertyWorkOrder.all_objects.filter(reservation_id=res_data["id"]).first()
    assert wo is not None
    assert wo.priority == PropertyWorkOrder.Priority.URGENT_SAME_DAY
    assert wo.work_type == PropertyWorkOrder.WorkType.TURNOVER_CLEAN
    assert len(wo.checklist_items) >= 3


@pytest.mark.django_db
def test_verification_gate_and_clean_pass_with_restock(api_client: APIClient):
    kevin_org = Organization.objects.get(slug="kevin")
    project = ConstructionProject.all_objects.create(
        organization=kevin_org,
        code="PRJ-SUP1",
        name="Supply Anchor Project",
    )
    prop = PropertyProfile.all_objects.create(
        organization=kevin_org,
        code="PROP-QA1",
        name="Marina Cove Condo",
        readiness_status=PropertyProfile.ReadinessStatus.CLEANING_IN_PROGRESS,
        source_project=project,
    )
    wo = PropertyWorkOrder.all_objects.create(
        organization=kevin_org,
        code="WO-QA1",
        title="Turnover & Stage QA",
        property_profile=prop,
        checklist_items=[
            {
                "id": "step-1",
                "room_area": "Kitchen",
                "instruction": "Sanitize counters",
                "requires_photo": True,
                "is_critical": True,
                "completed": False,
                "photo_url": "",
            }
        ],
    )

    # 1. Fails verification gate when critical item incomplete
    bad_res = api_client.post(
        f"/api/v1/work-orders/{wo.id}/verify/",
        {"checklist_items": wo.checklist_items},
        format="json",
        HTTP_X_TENANT_SLUG="kevin",
    )
    assert bad_res.status_code == 400
    assert bad_res.json()["success"] is False

    # 2. Fails when photo proof missing on requires_photo item
    no_photo_items = [{**wo.checklist_items[0], "completed": True, "photo_url": ""}]
    no_photo_res = api_client.post(
        f"/api/v1/work-orders/{wo.id}/verify/",
        {"checklist_items": no_photo_items},
        format="json",
        HTTP_X_TENANT_SLUG="kevin",
    )
    assert no_photo_res.status_code == 400

    # 3. Passes with photo proof and triggers MaterialOrder when supplies_low=True
    good_items = [
        {
            **wo.checklist_items[0],
            "completed": True,
            "photo_url": "https://cdn.musfiqdehan.com/beamline/tenants/kevin/verifications/kitchen.jpg",
        }
    ]
    good_res = api_client.post(
        f"/api/v1/work-orders/{wo.id}/verify/",
        {
            "checklist_items": good_items,
            "supplies_low": True,
            "verified_by": "Marcus Vance",
        },
        format="json",
        HTTP_X_TENANT_SLUG="kevin",
    )
    assert good_res.status_code == 200
    data = good_res.json()["data"]
    assert data["has_defect"] is False
    assert data["work_order"]["status"] == PropertyWorkOrder.WorkStatus.VERIFIED_COMPLETE
    assert data["work_order"]["verification_score"] == 100
    assert data["property"]["readiness_status"] == PropertyProfile.ReadinessStatus.VERIFIED_READY
    assert data["created_material_order"] is not None
    assert MaterialOrder.all_objects.filter(pk=data["created_material_order"]["id"]).exists()


@pytest.mark.django_db
def test_defect_escalation_creates_repair_work_order_and_cost(api_client: APIClient):
    kevin_org = Organization.objects.get(slug="kevin")
    project = ConstructionProject.all_objects.create(
        organization=kevin_org,
        code="PRJ-DEF1",
        name="Cliffside Defect Lineage Build",
    )
    prop = PropertyProfile.all_objects.create(
        organization=kevin_org,
        code="PROP-DEF1",
        name="Cliffside Villa",
        source_project=project,
        readiness_status=PropertyProfile.ReadinessStatus.PENDING_INSPECTION,
    )
    wo = PropertyWorkOrder.all_objects.create(
        organization=kevin_org,
        code="WO-DEF1",
        title="Pre-Arrival Inspection",
        property_profile=prop,
        checklist_items=[
            {
                "id": "step-1",
                "room_area": "Patio Doors",
                "instruction": "Inspect sliding lock",
                "requires_photo": True,
                "is_critical": True,
                "completed": True,
                "photo_url": "https://cdn.musfiqdehan.com/beamline/demo/latch.jpg",
                "flagged_defect": True,
                "defect_notes": "Broken patio door deadbolt latch",
            }
        ],
    )

    res = api_client.post(
        f"/api/v1/work-orders/{wo.id}/verify/",
        {
            "checklist_items": wo.checklist_items,
            "estimated_repair_cost": "410.00",
            "repair_vendor": "Coastal Locksmith & Doors",
            "billable_to": "Billable to Owner",
        },
        format="json",
        HTTP_X_TENANT_SLUG="kevin",
    )
    assert res.status_code == 200
    data = res.json()["data"]
    assert data["has_defect"] is True
    assert data["property"]["readiness_status"] == PropertyProfile.ReadinessStatus.MAINTENANCE_HOLD
    assert data["escalated_work_order"]["work_type"] == PropertyWorkOrder.WorkType.DAMAGE_REPAIR
    assert data["created_cost"] is not None
    assert Decimal(data["created_cost"]["amount"]) == Decimal("410.00")
    assert ProjectCost.all_objects.filter(pk=data["created_cost"]["id"]).exists()
    assert EmailCommunicationLog.all_objects.filter(related_cost_id=data["created_cost"]["id"]).exists()


@pytest.mark.django_db
def test_guest_upsell_fulfillment_and_automation_endpoints(api_client: APIClient):
    kevin_org = Organization.objects.get(slug="kevin")
    prop = PropertyProfile.all_objects.create(
        organization=kevin_org,
        code="PROP-UPS1",
        name="Oceanfront Sanctuary",
    )
    upsell = GuestServiceUpsell.all_objects.create(
        organization=kevin_org,
        property_profile=prop,
        service_name="Private Chef & Heated Pool Package",
        category=GuestServiceUpsell.ServiceCategory.CONCIERGE,
        guest_name="Sophia Laurent",
        price=Decimal("395.00"),
        status=GuestServiceUpsell.UpsellStatus.REQUESTED,
    )

    res = api_client.post(
        f"/api/v1/guest-upsells/{upsell.id}/fulfill/",
        {"provider_key": "stripe"},
        format="json",
        HTTP_X_TENANT_SLUG="kevin",
    )
    assert res.status_code == 200
    data = res.json()["data"]
    assert data["upsell"]["status"] == GuestServiceUpsell.UpsellStatus.PAID_SCHEDULED
    assert data["work_order"]["work_type"] == PropertyWorkOrder.WorkType.GUEST_CONCIERGE
    tx = PaymentTransaction.objects.get(pk=data["payment_transaction_id"])
    assert tx.scope == PaymentTransaction.Scope.GUEST_UPSELL
    assert tx.amount == Decimal("395.00")

    # Test automation scenarios & dashboard summary
    for scenario in (
        "same_day_turnover",
        "inspection_defect_escalation",
        "guest_upsell_monetization",
    ):
        auto_res = api_client.post(
            "/api/v1/property-ops/automate/",
            {"scenario": scenario},
            format="json",
            HTTP_X_TENANT_SLUG="kevin",
        )
        assert auto_res.status_code == 200
        assert auto_res.json()["success"] is True

    dash_res = api_client.get("/api/v1/dashboard/summary/", HTTP_X_TENANT_SLUG="kevin")
    assert dash_res.status_code == 200
    dash_data = dash_res.json()["data"]
    assert dash_data["kpis"]["managed_properties_count"] >= 1
    assert Decimal(dash_data["kpis"]["service_upsell_revenue_total"]) >= Decimal("395.00")
    assert "property_ops_summary" in dash_data
