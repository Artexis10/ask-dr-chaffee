import React from 'react';

export const LoadingSkeleton: React.FC = () => {
  return (
    <div className="loading-skeleton">
      <div className="loading-message">
        <div className="loading-spinner">
          <div className="spinner-circle"></div>
        </div>
        <p>Searching through Dr. Chaffee's knowledge base...</p>
      </div>
      
      <div className="skeleton-card">
        <div className="skeleton-header"></div>
        <div className="skeleton-video"></div>
        <div className="skeleton-clips">
          <div className="skeleton-clip-header"></div>
          <div className="skeleton-clip">
            <div className="skeleton-text"></div>
            <div className="skeleton-text"></div>
            <div className="skeleton-text"></div>
            <div className="skeleton-actions"></div>
          </div>
        </div>
      </div>
      
      <div className="skeleton-card">
        <div className="skeleton-header"></div>
        <div className="skeleton-video"></div>
        <div className="skeleton-clips">
          <div className="skeleton-clip-header"></div>
          <div className="skeleton-clip">
            <div className="skeleton-text"></div>
            <div className="skeleton-text"></div>
            <div className="skeleton-actions"></div>
          </div>
        </div>
      </div>
      
      <style jsx>{`
        .loading-message {
          display: flex;
          align-items: center;
          justify-content: center;
          gap: var(--space-4);
          margin-bottom: var(--space-6);
          padding: var(--space-4);
          background: var(--color-card);
          border-radius: var(--radius-xl);
          box-shadow: var(--shadow-sm);
        }
        
        .loading-message p {
          color: var(--color-text);
          font-weight: 500;
          font-size: 1.1rem;
        }
        
        .loading-spinner {
          width: 40px;
          height: 40px;
          position: relative;
          flex-shrink: 0;
        }
        
        .spinner-circle {
          position: absolute;
          width: 100%;
          height: 100%;
          border: 3px solid rgba(59, 130, 246, 0.2);
          border-top-color: var(--color-primary);
          border-radius: 50%;
          animation: spinner 1s linear infinite;
        }
        
        @keyframes spinner {
          to { transform: rotate(360deg); }
        }
        
        .skeleton-clip-header {
          height: 24px;
          width: 40%;
          background: var(--color-border-light);
          border-radius: var(--radius-lg);
          margin-bottom: var(--space-4);
        }
        
        .skeleton-clip {
          padding: var(--space-4);
          background: var(--color-background);
          border-radius: var(--radius-xl);
          margin-bottom: var(--space-3);
        }
        
        .skeleton-actions {
          height: 32px;
          margin-top: var(--space-3);
          background: var(--color-border-light);
          border-radius: var(--radius-lg);
          width: 60%;
        }
      `}</style>
    </div>
  );
};
