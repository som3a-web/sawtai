import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";

import { getJson, postJson } from "../../api/client";
import type { NotificationItem, NotificationsData } from "../../api/types";
import type { Locale, Page } from "../../app/types";

function icon(item: NotificationItem) {
  if (item.kind === "draft_approval") return "✦";
  if (item.level === "critical") return "!";
  if (item.kind.startsWith("sla_")) return "◷";
  return "◇";
}

export function NotificationCenter({ locale, go }: { locale: Locale; go: (page: Page) => void }) {
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const root = useRef<HTMLDivElement>(null);
  const notifications = useQuery({
    queryKey: ["notifications"],
    queryFn: () => getJson<NotificationsData>("/api/v1/notifications?limit=50"),
    refetchInterval: 30_000,
  });
  const refresh = () => queryClient.invalidateQueries({ queryKey: ["notifications"] });
  const read = useMutation({ mutationFn: (id: string) => postJson(`/api/v1/notifications/${id}/read`, {}), onSuccess: refresh });
  const readAll = useMutation({ mutationFn: () => postJson("/api/v1/notifications/read-all", {}), onSuccess: refresh });

  useEffect(() => {
    function close(event: MouseEvent) {
      if (root.current && !root.current.contains(event.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, []);

  function openTarget(item: NotificationItem) {
    if (!item.is_read) read.mutate(item.notification_id);
    go(item.target_page);
    setOpen(false);
  }

  const unread = notifications.data?.unread ?? 0;
  return <div className="notification-wrap" ref={root}>
    <button className={`notification ${open ? "active" : ""}`} aria-label={locale === "ar" ? "الإشعارات" : "Notifications"} onClick={() => setOpen(!open)}>♢{unread > 0 && <b>{unread > 9 ? "9+" : unread}</b>}</button>
    {open && <section className="notification-panel">
      <header><div><span className="eyebrow">ACTION CENTER</span><h3>{locale === "ar" ? "الإشعارات" : "Notifications"}</h3></div>{unread > 0 && <button onClick={() => readAll.mutate()} disabled={readAll.isPending}>{locale === "ar" ? "قراءة الكل" : "Mark all read"}</button>}</header>
      <div className="notification-list">{notifications.isLoading ? <div className="notification-empty">{locale === "ar" ? "جارٍ التحديث…" : "Refreshing…"}</div> : notifications.data?.items.length ? notifications.data.items.map((item) => <button key={item.notification_id} className={`${item.level} ${item.is_read ? "read" : "unread"}`} onClick={() => openTarget(item)}><i>{icon(item)}</i><div><b>{locale === "ar" ? item.title_ar : item.title_en}</b><p>{locale === "ar" ? item.body_ar : item.body_en}</p><small>{item.reference ? `${item.reference} · ` : ""}{new Date(item.occurred_at).toLocaleString(locale === "ar" ? "ar-AE" : "en-AE", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" })}</small></div>{!item.is_read && <em />}</button>) : <div className="notification-empty"><span>✓</span><b>{locale === "ar" ? "لا توجد إجراءات معلقة" : "No pending actions"}</b><small>{locale === "ar" ? "سننبهك عند حدوث تغيير مهم" : "Important changes will appear here"}</small></div>}</div>
      <footer><span>✓ {locale === "ar" ? "تُسجل حالة القراءة في سجل التدقيق" : "Read state is audit logged"}</span></footer>
    </section>}
  </div>;
}
