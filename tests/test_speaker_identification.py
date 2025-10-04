#!/usr/bin/env python3
"""
Unit tests for speaker identification
"""
import os
import sys
import unittest
from pathlib import Path
import numpy as np
import logging
from unittest.mock import patch, MagicMock

# Configure logging
logging.basicConfig(level=logging.INFO)

# Add backend to path
sys.path.append(os.path.join(os.path.dirname(os.path.dirname(__file__)), 'backend'))

# Import modules to test
from backend.scripts.common.voice_enrollment_optimized import VoiceEnrollment
from backend.scripts.common.enhanced_asr import EnhancedASR
from backend.scripts.common.enhanced_asr_config import EnhancedASRConfig

class TestSpeakerIdentification(unittest.TestCase):
    """Test speaker identification functionality"""
    
    def setUp(self):
        """Set up test environment"""
        # Create test directories
        self.test_dir = Path("test_data")
        self.test_dir.mkdir(exist_ok=True)
        
        self.voices_dir = self.test_dir / "voices"
        self.voices_dir.mkdir(exist_ok=True)
        
        # Create mock voice enrollment
        self.voice_enrollment = VoiceEnrollment(voices_dir=str(self.voices_dir))
        
        # Create mock ASR config
        self.asr_config = EnhancedASRConfig(
            overrides={
                'chaffee_min_sim': '0.62',
                'guest_min_sim': '0.82',
                'attr_margin': '0.05',
                'assume_monologue': 'true'
            }
        )
        
    def tearDown(self):
        """Clean up after tests"""
        # Remove test files
        import shutil
        if self.test_dir.exists():
            shutil.rmtree(self.test_dir)
    
    def test_compute_similarity_with_profile(self):
        """Test computing similarity between embedding and profile"""
        # Create mock profile
        mock_profile = {
            'embeddings': [
                np.ones(192, dtype=np.float64),  # All ones
                np.zeros(192, dtype=np.float64)  # All zeros
            ]
        }
        
        # Create test embeddings
        test_emb_ones = np.ones(192, dtype=np.float64)  # Should match first profile embedding
        test_emb_zeros = np.zeros(192, dtype=np.float64)  # Should match second profile embedding
        test_emb_mixed = np.array([0.5] * 192, dtype=np.float64)  # Should be in between
        
        # Test similarity calculations
        sim_ones = self.voice_enrollment.compute_similarity(test_emb_ones, mock_profile)
        sim_zeros = self.voice_enrollment.compute_similarity(test_emb_zeros, mock_profile)
        sim_mixed = self.voice_enrollment.compute_similarity(test_emb_mixed, mock_profile)
        
        # Assertions
        self.assertAlmostEqual(sim_ones, 1.0, places=5)
        self.assertAlmostEqual(sim_zeros, 1.0, places=5)
        self.assertGreater(sim_mixed, 0.5)
        
    def test_speaker_identification_chaffee(self):
        """Test identifying Dr. Chaffee's voice"""
        # Create mock EnhancedASR with patched methods
        with patch('backend.scripts.common.enhanced_asr.EnhancedASR._get_voice_enrollment') as mock_get_enrollment:
            # Set up mock voice enrollment
            mock_enrollment = MagicMock()
            mock_get_enrollment.return_value = mock_enrollment
            
            # Create mock profile
            mock_profile = {'embeddings': [np.ones(192, dtype=np.float64)]}
            mock_enrollment.load_profile.return_value = mock_profile
            
            # Set up mock embeddings extraction
            mock_embeddings = [np.ones(192, dtype=np.float64)]  # Similar to Chaffee profile
            mock_enrollment._extract_embeddings_from_audio.return_value = mock_embeddings
            
            # Set up mock similarity calculation
            mock_enrollment.compute_similarity.return_value = 0.9  # High similarity
            
            # Create EnhancedASR instance
            asr = EnhancedASR(self.asr_config)
            
            # Test monologue fast-path
            result = asr._check_monologue_fast_path("dummy_audio.wav")
            
            # Verify that voice enrollment methods were called
            mock_enrollment.load_profile.assert_called_with("chaffee")
            mock_enrollment._extract_embeddings_from_audio.assert_called_once()
            
            # Verify that similarity was computed
            self.assertTrue(mock_enrollment.compute_similarity.called)
            
            # Verify that result is not None (fast-path was triggered)
            self.assertIsNotNone(result)
            
            # Check that segments are labeled as Chaffee
            if result and hasattr(result, 'segments') and result.segments:
                for segment in result.segments:
                    self.assertEqual(segment.get('speaker', ''), 'Chaffee')
    
    def test_speaker_identification_guest(self):
        """Test identifying guest voice"""
        # Create mock EnhancedASR with patched methods
        with patch('backend.scripts.common.enhanced_asr.EnhancedASR._get_voice_enrollment') as mock_get_enrollment:
            # Set up mock voice enrollment
            mock_enrollment = MagicMock()
            mock_get_enrollment.return_value = mock_enrollment
            
            # Create mock profile
            mock_profile = {'embeddings': [np.ones(192, dtype=np.float64)]}
            mock_enrollment.load_profile.return_value = mock_profile
            
            # Set up mock embeddings extraction
            mock_embeddings = [np.zeros(192, dtype=np.float64)]  # Different from Chaffee profile
            mock_enrollment._extract_embeddings_from_audio.return_value = mock_embeddings
            
            # Set up mock similarity calculation
            mock_enrollment.compute_similarity.return_value = 0.3  # Low similarity
            
            # Create EnhancedASR instance
            asr = EnhancedASR(self.asr_config)
            
            # Test monologue fast-path
            result = asr._check_monologue_fast_path("dummy_audio.wav")
            
            # Verify that voice enrollment methods were called
            mock_enrollment.load_profile.assert_called_with("chaffee")
            mock_enrollment._extract_embeddings_from_audio.assert_called_once()
            
            # Verify that similarity was computed
            self.assertTrue(mock_enrollment.compute_similarity.called)
            
            # Verify that result is None (fast-path was not triggered)
            self.assertIsNone(result)
    
    def test_real_examples(self):
        """Test with real example transcripts"""
        # Example segments from Dr. Chaffee
        chaffee_segments = [
            "These are complex bioorganic compounds. And, you know, they work very differently in your body, you know, according to your biochemistry.",
            "Drug or substance that you put in your body. It's going to have an effect on your body. And so just the idea that just these are interchangeable units of energy is absolutely nonsensical.",
            "Unfortunately, that means that there's a lot of doctors that do that. And there's a lot of actually quite well-known doctors that have a big following and success."
        ]
        
        # Example segments from guests
        guest_segments = [
            "Other than oxalates, what are some of the other toxins that we're talking about, like lectins and phytates and stuff?",
            "When I got out of high school, I did a bunch of things. I didn't go to college. I started a carpentry business where I make furniture for movies.",
            "I got really extremely dry eye where like it just felt like constant crud was coming out of my eye and I couldn't really bugged me because I couldn't watch screens."
        ]
        
        # Create a function to test segment classification
        def classify_segment(text, is_chaffee_expected):
            # Create mock EnhancedASR with patched methods
            with patch('backend.scripts.common.enhanced_asr.EnhancedASR._get_voice_enrollment') as mock_get_enrollment:
                # Set up mock voice enrollment
                mock_enrollment = MagicMock()
                mock_get_enrollment.return_value = mock_enrollment
                
                # Create mock profile
                mock_profile = {'embeddings': [np.ones(192, dtype=np.float64)]}
                mock_enrollment.load_profile.return_value = mock_profile
                
                # Set up mock embeddings extraction based on expected speaker
                if is_chaffee_expected:
                    mock_embeddings = [np.ones(192, dtype=np.float64)]  # Similar to Chaffee profile
                    mock_enrollment.compute_similarity.return_value = 0.9  # High similarity
                else:
                    mock_embeddings = [np.zeros(192, dtype=np.float64)]  # Different from Chaffee profile
                    mock_enrollment.compute_similarity.return_value = 0.3  # Low similarity
                    
                mock_enrollment._extract_embeddings_from_audio.return_value = mock_embeddings
                
                # Create EnhancedASR instance
                asr = EnhancedASR(self.asr_config)
                
                # Test monologue fast-path
                result = asr._check_monologue_fast_path("dummy_audio.wav")
                
                # For Chaffee, result should not be None
                # For Guest, result should be None
                if is_chaffee_expected:
                    self.assertIsNotNone(result)
                else:
                    self.assertIsNone(result)
        
        # Test Chaffee segments
        for segment in chaffee_segments:
            classify_segment(segment, True)
            
        # Test Guest segments
        for segment in guest_segments:
            classify_segment(segment, False)

if __name__ == "__main__":
    unittest.main()
