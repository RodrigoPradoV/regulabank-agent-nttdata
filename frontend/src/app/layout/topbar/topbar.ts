import { ChangeDetectionStrategy, Component, computed, inject, output } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { NavigationEnd, Router } from '@angular/router';
import { toSignal } from '@angular/core/rxjs-interop';
import { catchError, filter, map, of, startWith } from 'rxjs';
import { API_URL } from '../../core/api.service';
import { Icon } from '../../shared/icon/icon';
import { NAVIGATION } from '../../config/navigation';

@Component({
  selector: 'app-topbar',
  imports: [Icon],
  templateUrl: './topbar.html',
  styleUrl: './topbar.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class Topbar {
  readonly menuClick = output<void>();
  private readonly router = inject(Router);
  // El proveedor real del API (/health), no una etiqueta fija: «OpenAI en vivo» o «maqueta».
  readonly provider = toSignal(inject(HttpClient).get<{ provider: string; live?: boolean }>(`${API_URL}/health`).pipe(
    map(h => h.provider === 'openai' && h.live ? 'OpenAI en vivo' : h.provider === 'mock' ? 'maqueta' : h.provider),
    catchError(() => of('API sin conexión'))));
  private readonly url = toSignal(this.router.events.pipe(
    filter((e): e is NavigationEnd => e instanceof NavigationEnd), map(e => e.urlAfterRedirects), startWith(this.router.url)));

  readonly crumbs = computed(() => {
    const url = this.url() ?? '/';
    const first = '/' + url.split('/').filter(Boolean)[0];
    for (const m of NAVIGATION) {
      const item = m.items.find(i => i.path === first);
      if (item) { const parts = url.split('/').filter(Boolean); return parts.length > 1 ? [m.label, item.label, first === '/flow' ? 'Etapa' : 'Detalle'] : [m.label, item.label]; }
    }
    return ['regulabank'];
  });
}
