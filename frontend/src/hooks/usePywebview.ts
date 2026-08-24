import { useState, useEffect } from 'react';

export function usePywebview() {
  const [isReady, setIsReady] = useState(false);

  useEffect(() => {
    // Check if pywebview is already injected
    if (window.pywebview) {
      setIsReady(true);
      return;
    }

    // Wait for the custom event fired by pywebview
    const handleReady = () => {
      setIsReady(true);
    };

    window.addEventListener('pywebviewready', handleReady);
    
    // Safety timeout - in dev mode, pywebview might not be there
    const timeout = setTimeout(() => {
      if (!window.pywebview) {
         console.warn("pywebview not detected. Running in mock mode?");
         // You could initialize a mock object here for purely web testing
         setIsReady(true); 
      }
    }, 2000);

    return () => {
      window.removeEventListener('pywebviewready', handleReady);
      clearTimeout(timeout);
    };
  }, []);

  return {
    isReady,
    api: isReady && window.pywebview ? window.pywebview.api : null,
  };
}
