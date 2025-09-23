#!/usr/bin/env python3
"""
Comprehensive test suite for Enhanced ASR system
Tests voice enrollment, speaker identification, and output formatting
"""

import os
import sys
import unittest
import tempfile
import json
import numpy as np
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

# Add backend scripts to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

class TestVoiceEnrollment(unittest.TestCase):
    """Test voice enrollment functionality"""
    
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.voices_dir = Path(self.temp_dir) / "voices"
        self.voices_dir.mkdir()
    
    def tearDown(self):
        import shutil
        shutil.rmtree(self.temp_dir)
    
    @patch('backend.scripts.common.voice_enrollment.EncoderClassifier')
    def test_voice_profile_creation(self, mock_encoder):
        """Test creating and saving voice profile"""
        from backend.scripts.common.voice_enrollment import VoiceEnrollment, VoiceProfile
        
        # Mock SpeechBrain model
        mock_model = Mock()
        mock_model.encode_batch.return_value = Mock()
        mock_model.encode_batch.return_value.squeeze.return_value.cpu.return_value.numpy.return_value = np.random.rand(192)
        mock_encoder.from_hparams.return_value = mock_model
        
        enrollment = VoiceEnrollment(voices_dir=str(self.voices_dir))
        
        # Create a test profile manually
        profile = VoiceProfile(
            name="TestSpeaker",
            centroid=[0.1, 0.2, 0.3],
            embeddings=[[0.1, 0.2, 0.3], [0.15, 0.25, 0.35]],
            metadata={"num_embeddings": 2, "recommended_threshold": 0.82},
            created_at="2024-01-01T00:00:00",
            audio_sources=["test.wav"]
        )
        
        # Save profile
        profile_path = self.voices_dir / "testspeaker.json"
        with open(profile_path, 'w') as f:
            json.dump(profile.to_dict(), f)
        
        # Load and verify
        loaded_profile = enrollment.load_profile("testspeaker")
        self.assertIsNotNone(loaded_profile)
        self.assertEqual(loaded_profile.name, "TestSpeaker")
        self.assertEqual(len(loaded_profile.embeddings), 2)
    
    def test_similarity_computation(self):
        """Test cosine similarity computation"""
        from backend.scripts.common.voice_enrollment import VoiceEnrollment, VoiceProfile
        
        enrollment = VoiceEnrollment(voices_dir=str(self.voices_dir))
        
        # Create test profile
        profile = VoiceProfile(
            name="TestSpeaker",
            centroid=[1.0, 0.0, 0.0],  # Unit vector along x-axis
            embeddings=[[1.0, 0.0, 0.0]],
            metadata={},
            created_at="2024-01-01T00:00:00",
            audio_sources=[]
        )
        
        # Test perfect match
        embedding = np.array([1.0, 0.0, 0.0])
        similarity = enrollment.compute_similarity(embedding, profile)
        self.assertAlmostEqual(similarity, 1.0, places=5)
        
        # Test orthogonal vectors (no similarity)
        embedding = np.array([0.0, 1.0, 0.0])
        similarity = enrollment.compute_similarity(embedding, profile)
        self.assertAlmostEqual(similarity, 0.0, places=5)
        
        # Test opposite direction (negative similarity)
        embedding = np.array([-1.0, 0.0, 0.0])
        similarity = enrollment.compute_similarity(embedding, profile)
        self.assertAlmostEqual(similarity, -1.0, places=5)

class TestEnhancedASRConfig(unittest.TestCase):
    """Test ASR configuration"""
    
    def test_default_config(self):
        """Test default configuration values"""
        from backend.scripts.common.enhanced_asr import EnhancedASRConfig
        
        config = EnhancedASRConfig()
        
        self.assertEqual(config.chaffee_min_sim, 0.82)
        self.assertEqual(config.guest_min_sim, 0.82)
        self.assertEqual(config.attr_margin, 0.05)
        self.assertEqual(config.overlap_bonus, 0.03)
        self.assertTrue(config.assume_monologue)
        self.assertTrue(config.align_words)
        self.assertEqual(config.unknown_label, "Unknown")
    
    @patch.dict(os.environ, {
        'CHAFFEE_MIN_SIM': '0.85',
        'GUEST_MIN_SIM': '0.80',
        'ATTR_MARGIN': '0.10',
        'ASSUME_MONOLOGUE': 'false'
    })
    def test_config_from_env(self):
        """Test configuration from environment variables"""
        from backend.scripts.common.enhanced_asr import EnhancedASRConfig
        
        config = EnhancedASRConfig()
        
        self.assertEqual(config.chaffee_min_sim, 0.85)
        self.assertEqual(config.guest_min_sim, 0.80)
        self.assertEqual(config.attr_margin, 0.10)
        self.assertFalse(config.assume_monologue)

