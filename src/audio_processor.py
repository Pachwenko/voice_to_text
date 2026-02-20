"""Audio preprocessing module for optimizing recordings for Whisper transcription.

Provides gain adjustment and loudness normalization using industry-standard
algorithms to ensure consistent, high-quality audio for speech recognition.
"""

import numpy as np
import logging
from typing import Tuple

logger = logging.getLogger("voice_to_text")


class AudioLevelMonitor:
    """Real-time audio level monitoring during recording.

    Tracks peak levels, RMS, and provides warnings for audio quality issues.
    """

    def __init__(self, sample_rate: int, window_size: int = 2048):
        """Initialize audio level monitor.

        Args:
            sample_rate: Sample rate in Hz
            window_size: Number of samples per monitoring window
        """
        self.sample_rate = sample_rate
        self.window_size = window_size
        self.peak_level = 0.0
        self.rms_level = 0.0
        self.peak_db = -np.inf
        self.rms_db = -np.inf
        self.num_frames = 0
        self.clipping_detected = False

    def update(self, audio_chunk: np.ndarray) -> None:
        """Update monitor with new audio data.

        Args:
            audio_chunk: Audio samples to analyze
        """
        if len(audio_chunk) == 0:
            return

        # Update peak level
        chunk_peak = np.max(np.abs(audio_chunk))
        if chunk_peak > self.peak_level:
            self.peak_level = chunk_peak
            self.peak_db = 20 * np.log10(chunk_peak + 1e-10)

        # Update RMS (Root Mean Square) level
        chunk_rms = np.sqrt(np.mean(audio_chunk ** 2))
        self.rms_level = chunk_rms
        self.rms_db = 20 * np.log10(chunk_rms + 1e-10)

        # Detect clipping
        if chunk_peak >= 0.99:
            self.clipping_detected = True

        self.num_frames += len(audio_chunk)

    def get_report(self) -> dict:
        """Get current monitoring report.

        Returns:
            Dictionary with audio level statistics
        """
        return {
            'peak_db': self.peak_db,
            'rms_db': self.rms_db,
            'peak_linear': self.peak_level,
            'rms_linear': self.rms_level,
            'clipping': self.clipping_detected,
            'duration_s': self.num_frames / self.sample_rate,
        }

    def get_quality_assessment(self) -> Tuple[str, str]:
        """Assess audio quality and provide recommendations.

        Returns:
            Tuple of (quality_level, recommendation)
            quality_level: 'excellent', 'good', 'fair', 'poor', 'clipped'
            recommendation: Actionable suggestion for improvement
        """
        if self.clipping_detected:
            return ('clipped', 'Reduce microphone gain - audio is clipping')

        if self.rms_db < -30:
            return ('poor', 'Audio is very quiet - increase microphone gain or boost')

        if self.rms_db < -25:
            return ('fair', 'Audio is quiet - consider using --boost 6-8')

        if -20 <= self.rms_db <= -14:
            return ('good', 'Audio level is optimal for transcription')

        if -14 < self.rms_db < -10:
            return ('good', 'Audio level is good')

        if self.rms_db >= -10:
            return ('excellent', 'Audio level is excellent')

        return ('unknown', 'Unable to assess audio quality')


try:
    import pyloudnorm
    PYLOUDNORM_AVAILABLE = True
except ImportError:
    PYLOUDNORM_AVAILABLE = False
    logger.warning("pyloudnorm not available; loudness normalization disabled")


def apply_gain(audio: np.ndarray, gain_db: float) -> np.ndarray:
    """Apply gain adjustment to audio.

    Args:
        audio: Audio samples (numpy array)
        gain_db: Gain in decibels (positive = boost, negative = reduce)

    Returns:
        Gain-adjusted audio samples (clipped to prevent distortion)
    """
    if gain_db == 0:
        return audio

    # Convert dB to linear gain
    gain_linear = 10 ** (gain_db / 20)
    audio_boosted = audio * gain_linear

    # Clip to prevent distortion (keep within -1.0 to 1.0)
    audio_clipped = np.clip(audio_boosted, -1.0, 1.0)

    # Warn if clipping occurred
    if np.any(np.abs(audio_boosted) > 1.0):
        logger.warning(
            f"Audio clipping detected with {gain_db}dB gain; "
            f"consider reducing gain or input volume"
        )

    return audio_clipped


