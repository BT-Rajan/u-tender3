import { useEffect, useState } from "react";
import QRCode from "qrcode";

/** A QR code image for `value`. Generated in the browser, so the link is never sent to another service. */
export function QrCode({ value, alt }: { value: string; alt: string }) {
  const [src, setSrc] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    QRCode.toDataURL(value, { margin: 1, width: 256, color: { dark: "#16324F", light: "#FFFFFF" } })
      .then((url) => {
        if (active) setSrc(url);
      })
      .catch(() => {
        if (active) setSrc(null);
      });
    return () => {
      active = false;
    };
  }, [value]);

  if (!src) {
    return <div className="h-64 w-64 rounded bg-paper" aria-hidden="true" />;
  }
  return <img src={src} alt={alt} width={256} height={256} className="h-64 w-64 rounded bg-white p-2" />;
}
