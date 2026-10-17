import { Injectable, signal } from '@angular/core';

// El shelf es el panel derecho contextual: muestra un articulo con su historia sin salir de la pagina.
export interface ShelfContent { kind: 'article'; articleId: string; }

@Injectable({ providedIn: 'root' })
export class ShelfService {
  readonly content = signal<ShelfContent | null>(null);
  openArticle(articleId: string): void { this.content.set({ kind: 'article', articleId }); }
  close(): void { this.content.set(null); }
}
