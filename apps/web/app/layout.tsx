import './globals.css';
import MobileApp from '../components/MobileApp';
export const metadata={icons:{apple:'/florp-180.png'},appleWebApp:{capable:true,title:'Florp'},title:'Florp — From blueprint to possibility',description:'Architectural visualisation workspace'};
export default function RootLayout({children}:{children:React.ReactNode}){return <html lang="en"><body><MobileApp/>{children}</body></html>}
