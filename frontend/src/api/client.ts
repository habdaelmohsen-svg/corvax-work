const ACCESS_KEY = 'corvax_token';
const USER_KEY = 'corvax_user';
const COMPANY_KEY = 'corvax_company';

// AUDIT H-07: the client refreshed the access token but did nothing useful when
// the refresh failed - it returned the 401 and left the user staring at a broken
// screen with stale data on the page. It also fired one refresh per concurrent
// request, so an expired session produced a burst of refresh calls.

let refreshInFlight: Promise<string | null> | null = null;

function endSession(reason: 'expired' | 'password') {
  sessionStorage.removeItem(ACCESS_KEY);
  if (reason === 'expired') {
    localStorage.removeItem(USER_KEY);
    localStorage.removeItem(COMPANY_KEY);
  }
  // Reload so the app returns to the login (or password) screen with clean state
  // instead of rendering data the session can no longer fetch.
  if (typeof window !== 'undefined' && !window.location.pathname.startsWith('/login')) {
    window.location.replace('/');
  }
}

async function rotateAccessToken(): Promise<string | null> {
  // Single-flight: concurrent 401s share one refresh call.
  if (refreshInFlight) return refreshInFlight;
  refreshInFlight = (async () => {
    try {
      const response = await fetch('/api/v1/auth/refresh', {
        method: 'POST',
        credentials: 'include',
      });
      if (!response.ok) {
        sessionStorage.removeItem(ACCESS_KEY);
        return null;
      }
      const payload = await response.json();
      sessionStorage.setItem(ACCESS_KEY, payload.access_token);
      return payload.access_token as string;
    } catch {
      sessionStorage.removeItem(ACCESS_KEY);
      return null;
    } finally {
      // Allow a new refresh on the next expiry.
      setTimeout(() => { refreshInFlight = null; }, 0);
    }
  })();
  return refreshInFlight;
}

export async function apiFetch(input: RequestInfo | URL, init: RequestInit = {}): Promise<Response> {
  const headers = new Headers(init.headers);
  const accessToken = sessionStorage.getItem(ACCESS_KEY);
  if (accessToken) headers.set('Authorization', `Bearer ${accessToken}`);

  let response = await fetch(input, {...init, headers, credentials: 'include'});

  // AUDIT H-02 companion: the server now answers 428 while a password change is
  // pending. Send the user to the mandatory change screen instead of showing an
  // unexplained failure on every panel.
  if (response.status === 428 && !String(input).includes('/auth/password/change')) {
    try {
      const raw = localStorage.getItem(USER_KEY);
      if (raw) {
        const stored = JSON.parse(raw);
        stored.require_password_change = true;
        localStorage.setItem(USER_KEY, JSON.stringify(stored));
      }
    } catch { /* ignore malformed storage */ }
    endSession('password');
    return response;
  }

  if (response.status !== 401 || String(input).includes('/auth/refresh')) return response;

  const rotated = await rotateAccessToken();
  if (!rotated) {
    endSession('expired');
    return response;
  }
  headers.set('Authorization', `Bearer ${rotated}`);
  response = await fetch(input, {...init, headers, credentials: 'include'});
  if (response.status === 401) endSession('expired');
  return response;
}

export function clearSessionTokens() {
  sessionStorage.removeItem(ACCESS_KEY);
  localStorage.removeItem(USER_KEY);
  localStorage.removeItem(COMPANY_KEY);
}
