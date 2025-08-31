import React from 'react';

interface NoResultsProps {
  sourceFilter: string;
  query: string;
}

export const NoResults: React.FC<NoResultsProps> = ({ sourceFilter, query }) => {
  return (
    <div className="results no-results" role="main" aria-live="polite">
      <h2>No results found</h2>
      <p>
        {sourceFilter !== 'all' ? (
          <>No {sourceFilter} content found matching <strong>"{query}"</strong>. Try another source filter or search term.</>
        ) : (
          <>No content found matching <strong>"{query}"</strong>. Try a different search term.</>
        )}
      </p>
    </div>
  );
};
