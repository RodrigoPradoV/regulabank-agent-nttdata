import { DecimalPipe } from '@angular/common';
import { ChangeDetectionStrategy, Component, ElementRef, computed, effect, input, signal, viewChild } from '@angular/core';
import * as d3 from 'd3';

type LayerId = 'refers' | 'similar' | 'nli';
interface Entity { name: string; type: string; mentions: number; }
interface NormNode { id: string; short: string; title: string; kind: string; status: string; published: string | null;
  chunks: number; edges: Record<string, number>; top_entities: Entity[]; x?: number; y?: number; }
interface Link { layer: LayerId; source: string; target: string; n: number; cosine?: number; entailment?: number; judged?: number; }
interface Overview { p_min: number; nodes: NormNode[]; links: Link[]; self_refers: Record<string, number>;
  totals: { chunks: number; entities: number; edges: number; nli_pairs: number }; }

const W = 760, H = 560;
const KIND: Record<string, string> = { sbs_resolution: 'Resolución SBS', legislative_decree: 'Decreto legislativo', supreme_decree: 'Decreto supremo',
  international_standard: 'Estándar internacional', international_guideline: 'Guía internacional', eu_regulation: 'Reglamento UE' };

// Qué enseña cada capa y con qué regla se construye; el grafo conserva las mismas posiciones en las tres.
const LAYERS = [
  { id: 'refers' as LayerId, label: 'Citas', rule: 'Un chunk cita a otro («conforme al artículo 8»). Regex, sin modelo.',
    caption: 'la flecha va de la que cita a la citada · grosor = chunks que citan' },
  { id: 'similar' as LayerId, label: 'Semejanza', rule: 'Vecinos por coseno (k = 10), sin el mismo artículo, entre normas distintas.',
    caption: 'grosor = aristas entre las dos normas' },
  { id: 'nli' as LayerId, label: 'Conflictos NLI', rule: 'Pares de oraciones con contradicción de RoBERTa XNLI y p ≥ 0,9.',
    caption: 'grosor = pares de oraciones en contradicción' },
];

