import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { getJson, patchJson, postJson } from "../../api/client";
import type { RoleRecord, UserRecord } from "../../api/types";
import type { Locale } from "../../app/types";
import { LoadingCard } from "../../components/LoadingCard";

const initialForm = { email: "", display_name_ar: "", display_name_en: "", password: "", role: "comms_officer" };

export function UserAdministration({ locale }: { locale: Locale }) {
  const queryClient = useQueryClient();
  const [form, setForm] = useState(initialForm);
  const [notice, setNotice] = useState("");
  const users = useQuery({ queryKey: ["admin-users"], queryFn: () => getJson<{ items: UserRecord[] }>("/api/v1/users") });
  const roles = useQuery({ queryKey: ["admin-roles"], queryFn: () => getJson<{ items: RoleRecord[] }>("/api/v1/roles") });
  const create = useMutation({
    mutationFn: () => postJson("/api/v1/users", {
      email: form.email,
      display_name_ar: form.display_name_ar,
      display_name_en: form.display_name_en,
      password: form.password,
      role_codes: [form.role],
      mfa_enrolled: false,
    }),
    onSuccess: async () => {
      setForm(initialForm);
      setNotice(locale === "ar" ? "تم إنشاء المستخدم" : "User created");
      await queryClient.invalidateQueries({ queryKey: ["admin-users"] });
    },
  });
  const status = useMutation({
    mutationFn: ({ userId, active }: { userId: string; active: boolean }) => patchJson(`/api/v1/users/${userId}/status`, { is_active: active }),
    onSuccess: async () => queryClient.invalidateQueries({ queryKey: ["admin-users"] }),
  });
  const assignRole = useMutation({
    mutationFn: ({ userId, role }: { userId: string; role: string }) => postJson(`/api/v1/users/${userId}/roles`, { role_codes: [role] }),
    onSuccess: async () => queryClient.invalidateQueries({ queryKey: ["admin-users"] }),
  });
  if (users.isLoading || roles.isLoading) return <LoadingCard />;

  return <div className="page-stack admin-page">
    <header className="page-heading"><div><span className="eyebrow">IDENTITY & ACCESS</span><h2>{locale === "ar" ? "المستخدمون والصلاحيات" : "Users & access"}</h2><p>{locale === "ar" ? "إدارة الحسابات والأدوار ضمن نطاق الجهة." : "Manage tenant accounts and role-scoped permissions."}</p></div><div className="admin-security"><b>5</b><span>{locale === "ar" ? "أدوار محكومة" : "governed roles"}</span></div></header>
    <section className="admin-layout">
      <form className="panel admin-create" onSubmit={(event) => { event.preventDefault(); create.mutate(); }}>
        <span className="eyebrow">NEW ACCOUNT</span><h3>{locale === "ar" ? "إضافة مستخدم" : "Add user"}</h3>
        <label><span>{locale === "ar" ? "الاسم بالعربية" : "Arabic name"}</span><input required minLength={2} value={form.display_name_ar} onChange={(event) => setForm({ ...form, display_name_ar: event.target.value })} /></label>
        <label><span>{locale === "ar" ? "الاسم بالإنجليزية" : "English name"}</span><input required minLength={2} value={form.display_name_en} onChange={(event) => setForm({ ...form, display_name_en: event.target.value })} /></label>
        <label><span>{locale === "ar" ? "البريد الإلكتروني" : "Email"}</span><input required type="email" value={form.email} onChange={(event) => setForm({ ...form, email: event.target.value })} /></label>
        <label><span>{locale === "ar" ? "كلمة مرور مؤقتة" : "Temporary password"}</span><input required type="password" minLength={12} value={form.password} onChange={(event) => setForm({ ...form, password: event.target.value })} /></label>
        <label><span>{locale === "ar" ? "الدور" : "Role"}</span><select value={form.role} onChange={(event) => setForm({ ...form, role: event.target.value })}>{roles.data?.items.map((role) => <option key={role.code} value={role.code}>{locale === "ar" ? role.name_ar : role.name_en}</option>)}</select></label>
        {(create.error || users.error || roles.error) && <div className="login-error">{locale === "ar" ? "تعذر إكمال العملية" : "The operation could not be completed"}</div>}{notice && <div className="admin-notice">✓ {notice}</div>}
        <button className="login-submit" disabled={create.isPending}>{create.isPending ? (locale === "ar" ? "جارٍ الإنشاء…" : "Creating…") : (locale === "ar" ? "إنشاء الحساب" : "Create account")}</button>
      </form>
      <section className="panel admin-users"><header><div><span className="eyebrow">TENANT DIRECTORY</span><h3>{locale === "ar" ? "دليل المستخدمين" : "User directory"}</h3></div><b>{users.data?.items.length ?? 0}</b></header>
        <div className="admin-user-list">{users.data?.items.map((item) => <article key={item.user_id} className={!item.is_active ? "inactive" : ""}>
          <div className="admin-avatar">{(locale === "ar" ? item.display_name_ar : item.display_name_en).slice(0, 1)}</div><div className="admin-user-copy"><b>{locale === "ar" ? item.display_name_ar : item.display_name_en}</b><small>{item.email}</small><span>{item.mfa_enrolled ? "✓ MFA" : (locale === "ar" ? "MFA غير مسجل" : "MFA not enrolled")}</span></div>
          <select value={item.roles[0] ?? ""} onChange={(event) => assignRole.mutate({ userId: item.user_id, role: event.target.value })}>{roles.data?.items.map((role) => <option key={role.code} value={role.code}>{locale === "ar" ? role.name_ar : role.name_en}</option>)}</select>
          <button className={item.is_active ? "deactivate" : "activate"} onClick={() => status.mutate({ userId: item.user_id, active: !item.is_active })}>{item.is_active ? (locale === "ar" ? "تعطيل" : "Disable") : (locale === "ar" ? "تفعيل" : "Enable")}</button>
        </article>)}</div>
      </section>
    </section>
  </div>;
}
