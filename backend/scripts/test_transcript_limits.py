#!/usr/bin/env python3
"""
Comprehensive testing script for transcript APIs to validate functionality and limits
"""

import os
import sys
import time
import json
import logging
import argparse
import concurrent.futures
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, Tuple
from pathlib import Path
from dotenv import load_dotenv

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.common.transcript_fetch import TranscriptFetcher, YOUTUBE_DATA_API_AVAILABLE, WHISPER_AVAILABLE
from scripts.common.transcript_api import YouTubeTranscriptAPI
from scripts.common.transcript_common import TranscriptSegment
# from scripts.common.database_upsert import DatabaseManager  # Not needed for this test

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class TranscriptAPITester:
    """Comprehensive testing for transcript APIs"""
    
    # Test video IDs for different scenarios
    TEST_VIDEOS = {
        'dr_chaffee': 'rz6Zb6gl4bE',  # Dr. Chaffee video with captions
        'short_video': 'dQw4w9WgXcQ',  # Rick Roll - short, popular video
        'long_video': 'JGwWNGJdvx8',  # Longer educational content
        'auto_captions': 'Ks-_Mh1QhMc',  # Video with auto-generated captions only
        'no_captions': 'MtN1YnoL46Q',  # Video likely without captions
        'ted_talk': 'TxbE79-1OSI',    # TED talk with high-quality captions
    }
    
    def __init__(self, api_key: str = None, credentials_path: str = None):
        self.api_key = api_key or os.getenv('YOUTUBE_API_KEY')
        self.credentials_path = credentials_path or os.getenv('YOUTUBE_CREDENTIALS_PATH')
        self.results = {}
        
        # Initialize transcript fetcher
        self.fetcher = TranscriptFetcher(
            api_key=self.api_key,
            credentials_path=self.credentials_path
        )
        
        logger.info("Initialized TranscriptAPITester")
        logger.info(f"YouTube Data API available: {YOUTUBE_DATA_API_AVAILABLE}")
        logger.info(f"Whisper available: {WHISPER_AVAILABLE}")
        logger.info(f"API key provided: {bool(self.api_key)}")
        logger.info(f"Credentials path provided: {bool(self.credentials_path)}")
    
    def test_youtube_transcript_api(self) -> Dict[str, Any]:
        """Test YouTube Transcript API with various videos"""
        logger.info("Testing YouTube Transcript API...")
        results = {
            'method': 'youtube_transcript_api',
            'tests': {},
            'summary': {
                'total_tests': 0,
                'successful': 0,
                'failed': 0,
                'errors': []
            }
        }
        
        for video_name, video_id in self.TEST_VIDEOS.items():
            logger.info(f"Testing {video_name} ({video_id})")
            test_start = time.time()
            
            try:
                segments = self.fetcher.fetch_youtube_transcript(video_id)
                test_duration = time.time() - test_start
                
                if segments:
                    results['tests'][video_name] = {
                        'video_id': video_id,
                        'success': True,
                        'segments_count': len(segments),
                        'duration_seconds': test_duration,
                        'first_segment': segments[0].to_dict() if segments else None,
                        'last_segment': segments[-1].to_dict() if len(segments) > 1 else None,
                        'total_text_length': sum(len(seg.text) for seg in segments)
                    }
                    results['summary']['successful'] += 1
                    logger.info(f"✓ {video_name}: {len(segments)} segments in {test_duration:.2f}s")
                else:
                    results['tests'][video_name] = {
                        'video_id': video_id,
                        'success': False,
                        'error': 'No segments returned',
                        'duration_seconds': test_duration
                    }
                    results['summary']['failed'] += 1
                    logger.warning(f"✗ {video_name}: No transcript found")
                    
            except Exception as e:
                test_duration = time.time() - test_start
                results['tests'][video_name] = {
                    'video_id': video_id,
                    'success': False,
                    'error': str(e),
                    'duration_seconds': test_duration
                }
                results['summary']['failed'] += 1
                results['summary']['errors'].append(f"{video_name}: {str(e)}")
                logger.error(f"✗ {video_name}: {str(e)}")
            
            results['summary']['total_tests'] += 1
            
            # Small delay to avoid rate limiting
            time.sleep(1)
        
        return results
    
    def test_youtube_data_api(self) -> Dict[str, Any]:
        """Test YouTube Data API for transcript fetching"""
        logger.info("Testing YouTube Data API...")
        results = {
            'method': 'youtube_data_api',
            'available': YOUTUBE_DATA_API_AVAILABLE,
            'tests': {},
            'summary': {
                'total_tests': 0,
                'successful': 0,
                'failed': 0,
                'errors': []
            }
        }
        
        if not YOUTUBE_DATA_API_AVAILABLE:
            results['error'] = 'YouTube Data API not available'
            logger.warning("YouTube Data API not available - skipping tests")
            return results
        
        if not self.credentials_path and not self.api_key:
            results['error'] = 'No API credentials provided'
            logger.warning("No YouTube Data API credentials provided - skipping tests")
            return results
        
        try:
            # Initialize API client
            api_client = YouTubeTranscriptAPI(
                credentials_path=self.credentials_path,
                api_key=self.api_key
            )
            
            # Test a subset of videos (Data API has quota limits)
            test_videos = {
                'dr_chaffee': self.TEST_VIDEOS['dr_chaffee'],
                'short_video': self.TEST_VIDEOS['short_video']
            }
            
            for video_name, video_id in test_videos.items():
                logger.info(f"Testing Data API with {video_name} ({video_id})")
                test_start = time.time()
                
                try:
                    # List captions first
                    captions = api_client.list_captions(video_id)
                    
                    # Get transcript segments
                    segments = api_client.get_transcript_segments(video_id)
                    test_duration = time.time() - test_start
                    
                    results['tests'][video_name] = {
                        'video_id': video_id,
                        'success': True,
                        'captions_available': len(captions),
                        'segments_count': len(segments) if segments else 0,
                        'duration_seconds': test_duration,
                        'captions_info': [
                            {
                                'language': cap['snippet']['language'],
                                'auto_generated': cap['snippet'].get('trackKind') == 'ASR'
                            }
                            for cap in captions
                        ]
                    }
                    
                    if segments:
                        results['tests'][video_name].update({
                            'first_segment': segments[0].to_dict(),
                            'total_text_length': sum(len(seg.text) for seg in segments)
                        })
                        results['summary']['successful'] += 1
                        logger.info(f"✓ Data API {video_name}: {len(segments)} segments, {len(captions)} caption tracks")
                    else:
                        results['summary']['failed'] += 1
                        logger.warning(f"✗ Data API {video_name}: No segments returned")
                
                except Exception as e:
                    test_duration = time.time() - test_start
                    results['tests'][video_name] = {
                        'video_id': video_id,
                        'success': False,
                        'error': str(e),
                        'duration_seconds': test_duration
                    }
                    results['summary']['failed'] += 1
                    results['summary']['errors'].append(f"Data API {video_name}: {str(e)}")
                    logger.error(f"✗ Data API {video_name}: {str(e)}")
                
                results['summary']['total_tests'] += 1
                
                # Longer delay for Data API to respect quotas
                time.sleep(2)
                
        except Exception as e:
            results['error'] = f"Failed to initialize Data API client: {str(e)}"
            logger.error(f"Failed to initialize Data API client: {str(e)}")
        
        return results
    
    def test_whisper_transcription(self) -> Dict[str, Any]:
        """Test Whisper transcription"""
        logger.info("Testing Whisper transcription...")
        results = {
            'method': 'whisper_transcription',
            'available': WHISPER_AVAILABLE,
            'tests': {},
            'summary': {
                'total_tests': 0,
                'successful': 0,
                'failed': 0,
                'errors': []
            }
        }
        
        if not WHISPER_AVAILABLE:
            results['error'] = 'Whisper not available'
            logger.warning("Whisper not available - skipping tests")
            return results
        
        # Test with one short video to avoid long processing times
        test_video = {'short_test': self.TEST_VIDEOS['short_video']}
        
        for video_name, video_id in test_video.items():
            logger.info(f"Testing Whisper with {video_name} ({video_id}) - this may take a while...")
            test_start = time.time()
            
            try:
                segments, method, metadata = self.fetcher.fetch_transcript(
                    video_id,
                    force_whisper=True,
                    max_duration_s=300  # 5 minute limit for testing
                )
                test_duration = time.time() - test_start
                
                if segments:
                    results['tests'][video_name] = {
                        'video_id': video_id,
                        'success': True,
                        'method': method,
                        'segments_count': len(segments),
                        'duration_seconds': test_duration,
                        'metadata': metadata,
                        'first_segment': segments[0].to_dict() if segments else None,
                        'total_text_length': sum(len(seg.text) for seg in segments)
                    }
                    results['summary']['successful'] += 1
                    logger.info(f"✓ Whisper {video_name}: {len(segments)} segments in {test_duration:.2f}s using {method}")
                else:
                    results['tests'][video_name] = {
                        'video_id': video_id,
                        'success': False,
                        'method': method,
                        'error': 'No segments returned',
                        'duration_seconds': test_duration,
                        'metadata': metadata
                    }
                    results['summary']['failed'] += 1
                    logger.warning(f"✗ Whisper {video_name}: No transcript generated")
            
            except Exception as e:
                test_duration = time.time() - test_start
                results['tests'][video_name] = {
                    'video_id': video_id,
                    'success': False,
                    'error': str(e),
                    'duration_seconds': test_duration
                }
                results['summary']['failed'] += 1
                results['summary']['errors'].append(f"Whisper {video_name}: {str(e)}")
                logger.error(f"✗ Whisper {video_name}: {str(e)}")
            
            results['summary']['total_tests'] += 1
        
        return results
    
    def test_rate_limits(self) -> Dict[str, Any]:
        """Test rate limits and concurrent requests"""
        logger.info("Testing rate limits and concurrent requests...")
        results = {
            'method': 'rate_limit_test',
            'sequential_test': {},
            'concurrent_test': {},
            'summary': {}
        }
        
        # Sequential test - make rapid requests
        logger.info("Testing sequential requests...")
        test_video = self.TEST_VIDEOS['dr_chaffee']
        request_times = []
        
        for i in range(5):
            start_time = time.time()
            try:
                segments = self.fetcher.fetch_youtube_transcript(test_video)
                duration = time.time() - start_time
                request_times.append(duration)
                logger.info(f"Request {i+1}: {duration:.2f}s, {len(segments) if segments else 0} segments")
                # No delay to test rate limits
            except Exception as e:
                duration = time.time() - start_time
                request_times.append(duration)
                logger.error(f"Request {i+1}: Failed after {duration:.2f}s - {str(e)}")
        
        results['sequential_test'] = {
            'requests_made': len(request_times),
            'avg_duration': sum(request_times) / len(request_times) if request_times else 0,
            'min_duration': min(request_times) if request_times else 0,
            'max_duration': max(request_times) if request_times else 0,
            'request_times': request_times
        }
        
        # Concurrent test - make parallel requests
        logger.info("Testing concurrent requests...")
        def fetch_transcript_concurrent(video_id):
            start_time = time.time()
            try:
                segments = self.fetcher.fetch_youtube_transcript(video_id)
                return {
                    'success': True,
                    'duration': time.time() - start_time,
                    'segments_count': len(segments) if segments else 0
                }
            except Exception as e:
                return {
                    'success': False,
                    'duration': time.time() - start_time,
                    'error': str(e)
                }
        
        concurrent_start = time.time()
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
            # Test with 3 different videos concurrently
            test_videos = [
                self.TEST_VIDEOS['dr_chaffee'],
                self.TEST_VIDEOS['short_video'],
                self.TEST_VIDEOS['ted_talk']
            ]
            
            futures = {
                executor.submit(fetch_transcript_concurrent, video_id): video_id 
                for video_id in test_videos
            }
            
            concurrent_results = {}
            for future in concurrent.futures.as_completed(futures):
                video_id = futures[future]
                result = future.result()
                concurrent_results[video_id] = result
        
        concurrent_duration = time.time() - concurrent_start
        
        results['concurrent_test'] = {
            'total_duration': concurrent_duration,
            'results': concurrent_results,
            'successful_requests': sum(1 for r in concurrent_results.values() if r['success']),
            'failed_requests': sum(1 for r in concurrent_results.values() if not r['success'])
        }
        
        return results
    
    def generate_report(self, save_path: str = None) -> str:
        """Generate comprehensive test report"""
        report = {
            'test_timestamp': datetime.now().isoformat(),
            'environment': {
                'youtube_data_api_available': YOUTUBE_DATA_API_AVAILABLE,
                'whisper_available': WHISPER_AVAILABLE,
                'api_key_provided': bool(self.api_key),
                'credentials_path_provided': bool(self.credentials_path)
            },
            'results': self.results
        }
        
        # Calculate overall statistics
        total_tests = 0
        total_successful = 0
        total_failed = 0
        
        for test_name, test_results in self.results.items():
            if 'summary' in test_results:
                total_tests += test_results['summary'].get('total_tests', 0)
                total_successful += test_results['summary'].get('successful', 0)
                total_failed += test_results['summary'].get('failed', 0)
        
        report['overall_summary'] = {
            'total_tests': total_tests,
            'successful_tests': total_successful,
            'failed_tests': total_failed,
            'success_rate': (total_successful / total_tests * 100) if total_tests > 0 else 0
        }
        
        # Save report if path provided
        if save_path:
            with open(save_path, 'w') as f:
                json.dump(report, f, indent=2)
            logger.info(f"Report saved to: {save_path}")
        
        return json.dumps(report, indent=2)
    
    def run_all_tests(self) -> Dict[str, Any]:
        """Run all transcript API tests"""
        logger.info("Starting comprehensive transcript API testing...")
        
        # Test 1: YouTube Transcript API
        self.results['youtube_transcript_api'] = self.test_youtube_transcript_api()
        
        # Test 2: YouTube Data API
        self.results['youtube_data_api'] = self.test_youtube_data_api()
        
        # Test 3: Whisper transcription (if available)
        if WHISPER_AVAILABLE:
            self.results['whisper_transcription'] = self.test_whisper_transcription()
        
        # Test 4: Rate limits
        self.results['rate_limits'] = self.test_rate_limits()
        
        return self.results

