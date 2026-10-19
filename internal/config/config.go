package config

import (
	"bufio"
	"fmt"
	"os"
	"path/filepath"
	"strconv"
	"strings"
	"sync"
)

// Config holds assistant runtime settings.
type Config struct {
	Enabled                  bool
	WhisperModel             string
	EnableVoiceReply         bool
	VoiceModel               string
	VoiceSpeaker             string
	TTSVolume                float64
	EnableProcessingVoiceCue bool
	ResultNotifTimeout       int
	AgyBin                   string
	ContinuousConversation   bool
	ActiveConversationID     string
	AssistantLanguage        string
	AutoStopSilence          bool
	SilenceDuration          float64
	AudioDucking             bool
	WakeWordEnabled          bool
	WakeWordModel            string
	WakeWordThreshold        float64
	OverlayHUDEnabled        bool
	Autostart                bool

	ProjectDir string
	ConfigPath string
}

var (
	configMu sync.Mutex
)

// DefaultConfig returns baseline configuration values.
func DefaultConfig(projectDir string) *Config {
	home, _ := os.UserHomeDir()
	configPath := filepath.Join(projectDir, "config", "config.env")

	return &Config{
		Enabled:                  true,
		WhisperModel:             "base",
		EnableVoiceReply:         true,
		VoiceModel:               "es_ES-davefx-medium.onnx",
		VoiceSpeaker:             "",
		TTSVolume:                0.35,
		EnableProcessingVoiceCue: true,
		ResultNotifTimeout:       15000,
		AgyBin:                   filepath.Join(home, ".local", "bin", "agy"),
		ContinuousConversation:   true,
		ActiveConversationID:     "",
		AssistantLanguage:        "es",
		AutoStopSilence:          false,
		SilenceDuration:          1.2,
		AudioDucking:             false,
		WakeWordEnabled:          false,
		WakeWordModel:            "hey_jarvis",
		WakeWordThreshold:        0.30,
		OverlayHUDEnabled:        true,
		Autostart:                IsAutostartEnabled(),
		ProjectDir:               projectDir,
		ConfigPath:               configPath,
	}
}

// ExpandHome replaces leading ~ or $HOME with actual home directory path.
func ExpandHome(path string) string {
	home, err := os.UserHomeDir()
	if err != nil {
		return path
	}
	if strings.HasPrefix(path, "~/") {
		return filepath.Join(home, path[2:])
	}
	if strings.HasPrefix(path, "$HOME/") {
		return filepath.Join(home, path[6:])
	}
	if path == "~" || path == "$HOME" {
		return home
	}
	return path
}

