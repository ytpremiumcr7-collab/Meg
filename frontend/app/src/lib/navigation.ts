/** Navigate within the current command center without discarding context. */
export function abrirModulo(app: string) {
  const url = new URL(window.location.href);
  url.searchParams.set('app', app);
  window.history.pushState({}, '', url);
  window.dispatchEvent(new PopStateEvent('popstate'));
}
