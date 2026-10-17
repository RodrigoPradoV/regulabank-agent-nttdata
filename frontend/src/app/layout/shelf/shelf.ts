import { ChangeDetectionStrategy, Component, computed, effect, inject, signal } from '@angular/core';
import { ApiService } from '../../core/api.service';
import { ShelfService } from '../../core/shelf.service';
import { Article, Version } from '../../core/models';
import { Icon } from '../../shared/icon/icon';

@Component({
  selector: 'app-shelf',
  imports: [Icon],
  templateUrl: './shelf.html',
  styleUrl: './shelf.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class Shelf {
  readonly shelf = inject(ShelfService);
  private readonly api = inject(ApiService);
  readonly article = signal<Article | null>(null);
  readonly selected = signal<Version | null>(null);
  readonly versions = computed(() => [...(this.article()?.versions ?? [])].sort((a, b) => b.n - a.n));

  constructor() {
    effect(() => {
      const content = this.shelf.content();
      if (!content) { this.article.set(null); return; }
      this.api.article(content.articleId).subscribe(a => { this.article.set(a); this.selected.set(a.current); });
    });
  }

  label(v: Version): string {
    const kinds: Record<string, string> = { original: 'Original', modified: 'Modificado', replaced: 'Sustituido', repealed: 'Derogado', added: 'Incorporado' };
    return v.valid_to ? `${kinds[v.change_kind]} · ${v.valid_from} a ${v.valid_to}` : `${kinds[v.change_kind]} · vigente desde ${v.valid_from}`;
  }
}
