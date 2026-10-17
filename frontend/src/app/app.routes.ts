import { Routes } from '@angular/router';
import { Shell } from './layout/shell/shell';

export const routes: Routes = [
  { path: '', component: Shell, children: [
    { path: '', redirectTo: 'norms', pathMatch: 'full' },
    { path: 'flow', loadComponent: () => import('./features/flow/flow').then(m => m.Flow) },
    { path: 'flow/:id', loadComponent: () => import('./features/flow/stage').then(m => m.StagePage) },
    { path: 'norms', loadComponent: () => import('./features/norms/norms').then(m => m.Norms) },
    { path: 'norms/:id', loadComponent: () => import('./features/norms/norm-detail').then(m => m.NormDetailPage) },
    { path: 'chat', loadComponent: () => import('./features/chat/chat').then(m => m.Chat) },
    { path: 'conflicts', loadComponent: () => import('./features/conflicts/conflicts').then(m => m.Conflicts) },
  ]},
  { path: '**', redirectTo: 'norms' },
];
