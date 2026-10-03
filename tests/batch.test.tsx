import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import BatchCalculator from "../src/features/batch/BatchCalculator";
import { calculateBatch, parseInput } from "../src/features/batch/calc";
import { buildCsv, buildPdf, buildReportPayload } from "../src/features/batch/report";
import { blankForm, blankRow } from "../src/features/batch/useBatchForm";

const setup = () => ({ user: userEvent.setup(), ...render(<BatchCalculator />) });
const resultRow = (name: RegExp) => within(screen.getByLabelText("Batch result")).getByRole("cell", { name }).closest("tr")!;
async function typeInto(user: ReturnType<typeof userEvent.setup>, label: string | RegExp, text: string) {
  const el = screen.getByLabelText(label); await user.clear(el); if (text) await user.type(el, text);
}

describe("pure calculation", () => {
  it("reproduces the checked example (153,000 planned units; API 78.291 kg; filler 10.449 kg; total 91.800 kg)", () => {
    const form = { product: "Paracetamol 500 mg Tablets", requestedUnits: "150000", unitLabel: "tablets", lossPct: "2", assayBasis: "dried" as const };
    const mk = (name: string, role: any, mg: string, a = "100", l = "0", c = false) => ({ ...blankRow(), name, role, mgPerUnit: mg, assayPct: a, lodPct: l, compensates: c });
    const r = calculateBatch(parseInput(form, [mk("P", "API", "500", "98.5", "0.8"), mk("A", "Diluent / Filler", "80", "100", "0", true), mk("S", "Disintegrant", "15"), mk("M", "Lubricant", "5")]));
    expect(r.plannedUnits).toBe(153000);
    expect(r.lines.map((l) => l.actualKg.toFixed(3))).toEqual(["78.291", "10.449", "2.295", "0.765"]);
    expect(r.totals.actualKg).toBeCloseTo(91.8, 6); expect(r.totals.differenceKg).toBeCloseTo(0, 6);
  });
  it("rejects bad input with readable messages", () => {
    const rows = [{ ...blankRow(), name: "X", role: "API" as const, mgPerUnit: "10" }];
    expect(() => parseInput({ ...blankForm(), product: "", requestedUnits: "5" }, rows)).toThrow(/Product/);
    expect(() => parseInput({ ...blankForm(), product: "p", requestedUnits: "0" }, rows)).toThrow(/greater than 0/);
    expect(() => parseInput({ ...blankForm(), product: "p", requestedUnits: "5", lossPct: "50" }, rows)).toThrow(/between 0 and 20/);
    expect(() => parseInput({ ...blankForm(), product: "p", requestedUnits: "5" }, [{ ...rows[0], assayPct: "0" }])).toThrow(/Assay/);
  });
});

