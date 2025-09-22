#!/usr/bin/env python3
"""
Simple transcript API testing to verify functionality and limits
"""

import os
import sys
import time
import json
from datetime import datetime
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api._errors import TranscriptsDisabled, NoTranscriptFound, VideoUnavailable

def test_video(video_id, description=""):
    """Test transcript fetching for a single video"""
    print(f"\nTesting {description} ({video_id})")
    print("-" * 50)
    
    start_time = time.time()
    try:
        api = YouTubeTranscriptApi()
        transcript_list = api.list(video_id)
        
        # List available languages
        available_languages = []
        for transcript in transcript_list:
            lang = transcript.language
            is_auto = transcript.is_generated
            available_languages.append(f"{lang} ({'auto' if is_auto else 'manual'})")
        
        print(f"Available languages: {', '.join(available_languages)}")
        
        # Try to get English transcript
        transcript = transcript_list.find_transcript(['en'])
        data = transcript.fetch()
        
        duration = time.time() - start_time
        
        # Safely extract text without encoding issues
        total_text = ""
        valid_segments = 0
        for segment in data:
            try:
                text = segment.text.encode('ascii', 'ignore').decode('ascii')
                if text.strip():
                    total_text += text + " "
                    valid_segments += 1
            except:
                valid_segments += 1  # Count it but skip the text
        
        print(f"SUCCESS: {len(data)} segments, {valid_segments} valid, {duration:.2f}s")
        print(f"Total text length: {len(total_text)} characters")
        if total_text:
            print(f"Sample: {total_text[:100]}...")
        
        return {
            'success': True,
            'segments': len(data),
            'duration': duration,
            'languages': available_languages,
            'text_length': len(total_text)
        }
        
    except (TranscriptsDisabled, NoTranscriptFound, VideoUnavailable) as e:
        duration = time.time() - start_time
        print(f"NO TRANSCRIPT: {str(e)} ({duration:.2f}s)")
        return {
            'success': False,
            'error': str(e),
            'duration': duration
        }
    except Exception as e:
        duration = time.time() - start_time
        print(f"ERROR: {str(e)} ({duration:.2f}s)")
        return {
            'success': False,
            'error': str(e),
            'duration': duration
        }

def test_rate_limits():
    """Test rate limits with rapid requests"""
    print("\n" + "="*60)
    print("RATE LIMIT TESTING")
    print("="*60)
    
    # Use a popular video for rate limit testing
    test_video_id = "dQw4w9WgXcQ"  # Rick Roll
    
    print("Making 10 rapid requests to test rate limiting...")
    results = []
    
    for i in range(10):
        start_time = time.time()
        try:
            api = YouTubeTranscriptApi()
            transcript_list = api.list(test_video_id)
            transcript = transcript_list.find_transcript(['en'])
            data = transcript.fetch()
            duration = time.time() - start_time
            
            result = {
                'request': i + 1,
                'success': True,
                'duration': duration,
                'segments': len(data)
            }
            results.append(result)
            print(f"Request {i+1}: SUCCESS ({duration:.2f}s, {len(data)} segments)")
            
        except Exception as e:
            duration = time.time() - start_time
            result = {
                'request': i + 1,
                'success': False,
                'duration': duration,
                'error': str(e)
            }
            results.append(result)
            print(f"Request {i+1}: ERROR ({duration:.2f}s) - {str(e)}")
        
        # No delay - test for rate limiting
    
    # Analyze results
    successful_requests = sum(1 for r in results if r['success'])
    failed_requests = len(results) - successful_requests
    avg_duration = sum(r['duration'] for r in results) / len(results)
    
    print(f"\nRate Limit Test Results:")
    print(f"  Successful: {successful_requests}/{len(results)}")
    print(f"  Failed: {failed_requests}/{len(results)}")
    print(f"  Average duration: {avg_duration:.2f}s")
    
    return results

def main():
    """Main testing function"""
    print("YOUTUBE TRANSCRIPT API TESTING")
    print("="*60)
    print(f"Test started at: {datetime.now()}")
    
    # Test videos with different characteristics
    test_videos = [
        ("dQw4w9WgXcQ", "Rick Astley - Popular music video"),
        ("TxbE79-1OSI", "TED Talk - Educational content"),
        ("Ks-_Mh1QhMc", "Popular video with auto-captions"),
        ("rz6Zb6gl4bE", "Dr. Chaffee - Target channel"),
        ("9bZkp7q19f0", "PSY - Gangnam Style"),
        ("invalid123", "Invalid video ID - should fail")
    ]
    
    results = {}
    
    # Test individual videos
    for video_id, description in test_videos:
        result = test_video(video_id, description)
        results[video_id] = result
        
        # Small delay between requests
        time.sleep(1)
    
    # Test rate limits
    rate_limit_results = test_rate_limits()
    results['rate_limit_test'] = rate_limit_results
    
    # Summary
    print("\n" + "="*60)
    print("TEST SUMMARY")
    print("="*60)
    
    successful_videos = sum(1 for v in results.values() if isinstance(v, dict) and v.get('success'))
    total_videos = len([v for v in results.values() if isinstance(v, dict) and 'success' in v])
    
    print(f"Video Tests: {successful_videos}/{total_videos} successful")
    
    # Find fastest and slowest responses
    video_results = [v for v in results.values() if isinstance(v, dict) and 'duration' in v]
    if video_results:
        fastest = min(video_results, key=lambda x: x['duration'])
        slowest = max(video_results, key=lambda x: x['duration'])
        avg_duration = sum(v['duration'] for v in video_results) / len(video_results)
        
        print(f"Response times: {fastest['duration']:.2f}s (fastest) - {slowest['duration']:.2f}s (slowest)")
        print(f"Average response time: {avg_duration:.2f}s")
    
    # Rate limit analysis
    if 'rate_limit_test' in results:
        rate_results = results['rate_limit_test']
        rate_success = sum(1 for r in rate_results if r['success'])
        print(f"Rate limit test: {rate_success}/{len(rate_results)} requests successful")
        
        if rate_success < len(rate_results):
            print("⚠️  Rate limiting detected - some requests failed")
        else:
            print("✅ No rate limiting detected in rapid requests")
    
    # Save detailed results
    output_file = f"transcript_test_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(output_file, 'w') as f:
        json.dump({
            'timestamp': datetime.now().isoformat(),
            'results': results,
            'summary': {
                'successful_videos': successful_videos,
                'total_videos': total_videos,
                'success_rate': (successful_videos / total_videos * 100) if total_videos > 0 else 0
            }
        }, f, indent=2)
    
    print(f"Detailed results saved to: {output_file}")
    
    # Recommendations
    print("\n" + "="*60)
    print("RECOMMENDATIONS FOR MVP")
    print("="*60)
    
    if successful_videos / total_videos >= 0.8:
        print("✅ YouTube Transcript API is working well")
        print("   - Good success rate for transcript fetching")
        print("   - Suitable for MVP with proper error handling")
    else:
        print("⚠️  YouTube Transcript API has limitations")
        print("   - Consider implementing fallback mechanisms")
        print("   - May need Whisper transcription for some videos")
    
    print("\nKey Points for MVP:")
    print("- Implement retry logic for failed requests")
    print("- Add delay between requests to avoid rate limiting")
    print("- Have fallback transcription method (Whisper)")
    print("- Monitor for IP blocking in production")

if __name__ == "__main__":
    main()
