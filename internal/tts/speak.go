package tts

import (
	"bytes"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"regexp"
	"strconv"
	"strings"
)

var (
	reCodeBlocks = regexp.MustCompile("(?s)```.*?```")
	reInlineCode = regexp.MustCompile("`([^`]+)`")
	reEmphasis   = regexp.MustCompile(`\*{1,3}([^*]+)\*{1,3}`)
	reHeaders    = regexp.MustCompile(`(?m)^#+\s*`)
	reLinks      = regexp.MustCompile(`\[([^\]]+)\]\([^)]+\)`)
	reListItems  = regexp.MustCompile(`(?m)^\s*[-*+]\s+`)
	reWhitespace = regexp.MustCompile(`\s+`)
	reVolume     = regexp.MustCompile(`Volume:\s+([0-9\.]+)`)
)

// CleanMarkdown removes markdown syntax to prepare text for TTS reading.
func CleanMarkdown(text string) string {
	s := reCodeBlocks.ReplaceAllString(text, "")
	s = reInlineCode.ReplaceAllString(s, "$1")
	s = reEmphasis.ReplaceAllString(s, "$1")
	s = reHeaders.ReplaceAllString(s, "")
	s = reLinks.ReplaceAllString(s, "$1")
	s = reListItems.ReplaceAllString(s, "")
	s = reWhitespace.ReplaceAllString(s, " ")
	return strings.TrimSpace(s)
}

func getSinkVolume() float64 {
	out, err := exec.Command("wpctl", "get-volume", "@DEFAULT_AUDIO_SINK@").Output()
	if err != nil {
		return -1
	}
	m := reVolume.FindStringSubmatch(string(out))
	if len(m) > 1 {
		if val, err := strconv.ParseFloat(m[1], 64); err == nil {
			return val
		}
	}
	return -1
}

// Speak synthesizes text using local Piper ONNX model and plays through PipeWire.
func Speak(text, projectDir, voiceModel, speaker string, volume float64, ducking bool) error {
	cleaned := CleanMarkdown(text)
	if cleaned == "" {
		return nil
	}

	modelPath := filepath.Join(projectDir, "voices", voiceModel)
	if _, err := os.Stat(modelPath); os.IsNotExist(err) {
		modelPath = filepath.Join(projectDir, "voices", "es_ES-davefx-medium.onnx")
	}

	outputWAV := "/tmp/nobara_assistant_speech.wav"
	args := []string{
		"-m", "piper",
		"--model", modelPath,
		"--output-file", outputWAV,
	}
	if strings.TrimSpace(speaker) != "" {
		args = append(args, "--speaker", strings.TrimSpace(speaker))
	}

	cmd := exec.Command("python3", args...)
	cmd.Stdin = strings.NewReader(cleaned)
	var errBuf bytes.Buffer
	cmd.Stderr = &errBuf

	if err := cmd.Run(); err != nil {
		return fmt.Errorf("piper execution failed: %v (%s)", err, errBuf.String())
	}

	fi, err := os.Stat(outputWAV)
	if err != nil || fi.Size() == 0 {
		return fmt.Errorf("generated speech file is empty")
	}

	// Audio ducking for background media
	var origVol float64 = -1
	if ducking {
		vol := getSinkVolume()
		if vol > 0.15 {
			origVol = vol
			duckVol := mathMax(0.1, round2(vol*0.45))
			_ = exec.Command("wpctl", "set-volume", "@DEFAULT_AUDIO_SINK@", fmt.Sprintf("%.2f", duckVol)).Run()
		}
	}

	defer func() {
		if ducking && origVol > 0 {
			_ = exec.Command("wpctl", "set-volume", "@DEFAULT_AUDIO_SINK@", fmt.Sprintf("%.2f", origVol)).Run()
		}
	}()

	volStr := fmt.Sprintf("--volume=%.2f", volume)
	playCmd := exec.Command("pw-play", volStr, outputWAV)
	return playCmd.Run()
}

func mathMax(a, b float64) float64 {
	if a > b {
		return a
	}
	return b
}

func round2(f float64) float64 {
	return float64(int(f*100+0.5)) / 100
}
