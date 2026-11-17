"use client";

import React, { useEffect, useState } from "react";
import {
  AlertTriangle,
  ArrowRight,
  Building2,
  CalendarClock,
  Camera,
  CheckCircle2,
  ClipboardCheck,
  DollarSign,
  KeyRound,
  Layers,
  Loader2,
  Plus,
  ShieldCheck,
  Sparkles,
  Wrench,
} from "lucide-react";
import { CursorDataTable } from "@/components/common/CursorDataTable";
import { MediaAssetUploader } from "@/components/common/MediaAssetUploader";
import {
  IconTile,
  InlineAlert,
  Modal,
  ModalBody,
  ModalFooter,
  ModalHeader,
} from "@/components/ui/overlay";
import {
  Badge,
  DropdownSelect,
  Field,
  StatCard,
  type Tone,
} from "@/components/ui/primitives";
import { apiClient } from "@/lib/api-client";
import { formatCompactCurrency, formatCurrency, formatDateTimeWithSeconds } from "@/lib/format";
import type {
  ChecklistStepItem,
  ChecklistTemplate,
  ConstructionProject,
  DashboardSummary,
  GuestServiceUpsell,
  PropertyOpsAutomationResponse,
  PropertyProfile,
  PropertyWorkOrder,
  ReservationTurn,
} from "@/lib/types";

export type PropertyOpsSubTab = "properties" | "checklists" | "turnovers" | "upsells";

export interface PropertyOpsViewProps {
  subTab: PropertyOpsSubTab;
  summary: DashboardSummary | null;
  refreshCounter: number;
  onRefresh: () => void;
  showToast: (text: string, type?: "success" | "error") => void;
}

function readinessTone(status: string): Tone {
  const s = (status || "").toLowerCase();
  if (s.includes("verified ready")) return "green";
  if (s.includes("maintenance hold") || s.includes("dirty")) return "red";
  if (s.includes("cleaning") || s.includes("pending")) return "amber";
  if (s.includes("occupied")) return "indigo";
  return "gray";
}

function workStatusTone(status: string): Tone {
  const s = (status || "").toLowerCase();
  if (s.includes("verified complete") || s.includes("fulfilled") || s.includes("paid")) return "green";
  if (s.includes("flagged") || s.includes("urgent")) return "red";
  if (s.includes("progress") || s.includes("dispatched") || s.includes("pending") || s.includes("requested")) {
    return "amber";
  }
  return "gray";
}