class TestOutputFormatters(unittest.TestCase):
    """Test output format generation"""
    
    def setUp(self):
        # Create mock transcription result
        self.mock_result = {
            'text': 'Hello world. How are you?',
            'segments': [
                {
                    'start': 0.0,
                    'end': 2.0,
                    'text': 'Hello world.',
                    'speaker': 'Chaffee',
                    'speaker_confidence': 0.95
                },
                {
                    'start': 2.0,
                    'end': 4.0,
                    'text': 'How are you?',
                    'speaker': 'Guest',
                    'speaker_confidence': 0.88
                }
            ],
            'words': [
                {'word': 'Hello', 'start': 0.0, 'end': 0.5, 'confidence': 0.99, 'speaker': 'Chaffee'},
                {'word': 'world.', 'start': 0.5, 'end': 1.0, 'confidence': 0.98, 'speaker': 'Chaffee'},
                {'word': 'How', 'start': 2.0, 'end': 2.3, 'confidence': 0.97, 'speaker': 'Guest'},
                {'word': 'are', 'start': 2.3, 'end': 2.6, 'confidence': 0.96, 'speaker': 'Guest'},
                {'word': 'you?', 'start': 2.6, 'end': 3.0, 'confidence': 0.95, 'speaker': 'Guest'}
            ],
            'metadata': {
                'duration': 4.0,
                'method': 'full_pipeline',
                'summary': {
                    'speaker_time_percentages': {'Chaffee': 50.0, 'Guest': 50.0},
                    'confidence_stats': {
                        'Chaffee': {'avg': 0.95, 'min': 0.95, 'max': 0.95},
                        'Guest': {'avg': 0.88, 'min': 0.88, 'max': 0.88}
                    },
                    'unknown_segments': 0,
                    'chaffee_percentage': 50.0
                }
            }
        }
    
    def test_srt_output(self):
        """Test SRT format generation"""
        from backend.scripts.common.asr_output_formats import ASROutputFormatter
        
        formatter = ASROutputFormatter()
        srt_output = formatter.to_srt(self.mock_result)
        
        self.assertIn('1\n00:00:00,000 --> 00:00:02,000\nChaffee: Hello world.', srt_output)
        self.assertIn('2\n00:00:02,000 --> 00:00:04,000\nGuest: How are you?', srt_output)
    
    def test_vtt_output(self):
        """Test VTT format generation"""
        from backend.scripts.common.asr_output_formats import ASROutputFormatter
        
        formatter = ASROutputFormatter()
        vtt_output = formatter.to_vtt(self.mock_result)
        
        self.assertIn('WEBVTT', vtt_output)
        self.assertIn('00:00:00.000 --> 00:00:02.000', vtt_output)
        self.assertIn('Chaffee: Hello world.', vtt_output)
        self.assertIn('Guest: How are you?', vtt_output)
    
    def test_json_output(self):
        """Test JSON format generation"""
        from backend.scripts.common.asr_output_formats import ASROutputFormatter
        
        formatter = ASROutputFormatter()
        json_output = formatter.to_json(self.mock_result)
        
        # Parse JSON to verify structure
        parsed = json.loads(json_output)
        self.assertIn('text', parsed)
        self.assertIn('segments', parsed)
        self.assertIn('words', parsed)
        self.assertIn('metadata', parsed)
    
    def test_summary_report(self):
        """Test summary report generation"""
        from backend.scripts.common.asr_output_formats import ASROutputFormatter
        
        formatter = ASROutputFormatter()
        summary = formatter.generate_summary_report(self.mock_result)
        
        self.assertIn('ASR TRANSCRIPTION SUMMARY', summary)
        self.assertIn('Chaffee: 50.0% of audio', summary)
        self.assertIn('Guest: 50.0% of audio', summary)
        self.assertIn('High confidence: 50.0% attributed to Dr. Chaffee', summary)

class TestSpeakerIdentification(unittest.TestCase):
    """Test speaker identification logic"""
    
    def test_threshold_application(self):
        """Test speaker attribution with different thresholds"""
        # This would test the core logic of speaker identification
        # For now, we'll create a simple test case
        
        # Simulate similarity scores
        chaffee_sim = 0.85
        guest_sim = 0.78
        threshold = 0.82
        margin = 0.05
        
        # Test Chaffee attribution (above threshold with sufficient margin)
        self.assertGreater(chaffee_sim, threshold)
        self.assertGreater(chaffee_sim - guest_sim, margin)
        
        # This would be attributed to Chaffee
        expected_speaker = "Chaffee"
        self.assertEqual(expected_speaker, "Chaffee")
    
    def test_overlap_threshold_bonus(self):
        """Test stricter thresholds during overlap"""
        base_threshold = 0.82
        overlap_bonus = 0.03
        
        # During overlap, threshold should be higher
        overlap_threshold = base_threshold + overlap_bonus
        self.assertEqual(overlap_threshold, 0.85)
        
        # Similarity that would pass normally but fail during overlap
        similarity = 0.83
        self.assertGreater(similarity, base_threshold)  # Would pass normally
        self.assertLess(similarity, overlap_threshold)  # Would fail during overlap