def main():
    """Main CLI interface"""
    parser = argparse.ArgumentParser(description='Test transcript API limits and functionality')
    parser.add_argument('--api-key', help='YouTube Data API key')
    parser.add_argument('--credentials-path', help='Path to YouTube API credentials file')
    parser.add_argument('--output', '-o', help='Output file for test report')
    parser.add_argument('--test', choices=['all', 'youtube', 'data-api', 'whisper', 'rate-limits'], 
                       default='all', help='Which tests to run')
    parser.add_argument('--verbose', '-v', action='store_true', help='Verbose logging')
    
    args = parser.parse_args()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    # Initialize tester
    tester = TranscriptAPITester(
        api_key=args.api_key,
        credentials_path=args.credentials_path
    )
    
    # Run selected tests
    if args.test == 'all':
        results = tester.run_all_tests()
    elif args.test == 'youtube':
        tester.results['youtube_transcript_api'] = tester.test_youtube_transcript_api()
    elif args.test == 'data-api':
        tester.results['youtube_data_api'] = tester.test_youtube_data_api()
    elif args.test == 'whisper':
        tester.results['whisper_transcription'] = tester.test_whisper_transcription()
    elif args.test == 'rate-limits':
        tester.results['rate_limits'] = tester.test_rate_limits()
    
    # Generate and display report
    output_path = args.output or f"transcript_test_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    report_json = tester.generate_report(output_path)
    
    # Print summary
    print("\n" + "="*80)
    print("TRANSCRIPT API TEST SUMMARY")
    print("="*80)
    
    if 'youtube_transcript_api' in tester.results:
        yt_results = tester.results['youtube_transcript_api']['summary']
        print(f"YouTube Transcript API: {yt_results['successful']}/{yt_results['total_tests']} successful")
    
    if 'youtube_data_api' in tester.results:
        data_results = tester.results['youtube_data_api']['summary']
        print(f"YouTube Data API: {data_results['successful']}/{data_results['total_tests']} successful")
    
    if 'whisper_transcription' in tester.results:
        whisper_results = tester.results['whisper_transcription']['summary']
        print(f"Whisper Transcription: {whisper_results['successful']}/{whisper_results['total_tests']} successful")
    
    # Show critical issues
    all_errors = []
    for test_name, test_results in tester.results.items():
        if 'summary' in test_results and 'errors' in test_results['summary']:
            all_errors.extend(test_results['summary']['errors'])
    
    if all_errors:
        print(f"\nCritical Issues Found:")
        for error in all_errors:
            print(f"  - {error}")
    else:
        print("\n✓ No critical issues found!")
    
    print(f"\nDetailed report saved to: {output_path}")
    print("="*80)

if __name__ == '__main__':
    main()
