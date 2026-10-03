export const ROLES = ["API", "Diluent / Filler", "Disintegrant", "Binder", "Lubricant", "Glidant", "Coating", "Other"] as const;
export type Role = (typeof ROLES)[number];
export type AssayBasis = "dried" | "as_is";

/** Everything the user types is kept as a STRING (controlled inputs: no NaN, no jumping cursor). Parsed only when calculating. */
export interface BatchFormData { product: string; requestedUnits: string; unitLabel: string; lossPct: string; assayBasis: AssayBasis }
export interface IngredientRow { id: string; name: string; role: Role; mgPerUnit: string; assayPct: string; lodPct: string; compensates: boolean }

/** Parsed, validated numbers (what the algorithm really uses). */
export interface BatchInput {
  product: string; requestedUnits: number; unitLabel: string; lossPct: number; assayBasis: AssayBasis;
  lines: { name: string; role: Role; mgPerUnit: number; assayPct: number; lodPct: number; compensates: boolean }[];
}
export interface ResultLine { name: string; role: Role; mgPerUnit: number; assayPct: number; lodPct: number; factor: number; theoreticalKg: number; actualKg: number; differenceKg: number; compensating: boolean }
export interface BatchResult {
  input: BatchInput; sourceKey: string; plannedUnits: number; unitMassMg: number; lines: ResultLine[];
  totals: { theoreticalKg: number; actualKg: number; differenceKg: number }; warnings: string[]; formulas: string[]; calculatedAt: string;
}
export class BatchError extends Error {}