export function PropertyOpsView({
  subTab,
  summary,
  refreshCounter,
  onRefresh,
  showToast,
}: PropertyOpsViewProps) {
  const [localRefresh, setLocalRefresh] = useState(0);
  const effectiveRefresh = refreshCounter + localRefresh;

  // Automation bar state
  const [runningScenario, setRunningScenario] = useState<string | null>(null);
  const [lastAutomation, setLastAutomation] = useState<PropertyOpsAutomationResponse | null>(null);

  // Reference lists for modals
  const [propertiesList, setPropertiesList] = useState<PropertyProfile[]>([]);
  const [templatesList, setTemplatesList] = useState<ChecklistTemplate[]>([]);
  const [projectsList, setProjectsList] = useState<ConstructionProject[]>([]);

  // Modal states
  const [isNewPropertyOpen, setIsNewPropertyOpen] = useState(false);
  const [isPromoteProjectOpen, setIsPromoteProjectOpen] = useState(false);
  const [isNewWorkOrderOpen, setIsNewWorkOrderOpen] = useState(false);
  const [isNewReservationOpen, setIsNewReservationOpen] = useState(false);
  const [isNewUpsellOpen, setIsNewUpsellOpen] = useState(false);
  const [verifyingWorkOrder, setVerifyingWorkOrder] = useState<PropertyWorkOrder | null>(null);
  const [fulfillingUpsellId, setFulfillingUpsellId] = useState<string | null>(null);
  const [updatingReadinessId, setUpdatingReadinessId] = useState<string | null>(null);

  const bumpRefresh = () => {
    setLocalRefresh((c) => c + 1);
    onRefresh();
  };

  useEffect(() => {
    Promise.all([
      apiClient.listPaginated<PropertyProfile>("/properties/", { page_size: 50 }),
      apiClient.listPaginated<ChecklistTemplate>("/property-checklists/", { page_size: 20 }),
      apiClient.listPaginated<ConstructionProject>("/projects/", { page_size: 50 }),
    ])
      .then(([propsRes, tplRes, projRes]) => {
        setPropertiesList(propsRes.results || []);
        setTemplatesList(tplRes.results || []);
        setProjectsList(projRes.results || []);
      })
      .catch(() => {
        // Non-blocking background preload
      });
  }, [effectiveRefresh]);

  const handleRunScenario = async (scenario: string) => {
    setRunningScenario(scenario);
    try {
      const res = await apiClient.post<PropertyOpsAutomationResponse>(
        "/property-ops/automate/",
        { scenario }
      );
      setLastAutomation(res.data);
      showToast(res.data.summary || "Property automation executed.", "success");
      bumpRefresh();
    } catch (err) {
      showToast(
        err instanceof Error ? err.message : "Failed to run property automation scenario.",
        "error"
      );
    } finally {
      setRunningScenario(null);
    }
  };

  const handleQuickReadinessChange = async (prop: PropertyProfile, newStatus: string) => {
    setUpdatingReadinessId(prop.id);
    try {
      await apiClient.patch(`/properties/${prop.id}/`, { readiness_status: newStatus });
      showToast(`${prop.code} readiness updated to ${newStatus}.`, "success");
      bumpRefresh();
    } catch (err) {
      showToast(
        err instanceof Error ? err.message : "Could not update property readiness.",
        "error"
      );
    } finally {
      setUpdatingReadinessId(null);
    }
  };

  const handleFulfillUpsell = async (upsell: GuestServiceUpsell) => {
    setFulfillingUpsellId(upsell.id);
    try {
      const res = await apiClient.post<{
        upsell: GuestServiceUpsell;
        work_order: PropertyWorkOrder;
        payment_external_id: string;
      }>(`/guest-upsells/${upsell.id}/fulfill/`, { provider_key: "stripe" });
      showToast(
        res.message ||
          `Collected ${formatCurrency(upsell.price, upsell.currency)} and dispatched ${res.data.work_order.code}.`,
        "success"
      );
      bumpRefresh();
    } catch (err) {
      showToast(
        err instanceof Error ? err.message : "Failed to process guest upsell.",
        "error"
      );
    } finally {
      setFulfillingUpsellId(null);
    }
  };

  const kpis = summary?.kpis;
  const managedProps = kpis?.managed_properties_count ?? propertiesList.length;
  const readyProps = kpis?.verified_ready_properties_count ?? 0;
  const activeWorkOrders = kpis?.active_work_orders_count ?? 0;
  const urgentTurns = kpis?.urgent_same_day_turns_count ?? 0;
  const upsellRevenue = kpis?.service_upsell_revenue_total ?? "0";
  const flaggedIssues = kpis?.flagged_property_issues_count ?? 0;

  return (
    <div className="space-y-6">
      {/* KPI Strip */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard
          label="Managed Properties"
          value={`${managedProps} Units`}
          hint={`${readyProps} verified guest-ready`}
          icon={Building2}
          tone="indigo"
        />
        <StatCard
          label="Same-Day Turnovers"
          value={`${urgentTurns} Urgent`}
          hint="Tight check-out to check-in SLA"
          icon={CalendarClock}
          tone={urgentTurns > 0 ? "amber" : "green"}
        />
        <StatCard
          label="Care & QA Work Orders"
          value={`${activeWorkOrders} Open`}
          hint={
            flaggedIssues > 0
              ? `${flaggedIssues} flagged maintenance holds`
              : "All checklists passing QA gates"
          }
          icon={ClipboardCheck}
          tone={flaggedIssues > 0 ? "red" : "green"}
        />
        <StatCard
          label="Service & Upsell Revenue"
          value={formatCompactCurrency(upsellRevenue)}
          hint="Early check-in, refresh & concierge"
          icon={DollarSign}
          tone="green"
        />
      </div>

      {/* Breezeway-Style Coordination & Verification Automation Bench */}
      <div className="rounded-2xl border border-stone-200/90 bg-white p-4 shadow-xs dark:border-stone-800 dark:bg-stone-900">
        <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
          <div className="flex items-start gap-3">
            <div className="flex size-9 shrink-0 items-center justify-center rounded-xl bg-amber-50 text-amber-700 dark:bg-amber-950/60 dark:text-amber-300">
              <Sparkles className="size-4" />
            </div>
            <div>
              <h3 className="text-sm font-semibold text-stone-900 dark:text-white">
                Property Operations Automation &amp; n8n Workflow Simulator
              </h3>
              <p className="text-xs text-stone-500 dark:text-stone-400">
                Test automated same-day turnover dispatch, visual defect escalation into ProjectCost, or paid guest upsell fulfillment.
              </p>
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            <button
              type="button"
              disabled={runningScenario !== null}
              onClick={() => handleRunScenario("same_day_turnover")}
              className="btn-secondary btn-sm"
            >
              {runningScenario === "same_day_turnover" ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
              ) : (
                <CalendarClock className="h-3.5 w-3.5 text-amber-600 dark:text-amber-400" />
              )}
              Simulate Same-Day Turn
            </button>
            <button
              type="button"
              disabled={runningScenario !== null}
              onClick={() => handleRunScenario("inspection_defect_escalation")}
              className="btn-secondary btn-sm"
            >
              {runningScenario === "inspection_defect_escalation" ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
              ) : (
                <AlertTriangle className="h-3.5 w-3.5 text-rose-600 dark:text-rose-400" />
              )}
              Flag Inspection Defect
            </button>
            <button
              type="button"
              disabled={runningScenario !== null}
              onClick={() => handleRunScenario("guest_upsell_monetization")}
              className="btn-primary btn-sm"
            >
              {runningScenario === "guest_upsell_monetization" ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
              ) : (
                <DollarSign className="h-3.5 w-3.5" />
              )}
              Simulate Guest Upsell ($245)
            </button>
          </div>
        </div>

        {lastAutomation && (
          <div className="mt-3 flex flex-col gap-1 rounded-xl border border-emerald-200/80 bg-emerald-50/70 px-3.5 py-2.5 text-xs text-emerald-900 dark:border-emerald-900/60 dark:bg-emerald-950/30 dark:text-emerald-200 sm:flex-row sm:items-center sm:justify-between">
            <div className="flex items-center gap-2">
              <CheckCircle2 className="h-4 w-4 shrink-0 text-emerald-600 dark:text-emerald-400" />
              <span>
                <strong>{lastAutomation.scenario_label}:</strong> {lastAutomation.summary}
              </span>
            </div>
            <Badge
              tone={
                lastAutomation.status_outcome === "FLAGGED_MAINTENANCE_HOLD"
                  ? "red"
                  : "green"
              }
            >
              {lastAutomation.status_outcome}
            </Badge>
          </div>
        )}
      </div>

      {/* ================================================================ */}
      {/* SUB-VIEW 1: PROPERTIES & READINESS BOARD                         */}
      {/* ================================================================ */}
      {subTab === "properties" && (
        <div className="space-y-4">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <p className="text-xs text-stone-500 dark:text-stone-400">
              Coordinate hospitality readiness, smart-lock pins, and post-construction estate handoffs.
            </p>
            <div className="flex flex-wrap items-center gap-2">
              <button
                type="button"
                onClick={() => setIsPromoteProjectOpen(true)}
                className="btn-secondary btn-sm"
              >
                <Layers className="h-3.5 w-3.5 text-emerald-600 dark:text-emerald-400" />
                Promote Build to Property
              </button>
              <button
                type="button"
                onClick={() => setIsNewPropertyOpen(true)}
                className="btn-primary btn-sm"
              >
                <Plus className="h-3.5 w-3.5" />
                New Property
              </button>
            </div>
          </div>

          <CursorDataTable<PropertyProfile>
            title="Managed properties & readiness status"
            endpoint="/properties/"
            refreshTrigger={effectiveRefresh}
            searchPlaceholder="Search by PROP code, property name, address..."
            filters={[
              {
                key: "readiness_status",
                label: "Readiness",
                options: [
                  { label: "Verified Ready", value: "Verified Ready" },
                  { label: "Occupied / Guest In-House", value: "Occupied / Guest In-House" },
                  { label: "Dirty / Turn Needed", value: "Dirty / Turn Needed" },
                  { label: "Cleaning in Progress", value: "Cleaning in Progress" },
                  { label: "Pending Inspection", value: "Pending Inspection" },
                  { label: "Maintenance Hold", value: "Maintenance Hold" },
                ],
              },
              {
                key: "property_type",
                label: "Type",
                options: [
                  { label: "Short-Term Rental", value: "Short-Term Rental" },
                  { label: "Luxury Estate / Villa", value: "Luxury Estate / Villa" },
                  { label: "Boutique Hospitality", value: "Boutique Hospitality" },
                  { label: "Post-Build Warranty Home", value: "Post-Build Warranty Home" },
                ],
              },
            ]}
            columns={[
              {
                key: "property",
                header: "Property & Location",
                render: (row) => (
                  <div>
                    <div className="flex flex-wrap items-center gap-1.5 font-semibold text-stone-900 dark:text-white">
                      <span className="font-mono text-amber-600 dark:text-amber-400">
                        {row.code}
                      </span>
                      <span>{row.name}</span>
                      {row.source_project_code && (
                        <Badge tone="indigo">From {row.source_project_code}</Badge>
                      )}
                    </div>
                    <div className="mt-0.5 text-xs text-stone-500 dark:text-stone-400">
                      {row.address || "Address pending"} • {row.bedrooms}bd / {row.bathrooms}ba • Up to {row.max_guests} guests
                    </div>
                    {row.latest_operational_note && (
                      <div className="mt-1 text-[11px] text-stone-500 dark:text-stone-400">
                        {row.latest_operational_note}
                      </div>
                    )}
                  </div>
                ),
              },
              {
                key: "readiness",
                header: "Readiness State",
                render: (row) => (
                  <div className="space-y-1.5 min-w-44">
                    <Badge tone={readinessTone(row.readiness_status)}>
                      {row.readiness_status}
                    </Badge>
                    <select
                      aria-label={`Readiness status for ${row.code}`}
                      disabled={updatingReadinessId === row.id}
                      value={row.readiness_status}
                      onChange={(e) => handleQuickReadinessChange(row, e.target.value)}
                      className="block w-full rounded-lg border border-stone-200 bg-white px-2 py-1 text-xs text-stone-700 dark:border-stone-700 dark:bg-stone-800 dark:text-stone-200"
                    >
                      <option value="Verified Ready">Verified Ready</option>
                      <option value="Occupied / Guest In-House">Occupied / Guest In-House</option>
                      <option value="Dirty / Turn Needed">Dirty / Turn Needed</option>
                      <option value="Cleaning in Progress">Cleaning in Progress</option>
                      <option value="Pending Inspection">Pending Inspection</option>
                      <option value="Maintenance Hold">Maintenance Hold</option>
                    </select>
                  </div>
                ),
              },
              {
                key: "access_staff",
                header: "Access & Care Team",
                render: (row) => (
                  <div className="text-xs space-y-1">
                    <div className="flex items-center gap-1 font-mono text-stone-700 dark:text-stone-300">
                      <KeyRound className="h-3 w-3 text-amber-500" />
                      PIN: {row.smart_lock_code || "N/A"}
                    </div>
                    <div className="text-stone-500 dark:text-stone-400">
                      Cleaner: {row.default_cleaner}
                    </div>
                    <div className="text-stone-500 dark:text-stone-400">
                      Supplies: <span className="font-medium text-stone-700 dark:text-stone-300">{row.supplies_status}</span>
                    </div>
                  </div>
                ),
              },
              {
                key: "metrics",
                header: "Ops & Revenue",
                render: (row) => (
                  <div className="text-xs space-y-0.5">
                    <div className="font-semibold text-stone-900 dark:text-white">
                      {formatCurrency(row.nightly_rate)} / night
                    </div>
                    <div className="text-emerald-700 dark:text-emerald-400 font-medium">
                      +{formatCurrency(row.upsells_revenue_total)} upsells
                    </div>
                    <div className="text-stone-500 dark:text-stone-400">
                      {row.open_work_orders_count} open tasks • {row.reservations_count} stays
                    </div>
                  </div>
                ),
              },
            ]}
          />
        </div>
      )}

      {/* ================================================================ */}
      {/* SUB-VIEW 2: WORK ORDERS & GUIDED VISUAL VERIFICATION             */}
      {/* ================================================================ */}
      {subTab === "checklists" && (
        <CursorDataTable<PropertyWorkOrder>
          title="Care work orders & visual QA verification"
          endpoint="/work-orders/"
          refreshTrigger={effectiveRefresh}
          onAddClick={() => setIsNewWorkOrderOpen(true)}
          addButtonLabel="New work order"
          searchPlaceholder="Search by WO code, title, assignee, property..."
          filters={[
            {
              key: "work_type",
              label: "Type",
              options: [
                { label: "Turnover Clean", value: "Turnover Clean" },
                { label: "Quality Inspection", value: "Quality Inspection" },
                { label: "Preventative Maintenance", value: "Preventative Maintenance" },
                { label: "Damage / Defect Repair", value: "Damage / Defect Repair" },
                { label: "Guest Concierge Service", value: "Guest Concierge Service" },
              ],
            },
            {
              key: "status",
              label: "Status",
              options: [
                { label: "Scheduled", value: "Scheduled" },
                { label: "Dispatched to Field", value: "Dispatched to Field" },
                { label: "In Progress", value: "In Progress" },
                { label: "Pending Verification", value: "Pending Verification" },
                { label: "Verified Complete", value: "Verified Complete" },
                { label: "Flagged / Issue Found", value: "Flagged / Issue Found" },
              ],
            },
            {
              key: "priority",
              label: "Priority",
              options: [
                { label: "Urgent Same-Day Turn", value: "Urgent Same-Day Turn" },
                { label: "High", value: "High" },
                { label: "Medium", value: "Medium" },
                { label: "Low", value: "Low" },
              ],
            },
          ]}
          columns={[
            {
              key: "work",
              header: "Work Order & Property",
              render: (row) => (
                <div>
                  <div className="flex flex-wrap items-center gap-1.5 font-semibold text-stone-900 dark:text-white">
                    <span className="font-mono text-amber-600 dark:text-amber-400">
                      {row.code}
                    </span>
                    <span>{row.title}</span>
                  </div>
                  <div className="mt-0.5 text-xs text-stone-500 dark:text-stone-400">
                    {row.property_code} ({row.property_name}) • {row.work_type}
                    {row.reservation_code ? ` • Stay ${row.reservation_code}` : ""}
                  </div>
                  {row.linked_cost_ref && (
                    <div className="mt-1 text-[11px] font-medium text-rose-600 dark:text-rose-400">
                      Linked Cost Record: {row.linked_cost_ref}
                    </div>
                  )}
                </div>
              ),
            },
            {
              key: "status",
              header: "Status & Priority",
              render: (row) => (
                <div className="space-y-1">
                  <Badge tone={workStatusTone(row.status)}>{row.status}</Badge>
                  <div className="text-xs text-stone-600 dark:text-stone-300">
                    {row.priority}
                  </div>
                </div>
              ),
            },
            {
              key: "checklist_qa",
              header: "Checklist & Proof",
              render: (row) => {
                const total = row.checklist_items?.length || 0;
                const done = (row.checklist_items || []).filter((i) => i.completed).length;
                const photoCount = row.verification_photos?.length || 0;
                return (
                  <div className="text-xs space-y-1">
                    <div className="font-medium text-stone-800 dark:text-stone-200">
                      {done}/{total} steps • {row.verification_score}% QA
                    </div>
                    <div className="flex items-center gap-1 text-stone-500 dark:text-stone-400">
                      <Camera className="h-3 w-3" />
                      {photoCount} photo proof(s)
                    </div>
                    <div className="text-stone-500 dark:text-stone-400">
                      {row.assigned_to}
                    </div>
                  </div>
                );
              },
            },
            {
              key: "sla",
              header: "SLA & Actions",
              render: (row) => (
                <div className="flex flex-col items-start gap-2 sm:items-end">
                  <div className="text-xs text-stone-500 dark:text-stone-400">
                    Due: {row.must_complete_by ? formatDateTimeWithSeconds(row.must_complete_by) : "Flexible"}
                  </div>
                  <button
                    type="button"
                    onClick={() => setVerifyingWorkOrder(row)}
                    className={
                      row.status === "Verified Complete"
                        ? "btn-secondary btn-sm"
                        : "btn-primary btn-sm"
                    }
                  >
                    <ShieldCheck className="h-3.5 w-3.5" />
                    {row.status === "Verified Complete"
                      ? "View QA Proof"
                      : "Coordinate & Verify"}
                  </button>
                </div>
              ),
            },
          ]}
        />
      )}

      {/* ================================================================ */}
      {/* SUB-VIEW 3: TURNOVERS & RESERVATIONS SCHEDULE                    */}
      {/* ================================================================ */}
      {subTab === "turnovers" && (
        <CursorDataTable<ReservationTurn>
          title="Reservations & automated turnover schedule"
          endpoint="/reservations/"
          refreshTrigger={effectiveRefresh}
          onAddClick={() => setIsNewReservationOpen(true)}
          addButtonLabel="Add reservation"
          searchPlaceholder="Search confirmation code, guest name, property..."
          filters={[
            {
              key: "channel",
              label: "Channel",
              options: [
                { label: "Airbnb", value: "Airbnb" },
                { label: "Vrbo", value: "Vrbo" },
                { label: "Direct / VIP Concierge", value: "Direct / VIP Concierge" },
                { label: "Booking.com", value: "Booking.com" },
                { label: "Owner Stay", value: "Owner Stay" },
              ],
            },
            {
              key: "is_same_day_turn",
              label: "Turn Urgency",
              options: [
                { label: "Same-Day Turn", value: "true" },
                { label: "Standard Turn", value: "false" },
              ],
            },
          ]}
          columns={[
            {
              key: "guest",
              header: "Guest & Confirmation",
              render: (row) => (
                <div>
                  <div className="flex flex-wrap items-center gap-1.5 font-semibold text-stone-900 dark:text-white">
                    <span className="font-mono text-amber-600 dark:text-amber-400">
                      {row.confirmation_code}
                    </span>
                    <span>{row.guest_name}</span>
                    {row.is_same_day_turn && (
                      <Badge tone="red">Urgent Same-Day Turn</Badge>
                    )}
                  </div>
                  <div className="mt-0.5 text-xs text-stone-500 dark:text-stone-400">
                    {row.property_code} ({row.property_name}) • {row.channel} • {row.guests_count} guests
                  </div>
                  {row.special_requests && (
                    <div className="mt-1 text-[11px] text-amber-700 dark:text-amber-300">
                      Request: {row.special_requests}
                    </div>
                  )}
                </div>
              ),
            },
            {
              key: "window",
              header: "Check-In / Check-Out",
              render: (row) => (
                <div className="text-xs space-y-0.5 text-stone-600 dark:text-stone-300">
                  <div>In: {formatDateTimeWithSeconds(row.check_in_at)}</div>
                  <div>Out: {formatDateTimeWithSeconds(row.check_out_at)}</div>
                </div>
              ),
            },
            {
              key: "status",
              header: "Stay & Care Dispatch",
              render: (row) => (
                <div className="space-y-1">
                  <Badge tone={row.stay_status === "Canceled" ? "red" : "green"}>
                    {row.stay_status}
                  </Badge>
                  <div className="text-xs text-stone-500 dark:text-stone-400">
                    {row.work_orders_count} linked care task(s)
                  </div>
                </div>
              ),
            },
            {
              key: "revenue",
              header: "Booking Value",
              render: (row) => (
                <div className="font-semibold text-stone-900 dark:text-white">
                  {formatCurrency(row.reservation_total)}
                </div>
              ),
            },
          ]}
        />
      )}

      {/* ================================================================ */}
      {/* SUB-VIEW 4: GUEST EXPERIENCE UPSELLS & SERVICE REVENUE           */}
      {/* ================================================================ */}
      {subTab === "upsells" && (
        <CursorDataTable<GuestServiceUpsell>
          title="Guest experience upsells & service revenue"
          endpoint="/guest-upsells/"
          refreshTrigger={effectiveRefresh}
          onAddClick={() => setIsNewUpsellOpen(true)}
          addButtonLabel="New service upsell"
          searchPlaceholder="Search service name, guest, property..."
          filters={[
            {
              key: "status",
              label: "Status",
              options: [
                { label: "Offered to Guest", value: "Offered to Guest" },
                { label: "Requested", value: "Requested" },
                { label: "Paid & Work Dispatched", value: "Paid & Work Dispatched" },
                { label: "Verified Fulfilled", value: "Verified Fulfilled" },
              ],
            },
            {
              key: "category",
              label: "Category",
              options: [
                { label: "Early Check-In / Late Check-Out", value: "Early Check-In / Late Check-Out" },
                { label: "Mid-Stay Refresh Clean", value: "Mid-Stay Refresh Clean" },
                { label: "Pool & Spa Heating", value: "Pool & Spa Heating" },
                { label: "Private Chef / Fridge Pre-Stock", value: "Private Chef / Fridge Pre-Stock" },
                { label: "Crib / Gear Rental", value: "Crib / Gear Rental" },
              ],
            },
          ]}
          columns={[
            {
              key: "service",
              header: "Experience Add-On",
              render: (row) => (
                <div>
                  <div className="font-semibold text-stone-900 dark:text-white">
                    {row.service_name}
                  </div>
                  <div className="mt-0.5 text-xs text-stone-500 dark:text-stone-400">
                    {row.property_code} ({row.property_name}) • {row.category}
                  </div>
                  <div className="mt-0.5 text-xs text-stone-500 dark:text-stone-400">
                    Guest: {row.guest_name || "VIP Guest"}
                    {row.work_order_code ? ` • Fulfilled by ${row.work_order_code}` : ""}
                  </div>
                </div>
              ),
            },
            {
              key: "price",
              header: "Service Price & Fee",
              render: (row) => (
                <div className="text-xs space-y-0.5">
                  <div className="text-sm font-bold text-emerald-700 dark:text-emerald-400">
                    {formatCurrency(row.price, row.currency)}
                  </div>
                  <div className="text-stone-500 dark:text-stone-400">
                    Operator margin: {row.operator_commission_percent}%
                  </div>
                </div>
              ),
            },
            {
              key: "status",
              header: "Payment & Dispatch",
              render: (row) => (
                <div className="space-y-1">
                  <Badge tone={workStatusTone(row.status)}>{row.status}</Badge>
                  {row.payment_external_id && (
                    <div className="font-mono text-[11px] text-stone-400">
                      TX: {row.payment_external_id}
                    </div>
                  )}
                </div>
              ),
            },
            {
              key: "actions",
              header: "Fulfill",
              render: (row) => {
                const alreadyPaid =
                  row.status === "Paid & Work Dispatched" ||
                  row.status === "Verified Fulfilled";
                return alreadyPaid ? (
                  <Badge tone="green">Dispatched</Badge>
                ) : (
                  <button
                    type="button"
                    disabled={fulfillingUpsellId === row.id}
                    onClick={() => handleFulfillUpsell(row)}
                    className="btn-primary btn-sm"
                  >
                    {fulfillingUpsellId === row.id ? (
                      <Loader2 className="h-3.5 w-3.5 animate-spin" />
                    ) : (
                      <DollarSign className="h-3.5 w-3.5" />
                    )}
                    Collect &amp; Dispatch
                  </button>
                );
              },
            },
          ]}
        />
      )}

      {/* ================================================================ */}
      {/* MODALS                                                           */}
      {/* ================================================================ */}
      <PromoteProjectModal
        isOpen={isPromoteProjectOpen}
        projects={projectsList}
        onClose={() => setIsPromoteProjectOpen(false)}
        onPromoted={(msg) => {
          showToast(msg, "success");
          bumpRefresh();
        }}
      />

      <NewPropertyModal
        isOpen={isNewPropertyOpen}
        onClose={() => setIsNewPropertyOpen(false)}
        onCreated={(msg) => {
          showToast(msg, "success");
          bumpRefresh();
        }}
      />

      <NewWorkOrderModal
        isOpen={isNewWorkOrderOpen}
        properties={propertiesList}
        templates={templatesList}
        onClose={() => setIsNewWorkOrderOpen(false)}
        onCreated={(msg) => {
          showToast(msg, "success");
          bumpRefresh();
        }}
      />

      <NewReservationModal
        isOpen={isNewReservationOpen}
        properties={propertiesList}
        onClose={() => setIsNewReservationOpen(false)}
        onCreated={(msg) => {
          showToast(msg, "success");
          bumpRefresh();
        }}
      />

      <NewUpsellModal
        isOpen={isNewUpsellOpen}
        properties={propertiesList}
        onClose={() => setIsNewUpsellOpen(false)}
        onCreated={(msg) => {
          showToast(msg, "success");
          bumpRefresh();
        }}
      />

      {verifyingWorkOrder && (
        <VerifyWorkOrderModal
          workOrder={verifyingWorkOrder}
          onClose={() => setVerifyingWorkOrder(null)}
          onVerified={(msg) => {
            setVerifyingWorkOrder(null);
            showToast(msg, "success");
            bumpRefresh();
          }}
        />
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Modal 1: Promote ConstructionProject -> PropertyProfile            */
/* ------------------------------------------------------------------ */
function PromoteProjectModal({
  isOpen,
  projects,
  onClose,
  onPromoted,
}: {
  isOpen: boolean;
  projects: ConstructionProject[];
  onClose: () => void;
  onPromoted: (msg: string) => void;
}) {
  const [selectedProjectId, setSelectedProjectId] = useState("");
  const [propertyType, setPropertyType] = useState("Post-Build Warranty Home");
  const [nightlyRate, setNightlyRate] = useState("950.00");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (isOpen && projects.length > 0 && !selectedProjectId) {
      setSelectedProjectId(projects[0].id);
    }
  }, [isOpen, projects, selectedProjectId]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedProjectId) return;
    setSubmitting(true);
    setError(null);
    try {
      const res = await apiClient.post<{
        property: PropertyProfile;
        initial_work_order: PropertyWorkOrder;
      }>(`/properties/promote-from-project/${selectedProjectId}/`, {
        property_type: propertyType,
        nightly_rate: nightlyRate,
      });
      onPromoted(
        res.message || `Promoted project to ${res.data.property.code} with initial readiness walkthrough.`
      );
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to promote construction project.");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Modal isOpen={isOpen} onClose={onClose} size="md">
      <form onSubmit={handleSubmit}>
        <ModalHeader
          icon={<IconTile icon={Layers} />}
          title="Promote Construction Build to Managed Property"
          subtitle="Transition a completed or closeout build into ongoing warranty & hospitality care."
          onClose={onClose}
        />
        <ModalBody className="space-y-4">
          {error && <InlineAlert tone="error">{error}</InlineAlert>}
          <Field label="Select Construction Project" required>
            <DropdownSelect
              value={selectedProjectId}
              onChange={setSelectedProjectId}
              options={projects.map((p) => ({
                value: p.id,
                label: `${p.code} — ${p.name}`,
                description: `${p.phase} • ${p.site_address}`,
              }))}
            />
          </Field>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <Field label="Target Operational Mode">
              <DropdownSelect
                value={propertyType}
                onChange={setPropertyType}
                options={[
                  { value: "Post-Build Warranty Home", label: "Post-Build Warranty Home" },
                  { value: "Luxury Estate / Villa", label: "Luxury Estate / Villa" },
                  { value: "Short-Term Rental", label: "Short-Term Rental" },
                ]}
              />
            </Field>
            <Field label="Nightly / Retainer Rate ($)">
              <input
                type="number"
                step="0.01"
                className="input"
                value={nightlyRate}
                onChange={(e) => setNightlyRate(e.target.value)}
              />
            </Field>
          </div>
        </ModalBody>
        <ModalFooter hint="Auto-inherits address, owner contact & schedules initial walkthrough">
          <button type="button" onClick={onClose} className="btn-secondary">
            Cancel
          </button>
          <button
            type="submit"
            disabled={submitting || !selectedProjectId}
            className="btn-primary"
          >
            {submitting ? "Promoting..." : "Promote to Property Ops"}
            <ArrowRight className="h-4 w-4" />
          </button>
        </ModalFooter>
      </form>
    </Modal>
  );
}

