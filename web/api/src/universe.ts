import fs from "node:fs";
import path from "node:path";

/**
 * Supported CSE GICS industry groups. A test compares this list with
 * `SUPPORTED_INDUSTRY_GROUPS` in the Python package so they cannot drift apart.
 */
export const GROUP_NAMES: string[] = [
  "Energy",
  "Materials",
  "Capital Goods",
  "Commercial & Professional Services",
  "Transportation",
  "Automobiles & Components",
  "Consumer Durables & Apparel",
  "Consumer Services",
  "Retailing",
  "Food & Staples Retailing",
  "Food, Beverage & Tobacco",
  "Household & Personal Products",
  "Health Care Equipment & Services",
  "Banks",
  "Diversified Financials",
  "Insurance",
  "Software & Services",
  "Telecommunication Services",
  "Utilities",
  "Real Estate Management & Development",
  "Technology Hardware & Equipment",
  "Pharmaceuticals, Biotechnology & Life Sciences",
];

/** Same slug the Python universe cache uses for its file name. */
export function groupSlug(name: string): string {
  return (name.toLowerCase().match(/[a-z0-9]+/g) ?? []).join("_");
}

export interface GroupInfo {
  name: string;
  slug: string;
  cached: boolean;
}

export interface UniverseCompany {
  ticker: string;
  name: string;
  industryGroup: string;
}

function cacheFile(repoRoot: string, name: string): string {
  return path.join(repoRoot, "data", "raw", "cse_universe", `${groupSlug(name)}.json`);
}

export function listGroups(repoRoot: string): GroupInfo[] {
  return GROUP_NAMES.map((name) => ({
    name,
    slug: groupSlug(name),
    cached: fs.existsSync(cacheFile(repoRoot, name)),
  }));
}

/** Companies of a group from the pipeline's cached CSE response, or null when it is not cached. */
export function cachedCompanies(repoRoot: string, name: string): UniverseCompany[] | null {
  const file = cacheFile(repoRoot, name);
  if (!GROUP_NAMES.includes(name) || !fs.existsSync(file)) {
    return null;
  }
  const payload = JSON.parse(fs.readFileSync(file, "utf-8")) as {
    companies?: { ticker: string; name: string; industry_group?: string }[];
  };
  return (payload.companies ?? []).map((item) => ({
    ticker: item.ticker,
    name: item.name,
    industryGroup: item.industry_group ?? name,
  }));
}
