import { QueryClient, QueryClientProvider, useQuery } from "@tanstack/react-query";
import type { EChartsOption } from "echarts";
import ReactECharts from "echarts-for-react";
import { StrictMode, useMemo, useState } from "react";
import { createRoot } from "react-dom/client";
import "./styles.css";

type Locale = "ar" | "en";
type Page = "overview" | "voice" | "draft" | "crisis";

interface OverviewData {
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

interface TimeseriesData {
  series: Array<{ bucket: string; volume: number; sentiment: number }>;
}

interface MessageItem {
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

interface MessagesData {
  items: MessageItem[];
  total_estimate: number;
  provenance: string;
}

interface AlertItem {
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

interface AlertsData {
  items: AlertItem[];
}

interface ReplayPoint {
  t: string;
  msg_count: number;
  neg_share: number;
  risk_score: number;
  tier: string | null;
}

interface ReplayData {
  label_ar: string;
  label_en: string;
  series: ReplayPoint[];
  lead_time_hours: number;
  method: string;
}

const copy = {
  ar: {
    overview: "نظرة عامة",
    voice: "صوت المتعامل",
    draft: "استوديو الصياغة",
    crisis: "غرفة الأزمات",
    live: "إعادة تشغيل تجريبية",
    platform: "منصة ذكاء الاتصال الحكومي",
    title: "صوتي",
    messages: "إجمالي الرسائل",
    satisfaction: "مؤشر الرضا",
    cases: "الحالات المفتوحة",
    alerts: "التنبيهات النشطة",
    synthetic: "بيانات تركيبية معلنة",
    evidence: "الدليل وراء الرقم",
    search: "ابحث في صوت المتعامل",
    all: "الكل",
    negative: "سلبي",
    neutral: "محايد",
    positive: "إيجابي",
    generate: "إنشاء مسودة موثقة",
    instruction: "اكتب رداً رسمياً متعاطفاً يوضح جدول جمع النفايات",
    source: "المصدر المعتمد",
    guardrails: "فحص الحوكمة",
    replay: "آلة الزمن",
    warning: "ساعة إنذار مبكر",
    drivers: "لماذا ارتفع الخطر؟",
    playbook: "خطة الاستجابة",
  },
  en: {
    overview: "Overview",
    voice: "Voice Explorer",
    draft: "Draft Studio",
    crisis: "Crisis Room",
    live: "Synthetic replay",
    platform: "Government Communication Intelligence",
    title: "SawtAI",
    messages: "Total messages",
    satisfaction: "Satisfaction index",
    cases: "Open cases",
    alerts: "Active alerts",
    synthetic: "Declared synthetic data",
    evidence: "Evidence behind the number",
    search: "Search citizen voice",
    all: "All",
    negative: "Negative",
    neutral: "Neutral",
    positive: "Positive",
    generate: "Generate grounded draft",
    instruction: "Write an empathetic official reply explaining the waste collection schedule",
    source: "Approved source",
    guardrails: "Governance checks",
    replay: "Time machine",
    warning: "hours early warning",
    drivers: "Why did risk rise?",
    playbook: "Response playbook",
  },
};

async function getJson<T>(path: string): Promise<T> {
  const response = await fetch(path, { headers: { Authorization: "Bearer sawtai-demo-token" } });
  if (!response.ok) throw new Error(`Request failed: ${response.status}`);
  return response.json() as Promise<T>;
}

function LoadingCard() {
  return <div className="panel loading"><span /><span /><span /></div>;
}

function KpiCard({ label, value, note, tone = "teal" }: { label: string; value: string; note: string; tone?: string }) {
  return (
    <article className={`kpi ${tone}`}>
      <div className="kpi-orb" />
      <p>{label}</p>
      <strong>{value}</strong>
      <small>{note}</small>
    </article>
  );
}

function Overview({ locale, go }: { locale: Locale; go: (page: Page) => void }) {
  const t = copy[locale];
  const overview = useQuery({ queryKey: ["overview"], queryFn: () => getJson<OverviewData>("/api/v1/analytics/overview") });
  const timeseries = useQuery({ queryKey: ["timeseries"], queryFn: () => getJson<TimeseriesData>("/api/v1/analytics/timeseries") });
  if (!overview.data || !timeseries.data) return <LoadingCard />;
  const data = overview.data;
  const sentimentOption: EChartsOption = {
    tooltip: { trigger: "item" },
    legend: { bottom: 0, textStyle: { color: "#65736f" } },
    series: [{
      type: "pie",
      radius: ["55%", "78%"],
      center: ["50%", "43%"],
      label: { show: false },
      data: [
        { name: t.negative, value: data.kpis.sentiment.negative, itemStyle: { color: "#e06b61" } },
        { name: t.neutral, value: data.kpis.sentiment.neutral, itemStyle: { color: "#d8b75c" } },
        { name: t.positive, value: data.kpis.sentiment.positive, itemStyle: { color: "#1f9d82" } },
      ],
    }],
  };
  const volumeOption: EChartsOption = {
    grid: { left: 44, right: 18, top: 20, bottom: 30 },
    tooltip: { trigger: "axis" },
    xAxis: { type: "category", data: timeseries.data.series.map((item) => new Date(item.bucket).toLocaleDateString(locale === "ar" ? "ar-AE" : "en-AE", { day: "numeric", month: "short" })), axisLine: { lineStyle: { color: "#dce5e1" } } },
    yAxis: { type: "value", splitLine: { lineStyle: { color: "#edf2ef" } } },
    series: [{ type: "line", smooth: true, data: timeseries.data.series.map((item) => item.volume), lineStyle: { width: 3, color: "#0b746b" }, areaStyle: { color: "rgba(22,148,132,.14)" }, symbol: "none" }],
  };
  return (
    <div className="page-stack">
      <header className="page-heading">
        <div><span className="eyebrow">LIVE INTELLIGENCE</span><h2>{t.overview}</h2><p>{locale === "ar" ? "صورة لحظية موثقة لصوت المجتمع" : "A traceable live picture of community voice"}</p></div>
        <div className="replay-badge"><i /> {t.live} · 14 JUN 2026</div>
      </header>
      <section className="kpi-grid">
        <KpiCard label={t.messages} value={data.kpis.total_messages.toLocaleString(locale === "ar" ? "ar-AE" : "en-AE")} note={`↑ ${data.kpis.delta_pct}%`} />
        <KpiCard label={t.satisfaction} value={`${data.kpis.csat_index.value}`} note={`${data.kpis.csat_index.delta} pts`} tone="gold" />
        <KpiCard label={t.cases} value={`${data.kpis.open_cases}`} note={locale === "ar" ? "47 مرتبطة بالأزمة" : "47 linked to crisis"} tone="ink" />
        <KpiCard label={t.alerts} value={`${Object.values(data.kpis.active_alerts).reduce((sum, value) => sum + value, 0)}`} note={locale === "ar" ? "تنبيه مرتفع واحد" : "1 high alert"} tone="coral" />
      </section>
      <section className="dashboard-grid">
        <article className="panel chart-panel wide"><div className="panel-title"><div><span>01</span><h3>{locale === "ar" ? "حجم التواصل" : "Communication volume"}</h3></div><button onClick={() => go("voice")}>{t.evidence} ←</button></div><ReactECharts option={volumeOption} style={{ height: 285 }} /></article>
        <article className="panel chart-panel"><div className="panel-title"><div><span>02</span><h3>{locale === "ar" ? "المشاعر" : "Sentiment"}</h3></div></div><ReactECharts option={sentimentOption} style={{ height: 285 }} /></article>
        <article className="panel topics-panel"><div className="panel-title"><div><span>03</span><h3>{locale === "ar" ? "المواضيع الصاعدة" : "Rising topics"}</h3></div></div>{data.top_topics.map((topic, index) => <button className="topic-row" key={topic.topic_id} onClick={() => go(topic.is_emerging ? "crisis" : "voice")}><b>{String(index + 1).padStart(2, "0")}</b><span><strong>{locale === "ar" ? topic.label_ar : topic.label_en}</strong><small>{topic.count} {locale === "ar" ? "رسالة" : "messages"}</small></span><em className={topic.risk_score > 60 ? "risk-high" : "risk-low"}>{Math.round(topic.risk_score)}</em></button>)}</article>
        <article className="panel alert-card" onClick={() => go("crisis")}><div className="alert-pulse" /><span>{locale === "ar" ? "تنبيه مرتفع" : "HIGH ALERT"}</span><h3>{locale === "ar" ? "تصاعد شكاوى تأخر جمع النفايات" : "Waste collection complaints are escalating"}</h3><p>{locale === "ar" ? "ارتفع الحجم 5.2× عن المعتاد مع تسارع المشاعر السلبية." : "Volume is 5.2× above normal with accelerating negative sentiment."}</p><strong>73.1</strong></article>
      </section>
      <div className="provenance"><span>ⓘ</span>{t.synthetic} · n={data.kpis.total_messages} · {data.provenance}</div>
    </div>
  );
}

function VoiceExplorer({ locale }: { locale: Locale }) {
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

function DraftStudio({ locale }: { locale: Locale }) {
  const t = copy[locale];
  const [instruction, setInstruction] = useState(t.instruction);
  const [draft, setDraft] = useState("");
  const [status, setStatus] = useState<"idle" | "loading" | "done" | "abstained">("idle");
  const generate = async () => {
    setDraft(""); setStatus("loading");
    const response = await fetch("/api/v1/drafts", { method: "POST", headers: { "Content-Type": "application/json", Authorization: "Bearer sawtai-demo-token" }, body: JSON.stringify({ kind: "reply", case_id: "00000000-0000-0000-0000-000000000a01", lang: "ar", audience: "citizen", instruction }) });
    const reader = response.body?.getReader();
    if (!reader) return;
    const decoder = new TextDecoder(); let buffer = "";
    while (true) {
      const { value, done } = await reader.read(); if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const events = buffer.split("\n\n"); buffer = events.pop() ?? "";
      for (const block of events) {
        const name = block.match(/event: (.+)/)?.[1];
        const raw = block.match(/data: (.+)/)?.[1];
        if (!raw) continue;
        const data = JSON.parse(raw) as { delta?: string };
        if (name === "token" && data.delta) setDraft((current) => current + data.delta);
        if (name === "abstain") setStatus("abstained");
        if (name === "done") setStatus("done");
      }
    }
  };
  return (
    <div className="page-stack">
      <header className="page-heading"><div><span className="eyebrow">GROUNDED COMMUNICATION</span><h2>{t.draft}</h2><p>{locale === "ar" ? "مسودة رسمية، موثقة، ولا تُنشر دون اعتماد بشري" : "Official drafts grounded in approved sources and human-approved"}</p></div><div className="case-chip">SHJ-2026-004182 · HIGH</div></header>
      <section className="studio-grid">
        <aside className="case-context panel"><span className="eyebrow">CASE CONTEXT</span><h3>{locale === "ar" ? "تأخر جمع النفايات" : "Delayed waste collection"}</h3><p>{locale === "ar" ? "47 شكوى مرتبطة · المنطقة الصناعية · مهلة الاستجابة 4 ساعات" : "47 linked complaints · Industrial Area · 4-hour SLA"}</p><div className="context-metric"><span>47</span><small>{locale === "ar" ? "شكوى" : "complaints"}</small></div><div className="context-metric"><span>-0.78</span><small>{locale === "ar" ? "المشاعر" : "sentiment"}</small></div><hr /><label>{locale === "ar" ? "تعليمات المسؤول" : "Officer instruction"}<textarea value={instruction} onChange={(event) => setInstruction(event.target.value)} /></label><button className="primary-button" onClick={generate} disabled={status === "loading"}>{status === "loading" ? "•••" : t.generate}</button></aside>
        <article className="draft-editor panel"><div className="editor-head"><div><span className="status-dot" /><b>{locale === "ar" ? "مسودة غير منشورة" : "Unpublished draft"}</b></div><span>العربية · MSA</span></div><div className={`draft-body ${status === "idle" ? "empty" : ""}`}>{status === "idle" ? <><strong>✦</strong><p>{locale === "ar" ? "ابدأ بإنشاء مسودة موثقة من السياسة المعتمدة" : "Generate a draft grounded in the approved policy"}</p></> : status === "abstained" ? <div className="abstain-box"><strong>{locale === "ar" ? "توقّف آمن" : "Safe refusal"}</strong><p>{locale === "ar" ? "لا توجد وثيقة معتمدة تدعم هذا الالتزام. يرجى إضافة المصدر أولاً." : "No approved source supports this commitment. Add the source first."}</p></div> : <p className="arabic-draft">{draft}<span className={status === "loading" ? "cursor" : ""} /></p>}</div>{status === "done" && <div className="citation"><span>1</span><div><b>{t.source}</b><p>سياسة إدارة النفايات · الجمع › الجدول الزمني</p><small>Entailment 0.91 · Rerank 0.81</small></div></div>}</article>
        <aside className="checks panel"><span className="eyebrow">{t.guardrails}</span>{[["✓", locale === "ar" ? "الاستناد إلى المصدر" : "Source grounding", "94%"], ["✓", locale === "ar" ? "لا توجد بيانات شخصية" : "No PII leakage", "PASS"], ["✓", locale === "ar" ? "لا التزام محظور" : "No forbidden commitment", "PASS"], ["✓", locale === "ar" ? "السجل الرسمي" : "Official register", "MSA"]].map(([icon, label, value]) => <div className="check-row" key={label}><i>{icon}</i><span>{label}</span><b>{value}</b></div>)}<hr /><p>{locale === "ar" ? "لا يمكن للنظام النشر. يلزم اعتماد مسؤول مختلف عن منشئ المسودة." : "The system cannot publish. Approval by a different officer is required."}</p><button disabled={status !== "done"}>{locale === "ar" ? "إرسال للاعتماد" : "Submit for approval"}</button></aside>
      </section>
    </div>
  );
}

function CrisisRoom({ locale }: { locale: Locale }) {
  const t = copy[locale];
  const alerts = useQuery({ queryKey: ["alerts"], queryFn: () => getJson<AlertsData>("/api/v1/alerts") });
  const replay = useQuery({ queryKey: ["replay"], queryFn: () => getJson<ReplayData>("/api/v1/forecast/replay") });
  const [position, setPosition] = useState(76);
  if (!alerts.data || !replay.data) return <LoadingCard />;
  const alert = alerts.data.items[0];
  const index = Math.min(replay.data.series.length - 1, Math.floor((position / 100) * replay.data.series.length));
  const current = replay.data.series[index];
  const riskOption: EChartsOption = { series: [{ type: "gauge", startAngle: 210, endAngle: -30, min: 0, max: 100, progress: { show: true, width: 18, itemStyle: { color: current.risk_score > 70 ? "#dd6157" : "#d7aa45" } }, axisLine: { lineStyle: { width: 18, color: [[1, "#edf1ef"]] } }, axisTick: { show: false }, splitLine: { show: false }, axisLabel: { show: false }, pointer: { show: false }, title: { offsetCenter: [0, "42%"], fontSize: 13, color: "#75817e" }, detail: { valueAnimation: true, formatter: "{value}", fontSize: 42, fontWeight: 700, color: "#163a36", offsetCenter: [0, "0%"] }, data: [{ value: current.risk_score, name: current.tier?.toUpperCase() ?? "WATCH" }] }] };
  const lineOption: EChartsOption = { grid: { left: 38, right: 14, top: 18, bottom: 30 }, tooltip: { trigger: "axis" }, xAxis: { type: "category", data: replay.data.series.map((point) => new Date(point.t).toLocaleDateString(locale === "ar" ? "ar-AE" : "en-AE", { day: "numeric", month: "short" })), axisLabel: { interval: 17 } }, yAxis: { type: "value", min: 0, max: 100, splitLine: { lineStyle: { color: "#edf2ef" } } }, series: [{ type: "line", smooth: true, showSymbol: false, data: replay.data.series.map((point) => point.risk_score), lineStyle: { width: 3, color: "#d3544b" }, markLine: { silent: true, data: [{ yAxis: 70, lineStyle: { color: "#df8a82", type: "dashed" }, label: { formatter: "T2" } }] } }] };
  return (
    <div className="page-stack">
      <header className="page-heading"><div><span className="eyebrow">EARLY WARNING · T2 HIGH</span><h2>{t.crisis}</h2><p>{locale === "ar" ? alert.title_ar : alert.title_en}</p></div><div className="warning-number"><strong>{replay.data.lead_time_hours}</strong><span>{t.warning}</span></div></header>
      <section className="crisis-grid"><article className="panel gauge-panel"><span className="eyebrow">RISK NOW</span><ReactECharts option={riskOption} style={{ height: 275 }} /><div className="risk-meta"><span>{current.msg_count} {locale === "ar" ? "رسالة/ساعة" : "msg/hour"}</span><span>{Math.round(current.neg_share * 100)}% {t.negative}</span></div></article><article className="panel timeline-panel"><div className="panel-title"><div><span>TIME</span><h3>{t.replay}</h3></div><time>{new Date(current.t).toLocaleString(locale === "ar" ? "ar-AE" : "en-AE")}</time></div><ReactECharts option={lineOption} style={{ height: 245 }} /><input type="range" min="1" max="100" value={position} onChange={(event) => setPosition(Number(event.target.value))} /><div className="timeline-labels"><span>10 JUN</span><b>FIRST ALERT</b><span>14 JUN · PEAK</span></div></article><article className="panel drivers-panel"><span className="eyebrow">{t.drivers}</span>{alert.drivers.map((driver) => <div className="driver" key={driver.feature}><div><b>{driver.feature.replaceAll("_", " ")}</b><span>{driver.value}</span></div><progress value={driver.contribution} max="0.35" /></div>)}</article><article className="panel playbook-panel"><span className="eyebrow">{t.playbook}</span><h3>{alert.playbook_title_ar}</h3>{alert.playbook_steps.map((step) => <div className="playbook-step" key={step.seq}><span>{step.seq}</span><div><b>{step.action_ar}</b><small>{step.owner_role}</small></div><input type="checkbox" /></div>)}<button className="primary-button">{locale === "ar" ? "إنشاء بيان أولي" : "Generate initial statement"}</button></article></section>
      <div className="provenance"><span>ⓘ</span>{replay.data.method}</div>
    </div>
  );
}

function App() {
  const [locale, setLocale] = useState<Locale>("ar");
  const [page, setPage] = useState<Page>("overview");
  const t = copy[locale];
  const nav = useMemo(() => [{ id: "overview" as Page, icon: "⌂", label: t.overview }, { id: "voice" as Page, icon: "◉", label: t.voice }, { id: "draft" as Page, icon: "✦", label: t.draft }, { id: "crisis" as Page, icon: "△", label: t.crisis }], [t]);
  return (
    <div className="app" dir={locale === "ar" ? "rtl" : "ltr"}>
      <aside className="sidebar"><div className="brand"><div className="brand-mark"><i /><i /><i /></div><div><strong>{t.title}</strong><span>{t.platform}</span></div></div><nav>{nav.map((item) => <button key={item.id} className={page === item.id ? "active" : ""} onClick={() => setPage(item.id)}><span>{item.icon}</span>{item.label}{item.id === "crisis" && <b>1</b>}</button>)}</nav><div className="sidebar-foot"><div className="data-shield">◇<span>{locale === "ar" ? "البيانات داخل النطاق" : "Data stays in scope"}</span></div><small>Prototype · v0.1.0</small></div></aside>
      <main className="main"><header className="topbar"><div className="entity"><span>ش</span><div><b>{locale === "ar" ? "بلدية الشارقة التجريبية" : "Sharjah Municipality Demo"}</b><small>{locale === "ar" ? "إدارة الاتصال الحكومي" : "Government Communication"}</small></div></div><div className="top-actions"><button className="locale" onClick={() => setLocale(locale === "ar" ? "en" : "ar")}>{locale === "ar" ? "EN" : "عربي"}</button><button className="notification">♢<b>1</b></button><div className="avatar">م</div></div></header><div className="content">{page === "overview" && <Overview locale={locale} go={setPage} />}{page === "voice" && <VoiceExplorer locale={locale} />}{page === "draft" && <DraftStudio locale={locale} />}{page === "crisis" && <CrisisRoom locale={locale} />}</div></main>
    </div>
  );
}

const queryClient = new QueryClient({ defaultOptions: { queries: { staleTime: 30_000, retry: 1 } } });
createRoot(document.getElementById("root")!).render(<StrictMode><QueryClientProvider client={queryClient}><App /></QueryClientProvider></StrictMode>);
