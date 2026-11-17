from __future__ import annotations

import re
from decimal import Decimal
from rest_framework import serializers
from crm.models import (
    ChecklistTemplate,
    ConstructionProject,
    Contact,
    EmailCommunicationLog,
    GuestServiceUpsell,
    MaterialOrder,
    Opportunity,
    ProjectCost,
    ProjectTask,
    PropertyProfile,
    PropertyWorkOrder,
    ReservationTurn,
    SalesActivity,
)

PHONE_REGEX = re.compile(r"^[0-9+\-() .ext]{7,30}$", re.IGNORECASE)


class ContactSerializer(serializers.ModelSerializer):
    opportunities_count = serializers.IntegerField(
        source="opportunities.count", read_only=True
    )

    class Meta:
        model = Contact
        fields = [
            "id",
            "name",
            "contact_type",
            "email",
            "phone",
            "company_or_household",
            "preferred_channel",
            "referral_source",
            "enquiry_summary",
            "opportunities_count",
            "notion_page_id",
            "notion_url",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "opportunities_count", "created_at", "updated_at"]

    def validate_name(self, value: str) -> str:
        cleaned = value.strip()
        if len(cleaned) < 2:
            raise serializers.ValidationError("Contact name must be at least 2 characters long.")
        return cleaned

    def validate_phone(self, value: str) -> str:
        cleaned = value.strip()
        if cleaned and not PHONE_REGEX.match(cleaned):
            raise serializers.ValidationError("Please enter a valid phone number format.")
        return cleaned


class ConstructionProjectSerializer(serializers.ModelSerializer):
    tasks_count = serializers.IntegerField(source="tasks.count", read_only=True)
    materials_count = serializers.IntegerField(source="material_orders.count", read_only=True)
    costs_count = serializers.IntegerField(source="costs.count", read_only=True)

    class Meta:
        model = ConstructionProject
        fields = [
            "id",
            "code",
            "name",
            "phase",
            "status",
            "project_manager",
            "site_address",
            "contract_budget",
            "start_date",
            "target_completion_date",
            "progress_percent",
            "latest_update",
            "tasks_count",
            "materials_count",
            "costs_count",
            "notion_page_id",
            "notion_url",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "tasks_count",
            "materials_count",
            "costs_count",
            "created_at",
            "updated_at",
        ]

    def validate_code(self, value: str) -> str:
        cleaned = value.strip().upper()
        if len(cleaned) < 3:
            raise serializers.ValidationError("Project code must be at least 3 characters (e.g., PRJ-101).")
        return cleaned

    def validate_contract_budget(self, value: Decimal) -> Decimal:
        if value <= Decimal("0"):
            raise serializers.ValidationError("Contract budget must be greater than zero.")
        return value

    def validate_progress_percent(self, value: int) -> int:
        if not (0 <= value <= 100):
            raise serializers.ValidationError("Progress percentage must be between 0 and 100.")
        return value

    def validate(self, attrs):
        start_date = attrs.get("start_date", getattr(self.instance, "start_date", None))
        target_date = attrs.get(
            "target_completion_date",
            getattr(self.instance, "target_completion_date", None),
        )
        if start_date and target_date and target_date < start_date:
            raise serializers.ValidationError(
                {"target_completion_date": "Target completion date cannot be earlier than start date."}
            )
        return attrs


class OpportunitySerializer(serializers.ModelSerializer):
    contact = serializers.PrimaryKeyRelatedField(
        queryset=Contact.objects.all(), required=False, allow_null=True
    )
    linked_project = serializers.PrimaryKeyRelatedField(
        queryset=ConstructionProject.objects.all(), required=False, allow_null=True
    )
    contact_name = serializers.CharField(source="contact.name", read_only=True, default="")
    project_name = serializers.CharField(
        source="linked_project.name", read_only=True, default=""
    )
    project_code = serializers.CharField(
        source="linked_project.code", read_only=True, default=""
    )

    class Meta:
        model = Opportunity
        fields = [
            "id",
            "name",
            "stage",
            "sales_owner",
            "contact",
            "contact_name",
            "linked_project",
            "project_name",
            "project_code",
            "estimated_value",
            "design_agreement_status",
            "construction_agreement_status",
            "requires_kevin_review",
            "kevin_review_notes",
            "next_follow_up_date",
            "qualification_notes",
            "notion_page_id",
            "notion_url",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "contact_name",
            "project_name",
            "project_code",
            "created_at",
            "updated_at",
        ]

    def to_internal_value(self, data):
        if isinstance(data, dict) and data.get("next_follow_up_date") == "":
            data = data.copy()
            data["next_follow_up_date"] = None
        return super().to_internal_value(data)

    def validate_name(self, value: str) -> str:
        cleaned = value.strip()
        if len(cleaned) < 3:
            raise serializers.ValidationError("Opportunity name must be at least 3 characters.")
        return cleaned

    def validate_estimated_value(self, value: Decimal) -> Decimal:
        if value <= Decimal("0"):
            raise serializers.ValidationError("Estimated deal value must be greater than zero.")
        return value


