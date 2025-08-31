import React from 'react';
import { VideoGroup, SearchResult } from '../types';

interface VideoCardProps {
  group: VideoGroup;
  query: string;
  highlightSearchTerms: (text: string, query: string) => string;
  seekToTimestamp: (videoId: string, seconds: number) => void;
  copyTimestampLink: (url: string) => void;
}

export const VideoCard: React.FC<VideoCardProps> = ({ 
  group, 
  query, 
  highlightSearchTerms, 
  seekToTimestamp, 
  copyTimestampLink 
}) => {
  return (
    <div key={group.videoId} className="video-card">
      <div className="video-header">
        <h3>🎥 {group.videoTitle}</h3>
        <span className="source-type">{group.source_type === 'youtube' ? '📺 YouTube' : '💼 Zoom'}</span>
      </div>
      
      {group.source_type === 'youtube' && group.videoId && (
        <div className="video-embed">
          <iframe
            width="100%"
            height="315"
            src={`https://www.youtube.com/embed/${group.videoId}?enablejsapi=1&origin=${typeof window !== 'undefined' ? window.location.origin : ''}`}
            title={group.videoTitle}
            frameBorder="0"
            allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
            allowFullScreen
          ></iframe>
        </div>
      )}
    
      <div className="clips-container">
        <h4>📄 {group.clips.length} relevant clip{group.clips.length !== 1 ? 's' : ''} found:</h4>
        {group.clips.map((clip: SearchResult) => (
          <div key={clip.id} className="clip-card">
            <div className="clip-content">
              <p 
                className="transcript-text"
                dangerouslySetInnerHTML={{
                  __html: highlightSearchTerms(clip.text, query)
                }}
              ></p>
            </div>
            <div className="clip-footer">
              <span className="timestamp">
                🕒 {formatTime(clip.start_time_seconds)} - {formatTime(clip.end_time_seconds)}
              </span>
              <span className="similarity">
                📊 {clip.similarity}% relevant
              </span>
              <div className="clip-actions">
                {group.source_type === 'youtube' && (
                  <button 
                    onClick={() => seekToTimestamp(group.videoId, Math.floor(clip.start_time_seconds))}
                    className="seek-button"
                    title="Jump to this moment in embedded video"
                    aria-label={`Play video at ${formatTime(clip.start_time_seconds)}`}
                  >
                    🎯 Play Here
                  </button>
                )}
                <button
                  onClick={() => copyTimestampLink(clip.url)}
                  className="copy-button"
                  title="Copy timestamp link"
                  aria-label="Copy link to clipboard"
                >
                  📋 Copy Link
                </button>
                <a 
                  href={clip.url} 
                  target="_blank" 
                  rel="noopener noreferrer" 
                  className="watch-link"
                  onClick={() => {
                    if (typeof window !== 'undefined') {
                      window.dispatchEvent(new CustomEvent('analytics', {
                        detail: { event: 'result_clicked_youtube', url: clip.url }
                      }));
                    }
                  }}
                >
                  ▶️ Open in YouTube
                </a>
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};

// Helper function to format time in MM:SS format
function formatTime(seconds: number): string {
  const mins = Math.floor(seconds / 60);
  const secs = Math.floor(seconds % 60);
  return `${mins}:${secs.toString().padStart(2, '0')}`;
}
