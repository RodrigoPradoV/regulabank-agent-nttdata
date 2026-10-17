import { ChangeDetectionStrategy, Component, input } from '@angular/core';

type IconSize = 'xs' | 'sm' | 'md' | 'lg';
const SIZE: Record<IconSize, number> = { xs: 14, sm: 16, md: 20, lg: 24 };

@Component({
  selector: 'app-icon',
  template: `<i [class]="'ph' + (weight() === 'fill' ? '-fill' : '') + ' ph-' + name()"
    [style.font-size.px]="px" [style.width.px]="px" [style.height.px]="px" [style.line-height.px]="px"></i>`,
  styles: [`:host { display: inline-flex; } i { display: inline-block; text-align: center; }`],
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class Icon {
  readonly name = input.required<string>();
  readonly size = input<IconSize>('md');
  readonly weight = input<'regular' | 'fill'>('regular');
  get px(): number { return SIZE[this.size()]; }
}
