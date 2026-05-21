import './globals.css';

export const metadata = {
  title: 'KubePACS - Performant, Highly Available, and Cost Efficient Spot Instances',
  description: 'Kubernetes Cluster Using Performant, Highly Available, and Cost Efficient Spot Instances',
  keywords: 'kubernetes, spot instances, spotlake, cloud computing, cost efficiency, performance aware',
  icons: {
    icon: '/favicon.png',
    shortcut: '/favicon.png',
    apple: '/favicon.png',
  },
};

export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <body>
        <main>{children}</main>
      </body>
    </html>
  );
}
