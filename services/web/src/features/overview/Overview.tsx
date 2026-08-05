import { useQuery } from "@tanstack/react-query";
import type { EChartsCoreOption } from "echarts/core";

import { getJson } from "../../api/client";
import type { OverviewData, TimeseriesData } from "../../api/types";
import type { Locale, Page } from "../../app/types";
import { Chart } from "../../components/Chart";
import { KpiCard } from "../../components/KpiCard";
import { LoadingCard } from "../../components/LoadingCard";
import { copy } from "../../i18n/copy";

interface OverviewProps {
  locale: Locale;
  go: (page: Page) => void;
}

export function Overview({ locale, go }: OverviewProps) {
  const t = copy[locale];
  const overview = useQuery({ queryKey: ["overview"], queryFn: () => getJson<OverviewData>("/api/v1/analytics/overview") });
  const timeseries = useQuery({ queryKey: ["timeseries"], queryFn: () => getJson<TimeseriesData>("/api/v1/analytics/timeseries") });
  if (!overview.data || !timeseries.data) return <LoadingCard />;
  const data = overview.data;
  const sentimentOption: EChartsCoreOption = {
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
  const volumeOption: EChartsCoreOption = {
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
        <article className="panel chart-panel wide"><div className="panel-title"><div><span>01</span><h3>{locale === "ar" ? "حجم التواصل" : "Communication volume"}</h3></div><button onClick={() => go("voice")}>{t.evidence} ←</button></div><Chart option={volumeOption} style={{ height: 285 }} /></article>
        <article className="panel chart-panel"><div className="panel-title"><div><span>02</span><h3>{locale === "ar" ? "المشاعر" : "Sentiment"}</h3></div></div><Chart option={sentimentOption} style={{ height: 285 }} /></article>
        <article className="panel topics-panel"><div className="panel-title"><div><span>03</span><h3>{locale === "ar" ? "المواضيع الصاعدة" : "Rising topics"}</h3></div></div>{data.top_topics.map((topic, index) => <button className="topic-row" key={topic.topic_id} onClick={() => go(topic.is_emerging ? "crisis" : "voice")}><b>{String(index + 1).padStart(2, "0")}</b><span><strong>{locale === "ar" ? topic.label_ar : topic.label_en}</strong><small>{topic.count} {locale === "ar" ? "رسالة" : "messages"}</small></span><em className={topic.risk_score > 60 ? "risk-high" : "risk-low"}>{Math.round(topic.risk_score)}</em></button>)}</article>
        <article className="panel alert-card" onClick={() => go("crisis")}><div className="alert-pulse" /><span>{locale === "ar" ? "تنبيه مرتفع" : "HIGH ALERT"}</span><h3>{locale === "ar" ? "تصاعد شكاوى تأخر جمع النفايات" : "Waste collection complaints are escalating"}</h3><p>{locale === "ar" ? "ارتفع الحجم 5.2× عن المعتاد مع تسارع المشاعر السلبية." : "Volume is 5.2× above normal with accelerating negative sentiment."}</p><strong>73.1</strong></article>
      </section>
      <div className="provenance"><span>ⓘ</span>{t.synthetic} · n={data.kpis.total_messages} · {data.provenance}</div>
    </div>
  );
}
