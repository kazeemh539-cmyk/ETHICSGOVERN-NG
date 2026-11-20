import { useEffect, useRef } from "react";
import Chart from "chart.js/auto";

Chart.defaults.font.family = "'Segoe UI', Calibri, Arial, sans-serif";
Chart.defaults.font.size = 12;
Chart.defaults.color = "#3C4F68";

export function ChartCanvas({ config, height = 220 }) {
  const ref = useRef(null);
  const inst = useRef(null);
  useEffect(() => {
    if (inst.current) inst.current.destroy();
    inst.current = new Chart(ref.current, config);
    return () => inst.current && inst.current.destroy();
  }, [JSON.stringify(config)]);
  return <div style={{ position: "relative", height }}><canvas ref={ref} /></div>;
}

export const COLORS = { navy: "#1F3A5F", teal: "#1C8C84", orange: "#D9822B", red: "#C0392B", grey: "#A9B4C4", green: "#2E8B57" };

export function ApprovalChart({ women, men }) {
  return <ChartCanvas height={210} config={{
    type: "bar",
    data: { labels: ["Women", "Men"], datasets: [{ data: [women * 100, men * 100], backgroundColor: [COLORS.orange, COLORS.navy], borderRadius: 4, barThickness: 64 }] },
    options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false }, tooltip: { callbacks: { label: (c) => c.parsed.y.toFixed(1) + "% approved" } } },
      scales: { y: { beginAtZero: true, max: 100, title: { display: true, text: "Approval rate (%)" }, grid: { color: "#E6EBF2" } }, x: { grid: { display: false } } } },
  }} />;
}

export function DirTrend({ runs, threshold }) {
  const pts = [...runs].reverse().filter((r) => r.metrics.fairness.di_ratio != null);
  return <ChartCanvas height={210} config={{
    type: "line",
    data: { labels: pts.map((r) => "#" + r.run_id),
      datasets: [
        { label: "Disparate impact ratio", data: pts.map((r) => r.metrics.fairness.di_ratio), borderColor: COLORS.navy, backgroundColor: COLORS.navy, tension: 0.25, pointRadius: 4 },
        { label: "Minimum " + threshold.toFixed(2), data: pts.map(() => threshold), borderColor: COLORS.red, borderDash: [6, 5], pointRadius: 0 },
      ] },
    options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { position: "bottom" } },
      scales: { y: { min: 0, suggestedMax: 1.2, grid: { color: "#E6EBF2" } }, x: { title: { display: true, text: "Monitoring run" }, grid: { display: false } } } },
  }} />;
}

export function AttributionChart({ attributions, features, unit }) {
  const entries = Object.entries(attributions).sort((a, b) => Math.abs(b[1]) - Math.abs(a[1]));
  const label = (k) => {
    const nice = { credit_score: "Credit score", income: "Income", loan_amount: "Loan amount", age: "Age", gender_f: "Gender (female)" }[k] || k;
    let v = features[k === "gender_f" ? "gender" : k];
    if (k === "income" || k === "loan_amount") v = "₦" + Math.round(v).toLocaleString();
    if (k === "gender_f") v = v === "F" ? "F" : "M";
    return nice + " = " + v;
  };
  return <ChartCanvas height={230} config={{
    type: "bar",
    data: { labels: entries.map(([k]) => label(k)), datasets: [{ data: entries.map(([, v]) => v),
      backgroundColor: entries.map(([, v]) => (v >= 0 ? COLORS.teal : COLORS.orange)), borderRadius: 3 }] },
    options: { indexAxis: "y", responsive: true, maintainAspectRatio: false,
      plugins: { legend: { display: false }, tooltip: { callbacks: { label: (c) => (c.parsed.x >= 0 ? "+" : "") + c.parsed.x.toFixed(3) + " " + unit } } },
      scales: { x: { title: { display: true, text: "← pushes toward decline | pushes toward approval →" }, grid: { color: "#E6EBF2" } }, y: { grid: { display: false } } } },
  }} />;
}
