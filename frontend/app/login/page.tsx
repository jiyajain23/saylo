import Link from "next/link";

export const metadata = { title: "Sign in · saylo" };

export default function LoginPage() {
  return <div className="state-message">You are signed in. <Link href="/dashboard">Open your dashboard</Link></div>;
}
