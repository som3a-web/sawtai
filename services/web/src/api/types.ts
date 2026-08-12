import type { Page } from "../app/types";

export interface OverviewData {
  window: { from: string; to: string };
  kpis: {
    total_messages: number;
    delta_pct: number;
    csat_index: { value: number; delta: number; sample_n: number };
    sentiment: { negative: number; neutral: number; positive: number; abstained: number };
    open_cases: number;
    sla_breach_rate: number;
    active_alerts: Record<string, number>;
  };
  by_channel: Array<{ code: string; name_ar: string; name_en: string; count: number; mean_sentiment: number }>;
  top_topics: Array<{ topic_id: string; label_ar: string; label_en: string; count: number; mean_sentiment: number; risk_score: number; is_emerging: boolean }>;
  provenance: string;
}

export interface TimeseriesData {
  series: Array<{ bucket: string; volume: number; sentiment: number }>;
}

export interface MessageItem {
  message_id: string;
  occurred_at: string;
  channel: { code: string; name_ar: string };
  text: string;
  lang_primary: string;
  dialect: string;
  sentiment: { label: string; score: number; confidence: number; model: string; version: string };
  classification: { node_code: string; label_ar: string; confidence: number };
  topics: Array<{ topic_id: string; label_ar: string; similarity: number }>;
  engagement: Record<string, number>;
  pii_redacted: Array<{ type: string; count: number }>;
}

export interface MessagesData {
  items: MessageItem[];
  total_estimate: number;
  provenance: string;
}

export interface AlertItem {
  alert_id: string;
  tier: string;
  risk_score: number;
  drivers: Array<{ feature: string; value: number; contribution: number }>;
  title_ar: string;
  title_en: string;
  topic_label_ar: string;
  topic_label_en: string;
  playbook_title_ar: string;
  playbook_steps: Array<{ seq: number; action_ar: string; owner_role: string }>;
}

export interface AlertsData {
  items: AlertItem[];
}

export interface ReplayPoint {
  t: string;
  msg_count: number;
  neg_share: number;
  risk_score: number;
  tier: string | null;
}

export interface ReplayData {
  label_ar: string;
  label_en: string;
  series: ReplayPoint[];
  lead_time_hours: number;
  method: string;
}

export interface DataTableSummary {
  name: string;
  schema: string;
  label_ar: string;
  label_en: string;
  description_ar: string;
  description_en: string;
  row_count: number;
}

export interface DataTablesData {
  database: string;
  schema: string;
  mode: string;
  items: DataTableSummary[];
}

export interface DataRowsData {
  name: string;
  label_ar: string;
  label_en: string;
  columns: string[];
  rows: Array<Record<string, unknown>>;
  mode: string;
}

export interface WhatsAppStatusData {
  tenant_id: string;
  configured: boolean;
  signature_required: boolean;
  delivery_mode: "simulate" | "live";
  reply_mode: "off" | "acknowledge" | "draft";
  voice_ready: boolean;
}

export interface WhatsAppCitation {
  seq: number;
  title_ar: string;
  title_en: string | null;
  heading_path: string | null;
  quoted_text: string;
  entailment: number;
}

export interface WhatsAppInboxItem {
  message_id: string;
  external_id: string;
  occurred_at: string;
  raw_text: string;
  author_pseudonym: string;
  lang_primary: string;
  enrichment_state: number;
  response_id: string | null;
  reply_body: string | null;
  reply_status: "draft" | "pending_approval" | "approved" | "rejected" | "published" | "withdrawn" | null;
  grounding_score: number | null;
  abstained: boolean | null;
  abstain_reason: string | null;
  policy_flags: string[] | null;
  published_ref: string | null;
  reply_created_at: string | null;
  created_by: string | null;
  edited_by: string | null;
  submitted_at: string | null;
  case_id: string | null;
  case_reference: string | null;
  citations: WhatsAppCitation[];
}

export interface WhatsAppInboxData {
  items: WhatsAppInboxItem[];
  count: number;
}

export interface WhatsAppDeliveryData {
  response_id: string;
  status: string;
  published_ref: string;
  simulated: boolean;
}

export interface AuthUser {
  user_id: string;
  tenant_id: string;
  email: string;
  display_name_ar: string;
  display_name_en: string;
  org_unit_id: string | null;
  roles: string[];
  permissions: string[];
  mfa_enrolled: boolean;
}

export interface AuthResponse {
  access_token: string;
  token_type: "bearer";
  expires_in: number;
  user: AuthUser;
}

export interface UserRecord {
  user_id: string;
  email: string;
  display_name_ar: string;
  display_name_en: string;
  org_unit_id: string | null;
  is_active: boolean;
  mfa_enrolled: boolean;
  last_login_at: string | null;
  roles: string[];
}

