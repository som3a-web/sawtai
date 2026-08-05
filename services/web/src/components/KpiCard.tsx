interface KpiCardProps {
  label: string;
  value: string;
  note: string;
  tone?: string;
}

export function KpiCard({ label, value, note, tone = "teal" }: KpiCardProps) {
  return (
    <article className={`kpi ${tone}`}>
      <div className="kpi-orb" />
      <p>{label}</p>
      <strong>{value}</strong>
      <small>{note}</small>
    </article>
  );
}
