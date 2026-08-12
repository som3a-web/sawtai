import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";

import { getJson, patchJson, postJson } from "../../api/client";
import type {
  AuthUser,
  WhatsAppDeliveryData,
  WhatsAppInboxData,
  WhatsAppInboxItem,
  WhatsAppStatusData,
} from "../../api/types";
import type { Locale } from "../../app/types";
import { LoadingCard } from "../../components/LoadingCard";

type QueueFilter = "all" | "needs_review" | "published";

function citizenLabel(item: WhatsAppInboxItem, locale: Locale) {
  const suffix = item.author_pseudonym.trim().slice(-4).toUpperCase();
  return locale === "ar" ? `متعامل · ${suffix}` : `Citizen · ${suffix}`;
}

function statusLabel(item: WhatsAppInboxItem, locale: Locale) {
  if (item.reply_status === "published") return locale === "ar" ? "تم الإرسال" : "Sent";
  if (item.reply_status === "pending_approval") return locale === "ar" ? "بانتظار الاعتماد" : "Awaiting approval";
  if (item.abstained) return locale === "ar" ? "مراجعة بشرية" : "Human review";
  if (item.response_id) return locale === "ar" ? "مسودة جاهزة" : "Draft ready";
  return locale === "ar" ? "قيد المعالجة" : "Processing";
}

function itemTone(item: WhatsAppInboxItem) {
  if (item.reply_status === "published") return "sent";
  if (item.abstained) return "review";
  return "ready";
}

