import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { getJson } from "../../api/client";
import type { MessageItem, MessagesData } from "../../api/types";
import type { Locale } from "../../app/types";
import { copy } from "../../i18n/copy";

export function VoiceExplorer({ locale }: { locale: Locale }) {
  const t = copy[locale];
  const [sentiment, setSentiment] = useState("");
  const [selected, setSelected] = useState<MessageItem | null>(null);
  const messages = useQuery({ queryKey: ["messages", sentiment], queryFn: () => getJson<MessagesData>(`/api/v1/messages?limit=40${sentiment ? `&sentiment=${sentiment}` : ""}`) });
  return (
    <div className="page-stack">
      <header className="page-heading"><div><span className="eyebrow">EVIDENCE EXPLORER</span><h2>{t.voice}</h2><p>{locale === "ar" ? "كل رقم يقود إلى الرسائل والنماذج التي أنتجته" : "Every number drills down to its messages and model lineage"}</p></div><div className="replay-badge"><i /> {t.live}</div></header>
      <div className="filter-bar"><label>⌕ <input placeholder={t.search} /></label>{[["", t.all], ["negative", t.negative], ["neutral", t.neutral], ["positive", t.positive]].map(([value, label]) => <button key={value} className={sentiment === value ? "active" : ""} onClick={() => setSentiment(value)}>{label}</button>)}</div>
      <section className="explorer-grid">
        <div className="message-list panel">{messages.data?.items.map((message) => <button key={message.message_id} className={`message-card ${selected?.message_id === message.message_id ? "selected" : ""}`} onClick={() => setSelected(message)}><div><span className={`sentiment-dot ${message.sentiment.label}`} /> <b>{message.channel.name_ar}</b><time>{new Date(message.occurred_at).toLocaleString(locale === "ar" ? "ar-AE" : "en-AE", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" })}</time></div><p><bdi>{message.text}</bdi></p><footer><span>{message.classification.label_ar}</span><span>{message.dialect.toUpperCase()}</span>{message.pii_redacted.length > 0 && <span className="pii">PII REDACTED</span>}</footer></button>)}</div>
        <aside className="evidence-panel panel">{selected ? <><span className="eyebrow">MODEL EVIDENCE</span><h3>{selected.classification.label_ar}</h3><p className="evidence-text"><bdi>{selected.text}</bdi></p><dl><div><dt>{locale === "ar" ? "المشاعر" : "Sentiment"}</dt><dd>{selected.sentiment.label} · {(selected.sentiment.confidence * 100).toFixed(0)}%</dd></div><div><dt>{locale === "ar" ? "التصنيف" : "Classification"}</dt><dd>{selected.classification.node_code} · {(selected.classification.confidence * 100).toFixed(0)}%</dd></div><div><dt>{locale === "ar" ? "اللهجة" : "Dialect"}</dt><dd>{selected.dialect}</dd></div><div><dt>{locale === "ar" ? "النموذج" : "Model"}</dt><dd>{selected.sentiment.model}<br />{selected.sentiment.version}</dd></div></dl><div className="lineage-ok">✓ {locale === "ar" ? "سلسلة المصدر مكتملة" : "Lineage chain complete"}</div></> : <div className="empty-evidence"><strong>↗</strong><p>{locale === "ar" ? "اختر رسالة لعرض أدلة النموذج" : "Select a message to inspect model evidence"}</p></div>}</aside>
      </section>
    </div>
  );
}