class SalesActivitySerializer(serializers.ModelSerializer):
    opportunity = serializers.PrimaryKeyRelatedField(
        queryset=Opportunity.objects.all()
    )
    contact = serializers.PrimaryKeyRelatedField(
        queryset=Contact.objects.all(), required=False, allow_null=True
    )
    opportunity_name = serializers.CharField(
        source="opportunity.name", read_only=True, default=""
    )
    contact_name = serializers.CharField(source="contact.name", read_only=True, default="")

    class Meta:
        model = SalesActivity
        fields = [
            "id",
            "title",
            "activity_type",
            "opportunity",
            "opportunity_name",
            "contact",
            "contact_name",
            "owner",
            "activity_date",
            "completed",
            "outcome_notes",
            "notion_page_id",
            "notion_url",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "opportunity_name",
            "contact_name",
            "created_at",
            "updated_at",
        ]

    def validate_title(self, value: str) -> str:
        cleaned = value.strip()
        if len(cleaned) < 3:
            raise serializers.ValidationError("Activity title must be at least 3 characters.")
        return cleaned


class ProjectTaskSerializer(serializers.ModelSerializer):
    project = serializers.PrimaryKeyRelatedField(
        queryset=ConstructionProject.objects.all()
    )
    project_name = serializers.CharField(source="project.name", read_only=True, default="")
    project_code = serializers.CharField(source="project.code", read_only=True, default="")

    class Meta:
        model = ProjectTask
        fields = [
            "id",
            "title",
            "project",
            "project_name",
            "project_code",
            "phase",
            "assigned_to",
            "priority",
            "status",
            "deadline",
            "progress_updates",
            "notion_page_id",
            "notion_url",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "project_name", "project_code", "created_at", "updated_at"]

    def validate_title(self, value: str) -> str:
        cleaned = value.strip()
        if len(cleaned) < 3:
            raise serializers.ValidationError("Task title must be at least 3 characters.")
        return cleaned


class MaterialOrderSerializer(serializers.ModelSerializer):
    project = serializers.PrimaryKeyRelatedField(
        queryset=ConstructionProject.objects.all()
    )
    project_name = serializers.CharField(source="project.name", read_only=True, default="")
    project_code = serializers.CharField(source="project.code", read_only=True, default="")

    class Meta:
        model = MaterialOrder
        fields = [
            "id",
            "item_name",
            "project",
            "project_name",
            "project_code",
            "supplier",
            "order_reference",
            "status",
            "quantity_description",
            "unit_cost_total",
            "order_date",
            "expected_delivery_date",
            "actual_delivery_date",
            "received_by",
            "delivery_notes",
            "notion_page_id",
            "notion_url",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "project_name", "project_code", "created_at", "updated_at"]

    def validate_item_name(self, value: str) -> str:
        cleaned = value.strip()
        if len(cleaned) < 2:
            raise serializers.ValidationError("Material item name must be at least 2 characters.")
        return cleaned

    def validate(self, attrs):
        order_date = attrs.get("order_date", getattr(self.instance, "order_date", None))
        expected_date = attrs.get(
            "expected_delivery_date",
            getattr(self.instance, "expected_delivery_date", None),
        )
        if order_date and expected_date and expected_date < order_date:
            raise serializers.ValidationError(
                {"expected_delivery_date": "Expected delivery date cannot precede order date."}
            )
        return attrs


