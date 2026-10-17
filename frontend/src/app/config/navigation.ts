export interface NavItem { path: string; label: string; icon: string; }
export interface NavModule { label: string; items: NavItem[]; }

export const NAVIGATION: NavModule[] = [
  { label: 'Flujo', items: [
    { path: '/flow', label: 'Del PDF al grafo', icon: 'flow-arrow' },
    { path: '/score', label: 'De la pregunta a la respuesta', icon: 'path' },
  ]},
  { label: 'Normativa', items: [
    { path: '/norms', label: 'Textos', icon: 'books' },
    { path: '/conflicts', label: 'Conflictos', icon: 'warning-diamond' },
  ]},
  { label: 'Asistente', items: [
    { path: '/chat', label: 'Consulta', icon: 'chat-circle-text' },
  ]},
];
