import { getTranslations } from "next-intl/server";
import { manifest } from "@/lib/data/snapshots";

interface Props {
  /** The snapshot date this page was built from, when the page has one. */
  asOf?: string | null;
  marketThrough?: string | null;
}

export async function SiteFooter({ asOf, marketThrough }: Props) {
  const t = await getTranslations("footer");
  const data = manifest();

  return (
    <footer className="border-t border-line">
      <div className="lens-shell flex flex-col gap-4 py-7 text-xs text-muted md:flex-row md:items-start md:justify-between">
        <div className="flex flex-col gap-1">
          <span className="font-bold text-ink">Company Lens</span>
          <span>{t("boundary")}</span>
          <span>{t("universe")}</span>
        </div>
        <div className="flex flex-col gap-1 md:items-end">
          {asOf ? <span>{t("snapshot", { date: asOf })}</span> : null}
          {marketThrough ? <span>{t("market", { date: marketThrough })}</span> : null}
          <span>{t("sources")}</span>
          {data.source === "fixtures" ? (
            <span className="font-bold text-caution">{t("fixtures")}</span>
          ) : null}
        </div>
      </div>
    </footer>
  );
}
