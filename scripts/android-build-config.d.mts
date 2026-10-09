export const STAGING_API_PLACEHOLDER: string;
export const ANDROID_ENVIRONMENTS: string[];
export function androidBuildConfig(environment?: string, variables?: Record<string, string | undefined>): { environment: string; apiBaseUrl: string; placeholder: boolean; mode: string; outDir: string };
