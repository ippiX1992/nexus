import type {Metadata} from "next"; import "./globals.css";
export const metadata:Metadata={title:"Nexus Identity",description:"Administración segura de identidad y empresas"};
export default function Layout({children}:{children:React.ReactNode}){return <html lang="es"><body>{children}</body></html>}
