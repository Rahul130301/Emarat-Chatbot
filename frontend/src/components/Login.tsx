import { useState } from 'react';

const API_BASE = import.meta.env.VITE_API_URL ?? 'http://localhost:8000';

interface LoginProps {
  onLogin: (sessionId: string, username: string, displayName?: string) => void;
}

export default function Login(_props: LoginProps) {
  const [error, setError] = useState('');
  const [isLoading, setIsLoading] = useState(false);

  const handleMicrosoftLogin = () => {
    setIsLoading(true);
    setError('');
    // Full browser redirect — Microsoft sets cookies during the flow.
    // The backend /api/v1/auth/azure-ad/login will redirect to Microsoft login page.
    window.location.href = `${API_BASE}/api/v1/auth/azure-ad/login`;
  };

  return (
    <div className="login-container fade-in">
      <div className="login-card">
        {/* Logo / Brand */}
        <div style={{ display: 'flex', justifyContent: 'center', marginBottom: '1.5rem' }}>
          <div style={{
            width: '64px', height: '64px', borderRadius: '16px',
            background: 'linear-gradient(135deg, #65a30d, #4d7c0f)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            boxShadow: '0 8px 24px rgba(101,163,13,0.35)',
          }}>
            <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M3 12L12 3l9 9"/>
              <path d="M5 10v9a1 1 0 001 1h4v-5h4v5h4a1 1 0 001-1v-9"/>
            </svg>
          </div>
        </div>

        <div className="login-header">
          <h1>Emarat Aviation</h1>
          <p>Sign in with your organizational account to continue</p>
        </div>

        {error && (
          <div className="error-message" style={{ marginBottom: '1rem' }}>
            {error}
          </div>
        )}

        {/* Microsoft SSO Button */}
        <button
          id="microsoft-sso-btn"
          onClick={handleMicrosoftLogin}
          disabled={isLoading}
          style={{
            width: '100%',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            gap: '12px',
            padding: '13px 20px',
            background: isLoading ? '#1e293b' : '#ffffff',
            color: '#1e293b',
            border: '1px solid #d1d5db',
            borderRadius: '8px',
            fontSize: '0.95rem',
            fontWeight: '600',
            cursor: isLoading ? 'not-allowed' : 'pointer',
            transition: 'all 0.2s ease',
            fontFamily: 'inherit',
            opacity: isLoading ? 0.7 : 1,
          }}
          onMouseEnter={e => {
            if (!isLoading) {
              (e.currentTarget as HTMLButtonElement).style.background = '#f1f5f9';
              (e.currentTarget as HTMLButtonElement).style.boxShadow = '0 4px 12px rgba(0,0,0,0.15)';
            }
          }}
          onMouseLeave={e => {
            (e.currentTarget as HTMLButtonElement).style.background = isLoading ? '#1e293b' : '#ffffff';
            (e.currentTarget as HTMLButtonElement).style.boxShadow = 'none';
          }}
        >
          {/* Microsoft logo SVG */}
          <svg width="20" height="20" viewBox="0 0 21 21" fill="none" xmlns="http://www.w3.org/2000/svg">
            <rect x="1" y="1" width="9" height="9" fill="#F25022"/>
            <rect x="11" y="1" width="9" height="9" fill="#7FBA00"/>
            <rect x="1" y="11" width="9" height="9" fill="#00A4EF"/>
            <rect x="11" y="11" width="9" height="9" fill="#FFB900"/>
          </svg>
          {isLoading ? 'Redirecting to Microsoft...' : 'Sign in with Microsoft'}
        </button>

        <p style={{
          textAlign: 'center',
          marginTop: '1.5rem',
          fontSize: '0.78rem',
          color: '#475569',
          lineHeight: '1.5',
        }}>
          By signing in, you agree to your organization's usage policies.
          <br />
          Your account is managed by your IT administrator.
        </p>
      </div>
    </div>
  );
}
