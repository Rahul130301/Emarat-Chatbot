import { useState } from 'react';
import { LogIn } from 'lucide-react';

interface LoginProps {
  onLogin: (sessionId: string) => void;
}

export default function Login({ onLogin }: LoginProps) {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [isLoading, setIsLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setIsLoading(true);

    try {
      const res = await fetch('http://localhost:8000/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username, password })
      });

      const data = await res.json();
      
      if (res.ok && data.session_id) {
        onLogin(data.session_id);
      } else {
        setError(data.detail || 'Login failed. Please try again.');
      }
    } catch (err) {
      setError('Could not connect to the server.');
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="login-container fade-in">
      <div className="login-card">
        <div className="login-header">
          <h1>Welcome Back</h1>
          <p>Login to your Emarat account</p>
        </div>
        
        {error && <div className="error-message">{error}</div>}

        <form onSubmit={handleSubmit}>
          <div className="form-group">
            <label htmlFor="username">Username</label>
            <input
              id="username"
              type="text"
              className="input"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              placeholder="Enter your username"
              required
            />
          </div>
          
          <div className="form-group">
            <label htmlFor="password">Password</label>
            <input
              id="password"
              type="password"
              className="input"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="••••••••"
              required
            />
          </div>
          
          <button type="submit" className="btn" style={{ width: '100%', marginTop: '1rem' }} disabled={isLoading}>
            {isLoading ? 'Signing in...' : (
              <>
                <LogIn size={20} />
                Sign In
              </>
            )}
          </button>
        </form>
      </div>
    </div>
  );
}
