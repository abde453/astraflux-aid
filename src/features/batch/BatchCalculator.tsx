import { ROLES } from "./types";
import { useBatchForm } from "./useBatchForm";
import { buildCsv, exportPdf } from "./report";

const k3 = (x: number) => x.toLocaleString("en-US", { minimumFractionDigits: 3, maximumFractionDigits: 3 });
const inp = "w-full rounded border px-2 py-1"; // swap for your shadcn <Input/> if you use it

export default function BatchCalculator() {
  const f = useBatchForm();
  const { form, rows, result, error, isStale } = f;
  const canExport = result !== null && !isStale;

  const downloadCsv = () => {
    if (!result) return;
    const a = document.createElement("a"); a.href = URL.createObjectURL(new Blob([buildCsv(result)], { type: "text/csv" }));
    a.download = "batch.csv"; a.click();
  };

  return (
    <section aria-label="Batch calculator" className="space-y-4">
      <p className="text-sm text-muted-foreground">Draft calculation aid - not a validated GMP/BPR system. Results must be reviewed by qualified personnel.</p>
      <div className="flex gap-2">
        <button type="button" onClick={f.loadExample}>Load example (Paracetamol 500 mg)</button>
        <button type="button" onClick={f.clear}>Clear form</button>
      </div>

      <div className="grid grid-cols-2 gap-3 md:grid-cols-5">
        <label>Product<input className={inp} value={form.product} onChange={(e) => f.setField("product", e.target.value)} /></label>
        <label>Requested units<input className={inp} inputMode="numeric" value={form.requestedUnits} onChange={(e) => f.setField("requestedUnits", e.target.value)} /></label>
        <label>Unit label<input className={inp} value={form.unitLabel} onChange={(e) => f.setField("unitLabel", e.target.value)} /></label>
        <label>Handling loss %<input className={inp} inputMode="decimal" value={form.lossPct} onChange={(e) => f.setField("lossPct", e.target.value)} /></label>
        <label>Assay basis
          <select className={inp} value={form.assayBasis} onChange={(e) => f.setField("assayBasis", e.target.value)}>
            <option value="dried">Dried basis (assay + LOD)</option><option value="as_is">As-is (assay only)</option>
          </select>
        </label>
      </div>

      <table className="w-full text-sm">
        <thead><tr><th>Ingredient</th><th>Role</th><th>mg / unit</th><th>Assay %</th><th>LOD %</th><th>Compensates</th><th /></tr></thead>
        <tbody>
          {rows.map((r, idx) => (
            <tr key={r.id /* stable id, NOT the index */}>
              <td><input className={inp} aria-label={`Ingredient name ${idx + 1}`} value={r.name} onChange={(e) => f.setRow(r.id, "name", e.target.value)} /></td>
              <td>
                <select className={inp} aria-label={`Role ${idx + 1}`} value={r.role} onChange={(e) => f.setRow(r.id, "role", e.target.value)}>
                  {ROLES.map((x) => <option key={x}>{x}</option>)}
                </select>
              </td>
              <td><input className={inp} aria-label={`mg per unit ${idx + 1}`} inputMode="decimal" value={r.mgPerUnit} onChange={(e) => f.setRow(r.id, "mgPerUnit", e.target.value)} /></td>
              <td><input className={inp} aria-label={`Assay ${idx + 1}`} inputMode="decimal" value={r.assayPct} onChange={(e) => f.setRow(r.id, "assayPct", e.target.value)} /></td>
              <td><input className={inp} aria-label={`LOD ${idx + 1}`} inputMode="decimal" value={r.lodPct} onChange={(e) => f.setRow(r.id, "lodPct", e.target.value)} /></td>
              <td className="text-center">
                {/* checked={...} + onChange: a CONTROLLED checkbox; the boolean comes from state, not from e.target.value */}
                <input type="checkbox" aria-label={`Compensates ${idx + 1}`} checked={r.compensates} disabled={r.role === "API"} onChange={() => f.toggleCompensator(r.id)} />
              </td>
              <td><button type="button" aria-label={`Remove ${idx + 1}`} onClick={() => f.removeRow(r.id)}>✕</button></td>
            </tr>
          ))}
        </tbody>
      </table>
      <div className="flex gap-2">
        <button type="button" onClick={f.addRow}>Add ingredient</button>
        <button type="button" onClick={f.calculate}>Calculate batch</button>
      </div>

      {error && <p role="alert" className="text-red-600">{error}</p>}
      {isStale && <p role="status" className="font-semibold text-red-600">Inputs changed after the last calculation. Click "Calculate batch" again before exporting.</p>}

      {result && (
        <div className={isStale ? "opacity-40" : ""} aria-label="Batch result">
          <h3>{result.input.product}</h3>
          <p>Planned units: {result.plannedUnits.toLocaleString("en-US")} - Calculation date: {result.calculatedAt.slice(0, 10)}</p>
          <table className="w-full text-sm">
            <thead><tr><th>Ingredient</th><th>Role</th><th>Theoretical (kg)</th><th>Actual weight (kg)</th><th>Difference (kg)</th></tr></thead>
            <tbody>
              {result.lines.map((l) => (
                <tr key={l.name}><td>{l.name}{l.compensating ? " (compensating)" : ""}</td><td>{l.role}</td><td>{k3(l.theoreticalKg)}</td><td><b>{k3(l.actualKg)}</b></td><td>{k3(l.differenceKg)}</td></tr>
              ))}
              <tr><td><b>Total</b></td><td /><td>{k3(result.totals.theoreticalKg)}</td><td><b>{k3(result.totals.actualKg)}</b></td><td>{k3(result.totals.differenceKg)}</td></tr>
            </tbody>
          </table>
          {result.warnings.map((w) => <p key={w} className="text-amber-700">Warning: {w}</p>)}
          <div className="flex gap-2">
            <button type="button" disabled={!canExport} onClick={() => exportPdf(result)}>Export PDF</button>
            <button type="button" disabled={!canExport} onClick={downloadCsv}>Export CSV</button>
          </div>
        </div>
      )}
    </section>
  );
}
