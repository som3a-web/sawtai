import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";

import { getJson, patchJson, postJson } from "../../api/client";
import type {
  AuthUser,
  CaseDetail,
  CaseItem,
  CaseListData,
  CaseMetadata,
  CaseSeverity,
  CaseStatus,
} from "../../api/types";
import type { Locale } from "../../app/types";
import { LoadingCard } from "../../components/LoadingCard";

const statuses: CaseStatus[] = ["new", "triaged", "assigned", "awaiting_response", "responded", "resolved", "closed", "rejected"];
const severities: CaseSeverity[] = ["low", "medium", "high", "critical"];

const labels = {
  ar: {
    new: "جديدة", triaged: "تم الفرز", assigned: "مسندة", awaiting_response: "بانتظار الرد",
    responded: "تم الرد", resolved: "تم الحل", closed: "مغلقة", rejected: "مرفوضة",
    low: "منخفضة", medium: "متوسطة", high: "عالية", critical: "حرجة",
  },
  en: {
    new: "New", triaged: "Triaged", assigned: "Assigned", awaiting_response: "Awaiting response",
    responded: "Responded", resolved: "Resolved", closed: "Closed", rejected: "Rejected",
    low: "Low", medium: "Medium", high: "High", critical: "Critical",
  },
} as const;

function slaText(item: CaseItem, locale: Locale) {
  if (item.sla_state === "completed") return locale === "ar" ? "اكتملت الساعة" : "SLA completed";
  if (item.sla_state === "not_set" || item.sla_remaining_seconds === null) return locale === "ar" ? "بلا ساعة خدمة" : "No SLA";
  const totalMinutes = Math.round(Math.abs(item.sla_remaining_seconds) / 60);
  const hours = Math.floor(totalMinutes / 60);
  const minutes = totalMinutes % 60;
  const duration = hours ? `${hours}${locale === "ar" ? "س" : "h"} ${minutes}${locale === "ar" ? "د" : "m"}` : `${minutes}${locale === "ar" ? "د" : "m"}`;
  if (item.sla_state === "breached") return locale === "ar" ? `متأخرة ${duration}` : `${duration} overdue`;
  return locale === "ar" ? `متبقي ${duration}` : `${duration} remaining`;
}

function actionLabel(action: string, locale: Locale) {
  const map: Record<string, [string, string]> = {
    "case.create": ["تم إنشاء الحالة", "Case created"],
    "case.update": ["تم تحديث التفاصيل", "Details updated"],
    "case.assign": ["تم تغيير المسؤول", "Assignee changed"],
    "case.status": ["تم تغيير الحالة", "Status changed"],
    "case.note": ["ملاحظة داخلية", "Internal note"],
    "case.escalate": ["تم التصعيد", "Case escalated"],
  };
  return map[action]?.[locale === "ar" ? 0 : 1] ?? action;
}