class ProjectCostSerializer(serializers.ModelSerializer):
    project = serializers.PrimaryKeyRelatedField(
        queryset=ConstructionProject.objects.all(), required=False, allow_null=True
    )
    project_name = serializers.CharField(source="project.name", read_only=True, default="")
    project_code = serializers.CharField(source="project.code", read_only=True, default="")

    class Meta:
        model = ProjectCost
        fields = [
            "id",
            "title",
            "supplier",
            "document_reference",
            "project",
            "project_name",
            "project_code",
            "invoice_date",
            "event_timestamp",
            "amount",
            "currency",
            "payment_status",
            "payment_due_date",
            "supporting_document_url",
            "source_email",
            "submission_count",
            "needs_clarification",
            "clarification_notes",
            "notified_person",
            "notion_page_id",
            "notion_url",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "project_name",
            "project_code",
            "created_at",
            "updated_at",
        ]

    def validate_amount(self, value: Decimal) -> Decimal:
        if value <= Decimal("0"):
            raise serializers.ValidationError("Cost amount must be strictly greater than zero.")
        return value

    def validate_document_reference(self, value: str) -> str:
        cleaned = value.strip()
        if len(cleaned) < 2:
            raise serializers.ValidationError("Document reference is required.")
        return cleaned

    def validate(self, attrs):
        invoice_date = attrs.get("invoice_date", getattr(self.instance, "invoice_date", None))
        due_date = attrs.get("payment_due_date", getattr(self.instance, "payment_due_date", None))
        if invoice_date and due_date and due_date < invoice_date:
            raise serializers.ValidationError(
                {"payment_due_date": "Payment due date cannot be earlier than the invoice date."}
            )
        return attrs


class EmailCommunicationLogSerializer(serializers.ModelSerializer):
    related_cost = serializers.PrimaryKeyRelatedField(
        queryset=ProjectCost.objects.all(), required=False, allow_null=True
    )
    related_cost_ref = serializers.CharField(
        source="related_cost.document_reference", read_only=True, default=""
    )

    class Meta:
        model = EmailCommunicationLog
        fields = [
            "id",
            "subject",
            "sender",
            "recipient",
            "direction",
            "status",
            "body_preview",
            "attachment_name",
            "related_cost",
            "related_cost_ref",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "related_cost_ref", "created_at", "updated_at"]


class InvoiceExtractRequestSerializer(serializers.Serializer):
    """Validates incoming email/PDF extraction requests from n8n or simulator."""

    email_subject = serializers.CharField(max_length=255, required=False, allow_blank=True, default="")
    email_sender = serializers.EmailField(required=False, allow_blank=True, default="billing@vendor.com")
    email_body = serializers.CharField(required=False, allow_blank=True, default="")
    attachment_base64 = serializers.CharField(required=False, allow_blank=True, default="")
    attachment_filename = serializers.CharField(max_length=255, required=False, allow_blank=True, default="")
    llm_provider = serializers.ChoiceField(
        choices=["auto", "deterministic", "openai", "gemini", "deepseek"],
        default="auto",
        required=False,
    )