@Component({
  selector: 'app-graph',
  imports: [DecimalPipe],
  templateUrl: './graph.html',
  styleUrl: './graph.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class Graph {
  readonly layers = LAYERS;
  readonly data = signal<Overview | null>(null);
  readonly layer = signal<LayerId>('refers');
  readonly share = signal(100);
  readonly selectedId = signal<string | null>(null);
  readonly startLayer = input<string | undefined>(undefined, { alias: 'layer' });
  private readonly svgRef = viewChild.required<ElementRef<SVGSVGElement>>('svg');

  readonly nodes = computed(() => this.data()?.nodes ?? []);
  readonly layerInfo = computed(() => LAYERS.find(l => l.id === this.layer())!);
  readonly pool = computed(() => (this.data()?.links ?? []).filter(l => l.layer === this.layer()).sort((a, b) => b.n - a.n));
  readonly shown = computed(() => this.pool().slice(0, Math.max(1, Math.ceil(this.pool().length * this.share() / 100))));
  readonly hiddenBelow = computed(() => this.shown().length < this.pool().length ? this.shown()[this.shown().length - 1].n : null);
  readonly selected = computed(() => this.nodes().find(n => n.id === this.selectedId()) ?? null);
  readonly neighbors = computed(() => {
    const id = this.selectedId(); const short = new Map(this.nodes().map(n => [n.id, n.short]));
    if (!id) { return []; }
    return this.shown().filter(l => l.source === id || l.target === id)
      .map(l => { const o = l.source === id ? l.target : l.source; return { id: o, short: short.get(o) ?? o, n: l.n }; })
      .sort((a, b) => b.n - a.n);
  });

  private positions: Map<string, { x: number; y: number }> | null = null;

  constructor() {
    fetch('data/graph-overview.json').then(r => r.json()).then((d: Overview) => { this.data.set(d); this.selectedId.set(d.nodes[0]?.id ?? null); });
    effect(() => { const l = this.startLayer(); if (l === 'refers' || l === 'similar' || l === 'nli') { this.setLayer(l); } }, { allowSignalWrites: true });
    effect(() => { this.data(); this.layer(); this.shown(); this.selectedId(); this.render(); });
  }

  setLayer(id: LayerId): void { this.layer.set(id); this.share.set(id === 'refers' ? 100 : 50); }
  select(id: string): void { this.selectedId.set(id); }
  count(n: NormNode, type: string): number { return n.edges[type] ?? 0; }
  kindLabel(k: string): string { return KIND[k] ?? k; }

  private radius(n: NormNode): number { return 7 + Math.sqrt(n.chunks) * 0.85; }

  // Posiciones fijas: se calculan una vez con todas las capas, para poder comparar capas sin que los nodos se muevan.
  private layout(d: Overview): Map<string, { x: number; y: number }> {
    if (this.positions) { return this.positions; }
    const nodes = d.nodes.map(n => ({ ...n }));
    const weight = (l: Link) => (l.layer === 'similar' ? 0.4 : l.layer === 'refers' ? 1 : 0.2) * Math.log2(1 + l.n);
    const links = d.links.map(l => ({ source: l.source, target: l.target, w: weight(l) }));
    const sim = d3.forceSimulation(nodes as d3.SimulationNodeDatum[])
      .force('link', d3.forceLink(links).id((n: d3.SimulationNodeDatum) => (n as NormNode).id).distance(l => 260 - Math.min(140, (l as unknown as { w: number }).w * 18)).strength(l => Math.min(0.35, (l as unknown as { w: number }).w / 20)))
      .force('charge', d3.forceManyBody().strength(-1500))
      .force('center', d3.forceCenter(W / 2, H / 2))
      .force('collide', d3.forceCollide<d3.SimulationNodeDatum>().radius(n => this.radius(n as NormNode) + 34))
      .stop();
    const padX = 70, padY = 56;
    for (let i = 0; i < 400; i++) {
      sim.tick();
      for (const n of nodes) { n.x = Math.max(padX, Math.min(W - padX, n.x ?? W / 2)); n.y = Math.max(padY, Math.min(H - padY - 12, n.y ?? H / 2)); }
    }
    this.positions = new Map(nodes.map(n => [n.id, { x: n.x ?? W / 2, y: n.y ?? H / 2 }]));
    return this.positions;
  }

  private render(): void {
    const d = this.data(); if (!d) { return; }
    const pos = this.layout(d); const layer = this.layer(); const sel = this.selectedId();
    const svg = d3.select(this.svgRef().nativeElement); svg.selectAll('*').remove();
    const color = layer === 'nli' ? '#ff3b30' : layer === 'similar' ? '#a3a3a3' : '#1d1d1f';
    const byId = new Map(d.nodes.map(n => [n.id, n]));
    const links = this.shown(); const max = d3.max(links, l => l.n) ?? 1;
    const width = d3.scaleSqrt().domain([1, Math.max(max, 2)]).range([1.2, 9]);
    if (layer === 'refers') {
      svg.append('defs').append('marker').attr('id', 'head').attr('viewBox', '0 0 10 10').attr('refX', 8).attr('refY', 5).attr('markerUnits', 'userSpaceOnUse').attr('markerWidth', 11).attr('markerHeight', 11).attr('orient', 'auto')
        .append('path').attr('d', 'M0,0 L10,5 L0,10 z').attr('fill', color);
    }
    const edge = (l: Link) => {
      const a = pos.get(l.source)!, b = pos.get(l.target)!;
      const dx = b.x - a.x, dy = b.y - a.y, len = Math.hypot(dx, dy) || 1;
      const ra = this.radius(byId.get(l.source)!), rb = this.radius(byId.get(l.target)!) + (layer === 'refers' ? 5 : 0);
      return { x1: a.x + dx / len * ra, y1: a.y + dy / len * ra, x2: b.x - dx / len * rb, y2: b.y - dy / len * rb };
    };
    const touches = (l: Link) => sel !== null && (l.source === sel || l.target === sel);
    svg.append('g').selectAll('line').data(links).join('line')
      .attr('x1', l => edge(l).x1).attr('y1', l => edge(l).y1).attr('x2', l => edge(l).x2).attr('y2', l => edge(l).y2)
      .attr('stroke', color).attr('stroke-linecap', 'round').attr('stroke-width', l => width(l.n))
      .attr('opacity', l => (sel === null || touches(l) ? 0.75 : 0.14))
      .attr('marker-end', layer === 'refers' ? 'url(#head)' : null)
      .append('title').text(l => `${byId.get(l.source)!.short} ↔ ${byId.get(l.target)!.short}: ${l.n}`);
    const node = svg.append('g').selectAll('g').data(d.nodes).join('g').attr('transform', n => `translate(${pos.get(n.id)!.x},${pos.get(n.id)!.y})`)
      .style('cursor', 'pointer').on('click', (_e, n) => this.select(n.id));
    node.append('circle').attr('r', n => this.radius(n)).attr('fill', n => (n.id === sel ? '#1d1d1f' : '#f5f5f7'))
      .attr('stroke', n => (n.id === sel ? '#1d1d1f' : 'rgba(0,0,0,0.18)')).attr('stroke-width', 1.5);
    node.append('text').attr('y', n => this.radius(n) + 14).attr('text-anchor', 'middle').attr('font-size', 11.5)
      .attr('font-weight', n => (n.id === sel ? 600 : 500)).attr('fill', n => (n.id === sel ? '#1d1d1f' : '#525252')).text(n => n.short);
    node.append('title').text(n => `${n.short}: ${n.chunks} chunks`);
  }
}
