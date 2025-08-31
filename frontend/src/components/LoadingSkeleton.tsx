import React from 'react';

export const LoadingSkeleton: React.FC = () => {
  return (
    <div className="loading-skeleton" aria-live="polite" aria-label="Loading search results">
      {Array.from({length: 3}).map((_, i) => (
        <div key={i} className="skeleton-card">
          <div className="skeleton-header"></div>
          <div className="skeleton-video"></div>
          <div className="skeleton-text"></div>
          <div className="skeleton-text"></div>
        </div>
      ))}
    </div>
  );
};
