import type { CapacitorConfig } from '@capacitor/cli';

const config: CapacitorConfig = {
  appId: 'com.canteenos.student',
  appName: 'Canteen OS',
  webDir: 'dist/student-android',
  backgroundColor: '#f5f1eb',
  loggingBehavior: 'debug',
  android: {
    backgroundColor: '#f5f1eb',
    allowMixedContent: false,
    zoomEnabled: false,
  },
  plugins: {
    SystemBars: {
      insetsHandling: 'native',
      initialViewportFitValueHint: 'contain',
      style: 'LIGHT',
    },
    StatusBar: {
      style: 'LIGHT',
      backgroundColor: '#f5f1eb',
    },
    SplashScreen: {
      launchAutoHide: true,
      launchShowDuration: 700,
      launchFadeOutDuration: 200,
      backgroundColor: '#f5f1eb',
      androidSplashResourceName: 'splash',
      androidScaleType: 'CENTER_INSIDE',
      showSpinner: false,
    },
  },
};

export default config;
