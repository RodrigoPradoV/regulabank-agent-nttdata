import { ChangeDetectionStrategy, Component, signal } from '@angular/core';
import { RouterOutlet } from '@angular/router';
import { Sidebar } from '../sidebar/sidebar';
import { Topbar } from '../topbar/topbar';
import { Shelf } from '../shelf/shelf';

@Component({
  selector: 'app-shell',
  imports: [RouterOutlet, Sidebar, Topbar, Shelf],
  templateUrl: './shell.html',
  styleUrl: './shell.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class Shell {
  readonly mobileSidebarOpen = signal(false);
  toggleMobileSidebar(): void { this.mobileSidebarOpen.update(v => !v); }
}
