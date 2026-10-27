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
        // The path is built by the API from validated parts; the host is fixed.
        await page.goto(new URL(path, webUrl).toString(), { waitUntil: "networkidle", timeout: timeoutMs });
        await page.waitForSelector('[data-print-ready="true"], [data-print-error="true"]', { timeout: timeoutMs });
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
