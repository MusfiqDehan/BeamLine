import {
  BarChart3,
  Building2,
  Camera,
  ClipboardCheck,
  FileCheck2,
  Hammer,
  HardHat,
  Layers3,
  Ruler,
  ShieldCheck,
  Sparkles,
  Truck,
  UsersRound,
  Workflow,
  Zap,
  type LucideIcon,
} from "lucide-react";

export const navLinks = [
  { label: "Platform", href: "#platform" },
  { label: "Integrations", href: "#integrations" },
  { label: "Multi-tenant", href: "#tenants" },
  { label: "Process", href: "#process" },
  { label: "Growth", href: "#growth" },
  { label: "Pricing", href: "#pricing" },
  { label: "FAQ", href: "#faq" },
] as const;

export const rotatingWords = [
  "digital HQ.",
  "sharper pipeline.",
  "calmer job site.",
  "verified property ops.",
  "higher service revenue.",
];

export const tapeItems: Array<{ label: string; icon: LucideIcon }> = [
  { label: "Lead capture", icon: UsersRound },
  { label: "Design agreements", icon: Ruler },
  { label: "Permits & engineering", icon: ClipboardCheck },
  { label: "Framing & rough MEP", icon: Hammer },
  { label: "Material deliveries", icon: Truck },
  { label: "Property care & turnovers", icon: Building2 },
  { label: "Photo-verified checklists", icon: Camera },
  { label: "Guest experience upsells", icon: Sparkles },
  { label: "Invoice automation", icon: Workflow },
  { label: "Duplicate protection", icon: ShieldCheck },
  { label: "Executive dashboards", icon: BarChart3 },
  { label: "Closeout & warranty", icon: FileCheck2 },
  { label: "Field-ready teams", icon: HardHat },
];

export const stats = [
  { value: 12, suffix: " hrs", label: "Admin time returned to each manager weekly" },
  { value: 3, suffix: "×", label: "Faster vendor invoice turnaround" },
  { value: 100, suffix: "%", label: "Of invoices checked for duplicates" },
  { value: 14, suffix: " days", label: "From kickoff to a live workspace" },
];

export type ExplorerTab = {
  id: "sales" | "projects" | "property_ops" | "invoices" | "insights";
  label: string;
  icon: LucideIcon;
  title: string;
  description: string;
  points: string[];
};

export const explorerTabs: ExplorerTab[] = [
  {
    id: "sales",
    label: "Sales pipeline",
    icon: UsersRound,
    title: "Every referral, tracked to a signed contract.",
    description: "Architect referrals, past clients, and new enquiries move through clear stages with the next action always visible.",
    points: ["Qualification → design → construction agreement", "Founder review flags for high-stakes deals", "One-click logging for calls and site visits"],
  },
  {
    id: "projects",
    label: "Project delivery",
    icon: Layers3,
    title: "Four phases. Zero guesswork on site.",
    description: "Standard checklists keep managers, trades, and inspectors aligned while every custom home keeps its character.",
    points: ["Pre-construction, build, closeout, warranty", "Milestones, materials, and inspections in one view", "At-risk tasks surface before they slip"],
  },
  {
    id: "property_ops",
    label: "Property care & ops",
    icon: Building2,
    title: "Coordinate, verify, and monetize every property.",
    description:
      "Power short-term rental turnovers, estate retainers, and post-build care. Auto-schedule tasks from reservations, enforce R2 photo proof, and unlock guest upsell revenue.",
    points: [
      "Same-day turnover & smart-lock readiness tracking",
      "Room-by-room photo checklists & auto defect escalation",
      "Paid guest add-ons (early check-in, refresh cleans, concierge)",
    ],
  },
  {
    id: "invoices",
    label: "Invoice automation",
    icon: Workflow,
    title: "Vendor invoices that process themselves.",
    description: "Emails and PDFs are read, matched to the right project, checked for duplicates, and routed for review when needed.",
    points: ["PDF and email field extraction", "Supplier + reference duplicate protection", "Clarification requests routed automatically"],
  },
  {
    id: "insights",
    label: "Executive insight",
    icon: BarChart3,
    title: "The whole business on one calm screen.",
    description: "Pipeline value, active builds, managed properties, service revenue, and leadership decisions — without chasing anyone for updates.",
    points: ["Live pipeline, build, and property readiness KPIs", "Cost-to-date versus budget & service upsell revenue", "A single queue for leadership decisions"],
  },
];

export type TenantTheme = {
  id: string;
  name: string;
  initials: string;
  slug: string;
  specialty: string;
  accent: { solid: string; soft: string; text: string; ring: string; bar: string };
  metrics: Array<[string, string]>;
};

