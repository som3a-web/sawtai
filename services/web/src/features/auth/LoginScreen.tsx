import { useState } from "react";

import { login } from "../../api/client";
import type { AuthUser } from "../../api/types";
import type { Locale } from "../../app/types";

const accounts = [
  { email: "officer@sawtai.ae", ar: "مسؤول الاتصال", en: "Communication Officer" },
  { email: "approver@sawtai.ae", ar: "رئيس القسم", en: "Department Head" },
  { email: "crisis@sawtai.ae", ar: "مسؤول الأزمات", en: "Crisis Lead" },
  { email: "admin@sawtai.ae", ar: "مدير النظام", en: "System Administrator" },
  { email: "dpo@sawtai.ae", ar: "حماية البيانات", en: "Data Steward" },
];

export function LoginScreen({ locale, onLocale, onAuthenticated }: {
  locale: Locale;
  onLocale: () => void;
  onAuthenticated: (user: AuthUser) => void;
}) {
  const [email, setEmail] = useState(accounts[0].email);
  const [password, setPassword] = useState("SawtAI-2026!");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      const result = await login(email, password);
      onAuthenticated(result.user);
    } catch {
      setError(locale === "ar" ? "تعذر تسجيل الدخول. تحقق من البيانات." : "Sign-in failed. Check your credentials.");
    } finally {
      setBusy(false);
    }
  }

  return <div className="login-shell" dir={locale === "ar" ? "rtl" : "ltr"}>
    <button className="login-locale" onClick={onLocale}>{locale === "ar" ? "EN" : "عربي"}</button>
    <section className="login-story">
      <div className="brand login-brand"><div className="brand-mark"><i /><i /><i /></div><div><strong>صوتي</strong><span>SawtAI</span></div></div>
      <div className="login-orbit"><i /><i /><i /><span>ص</span></div>
      <p>{locale === "ar" ? "ذكاء اتصال حكومي آمن، واضح، ومسؤول." : "Secure, clear, and accountable government communication intelligence."}</p>
      <div className="login-trust"><span>✓ {locale === "ar" ? "صلاحيات حسب الدور" : "Role-based access"}</span><span>✓ {locale === "ar" ? "اعتماد بشري مزدوج" : "Two-person approval"}</span><span>✓ {locale === "ar" ? "سجل تدقيق كامل" : "Complete audit trail"}</span></div>
    </section>
    <form className="login-card" onSubmit={submit}>
      <span className="eyebrow">SECURE WORKSPACE</span>
      <h1>{locale === "ar" ? "مرحباً بعودتك" : "Welcome back"}</h1>
      <p>{locale === "ar" ? "اختر حساباً تجريبياً لمشاهدة تجربة كل دور." : "Choose a demo account to experience each role."}</p>
      <div className="demo-accounts">{accounts.map((account) => <button type="button" key={account.email} className={email === account.email ? "active" : ""} onClick={() => setEmail(account.email)}><b>{locale === "ar" ? account.ar : account.en}</b><small>{account.email}</small></button>)}</div>
      <label><span>{locale === "ar" ? "البريد الإلكتروني" : "Email"}</span><input type="email" value={email} onChange={(event) => setEmail(event.target.value)} autoComplete="username" /></label>
      <label><span>{locale === "ar" ? "كلمة المرور" : "Password"}</span><input type="password" value={password} onChange={(event) => setPassword(event.target.value)} autoComplete="current-password" /></label>
      {error && <div className="login-error">{error}</div>}
      <button className="login-submit" disabled={busy}>{busy ? (locale === "ar" ? "جارٍ الدخول…" : "Signing in…") : (locale === "ar" ? "الدخول إلى مساحة العمل" : "Enter workspace")}</button>
      <small className="login-note">{locale === "ar" ? "النموذج يستخدم بيانات اصطناعية فقط" : "Prototype uses synthetic data only"}</small>
    </form>
  </div>;
}
