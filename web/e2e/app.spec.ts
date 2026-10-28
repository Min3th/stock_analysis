import fs from "node:fs";
import path from "node:path";
import { expect, test, type Page } from "@playwright/test";

const REPO = path.resolve(__dirname, ".tmp", "fixture", "repo");
const PDF = path.join(REPO, "data", "raw", "AAA_N0000", "a1b2c3d4e5f60718.pdf");

// One browser session, in order: each step builds on the run created in the first.
test.describe.configure({ mode: "serial" });

let runId = "";
let page: Page;

test.beforeAll(async ({ browser }) => {
  page = await (await browser.newContext({ acceptDownloads: true })).newPage();
});
test.afterAll(async () => page.context().close());

test("dashboard starts an offline run and shows it completed", async () => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Runs", exact: true })).toBeVisible();
  await expect(page.getByText("No runs yet")).toBeVisible();
  // The cached group offers an offline run; groups with no cache do not.
  await expect(page.getByRole("option", { name: "Capital Goods (cached)" })).toBeAttached();
  await page.getByLabel("Industry group").selectOption("Capital Goods");
  await page.getByLabel("Period label").fill("2026Q3");
  await page.getByLabel("Offline (cache only)").check();
  await page.getByRole("button", { name: "Start run" }).click();
  const row = page.getByTestId("run-row").first();
  await expect(row.getByText("Completed")).toBeVisible();
  await expect(page.getByRole("log", { name: "Pipeline output" })).toContainText("Running Capital Goods 2026Q3");
  await expect(row).toContainText("Offline");
  await expect(row).toContainText("e2e000"); // the pipeline commit recorded in the manifest
  await row.getByRole("link", { name: "Results" }).click();
  await expect(page).toHaveURL(/\/runs\/\d{14}-capital_goods-2026Q3-/, { timeout: 90_000 });
  runId = new URL(page.url()).pathname.split("/").pop() ?? "";
});

test("an invalid run request is refused with a message", async () => {
  await page.goto("/");
  await page.getByLabel("Company (optional)").fill("not-a-ticker");
  await page.getByRole("button", { name: "Start run" }).click();
  // The browser's own pattern check blocks it before the API is called.
  await expect(page.getByTestId("run-row")).toHaveCount(1);
  const response = await page.request.post("/api/runs", { data: { sector: "Banks; calc", period: "2026Q3" } });
  expect(response.status()).toBe(400);
});

test("sector view: table, sorting, filters, medians, flags and the disclaimer", async () => {
  await page.goto(`/runs/${runId}`);
  const table = page.getByTestId("screening-table");
  await expect(table.locator("tbody tr")).toHaveCount(3);
  await expect(table.locator("tbody tr").first()).toContainText("AAA.N0000"); // ticker order by default
  await expect(page.getByText("Medians as calculated by the pipeline")).toBeVisible();
  await expect(page.getByRole("cell", { name: "7.3%" })).toBeVisible(); // the pipeline's median ROE, formatted

  await table.getByRole("button", { name: /^ROE/ }).click();
  await expect(table.getByRole("columnheader", { name: /ROE/ })).toHaveAttribute("aria-sort", "ascending");
  await expect(table.locator("tbody tr").first()).toContainText("BBB.N0000"); // lowest ROE first; ascending is a sort, not a rating

  await page.getByLabel("Confidence").selectOption("review");
  await expect(table.locator("tbody tr")).toHaveCount(1);
  await page.getByLabel("Confidence").selectOption("all");
  await page.getByPlaceholder("Ticker or company").fill("gamma");
  await expect(table.locator("tbody tr")).toHaveCount(1);
  await page.getByPlaceholder("Ticker or company").fill("");

  await expect(page.getByRole("cell", { name: "negative operating cash flow" })).toBeVisible();
  await expect(page.getByText("not investment advice")).toBeVisible();
  await expect(page.locator("body")).not.toContainText(/best|top pick|buy |sell /i);
});

