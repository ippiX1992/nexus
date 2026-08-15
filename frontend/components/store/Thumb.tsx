// The demo catalog has no product images, so we render a deterministic gradient
// tile with the product initials. Same name -> same colours, which keeps the
// grid stable and reads as an intentional design rather than a broken <img>.
export function Thumb({ name }: { name: string }) {
  let hash = 0;
  for (let i = 0; i < name.length; i++) hash = (hash * 31 + name.charCodeAt(i)) >>> 0;
  const hue = hash % 360;
  const hue2 = (hue + 42) % 360;
  const initials = name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((word) => word[0])
    .join("")
    .toUpperCase();
  return (
    <div className="sf-thumb" style={{ background: `linear-gradient(135deg, hsl(${hue} 68% 56%), hsl(${hue2} 70% 44%))` }} aria-hidden="true">
      <span>{initials}</span>
    </div>
  );
}