export const tenants: TenantTheme[] = [
  {
    id: "northstar",
    name: "Northstar Custom Homes",
    initials: "N",
    slug: "northstar",
    specialty: "Luxury custom residences",
    accent: {
      solid: "bg-amber-400 text-stone-950",
      soft: "bg-amber-400/15",
      text: "text-amber-300",
      ring: "ring-amber-400",
      bar: "bg-amber-400",
    },
    metrics: [["$8.4M", "Pipeline"], ["7", "Live builds"], ["96%", "On-time tasks"]],
  },
  {
    id: "ridgeline",
    name: "Ridgeline Design-Build",
    initials: "R",
    slug: "ridgeline",
    specialty: "Design-build studio",
    accent: {
      solid: "bg-emerald-400 text-stone-950",
      soft: "bg-emerald-400/15",
      text: "text-emerald-300",
      ring: "ring-emerald-400",
      bar: "bg-emerald-400",
    },
    metrics: [["$5.1M", "Pipeline"], ["11", "Live builds"], ["92%", "On-time tasks"]],
  },
  {
    id: "harbor",
    name: "Harbor & Pine Renovation",
    initials: "H",
    slug: "harborpine",
    specialty: "High-end renovation",
    accent: {
      solid: "bg-sky-400 text-stone-950",
      soft: "bg-sky-400/15",
      text: "text-sky-300",
      ring: "ring-sky-400",
      bar: "bg-sky-400",
    },
    metrics: [["$2.7M", "Pipeline"], ["18", "Live builds"], ["98%", "On-time tasks"]],
  },
  {
    id: "coastal",
    name: "Coastal Haven Hospitality",
    initials: "C",
    slug: "coastalhaven",
    specialty: "Short-term rentals & luxury estates",
    accent: {
      solid: "bg-violet-400 text-stone-950",
      soft: "bg-violet-400/15",
      text: "text-violet-300",
      ring: "ring-violet-400",
      bar: "bg-violet-400",
    },
    metrics: [["140", "Managed units"], ["99%", "Verified turns"], ["+$42K", "Upsell rev"]],
  },
];

export const phases = [
  {
    step: "01",
    title: "Capture",
    description: "Enquiries and referrals land in one pipeline with owners, values, and next actions.",
    icon: UsersRound,
  },
  {
    step: "02",
    title: "Plan",
    description: "Signed work becomes a structured project with phases, budgets, permits, and milestones.",
    icon: Ruler,
  },
  {
    step: "03",
    title: "Build",
    description: "Tasks, materials, inspections, and invoices flow through one shared operating rhythm.",
    icon: Hammer,
  },
  {
    step: "04",
    title: "Care & Verify",
    description: "Promote finished builds or onboard STR portfolios with automated turnovers and photo-verified checklists.",
    icon: Building2,
  },
  {
    step: "05",
    title: "Monetize & Grow",
    description: "Boost recurring service revenue through guest upsells, estate retainers, and margin-protected cost intelligence.",
    icon: Zap,
  },
];

export const plans = [
  {
    name: "Foundation",
    monthly: 299,
    description: "For small builders and boutique hosts replacing spreadsheets.",
    features: ["Branded subdomain", "Up to 5 team members", "CRM + project workflows", "Property care checklists", "Core dashboards & support"],
  },
  {
    name: "Builder & Hospitality",
    monthly: 699,
    description: "For growing builders and STR operators automating operations & revenue.",
    features: ["Custom domain + subdomain", "Up to 20 team members", "Invoice & turnover automation", "R2 photo proof & guest upsells", "PMS sync & review queues"],
    featured: true,
  },
  {
    name: "Enterprise",
    monthly: null,
    description: "For multi-division builders and large property managers with custom scale.",
    features: ["Multiple business units", "Unlimited team members & units", "Custom n8n & PMS workflows", "BYOC payment & AI vault", "Dedicated success lead"],
  },
];

export const faqs = [
  {
    question: "Who is BeamLine built for?",
    answer:
      "Custom home builders, design-build firms, luxury estate managers, and short-term rental or hospitality operators who want one platform for sales, construction delivery, verified property care, and service revenue.",
  },
  {
    question: "How does the Property Operations & Experience platform work?",
    answer:
      "You can promote completed construction builds into managed properties in one click or onboard standalone rental units. BeamLine auto-schedules turnovers from bookings, enforces room-by-room R2 photo checklists, escalates defects into repair tasks and costs, and monetizes guest add-ons like early check-in or pool heating.",
  },
  {
    question: "What does multi-tenant mean for my company?",
    answer:
      "Your company gets its own isolated workspace — users, records, branding, and settings are separate from every other business on the platform.",
  },
  {
    question: "How does the custom subdomain work?",
    answer:
      "Each workspace launches at an address like yourcompany.beamline.app. Builder and Enterprise plans can also connect a domain you already own.",
  },
  {
    question: "Can we bring our existing data?",
    answer:
      "Yes. Onboarding includes structured imports from spreadsheets and common CRM exports, plus a review so active opportunities and projects are ready on day one.",
  },
  {
    question: "Does my field team need training?",
    answer:
      "Very little. BeamLine is organized around familiar construction stages and clear next actions, so a short role-based walkthrough is usually enough.",
  },
  {
    question: "Can we cancel or change plans?",
    answer:
      "Plans can be upgraded at any time. Monthly plans can be cancelled at the end of a billing period, and annual plans renew yearly.",
  },
];
