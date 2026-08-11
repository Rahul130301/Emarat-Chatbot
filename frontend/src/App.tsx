import { useState, useEffect } from 'react';
import Login from './components/Login';
import Chat from './components/Chat';

const SESSION_TIMEOUT_MS = 30 * 60 * 1000; // 30 minutes

function App() {
  const [sessionId, setSessionId] = useState<string | null>(null);

  useEffect(() => {
    // Check for existing session in localStorage
    const storedSession = localStorage.getItem('chat_session_id');
    const storedActivity = localStorage.getItem('chat_last_activity');
    
    if (storedSession && storedActivity) {
      const timeSinceActivity = Date.now() - parseInt(storedActivity, 10);
      if (timeSinceActivity < SESSION_TIMEOUT_MS) {
        setSessionId(storedSession);
      } else {
        handleLogout();
      }
    }
  }, []);

  useEffect(() => {
    // Auto logout interval check
    if (!sessionId) return;

    const interval = setInterval(() => {
      const storedActivity = localStorage.getItem('chat_last_activity');
      if (storedActivity && Date.now() - parseInt(storedActivity, 10) > SESSION_TIMEOUT_MS) {
        handleLogout();
        alert('Session expired due to inactivity. Please login again.');
      }
    }, 60000); // Check every minute

    return () => clearInterval(interval);
  }, [sessionId]);

  const updateActivity = () => {
    localStorage.setItem('chat_last_activity', Date.now().toString());
  };

  useEffect(() => {
    // Global activity tracker to keep session alive during reading/mouse movement
    if (!sessionId) return;
    
    let throttleTimeout: NodeJS.Timeout | null = null;
    const handleGlobalActivity = () => {
      if (!throttleTimeout) {
        updateActivity();
        throttleTimeout = setTimeout(() => {
          throttleTimeout = null;
        }, 5000); // Throttle updates to every 5 seconds
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

  const handleLogin = (newSessionId: string) => {
    const now = Date.now();
    setSessionId(newSessionId);
    localStorage.setItem('chat_session_id', newSessionId);
    localStorage.setItem('chat_last_activity', now.toString());

    // Add to sessions registry if not exists
    const sessions = JSON.parse(localStorage.getItem('chat_sessions') || '[]');
    if (!sessions.find((s: any) => s.id === newSessionId)) {
      sessions.unshift({ id: newSessionId, title: 'New Chat', updatedAt: now });
      localStorage.setItem('chat_sessions', JSON.stringify(sessions));
    }
  };

  const handleLogout = () => {
    setSessionId(null);
    localStorage.removeItem('chat_session_id');
    localStorage.removeItem('chat_last_activity');
    // Clear all history
    const sessions = JSON.parse(localStorage.getItem('chat_sessions') || '[]');
    sessions.forEach((s: any) => localStorage.removeItem(`chat_history_${s.id}`));
    localStorage.removeItem('chat_sessions');
  };

  const handleNewChat = async () => {
    try {
      const res = await fetch('http://localhost:8000/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username: "user", password: "newchat" })
      });
      const data = await res.json();
      if (data.session_id) {
        handleLogin(data.session_id);
      }
    } catch (e) {
      console.error("Failed to start new chat", e);
    }
  };

  const handleSwitchSession = (id: string) => {
    setSessionId(id);
    updateActivity();
    localStorage.setItem('chat_session_id', id);
  };

  return (
    <>
      {sessionId ? (
        <Chat 
          key={sessionId}
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
