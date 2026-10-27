import { Router } from "express";
import type { Config } from "../config.js";
import { cachedCompanies, GROUP_NAMES, listGroups } from "../universe.js";

export function universeRouter(config: Config): Router {
  const router = Router();

  router.get("/universe/groups", (_req, res) => {
    res.json(listGroups(config.repoRoot));
  });

  // Companies come from the pipeline's cached CSE response; this route never fetches.
  router.get("/universe/:group", (req, res) => {
    const name = GROUP_NAMES.find((group) => group === req.params.group);
    const companies = name ? cachedCompanies(config.repoRoot, name) : null;
    if (!name || !companies) {
      res.status(404).json({
        error: "not_cached",
        message: "Run this industry group once to cache its CSE universe.",
      });
      return;
    }
    res.json({ group: name, companies });
  });

  return router;
}
