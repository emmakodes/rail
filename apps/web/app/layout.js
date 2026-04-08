import "./globals.css";

export const metadata = {
  title: "Simple Todo",
  description: "Minimal Next.js frontend for a FastAPI todo API",
};

export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
