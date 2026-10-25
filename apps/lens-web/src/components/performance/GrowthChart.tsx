"use client";

import { useId, useMemo, useRef, useState } from "react";
import { useTranslations } from "next-intl";
import type { GrowthPoint } from "@/lib/contracts/snapshot";
import { money } from "@/lib/format";

interface Props {
  points: GrowthPoint[];
  benchmark: string;
  ticker: string;
}

const WIDTH = 720;
const HEIGHT = 260;
const PAD = { top: 16, right: 12, bottom: 26, left: 48 };

/**
 * The two growth curves, drawn from the engine's own sampled series.
 *
 * Geometry only: every value plotted is a value the engine already computed for
 * this period, and the chart neither interpolates a missing session nor rebases
 * a series. Hand-drawn SVG rather than a charting library, because the series
 * is pre-sampled to at most a few hundred points, the design is two lines on a
 * grid, and a library would arrive with its own styling to fight and its own
 * idea of what to do with a null.
 *
 * Hover reads values out; it never changes them. The figure also carries a
 * text summary, so the chart is not the only way to learn what it shows.
 */
export function GrowthChart({ points, benchmark, ticker }: Props) {
  const t = useTranslations("performance.chart");
  const gradientId = useId();
  const [cursor, setCursor] = useState<number | null>(null);
  const frame = useRef<SVGSVGElement>(null);

  const geometry = useMemo(() => {
    const values = points.flatMap((point) => [point.asset_value, point.benchmark_value]);
    const min = Math.min(...values);
    const max = Math.max(...values);
    const span = max - min || 1;
    const plotWidth = WIDTH - PAD.left - PAD.right;
    const plotHeight = HEIGHT - PAD.top - PAD.bottom;
    const x = (index: number) =>
      PAD.left + (points.length === 1 ? plotWidth / 2 : (index / (points.length - 1)) * plotWidth);
    const y = (value: number) => PAD.top + plotHeight - ((value - min) / span) * plotHeight;
    const line = (pick: (point: GrowthPoint) => number) =>
      points.map((point, index) => `${index === 0 ? "M" : "L"}${x(index)},${y(pick(point))}`).join(" ");
    const ticks = [min, min + span / 2, max];
    return { min, max, x, y, ticks, asset: line((p) => p.asset_value), benchmark: line((p) => p.benchmark_value) };
  }, [points]);

  if (points.length === 0) return null;

  const first = points[0]!;
  const last = points[points.length - 1]!;
  const active = cursor === null ? null : points[cursor];

  function locate(clientX: number) {
    const node = frame.current;
    if (!node) return;
    const box = node.getBoundingClientRect();
    const ratio = (clientX - box.left) / box.width;
    const plotStart = PAD.left / WIDTH;
    const plotEnd = (WIDTH - PAD.right) / WIDTH;
    const within = (ratio - plotStart) / (plotEnd - plotStart);
    const index = Math.round(within * (points.length - 1));
    setCursor(Math.max(0, Math.min(points.length - 1, index)));
  }

  return (
    <figure className="m-0 flex flex-col gap-2">
      <div className="flex flex-wrap items-center gap-x-5 gap-y-1 text-[11px] text-muted">
        <span className="flex items-center gap-1.5">
          <span aria-hidden="true" className="inline-block h-[3px] w-4 rounded bg-accent" />
          {ticker}
        </span>
        <span className="flex items-center gap-1.5">
          <span aria-hidden="true" className="inline-block h-[3px] w-4 rounded bg-muted" />
          {benchmark}
        </span>
        <span className="ml-auto">{t("basis")}</span>
      </div>

      <div className="relative rounded-card border border-line bg-panel p-2">
        <svg
          ref={frame}
          viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
          className="block h-auto w-full touch-pan-y"
          role="img"
          aria-label={t("alt", {
            ticker,
            benchmark,
            start: first.date,
            end: last.date,
            assetEnd: money(last.asset_value) ?? "",
            benchmarkEnd: money(last.benchmark_value) ?? "",
          })}
          onPointerMove={(event) => locate(event.clientX)}
          onPointerLeave={() => setCursor(null)}
        >
          <defs>
            <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="var(--color-accent)" stopOpacity="0.12" />
              <stop offset="100%" stopColor="var(--color-accent)" stopOpacity="0" />
            </linearGradient>
          </defs>
          {geometry.ticks.map((value) => (
            <g key={value}>
              <line
                x1={PAD.left}
                x2={WIDTH - PAD.right}
                y1={geometry.y(value)}
                y2={geometry.y(value)}
                stroke="var(--color-line)"
                strokeWidth="1"
              />
              <text
                x={PAD.left - 8}
                y={geometry.y(value) + 3}
                textAnchor="end"
                fontSize="10"
                fill="var(--color-muted)"
              >
                {money(value)}
              </text>
            </g>
          ))}
          <path
            d={`${geometry.asset} L${geometry.x(points.length - 1)},${HEIGHT - PAD.bottom} L${geometry.x(0)},${HEIGHT - PAD.bottom} Z`}
            fill={`url(#${gradientId})`}
            stroke="none"
          />
          <path
            d={geometry.benchmark}
            fill="none"
            stroke="var(--color-muted)"
            strokeWidth="2"
            strokeLinecap="round"
          />
          <path
            d={geometry.asset}
            fill="none"
            stroke="var(--color-accent)"
            strokeWidth="3"
            strokeLinecap="round"
          />
          <text x={PAD.left} y={HEIGHT - 8} fontSize="10" fill="var(--color-muted)">
            {first.date}
          </text>
          <text
            x={WIDTH - PAD.right}
            y={HEIGHT - 8}
            fontSize="10"
            textAnchor="end"
            fill="var(--color-muted)"
          >
            {last.date}
          </text>
          {active && cursor !== null ? (
            <g>
              <line
                x1={geometry.x(cursor)}
                x2={geometry.x(cursor)}
                y1={PAD.top}
                y2={HEIGHT - PAD.bottom}
                stroke="var(--color-line-strong)"
                strokeDasharray="3 3"
              />
              <circle
                cx={geometry.x(cursor)}
                cy={geometry.y(active.benchmark_value)}
                r="4"
                fill="var(--color-muted)"
                stroke="white"
                strokeWidth="2"
              />
              <circle
                cx={geometry.x(cursor)}
                cy={geometry.y(active.asset_value)}
                r="5"
                fill="var(--color-accent)"
                stroke="white"
                strokeWidth="2"
              />
            </g>
          ) : null}
        </svg>

        {active ? (
          <div
            aria-hidden="true"
            className="pointer-events-none absolute top-3 left-1/2 -translate-x-1/2 rounded-md bg-ink px-3 py-2 text-[11px] text-paper shadow-float"
          >
            <b className="block">{active.date}</b>
            <span className="block">
              {ticker} {money(active.asset_value)}
            </span>
            <span className="block opacity-80">
              {benchmark} {money(active.benchmark_value)}
            </span>
          </div>
        ) : null}
      </div>

      <figcaption className="text-[11px] text-muted">
        {t("caption", {
          ticker,
          benchmark,
          start: first.date,
          end: last.date,
          initial: money(first.asset_value) ?? "",
        })}
      </figcaption>
    </figure>
  );
}