export interface RoleRecord {
  role_id: string;
  code: string;
  name_ar: string;
  name_en: string;
  permissions: string[];
}

export type CaseStatus = "new" | "triaged" | "assigned" | "awaiting_response" | "responded" | "resolved" | "closed" | "rejected";
export type CaseSeverity = "low" | "medium" | "high" | "critical";
export type SlaState = "on_track" | "due_soon" | "breached" | "completed" | "not_set";

export interface CaseItem {
  case_id: string;
  reference: string;
  title_ar: string;
  title_en: string;
  status: CaseStatus;
  severity: CaseSeverity;
  sla_due_at: string | null;
  sla_state: SlaState;
  sla_remaining_seconds: number | null;
  first_response_at: string | null;
  resolved_at: string | null;
  complaint_count: number;
  created_at: string;
  updated_at: string;
  node_id: string | null;
  taxonomy_code: string | null;
  taxonomy_label_ar: string | null;
  taxonomy_label_en: string | null;
  sla_hours: number | null;
  org_name_ar: string | null;
  org_name_en: string | null;
  assigned_to: string | null;
  assignee_name_ar: string | null;
  assignee_name_en: string | null;
}

export interface CaseListData {
  items: CaseItem[];
  summary: { total: number; open: number; breached: number; unassigned: number; critical: number };
}

export interface CaseHistoryItem {
  audit_id: string;
  occurred_at: string;
  action: string;
  outcome: string;
  before_state: Record<string, unknown> | null;
  after_state: Record<string, unknown> | null;
  actor_name_ar: string | null;
  actor_name_en: string | null;
}

export interface CaseDetail extends CaseItem {
  history: CaseHistoryItem[];
  responses: Array<{ response_id: string; kind: string; status: string; body: string; grounding_score: number | null; created_at: string; approved_at: string | null; published_at: string | null }>;
  allowed_transitions: CaseStatus[];
}

export interface CaseMetadata {
  taxonomy: Array<{ node_id: string; code: string; label_ar: string; label_en: string; sla_hours: number | null }>;
  assignees: Array<{ user_id: string; display_name_ar: string; display_name_en: string; roles: string[] }>;
}

export interface NotificationItem {
  notification_id: string;
  occurred_at: string;
  is_read: boolean;
  recipient_user_id: string;
  kind: "case_assigned" | "case_unassigned" | "sla_due_soon" | "sla_breached" | "case_critical" | "customer_waiting" | "draft_approval";
  level: "info" | "warning" | "critical" | "action";
  title_ar: string;
  title_en: string;
  body_ar: string;
  body_en: string;
  target_type: "case" | "response";
  target_id: string;
  target_page: Page;
  reference: string | null;
}

export interface NotificationsData {
  items: NotificationItem[];
  unread: number;
  count: number;
}

export type DocumentKind = "policy" | "press_release" | "faq" | "tone_of_voice" | "service_guide" | "legal" | "template";

export interface KnowledgeDocument {
  document_id: string;
  kind: DocumentKind;
  title_ar: string;
  title_en: string | null;
  lang: "ar" | "en" | "mixed";
  version: string;
  effective_from: string | null;
  effective_to: string | null;
  is_approved: boolean;
  is_retrievable: boolean;
  is_retired: boolean;
  approved_by: string | null;
  object_key: string;
  created_at: string;
  chunk_count: number;
  citation_count: number;
  created_by: string | null;
  creator_name_ar: string | null;
  creator_name_en: string | null;
  approver_name_ar: string | null;
  approver_name_en: string | null;
  ingestion_status: "processing" | "indexed" | "failed";
  extraction_method: string | null;
  embedding_provider: string | null;
  storage_backend: string | null;
  ingestion_error: string | null;
}

export interface KnowledgeListData {
  items: KnowledgeDocument[];
  summary: { total: number; approved: number; pending: number; retired: number; chunks: number };
}

export interface KnowledgeDetail extends KnowledgeDocument {
  sha256: string;
  org_unit_id: string | null;
  chunks: Array<{ chunk_id: string; seq: number; heading_path: string | null; text: string; token_count: number; lang: string }>;
  history: Array<{ audit_id: string; occurred_at: string; action: string; outcome: string; before_state: Record<string, unknown> | null; after_state: Record<string, unknown> | null; actor_name_ar: string | null; actor_name_en: string | null }>;
}

export interface KnowledgeSearchData {
  retrieval_run_id: string;
  tenant_id: string;
  gate: { passed: boolean; top_score: number; threshold: number; mode: string };
  results: Array<{
    chunk_id: string;
    document: { document_id: string; title_ar: string; title_en: string | null };
    heading_path: string | null;
    text: string;
    scores: { dense: number; sparse: number; rerank: number; retrieval: number };
    models: { embedding: string; reranker: string };
  }>;
}
