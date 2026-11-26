export type ProjectStatus =
  | "draft"
  | "open"
  | "closed"
  | "under_evaluation"
  | "awarded"
  | "no_award"
  | "canceled"
  | "expired";
export type TenderType = "sealed" | "owner_visible";
export type OfferStatus = "submitted" | "approved" | "rejected" | "withdrawn";
export type VerificationStatus = "incomplete" | "pending_review" | "changes_requested" | "approved";
export type DocumentStatus = "not_submitted" | "pending" | "approved" | "rejected";

export interface Project {
  id: string;
  owner_id: string;
  title: string;
  address: string;
  description: string | null;
  trade: string | null;
  bid_deadline: string;
  status: ProjectStatus;
  tender_type: TenderType;
  tender_type_locked: boolean;
  is_suspended: boolean;
  created_at: string;
  offer_count: number;
  my_offer_status: OfferStatus | null;
}

export interface Drawing {
  id: string;
  file_name: string;
  uploaded_at: string;
  revision: number;
  is_current: boolean;
  url: string | null;
}

export interface ProjectDetail extends Project {
  drawings: Drawing[];
}

export interface Offer {
  id: string;
  project_id: string;
  contractor_id: string | null;
  amount: string | null;
  timeline_estimate: string | null;
  message: string | null;
  status: OfferStatus;
  is_suspended: boolean;
  revision: number;
  created_at: string;
  updated_at: string;
  contractor_company_name?: string | null;
  contractor_avg_rating?: string | null;
  contractor_review_count?: number | null;
  sealed: boolean;
  quotation?: { id: string; file_name: string } | null;
}

export interface OfferRevision {
  id: string;
  offer_id: string;
  revision_number: number;
  amount: string;
  timeline_estimate: string | null;
  message: string | null;
  status: OfferStatus;
  recorded_at: string;
}

export interface ContractorProfile {
  user_id: string;
  company_name: string;
  license_number: string | null;
  primary_trade: string | null;
  service_area: string | null;
  verification_status: VerificationStatus;
  is_suspended: boolean;
  avg_rating: string;
  review_count: number;
  paid_until: string | null;
  trial_until: string | null;
  payment_active: boolean;
  payment_override_active: boolean;
  marketplace_status:
    | "documents_incomplete"
    | "submitted_for_review"
    | "changes_requested"
    | "payment_required"
    | "verified_active"
    | "suspended";
  created_at: string;
  email?: string | null;
}

export interface DocumentRequirement {
  id: string;
  name: string;
  description: string | null;
  is_required: boolean;
  is_active: boolean;
  applies_to: "owner" | "contractor";
  effective_from: string;
  created_at: string;
}

export interface ContractorDocument {
  id: string;
  contractor_id: string;
  requirement_id: string;
  status: DocumentStatus;
  admin_note: string | null;
  reviewed_at: string | null;
  submitted_at: string | null;
  expires_on: string | null;
  requirement_name: string | null;
  requirement_description: string | null;
  requirement_is_required: boolean | null;
  requirement_effective_from: string | null;
}

export interface OwnerProfile {
  user_id: string;
  verification_status: VerificationStatus;
  is_suspended: boolean;
  marketplace_status: "documents_incomplete" | "submitted_for_review" | "changes_requested" | "verified_active" | "suspended";
  created_at: string;
  email?: string | null;
  full_name?: string | null;
  project_count: number;
}

export interface OwnerDocument {
  id: string;
  owner_id: string;
  requirement_id: string;
  status: DocumentStatus;
  admin_note: string | null;
  reviewed_at: string | null;
  submitted_at: string | null;
  expires_on: string | null;
  requirement_name: string | null;
  requirement_description: string | null;
  requirement_is_required: boolean | null;
  requirement_effective_from: string | null;
}

export interface AdminOffer {
  id: string;
  project_id: string;
  project_title: string;
  project_status: ProjectStatus;
  tender_type: TenderType;
  contractor_id: string | null;
  contractor_company_name: string | null;
  amount: string | null;
  timeline_estimate: string | null;
  message?: string | null;
  status: OfferStatus;
  is_suspended: boolean;
  revision: number;
  created_at: string;
  updated_at: string;
}

export interface AdminProject {
  id: string;
  owner_id: string;
  owner_name: string | null;
  owner_email: string | null;
  title: string;
  address: string;
  description: string | null;
  trade: string | null;
  bid_deadline: string;
  status: ProjectStatus;
  tender_type: TenderType;
  tender_type_locked: boolean;
  is_suspended: boolean;
  created_at: string;
  offer_count: number;
}

export interface AdminProjectDetail {
  project: AdminProject;
  offers: AdminOffer[];
}

export interface Clarification {
  id: string;
  project_id: string;
  // null when redacted for the owner on a still-sealed-and-open tender.
  contractor_id: string | null;
  question: string;
  answer: string | null;
  shared_with_all: boolean;
  created_at: string;
  answered_at: string | null;
  contractor_company_name: string | null;
}

export interface ProjectAmendment {
  id: string;
  project_id: string;
  amendment_number: number;
  summary: string;
  changed_fields: string;
  reason: string | null;
  deadline_extended: boolean;
  created_by: string;
  created_at: string;
}

export interface PaymentOverrideRecord {
  id: string;
  granted_by: string;
  reason: string;
  created_at: string;
  revoked_by: string | null;
  revoked_at: string | null;
}