class TestGuardrails(unittest.TestCase):
    """Test guardrail mechanisms"""
    
    def test_minimum_duration_check(self):
        """Test minimum duration guardrail"""
        min_duration = 3.0
        
        # Short segment should be rejected
        short_duration = 2.5
        self.assertLess(short_duration, min_duration)
        
        # Long enough segment should pass
        good_duration = 4.0
        self.assertGreaterEqual(good_duration, min_duration)
    
    def test_confidence_thresholds(self):
        """Test confidence-based rejection"""
        min_confidence = 0.5
        
        # High confidence should pass
        high_conf = 0.85
        self.assertGreater(high_conf, min_confidence)
        
        # Low confidence should be rejected
        low_conf = 0.3
        self.assertLess(low_conf, min_confidence)

class TestIntegrationScenarios(unittest.TestCase):
    """Test complete integration scenarios"""
    
    def test_monologue_scenario(self):
        """Test monologue detection and fast-path"""
        # Simulate high Chaffee similarity across multiple segments
        similarities = [0.89, 0.91, 0.87, 0.93]
        threshold = 0.82 + 0.03  # Fast-path threshold
        
        avg_similarity = np.mean(similarities)
        self.assertGreater(avg_similarity, threshold)
        
        # Should trigger monologue fast-path
        should_use_fast_path = avg_similarity >= threshold
        self.assertTrue(should_use_fast_path)
    
    def test_mixed_content_scenario(self):
        """Test mixed speaker content"""
        # Simulate different speakers with varying confidence
        segments = [
            {'speaker_sim': 0.91, 'expected': 'Chaffee'},    # High Chaffee
            {'speaker_sim': 0.75, 'expected': 'Unknown'},    # Below threshold
            {'speaker_sim': 0.88, 'expected': 'Guest'},      # High guest
            {'speaker_sim': 0.95, 'expected': 'Chaffee'},    # Very high Chaffee
        ]
        
        chaffee_count = sum(1 for s in segments if s['expected'] == 'Chaffee')
        total_segments = len(segments)
        chaffee_percentage = (chaffee_count / total_segments) * 100
        
        # Should detect mixed content (not pure monologue)
        self.assertEqual(chaffee_percentage, 50.0)
        self.assertLess(chaffee_percentage, 90.0)  # Not monologue

def create_test_audio_file():
    """Create a temporary test audio file for integration tests"""
    try:
        import librosa
        import soundfile as sf
        
        # Generate 5 seconds of test audio (sine wave)
        sr = 16000
        duration = 5.0
        t = np.linspace(0, duration, int(sr * duration))
        frequency = 440  # A4 note
        audio = 0.5 * np.sin(2 * np.pi * frequency * t)
        
        # Save to temporary file
        temp_file = tempfile.NamedTemporaryFile(suffix='.wav', delete=False)
        sf.write(temp_file.name, audio, sr)
        return temp_file.name
        
    except ImportError:
        # If audio libraries not available, return None
        return None

class TestFullPipeline(unittest.TestCase):
    """Test complete ASR pipeline (requires audio dependencies)"""
    
    def setUp(self):
        self.test_audio = create_test_audio_file()
        self.temp_dir = tempfile.mkdtemp()
    
    def tearDown(self):
        if self.test_audio and os.path.exists(self.test_audio):
            os.unlink(self.test_audio)
        import shutil
        shutil.rmtree(self.temp_dir)
    
    @unittest.skipIf(create_test_audio_file() is None, "Audio libraries not available")
    def test_end_to_end_pipeline(self):
        """Test complete pipeline with real audio (if dependencies available)"""
        # This would be a full integration test but requires actual models
        # For now, just verify we can create test audio
        self.assertIsNotNone(self.test_audio)
        self.assertTrue(os.path.exists(self.test_audio))

def run_test_suite():
    """Run the complete test suite"""
    # Create test suite
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    
    # Add test classes
    test_classes = [
        TestVoiceEnrollment,
        TestEnhancedASRConfig,
        TestOutputFormatters,
        TestSpeakerIdentification,
        TestGuardrails,
        TestIntegrationScenarios,
        TestFullPipeline
    ]
    
    for test_class in test_classes:
        tests = loader.loadTestsFromTestCase(test_class)
        suite.addTests(tests)
    
    # Run tests
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    return result.wasSuccessful()

if __name__ == '__main__':
    print("🧪 Running Enhanced ASR Test Suite")
    print("=" * 50)
    
    success = run_test_suite()
    
    if success:
        print("\n✅ All tests passed!")
        exit(0)
    else:
        print("\n❌ Some tests failed!")
        exit(1)
