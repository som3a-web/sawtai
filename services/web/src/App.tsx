import { lazy, Suspense, useEffect, useMemo, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";

import { getAccessToken, getJson, logout, restoreSession } from "./api/client";
import type { AuthUser } from "./api/types";
import { initialPage } from "./app/navigation";
import type { Locale, Page } from "./app/types";
import { LoadingCard } from "./components/LoadingCard";
import { LoginScreen } from "./features/auth/LoginScreen";
import { copy } from "./i18n/copy";

const Overview = lazy(() => import("./features/overview/Overview").then((module) => ({ default: module.Overview })));
const WhatsAppHub = lazy(() => import("./features/whatsapp/WhatsAppHub").then((module) => ({ default: module.WhatsAppHub })));
const VoiceExplorer = lazy(() => import("./features/voice/VoiceExplorer").then((module) => ({ default: module.VoiceExplorer })));
const DraftStudio = lazy(() => import("./features/draft/DraftStudio").then((module) => ({ default: module.DraftStudio })));
const CrisisRoom = lazy(() => import("./features/crisis/CrisisRoom").then((module) => ({ default: module.CrisisRoom })));
const DataExplorer = lazy(() => import("./features/data/DataExplorer").then((module) => ({ default: module.DataExplorer })));
const UserAdministration = lazy(() => import("./features/admin/UserAdministration").then((module) => ({ default: module.UserAdministration })));

function permitted(user: AuthUser, permission: string) {
  const namespace = permission.split(":")[0];
  return user.permissions.includes(permission) || user.permissions.includes(`${namespace}:*`);
}

export function App() {
  const queryClient = useQueryClient();
  const [locale, setLocale] = useState<Locale>("ar");
  const [page, setPage] = useState<Page>(() => initialPage(window.location.search));
  const [user, setUser] = useState<AuthUser | null | undefined>(undefined);
  const t = copy[locale];

  useEffect(() => {
    let active = true;
    async function bootstrap() {
      try {
        if (getAccessToken()) {
          const profile = await getJson<AuthUser>("/api/v1/auth/me");
          if (active) setUser(profile);
          return;
        }
        const session = await restoreSession();
        if (active) setUser(session?.user ?? null);
      } catch {
        const session = await restoreSession();
        if (active) setUser(session?.user ?? null);
      }
    }
    void bootstrap();
    return () => { active = false; };
  }, []);

  const nav = useMemo(() => user ? [
    { id: "overview" as Page, icon: "⌂", label: t.overview, permission: "analytics:read" },
    { id: "whatsapp" as Page, icon: "◌", label: t.whatsapp, permission: "message:read" },
    { id: "voice" as Page, icon: "◉", label: t.voice, permission: "message:read" },
    { id: "draft" as Page, icon: "✦", label: t.draft, permission: "draft:create" },
    { id: "crisis" as Page, icon: "△", label: t.crisis, permission: "alert:read" },
    { id: "data" as Page, icon: "▦", label: t.data, permission: "data:read" },
    { id: "admin" as Page, icon: "⚙", label: locale === "ar" ? "المستخدمون" : "Users", permission: "user:read" },
  ].filter((item) => permitted(user, item.permission)) : [], [locale, t, user]);

  useEffect(() => {
    if (user && nav.length && !nav.some((item) => item.id === page)) setPage(nav[0].id);
  }, [nav, page, user]);

  if (user === undefined) return <div className="auth-loading"><div className="brand-mark"><i /><i /><i /></div><span>Loading SawtAI…</span></div>;
  if (user === null) return <LoginScreen locale={locale} onLocale={() => setLocale(locale === "ar" ? "en" : "ar")} onAuthenticated={setUser} />;

  const displayName = locale === "ar" ? user.display_name_ar : user.display_name_en;
  async function signOut() {
    await logout();
    queryClient.clear();
    setUser(null);
  }

  return (
    <div className="app" dir={locale === "ar" ? "rtl" : "ltr"}>
      <aside className="sidebar"><div className="brand"><div className="brand-mark"><i /><i /><i /></div><div><strong>{t.title}</strong><span>{t.platform}</span></div></div><nav>{nav.map((item) => <button key={item.id} className={page === item.id ? "active" : ""} onClick={() => setPage(item.id)}><span>{item.icon}</span>{item.label}{item.id === "crisis" && <b>1</b>}</button>)}</nav><div className="sidebar-foot"><div className="data-shield">◇<span>{locale === "ar" ? "البيانات داخل النطاق" : "Data stays in scope"}</span></div><small>Prototype · v0.2.0</small></div></aside>
      <main className="main"><header className="topbar"><div className="entity"><span>ش</span><div><b>{locale === "ar" ? "بلدية الشارقة التجريبية" : "Sharjah Municipality Demo"}</b><small>{locale === "ar" ? "إدارة الاتصال الحكومي" : "Government Communication"}</small></div></div><div className="top-actions"><button className="locale" onClick={() => setLocale(locale === "ar" ? "en" : "ar")}>{locale === "ar" ? "EN" : "عربي"}</button><button className="notification">♢<b>1</b></button><div className="profile-chip"><div className="avatar">{displayName.slice(0, 1)}</div><span><b>{displayName}</b><small>{user.roles.join(" · ")}</small></span><button onClick={() => void signOut()}>{locale === "ar" ? "خروج" : "Sign out"}</button></div></div></header><div className="content"><Suspense fallback={<LoadingCard />}>{page === "overview" && <Overview locale={locale} go={setPage} />}{page === "whatsapp" && <WhatsAppHub locale={locale} user={user} />}{page === "voice" && <VoiceExplorer locale={locale} />}{page === "draft" && <DraftStudio locale={locale} />}{page === "crisis" && <CrisisRoom locale={locale} />}{page === "data" && <DataExplorer locale={locale} />}{page === "admin" && <UserAdministration locale={locale} />}</Suspense></div></main>
    </div>
  );
}
