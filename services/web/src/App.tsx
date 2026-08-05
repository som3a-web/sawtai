import { lazy, Suspense, useMemo, useState } from "react";

import { initialPage } from "./app/navigation";
import type { Locale, Page } from "./app/types";
import { LoadingCard } from "./components/LoadingCard";
import { copy } from "./i18n/copy";

const Overview = lazy(() => import("./features/overview/Overview").then((module) => ({ default: module.Overview })));
const VoiceExplorer = lazy(() => import("./features/voice/VoiceExplorer").then((module) => ({ default: module.VoiceExplorer })));
const DraftStudio = lazy(() => import("./features/draft/DraftStudio").then((module) => ({ default: module.DraftStudio })));
const CrisisRoom = lazy(() => import("./features/crisis/CrisisRoom").then((module) => ({ default: module.CrisisRoom })));
const DataExplorer = lazy(() => import("./features/data/DataExplorer").then((module) => ({ default: module.DataExplorer })));

export function App() {
  const [locale, setLocale] = useState<Locale>("ar");
  const [page, setPage] = useState<Page>(() => initialPage(window.location.search));
  const t = copy[locale];
  const nav = useMemo(() => [
    { id: "overview" as Page, icon: "⌂", label: t.overview },
    { id: "voice" as Page, icon: "◉", label: t.voice },
    { id: "draft" as Page, icon: "✦", label: t.draft },
    { id: "crisis" as Page, icon: "△", label: t.crisis },
    { id: "data" as Page, icon: "▦", label: t.data },
  ], [t]);
  return (
    <div className="app" dir={locale === "ar" ? "rtl" : "ltr"}>
      <aside className="sidebar"><div className="brand"><div className="brand-mark"><i /><i /><i /></div><div><strong>{t.title}</strong><span>{t.platform}</span></div></div><nav>{nav.map((item) => <button key={item.id} className={page === item.id ? "active" : ""} onClick={() => setPage(item.id)}><span>{item.icon}</span>{item.label}{item.id === "crisis" && <b>1</b>}</button>)}</nav><div className="sidebar-foot"><div className="data-shield">◇<span>{locale === "ar" ? "البيانات داخل النطاق" : "Data stays in scope"}</span></div><small>Prototype · v0.1.0</small></div></aside>
      <main className="main"><header className="topbar"><div className="entity"><span>ش</span><div><b>{locale === "ar" ? "بلدية الشارقة التجريبية" : "Sharjah Municipality Demo"}</b><small>{locale === "ar" ? "إدارة الاتصال الحكومي" : "Government Communication"}</small></div></div><div className="top-actions"><button className="locale" onClick={() => setLocale(locale === "ar" ? "en" : "ar")}>{locale === "ar" ? "EN" : "عربي"}</button><button className="notification">♢<b>1</b></button><div className="avatar">م</div></div></header><div className="content"><Suspense fallback={<LoadingCard />}>{page === "overview" && <Overview locale={locale} go={setPage} />}{page === "voice" && <VoiceExplorer locale={locale} />}{page === "draft" && <DraftStudio locale={locale} />}{page === "crisis" && <CrisisRoom locale={locale} />}{page === "data" && <DataExplorer locale={locale} />}</Suspense></div></main>
    </div>
  );
}
