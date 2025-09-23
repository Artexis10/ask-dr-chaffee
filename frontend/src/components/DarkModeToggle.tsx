import React, { useState, useEffect } from 'react';

export const DarkModeToggle: React.FC = () => {
  const [isDarkMode, setIsDarkMode] = useState(false);

  // Initialize dark mode based on system preference or localStorage
  useEffect(() => {
    const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
    const storedTheme = localStorage.getItem('theme');
    
    if (storedTheme === 'dark' || (!storedTheme && prefersDark)) {
      setIsDarkMode(true);
      document.documentElement.classList.add('dark-mode');
    } else {
      setIsDarkMode(false);
      document.documentElement.classList.remove('dark-mode');
    }
  }, []);

  // Toggle dark mode
  const toggleDarkMode = () => {
    if (isDarkMode) {
      document.documentElement.classList.remove('dark-mode');
      localStorage.setItem('theme', 'light');
    } else {
      document.documentElement.classList.add('dark-mode');
      localStorage.setItem('theme', 'dark');
    }
    
    setIsDarkMode(!isDarkMode);
  };

  return (
    <button 
      onClick={toggleDarkMode} 
      className="dark-mode-toggle"
      aria-label={isDarkMode ? "Switch to light mode" : "Switch to dark mode"}
      title={isDarkMode ? "Switch to light mode" : "Switch to dark mode"}
    >
      {isDarkMode ? (
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
          <path d="M12 3V4M12 20V21M21 12H20M4 12H3M18.364 18.364L17.657 17.657M6.343 6.343L5.636 5.636M18.364 5.636L17.657 6.343M6.343 17.657L5.636 18.364M16 12C16 14.2091 14.2091 16 12 16C9.79086 16 8 14.2091 8 12C8 9.79086 9.79086 8 12 8C14.2091 8 16 9.79086 16 12Z" 
            stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
        </svg>
      ) : (
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
          <path d="M21.752 15.002C20.5633 15.4975 19.2879 15.7517 18 15.75C13.4436 15.75 9.75 12.0564 9.75 7.5C9.75 6.21226 10.0043 4.93692 10.5 3.74805C5.81563 4.97317 2.75 9.28043 2.75 14.25C2.75 20.1825 7.56751 25 13.5 25C18.4693 25 22.7764 21.9348 24.002 17.251C24.0008 17.2539 24.0015 17.2539 24.002 17.251C24.0005 17.2481 23.9989 17.2452 23.9974 17.2424C23.3644 16.386 22.5926 15.6142 21.7362 14.9813C21.7334 14.9797 21.7305 14.9781 21.7277 14.9766C21.7365 14.9919 21.7444 15.0076 21.752 15.0233V15.002Z" 
            stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
        </svg>
      )}
      
      <style jsx>{`
        .dark-mode-toggle {
          position: fixed;
          bottom: 20px;
          right: 20px;
          width: 48px;
          height: 48px;
          border-radius: 50%;
          background: var(--color-card);
          border: 1px solid var(--color-border);
          color: var(--color-text);
          display: flex;
          align-items: center;
          justify-content: center;
          cursor: pointer;
          z-index: 100;
          box-shadow: var(--shadow-md);
          transition: all var(--transition-normal);
        }
        
        .dark-mode-toggle:hover {
          transform: translateY(-3px);
          box-shadow: var(--shadow-lg);
          background: ${isDarkMode ? 'var(--color-primary)' : 'var(--color-accent)'};
          color: white;
        }
        
        @media (max-width: 768px) {
          .dark-mode-toggle {
            width: 40px;
            height: 40px;
            bottom: 15px;
            right: 15px;
          }
        }
      `}</style>
    </button>
  );
};