/* ------------------------------------------------------------------ */
/* Modal 2: Create Standalone PropertyProfile                         */
/* ------------------------------------------------------------------ */
function NewPropertyModal({
  isOpen,
  onClose,
  onCreated,
}: {
  isOpen: boolean;
  onClose: () => void;
  onCreated: (msg: string) => void;
}) {
  const [name, setName] = useState("");
  const [code, setCode] = useState("");
  const [propertyType, setPropertyType] = useState("Short-Term Rental");
  const [address, setAddress] = useState("");
  const [bedrooms, setBedrooms] = useState("3");
  const [nightlyRate, setNightlyRate] = useState("495.00");
  const [smartLockCode, setSmartLockCode] = useState("4829#");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      const res = await apiClient.post<PropertyProfile>("/properties/", {
        name,
        code: code.trim() || undefined,
        property_type: propertyType,
        address,
        bedrooms: Number(bedrooms) || 3,
        nightly_rate: nightlyRate,
        smart_lock_code: smartLockCode,
      });
      setName("");
      setCode("");
      setAddress("");
      onCreated(res.message || "Property created.");
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create property.");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Modal isOpen={isOpen} onClose={onClose} size="md">
      <form onSubmit={handleSubmit}>
        <ModalHeader
          icon={<IconTile icon={Building2} />}
          title="Add Managed Property"
          subtitle="Onboard a short-term rental, boutique unit, or luxury estate."
          onClose={onClose}
        />
        <ModalBody className="space-y-4">
          {error && <InlineAlert tone="error">{error}</InlineAlert>}
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
            <Field label="Code (Optional)">
              <input
                className="input"
                value={code}
                onChange={(e) => setCode(e.target.value)}
                placeholder="PROP-205"
              />
            </Field>
            <Field label="Property Name" required className="sm:col-span-2">
              <input
                required
                className="input"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="e.g. Laguna Sunset Penthouse"
              />
            </Field>
          </div>
          <Field label="Street Address">
            <input
              className="input"
              value={address}
              onChange={(e) => setAddress(e.target.value)}
              placeholder="410 Ocean Blvd, Laguna Beach, CA"
            />
          </Field>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
            <Field label="Property Type">
              <DropdownSelect
                value={propertyType}
                onChange={setPropertyType}
                options={[
                  { value: "Short-Term Rental", label: "Short-Term Rental" },
                  { value: "Luxury Estate / Villa", label: "Luxury Estate / Villa" },
                  { value: "Boutique Hospitality", label: "Boutique Hospitality" },
                  { value: "Post-Build Warranty Home", label: "Post-Build Warranty Home" },
                ]}
              />
            </Field>
            <Field label="Bedrooms">
              <input
                type="number"
                min="1"
                className="input"
                value={bedrooms}
                onChange={(e) => setBedrooms(e.target.value)}
              />
            </Field>
            <Field label="Nightly Rate ($)">
              <input
                type="number"
                step="0.01"
                className="input"
                value={nightlyRate}
                onChange={(e) => setNightlyRate(e.target.value)}
              />
            </Field>
          </div>
          <Field label="Smart Lock PIN / Access">
            <input
              className="input"
              value={smartLockCode}
              onChange={(e) => setSmartLockCode(e.target.value)}
            />
          </Field>
        </ModalBody>
        <ModalFooter>
          <button type="button" onClick={onClose} className="btn-secondary">
            Cancel
          </button>
          <button type="submit" disabled={submitting} className="btn-primary">
            {submitting ? "Saving..." : "Create Property"}
          </button>
        </ModalFooter>
      </form>
    </Modal>
  );
}

