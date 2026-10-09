const retryButton = document.getElementById('retry-connection');
retryButton?.addEventListener('click', async () => {
  retryButton.disabled = true;
  try {
    if ('serviceWorker' in navigator) {
      const registrations = await navigator.serviceWorker.getRegistrations();
      await Promise.all(registrations.map(registration => registration.unregister()));
    }
  } catch {
    // Reload still retries the network if a registration cannot be removed.
  } finally {
    window.location.href = '/?r=' + Date.now();
  }
});
