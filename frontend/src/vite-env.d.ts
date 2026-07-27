/// <reference types="vite/client" />
declare module "*.css";

interface ImportMetaEnv {
  /** Backend origin for cross-site production (e.g. https://bidpilot-api.onrender.com). Empty in dev. */
  readonly VITE_API_BASE?: string;
}
interface ImportMeta {
  readonly env: ImportMetaEnv;
}
