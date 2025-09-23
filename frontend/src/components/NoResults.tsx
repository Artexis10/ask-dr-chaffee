import React from 'react';

interface NoResultsProps {
  sourceFilter: string;
  query: string;
}

export const NoResults: React.FC<NoResultsProps> = ({ sourceFilter, query }) => {
  return (
    <div className="no-results">
      <div className="no-results-icon">🔍</div>
      <h2>No results found</h2>
      <p>
        We couldn't find any matches for <strong>"{query}"</strong>
        {sourceFilter !== 'all' && <> in <span className="highlight">{sourceFilter}</span> content</>}.
      </p>
      
      <div className="search-tips">
        <h3>Search Tips:</h3>
        <ul>
          <li>Check your spelling</li>
          <li>Try more general keywords</li>
          <li>Try different keywords</li>
          {sourceFilter !== 'all' && <li>Remove the source filter</li>}
        </ul>
      </div>
      
      <style jsx>{`
        .search-tips {
          background: rgba(59, 130, 246, 0.05);
          border-radius: var(--radius-xl);
          padding: var(--space-4);
          text-align: left;
          max-width: 500px;
          margin: 0 auto;
        }
        
        .search-tips h3 {
          font-size: 1.1rem;
          margin-bottom: var(--space-3);
          color: var(--color-primary);
          font-weight: 600;
        }
        
        .search-tips ul {
          list-style-type: none;
          padding: 0;
          margin: 0;
        }
        
        .search-tips li {
          padding: var(--space-2) 0;
          position: relative;
          padding-left: var(--space-5);
          color: var(--color-text);
        }
        
        .search-tips li::before {
          content: '•';
          position: absolute;
          left: var(--space-2);
          color: var(--color-primary);
          font-weight: bold;
        }
        
        .highlight {
          background: rgba(139, 92, 246, 0.15);
          color: var(--color-accent-dark);
          padding: 0.1em 0.3em;
          border-radius: var(--radius-sm);
          font-weight: 500;
        }
      `}</style>
    </div>
  );
};