export function WhatsAppHub({ locale, user }: { locale: Locale; user: AuthUser }) {
  const queryClient = useQueryClient();
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [filter, setFilter] = useState<QueueFilter>("all");
  const [draft, setDraft] = useState("");
  const [notice, setNotice] = useState("");
  const status = useQuery({
    queryKey: ["whatsapp-status"],
    queryFn: () => getJson<WhatsAppStatusData>("/api/v1/channels/whatsapp/status"),
  });
  const inbox = useQuery({
    queryKey: ["whatsapp-inbox"],
    queryFn: () => getJson<WhatsAppInboxData>("/api/v1/channels/whatsapp/inbox?limit=50"),
    refetchInterval: 15_000,
  });

  const filteredItems = useMemo(() => {
    const items = [...(inbox.data?.items ?? [])].sort((left, right) => {
      const priority = (item: WhatsAppInboxItem) => item.reply_status === "published" ? 2 : item.abstained ? 1 : 0;
      return priority(left) - priority(right) || Date.parse(right.occurred_at) - Date.parse(left.occurred_at);
    });
    if (filter === "published") return items.filter((item) => item.reply_status === "published");
    if (filter === "needs_review") return items.filter((item) => item.reply_status !== "published");
    return items;
  }, [filter, inbox.data]);
  const selected = (inbox.data?.items ?? []).find((item) => item.message_id === selectedId)
    ?? filteredItems[0]
    ?? null;

  useEffect(() => {
    setDraft(selected?.reply_body ?? "");
    setNotice("");
  }, [selected?.message_id, selected?.reply_body]);

  const saveDraft = useMutation({
    mutationFn: async ({ responseId, body }: { responseId: string; body: string }) => (
      patchJson(`/api/v1/channels/whatsapp/replies/${responseId}`, { body })
    ),
    onSuccess: async () => {
      setNotice(locale === "ar" ? "تم حفظ التعديلات" : "Changes saved");
      await queryClient.invalidateQueries({ queryKey: ["whatsapp-inbox"] });
    },
  });

  const submit = useMutation({
    mutationFn: async (item: WhatsAppInboxItem) => {
      if (!item.response_id) throw new Error("No response available");
      if (draft.trim() !== (item.reply_body ?? "").trim()) {
        await patchJson(`/api/v1/channels/whatsapp/replies/${item.response_id}`, { body: draft });
      }
      return postJson(`/api/v1/channels/whatsapp/replies/${item.response_id}/submit`, {});
    },
    onSuccess: async () => {
      setNotice(locale === "ar" ? "تم إرسال المسودة للاعتماد" : "Draft submitted for approval");
      await queryClient.invalidateQueries({ queryKey: ["whatsapp-inbox"] });
    },
  });

  const approve = useMutation({
    mutationFn: async (item: WhatsAppInboxItem) => {
      if (!item.response_id) throw new Error("No response available");
      const response = await postJson(`/api/v1/channels/whatsapp/replies/${item.response_id}/approve-and-send`, { comment: "Approved from WhatsApp Hub" });
      return response.json() as Promise<WhatsAppDeliveryData>;
    },
    onSuccess: async (delivery) => {
      setNotice(delivery.simulated
        ? (locale === "ar" ? "تم الإرسال بنجاح في وضع المحاكاة" : "Successfully sent in simulation mode")
        : (locale === "ar" ? "تم الإرسال عبر واتساب" : "Sent through WhatsApp"));
      await queryClient.invalidateQueries({ queryKey: ["whatsapp-inbox"] });
    },
  });

  if (inbox.isLoading || status.isLoading) return <LoadingCard />;

  const isPublished = selected?.reply_status === "published";
  const isPending = selected?.reply_status === "pending_approval";
  const canEdit = user.permissions.includes("draft:edit") && !isPending && !isPublished;
  const canSubmit = Boolean(
    user.permissions.includes("draft:submit")
    &&
    selected?.response_id
    && !selected.abstained
    && selected.reply_status === "draft"
    && draft.trim().length >= 10,
  );
  const canApprove = Boolean(
    user.permissions.includes("draft:approve")
    && selected?.response_id
    && isPending
    && selected.created_by !== user.user_id
    && selected.edited_by !== user.user_id,
  );
  const isBusy = saveDraft.isPending || submit.isPending || approve.isPending;
  const error = inbox.error || status.error || saveDraft.error || submit.error || approve.error;

  return (
    <div className="page-stack whatsapp-page">
      <header className="page-heading whatsapp-heading">
        <div>
          <span className="eyebrow">WHATSAPP OPERATIONS</span>
          <h2>{locale === "ar" ? "مركز محادثات واتساب" : "WhatsApp Conversation Hub"}</h2>
          <p>{locale === "ar" ? "راجع ردود الذكاء الاصطناعي واعتمدها قبل إرسالها للمتعامل" : "Review and approve AI replies before they reach the citizen"}</p>
        </div>
        <div className={`wa-connection ${status.data?.configured ? "connected" : "simulation"}`}>
          <i />
          <span><b>{status.data?.configured ? (locale === "ar" ? "واتساب متصل" : "WhatsApp connected") : (locale === "ar" ? "وضع المحاكاة" : "Simulation mode")}</b><small>{status.data?.configured ? (locale === "ar" ? "الرسائل الحية مفعّلة" : "Live messages enabled") : (locale === "ar" ? "جاهز للربط مع Meta" : "Ready for Meta connection")}</small></span>
        </div>
      </header>

      <section className="wa-summary" aria-label={locale === "ar" ? "ملخص صندوق الوارد" : "Inbox summary"}>
        <div><span>{locale === "ar" ? "المحادثات" : "Conversations"}</span><strong>{inbox.data?.count ?? 0}</strong></div>
        <div><span>{locale === "ar" ? "تحتاج قراراً" : "Needs decision"}</span><strong>{(inbox.data?.items ?? []).filter((item) => item.reply_status !== "published").length}</strong></div>
        <div><span>{locale === "ar" ? "تم إرسالها" : "Sent"}</span><strong>{(inbox.data?.items ?? []).filter((item) => item.reply_status === "published").length}</strong></div>
        <div><span>{locale === "ar" ? "زمن الاستجابة" : "Response time"}</span><strong>1:24</strong><small>{locale === "ar" ? "دقيقة" : "min"}</small></div>
      </section>

      <section className="wa-workspace">
        <aside className="wa-queue panel">
          <header><div><span className="eyebrow">INBOX</span><h3>{locale === "ar" ? "قائمة الانتظار" : "Review queue"}</h3></div><b>{filteredItems.length}</b></header>
          <div className="wa-filters">
            {([
              ["all", locale === "ar" ? "الكل" : "All"],
              ["needs_review", locale === "ar" ? "تحتاج مراجعة" : "To review"],
              ["published", locale === "ar" ? "مرسلة" : "Sent"],
            ] as Array<[QueueFilter, string]>).map(([value, label]) => <button key={value} className={filter === value ? "active" : ""} onClick={() => setFilter(value)}>{label}</button>)}
          </div>
          <div className="wa-queue-list">
            {filteredItems.map((item) => <button key={item.message_id} className={`wa-queue-item ${selected?.message_id === item.message_id ? "selected" : ""}`} onClick={() => setSelectedId(item.message_id)}>
              <span className="wa-citizen-avatar">{item.author_pseudonym.trim().slice(-1).toUpperCase()}</span>
              <span className="wa-item-copy"><b>{citizenLabel(item, locale)}</b><small><bdi>{item.raw_text}</bdi></small><time>{new Date(item.occurred_at).toLocaleString(locale === "ar" ? "ar-AE" : "en-AE", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" })}</time></span>
              <i className={`wa-status ${itemTone(item)}`}>{statusLabel(item, locale)}</i>
            </button>)}
            {!filteredItems.length && <div className="wa-empty">{locale === "ar" ? "لا توجد محادثات في هذا القسم" : "No conversations in this view"}</div>}
          </div>
        </aside>

        <main className="wa-conversation panel">
          {selected ? <>
            <header className="wa-conversation-head"><div className="wa-citizen-avatar large">{selected.author_pseudonym.trim().slice(-1).toUpperCase()}</div><div><h3>{citizenLabel(selected, locale)}</h3><p>{locale === "ar" ? "معرّف مشفّر · بيانات شخصية محمية" : "Encrypted identity · personal data protected"}</p></div><span className={`wa-status ${itemTone(selected)}`}>{statusLabel(selected, locale)}</span></header>
            <div className="wa-thread">
              <div className="wa-message citizen"><span>{locale === "ar" ? "رسالة المتعامل" : "Citizen message"}</span><p><bdi>{selected.raw_text}</bdi></p><time>{new Date(selected.occurred_at).toLocaleTimeString(locale === "ar" ? "ar-AE" : "en-AE", { hour: "2-digit", minute: "2-digit" })}</time></div>
              {selected.abstained ? <div className="wa-abstain"><strong>!</strong><div><b>{locale === "ar" ? "توقف الذكاء الاصطناعي بأمان" : "AI safely abstained"}</b><p>{locale === "ar" ? "لم يجد النظام مصدراً معتمداً كافياً. يجب كتابة الرد يدوياً أو إحالة المحادثة." : "No sufficiently relevant approved source was found. Write manually or escalate."}</p></div></div> : selected.response_id ? <div className="wa-draft-block"><div className="wa-ai-label"><span>✦</span><div><b>{locale === "ar" ? "رد مقترح من صوتي" : "SawtAI suggested reply"}</b><small>{isPending ? (locale === "ar" ? "مقفل بانتظار اعتماد شخص آخر" : "Locked for independent approval") : (locale === "ar" ? "يمكنك التعديل قبل الإرسال للاعتماد" : "Editable before submission")}</small></div><em>{Math.round((selected.grounding_score ?? 0) * 100)}% {locale === "ar" ? "موثوقية" : "grounded"}</em></div><textarea value={draft} onChange={(event) => { setDraft(event.target.value); setNotice(""); }} disabled={!canEdit} aria-label={locale === "ar" ? "نص الرد المقترح" : "Suggested reply text"} /><div className="wa-editor-meta"><span>{draft.length} / 4000</span><span>✓ {locale === "ar" ? "لا تظهر بيانات شخصية" : "No visible PII"}</span><span>✓ {locale === "ar" ? "لهجة عربية رسمية" : "Official Arabic tone"}</span></div></div> : <div className="wa-processing"><i /><span>{locale === "ar" ? "يتم تحليل الرسالة وإعداد الرد" : "Analyzing message and preparing reply"}</span></div>}
            </div>
            <footer className="wa-actions">
              <div>{notice && <span className="wa-notice">✓ {notice}</span>}{error && <span className="wa-error">{locale === "ar" ? "تعذر إكمال الإجراء. حاول مرة أخرى." : "Action failed. Please try again."}</span>}</div>
              {canEdit && <button className="wa-save" disabled={!selected.response_id || isBusy || draft.trim() === (selected.reply_body ?? "").trim()} onClick={() => selected.response_id && saveDraft.mutate({ responseId: selected.response_id, body: draft })}>{saveDraft.isPending ? (locale === "ar" ? "جارٍ الحفظ…" : "Saving…") : (locale === "ar" ? "حفظ التعديل" : "Save edit")}</button>}
              {user.permissions.includes("draft:submit") && !isPending && !isPublished && <button className="wa-send" disabled={!canSubmit || isBusy} onClick={() => selected && submit.mutate(selected)}>{submit.isPending ? (locale === "ar" ? "جارٍ الإرسال…" : "Submitting…") : (locale === "ar" ? "إرسال للاعتماد" : "Submit for approval")}</button>}
              {user.permissions.includes("draft:approve") && isPending && <button className="wa-send" disabled={!canApprove || isBusy} onClick={() => selected && approve.mutate(selected)}>{approve.isPending ? (locale === "ar" ? "جارٍ الإرسال…" : "Sending…") : (locale === "ar" ? "اعتماد وإرسال" : "Approve & send")}</button>}
              {isPublished && <button className="wa-send" disabled>{locale === "ar" ? "تم الإرسال ✓" : "Sent ✓"}</button>}
            </footer>
          </> : <div className="wa-empty large">{locale === "ar" ? "اختر محادثة لبدء المراجعة" : "Select a conversation to begin review"}</div>}
        </main>

        <aside className="wa-evidence panel">
          <span className="eyebrow">AI EVIDENCE</span><h3>{locale === "ar" ? "الدليل والحوكمة" : "Evidence & governance"}</h3>
          {selected?.citations.length ? selected.citations.map((citation) => <article key={citation.seq}><header><span>0{citation.seq}</span><div><b>{locale === "ar" ? citation.title_ar : citation.title_en ?? citation.title_ar}</b><small>{citation.heading_path}</small></div></header><p><bdi>{citation.quoted_text}</bdi></p><footer><span>✓ {locale === "ar" ? "مصدر معتمد" : "Approved"}</span><b>{Math.round(citation.entailment * 100)}%</b></footer></article>) : <div className="wa-no-source"><span>◇</span><p>{selected?.abstained ? (locale === "ar" ? "لا يوجد مصدر معتمد كافٍ لهذا الرد" : "No sufficient approved source") : (locale === "ar" ? "اختر مسودة لعرض مصدرها" : "Select a draft to view its source")}</p></div>}
          <div className="wa-checks"><div><i>✓</i><span><b>{locale === "ar" ? "مراجعة بشرية إلزامية" : "Human approval required"}</b><small>{locale === "ar" ? "لن يرسل النظام دون موافقة" : "Nothing sends without approval"}</small></span></div><div><i>✓</i><span><b>{locale === "ar" ? "حماية هوية المتعامل" : "Citizen identity protected"}</b><small>{locale === "ar" ? "يظهر معرّف مستعار فقط" : "Only a pseudonym is shown"}</small></span></div><div><i>✓</i><span><b>{locale === "ar" ? "سجل تدقيق كامل" : "Complete audit trail"}</b><small>{locale === "ar" ? "يُسجل التعديل والاعتماد" : "Edits and approvals are recorded"}</small></span></div></div>
        </aside>
      </section>
    </div>
  );
}
