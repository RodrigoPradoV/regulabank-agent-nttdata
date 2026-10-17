import { ChangeDetectionStrategy, Component, inject, input } from '@angular/core';
import { RouterLink } from '@angular/router';
import { toObservable, toSignal } from '@angular/core/rxjs-interop';
import { switchMap } from 'rxjs';
import { ApiService } from '../../core/api.service';
import { ShelfService } from '../../core/shelf.service';
import { NORM_KIND_LABEL } from '../../core/models';
import { Icon } from '../../shared/icon/icon';

@Component({
  selector: 'app-norm-detail',
  imports: [Icon, RouterLink],
  templateUrl: './norm-detail.html',
  styleUrl: './norm-detail.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class NormDetailPage {
  readonly id = input.required<string>();
  private readonly api = inject(ApiService);
  readonly shelf = inject(ShelfService);
  readonly kindLabel = NORM_KIND_LABEL;
  readonly norm = toSignal(toObservable(this.id).pipe(switchMap(id => this.api.norm(id))));
}
