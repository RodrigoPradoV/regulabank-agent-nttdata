import { ChangeDetectionStrategy, Component, computed, inject, output } from '@angular/core';
import { NavigationEnd, Router } from '@angular/router';
import { toSignal } from '@angular/core/rxjs-interop';
import { filter, map, startWith } from 'rxjs';
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
