import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { getJson } from "../../api/client";
import type { DataRowsData, DataTablesData } from "../../api/types";
import type { Locale } from "../../app/types";
import { KpiCard } from "../../components/KpiCard";
import { LoadingCard } from "../../components/LoadingCard";
import { copy } from "../../i18n/copy";
import { formatCell } from "./format";

export function DataExplorer({ locale }: { locale: Locale }) {
  const [selectedTable, setSelectedTable] = useState("messages");
  const tables = useQuery({ queryKey: ["data-tables"], queryFn: () => getJson<DataTablesData>("/api/v1/data/tables") });
  const rows = useQuery({ queryKey: ["data-rows", selectedTable], queryFn: () => getJson<DataRowsData>(`/api/v1/data/tables/${selectedTable}?limit=50`) });
  if (!tables.data) return <LoadingCard />;
  const selected = tables.data.items.find((item) => item.name === selectedTable);
  const totalRows = tables.data.items.reduce((sum, item) => sum + item.row_count, 0);
  return (
    <div className="page-stack">
      <header className="page-heading">
        <div><span className="eyebrow">POSTGRESQL · TENANT SCOPED</span><h2>{copy[locale].data}</h2><p>{locale === "ar" ? "عرض مباشر وآمن للبيانات التي تشغّل المنصة" : "A safe, live view of the data powering the platform"}</p></div>
        <div className="replay-badge"><i /> {locale === "ar" ? "قراءة فقط" : "READ ONLY"}</div>
      </header>
      <section className="data-summary">
        <KpiCard label={locale === "ar" ? "قاعدة البيانات" : "Database"} value={tables.data.database} note="PostgreSQL 16" />
        <KpiCard label={locale === "ar" ? "الجداول المتاحة" : "Available tables"} value={`${tables.data.items.length}`} note="core schema" tone="gold" />
        <KpiCard label={locale === "ar" ? "إجمالي السجلات" : "Total records"} value={totalRows.toLocaleString(locale === "ar" ? "ar-AE" : "en-AE")} note={locale === "ar" ? "ضمن نطاق الجهة" : "tenant scoped"} tone="ink" />
      </section>
      <section className="data-layout">
        <aside className="data-catalog panel">
          <div className="data-catalog-head"><span className="eyebrow">CORE SCHEMA</span><b>{tables.data.items.length}</b></div>
          {tables.data.items.map((table) => <button key={table.name} className={selectedTable === table.name ? "active" : ""} onClick={() => setSelectedTable(table.name)}><span><strong>{locale === "ar" ? table.label_ar : table.label_en}</strong><code>core.{table.name}</code></span><b>{table.row_count.toLocaleString(locale === "ar" ? "ar-AE" : "en-AE")}</b></button>)}
        </aside>
        <article className="data-preview panel">
          <div className="data-preview-head"><div><span className="eyebrow">TABLE PREVIEW</span><h3>{locale === "ar" ? selected?.label_ar : selected?.label_en}</h3><p>{locale === "ar" ? selected?.description_ar : selected?.description_en}</p></div><code>core.{selectedTable}</code></div>
          {rows.isLoading ? <LoadingCard /> : rows.data && rows.data.rows.length > 0 ? <div className="data-table-wrap"><table className="data-table"><thead><tr>{rows.data.columns.map((column) => <th key={column}>{column}</th>)}</tr></thead><tbody>{rows.data.rows.map((row, rowIndex) => <tr key={rowIndex}>{rows.data.columns.map((column) => <td key={column}><bdi>{formatCell(row[column])}</bdi></td>)}</tr>)}</tbody></table></div> : <div className="data-empty">{locale === "ar" ? "لا توجد سجلات في هذا الجدول" : "No records in this table"}</div>}
          <footer className="data-footer"><span>ⓘ {locale === "ar" ? "الحقول الحساسة والمخطط المقيّد غير معروضين" : "Sensitive fields and the restricted schema are hidden"}</span><b>{locale === "ar" ? "آخر 50 سجلاً" : "Latest 50 rows"}</b></footer>
        </article>
      </section>
    </div>
  );
}
