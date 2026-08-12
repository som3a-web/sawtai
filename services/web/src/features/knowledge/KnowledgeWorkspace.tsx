import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import { deleteJson, getJson, postForm, postJson } from "../../api/client";
import type { AuthUser, DocumentKind, KnowledgeDetail, KnowledgeListData, KnowledgeSearchData } from "../../api/types";
import type { Locale } from "../../app/types";
import { LoadingCard } from "../../components/LoadingCard";
import "./knowledge.css";

const kinds: DocumentKind[] = ["policy", "service_guide", "faq", "legal", "tone_of_voice", "press_release", "template"];
const blankForm = { kind: "service_guide" as DocumentKind, title_ar: "", title_en: "", lang: "ar", version: "1", effective_from: "", heading_path: "", content: "" };

function can(user: AuthUser, permission: string) {
  const namespace = permission.split(":")[0];
  return user.permissions.includes(permission) || user.permissions.includes(`${namespace}:*`);
}

function kindLabel(kind: DocumentKind, locale: Locale) {
  const labels: Record<DocumentKind, [string, string]> = {
    policy: ["سياسة", "Policy"], press_release: ["بيان صحفي", "Press release"], faq: ["أسئلة شائعة", "FAQ"],
    tone_of_voice: ["دليل النبرة", "Tone of voice"], service_guide: ["دليل خدمة", "Service guide"], legal: ["مرجع قانوني", "Legal"], template: ["قالب", "Template"],
  };
  return labels[kind][locale === "ar" ? 0 : 1];
}

