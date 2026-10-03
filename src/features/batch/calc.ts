import { BatchError, BatchFormData, BatchInput, BatchResult, IngredientRow, ROLES } from "./types";

export const FORMULAS = [
  "Planned units = ceil(requested units x (1 + loss % / 100))",
  "Theoretical kg = planned units x mg per unit / 1,000,000",
  "Correction factor = 100/Assay x 100/(100 - LOD)  [basis 'dried'];  100/Assay  [basis 'as is']",
  "Actual kg (normal line) = theoretical kg x correction factor",
  "Compensating filler actual kg = total theoretical kg - sum of the other lines' actual kg (batch total stays constant)",
];
const r6 = (x: number) => Math.round(x * 1e6) / 1e6;

function num(label: string, raw: string): number {
  const v = Number(raw.trim().replace(",", "."));
  if (raw.trim() === "" || !Number.isFinite(v)) throw new BatchError(`${label}: enter a valid number.`);
  return v;
}

/** Turns the raw form state into validated numbers. Throws BatchError with a user-readable message. */
export function parseInput(form: BatchFormData, rows: IngredientRow[]): BatchInput {
  if (!form.product.trim()) throw new BatchError("Product name is required.");
  const requestedUnits = num("Requested units", form.requestedUnits);
  if (!Number.isInteger(requestedUnits) || requestedUnits <= 0) throw new BatchError("Requested units must be a whole number greater than 0.");
  const lossPct = num("Handling loss %", form.lossPct);
  if (lossPct < 0 || lossPct > 20) throw new BatchError("Handling loss must be between 0 and 20 %.");
  if (rows.length === 0) throw new BatchError("Add at least one ingredient.");
  const names = new Set<string>();
  const lines = rows.map((r, i) => {
    const name = r.name.trim(); const tag = name || `row ${i + 1}`;
    if (!name) throw new BatchError(`Ingredient name is required (row ${i + 1}).`);
    if (names.has(name.toLowerCase())) throw new BatchError("Ingredient names must be unique.");
    names.add(name.toLowerCase());
    if (!ROLES.includes(r.role)) throw new BatchError(`Unknown role for ${tag}.`);
    const mgPerUnit = num(`mg per unit (${tag})`, r.mgPerUnit); if (mgPerUnit <= 0) throw new BatchError(`mg per unit of ${tag} must be > 0.`);
    const assayPct = num(`Assay % (${tag})`, r.assayPct); if (!(assayPct > 0 && assayPct <= 100)) throw new BatchError(`Assay of ${tag} must be in (0, 100] %.`);
    const lodPct = num(`LOD % (${tag})`, r.lodPct); if (!(lodPct >= 0 && lodPct < 100)) throw new BatchError(`LOD of ${tag} must be in [0, 100) %.`);
    return { name, role: r.role, mgPerUnit, assayPct, lodPct, compensates: r.compensates === true };
  });
  return { product: form.product.trim(), requestedUnits, unitLabel: form.unitLabel.trim() || "units", lossPct, assayBasis: form.assayBasis, lines };
}

/** Pure function: same input -> same output. Mirrors the backend algorithm (POST /api/batch/calculate). */
export function calculateBatch(input: BatchInput, sourceKey = ""): BatchResult {
  const comps = input.lines.filter((l) => l.compensates);
  if (comps.length > 1) throw new BatchError("Only one ingredient can be the compensating filler.");
  if (comps[0]?.role === "API") throw new BatchError("The API cannot be the compensating ingredient.");
  if (!input.lines.some((l) => l.role === "API")) throw new BatchError("At least one ingredient must have the role 'API'.");
  const planned = Math.ceil((input.requestedUnits * (100 + input.lossPct)) / 100 - 1e-9); // epsilon guards float noise
  const rows = input.lines.map((l) => {
    const factor = (100 / l.assayPct) * (input.assayBasis === "dried" ? 100 / (100 - l.lodPct) : 1);
    const th = (planned * l.mgPerUnit) / 1_000_000;
    return { l, factor, th, act: th * factor };
  });
  const totalTh = rows.reduce((s, x) => s + x.th, 0);
  const warnings: string[] = [];
  const comp = rows.find((x) => x.l.compensates);
  if (comp) {
    const others = rows.filter((x) => x !== comp).reduce((s, x) => s + x.act, 0);
    comp.act = totalTh - others; comp.factor = 1;
    if (comp.act <= 0) throw new BatchError(`The corrections exceed the amount of '${comp.l.name}'. Revise the recipe or the assay/LOD values.`);
    if (comp.th - comp.act > comp.th * 0.25) warnings.push(`'${comp.l.name}' is reduced by more than 25 % of its theoretical quantity; check the assay/LOD inputs.`);
  } else warnings.push("No compensating filler selected: the actual batch total is larger than the theoretical total.");
  if (rows.some((x) => x.factor > 1.05)) warnings.push("A correction factor exceeds 1.05: verify the certificate-of-analysis values.");
  const totalAct = rows.reduce((s, x) => s + x.act, 0);
  return {
    input, sourceKey, plannedUnits: planned, unitMassMg: r6(input.lines.reduce((s, l) => s + l.mgPerUnit, 0)),
    lines: rows.map((x) => ({ name: x.l.name, role: x.l.role, mgPerUnit: x.l.mgPerUnit, assayPct: x.l.assayPct, lodPct: x.l.lodPct, factor: r6(x.factor),
      theoreticalKg: r6(x.th), actualKg: r6(x.act), differenceKg: r6(x.act - x.th), compensating: x === comp })),
    totals: { theoreticalKg: r6(totalTh), actualKg: r6(totalAct), differenceKg: r6(totalAct - totalTh) },
    warnings, formulas: FORMULAS, calculatedAt: new Date().toISOString(),
  };
}
