package audio

import (
	"context"
	"encoding/binary"
	"io"
	"math"
	"os"
	"os/exec"
	"syscall"
	"time"
)

// RecordOptions defines capture and VAD parameters.
type RecordOptions struct {
	OutputPath      string
	AutoStop        bool
	SilenceDuration float64
	Timeout         float64
	TriggerCmd      string
}

// Record captures audio from PipeWire with real-time VAD silence detection.
func Record(ctx context.Context, opts RecordOptions) (bool, error) {
	silenceLimit := opts.SilenceDuration
	if silenceLimit < 0.6 {
		silenceLimit = 0.6
	}
	timeoutLimit := opts.Timeout
	if timeoutLimit <= 0 {
		timeoutLimit = 25.0
	}

	// Output file initialization
	outFile, err := os.Create(opts.OutputPath)
	if err != nil {
		return false, err
	}
	defer outFile.Close()

	// Write empty WAV header placeholder
	if err := WriteWAVHeader(outFile, 0); err != nil {
		return false, err
	}

	// 16000 Hz, 1 channel, 16-bit. 50ms chunk = 800 samples = 1600 bytes.
	const (
		chunkDuration = 0.05
		chunkBytes    = 1600
		chunkSamples  = 800
	)

	cmd := exec.CommandContext(ctx, "pw-record",
		"--rate", "16000",
		"--channels", "1",
		"--format", "s16",
		"--container", "raw",
		"-",
	)

	stdout, err := cmd.StdoutPipe()
	if err != nil {
		return false, err
	}

	if err := cmd.Start(); err != nil {
		return false, err
	}

	var (
		totalAudioBytes        uint32
		startTime              = time.Now()
		noiseSamples           []float64
		noiseFloor             = 300.0
		speechThreshold        = 800.0
		silenceThreshold       = 450.0
		peakSpeechRMS          = 1200.0
		hasSpoken              = false
		consecutiveVoiceChunks = 0
		silenceElapsed         = 0.0
		autoTriggered          = false
		buf                    = make([]byte, chunkBytes)
	)

	defer func() {
		_ = FinalizeWAV(outFile, totalAudioBytes)
		if cmd.Process != nil {
			_ = cmd.Process.Signal(syscall.SIGTERM)
			done := make(chan error, 1)
			go func() { done <- cmd.Wait() }()
			select {
			case <-done:
			case <-time.After(200 * time.Millisecond):
				_ = cmd.Process.Kill()
			}
		}
	}()

	for {
		select {
		case <-ctx.Done():
			return false, nil
		default:
		}

		_, err := io.ReadFull(stdout, buf)
		if err != nil {
			break
		}

		if _, err := outFile.Write(buf); err != nil {
			break
		}
		totalAudioBytes += chunkBytes

		elapsed := time.Since(startTime).Seconds()
		if elapsed >= timeoutLimit {
			if hasSpoken {
				autoTriggered = true
			}
			break
		}

		if !opts.AutoStop {
			continue
		}

		// Calculate Root Mean Square (RMS) for 16-bit PCM chunk
		var sumSq float64
		for i := 0; i < chunkBytes; i += 2 {
			sample := int16(binary.LittleEndian.Uint16(buf[i : i+2]))
			sumSq += float64(sample) * float64(sample)
		}
		rms := math.Sqrt(sumSq / float64(chunkSamples))

		// Phase 1: Calibrate ambient noise floor during first 250ms (5 chunks)
		if len(noiseSamples) < 5 {
			noiseSamples = append(noiseSamples, rms)
			if len(noiseSamples) == 5 {
				var sum float64
				for _, v := range noiseSamples {
					sum += v
				}
				mean := sum / 5.0
				noiseFloor = math.Max(150.0, math.Min(mean, 800.0))
				speechThreshold = math.Max(750.0, noiseFloor*2.2)
				silenceThreshold = math.Max(350.0, noiseFloor*1.5)
			}
			continue
		}

		// Phase 2: Speech onset detection
		if !hasSpoken {
			if rms > speechThreshold {
				consecutiveVoiceChunks++
				if consecutiveVoiceChunks >= 2 {
					hasSpoken = true
					silenceElapsed = 0.0
					peakSpeechRMS = math.Max(peakSpeechRMS, rms)
					silenceThreshold = math.Max(350.0, math.Min(noiseFloor*1.5, peakSpeechRMS*0.4))
				}
			} else {
				consecutiveVoiceChunks = 0
				if elapsed > 8.0 {
					// Timeout if user did not speak within 8 seconds
					break
				}
			}
		} else {
			// Phase 3: Speech continuation or silence detection
			if rms > silenceThreshold {
				silenceElapsed = 0.0
				peakSpeechRMS = math.Max(peakSpeechRMS, rms)
				silenceThreshold = math.Max(350.0, math.Min(noiseFloor*1.5, peakSpeechRMS*0.4))
			} else {
				silenceElapsed += chunkDuration
				if silenceElapsed >= silenceLimit {
					autoTriggered = true
					break
				}
			}
		}
	}

	return autoTriggered, nil
}
