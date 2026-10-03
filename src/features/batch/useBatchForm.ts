import { useCallback, useMemo, useReducer } from "react";
import { calculateBatch, parseInput } from "./calc";
import { AssayBasis, BatchError, BatchFormData, BatchResult, IngredientRow, Role } from "./types";

let seq = 0;
export const newId = () => `row-${Date.now().toString(36)}-${seq++}`; // stable React keys (never use the array index)

export const blankRow = (): IngredientRow => ({ id: newId(), name: "", role: "Other", mgPerUnit: "", assayPct: "100", lodPct: "0", compensates: false });
export const blankForm = (): BatchFormData => ({ product: "", requestedUnits: "", unitLabel: "tablets", lossPct: "0", assayBasis: "dried" });
export const emptyState = () => ({ form: blankForm(), rows: [{ ...blankRow(), role: "API" as Role }], result: null as BatchResult | null, error: null as string | null });

/** Frozen template: NEVER put this object in state directly. loadExample() builds fresh copies every time. */
const EXAMPLE = Object.freeze({
  form: Object.freeze({ product: "Paracetamol 500 mg Tablets", requestedUnits: "150000", unitLabel: "tablets", lossPct: "2", assayBasis: "dried" as AssayBasis }),
  rows: Object.freeze([
    { name: "Paracetamol", role: "API", mgPerUnit: "500", assayPct: "98.5", lodPct: "0.8", compensates: false },
    { name: "Avicel PH-102", role: "Diluent / Filler", mgPerUnit: "80", assayPct: "100", lodPct: "0", compensates: true },
    { name: "Sodium Starch Glycolate", role: "Disintegrant", mgPerUnit: "15", assayPct: "100", lodPct: "0", compensates: false },
    { name: "Magnesium Stearate", role: "Lubricant", mgPerUnit: "5", assayPct: "100", lodPct: "0", compensates: false },
  ] as const),
});
export const EXAMPLE_PRODUCT = EXAMPLE.form.product;

export type State = ReturnType<typeof emptyState>;
type Action =
  | { type: "field"; key: keyof BatchFormData; value: string }
  | { type: "row"; id: string; key: keyof Omit<IngredientRow, "id" | "compensates">; value: string }
  | { type: "toggleCompensator"; id: string }
  | { type: "addRow" } | { type: "removeRow"; id: string }
  | { type: "loadExample" } | { type: "clear" } | { type: "calculate" };

/** Key of everything that influences the calculation (row ids excluded). Used to detect stale results. */
export const sourceKey = (f: BatchFormData, rows: IngredientRow[]) => JSON.stringify([f, rows.map(({ id, ...r }) => r)]);

function reducer(s: State, a: Action): State {
  switch (a.type) {
    case "field": return { ...s, form: { ...s.form, [a.key]: a.value } as BatchFormData };
    case "row": return { ...s, rows: s.rows.map((r) => (r.id === a.id ? { ...r, [a.key]: a.value } : r)) };
    case "toggleCompensator": // at most one compensating filler; clicking the active one switches it off; the API can't compensate
      return { ...s, rows: s.rows.map((r) => ({ ...r, compensates: r.id === a.id ? !r.compensates && r.role !== "API" : false })) };
    case "addRow": return { ...s, rows: [...s.rows, blankRow()] };
    case "removeRow": return { ...s, rows: s.rows.filter((r) => r.id !== a.id) };
    case "loadExample":
      return { form: { ...EXAMPLE.form }, rows: EXAMPLE.rows.map((r) => ({ ...r, id: newId() })) as IngredientRow[], result: null, error: null };
    case "clear": return emptyState();
    case "calculate": { // computed INSIDE the reducer => always uses the latest state, never a stale closure
      try {
        const input = parseInput(s.form, s.rows);
        return { ...s, error: null, result: calculateBatch(input, sourceKey(s.form, s.rows)) };
      } catch (e) {
        if (e instanceof BatchError) return { ...s, result: null, error: e.message };
        throw e;
      }
    }
  }
}

export function useBatchForm() {
  const [state, dispatch] = useReducer(reducer, undefined, emptyState);
  const isStale = useMemo(() => state.result !== null && state.result.sourceKey !== sourceKey(state.form, state.rows), [state]);
  return {
    ...state, isStale,
    setField: useCallback((key: keyof BatchFormData, value: string) => dispatch({ type: "field", key, value }), []),
    setRow: useCallback((id: string, key: keyof Omit<IngredientRow, "id" | "compensates">, value: string) => dispatch({ type: "row", id, key, value }), []),
    toggleCompensator: useCallback((id: string) => dispatch({ type: "toggleCompensator", id }), []),
    addRow: useCallback(() => dispatch({ type: "addRow" }), []),
    removeRow: useCallback((id: string) => dispatch({ type: "removeRow", id }), []),
    loadExample: useCallback(() => dispatch({ type: "loadExample" }), []),
    clear: useCallback(() => dispatch({ type: "clear" }), []),
    calculate: useCallback(() => dispatch({ type: "calculate" }), []),
  };
}
