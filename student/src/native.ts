import { Capacitor } from '@capacitor/core';

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
