import { Routes } from '@angular/router';
import { Shell } from './layout/shell/shell';

export const routes: Routes = [
  { path: '', component: Shell, children: [
    { path: '', redirectTo: 'norms', pathMatch: 'full' },
    { path: 'flow', loadComponent: () => import('./features/flow/flow').then(m => m.Flow) },
    { path: 'score', redirectTo: 'flow', pathMatch: 'full' },
    { path: 'graph', redirectTo: 'flow', pathMatch: 'full' },       // la pagina Grafo esta desactivada (el codigo sigue en features/graph)
    { path: 'norms', loadComponent: () => import('./features/norms/norms').then(m => m.Norms) },
    { path: 'norms/:id', loadComponent: () => import('./features/norms/norm-detail').then(m => m.NormDetailPage) },
    { path: 'chat', loadComponent: () => import('./features/chat/chat').then(m => m.Chat) },
    { path: 'conflicts', redirectTo: 'norms', pathMatch: 'full' },  // la pagina Conflictos esta desactivada (el codigo sigue en features/conflicts)
  ]},
  { path: '**', redirectTo: 'norms' },
];