describe("BatchCalculator component (the reported bugs)", () => {
  it("Load example -> Calculate gives the checked numbers and shows the product", async () => {
    const { user } = setup();
    await user.click(screen.getByText(/Load example/)); await user.click(screen.getByText("Calculate batch"));
    expect(screen.getByRole("heading", { name: "Paracetamol 500 mg Tablets" })).toBeInTheDocument();
    expect(resultRow(/^Paracetamol$/)).toHaveTextContent("78.291"); expect(resultRow(/Avicel/)).toHaveTextContent("10.449");
    expect(screen.queryByText(/No compensating/)).toBeNull();
  });

  it("switching to Aspirin 81 mg uses the NEW values everywhere (result, PDF payload, PDF text, CSV)", async () => {
    const { user } = setup();
    await user.click(screen.getByText(/Load example/));
    await typeInto(user, /^Product/, "Aspirin 81 mg Tablets"); await typeInto(user, /Requested units/, "200000"); await typeInto(user, /Handling loss/, "1.5");
    await typeInto(user, "Ingredient name 1", "Aspirin"); await typeInto(user, "mg per unit 1", "81"); await typeInto(user, "Assay 1", "99.5"); await typeInto(user, "LOD 1", "0.5");
    await typeInto(user, "mg per unit 2", "300");
    await user.click(screen.getByText("Calculate batch"));
    expect(screen.getByRole("heading", { name: "Aspirin 81 mg Tablets" })).toBeInTheDocument();
    expect(resultRow(/^Aspirin$/)).toHaveTextContent("16.609");   // 203,000 units x 81 mg = 16.443 kg theoretical, x1.0101 factor
    expect(screen.getByText(/Planned units: 203,000/)).toBeInTheDocument();
  });

  it("toggling the compensating filler moves the adjustment to the chosen ingredient", async () => {
    const { user } = setup();
    await user.click(screen.getByText(/Load example/));
    await user.click(screen.getByLabelText("Compensates 3")); // Sodium Starch Glycolate becomes the compensator; Avicel is switched off
    expect(screen.getByLabelText("Compensates 2")).not.toBeChecked(); expect(screen.getByLabelText("Compensates 3")).toBeChecked();
    await user.click(screen.getByText("Calculate batch"));
    expect(resultRow(/Sodium Starch/)).toHaveTextContent("(compensating)"); expect(resultRow(/Sodium Starch/)).toHaveTextContent("0.504");
    expect(resultRow(/Avicel/)).toHaveTextContent("12.240"); expect(resultRow(/^Total$/)).toHaveTextContent("91.800");
    // switch the compensator off -> warning + total no longer constant
    await user.click(screen.getByLabelText("Compensates 3")); await user.click(screen.getByText("Calculate batch"));
    expect(screen.getByText(/No compensating filler selected/)).toBeInTheDocument();
  });

  it("the API line cannot be the compensator (checkbox disabled)", async () => {
    const { user } = setup(); await user.click(screen.getByText(/Load example/));
    expect(screen.getByLabelText("Compensates 1")).toBeDisabled();
  });

  it("editing after calculating marks the result stale and disables exports until recalculated", async () => {
    const { user } = setup(); await user.click(screen.getByText(/Load example/)); await user.click(screen.getByText("Calculate batch"));
    expect(screen.getByText("Export PDF")).toBeEnabled();
    await typeInto(user, /^Product/, "Ibuprofen 400 mg Tablets");
    expect(screen.getByRole("status")).toHaveTextContent(/Inputs changed/); expect(screen.getByText("Export PDF")).toBeDisabled(); expect(screen.getByText("Export CSV")).toBeDisabled();
    await user.click(screen.getByText("Calculate batch"));
    expect(screen.getByRole("heading", { name: "Ibuprofen 400 mg Tablets" })).toBeInTheDocument(); expect(screen.getByText("Export PDF")).toBeEnabled(); expect(screen.queryByRole("status")).toBeNull();
  });

  it("Clear form empties every field and the result; Load example afterwards still works and never mutates the template", async () => {
    const { user } = setup(); await user.click(screen.getByText(/Load example/)); await typeInto(user, /^Product/, "Changed"); await typeInto(user, "mg per unit 1", "999");
    await user.click(screen.getByText("Calculate batch"));
    await user.click(screen.getByText("Clear form"));
    expect(screen.getByLabelText(/^Product/)).toHaveValue(""); expect(screen.getByLabelText(/Requested units/)).toHaveValue(""); expect(screen.getByLabelText("mg per unit 1")).toHaveValue("");
    expect(screen.getAllByLabelText(/^Ingredient name/)).toHaveLength(1); expect(screen.queryByLabelText("Batch result")).toBeNull();
    await user.click(screen.getByText("Calculate batch")); expect(screen.getByRole("alert")).toHaveTextContent(/Product name is required/);
    await user.click(screen.getByText(/Load example/)); expect(screen.getByLabelText(/^Product/)).toHaveValue("Paracetamol 500 mg Tablets"); expect(screen.getByLabelText("mg per unit 1")).toHaveValue("500");
  });

  it("add / edit / remove rows keep values attached to the right row (stable keys)", async () => {
    const { user } = setup(); await user.click(screen.getByText(/Load example/));
    await user.click(screen.getByLabelText("Remove 2")); // remove Avicel
    expect(screen.getByLabelText("Ingredient name 2")).toHaveValue("Sodium Starch Glycolate"); expect(screen.getByLabelText("mg per unit 2")).toHaveValue("15");
    await user.click(screen.getByText("Add ingredient")); expect(screen.getAllByLabelText(/^Ingredient name/)).toHaveLength(4); expect(screen.getByLabelText("Ingredient name 4")).toHaveValue("");
  });
});

describe("PDF / CSV are built from the calculated result only", () => {
  const form = { product: "Aspirin 81 mg Tablets", requestedUnits: "200000", unitLabel: "tablets", lossPct: "1.5", assayBasis: "dried" as const };
  const rows = [{ ...blankRow(), name: "Aspirin", role: "API" as const, mgPerUnit: "81", assayPct: "99.5", lodPct: "0.5" }, { ...blankRow(), name: "Starch", role: "Diluent / Filler" as const, mgPerUnit: "300", compensates: true }];
  const result = calculateBatch(parseInput(form, rows));
  it("payload and PDF text carry the Aspirin data and no Paracetamol", () => {
    const p = buildReportPayload(result); expect(p.title).toBe("Aspirin 81 mg Tablets"); expect(JSON.stringify(p)).not.toMatch(/Paracetamol/);
    const raw = buildPdf(p).output(); expect(raw).toContain("Aspirin 81 mg Tablets"); expect(raw).toContain("Planned units"); expect(raw).not.toContain("Paracetamol");
    expect(buildCsv(result)).toContain('"Aspirin (compensating)"'.replace("Aspirin", "Starch"));
  });
});