/* ------------------------------------------------------------------ */
/* Modal 3: Create Guided PropertyWorkOrder                           */
/* ------------------------------------------------------------------ */
function NewWorkOrderModal({
  isOpen,
  properties,
  templates,
  onClose,
  onCreated,
}: {
  isOpen: boolean;
  properties: PropertyProfile[];
  templates: ChecklistTemplate[];
  onClose: () => void;
  onCreated: (msg: string) => void;
}) {
  const [propertyId, setPropertyId] = useState("");
  const [templateId, setTemplateId] = useState("");
  const [title, setTitle] = useState("");
  const [workType, setWorkType] = useState("Turnover Clean");
  const [priority, setPriority] = useState("High");
  const [assignedTo, setAssignedTo] = useState("Elena Rostova (Lead Hospitality Tech)");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (isOpen && properties.length > 0 && !propertyId) {
      setPropertyId(properties[0].id);
    }
    if (isOpen && templates.length > 0 && !templateId) {
      setTemplateId(templates[0].id);
    }
  }, [isOpen, properties, templates, propertyId, templateId]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!propertyId) return;
    setSubmitting(true);
    setError(null);
    try {
      const res = await apiClient.post<PropertyWorkOrder>("/work-orders/", {
        property_profile: propertyId,
        template: templateId || null,
        title: title.trim() || `${workType} Task`,
        work_type: workType,
        priority,
        assigned_to: assignedTo,
      });
      setTitle("");
      onCreated(res.message || "Work order scheduled.");
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create work order.");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Modal isOpen={isOpen} onClose={onClose} size="md">
      <form onSubmit={handleSubmit}>
        <ModalHeader
          icon={<IconTile icon={Wrench} />}
          title="Schedule Property Work Order"
          subtitle="Dispatch cleaning, inspection, maintenance, or warranty care with a guided checklist."
          onClose={onClose}
        />
        <ModalBody className="space-y-4">
          {error && <InlineAlert tone="error">{error}</InlineAlert>}
          <Field label="Property" required>
            <DropdownSelect
              value={propertyId}
              onChange={setPropertyId}
              options={properties.map((p) => ({
                value: p.id,
                label: `${p.code} — ${p.name}`,
              }))}
            />
          </Field>
          <Field label="Work Order Title" required>
            <input
              required
              className="input"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="e.g. Pre-Arrival Inspection & Pool Calibration"
            />
          </Field>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <Field label="Work Type">
              <DropdownSelect
                value={workType}
                onChange={setWorkType}
                options={[
                  { value: "Turnover Clean", label: "Turnover Clean" },
                  { value: "Quality Inspection", label: "Quality Inspection" },
                  { value: "Preventative Maintenance", label: "Preventative Maintenance" },
                  { value: "Damage / Defect Repair", label: "Damage / Defect Repair" },
                  { value: "Guest Concierge Service", label: "Guest Concierge Service" },
                ]}
              />
            </Field>
            <Field label="Priority">
              <DropdownSelect
                value={priority}
                onChange={setPriority}
                options={[
                  { value: "Urgent Same-Day Turn", label: "Urgent Same-Day Turn" },
                  { value: "High", label: "High" },
                  { value: "Medium", label: "Medium" },
                  { value: "Low", label: "Low" },
                ]}
              />
            </Field>
          </div>
          <Field label="Checklist Template">
            <DropdownSelect
              value={templateId}
              onChange={setTemplateId}
              options={templates.map((t) => ({
                value: t.id,
                label: `${t.name} (${t.items_count} steps)`,
              }))}
            />
          </Field>
          <Field label="Assigned Field Technician / Inspector">
            <input
              className="input"
              value={assignedTo}
              onChange={(e) => setAssignedTo(e.target.value)}
            />
          </Field>
        </ModalBody>
        <ModalFooter>
          <button type="button" onClick={onClose} className="btn-secondary">
            Cancel
          </button>
          <button type="submit" disabled={submitting} className="btn-primary">
            {submitting ? "Dispatching..." : "Dispatch Work Order"}
          </button>
        </ModalFooter>
      </form>
    </Modal>
  );
}

