export interface SearchResult {
  id: string;
  text: string;
  start_time_seconds: number;
  end_time_seconds: number;
  similarity: number;
  url: string;
  source_type: string;
  title?: string;
  published_at?: string;
}

export interface VideoGroup {
  videoId: string;
  videoTitle: string;
  source_type: string;
  url?: string;
  clips: SearchResult[];
}
