/// <reference types="vite/client" />
interface ImportMetaEnv {
  readonly VITE_API_BASE_URL?: string;
  readonly VITE_NATIVE_APP?: string;
  readonly VITE_ANDROID_BACKEND_PLACEHOLDER?: string;
}
interface ImportMeta { readonly env: ImportMetaEnv; }
