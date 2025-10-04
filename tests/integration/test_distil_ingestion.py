#!/usr/bin/env python3
"""
Test the enhanced distil-large-v3 ingestion with 2-3 videos for POC
"""

import os
import sys
import logging
from dotenv import load_dotenv

load_dotenv()

# Add backend scripts to path
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'backend', 'scripts'))

def test_ingestion():
    """Test the enhanced ingestion with a few videos"""
    
    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Test video IDs (Dr. Chaffee solo content for initial testing)
    test_videos = [
        "48fTLPbE5JA",  # Solo Chaffee video (known good from memories)
        "RcBwvdVEAr8",  # Solo Chaffee video  
        "uG31-q5ivUI"   # Solo Chaffee video
    ]
    
    print("=" * 60)
    print("TESTING ENHANCED DISTIL-LARGE-V3 INGESTION")
    print("=" * 60)
    
    print(f"Test Videos: {test_videos}")
    print(f"Primary Model: distil-large-v3")
    print(f"Refinement Model: large-v3")
    print(f"Embedding Provider: {os.getenv('EMBEDDING_PROVIDER', 'openai')}")
    print(f"Database: {os.getenv('DATABASE_URL', 'Not configured')}")
    
    # Import and initialize the enhanced ingestion
    try:
        from ingest_youtube_enhanced_asr import EnhancedYouTubeIngestion
        
        # Initialize with test configuration
        ingestion = EnhancedYouTubeIngestion(
            enable_speaker_id=True,
            voices_dir='voices',
            chaffee_min_sim=0.62,
            source_type='youtube',
            workers=2  # Reduce for testing
        )
        
        print("\nIngestion system initialized successfully!")
        
        # Process test videos
        print(f"\nProcessing {len(test_videos)} test videos...")
        
        batch_results = ingestion.process_video_batch(
            video_ids=test_videos,
            force_enhanced_asr=True,  # Force Enhanced ASR for testing
            skip_existing=False       # Reprocess for testing
        )
        
        # Print results
        print("\n" + "=" * 60)
        print("TEST RESULTS")
        print("=" * 60)
        
        print(f"Total Videos: {batch_results['total_videos']}")
        print(f"Successful: {batch_results['successful']}")
        print(f"Failed: {batch_results['failed']}")
        print(f"Skipped: {batch_results['skipped']}")
        print(f"Total Chunks: {batch_results['summary']['total_chunks_processed']}")
        
        # Show individual results
        for video_id, result in batch_results['video_results'].items():
            status = "SUCCESS" if result['success'] else "FAILED"
            chunks = result.get('chunks_count', 0)
            method = result.get('method', 'unknown')
            processing_time = result.get('processing_time', 0)
            
            print(f"\n{video_id}: {status}")
            print(f"  Method: {method}")
            print(f"  Chunks: {chunks}")
            print(f"  Time: {processing_time:.1f}s")
            
            # Show speaker metadata if available
            if result.get('speaker_metadata'):
                speaker_meta = result['speaker_metadata']
                chaffee_pct = speaker_meta.get('chaffee_percentage', 0)
                print(f"  Chaffee: {chaffee_pct:.1f}%")
            
            # Show refinement stats if available
            if result.get('refinement_stats'):
                ref_stats = result['refinement_stats']
                refined = ref_stats.get('refined_segments', 0)
                total = ref_stats.get('total_segments', 0)
                if total > 0:
                    print(f"  Refined: {refined}/{total} ({refined/total*100:.1f}%)")
            
            if not result['success']:
                print(f"  Error: {result.get('error', 'Unknown')}")
        
        # Test database connection
        print(f"\nTesting database connection...")
        try:
            import psycopg2
            conn = psycopg2.connect(os.getenv('DATABASE_URL'))
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM segments")
                segment_count = cur.fetchone()[0]
                print(f"Total segments in database: {segment_count}")
                
                # Check for test videos
                cur.execute("SELECT DISTINCT video_id FROM segments WHERE video_id = ANY(%s)", (test_videos,))
                processed_videos = [row[0] for row in cur.fetchall()]
                print(f"Test videos in database: {processed_videos}")
            
            conn.close()
            
        except Exception as e:
            print(f"Database check failed: {e}")
        
        print("\n" + "=" * 60)
        print("TEST COMPLETED")
        print("=" * 60)
        
        return batch_results
        
    except Exception as e:
        print(f"Test failed: {e}")
        import traceback
        traceback.print_exc()
        return None

if __name__ == '__main__':
    test_ingestion()
