import { useState } from "react";

import { postJson } from "../../api/client";
import { parseSseBlock } from "../../api/sse";
import type { Locale } from "../../app/types";
import { copy } from "../../i18n/copy";

type DraftStatus = "idle" | "loading" | "done" | "abstained" | "error";
type DraftEventData = {
  delta?: string;
  top_score?: number;
  chunks?: Array<{ title_ar: string; heading_path: string | null; rerank_score: number }>;
  grounding_score?: number;
  policy_flags?: string[];
};

export function DraftStudio({ locale }: { locale: Locale }) {
  const t = copy[locale];
  const [instruction, setInstruction] = useState<string>(t.instruction);
  const [draft, setDraft] = useState("");
  const [status, setStatus] = useState<DraftStatus>("idle");
  const [retrieval, setRetrieval] = useState<DraftEventData | null>(null);
  const [verification, setVerification] = useState<DraftEventData | null>(null);

  const generate = async () => {
    setDraft("");
    setRetrieval(null);
    setVerification(null);
    setStatus("loading");
    try {
      const response = await postJson("/api/v1/drafts", {
        kind: "reply",
        case_id: "00000000-0000-0000-0000-000000000a01",
        lang: "ar",
        audience: "citizen",
        instruction,
      });
      const reader = response.body?.getReader();
      if (!reader) throw new Error("Streaming response is unavailable");
      const decoder = new TextDecoder();
      let buffer = "";
      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const blocks = buffer.split("\n\n");
        buffer = blocks.pop() ?? "";
        for (const block of blocks) {
          const event = parseSseBlock<DraftEventData>(block);
          if (event?.name === "retrieval") setRetrieval(event.data);
          if (event?.name === "token" && event.data.delta) setDraft((current) => current + event.data.delta);
          if (event?.name === "verification") setVerification(event.data);
          if (event?.name === "abstain") setStatus("abstained");
          if (event?.name === "done") setStatus("done");
        }
      }
    } catch {
      setStatus("error");
    }
  };

  return (
    <div className="page-stack">
      <header className="page-heading"><div><span className="eyebrow">GROUNDED COMMUNICATION</span><h2>{t.draft}</h2><p>{locale === "ar" ? "مسودة رسمية، موثقة، ولا تُنشر دون اعتماد بشري" : "Official drafts grounded in approved sources and human-approved"}</p></div><div className="case-chip">SHJ-2026-004182 · HIGH</div></header>
      <section className="studio-grid">
        <aside className="case-context panel"><span className="eyebrow">CASE CONTEXT</span><h3>{locale === "ar" ? "تأخر جمع النفايات" : "Delayed waste collection"}</h3><p>{locale === "ar" ? "47 شكوى مرتبطة · المنطقة الصناعية · مهلة الاستجابة 4 ساعات" : "47 linked complaints · Industrial Area · 4-hour SLA"}</p><div className="context-metric"><span>47</span><small>{locale === "ar" ? "شكوى" : "complaints"}</small></div><div className="context-metric"><span>-0.78</span><small>{locale === "ar" ? "المشاعر" : "sentiment"}</small></div><hr /><label>{locale === "ar" ? "تعليمات المسؤول" : "Officer instruction"}<textarea value={instruction} onChange={(event) => setInstruction(event.target.value)} /></label><button className="primary-button" onClick={generate} disabled={status === "loading"}>{status === "loading" ? "•••" : t.generate}</button></aside>
        <article className="draft-editor panel"><div className="editor-head"><div><span className="status-dot" /><b>{locale === "ar" ? "مسودة غير منشورة" : "Unpublished draft"}</b></div><span>العربية · MSA</span></div><div className={`draft-body ${status === "idle" ? "empty" : ""}`}>{status === "idle" ? <><strong>✦</strong><p>{locale === "ar" ? "ابدأ بإنشاء مسودة موثقة من السياسة المعتمدة" : "Generate a draft grounded in the approved policy"}</p></> : status === "abstained" ? <div className="abstain-box"><strong>{locale === "ar" ? "توقّف آمن" : "Safe refusal"}</strong><p>{locale === "ar" ? "لا توجد وثيقة معتمدة تدعم هذا الالتزام. يرجى إضافة المصدر أولاً." : "No approved source supports this commitment. Add the source first."}</p></div> : status === "error" ? <div className="abstain-box"><strong>{locale === "ar" ? "تعذر إنشاء المسودة" : "Draft generation failed"}</strong><p>{locale === "ar" ? "يرجى المحاولة مرة أخرى." : "Please try again."}</p></div> : <p className="arabic-draft">{draft}<span className={status === "loading" ? "cursor" : ""} /></p>}</div>{status === "done" && retrieval?.chunks?.[0] && <div className="citation"><span>1</span><div><b>{t.source}</b><p>{retrieval.chunks[0].title_ar} · {retrieval.chunks[0].heading_path}</p><small>Entailment {verification?.grounding_score?.toFixed(2) ?? "—"} · Retrieval {retrieval.chunks[0].rerank_score.toFixed(2)}</small></div></div>}</article>
        <aside className="checks panel"><span className="eyebrow">{t.guardrails}</span>{[["✓", locale === "ar" ? "الاستناد إلى المصدر" : "Source grounding", verification?.grounding_score ? `${Math.round(verification.grounding_score * 100)}%` : "—"], ["✓", locale === "ar" ? "لا توجد بيانات شخصية" : "No PII leakage", "PASS"], [verification?.policy_flags?.length ? "!" : "✓", locale === "ar" ? "لا التزام محظور" : "No forbidden commitment", verification?.policy_flags?.length ? "REVIEW" : "PASS"], ["✓", locale === "ar" ? "السجل الرسمي" : "Official register", "MSA"]].map(([icon, label, value]) => <div className="check-row" key={label}><i>{icon}</i><span>{label}</span><b>{value}</b></div>)}<hr /><p>{locale === "ar" ? "لا يمكن للنظام النشر. يلزم اعتماد مسؤول مختلف عن منشئ المسودة." : "The system cannot publish. Approval by a different officer is required."}</p><button disabled={status !== "done"}>{locale === "ar" ? "إرسال للاعتماد" : "Submit for approval"}</button></aside>
      </section>
    </div>
  );
}