def normalize_loudness(
    audio: np.ndarray,
    sample_rate: int,
    target_loudness: float = -20.0
) -> np.ndarray:
    """Normalize audio loudness to a target LUFS level using ITU-R BS.1770-4 standard.

    This is the recommended approach for speech audio preprocessing, providing
    perceptually consistent loudness across different recordings and microphones.

    Args:
        audio: Audio samples (numpy array)
        sample_rate: Sample rate in Hz
        target_loudness: Target loudness in LUFS (default: -20.0, optimal for speech)

    Returns:
        Loudness-normalized audio samples
    """
    if not PYLOUDNORM_AVAILABLE:
        logger.warning(
            "pyloudnorm not installed; using RMS normalization instead. "
            "Install pyloudnorm for better results: pip install pyloudnorm"
        )
        return normalize_rms(audio, target_loudness=-20.0)

    try:
        meter = pyloudnorm.Meter(sample_rate)
        loudness = meter.integrated_loudness(audio)

        # Skip if audio is silent or invalid
        if loudness == -np.inf:
            logger.warning("Audio is silent or too quiet for loudness measurement")
            return audio

        audio_normalized = pyloudnorm.normalize.loudness(
            audio, loudness, target_loudness
        )

        # Clip to prevent distortion
        audio_normalized = np.clip(audio_normalized, -1.0, 1.0)

        current_db = 20 * np.log10(np.sqrt(np.mean(audio ** 2)) + 1e-10)
        normalized_db = 20 * np.log10(np.sqrt(np.mean(audio_normalized ** 2)) + 1e-10)

        logger.debug(
            f"Loudness normalized: {current_db:.1f}dB -> {normalized_db:.1f}dB "
            f"(target: {target_loudness:.1f} LUFS)"
        )

        return audio_normalized
    except Exception as e:
        logger.warning(f"Loudness normalization failed: {e}; using RMS instead")
        return normalize_rms(audio, target_loudness=-20.0)


def normalize_rms(
    audio: np.ndarray,
    target_loudness: float = -20.0
) -> np.ndarray:
    """Normalize audio using RMS (Root Mean Square) energy normalization.

    Simpler than loudness normalization but still effective. Used as fallback
    if pyloudnorm is not available.

    Args:
        audio: Audio samples (numpy array)
        target_loudness: Target RMS level in dB (default: -20.0dB)

    Returns:
        RMS-normalized audio samples
    """
    # Calculate current RMS
    rms = np.sqrt(np.mean(audio ** 2))
    current_db = 20 * np.log10(rms + 1e-10)

    # Calculate required gain
    target_linear = 10 ** (target_loudness / 20)
    gain = target_linear / (rms + 1e-10)

    # Apply gain and clip
    audio_normalized = np.clip(audio * gain, -1.0, 1.0)

    normalized_db = 20 * np.log10(np.sqrt(np.mean(audio_normalized ** 2)) + 1e-10)
    logger.debug(f"RMS normalized: {current_db:.1f}dB -> {normalized_db:.1f}dB")

    return audio_normalized


def process_audio_for_whisper(
    audio: np.ndarray,
    sample_rate: int,
    gain_db: float = 0.0,
    normalize: bool = True
) -> np.ndarray:
    """Complete preprocessing pipeline for Whisper transcription.

    Applies gain boost and loudness normalization to optimize audio quality
    for speech recognition.

    Args:
        audio: Audio samples (numpy array)
        sample_rate: Sample rate in Hz
        gain_db: Gain to apply in decibels (default: 0 = no boost)
        normalize: Whether to apply loudness normalization (default: True)

    Returns:
        Processed audio samples, ready for Whisper transcription
    """
    logger.debug(f"Processing audio: gain={gain_db}dB, normalize={normalize}")

    # Step 1: Apply gain if requested
    if gain_db != 0:
        audio = apply_gain(audio, gain_db)
        logger.debug(f"Applied {gain_db}dB gain boost")

    # Step 2: Normalize loudness if requested
    if normalize:
        audio = normalize_loudness(audio, sample_rate, target_loudness=-20.0)
        logger.debug("Applied loudness normalization")

    # Step 3: Final safety clip
    audio = np.clip(audio, -1.0, 1.0)

    return audio
