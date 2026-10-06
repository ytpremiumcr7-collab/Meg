/** Navigate within the current command center without discarding context. */
export function abrirModulo(app: string, programaId?: string) {
  const url = new URL(window.location.href);
  url.searchParams.set('app', app);
  if (programaId) url.searchParams.set('programa', programaId);
  else url.searchParams.delete('programa');
  window.history.pushState({}, '', url);
  window.dispatchEvent(new PopStateEvent('popstate'));
}
