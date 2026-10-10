import { redirect } from 'next/navigation';

/**
 * D-172 §2 — the admin panel is the only surface this track ships today, so the
 * root path forwards to it instead of rendering an empty placeholder page.
 */
export default function Home() {
  redirect('/admin');
}
