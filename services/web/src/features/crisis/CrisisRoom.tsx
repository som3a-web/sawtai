import { useQuery } from "@tanstack/react-query";
import type { EChartsCoreOption } from "echarts/core";
import { useState } from "react";

import { getJson } from "../../api/client";
import type { AlertsData, ReplayData } from "../../api/types";
import type { Locale } from "../../app/types";
import { Chart } from "../../components/Chart";
import { LoadingCard } from "../../components/LoadingCard";
import { copy } from "../../i18n/copy";

export function CrisisRoom({ locale }: { locale: Locale }) {
  const t = copy[locale];
  const alerts = useQuery({ queryKey: ["alerts"], queryFn: () => getJson<AlertsData>("/api/v1/alerts") });
  const replay = useQuery({ queryKey: ["replay"], queryFn: () => getJson<ReplayData>("/api/v1/forecast/replay") });
  const [position, setPosition] = useState(76);
  if (!alerts.data || !replay.data || alerts.data.items.length === 0 || replay.data.series.length === 0) return <LoadingCard />;
  const alert = alerts.data.items[0];
  const index = Math.min(replay.data.series.length - 1, Math.floor((position / 100) * replay.data.series.length));
  const current = replay.data.series[index];
  const riskOption: EChartsCoreOption = { series: [{ type: "gauge", startAngle: 210, endAngle: -30, min: 0, max: 100, progress: { show: true, width: 18, itemStyle: { color: current.risk_score > 70 ? "#dd6157" : "#d7aa45" } }, axisLine: { lineStyle: { width: 18, color: [[1, "#edf1ef"]] } }, axisTick: { show: false }, splitLine: { show: false }, axisLabel: { show: false }, pointer: { show: false }, title: { offsetCenter: [0, "42%"], fontSize: 13, color: "#75817e" }, detail: { valueAnimation: true, formatter: "{value}", fontSize: 42, fontWeight: 700, color: "#163a36", offsetCenter: [0, "0%"] }, data: [{ value: current.risk_score, name: current.tier?.toUpperCase() ?? "WATCH" }] }] };
  const lineOption: EChartsCoreOption = { grid: { left: 38, right: 14, top: 18, bottom: 30 }, tooltip: { trigger: "axis" }, xAxis: { type: "category", data: replay.data.series.map((point) => new Date(point.t).toLocaleDateString(locale === "ar" ? "ar-AE" : "en-AE", { day: "numeric", month: "short" })), axisLabel: { interval: 17 } }, yAxis: { type: "value", min: 0, max: 100, splitLine: { lineStyle: { color: "#edf2ef" } } }, series: [{ type: "line", smooth: true, showSymbol: false, data: replay.data.series.map((point) => point.risk_score), lineStyle: { width: 3, color: "#d3544b" }, markLine: { silent: true, data: [{ yAxis: 70, lineStyle: { color: "#df8a82", type: "dashed" }, label: { formatter: "T2" } }] } }] };
  return (
    <div className="page-stack">
      <header className="page-heading"><div><span className="eyebrow">EARLY WARNING · T2 HIGH</span><h2>{t.crisis}</h2><p>{locale === "ar" ? alert.title_ar : alert.title_en}</p></div><div className="warning-number"><strong>{replay.data.lead_time_hours}</strong><span>{t.warning}</span></div></header>
      <section className="crisis-grid"><article className="panel gauge-panel"><span className="eyebrow">RISK NOW</span><Chart option={riskOption} style={{ height: 275 }} /><div className="risk-meta"><span>{current.msg_count} {locale === "ar" ? "رسالة/ساعة" : "msg/hour"}</span><span>{Math.round(current.neg_share * 100)}% {t.negative}</span></div></article><article className="panel timeline-panel"><div className="panel-title"><div><span>TIME</span><h3>{t.replay}</h3></div><time>{new Date(current.t).toLocaleString(locale === "ar" ? "ar-AE" : "en-AE")}</time></div><Chart option={lineOption} style={{ height: 245 }} /><input type="range" min="1" max="100" value={position} onChange={(event) => setPosition(Number(event.target.value))} /><div className="timeline-labels"><span>10 JUN</span><b>FIRST ALERT</b><span>14 JUN · PEAK</span></div></article><article className="panel drivers-panel"><span className="eyebrow">{t.drivers}</span>{alert.drivers.map((driver) => <div className="driver" key={driver.feature}><div><b>{driver.feature.replaceAll("_", " ")}</b><span>{driver.value}</span></div><progress value={driver.contribution} max="0.35" /></div>)}</article><article className="panel playbook-panel"><span className="eyebrow">{t.playbook}</span><h3>{alert.playbook_title_ar}</h3>{alert.playbook_steps.map((step) => <div className="playbook-step" key={step.seq}><span>{step.seq}</span><div><b>{step.action_ar}</b><small>{step.owner_role}</small></div><input type="checkbox" /></div>)}<button className="primary-button">{locale === "ar" ? "إنشاء بيان أولي" : "Generate initial statement"}</button></article></section>
      <div className="provenance"><span>ⓘ</span>{replay.data.method}</div>
    </div>
  );
}