test("company page: lineage drawer and the cited PDF page", async () => {
  await page.goto(`/runs/${runId}`);
  await page.getByRole("link", { name: "AAA.N0000" }).click();
  await expect(page).toHaveURL(/\/AAA\.N0000$/, { timeout: 90_000 });
  const roe = page.getByTestId("metric-ROE");
  await expect(roe).toContainText("18.7%");
  await expect(roe).toContainText("FY to 2026-03-31");
  await roe.getByRole("button", { name: /How ROE is calculated/ }).click();
  const drawer = page.getByRole("dialog", { name: "How ROE is calculated" });
  await expect(drawer).toContainText("Net profit attributable to ordinary shareholders / average ordinary equity");
  await expect(drawer).toContainText("33,851,268,000");
  await expect(drawer.getByTestId("lineage-row")).toHaveCount(1);
  await drawer.getByRole("button", { name: "View source" }).first().click();

  const viewer = page.getByRole("dialog", { name: /Source: Annual Report/ });
  await expect(viewer.getByTestId("source-quote")).toContainText("Profit attributable to owners of the company 6,337,879");
  const src = await viewer.locator("iframe").getAttribute("src");
  expect(src).toMatch(/\/api\/documents\/AAA\.N0000\/a1b2c3d4e5f60718\/file\?run=.*#page=2$/);
  const pdf = await page.request.get(src!.split("#")[0]!);
  expect(pdf.status()).toBe(200);
  expect(pdf.headers()["content-type"]).toBe("application/pdf");
  expect((await pdf.body()).subarray(0, 4).toString()).toBe("%PDF");
});

test("review queue: validation, then a correction written through the pipeline command", async () => {
  await page.goto(`/review?run=${runId}`);
  await expect(page.getByTestId("review-table").locator("tbody tr")).toHaveCount(2);
  await page.getByLabel("Reason").first().selectOption("low_confidence");
  await expect(page.getByTestId("review-table").locator("tbody tr")).toHaveCount(1);
  await page.getByTestId("review-table").getByRole("button", { name: "AAA.N0000" }).click();
  await expect(page.getByTestId("review-detail")).toContainText("Two candidate rows disagree");
  await expect(page.locator("iframe").first()).toHaveAttribute("src", /#page=2$/);

  const form = page.getByRole("form", { name: "Add a correction" });
  await form.getByLabel("Value as printed").fill("12abc");
  await form.getByLabel("Reason", { exact: true }).fill("Re-typed from the cited page");
  await form.getByRole("button", { name: "Save correction" }).click();
  await expect(form.getByRole("alert")).toContainText("value must be a plain number");

  await form.getByLabel("Value as printed").fill("6,337,879");
  await form.getByLabel("Unit").selectOption("LKR '000");
  await form.getByRole("button", { name: "Save correction" }).click();
  await expect(page.getByRole("status")).toContainText("AAA.N0000-net_profit-2026-03-31-1");
  const yaml = fs.readFileSync(path.join(REPO, "config", "corrections.yml"), "utf-8");
  expect(yaml).toContain("id: AAA.N0000-net_profit-2026-03-31-1");
  expect(yaml).toContain("value: '6337879'");
});

test("upload: previews the extraction, highlights low-confidence facts, then accepts", async () => {
  await page.goto("/upload");
  await expect(page.locator("form[data-hydrated=true]")).toBeAttached();
  await page.getByTestId("upload-input").setInputFiles(PDF);
  await page.getByLabel("Company").fill("AAA.N0000");
  await page.getByLabel("Period end").fill("2026-03-31");
  await page.getByRole("button", { name: "Preview extraction" }).click();

  const facts = page.getByTestId("preview-fact");
  await expect(facts).toHaveCount(2);
  await expect(facts.filter({ has: page.getByText("net_profit") })).toHaveAttribute("data-below", "false");
  const low = facts.filter({ has: page.getByText("eps") });
  await expect(low).toHaveAttribute("data-below", "true");
  await expect(low).toContainText("below threshold");
  await expect(page.getByTestId("upload-preview")).toContainText("income 2");

  await page.getByRole("button", { name: "Accept as a source" }).click();
  await expect(page.getByRole("status")).toContainText("Accepted");
  const uploads = fs.readFileSync(path.join(REPO, "config", "uploads.yml"), "utf-8");
  expect(uploads).toContain("ticker: AAA.N0000");
  expect(uploads).toContain("original_filename: a1b2c3d4e5f60718.pdf");
});

test("upload: a file that is not a PDF is refused", async () => {
  await page.goto("/upload");
  await expect(page.locator("form[data-hydrated=true]")).toBeAttached();
  await page.getByTestId("upload-input").setInputFiles({ name: "report.pdf", mimeType: "application/pdf", buffer: Buffer.from("<html>nope</html>") });
  await page.getByLabel("Company").fill("AAA.N0000");
  await page.getByLabel("Period end").fill("2026-03-31");
  await page.getByRole("button", { name: "Preview extraction" }).click();
  await expect(page.getByRole("alert").filter({ hasText: "not a PDF" })).toBeVisible();
  await expect(page.getByTestId("upload-preview")).toHaveCount(0);
});

async function download(trigger: () => Promise<void>): Promise<Buffer> {
  const [file] = await Promise.all([page.waitForEvent("download", { timeout: 100_000 }), trigger()]);
  return fs.readFileSync((await file.path())!);
}

test("exports: the sector report, the company sheet and the review pack are PDFs", async () => {
  await page.goto(`/runs/${runId}`);
  const sector = await download(() => page.getByRole("button", { name: "Download sector report (PDF)" }).click());
  expect(sector.subarray(0, 4).toString()).toBe("%PDF");
  expect(sector.length).toBeGreaterThan(5_000);
  const review = await download(() => page.getByRole("button", { name: "Download review pack (PDF)" }).click());
  expect(review.subarray(0, 4).toString()).toBe("%PDF");

  await page.goto(`/runs/${runId}/AAA.N0000`);
  const company = await download(() => page.getByRole("button", { name: "Download company sheet (PDF)" }).click());
  expect(company.subarray(0, 4).toString()).toBe("%PDF");
  expect(company.length).toBeGreaterThan(5_000);
});
