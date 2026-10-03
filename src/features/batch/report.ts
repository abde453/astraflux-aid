import { jsPDF } from "jspdf";
import autoTable from "jspdf-autotable";
import { BatchResult } from "./types";

const k3 = (x: number) => x.toLocaleString("en-US", { minimumFractionDigits: 3, maximumFractionDigits: 3 });

/** Everything the PDF/CSV needs, built ONLY from the calculated result object (never from constants or live form fields). */
export function buildReportPayload(r: BatchResult) {
  const i = r.input;
  return {
    title: i.product, // <- the product typed by the user, exactly as it was calculated
    heading: "DRAFT calculation sheet - not an approved batch record",
    header: [
      ["Product", i.product], ["Requested", `${i.requestedUnits.toLocaleString("en-US")} ${i.unitLabel}`], ["Handling loss", `${i.lossPct} %`],
      ["Planned units", r.plannedUnits.toLocaleString("en-US")], ["Unit mass", `${r.unitMassMg} mg`], ["Assay basis", i.assayBasis === "dried" ? "dried (assay + LOD)" : "as is (assay only)"],
      ["Calculated at", r.calculatedAt], ["Batch no.", ""],
    ] as [string, string][],
    columns: ["Ingredient", "Role", "Assay %", "LOD %", "Factor", "Theoretical (kg)", "Actual weight (kg)", "Difference (kg)"],
    rows: r.lines.map((l) => [l.name + (l.compensating ? " (compensating)" : ""), l.role, String(l.assayPct), String(l.lodPct), l.factor.toFixed(4), k3(l.theoreticalKg), k3(l.actualKg), (l.differenceKg > 0 ? "+" : "") + k3(l.differenceKg)]),
    totals: ["Total", "", "", "", "", k3(r.totals.theoreticalKg), k3(r.totals.actualKg), k3(r.totals.differenceKg)],
    warnings: r.warnings, formulas: r.formulas,
    signatures: ["Prepared by (name / signature / date)", "Checked by (name / signature / date)", "QA approval (name / signature / date)"],
    disclaimer: "Draft calculation aid. Not a validated GMP/BPR system; verify and approve under your quality system.",
  };
}
export type ReportPayload = ReturnType<typeof buildReportPayload>;

export function buildPdf(p: ReportPayload): jsPDF {
  const doc = new jsPDF({ unit: "mm", format: "a4" });
  doc.setFontSize(14); doc.text(p.heading, 14, 16);
  doc.setFontSize(10); doc.text(p.title, 14, 23);
  autoTable(doc, { startY: 28, body: p.header.map(([k, v]) => [k, v]), theme: "grid", styles: { fontSize: 9 }, columnStyles: { 0: { fontStyle: "bold", cellWidth: 40 } } });
  autoTable(doc, { startY: (doc as any).lastAutoTable.finalY + 6, head: [p.columns], body: [...p.rows, p.totals], theme: "grid", styles: { fontSize: 8 }, headStyles: { fillColor: [31, 95, 191] } });
  let y = (doc as any).lastAutoTable.finalY + 6;
  doc.setFontSize(9);
  p.warnings.forEach((w) => { doc.text(`Warning: ${w}`, 14, y, { maxWidth: 182 }); y += 6; });
  autoTable(doc, { startY: y + 4, head: [p.signatures], body: [["", "", ""]], theme: "grid", styles: { fontSize: 8, minCellHeight: 22 } });
  doc.setFontSize(8); doc.text(p.disclaimer, 14, (doc as any).lastAutoTable.finalY + 8, { maxWidth: 182 });
  return doc;
}
export const exportPdf = (r: BatchResult) => buildPdf(buildReportPayload(r)).save(`batch_${r.input.product.replace(/[^\w]+/g, "_")}.pdf`);

export function buildCsv(r: BatchResult): string {
  const p = buildReportPayload(r); const q = (v: string) => `"${v.replace(/"/g, '""')}"`;
  return [p.columns, ...p.rows, p.totals].map((row) => row.map(q).join(",")).join("\r\n");
}