// Load reads and parses config.env file.
func Load(projectDir string) (*Config, error) {
	configMu.Lock()
	defer configMu.Unlock()

	cfg := DefaultConfig(projectDir)
	if _, err := os.Stat(cfg.ConfigPath); os.IsNotExist(err) {
		return cfg, nil
	}

	file, err := os.Open(cfg.ConfigPath)
	if err != nil {
		return cfg, err
	}
	defer file.Close()

	scanner := bufio.NewScanner(file)
	for scanner.Scan() {
		line := strings.TrimSpace(scanner.Text())
		if line == "" || strings.HasPrefix(line, "#") {
			continue
		}
		parts := strings.SplitN(line, "=", 2)
		if len(parts) != 2 {
			continue
		}

		k := strings.TrimSpace(parts[0])
		v := strings.Trim(strings.TrimSpace(parts[1]), "\"'")

		switch k {
		case "ENABLED":
			cfg.Enabled = parseBool(v, cfg.Enabled)
		case "WHISPER_MODEL":
			cfg.WhisperModel = v
		case "ENABLE_VOICE_REPLY":
			cfg.EnableVoiceReply = parseBool(v, cfg.EnableVoiceReply)
		case "VOICE_MODEL":
			cfg.VoiceModel = v
		case "VOICE_SPEAKER":
			cfg.VoiceSpeaker = v
		case "TTS_VOLUME":
			if f, err := strconv.ParseFloat(v, 64); err == nil {
				cfg.TTSVolume = f
			}
		case "ENABLE_PROCESSING_VOICE_CUE":
			cfg.EnableProcessingVoiceCue = parseBool(v, cfg.EnableProcessingVoiceCue)
		case "RESULT_NOTIF_TIMEOUT":
			if n, err := strconv.Atoi(v); err == nil {
				cfg.ResultNotifTimeout = n
			}
		case "AGY_BIN":
			cfg.AgyBin = ExpandHome(v)
		case "CONTINUOUS_CONVERSATION":
			cfg.ContinuousConversation = parseBool(v, cfg.ContinuousConversation)
		case "ACTIVE_CONVERSATION_ID":
			cfg.ActiveConversationID = v
		case "ASSISTANT_LANGUAGE":
			cfg.AssistantLanguage = strings.ToLower(v)
		case "AUTO_STOP_SILENCE":
			cfg.AutoStopSilence = parseBool(v, cfg.AutoStopSilence)
		case "SILENCE_DURATION":
			if f, err := strconv.ParseFloat(v, 64); err == nil {
				cfg.SilenceDuration = f
			}
		case "AUDIO_DUCKING":
			cfg.AudioDucking = parseBool(v, cfg.AudioDucking)
		case "WAKE_WORD_ENABLED":
			cfg.WakeWordEnabled = parseBool(v, cfg.WakeWordEnabled)
		case "WAKE_WORD_MODEL":
			cfg.WakeWordModel = v
		case "WAKE_WORD_THRESHOLD":
			if f, err := strconv.ParseFloat(v, 64); err == nil {
				cfg.WakeWordThreshold = f
			}
		case "OVERLAY_HUD_ENABLED":
			cfg.OverlayHUDEnabled = parseBool(v, cfg.OverlayHUDEnabled)
		}
	}

	return cfg, scanner.Err()
}

// UpdateValue sets a single configuration key in config.env.
func UpdateValue(configPath, key, value string) error {
	configMu.Lock()
	defer configMu.Unlock()

	var lines []string
	found := false

	if data, err := os.ReadFile(configPath); err == nil {
		scanner := bufio.NewScanner(strings.NewReader(string(data)))
		for scanner.Scan() {
			line := scanner.Text()
			trimmed := strings.TrimSpace(line)
			if strings.HasPrefix(trimmed, key+"=") {
				lines = append(lines, formatConfigLine(key, value))
				found = true
			} else {
				lines = append(lines, line)
			}
		}
	}

	if !found {
		lines = append(lines, formatConfigLine(key, value))
	}

	tmpPath := configPath + ".tmp"
	if err := os.WriteFile(tmpPath, []byte(strings.Join(lines, "\n")+"\n"), 0644); err != nil {
		return err
	}
	return os.Rename(tmpPath, configPath)
}

func formatConfigLine(key, val string) string {
	lower := strings.ToLower(val)
	if lower == "true" || lower == "false" {
		return fmt.Sprintf("%s=%s", key, val)
	}
	if _, err := strconv.ParseFloat(val, 64); err == nil {
		return fmt.Sprintf("%s=%s", key, val)
	}
	return fmt.Sprintf("%s=\"%s\"", key, val)
}

func parseBool(val string, defaultVal bool) bool {
	v := strings.ToLower(strings.TrimSpace(val))
	if v == "true" || v == "1" || v == "yes" {
		return true
	}
	if v == "false" || v == "0" || v == "no" {
		return false
	}
	return defaultVal
}

// IsAutostartEnabled checks if desktop autostart entry exists and is active.
func IsAutostartEnabled() bool {
	home, err := os.UserHomeDir()
	if err != nil {
		return false
	}
	desktopPath := filepath.Join(home, ".config", "autostart", "nobara-jarvis-autostart.desktop")
	data, err := os.ReadFile(desktopPath)
	if err != nil {
		return false
	}
	return !strings.Contains(string(data), "Hidden=true")
}

