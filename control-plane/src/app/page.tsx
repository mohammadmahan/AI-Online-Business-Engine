import { redirect } from 'next/navigation';

/** The control plane's entry point is the command overview (D-171 §5.1). */
export default function RootPage() {
  redirect('/dashboard');
}
