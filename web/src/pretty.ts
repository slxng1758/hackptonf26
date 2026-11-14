// Our own pages (the rebuilt Amazon listing, generated product stores) live on the local API. Owners and judges should
// read "the product page", never 127.0.0.1:4620/api/... (found by /qa on 2026-11-14).
const OWN = /(?:https?:\/\/(?:127\.0\.0\.1|localhost)(?::\d+)?)?\/api\/products?\/[\w.-]+(?:\.html)?(?:\/[\w?=&.-]*)?/g;
export const pretty = (s: string) => (s || "").replace(OWN, "the product page");
export const isOwnPage = (url: string) => /\/api\/products?\//.test(url || "");