// SetAutostart creates or deletes the KDE autostart desktop entry.
func SetAutostart(enable bool, projectDir string) error {
	home, err := os.UserHomeDir()
	if err != nil {
		return err
	}
	autostartDir := filepath.Join(home, ".config", "autostart")
	desktopPath := filepath.Join(autostartDir, "nobara-jarvis-autostart.desktop")

	if !enable {
		if _, err := os.Stat(desktopPath); err == nil {
			return os.Remove(desktopPath)
		}
		return nil
	}

	_ = os.MkdirAll(autostartDir, 0755)
	autostartBin := filepath.Join(projectDir, "bin", "nobara-voice-assistant-autostart")
	content := fmt.Sprintf(`[Desktop Entry]
Name=Jarvis AI Autostart
Comment=Inicia Jarvis AI al arrancar el sistema
Exec=%s
Icon=nobara-jarvis
Terminal=false
Type=Application
Categories=Utility;
StartupNotify=false
X-GNOME-Autostart-enabled=true
X-KDE-autostart-after=panel
Hidden=false
`, autostartBin)

	return os.WriteFile(desktopPath, []byte(content), 0644)
}

// SaveConfig persists the in-memory configuration struct to config.env.
func SaveConfig(cfg *Config) error {
	configMu.Lock()
	defer configMu.Unlock()

	var sb strings.Builder
	sb.WriteString("# Nobara Voice Assistant Configuration\n")
	sb.WriteString(formatConfigLine("ENABLED", fmt.Sprintf("%t", cfg.Enabled)) + "\n")
	sb.WriteString(formatConfigLine("WHISPER_MODEL", cfg.WhisperModel) + "\n")
	sb.WriteString(formatConfigLine("ENABLE_VOICE_REPLY", fmt.Sprintf("%t", cfg.EnableVoiceReply)) + "\n")
	sb.WriteString(formatConfigLine("VOICE_MODEL", cfg.VoiceModel) + "\n")
	sb.WriteString(formatConfigLine("VOICE_SPEAKER", cfg.VoiceSpeaker) + "\n")
	sb.WriteString(formatConfigLine("TTS_VOLUME", fmt.Sprintf("%.2f", cfg.TTSVolume)) + "\n")
	sb.WriteString(formatConfigLine("ENABLE_PROCESSING_VOICE_CUE", fmt.Sprintf("%t", cfg.EnableProcessingVoiceCue)) + "\n")
	sb.WriteString(formatConfigLine("RESULT_NOTIF_TIMEOUT", fmt.Sprintf("%d", cfg.ResultNotifTimeout)) + "\n")
	sb.WriteString(formatConfigLine("AGY_BIN", cfg.AgyBin) + "\n")
	sb.WriteString(formatConfigLine("CONTINUOUS_CONVERSATION", fmt.Sprintf("%t", cfg.ContinuousConversation)) + "\n")
	sb.WriteString(formatConfigLine("ACTIVE_CONVERSATION_ID", cfg.ActiveConversationID) + "\n")
	sb.WriteString(formatConfigLine("ASSISTANT_LANGUAGE", cfg.AssistantLanguage) + "\n")
	sb.WriteString(formatConfigLine("AUTO_STOP_SILENCE", fmt.Sprintf("%t", cfg.AutoStopSilence)) + "\n")
	sb.WriteString(formatConfigLine("SILENCE_DURATION", fmt.Sprintf("%.1f", cfg.SilenceDuration)) + "\n")
	sb.WriteString(formatConfigLine("AUDIO_DUCKING", fmt.Sprintf("%t", cfg.AudioDucking)) + "\n")
	sb.WriteString(formatConfigLine("WAKE_WORD_ENABLED", fmt.Sprintf("%t", cfg.WakeWordEnabled)) + "\n")
	sb.WriteString(formatConfigLine("WAKE_WORD_MODEL", cfg.WakeWordModel) + "\n")
	sb.WriteString(formatConfigLine("WAKE_WORD_THRESHOLD", fmt.Sprintf("%.2f", cfg.WakeWordThreshold)) + "\n")
	sb.WriteString(formatConfigLine("OVERLAY_HUD_ENABLED", fmt.Sprintf("%t", cfg.OverlayHUDEnabled)) + "\n")

	tmpPath := cfg.ConfigPath + ".tmp"
	if err := os.WriteFile(tmpPath, []byte(sb.String()), 0644); err != nil {
		return err
	}
	if err := os.Rename(tmpPath, cfg.ConfigPath); err != nil {
		return err
	}

	return SetAutostart(cfg.Autostart, cfg.ProjectDir)
}

