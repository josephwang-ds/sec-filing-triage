import { getTranslations } from "next-intl/server";
import { Section } from "@/components/ui/Section";
import { EmptyState } from "@/components/ui/EmptyState";
import { EvidenceTable } from "@/components/research/EvidenceTable";
import { researchEvidence } from "@/lib/data/research";
import { count, multiple, percent } from "@/lib/format";

function num(value: string | undefined): number | null {
  if (value === undefined || value.trim() === "") return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function cell(value: string | null): string {
  return value ?? "—";
}

/**
 * Capacity, tradability, model comparison, calibration and volatility.
 *
 * Each block is present only when its evidence files are. A missing file is
 * an unavailable section, not a blank number and not a sentence that invents one.
 */
export async function AuditSections() {
  const t = await getTranslations("research");
  const evidence = researchEvidence();
  const post = evidence.tradability.find((row) => row.population === "material, accepted post");
  const openAnchored = evidence.anchoring.find((row) => row["reaction measured from"] === "entry open");
  const calibrationReady = Boolean(evidence.calibration && evidence.calibrationComparison.length);
  const volatilityReady = Boolean(
    evidence.volatility &&
      evidence.volatilityForecasters.length &&
      evidence.volatilityRegimes.length &&
      evidence.volatilityPaired.length,
  );
  const shippedVol = evidence.volatility?.shipped;
  const calm = evidence.volatilityRegimes.find(
    (row) => row.forecaster === shippedVol && row.regime === "calm",
  );
  const turbulent = evidence.volatilityRegimes.find(
    (row) => row.forecaster === shippedVol && row.regime === "turbulent",
  );

  return (
    <>
      <Section id="capacity" eyebrow={t("nav.capacity")} title={t("capacity.title")} intro={t("capacity.intro")}>
        {evidence.capacity.length ? (
          <>
            <EvidenceTable
              caption={t("capacity.caption")}
              headers={[
                t("capacity.column.k"),
                t("capacity.column.sessions"),
                t("capacity.column.random"),
                t("capacity.column.model"),
                t("capacity.column.ceiling"),
                t("capacity.column.lift"),
                t("capacity.column.span"),
              ]}
              rows={evidence.capacity.map((row) => [
                row.capacity_k,
                cell(count(num(row.sessions))),
                cell(percent(num(row.random_floor), 1)),
                cell(percent(num(row.model), 1)),
                cell(percent(num(row.oracle_ceiling), 1)),
                cell(multiple(num(row.lift_vs_random), 2)),
                cell(percent(num(row.span_captured), 0)),
              ])}
            />
            <p className="mt-4 mb-0 max-w-[70ch] text-sm text-muted">{t("capacity.note")}</p>
          </>
        ) : (
          <EmptyState compact title={t("unavailable.title")} body={t("capacity.missing")} />
        )}
      </Section>

      <Section id="tradability" eyebrow={t("nav.tradability")} title={t("tradability.title")} intro={t("tradability.intro")}>
        {evidence.tradability.length ? (
          <>
            <p className="m-0 max-w-[70ch] text-sm">
              {t("tradability.measured", {
                share: percent(num(post?.median_share_in_open), 1) ?? t("unavailable.notInExport"),
              })}
            </p>
            <div className="mt-4">
              <EvidenceTable
                caption={t("tradability.caption")}
                headers={[t("tradability.column.population"), t("tradability.column.count"), t("tradability.column.share")]}
                rows={evidence.tradability.map((row) => [
                  row.population,
                  cell(count(num(row.filings))),
                  cell(percent(num(row.median_share_in_open), 1)),
                ])}
              />
            </div>
            <p className="mt-4 mb-0 max-w-[70ch] text-sm text-muted">
              {t("tradability.openAnchored", {
                precision: percent(num(openAnchored?.average_precision), 1) ?? t("unavailable.notInExport"),
              })}
            </p>
          </>
        ) : (
          <EmptyState compact title={t("unavailable.title")} body={t("tradability.missing")} />
        )}
      </Section>

      <Section id="models" eyebrow={t("nav.models")} title={t("models.title")} intro={t("models.intro")}>
        {evidence.modelComparison.length ? (
          <>
            <EvidenceTable
              caption={t("models.caption")}
              headers={[
                t("models.column.family"),
                t("models.column.ap"),
                t("models.column.auc"),
                t("models.column.apInterval"),
              ]}
              rows={evidence.modelComparison.map((row) => [
                row.candidate,
                cell(percent(num(row.average_precision), 1)),
                cell(multiple(num(row.roc_auc), 3)),
                `${cell(percent(num(row.average_precision_ci_low), 1))} – ${cell(percent(num(row.average_precision_ci_high), 1))}`,
              ])}
            />
            {evidence.modelPaired.length ? (
              <div className="mt-4">
                <EvidenceTable
                  caption={t("models.pairedCaption")}
                  headers={[
                    t("models.column.family"),
                    t("models.column.reference"),
                    t("models.column.difference"),
                    t("models.column.interval"),
                  ]}
                  rows={evidence.modelPaired.map((row) => [
                    row.candidate,
                    row.reference,
                    cell(multiple(num(row.difference), 3)),
                    `${cell(multiple(num(row.difference_ci_low), 3))} – ${cell(multiple(num(row.difference_ci_high), 3))}`,
                  ])}
                />
              </div>
            ) : (
              <EmptyState compact title={t("unavailable.title")} body={t("models.pairedMissing")} />
            )}
            <p className="mt-4 mb-0 max-w-[70ch] text-sm text-muted">{t("models.note")}</p>
          </>
        ) : (
          <EmptyState compact title={t("unavailable.title")} body={t("models.missing")} />
        )}
      </Section>

      <Section id="calibration" eyebrow={t("nav.calibration")} title={t("calibration.title")} intro={t("calibration.intro")}>
        {calibrationReady ? (
          <>
            <p className="m-0 max-w-[70ch] text-sm">
              {t("calibration.shipped", { method: evidence.calibration?.shipped ?? "—" })}
            </p>
            <div className="mt-4">
              <EvidenceTable
                caption={t("calibration.caption")}
                headers={[
                  t("calibration.column.method"),
                  t("calibration.column.brier"),
                  t("calibration.column.ece"),
                  t("calibration.column.ap"),
                  t("calibration.column.auc"),
                ]}
                rows={evidence.calibrationComparison.map((row) => [
                  row.method,
                  cell(multiple(num(row.brier), 3)),
                  cell(multiple(num(row.ece), 3)),
                  cell(percent(num(row.pr_auc), 1)),
                  cell(multiple(num(row.roc_auc), 3)),
                ])}
              />
            </div>
            <p className="mt-4 mb-0 max-w-[70ch] text-sm text-muted">{t("calibration.note")}</p>
          </>
        ) : (
          <EmptyState compact title={t("unavailable.title")} body={t("calibration.missing")} />
        )}
      </Section>

      <Section id="volatility" eyebrow={t("nav.volatility")} title={t("volatility.title")} intro={t("volatility.intro")}>
        {volatilityReady ? (
          <>
            <EvidenceTable
              caption={t("volatility.caption")}
              headers={[
                t("volatility.column.forecaster"),
                t("volatility.column.pinball"),
                t("volatility.column.coverage80"),
                t("volatility.column.width"),
                t("volatility.column.calibrated"),
              ]}
              rows={evidence.volatilityForecasters.map((row) => [
                row.forecaster,
                cell(multiple(num(row.pinball_mean), 3)),
                cell(percent(num(row.coverage_80), 1)),
                cell(multiple(num(row.width_80), 3)),
                evidence.volatility?.gates?.[row.forecaster ?? ""]?.calibrated
                  ? t("volatility.yes")
                  : t("volatility.no"),
              ])}
            />
            <p className="mt-4 mb-0 max-w-[70ch] text-sm text-muted">
              {t("volatility.regime", {
                shipped: shippedVol ?? "—",
                calm: percent(num(calm?.coverage_80), 1) ?? t("unavailable.notInExport"),
                turbulent: percent(num(turbulent?.coverage_80), 1) ?? t("unavailable.notInExport"),
              })}
            </p>
            <p className="mt-3 mb-0 max-w-[70ch] text-sm text-muted">{t("volatility.note")}</p>
          </>
        ) : (
          <EmptyState compact title={t("unavailable.title")} body={t("volatility.missing")} />
        )}
      </Section>
    </>
  );
}