/* ------------------------------------------------------------------ */
/* Modal 4: Add Reservation (Auto-Schedules Turnover Work Order)      */
/* ------------------------------------------------------------------ */
function NewReservationModal({
  isOpen,
  properties,
  onClose,
  onCreated,
}: {
  isOpen: boolean;
  properties: PropertyProfile[];
  onClose: () => void;
  onCreated: (msg: string) => void;
}) {
  const [propertyId, setPropertyId] = useState("");
  const [guestName, setGuestName] = useState("");
  const [guestEmail, setGuestEmail] = useState("");
  const [channel, setChannel] = useState("Airbnb");
  const [isSameDayTurn, setIsSameDayTurn] = useState(true);
  const [total, setTotal] = useState("2400.00");
  const [requests, setRequests] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (isOpen && properties.length > 0 && !propertyId) {
      setPropertyId(properties[0].id);
    }
  }, [isOpen, properties, propertyId]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!propertyId) return;
    setSubmitting(true);
    setError(null);
    const now = new Date();
    const checkIn = new Date(now.getTime() + 4 * 60 * 60 * 1000).toISOString();
    const checkOut = new Date(now.getTime() + 72 * 60 * 60 * 1000).toISOString();
    try {
      const res = await apiClient.post<ReservationTurn>("/reservations/", {
        property_profile: propertyId,
        guest_name: guestName,
        guest_email: guestEmail,
        channel,
        is_same_day_turn: isSameDayTurn,
        reservation_total: total,
        special_requests: requests,
        check_in_at: checkIn,
        check_out_at: checkOut,
        auto_schedule_turnover: true,
      });
      setGuestName("");
      setGuestEmail("");
      setRequests("");
      onCreated(
        res.message || "Reservation added and turnover care task auto-dispatched."
      );
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save reservation.");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Modal isOpen={isOpen} onClose={onClose} size="md">
      <form onSubmit={handleSubmit}>
        <ModalHeader
          icon={<IconTile icon={CalendarClock} />}
          title="Add Reservation & Auto-Schedule Turnover"
          subtitle="Automatically dispatches a photo-verified turnover work order on check-out."
          onClose={onClose}
        />
        <ModalBody className="space-y-4">
          {error && <InlineAlert tone="error">{error}</InlineAlert>}
          <Field label="Property" required>
            <DropdownSelect
              value={propertyId}
              onChange={setPropertyId}
              options={properties.map((p) => ({
                value: p.id,
                label: `${p.code} — ${p.name}`,
              }))}
            />
          </Field>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <Field label="Guest Name" required>
              <input
                required
                className="input"
                value={guestName}
                onChange={(e) => setGuestName(e.target.value)}
                placeholder="e.g. Jordan & Maya Vance"
              />
            </Field>
            <Field label="Guest Email">
              <input
                type="email"
                className="input"
                value={guestEmail}
                onChange={(e) => setGuestEmail(e.target.value)}
                placeholder="guest@example.com"
              />
            </Field>
          </div>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <Field label="Booking Channel">
              <DropdownSelect
                value={channel}
                onChange={setChannel}
                options={[
                  { value: "Airbnb", label: "Airbnb" },
                  { value: "Vrbo", label: "Vrbo" },
                  { value: "Direct / VIP Concierge", label: "Direct / VIP Concierge" },
                  { value: "Booking.com", label: "Booking.com" },
                  { value: "Owner Stay", label: "Owner Stay" },
                ]}
              />
            </Field>
            <Field label="Reservation Total ($)">
              <input
                type="number"
                step="0.01"
                className="input"
                value={total}
                onChange={(e) => setTotal(e.target.value)}
              />
            </Field>
          </div>
          <label className="flex items-center gap-2.5 text-sm text-stone-700 dark:text-stone-300 cursor-pointer">
            <input
              type="checkbox"
              checked={isSameDayTurn}
              onChange={(e) => setIsSameDayTurn(e.target.checked)}
              className="h-4 w-4 rounded border-stone-300 text-amber-600 focus:ring-amber-500"
            />
            Mark as Urgent Same-Day Back-to-Back Turnover
          </label>
          <Field label="Special Guest Requests">
            <textarea
              rows={2}
              className="input"
              value={requests}
              onChange={(e) => setRequests(e.target.value)}
              placeholder="e.g. Warm pool to 84F, setup travel crib in Bedroom 2"
            />
          </Field>
        </ModalBody>
        <ModalFooter>
          <button type="button" onClick={onClose} className="btn-secondary">
            Cancel
          </button>
          <button type="submit" disabled={submitting} className="btn-primary">
            {submitting ? "Scheduling..." : "Create & Auto-Dispatch Turn"}
          </button>
        </ModalFooter>
      </form>
    </Modal>
  );
}

