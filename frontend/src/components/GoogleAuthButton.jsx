import { useState } from 'react';
import { Button } from '@/components/ui/button';
import { Loader2 } from 'lucide-react';
import { api } from '@/lib/api';

/**
 * Google "G" mark — official 4-colour glyph rendered as inline SVG so we
 * don't ship a remote image (CSP-friendly, fully offline).
 */
const GoogleGlyph = ({ className = 'h-4 w-4' }) => (
  <svg className={className} viewBox="0 0 18 18" aria-hidden="true">
    <path
      fill="#4285F4"
      d="M17.64 9.2c0-.64-.06-1.25-.16-1.84H9v3.48h4.84a4.14 4.14 0 0 1-1.8 2.71v2.26h2.92c1.7-1.57 2.68-3.88 2.68-6.61z"
    />
    <path
      fill="#34A853"
      d="M9 18c2.43 0 4.47-.8 5.96-2.18l-2.92-2.26c-.81.54-1.84.86-3.04.86-2.34 0-4.32-1.58-5.03-3.7H.96v2.32A9 9 0 0 0 9 18z"
    />
    <path
      fill="#FBBC05"
      d="M3.97 10.72A5.41 5.41 0 0 1 3.68 9c0-.6.1-1.18.29-1.72V4.96H.96A9 9 0 0 0 0 9c0 1.45.35 2.83.96 4.04l3.01-2.32z"
    />
    <path
      fill="#EA4335"
      d="M9 3.58c1.32 0 2.5.45 3.43 1.34l2.58-2.58C13.46.89 11.43 0 9 0A9 9 0 0 0 .96 4.96l3.01 2.32C4.68 5.16 6.66 3.58 9 3.58z"
    />
  </svg>
);

/**
 * "Continue with Google" button. Resolves the Google OAuth start URL from
 * the backend, then does a full-page redirect — no popup, no PKCE library
 * needed.
 *
 * Props:
 *   • withCalendar (bool, default false) — also requests calendar.readonly.
 *   • next (string)                       — relative path to land on after sign-in.
 *   • label (string)                      — visible button text.
 *   • testId (string)                     — data-testid override.
 */
export const GoogleAuthButton = ({
  withCalendar = false,
  next = null,
  label,
  testId = 'google-auth-button',
  disabled = false,
}) => {
  const [busy, setBusy] = useState(false);

  const onClick = async () => {
    setBusy(true);
    try {
      const { authorization_url } = await api.googleLoginStart({
        withCalendar,
        next,
      });
      // Full-page redirect — Google's consent screen takes over from here.
      window.location.assign(authorization_url);
    } catch (err) {
      setBusy(false);
      // Surface a console hint so the user knows the backend isn't wired up.
      console.error('googleLoginStart failed', err);
      // eslint-disable-next-line no-alert
      alert(
        err?.response?.data?.detail ||
          'Google sign-in is not configured on this server.'
      );
    }
  };

  return (
    <Button
      type="button"
      variant="outline"
      onClick={onClick}
      disabled={busy || disabled}
      className="w-full rounded-xl border-border bg-background hover:bg-accent/5"
      data-testid={testId}
    >
      {busy ? (
        <Loader2 className="h-4 w-4 me-2 animate-spin" />
      ) : (
        <GoogleGlyph className="h-4 w-4 me-2" />
      )}
      {label}
    </Button>
  );
};