class InvoiceProcessRequestSerializer(serializers.Serializer):
    """Validates extracted cost payload for idempotent deduplication, Notion sync, and notification."""

    title = serializers.CharField(max_length=220, required=False, allow_blank=True, allow_null=True, default="")
    supplier = serializers.CharField(max_length=180, required=False, allow_blank=True, allow_null=True, default="Unknown Supplier / Subcontractor")
    document_reference = serializers.CharField(max_length=100, required=False, allow_blank=True, allow_null=True, default="")
    project_reference = serializers.CharField(max_length=220, required=False, allow_blank=True, allow_null=True, default="")
    invoice_date = serializers.DateField(required=False, allow_null=True, default=None)
    event_timestamp = serializers.DateTimeField(required=False, allow_null=True, default=None)
    amount = serializers.DecimalField(
        max_digits=12, decimal_places=2, required=False, allow_null=True, default=None
    )
    currency = serializers.ChoiceField(
        choices=["USD", "CAD", "EUR", "GBP"], default="USD", required=False, allow_null=True
    )
    payment_status = serializers.ChoiceField(
        choices=["Paid", "Unpaid", "Partially Paid"], default="Unpaid", required=False, allow_null=True
    )
    payment_due_date = serializers.DateField(required=False, allow_null=True, default=None)
    supporting_document_url = serializers.URLField(required=False, allow_blank=True, default="")
    source_email = serializers.EmailField(required=False, allow_blank=True, default="vendor@supplier.com")
    sync_to_notion = serializers.BooleanField(default=True, required=False)

    def to_internal_value(self, data):
        if isinstance(data, dict):
            data = data.copy()
            if not data.get("supplier"):
                data["supplier"] = "Unknown Supplier / Subcontractor"
            if not data.get("title"):
                data["title"] = "Construction Cost / Invoice"
            if not data.get("currency"):
                data["currency"] = "USD"
            if not data.get("payment_status"):
                data["payment_status"] = "Unpaid"
            if data.get("amount") is None:
                data["amount"] = "0.00"

            import re
            from datetime import datetime
            def _clean_date(val):
                if not val:
                    return None
                val_s = str(val).strip()
                if not val_s:
                    return None
                m = re.search(r'(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})', val_s)
                if m:
                    return f"{int(m.group(1)):04d}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
                for fmt in ('%Y-%m-%d', '%B %d, %Y', '%b %d, %Y', '%m/%d/%Y', '%d/%m/%Y'):
                    try:
                        return datetime.strptime(val_s, fmt).date().isoformat()
                    except Exception:
                        pass
                return None

            data["invoice_date"] = _clean_date(data.get("invoice_date"))
            data["payment_due_date"] = _clean_date(data.get("payment_due_date"))

        return super().to_internal_value(data)


class SMTPTestConnectionSerializer(serializers.Serializer):
    """Allows testing outbound SMTP transmission to any recipient."""

    recipient = serializers.EmailField(required=False, allow_blank=True, default="")
    subject = serializers.CharField(
        max_length=255,
        required=False,
        default="Kevin Construction OS — Live SMTP Verification",
    )
    body = serializers.CharField(
        required=False,
        default="Live verification email sent from Kevin's Construction OS via Gmail SMTP SSL.",
    )


class ClientEmailTriggerSerializer(serializers.Serializer):
    """Allows triggering realistic client emails per Part 3 assessment."""

    client_email = serializers.EmailField(default="musfiq.works+client1@gmail.com")
    client_name = serializers.CharField(max_length=255, default="Arthur & Clara Henderson")
    project_code = serializers.CharField(max_length=50, default="PRJ-101")
    email_type = serializers.ChoiceField(
        choices=[
            "milestone_update",
            "design_agreement",
            "invoice_notice",
            "review_alert",
            "custom",
        ],
        default="milestone_update",
    )
    subject = serializers.CharField(max_length=255, required=False, allow_blank=True, default="")
    message = serializers.CharField(required=False, allow_blank=True, default="")


# ==============================================================================
# Multi-Tenancy, SuperAdmin & Authentication Serializers
# ==============================================================================
from common.tenancy import (
    Organization,
    OrganizationMember,
    PlatformSettings,
    Invitation,
    ClientSubscription,
    ClientSupportTicket,
    PlatformNotification,
)


class PlatformSettingsSerializer(serializers.ModelSerializer):
    class Meta:
        model = PlatformSettings
        fields = [
            "id",
            "platform_name",
            "base_domain",
            "site_title",
            "site_description",
            "logo_url",
            "social_cover_url",
            "allow_self_registration",
            "remember_me_enabled",
            "remember_me_duration_days",
            "access_token_lifetime_minutes",
            "updated_at",
        ]

    def validate_remember_me_duration_days(self, value: int) -> int:
        if not (1 <= value <= 365):
            raise serializers.ValidationError(
                "Remember Me duration must be between 1 and 365 days."
            )
        return value

    def validate_access_token_lifetime_minutes(self, value: int) -> int:
        if not (5 <= value <= 43200):
            raise serializers.ValidationError(
                "Access token lifetime must be between 5 and 43200 minutes."
            )
        return value