export interface ContractorStatus {
  next_step: "details" | "subscribe" | "awaiting_activation" | "active" | "suspended";
  onboarding_complete: boolean;
  verification_status: VerificationStatus;
  is_suspended: boolean;
  paid_until: string | null;
  trial_until: string | null;
  trial_active: boolean;
  payment_active: boolean;
  activation_due_at: string | null;
  activation_overdue: boolean;
  active: boolean;
  can_bid: boolean;
  grace_days: number;
}

export interface BusinessDetails {
  business_name: string;
  business_address: string | null;
  website: string | null;
  business_email: string | null;
  business_registration_id: string | null;
  trades: string[];
  complete: boolean;
}

export interface SubscriptionPlanItem {
  id: string;
  name: string;
  description: string | null;
  activation_fee: string;
  monthly_fee: string;
  currency: string;
}

export interface PaymentInvoiceItem {
  id: string;
  kind: "activation" | "monthly";
  status: "pending" | "paid" | "canceled" | "expired";
  amount: string;
  currency: string;
  payment_url: string | null;
  covers_from: string | null;
  covers_until: string | null;
  paid_at: string | null;
  created_at: string;
}

export interface AdminPlan {
  id: string;
  name: string;
  description: string | null;
  activation_fee: string;
  monthly_fee: string;
  currency: string;
  is_active: boolean;
}

export interface SecretSetting {
  configured: boolean;
  hint: string | null;
  source: "admin" | "env" | "none";
}

export interface PlainSetting {
  value: string | null;
  source: "admin" | "env" | "none";
}

export interface BillingSettings {
  myfatoorah_api_key: SecretSetting;
  myfatoorah_webhook_secret: SecretSetting;
  myfatoorah_base_url: PlainSetting;
  whatsapp_otp_template: PlainSetting;
  payments_ready: boolean;
}

export interface ActivationRow {
  contractor_id: string;
  company_name: string;
  contact_name: string | null;
  email: string | null;
  phone: string | null;
  verification_status: VerificationStatus;
  payment_active: boolean;
  activation_due_at: string;
  hours_left: number;
  overdue: boolean;
}

export interface AdminUserRow {
  id: string;
  email: string | null;
  full_name: string | null;
  phone: string | null;
  role: "owner" | "contractor" | "admin";
  company_name: string | null;
  created_at: string | null;
  status: string;
  is_suspended: boolean;
}

export interface AdminUserList {
  items: AdminUserRow[];
  total: number;
  limit: number;
  offset: number;
}

export interface AdminUserDetail extends AdminUserRow {
  language: string;
  email_verified: boolean;
  can_log_in_with_password: boolean;
  contractor?: {
    verification_status: string;
    marketplace_status: string;
    payment_active: boolean;
    paid_until: string | null;
    trial_until: string | null;
    activation_due_at: string | null;
    payment_override_active: boolean;
  };
  owner?: { verification_status: string; marketplace_status: string; project_count: number };
  recent_activity: { action: string; previous_value: string | null; new_value: string | null; reason: string | null; created_at: string | null }[];
}

export interface ReportRows<T> {
  rows: T[];
  rows_total: number;
}

export interface ReportPeriod {
  period: { from: string; to: string };
}

export interface SummaryReport {
  generated_at: string;
  users: Record<string, number>;
  contractors: {
    total: number;
    by_status: Record<string, number>;
    active: number;
    paid: number;
    on_trial: number;
    waiting_activation: number;
    activation_overdue: number;
  };
  owners: { total: number; by_status: Record<string, number> };
  projects: { total: number; by_status: Record<string, number> };
  offers: { total: number; by_status: Record<string, number> };
  awards: { count: number; value: string };
}

export interface TenderRow {
  reference: string;
  title: string;
  trade: string;
  owner: string;
  status: string;
  tender_type: string;
  bid_deadline: string | null;
  offers: number;
  awarded_amount: string;
  created_at: string | null;
}

export interface TenderReport extends ReportPeriod, ReportRows<TenderRow> {
  summary: {
    projects_created: number;
    by_status: Record<string, number>;
    offers_received: number;
    awards: number;
    awarded_value: string;
  };
}

export interface BillingRow {
  paid_at: string | null;
  company: string;
  email: string;
  plan: string;
  kind: string;
  amount: string;
  currency: string;
  reference: string;
  myfatoorah_invoice_id: string | number;
}

export interface BillingReport extends ReportPeriod, ReportRows<BillingRow> {
  summary: {
    paid_count: number;
    totals: Record<string, string>;
    by_plan: { plan: string; count: number; totals: Record<string, string> }[];
    by_kind: { activation: number; monthly: number };
    invoices_created: number;
    still_pending: number;
    canceled_or_expired: number;
    paid_contractors_now: number;
    trials_now: number;
  };
}

export interface ActivationReportRow {
  company: string;
  contact: string;
  email: string;
  paid_at: string | null;
  activation_due_at: string | null;
  activated_at: string | null;
  hours_to_activate: number | "";
  status: "activated" | "waiting";
}

export interface ActivationReport extends ReportPeriod, ReportRows<ActivationReportRow> {
  summary: {
    first_payments: number;
    activated_within_sla: number;
    activated_late: number;
    still_waiting: number;
    average_hours_to_activate: number | null;
    queue_now: number;
    queue_overdue_now: number;
    activation_target_hours: number;
  };
}

export interface AuditLogEntry {
  id: string;
  actor_id: string | null;
  action: string;
  previous_value: string | null;
  new_value: string | null;
  reason: string | null;
  created_at: string;
}
