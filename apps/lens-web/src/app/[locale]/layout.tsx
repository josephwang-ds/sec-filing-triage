import type { Metadata } from "next";
import type { ReactNode } from "react";
import { notFound } from "next/navigation";
import { NextIntlClientProvider, hasLocale } from "next-intl";
import { getTranslations, setRequestLocale } from "next-intl/server";
import { routing } from "@/i18n/routing";

export function generateStaticParams() {
  return routing.locales.map((locale) => ({ locale }));
}

export async function generateMetadata({
  params,
}: {
  params: Promise<{ locale: string }>;
}): Promise<Metadata> {
  const { locale } = await params;
  if (!hasLocale(routing.locales, locale)) return {};
  const t = await getTranslations({ locale, namespace: "meta" });
  return {
    title: { default: t("title"), template: `%s · Company Lens` },
    description: t("description"),
    // Both languages are indexable and each points at the other, so a search
    // result lands a reader on the version they can read.
    alternates: {
      canonical: `/${locale}`,
      languages: { zh: "/zh", en: "/en" },
    },
  };
}

export default async function LocaleLayout({
  children,
  params,
}: {
  children: ReactNode;
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  if (!hasLocale(routing.locales, locale)) notFound();
  // Without this the page renders dynamically and loses static generation.
  setRequestLocale(locale);

  return (
    <html lang={locale} suppressHydrationWarning>
      <body className="min-h-dvh bg-paper antialiased">
        <NextIntlClientProvider>
          <a
            href="#main"
            className="sr-only focus:not-sr-only focus:absolute focus:z-50 focus:m-2 focus:rounded-md focus:bg-ink focus:px-3 focus:py-2 focus:text-paper"
          >
            {(await getTranslations({ locale, namespace: "nav" }))("skip")}
          </a>
          {children}
        </NextIntlClientProvider>
      </body>
    </html>
  );
}
