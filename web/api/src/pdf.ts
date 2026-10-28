import { chromium, type Browser } from "playwright-core";

export interface PdfOptions {
  landscape: boolean;
}

/** Renders one of the app's `/print/...` pages to a PDF. Injected in tests. */
export interface PdfRenderer {
  render(path: string, options: PdfOptions): Promise<Buffer>;
  close(): Promise<void>;
}

const FOOTER = `
<div style="width:100%;font-size:8px;color:#555;padding:0 12mm;display:flex;justify-content:space-between;">
  <span>Descriptive evidence from public filings. Not investment advice; no ranking or recommendation.</span>
  <span>Page <span class="pageNumber"></span> of <span class="totalPages"></span></span>
</div>`;

/**
 * Opens the print route in headless Chromium and waits for the page to say its data has
 * loaded (`data-print-ready`), so a half-rendered page is never exported.
 */
export function playwrightRenderer(webUrl: string, timeoutMs = 90_000): PdfRenderer {
  let browser: Browser | null = null;
  return {
    async render(path, options) {
      browser ??= await chromium.launch();
      const context = await browser.newContext();
      try {
        const page = await context.newPage();
        const problems: string[] = [];
        page.on("pageerror", (error) => problems.push(error.message));
        page.on("console", (message) => message.type() === "error" && problems.push(message.text()));
        page.on("response", (response) => response.status() >= 400 && problems.push(`HTTP ${response.status()} ${new URL(response.url()).pathname}`));
        // The path is built by the API from validated parts; the host is fixed.
        await page.goto(new URL(path, webUrl).toString(), { waitUntil: "domcontentloaded", timeout: timeoutMs });
        try {
          await page.waitForSelector('[data-print-ready="true"], [data-print-error="true"]', { timeout: timeoutMs });
        } catch {
          // Say what the page was doing, not just that it timed out.
          const text = (await page.locator("body").innerText().catch(() => "")).replace(/\s+/g, " ").slice(0, 160);
          throw new Error(`The report page did not finish loading (${problems.slice(0, 3).join("; ") || "no page errors"}); it showed: ${text}`);
        }
        const failure = page.locator('[data-print-error="true"]');
        if ((await failure.count()) > 0) {
          throw new Error((await failure.first().innerText()).trim());
        }
        await page.emulateMedia({ media: "print" });
        return Buffer.from(
          await page.pdf({
            format: "A4",
            landscape: options.landscape,
            printBackground: true,
            displayHeaderFooter: true,
            headerTemplate: "<span></span>",
            footerTemplate: FOOTER,
            margin: { top: "14mm", bottom: "16mm", left: "12mm", right: "12mm" },
          }),
        );
      } finally {
        await context.close();
      }
    },
    async close() {
      await browser?.close();
      browser = null;
    },
  };
}
