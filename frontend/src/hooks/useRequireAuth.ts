import { useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from './useAuth';

/**
 * Hook that redirects to /login if the user is not authenticated.
 * Use in page components that require authentication.
 *
 * Uses the httpOnly cookie-based auth system (useAuth), not localStorage.
 * Note: App.tsx already handles auth routing, so this hook is a
 * defense-in-depth guard for page components.
 */
export function useRequireAuth() {
  const navigate = useNavigate();
  const { isAuthenticated } = useAuth();

  useEffect(() => {
    if (!isAuthenticated) {
      navigate('/login', { replace: true });
    }
  }, [isAuthenticated, navigate]);
}