class OrganizationSerializer(serializers.ModelSerializer):
    subdomain_host = serializers.CharField(read_only=True)
    member_count = serializers.SerializerMethodField()
    project_count = serializers.SerializerMethodField()

    class Meta:
        model = Organization
        fields = [
            "id",
            "name",
            "slug",
            "subdomain_host",
            "custom_domain",
            "custom_domain_verified",
            "is_active",
            "currency",
            "deal_review_threshold",
            "invoice_review_threshold",
            "executive_recipient_email",
            "feature_flags",
            "site_title",
            "site_description",
            "logo_url",
            "social_cover_url",
            "primary_color",
            "member_count",
            "project_count",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "subdomain_host", "created_at", "updated_at"]

    def get_member_count(self, obj: Organization) -> int:
        return obj.members.filter(is_active=True).count()

    def get_project_count(self, obj: Organization) -> int:
        return getattr(obj, "crm_constructionproject_records", obj.constructionproject_set if hasattr(obj, "constructionproject_set") else None).count() if hasattr(obj, "crm_constructionproject_records") else 0

    def to_representation(self, instance: Organization) -> dict:
        ret = super().to_representation(instance)
        ret["feature_flags"] = instance.get_feature_flags()
        return ret

    def update(self, instance: Organization, validated_data: dict) -> Organization:
        # If custom domain was updated, trigger Traefik dynamic sync
        domain_changed = "custom_domain" in validated_data and validated_data["custom_domain"] != instance.custom_domain
        instance = super().update(instance, validated_data)
        if domain_changed:
            from crm.services.traefik_sync import sync_traefik_custom_domains
            sync_traefik_custom_domains()
        return instance


class OrganizationMemberSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source="user.username", read_only=True)
    email = serializers.EmailField(source="user.email", read_only=True)
    first_name = serializers.CharField(source="user.first_name", read_only=True)
    last_name = serializers.CharField(source="user.last_name", read_only=True)
    avatar_url = serializers.SerializerMethodField()
    bio = serializers.SerializerMethodField()
    job_title = serializers.SerializerMethodField()

    class Meta:
        model = OrganizationMember
        fields = [
            "id",
            "organization",
            "user",
            "username",
            "email",
            "first_name",
            "last_name",
            "avatar_url",
            "bio",
            "job_title",
            "role",
            "is_active",
            "created_at",
        ]
        read_only_fields = ["id", "created_at"]

    def get_avatar_url(self, obj: OrganizationMember) -> str:
        profile = getattr(obj.user, "profile", None)
        return profile.avatar_url if profile else ""

    def get_bio(self, obj: OrganizationMember) -> str:
        profile = getattr(obj.user, "profile", None)
        return profile.bio if profile else ""

    def get_job_title(self, obj: OrganizationMember) -> str:
        profile = getattr(obj.user, "profile", None)
        return profile.job_title if profile else ""


class InvitationSerializer(serializers.ModelSerializer):
    organization_slug = serializers.CharField(source="organization.slug", read_only=True)
    organization_name = serializers.CharField(source="organization.name", read_only=True)
    invited_by_username = serializers.CharField(source="invited_by.username", read_only=True)

    class Meta:
        model = Invitation
        fields = [
            "id",
            "invitation_type",
            "email",
            "invited_name",
            "organization",
            "organization_slug",
            "organization_name",
            "role",
            "token",
            "status",
            "invited_by",
            "invited_by_username",
            "expires_at",
            "created_at",
        ]
        read_only_fields = ["id", "token", "created_at"]


class GoogleAuthRequestSerializer(serializers.Serializer):
    id_token = serializers.CharField(required=True)
    invitation_token = serializers.CharField(required=False, allow_blank=True, default="")
    remember_me = serializers.BooleanField(required=False, default=False)


class LoginRequestSerializer(serializers.Serializer):
    username_or_email = serializers.CharField(required=True)
    password = serializers.CharField(required=True)
    remember_me = serializers.BooleanField(required=False, default=False)


class RegisterRequestSerializer(serializers.Serializer):
    email = serializers.EmailField(required=True)
    password = serializers.CharField(required=True, min_length=8)
    full_name = serializers.CharField(required=False, allow_blank=True, default="")
    username = serializers.CharField(required=False, allow_blank=True, default="")
    organization_name = serializers.CharField(required=False, allow_blank=True, default="")
    organization_slug = serializers.CharField(required=False, allow_blank=True, default="")
    remember_me = serializers.BooleanField(required=False, default=False)


class RefreshTokenRequestSerializer(serializers.Serializer):
    refresh_token = serializers.CharField(required=True)