/* ------------------------------------------------------------------ */
/* Modal 5: Create Monetizable Guest Service Upsell                   */
/* ------------------------------------------------------------------ */
function NewUpsellModal({
  isOpen,
  properties,
  onClose,
  onCreated,
}: {
  isOpen: boolean;
  properties: PropertyProfile[];
  onClose: () => void;
  onCreated: (msg: string) => void;
}) {
  const [propertyId, setPropertyId] = useState("");
  const [serviceName, setServiceName] = useState("Early Check-In (+2 Hours)");
  const [category, setCategory] = useState("Early Check-In / Late Check-Out");
  const [guestName, setGuestName] = useState("");
  const [price, setPrice] = useState("150.00");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (isOpen && properties.length > 0 && !propertyId) {
      setPropertyId(properties[0].id);
    }
  }, [isOpen, properties, propertyId]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!propertyId) return;
    setSubmitting(true);
    setError(null);
    try {
      const res = await apiClient.post<GuestServiceUpsell>("/guest-upsells/", {
        property_profile: propertyId,
        service_name: serviceName,
        category,
        guest_name: guestName,
        price,
        status: "Requested",
      });
      setGuestName("");
      onCreated(res.message || "Guest experience upsell added.");
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create guest upsell.");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Modal isOpen={isOpen} onClose={onClose} size="md">
      <form onSubmit={handleSubmit}>
        <ModalHeader
          icon={<IconTile icon={DollarSign} />}
          title="Add Monetizable Guest Experience Offer"
          subtitle="Offer early check-in, mid-stay clean, pool heating, or VIP stocking."
          onClose={onClose}
        />
        <ModalBody className="space-y-4">
          {error && <InlineAlert tone="error">{error}</InlineAlert>}
          <Field label="Property" required>
            <DropdownSelect
              value={propertyId}
              onChange={setPropertyId}
              options={properties.map((p) => ({
                value: p.id,
                label: `${p.code} — ${p.name}`,
              }))}
            />
          </Field>
          <Field label="Service Offer Name" required>
            <input
              required
              className="input"
              value={serviceName}
              onChange={(e) => setServiceName(e.target.value)}
            />
          </Field>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <Field label="Category">
              <DropdownSelect
                value={category}
                onChange={setCategory}
                options={[
                  { value: "Early Check-In / Late Check-Out", label: "Early Check-In / Late Check-Out" },
                  { value: "Mid-Stay Refresh Clean", label: "Mid-Stay Refresh Clean" },
                  { value: "Pool & Spa Heating", label: "Pool & Spa Heating" },
                  { value: "Private Chef / Fridge Pre-Stock", label: "Private Chef / Fridge Pre-Stock" },
                  { value: "Crib / Gear Rental", label: "Crib / Gear Rental" },
                ]}
              />
            </Field>
            <Field label="Price ($)" required>
              <input
                type="number"
                step="0.01"
                className="input"
                value={price}
                onChange={(e) => setPrice(e.target.value)}
              />
            </Field>
          </div>
          <Field label="Guest Name">
            <input
              className="input"
              value={guestName}
              onChange={(e) => setGuestName(e.target.value)}
              placeholder="e.g. Sophia Laurent"
            />
          </Field>
        </ModalBody>
        <ModalFooter>
          <button type="button" onClick={onClose} className="btn-secondary">
            Cancel
          </button>
          <button type="submit" disabled={submitting} className="btn-primary">
            {submitting ? "Saving..." : "Create Upsell Offer"}
          </button>
        </ModalFooter>
      </form>
    </Modal>
  );
}