export function KnowledgeWorkspace({ locale, user }: { locale: Locale; user: AuthUser }) {
  const queryClient = useQueryClient();
  const [selected, setSelected] = useState<string | null>(null);
  const [showCreate, setShowCreate] = useState(false);
  const [form, setForm] = useState(blankForm);
  const [uploadFile, setUploadFile] = useState<File | null>(null);
  const [searchText, setSearchText] = useState("");
  const [notice, setNotice] = useState("");
  const documents = useQuery({ queryKey: ["knowledge-documents"], queryFn: () => getJson<KnowledgeListData>("/api/v1/documents") });
  const detail = useQuery({ queryKey: ["knowledge-document", selected], queryFn: () => getJson<KnowledgeDetail>(`/api/v1/documents/${selected}`), enabled: Boolean(selected) });
  useEffect(() => { if (!selected && documents.data?.items[0]) setSelected(documents.data.items[0].document_id); }, [documents.data, selected]);

  async function refresh(documentId?: string) {
    await queryClient.invalidateQueries({ queryKey: ["knowledge-documents"] });
    if (documentId) await queryClient.invalidateQueries({ queryKey: ["knowledge-document", documentId] });
  }
  const create = useMutation({
    mutationFn: async () => {
      if (uploadFile) {
        const body = new FormData();
        body.append("file", uploadFile);
        body.append("kind", form.kind);
        body.append("title_ar", form.title_ar);
        if (form.title_en) body.append("title_en", form.title_en);
        body.append("lang", form.lang);
        body.append("version", form.version);
        if (form.effective_from) body.append("effective_from", form.effective_from);
        const response = await postForm("/api/v1/documents/upload", body);
        return response.json() as Promise<{ document_id: string; extraction_method: string; chunks: number }>;
      }
      const response = await postJson("/api/v1/documents", { ...form, title_en: form.title_en || null, effective_from: form.effective_from || null, heading_path: form.heading_path || null });
      return response.json() as Promise<{ document_id: string; extraction_method?: string; chunks?: number }>;
    },
    onSuccess: async (result) => { setForm(blankForm); setUploadFile(null); setShowCreate(false); setSelected(result.document_id); setNotice(locale === "ar" ? "تم الاستخراج والفهرسة وبانتظار اعتماد مستقل" : "Extracted and indexed; awaiting independent approval"); await refresh(); },
  });
  const approve = useMutation({ mutationFn: (id: string) => postJson(`/api/v1/documents/${id}/approve`, {}), onSuccess: async (_, id) => { setNotice(locale === "ar" ? "تم اعتماد المصدر وأصبح متاحاً للذكاء الاصطناعي" : "Source approved and available to AI"); await refresh(id); } });
  const reindex = useMutation({ mutationFn: (id: string) => postJson(`/api/v1/documents/${id}/reindex`, {}), onSuccess: async (_, id) => { setNotice(locale === "ar" ? "تمت إعادة الفهرسة" : "Source reindexed"); await refresh(id); } });
  const retry = useMutation({ mutationFn: (id: string) => postJson(`/api/v1/documents/${id}/retry`, {}), onSuccess: async (_, id) => { setNotice(locale === "ar" ? "نجحت إعادة المعالجة" : "Processing retry succeeded"); await refresh(id); } });
  const retire = useMutation({ mutationFn: (id: string) => deleteJson(`/api/v1/documents/${id}`), onSuccess: async (_, id) => { setNotice(locale === "ar" ? "تم إيقاف المصدر مع حفظ سجل الاستشهادات" : "Source retired with citation history preserved"); await refresh(id); } });
  const search = useMutation({
    mutationFn: async () => { const response = await postJson("/api/v1/search/documents", { query: searchText, limit: 5 }); return response.json() as Promise<KnowledgeSearchData>; },
  });
  const current = detail.data;
  const summary = documents.data?.summary;
  if (documents.isLoading) return <LoadingCard />;

  return <div className="page-stack knowledge-page">
    <header className="page-heading"><div><span className="eyebrow">GOVERNED KNOWLEDGE</span><h2>{locale === "ar" ? "مصادر المعرفة المعتمدة" : "Approved knowledge sources"}</h2><p>{locale === "ar" ? "كل إجابة تبدأ من مصدر موثوق، وتبقى قابلة للتتبع والمراجعة." : "Every AI answer starts from a trusted, traceable and reviewable source."}</p></div>{can(user, "doc:create") && <button className="kb-add" onClick={() => setShowCreate(!showCreate)}>+ {locale === "ar" ? "إضافة مصدر" : "Add source"}</button>}</header>
    <section className="kb-pulse"><div><b>{summary?.approved ?? 0}</b><span>{locale === "ar" ? "مصادر نشطة" : "active sources"}</span></div><i /><div><b>{summary?.pending ?? 0}</b><span>{locale === "ar" ? "بانتظار الاعتماد" : "awaiting approval"}</span></div><i /><div><b>{summary?.chunks ?? 0}</b><span>{locale === "ar" ? "مقاطع قابلة للاسترجاع" : "retrievable chunks"}</span></div><em>✓ {locale === "ar" ? "الاسترجاع محصور بالمحتوى المعتمد" : "Retrieval is approved-content only"}</em></section>
    {notice && <div className="kb-notice">✓ {notice}<button onClick={() => setNotice("")}>×</button></div>}
    {showCreate && <form className="panel kb-create" onSubmit={(event) => { event.preventDefault(); create.mutate(); }}><header><div><span className="eyebrow">NEW SOURCE VERSION</span><h3>{locale === "ar" ? "إضافة محتوى موثوق" : "Add trusted content"}</h3></div><button type="button" onClick={() => setShowCreate(false)}>×</button></header><div className="kb-form-grid">
      <label><span>{locale === "ar" ? "العنوان بالعربية" : "Arabic title"}</span><input required minLength={3} value={form.title_ar} onChange={(event) => setForm({ ...form, title_ar: event.target.value })} /></label>
      <label><span>{locale === "ar" ? "العنوان بالإنجليزية" : "English title"}</span><input value={form.title_en} onChange={(event) => setForm({ ...form, title_en: event.target.value })} /></label>
      <label><span>{locale === "ar" ? "نوع المصدر" : "Source type"}</span><select value={form.kind} onChange={(event) => setForm({ ...form, kind: event.target.value as DocumentKind })}>{kinds.map((kind) => <option value={kind} key={kind}>{kindLabel(kind, locale)}</option>)}</select></label>
      <label><span>{locale === "ar" ? "الإصدار" : "Version"}</span><input required value={form.version} onChange={(event) => setForm({ ...form, version: event.target.value })} /></label>
      <label><span>{locale === "ar" ? "ساري من" : "Effective from"}</span><input type="date" value={form.effective_from} onChange={(event) => setForm({ ...form, effective_from: event.target.value })} /></label>
      <label><span>{locale === "ar" ? "مسار القسم" : "Section path"}</span><input placeholder={locale === "ar" ? "الخدمات > المتابعة" : "Services > Follow-up"} value={form.heading_path} onChange={(event) => setForm({ ...form, heading_path: event.target.value })} /></label>
    </div><label className="kb-content"><span>{uploadFile ? (locale === "ar" ? "سيُستخرج المحتوى من الملف" : "Content will be extracted from the file") : (locale === "ar" ? "أو الصق محتوى نصياً أو Markdown" : "Or paste text or Markdown content")}</span><textarea required={!uploadFile} minLength={20} disabled={Boolean(uploadFile)} value={form.content} onChange={(event) => setForm({ ...form, content: event.target.value })} /></label><div className="kb-upload"><label><input type="file" accept=".pdf,.docx,.txt,.md,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document,text/plain,text/markdown" onChange={(event) => { const file = event.target.files?.[0] ?? null; setUploadFile(file); if (file) setForm((value) => ({ ...value, title_en: value.title_en || file.name.replace(/\.(pdf|docx|txt|md)$/i, "") })); }} /><span>⇧ {uploadFile ? uploadFile.name : (locale === "ar" ? "تحميل PDF أو DOCX أو ملف نصي" : "Upload PDF, DOCX, or text")}</span></label><small>{uploadFile ? `${(uploadFile.size / 1_048_576).toFixed(2)} MB · ${locale === "ar" ? "فحص أمني واستخراج تلقائي" : "security scan + automatic extraction"}` : (locale === "ar" ? "يدعم OCR العربي للملفات الممسوحة، بحد أقصى 15 MB." : "Arabic OCR for scanned PDFs, up to 15 MB.")}</small><button className="kb-submit" disabled={create.isPending || (!uploadFile && form.content.trim().length < 20)}>{create.isPending ? (locale === "ar" ? "جارٍ الاستخراج والفهرسة…" : "Extracting and indexing…") : (locale === "ar" ? "معالجة وإضافة" : "Process and add")}</button></div>{create.error && <div className="login-error">{create.error.message}</div>}</form>}
    <section className="kb-layout">
      <aside className="panel kb-library"><header><div><span className="eyebrow">SOURCE LIBRARY</span><h3>{locale === "ar" ? "المكتبة" : "Library"}</h3></div><b>{summary?.total ?? 0}</b></header><div className="kb-list">{documents.data?.items.map((item) => <button key={item.document_id} className={selected === item.document_id ? "selected" : ""} onClick={() => setSelected(item.document_id)}><span className={`kb-status ${item.ingestion_status === "failed" || item.is_retired ? "retired" : item.is_retrievable ? "approved" : "pending"}`}>{item.ingestion_status === "failed" ? "!" : item.is_retired ? "×" : item.is_retrievable ? "✓" : "◷"}</span><div><b>{locale === "ar" ? item.title_ar : item.title_en ?? item.title_ar}</b><small>{kindLabel(item.kind, locale)} · v{item.version}</small><em>{item.ingestion_status === "failed" ? (locale === "ar" ? "فشل المعالجة" : "processing failed") : `${item.chunk_count} ${locale === "ar" ? "مقاطع" : "chunks"}`}</em></div></button>)}</div></aside>
      <main className="panel kb-detail">{detail.isLoading ? <LoadingCard /> : current ? <><header><div><span className="eyebrow">SOURCE PROVENANCE</span><h3>{locale === "ar" ? current.title_ar : current.title_en ?? current.title_ar}</h3><p>{current.title_en && locale === "ar" ? current.title_en : current.title_ar}</p></div><span className={`kb-state ${current.ingestion_status === "failed" || current.is_retired ? "retired" : current.is_retrievable ? "approved" : "pending"}`}>{current.ingestion_status === "failed" ? (locale === "ar" ? "فشل الاستخراج" : "Processing failed") : current.is_retired ? (locale === "ar" ? "متوقف" : "Retired") : current.is_retrievable ? (locale === "ar" ? "معتمد" : "Approved") : current.is_approved ? (locale === "ar" ? "مجدول" : "Scheduled") : (locale === "ar" ? "بانتظار الاعتماد" : "Pending approval")}</span></header><div className={`kb-processing ${current.ingestion_status}`}><span>{current.ingestion_status === "failed" ? "!" : "✓"}</span><div><b>{current.ingestion_status === "failed" ? current.ingestion_error : (locale === "ar" ? "اكتمل الاستخراج والفهرسة" : "Extraction and indexing complete")}</b><small>{current.extraction_method ?? "manual_text"} · {current.embedding_provider ?? "local-hash-fallback-v1"} · {current.storage_backend ?? "prototype"}</small></div></div><div className="kb-meta"><div><small>{locale === "ar" ? "النوع" : "Type"}</small><b>{kindLabel(current.kind, locale)}</b></div><div><small>{locale === "ar" ? "الإصدار" : "Version"}</small><b>{current.version}</b></div><div><small>{locale === "ar" ? "المقاطع" : "Chunks"}</small><b>{current.chunks.length}</b></div><div><small>SHA-256</small><b>{current.sha256.slice(0, 12)}…</b></div></div><div className="kb-chunks"><header><b>{locale === "ar" ? "المحتوى المفهرس" : "Indexed content"}</b><small>{locale === "ar" ? "المقاطع التي يراها نموذج الاسترجاع" : "Exactly what retrieval can inspect"}</small></header>{current.chunks.map((chunk) => <article key={chunk.chunk_id}><span>0{chunk.seq}</span><div><small>{chunk.heading_path ?? (locale === "ar" ? "قسم عام" : "General section")}</small><p><bdi>{chunk.text}</bdi></p><em>{chunk.token_count} tokens</em></div></article>)}</div><footer className="kb-actions"><div><small>{locale === "ar" ? "أنشأه" : "Created by"}</small><b>{locale === "ar" ? current.creator_name_ar ?? "—" : current.creator_name_en ?? "—"}</b></div>{can(user, "doc:reindex") && current.ingestion_status === "failed" && <button className="approve" onClick={() => retry.mutate(current.document_id)} disabled={retry.isPending}>{locale === "ar" ? "إعادة المحاولة" : "Retry processing"}</button>}{can(user, "doc:reindex") && current.ingestion_status === "indexed" && !current.is_retired && <button onClick={() => reindex.mutate(current.document_id)} disabled={reindex.isPending}>{locale === "ar" ? "إعادة الفهرسة" : "Reindex"}</button>}{can(user, "doc:approve") && current.ingestion_status === "indexed" && !current.is_approved && !current.is_retired && current.created_by !== user.user_id && <button className="approve" onClick={() => approve.mutate(current.document_id)} disabled={approve.isPending}>✓ {locale === "ar" ? "اعتماد المصدر" : "Approve source"}</button>}{can(user, "doc:retire") && !current.is_retired && <button className="retire" onClick={() => retire.mutate(current.document_id)} disabled={retire.isPending}>{locale === "ar" ? "إيقاف" : "Retire"}</button>}</footer></> : <div className="notification-empty">{locale === "ar" ? "لا توجد مصادر" : "No sources"}</div>}</main>
      <aside className="panel kb-lab"><span className="eyebrow">HYBRID RETRIEVAL LAB</span><h3>{locale === "ar" ? "اختبر إجابة الذكاء" : "Test AI retrieval"}</h3><p>{locale === "ar" ? "بحث دلالي وكلمات مفتاحية مع إعادة ترتيب النتائج قبل إنشاء الرد." : "Semantic and keyword search with reranking before a reply is generated."}</p><textarea value={searchText} onChange={(event) => setSearchText(event.target.value)} placeholder={locale === "ar" ? "متى يتم جمع النفايات؟" : "When is waste collected?"} /><button disabled={searchText.trim().length < 2 || search.isPending} onClick={() => search.mutate()}>✦ {search.isPending ? (locale === "ar" ? "جارٍ البحث…" : "Searching…") : (locale === "ar" ? "فحص الاسترجاع" : "Inspect retrieval")}</button>{search.data && <div className={`kb-gate ${search.data.gate.passed ? "pass" : "fail"}`}><header><b>{search.data.gate.passed ? "✓" : "!"} {search.data.gate.passed ? (locale === "ar" ? "يوجد دعم موثوق" : "Grounding available") : (locale === "ar" ? "توقف آمن" : "Safe abstention")}</b><span>{Math.round(search.data.gate.top_score * 100)}%</span></header>{search.data.results.map((result) => <article key={result.chunk_id}><b>{locale === "ar" ? result.document.title_ar : result.document.title_en ?? result.document.title_ar}</b><small>{result.heading_path}</small><p>{result.text}</p><div className="kb-score-row"><span>D {Math.round(result.scores.dense * 100)}</span><span>S {Math.round(result.scores.sparse * 100)}</span><span>R {Math.round(result.scores.rerank * 100)}</span></div><em>{result.models.embedding}</em></article>)}</div>}</aside>
    </section>
  </div>;
}
