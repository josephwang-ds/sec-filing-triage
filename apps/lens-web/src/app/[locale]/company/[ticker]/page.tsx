export default async function Placeholder({ params }: { params: Promise<{ ticker: string }> }) {
  const { ticker } = await params;
  return <main id="main" className="lens-shell py-10">{ticker}</main>;
}