export function CaseWorkspace({ locale, user }: { locale: Locale; user: AuthUser }) {
  const queryClient = useQueryClient();
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [statusFilter, setStatusFilter] = useState<CaseStatus | "">("");
  const [severityFilter, setSeverityFilter] = useState<CaseSeverity | "">("");
  const [search, setSearch] = useState("");
  const [note, setNote] = useState("");
  const [showCreate, setShowCreate] = useState(false);
  const [notice, setNotice] = useState("");
  const [createForm, setCreateForm] = useState({ title_ar: "", title_en: "", node_id: "", severity: "medium" as CaseSeverity });
  const canWrite = user.permissions.includes("case:write");
  const query = new URLSearchParams();
  if (statusFilter) query.set("status", statusFilter);
  if (severityFilter) query.set("severity", severityFilter);
  if (search.trim()) query.set("search", search.trim());

  const cases = useQuery({ queryKey: ["cases", statusFilter, severityFilter, search], queryFn: () => getJson<CaseListData>(`/api/v1/cases?${query}`) });
  const metadata = useQuery({ queryKey: ["case-metadata"], queryFn: () => getJson<CaseMetadata>("/api/v1/cases/metadata") });
  const selected = selectedId ?? cases.data?.items[0]?.case_id ?? null;
  const detail = useQuery({ queryKey: ["case", selected], queryFn: () => getJson<CaseDetail>(`/api/v1/cases/${selected}`), enabled: Boolean(selected) });

  useEffect(() => { setNotice(""); setNote(""); }, [selected]);
  const refresh = async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ["cases"] }),
      queryClient.invalidateQueries({ queryKey: ["case"] }),
    ]);
  };
  const assign = useMutation({ mutationFn: (assignedTo: string) => postJson(`/api/v1/cases/${selected}/assign`, { assigned_to: assignedTo }), onSuccess: async () => { setNotice(locale === "ar" ? "تم تحديث المسؤول" : "Assignee updated"); await refresh(); } });
  const transition = useMutation({ mutationFn: (status: CaseStatus) => postJson(`/api/v1/cases/${selected}/status`, { status }), onSuccess: async () => { setNotice(locale === "ar" ? "تم تحديث مسار الحالة" : "Case status updated"); await refresh(); } });
  const addNote = useMutation({ mutationFn: () => postJson(`/api/v1/cases/${selected}/notes`, { note }), onSuccess: async () => { setNote(""); setNotice(locale === "ar" ? "تمت إضافة الملاحظة" : "Note added"); await refresh(); } });
  const escalate = useMutation({ mutationFn: () => postJson(`/api/v1/cases/${selected}/escalate`, { reason: locale === "ar" ? "تصعيد تشغيلي من مساحة الحالات" : "Operational escalation from case workspace" }), onSuccess: async () => { setNotice(locale === "ar" ? "تم تصعيد الحالة كحالة حرجة" : "Case escalated to critical"); await refresh(); } });
  const updateSeverity = useMutation({ mutationFn: (severity: CaseSeverity) => patchJson(`/api/v1/cases/${selected}`, { severity }), onSuccess: refresh });
  const create = useMutation({
    mutationFn: async () => {
      const response = await postJson("/api/v1/cases", { ...createForm, node_id: createForm.node_id || null });
      return response.json() as Promise<{ case_id: string }>;
    },
    onSuccess: async (created) => {
      setShowCreate(false); setCreateForm({ title_ar: "", title_en: "", node_id: "", severity: "medium" });
      await refresh(); setSelectedId(created.case_id); setNotice(locale === "ar" ? "تم إنشاء الحالة وتفعيل ساعة الخدمة" : "Case created and SLA clock started");
    },
  });

  const error = cases.error || metadata.error || detail.error || assign.error || transition.error || addNote.error || escalate.error || updateSeverity.error || create.error;
  const item = detail.data;
  const busy = assign.isPending || transition.isPending || addNote.isPending || escalate.isPending || updateSeverity.isPending;
  const summary = cases.data?.summary;
  const assignee = useMemo(() => metadata.data?.assignees.find((person) => person.user_id === item?.assigned_to), [item?.assigned_to, metadata.data]);

  if (cases.isLoading || metadata.isLoading) return <LoadingCard />;
  return <div className="page-stack cases-page">
    <header className="page-heading case-heading"><div><span className="eyebrow">SERVICE OPERATIONS</span><h2>{locale === "ar" ? "إدارة الحالات" : "Case Management"}</h2><p>{locale === "ar" ? "حوّل صوت المتعامل إلى مسؤولية واضحة، ساعة خدمة، وإجراء موثق." : "Turn citizen voice into clear ownership, an SLA clock, and auditable action."}</p></div>{canWrite && <button className="case-create-button" onClick={() => setShowCreate(!showCreate)}>＋ {locale === "ar" ? "حالة جديدة" : "New case"}</button>}</header>

    {showCreate && <form className="panel case-create-panel" onSubmit={(event) => { event.preventDefault(); create.mutate(); }}><header><div><span className="eyebrow">DETERMINISTIC ROUTING</span><h3>{locale === "ar" ? "إنشاء حالة وتشغيل SLA" : "Create case and start SLA"}</h3></div><button type="button" onClick={() => setShowCreate(false)}>×</button></header><div className="case-create-grid"><label><span>{locale === "ar" ? "العنوان بالعربية" : "Arabic title"}</span><input required minLength={3} value={createForm.title_ar} onChange={(event) => setCreateForm({ ...createForm, title_ar: event.target.value })} /></label><label><span>{locale === "ar" ? "العنوان بالإنجليزية" : "English title"}</span><input required minLength={3} value={createForm.title_en} onChange={(event) => setCreateForm({ ...createForm, title_en: event.target.value })} /></label><label><span>{locale === "ar" ? "تصنيف الخدمة" : "Service category"}</span><select required value={createForm.node_id} onChange={(event) => setCreateForm({ ...createForm, node_id: event.target.value })}><option value="">—</option>{metadata.data?.taxonomy.map((node) => <option key={node.node_id} value={node.node_id}>{locale === "ar" ? node.label_ar : node.label_en} · {node.sla_hours ?? "—"}h</option>)}</select></label><label><span>{locale === "ar" ? "الأولوية" : "Priority"}</span><select value={createForm.severity} onChange={(event) => setCreateForm({ ...createForm, severity: event.target.value as CaseSeverity })}>{severities.map((severity) => <option key={severity} value={severity}>{labels[locale][severity]}</option>)}</select></label></div><button className="login-submit" disabled={create.isPending}>{create.isPending ? (locale === "ar" ? "جارٍ الإنشاء…" : "Creating…") : (locale === "ar" ? "إنشاء وتوجيه الحالة" : "Create and route case")}</button></form>}

    <section className="case-summary" aria-label={locale === "ar" ? "ملخص الحالات" : "Case summary"}><div><span>{locale === "ar" ? "مفتوحة" : "Open"}</span><strong>{summary?.open ?? 0}</strong></div><div className="breached"><span>{locale === "ar" ? "متجاوزة SLA" : "SLA breached"}</span><strong>{summary?.breached ?? 0}</strong></div><div><span>{locale === "ar" ? "غير مسندة" : "Unassigned"}</span><strong>{summary?.unassigned ?? 0}</strong></div><div className="critical"><span>{locale === "ar" ? "حرجة" : "Critical"}</span><strong>{summary?.critical ?? 0}</strong></div></section>

    <section className="case-workspace">
      <aside className="panel case-queue"><header><div><span className="eyebrow">CASE QUEUE</span><h3>{locale === "ar" ? "قائمة العمل" : "Work queue"}</h3></div><b>{cases.data?.items.length ?? 0}</b></header><div className="case-filters"><input value={search} onChange={(event) => setSearch(event.target.value)} placeholder={locale === "ar" ? "بحث بالمرجع أو العنوان" : "Search reference or title"} /><select value={statusFilter} onChange={(event) => setStatusFilter(event.target.value as CaseStatus | "")}><option value="">{locale === "ar" ? "كل الحالات" : "All statuses"}</option>{statuses.map((status) => <option key={status} value={status}>{labels[locale][status]}</option>)}</select><select value={severityFilter} onChange={(event) => setSeverityFilter(event.target.value as CaseSeverity | "")}><option value="">{locale === "ar" ? "كل الأولويات" : "All priorities"}</option>{severities.map((severity) => <option key={severity} value={severity}>{labels[locale][severity]}</option>)}</select></div><div className="case-list">{cases.data?.items.map((caseItem) => <button key={caseItem.case_id} className={selected === caseItem.case_id ? "selected" : ""} onClick={() => setSelectedId(caseItem.case_id)}><div className="case-list-top"><span className={`case-severity ${caseItem.severity}`}>{labels[locale][caseItem.severity]}</span><time className={`case-sla ${caseItem.sla_state}`}>{slaText(caseItem, locale)}</time></div><b>{locale === "ar" ? caseItem.title_ar : caseItem.title_en}</b><small>{caseItem.reference} · {locale === "ar" ? caseItem.taxonomy_label_ar : caseItem.taxonomy_label_en}</small><footer><span>{locale === "ar" ? caseItem.assignee_name_ar ?? "غير مسندة" : caseItem.assignee_name_en ?? "Unassigned"}</span><i>{labels[locale][caseItem.status]}</i></footer></button>)}{!cases.data?.items.length && <div className="case-empty">{locale === "ar" ? "لا توجد حالات مطابقة" : "No matching cases"}</div>}</div></aside>

      <main className="panel case-detail">{detail.isLoading ? <LoadingCard /> : item ? <><header className="case-detail-head"><div><span className="eyebrow">{item.reference}</span><h3>{locale === "ar" ? item.title_ar : item.title_en}</h3><p>{locale === "ar" ? item.title_en : item.title_ar}</p></div><div className={`case-sla-clock ${item.sla_state}`}><small>SLA</small><b>{slaText(item, locale)}</b><span>{item.sla_due_at ? new Date(item.sla_due_at).toLocaleString(locale === "ar" ? "ar-AE" : "en-AE", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" }) : "—"}</span></div></header><div className="case-routing"><div><span>{locale === "ar" ? "تصنيف الخدمة" : "Service category"}</span><b>{locale === "ar" ? item.taxonomy_label_ar : item.taxonomy_label_en}</b><small>{item.taxonomy_code}</small></div><div><span>{locale === "ar" ? "الجهة المسؤولة" : "Owning unit"}</span><b>{locale === "ar" ? item.org_name_ar : item.org_name_en}</b><small>{locale === "ar" ? "توجيه حتمي من التصنيف" : "Deterministic taxonomy routing"}</small></div><div><span>{locale === "ar" ? "الشكاوى المرتبطة" : "Linked complaints"}</span><b>{item.complaint_count}</b><small>{locale === "ar" ? "رسالة موحدة في حالة واحدة" : "messages consolidated"}</small></div></div>
        <section className="case-controls"><div><label>{locale === "ar" ? "المسؤول" : "Assignee"}</label><select disabled={!canWrite || busy} value={item.assigned_to ?? ""} onChange={(event) => event.target.value && assign.mutate(event.target.value)}><option value="">{locale === "ar" ? "اختر مسؤولاً" : "Choose assignee"}</option>{metadata.data?.assignees.map((person) => <option key={person.user_id} value={person.user_id}>{locale === "ar" ? person.display_name_ar : person.display_name_en}</option>)}</select><small>{assignee?.roles.join(" · ")}</small></div><div><label>{locale === "ar" ? "الأولوية" : "Priority"}</label><select disabled={!canWrite || busy} value={item.severity} onChange={(event) => updateSeverity.mutate(event.target.value as CaseSeverity)}>{severities.map((severity) => <option key={severity} value={severity}>{labels[locale][severity]}</option>)}</select></div></section>
        <section className="case-progress"><span className="eyebrow">{locale === "ar" ? "الإجراء التالي المسموح" : "ALLOWED NEXT ACTION"}</span><div>{item.allowed_transitions.map((status) => <button key={status} disabled={!canWrite || busy} onClick={() => transition.mutate(status)}>{labels[locale][status]} <span>←</span></button>)}{!item.allowed_transitions.length && <small>{locale === "ar" ? "اكتمل مسار هذه الحالة" : "This case workflow is complete"}</small>}</div></section>
        <section className="case-note"><label>{locale === "ar" ? "ملاحظة داخلية" : "Internal note"}</label><textarea value={note} onChange={(event) => setNote(event.target.value)} placeholder={locale === "ar" ? "اكتب تحديثاً للفريق…" : "Write an update for the team…"} /><div><button disabled={!canWrite || note.trim().length < 2 || busy} onClick={() => addNote.mutate()}>{locale === "ar" ? "إضافة للسجل" : "Add to history"}</button><button className="case-escalate" disabled={!canWrite || item.severity === "critical" || busy} onClick={() => escalate.mutate()}>↑ {locale === "ar" ? "تصعيد كحالة حرجة" : "Escalate to critical"}</button></div></section>{notice && <div className="case-notice">✓ {notice}</div>}{error && <div className="login-error">{locale === "ar" ? "تعذر إكمال الإجراء" : "The action could not be completed"}</div>}</> : <div className="case-empty large">{locale === "ar" ? "اختر حالة" : "Select a case"}</div>}</main>

      <aside className="panel case-history"><span className="eyebrow">AUDITABLE HISTORY</span><h3>{locale === "ar" ? "سجل الحالة" : "Case history"}</h3>{item?.history.length ? <div className="case-timeline">{item.history.map((event) => <article key={event.audit_id}><i /><div><b>{actionLabel(event.action, locale)}</b><small>{locale === "ar" ? event.actor_name_ar ?? "النظام" : event.actor_name_en ?? "System"} · {new Date(event.occurred_at).toLocaleString(locale === "ar" ? "ar-AE" : "en-AE", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" })}</small>{typeof event.after_state?.note === "string" && <p>{event.after_state.note}</p>}{typeof event.after_state?.reason === "string" && <p>{event.after_state.reason}</p>}</div></article>)}</div> : <div className="case-empty">{locale === "ar" ? "ستظهر التغييرات والملاحظات هنا" : "Changes and notes will appear here"}</div>}<div className="case-governance"><span>✓</span><div><b>{locale === "ar" ? "سجل غير قابل للمحو" : "Append-only record"}</b><small>{locale === "ar" ? "كل إجراء مرتبط بالمستخدم والوقت" : "Every action is tied to user and time"}</small></div></div></aside>
    </section>
  </div>;
}
