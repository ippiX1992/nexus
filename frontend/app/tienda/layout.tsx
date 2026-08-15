import type { Metadata } from "next";
import { StoreChrome } from "@/components/store/StoreChrome";
import "./storefront.css";

export const metadata: Metadata = {
  title: "ClickHome · Tienda",
  description: "Tecnología y hogar. Envíos a todo el Ecuador.",
};

export default function StoreLayout({ children }: { children: React.ReactNode }) {
  return <StoreChrome storeName="ClickHome">{children}</StoreChrome>;
}
