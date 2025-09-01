import React from 'react';
import { VideoGroup } from '../types';
import { VideoCard } from './VideoCard';
import { NoResults } from './NoResults';

interface SearchResultsProps {
  results: any[];
  query: string;
  loading: boolean;
  totalResults: number;
  groupedResults: VideoGroup[];
  sourceFilter: string;
  highlightSearchTerms: (text: string, query: string) => string;
  seekToTimestamp: (videoId: string, seconds: number) => void;
  copyTimestampLink: (url: string) => void;
}

export const SearchResults: React.FC<SearchResultsProps> = ({
  results,
  query,
  loading,
  totalResults,
  groupedResults,
  sourceFilter,
  highlightSearchTerms,
  seekToTimestamp,
  copyTimestampLink
}) => {
  console.log('SearchResults render:', { 
    resultsLength: results.length, 
    totalResults, 
    groupedResultsLength: groupedResults.length, 
    query, 
    loading 
  });

  if (loading) return null;
  if (!query.trim()) return null;
  
  if (results.length === 0) {
    console.log('Showing NoResults because results.length === 0');
    return <NoResults sourceFilter={sourceFilter} query={query} />;
  }

  return (
    <div className="results" role="main">
      <h2 aria-live="polite">
        🎯 Found {totalResults} relevant clip{totalResults !== 1 ? 's' : ''} in {groupedResults.length} video{groupedResults.length !== 1 ? 's' : ''}
      </h2>
      {groupedResults.map((group) => (
        <VideoCard
          key={group.videoId}
          group={group}
          query={query}
          highlightSearchTerms={highlightSearchTerms}
          seekToTimestamp={seekToTimestamp}
          copyTimestampLink={copyTimestampLink}
        />
      ))}
    </div>
  );
};
