import { useState, useEffect } from 'react';
import Login from './components/Login';
import Chat from './components/Chat';

const API_BASE = import.meta.env.VITE_API_URL ?? 'http://localhost:8000';
const SESSION_TIMEOUT_MS = 30 * 60 * 1000; // 30 minutes

function App() {
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [isCheckingAuth, setIsCheckingAuth] = useState(true); // prevent login flash on load

  // ── On every page load / refresh: check if the user is already authenticated ──
  useEffect(() => {
    const checkAuth = async () => {
      try {
        // 1. Check URL parameters passed from SSO redirect
        const params = new URLSearchParams(window.location.search);
        const ssoSessionId = params.get('session_id');
        const ssoUsername = params.get('username');
        const ssoDisplayName = params.get('display_name');

        if (ssoSessionId && ssoUsername) {
          handleLogin(ssoSessionId, ssoUsername, ssoDisplayName || ssoUsername);
          // Register session in memory with backend
          fetch(`${API_BASE}/sessions/register`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ username: ssoUsername, session_id: ssoSessionId }),
          }).catch(console.error);
          return;
        }

        // 2. Otherwise check existing session cookie
        const res = await fetch(`${API_BASE}/api/v1/auth/me`, {
          credentials: 'include', // send the HTTP-only session cookie
        });

        if (res.ok) {
          const data = await res.json();
          // User has a valid session cookie → restore session
          handleLogin(data.session_id, data.username, data.display_name);
        }
        // 401 = not logged in → show login page (do nothing)
      } catch (err) {
        console.error('Auth check failed:', err);
      } finally {
        // Remove ?sso=ok and params from URL without triggering a reload
        if (window.location.search.includes('sso=ok')) {
          window.history.replaceState({}, '', window.location.pathname);
        }
        setIsCheckingAuth(false);
      }
    };

    checkAuth();
  }, []);

  // ── Session timeout auto-logout ───────────────────────────────────────────
  useEffect(() => {
    if (!sessionId) return;

    const interval = setInterval(() => {
      const storedActivity = localStorage.getItem('chat_last_activity');
      if (storedActivity && Date.now() - parseInt(storedActivity, 10) > SESSION_TIMEOUT_MS) {
        handleLogout();
        alert('Session expired due to inactivity. Please sign in again.');
      }
    }, 60000); // Check every minute

    return () => clearInterval(interval);
  }, [sessionId]);

  // ── Global activity tracking (keep session alive) ─────────────────────────
  useEffect(() => {
    if (!sessionId) return;

    let throttleTimeout: ReturnType<typeof setTimeout> | null = null;
    const handleGlobalActivity = () => {
      if (!throttleTimeout) {
        localStorage.setItem('chat_last_activity', Date.now().toString());
        throttleTimeout = setTimeout(() => { throttleTimeout = null; }, 5000);
      }
    };

    window.addEventListener('mousemove', handleGlobalActivity);
    window.addEventListener('keydown', handleGlobalActivity);
    window.addEventListener('click', handleGlobalActivity);

    return () => {
      window.removeEventListener('mousemove', handleGlobalActivity);
      window.removeEventListener('keydown', handleGlobalActivity);
      window.removeEventListener('click', handleGlobalActivity);
      if (throttleTimeout) clearTimeout(throttleTimeout);
    };
  }, [sessionId]);

  const handleLogin = (newSessionId: string, username: string, displayName?: string) => {
    setSessionId(newSessionId);
    localStorage.setItem('chat_last_activity', Date.now().toString());
    localStorage.setItem('sidebar_visible', 'true');
    // Store username for new-chat creation
    localStorage.setItem('chat_username', username);
    localStorage.setItem('chat_display_name', displayName || username);
  };

  const handleLogout = async () => {
    try {
      // Clear the server-side session cookie
      await fetch(`${API_BASE}/api/v1/auth/logout`, {
        method: 'POST',
        credentials: 'include',
      });
    } catch (err) {
      console.error('Logout request failed:', err);
    }
    setSessionId(null);
    localStorage.removeItem('chat_last_activity');
    localStorage.removeItem('sidebar_visible');
    localStorage.removeItem('chat_username');
    localStorage.removeItem('chat_display_name');
  };

  // Called by Chat.tsx after it creates the new session (Chat knows the agentKey)
  const handleNewChat = (newSessionId: string) => {
    const username = localStorage.getItem('chat_username') || 'user';
    const displayName = localStorage.getItem('chat_display_name') || username;
    handleLogin(newSessionId, username, displayName);
  };

  const updateActivity = () => {
    localStorage.setItem('chat_last_activity', Date.now().toString());
  };

  const handleSwitchSession = (id: string) => {
    setSessionId(id);
    updateActivity();
  };

  // Show nothing while we check the cookie (prevents login-page flash on refresh)
  if (isCheckingAuth) {
    return (
      <div style={{
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        height: '100vh', background: '#0a0f1e', color: '#64748b',
        fontSize: '0.9rem', gap: '12px',
      }}>
        <div style={{
          width: '20px', height: '20px', border: '2px solid #1e293b',
          borderTop: '2px solid #65a30d', borderRadius: '50%',
          animation: 'spin 0.8s linear infinite',
        }} />
        Checking authentication...
        <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
      </div>
    );
  }

  return (
    <>
      {sessionId ? (
        <Chat
          sessionId={sessionId}
          onLogout={handleLogout}
          onActivity={updateActivity}
          onNewChat={handleNewChat}
          onSwitchSession={handleSwitchSession}
        />
      ) : (
        <Login onLogin={handleLogin} />
      )}
    </>
  );
}

export default App;
