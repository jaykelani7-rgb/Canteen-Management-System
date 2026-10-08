export function registerStudentPwa(): void {
  if (!import.meta.env.PROD || !('serviceWorker' in navigator) || !window.isSecureContext) return;
  window.addEventListener('load', () => {
    void navigator.serviceWorker.register('/sw.js', { scope: '/' })
      .then(() => navigator.serviceWorker.ready)
      .then(() => console.info('Smart Canteen service worker ready'))
      .catch(() => console.warn('Smart Canteen offline shell unavailable'));
  });
}
