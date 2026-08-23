import "./styles.css";import type {Metadata} from "next";
export const metadata:Metadata={title:"Smart Money",description:"Trading intelligence platform"};
export default function Layout({children}:{children:React.ReactNode}){return <html lang="ru"><body>{children}</body></html>}
