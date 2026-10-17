import { Capacitor } from '@capacitor/core';
import type { PluginListenerHandle } from '@capacitor/core';

/** One owned listener: ignore WebView canGoBack because screens live in React state. */
export function attachStudentNativeBack(onBack: () => boolean): () => void {
  if (!Capacitor.isNativePlatform()) return () => {};
  let disposed = false;
  let listener: PluginListenerHandle | undefined;
  void import('@capacitor/app').then(async ({ App }) => {
    if (disposed) return;
    const handle = await App.addListener('backButton', () => {
      if (!disposed && !onBack()) void App.exitApp();
    });
    // React StrictMode/unmount can clean up before the native promise resolves.
    if (disposed) await handle.remove();
    else listener = handle;
  }).catch(() => { console.warn('Native Back navigation unavailable.'); });
  return () => { disposed = true; if (listener) void listener.remove(); };
}

/** Runs only in the bundled Android app. The normal web PWA is unchanged. */
export async function initializeStudentNative(): Promise<void> {
  if (!Capacitor.isNativePlatform()) return;
  try {
    const { StatusBar, Style } = await import('@capacitor/status-bar');
    await StatusBar.setStyle({ style: Style.Light });
  } catch {
    console.warn('Native status bar styling unavailable.');
  }
  try {
    const { SplashScreen } = await import('@capacitor/splash-screen');
    await SplashScreen.hide({ fadeOutDuration: 200 });
  } catch {
    console.warn('Native splash screen unavailable.');
  }
}