class ClientSubscriptionSerializer(serializers.ModelSerializer):
    organization_name = serializers.CharField(source="organization.name", read_only=True)
    organization_slug = serializers.CharField(source="organization.slug", read_only=True)

    class Meta:
        model = ClientSubscription
        fields = [
            "id",
            "organization",
            "organization_name",
            "organization_slug",
            "plan_tier",
            "monthly_price",
            "billing_cycle",
            "status",
            "payment_method",
            "next_billing_date",
            "last_payment_date",
            "total_paid_ytd",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


class ClientSupportTicketSerializer(serializers.ModelSerializer):
    organization_name = serializers.CharField(source="organization.name", read_only=True)
    organization_slug = serializers.CharField(source="organization.slug", read_only=True)

    class Meta:
        model = ClientSupportTicket
        fields = [
            "id",
            "organization",
            "organization_name",
            "organization_slug",
            "submitted_by_name",
            "submitted_by_email",
            "subject",
            "category",
            "priority",
            "status",
            "message",
            "admin_notes",
            "created_at",
            "updated_at",
            "resolved_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


class PlatformNotificationSerializer(serializers.ModelSerializer):
    target_organization_name = serializers.CharField(
        source="target_organization.name", read_only=True
    )
    target_organization_slug = serializers.CharField(
        source="target_organization.slug", read_only=True
    )

    class Meta:
        model = PlatformNotification
        fields = [
            "id",
            "title",
            "message",
            "severity",
            "target_organization",
            "target_organization_name",
            "target_organization_slug",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


class PlatformUserDirectorySerializer(serializers.Serializer):
    id = serializers.CharField()
    username = serializers.CharField()
    email = serializers.EmailField()
    first_name = serializers.CharField()
    last_name = serializers.CharField()
    avatar_url = serializers.CharField(allow_blank=True, default="")
    bio = serializers.CharField(allow_blank=True, default="")
    job_title = serializers.CharField(allow_blank=True, default="")
    is_active = serializers.BooleanField()
    is_superuser = serializers.BooleanField()
    date_joined = serializers.DateTimeField()
    last_login = serializers.DateTimeField(allow_null=True)
    organization = serializers.CharField(allow_null=True)
    organization_name = serializers.CharField(allow_null=True)
    role = serializers.CharField()


class ChecklistTemplateSerializer(serializers.ModelSerializer):
    items_count = serializers.SerializerMethodField()

    class Meta:
        model = ChecklistTemplate
        fields = [
            "id",
            "name",
            "category",
            "description",
            "estimated_duration_minutes",
            "requires_supervisor_signoff",
            "items_schema",
            "items_count",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "items_count", "created_at", "updated_at"]

    def get_items_count(self, obj: ChecklistTemplate) -> int:
        return len(obj.items_schema or [])


class PropertyProfileSerializer(serializers.ModelSerializer):
    owner_contact = serializers.PrimaryKeyRelatedField(
        queryset=Contact.objects.all(), required=False, allow_null=True
    )
    source_project = serializers.PrimaryKeyRelatedField(
        queryset=ConstructionProject.objects.all(), required=False, allow_null=True
    )
    owner_contact_name = serializers.CharField(
        source="owner_contact.name", read_only=True, default=""
    )
    source_project_code = serializers.CharField(
        source="source_project.code", read_only=True, default=""
    )
    source_project_name = serializers.CharField(
        source="source_project.name", read_only=True, default=""
    )
    work_orders_count = serializers.IntegerField(source="work_orders.count", read_only=True)
    open_work_orders_count = serializers.SerializerMethodField()
    reservations_count = serializers.IntegerField(source="reservations.count", read_only=True)
    upsells_revenue_total = serializers.SerializerMethodField()

    class Meta:
        model = PropertyProfile
        fields = [
            "id",
            "code",
            "name",
            "property_type",
            "readiness_status",
            "address",
            "bedrooms",
            "bathrooms",
            "max_guests",
            "nightly_rate",
            "management_fee_percent",
            "smart_lock_code",
            "wifi_network",
            "access_instructions",
            "owner_contact",
            "owner_contact_name",
            "source_project",
            "source_project_code",
            "source_project_name",
            "default_cleaner",
            "default_inspector",
            "supplies_status",
            "last_verified_at",
            "latest_operational_note",
            "work_orders_count",
            "open_work_orders_count",
            "reservations_count",
            "upsells_revenue_total",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "owner_contact_name",
            "source_project_code",
            "source_project_name",
            "work_orders_count",
            "open_work_orders_count",
            "reservations_count",
            "upsells_revenue_total",
            "created_at",
            "updated_at",
        ]
        extra_kwargs = {
            "code": {"required": False, "allow_blank": True},
        }

    def get_open_work_orders_count(self, obj: PropertyProfile) -> int:
        return obj.work_orders.exclude(
            status=PropertyWorkOrder.WorkStatus.VERIFIED_COMPLETE
        ).count()

    def get_upsells_revenue_total(self, obj: PropertyProfile) -> str:
        paid_upsells = obj.upsells.filter(
            status__in=[
                GuestServiceUpsell.UpsellStatus.PAID_SCHEDULED,
                GuestServiceUpsell.UpsellStatus.FULFILLED,
            ]
        )
        total = sum((u.price for u in paid_upsells), Decimal("0.00"))
        return str(total)

    def validate(self, attrs):
        import uuid
        from common.middleware import get_current_tenant

        request = self.context.get("request")
        org = (
            getattr(request, "tenant", None)
            or get_current_tenant()
            or getattr(self.instance, "organization", None)
        )
        raw_code = attrs.get("code")
        if raw_code is not None:
            cleaned = raw_code.strip().upper()
            if not cleaned:
                cleaned = f"PROP-{uuid.uuid4().hex[:5].upper()}"
            attrs["code"] = cleaned
        elif not self.instance:
            attrs["code"] = f"PROP-{uuid.uuid4().hex[:5].upper()}"

        check_code = attrs.get("code") or getattr(self.instance, "code", None)
        if check_code and org:
            qs = PropertyProfile.all_objects.filter(organization=org, code__iexact=check_code)
            if self.instance:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise serializers.ValidationError(
                    {"code": f"A property with code '{check_code}' already exists in this workspace."}
                )
        return attrs


class ReservationTurnSerializer(serializers.ModelSerializer):
    property_profile = serializers.PrimaryKeyRelatedField(
        queryset=PropertyProfile.objects.all()
    )
    property_name = serializers.CharField(source="property_profile.name", read_only=True)
    property_code = serializers.CharField(source="property_profile.code", read_only=True)
    work_orders_count = serializers.IntegerField(source="work_orders.count", read_only=True)
    auto_schedule_turnover = serializers.BooleanField(
        write_only=True, required=False, default=True
    )

    class Meta:
        model = ReservationTurn
        fields = [
            "id",
            "property_profile",
            "property_name",
            "property_code",
            "confirmation_code",
            "guest_name",
            "guest_email",
            "guest_phone",
            "guests_count",
            "channel",
            "stay_status",
            "check_in_at",
            "check_out_at",
            "next_guest_check_in_at",
            "is_same_day_turn",
            "reservation_total",
            "special_requests",
            "work_orders_count",
            "auto_schedule_turnover",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "property_name",
            "property_code",
            "work_orders_count",
            "created_at",
            "updated_at",
        ]
        extra_kwargs = {
            "confirmation_code": {"required": False, "allow_blank": True},
        }

    def validate(self, attrs):
        import uuid

        if not attrs.get("confirmation_code") and not self.instance:
            attrs["confirmation_code"] = f"RES-{uuid.uuid4().hex[:6].upper()}"
        check_in = attrs.get("check_in_at", getattr(self.instance, "check_in_at", None))
        check_out = attrs.get("check_out_at", getattr(self.instance, "check_out_at", None))
        if check_in and check_out and check_out < check_in:
            raise serializers.ValidationError(
                {"check_out_at": "Check-out timestamp cannot be earlier than check-in timestamp."}
            )
        return attrs

    def create(self, validated_data):
        auto_schedule = validated_data.pop("auto_schedule_turnover", True)
        instance = super().create(validated_data)
        if auto_schedule:
            from crm.services.property_ops_processor import PropertyOperationsEngine

            PropertyOperationsEngine.schedule_turnover_for_reservation(instance)
        return instance


class PropertyWorkOrderSerializer(serializers.ModelSerializer):
    property_profile = serializers.PrimaryKeyRelatedField(
        queryset=PropertyProfile.objects.all()
    )
    reservation = serializers.PrimaryKeyRelatedField(
        queryset=ReservationTurn.objects.all(), required=False, allow_null=True
    )
    template = serializers.PrimaryKeyRelatedField(
        queryset=ChecklistTemplate.objects.all(), required=False, allow_null=True
    )
    property_name = serializers.CharField(source="property_profile.name", read_only=True)
    property_code = serializers.CharField(source="property_profile.code", read_only=True)
    property_readiness = serializers.CharField(
        source="property_profile.readiness_status", read_only=True
    )
    reservation_code = serializers.CharField(
        source="reservation.confirmation_code", read_only=True, default=""
    )
    guest_name = serializers.CharField(
        source="reservation.guest_name", read_only=True, default=""
    )
    template_name = serializers.CharField(source="template.name", read_only=True, default="")
    linked_cost_ref = serializers.CharField(
        source="linked_cost.document_reference", read_only=True, default=""
    )
    linked_material_ref = serializers.CharField(
        source="linked_material_order.order_reference", read_only=True, default=""
    )

    class Meta:
        model = PropertyWorkOrder
        fields = [
            "id",
            "code",
            "title",
            "property_profile",
            "property_name",
            "property_code",
            "property_readiness",
            "reservation",
            "reservation_code",
            "guest_name",
            "template",
            "template_name",
            "work_type",
            "priority",
            "status",
            "assigned_to",
            "assignee_phone",
            "scheduled_start_at",
            "must_complete_by",
            "completed_at",
            "verified_by",
            "verified_at",
            "verification_score",
            "checklist_items",
            "verification_photos",
            "supplies_used",
            "estimated_cost",
            "billable_to",
            "linked_cost",
            "linked_cost_ref",
            "linked_material_order",
            "linked_material_ref",
            "field_notes",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "property_name",
            "property_code",
            "property_readiness",
            "reservation_code",
            "guest_name",
            "template_name",
            "linked_cost_ref",
            "linked_material_ref",
            "created_at",
            "updated_at",
        ]
        extra_kwargs = {
            "code": {"required": False, "allow_blank": True},
        }

    def create(self, validated_data):
        import uuid
        from crm.services.property_ops_processor import (
            DEFAULT_TURNOVER_CHECKLIST_ITEMS,
            _instantiate_checklist,
        )

        if not validated_data.get("code"):
            validated_data["code"] = f"WO-{uuid.uuid4().hex[:6].upper()}"
        if not validated_data.get("checklist_items"):
            tpl = validated_data.get("template")
            if tpl and tpl.items_schema:
                validated_data["checklist_items"] = _instantiate_checklist(tpl.items_schema)
            else:
                validated_data["checklist_items"] = _instantiate_checklist(
                    DEFAULT_TURNOVER_CHECKLIST_ITEMS
                )
        return super().create(validated_data)


class GuestServiceUpsellSerializer(serializers.ModelSerializer):
    property_profile = serializers.PrimaryKeyRelatedField(
        queryset=PropertyProfile.objects.all()
    )
    reservation = serializers.PrimaryKeyRelatedField(
        queryset=ReservationTurn.objects.all(), required=False, allow_null=True
    )
    property_name = serializers.CharField(source="property_profile.name", read_only=True)
    property_code = serializers.CharField(source="property_profile.code", read_only=True)
    reservation_code = serializers.CharField(
        source="reservation.confirmation_code", read_only=True, default=""
    )
    payment_status = serializers.CharField(
        source="payment_transaction.status", read_only=True, default=""
    )
    payment_external_id = serializers.CharField(
        source="payment_transaction.external_transaction_id", read_only=True, default=""
    )
    work_order_code = serializers.CharField(
        source="fulfillment_work_order.code", read_only=True, default=""
    )

    class Meta:
        model = GuestServiceUpsell
        fields = [
            "id",
            "property_profile",
            "property_name",
            "property_code",
            "reservation",
            "reservation_code",
            "service_name",
            "category",
            "guest_name",
            "price",
            "operator_commission_percent",
            "currency",
            "status",
            "payment_transaction",
            "payment_status",
            "payment_external_id",
            "fulfillment_work_order",
            "work_order_code",
            "notes",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "property_name",
            "property_code",
            "reservation_code",
            "payment_status",
            "payment_external_id",
            "work_order_code",
            "created_at",
            "updated_at",
        ]




