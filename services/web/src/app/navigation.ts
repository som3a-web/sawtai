import type { Page } from "./types";

const PAGES: Page[] = ["overview", "whatsapp", "cases", "voice", "draft", "crisis", "data", "admin"];

export function initialPage(search: string): Page {
  const requested = new URLSearchParams(search).get("page");
  return requested && PAGES.includes(requested as Page) ? requested as Page : "overview";
}