/* ------------------------------------------------------------------ */
/* Modal 6: Guided Checklist & Visual R2 Verification Sign-Off        */
/* ------------------------------------------------------------------ */
function VerifyWorkOrderModal({
  workOrder,
  onClose,
  onVerified,
}: {
  workOrder: PropertyWorkOrder;
  onClose: () => void;
  onVerified: (msg: string) => void;
}) {
  const [items, setItems] = useState<ChecklistStepItem[]>(() =>
    (workOrder.checklist_items || []).map((it) => ({ ...it }))
  );
  const [globalPhotoUrl, setGlobalPhotoUrl] = useState<string>(
    workOrder.verification_photos?.[0] || ""
  );
  const [fieldNotes, setFieldNotes] = useState(workOrder.field_notes || "");
  const [suppliesLow, setSuppliesLow] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const hasAnyDefect = items.some((it) => it.flagged_defect);

  const toggleItem = (idx: number) => {
    setItems((prev) =>
      prev.map((it, i) =>
        i === idx
          ? {
              ...it,
              completed: !it.completed,
              completed_at: !it.completed ? new Date().toISOString() : null,
            }
          : it
      )
    );
  };

  const toggleDefect = (idx: number) => {
    setItems((prev) =>
      prev.map((it, i) =>
        i === idx ? { ...it, flagged_defect: !it.flagged_defect } : it
      )
    );
  };

  const updateDefectNote = (idx: number, notes: string) => {
    setItems((prev) =>
      prev.map((it, i) => (i === idx ? { ...it, defect_notes: notes } : it))
    );
  };

  const updateItemPhoto = (idx: number, url: string) => {
    setItems((prev) =>
      prev.map((it, i) => (i === idx ? { ...it, photo_url: url } : it))
    );
  };

  const handleMarkAllComplete = () => {
    const sampleUrl =
      globalPhotoUrl ||
      "https://cdn.musfiqdehan.com/beamline/demo/verified-turn-proof.jpg";
    if (!globalPhotoUrl) setGlobalPhotoUrl(sampleUrl);
    setItems((prev) =>
      prev.map((it) => ({
        ...it,
        completed: true,
        completed_at: new Date().toISOString(),
        photo_url: it.requires_photo ? it.photo_url || sampleUrl : it.photo_url,
      }))
    );
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      const res = await apiClient.post<{
        work_order: PropertyWorkOrder;
        property: PropertyProfile;
        has_defect: boolean;
      }>(`/work-orders/${workOrder.id}/verify/`, {
        checklist_items: items,
        verification_photos: globalPhotoUrl ? [globalPhotoUrl] : [],
        field_notes: fieldNotes,
        supplies_low: suppliesLow,
        verified_by: "Quality Operations Supervisor",
      });
      onVerified(
        res.message || `Work order ${workOrder.code} processed successfully.`
      );
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Verification gate failed."
      );
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Modal isOpen={true} onClose={onClose} size="xl">
      <form onSubmit={handleSubmit}>
        <ModalHeader
          icon={<IconTile icon={ShieldCheck} />}
          title={`Coordinate & Verify: ${workOrder.code}`}
          subtitle={`${workOrder.property_code} (${workOrder.property_name}) • Assigned to ${workOrder.assigned_to}`}
          onClose={onClose}
        />
        <ModalBody className="space-y-5">
          {error && <InlineAlert tone="error">{error}</InlineAlert>}

          <div className="flex flex-wrap items-center justify-between gap-2 rounded-xl border border-stone-200 bg-stone-50/70 p-3 dark:border-stone-800 dark:bg-stone-950/40">
            <div className="text-xs text-stone-600 dark:text-stone-300">
              Complete all critical room steps and upload Cloudflare R2 visual proof before flipping the property to <strong>Verified Ready</strong>.
            </div>
            <button
              type="button"
              onClick={handleMarkAllComplete}
              className="btn-secondary btn-sm"
            >
              <CheckCircle2 className="h-3.5 w-3.5 text-emerald-600" />
              Quick-Complete &amp; Attach Proof
            </button>
          </div>

          <div className="space-y-3">
            {items.map((item, idx) => (
              <div
                key={item.id || idx}
                className={`rounded-xl border p-3.5 transition ${
                  item.flagged_defect
                    ? "border-rose-300 bg-rose-50/50 dark:border-rose-900/60 dark:bg-rose-950/20"
                    : item.completed
                    ? "border-emerald-200 bg-emerald-50/40 dark:border-emerald-900/40 dark:bg-emerald-950/15"
                    : "border-stone-200 bg-white dark:border-stone-800 dark:bg-stone-900"
                }`}
              >
                <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                  <label className="flex items-start gap-3 cursor-pointer flex-1">
                    <input
                      type="checkbox"
                      checked={Boolean(item.completed)}
                      onChange={() => toggleItem(idx)}
                      className="mt-1 h-4 w-4 rounded border-stone-300 text-emerald-600 focus:ring-emerald-500"
                    />
                    <div>
                      <div className="flex flex-wrap items-center gap-1.5 text-xs font-semibold text-stone-900 dark:text-white">
                        <span>{item.room_area}</span>
                        {item.is_critical && <Badge tone="amber">Critical</Badge>}
                        {item.requires_photo && (
                          <Badge tone="indigo">Photo Required</Badge>
                        )}
                      </div>
                      <p className="mt-1 text-xs text-stone-600 dark:text-stone-300">
                        {item.instruction}
                      </p>
                    </div>
                  </label>

                  <button
                    type="button"
                    onClick={() => toggleDefect(idx)}
                    className={`btn-sm shrink-0 ${
                      item.flagged_defect ? "btn-primary bg-rose-600 hover:bg-rose-700" : "btn-secondary"
                    }`}
                  >
                    <AlertTriangle className="h-3.5 w-3.5" />
                    {item.flagged_defect ? "Defect Flagged" : "Flag Defect"}
                  </button>
                </div>

                {(item.requires_photo || item.photo_url) && (
                  <div className="mt-3 pl-7">
                    <input
                      className="input text-xs"
                      value={item.photo_url || ""}
                      onChange={(e) => updateItemPhoto(idx, e.target.value)}
                      placeholder="Proof-of-work photo URL (or upload below)"
                    />
                  </div>
                )}

                {item.flagged_defect && (
                  <div className="mt-3 pl-7">
                    <input
                      className="input text-xs border-rose-300 dark:border-rose-800"
                      value={item.defect_notes || ""}
                      onChange={(e) => updateDefectNote(idx, e.target.value)}
                      placeholder="Describe damage or maintenance issue for auto-escalation..."
                    />
                  </div>
                )}
              </div>
            ))}
          </div>

          {/* Cloudflare R2 Visual Proof Uploader */}
          <div className="rounded-xl border border-stone-200 p-4 dark:border-stone-800">
            <MediaAssetUploader
              value={globalPhotoUrl}
              onChange={setGlobalPhotoUrl}
              category="general"
              scopeId="verifications"
              label="Upload Proof-of-Work Photo / Video to Cloudflare R2"
              hint="Images (JPEG/PNG/WebP) or short walkthrough videos (MP4/WebM) stored per-tenant in R2."
            />
          </div>

          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <Field label="Field Inspector Notes">
              <textarea
                rows={2}
                className="input"
                value={fieldNotes}
                onChange={(e) => setFieldNotes(e.target.value)}
                placeholder="Smart lock tested, linens staged, thermostat calibrated..."
              />
            </Field>
            <div className="flex items-center">
              <label className="flex items-center gap-2.5 text-sm text-stone-700 dark:text-stone-300 cursor-pointer">
                <input
                  type="checkbox"
                  checked={suppliesLow}
                  onChange={(e) => setSuppliesLow(e.target.checked)}
                  className="h-4 w-4 rounded border-stone-300 text-amber-600 focus:ring-amber-500"
                />
                <span>
                  Supplies &amp; Linens Below Par — Auto-Order Restock via MaterialOrder
                </span>
              </label>
            </div>
          </div>
        </ModalBody>
        <ModalFooter
          hint={
            hasAnyDefect
              ? "Flagging a defect places the property on Maintenance Hold and auto-creates a Repair Work Order & Cost."
              : "Passing verification flips the property status to Verified Ready."
          }
        >
          <button type="button" onClick={onClose} className="btn-secondary">
            Cancel
          </button>
          <button type="submit" disabled={submitting} className="btn-primary">
            {submitting
              ? "Submitting..."
              : hasAnyDefect
              ? "Escalate Defect & Place Hold"
              : "Verify Complete & Mark Ready"}
          </button>
        </ModalFooter>
      </form>
    </Modal>
  );
}
