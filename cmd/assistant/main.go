package main

import (
	"context"
	"encoding/json"
	"flag"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"strconv"
	"strings"
	"syscall"
	"time"

	"nobara-voice-assistant/internal/agent"
	"nobara-voice-assistant/internal/audio"
	"nobara-voice-assistant/internal/config"
	"nobara-voice-assistant/internal/conversations"
	"nobara-voice-assistant/internal/fastpath"
	"nobara-voice-assistant/internal/server"
	"nobara-voice-assistant/internal/tts"
)

const (
	pidFile        = "/tmp/nobara_assistant.pid"
	audioFile      = "/tmp/nobara_assistant_mic.wav"
	notifIDFile    = "/tmp/nobara_assistant_notif.id"
	lockFile       = "/tmp/nobara_assistant.lock"
	hudEventFile   = "/tmp/nobara_assistant_hud.json"
	soundStart     = "/usr/share/sounds/ocean/stereo/bell.oga"
	soundStop      = "/usr/share/sounds/ocean/stereo/button-pressed.oga"
)

func findProjectDir() string {
	exe, err := os.Executable()
	if err != nil {
		dir, _ := os.Getwd()
		return dir
	}
	realExe, err := filepath.EvalSymlinks(exe)
	if err == nil {
		exe = realExe
	}
	dir := filepath.Dir(exe)
	if filepath.Base(dir) == "bin" {
		return filepath.Dir(dir)
	}
	return dir
}

func playSoundAsync(path string, volume float64) {
	if _, err := os.Stat(path); err == nil {
		volStr := fmt.Sprintf("--volume=%.2f", volume)
		cmd := exec.Command("pw-play", volStr, path)
		_ = cmd.Start()
	}
}

func stopSpeechAndTasks() {
	_ = exec.Command("pkill", "-f", "piper").Run()
	_ = exec.Command("pkill", "-f", "pw-play").Run()
	_ = exec.Command("pkill", "-f", "speak.py").Run()

	// Terminate active agent task if running
	agentPidData, err := os.ReadFile("/tmp/nobara_assistant_agent.pid")
	if err == nil {
		if pid, err := strconv.Atoi(strings.TrimSpace(string(agentPidData))); err == nil {
			_ = syscall.Kill(pid, syscall.SIGTERM)
		}
		_ = os.Remove("/tmp/nobara_assistant_agent.pid")
	}

	// Dismiss notification
	notifData, err := os.ReadFile(notifIDFile)
	if err == nil {
		idStr := strings.TrimSpace(string(notifData))
		if idStr != "" {
			_ = exec.Command("notify-send", "-C", idStr).Run()
		}
		_ = os.Remove(notifIDFile)
	}
}

func transcribeAudio(projectDir, whisperModel, lang string) (string, error) {
	transcribeScript := filepath.Join(projectDir, "src", "transcribe.py")
	out, err := exec.Command("python3", transcribeScript, audioFile, whisperModel, lang).Output()
	if err != nil {
		return "", err
	}
	return strings.TrimSpace(string(out)), nil
}

func main() {
	projectDir := findProjectDir()
	cfg, err := config.Load(projectDir)
	if err != nil {
		fmt.Fprintf(os.Stderr, "Error loading configuration: %v\n", err)
	}

	if len(os.Args) > 1 {
		switch os.Args[1] {
		case "--silence", "--stop", "-s", "silence", "stop":
			stopSpeechAndTasks()
			os.Exit(0)

		case "gui", "web", "settings", "panel":
			if err := server.StartAndOpenUI(projectDir); err != nil {
				fmt.Fprintf(os.Stderr, "Error starting UI: %v\n", err)
				os.Exit(1)
			}
			os.Exit(0)

		case "record-vad":
			// Internal VAD background recorder invoked by assistant
			opts := audio.RecordOptions{
				OutputPath:      audioFile,
				AutoStop:        true,
				SilenceDuration: cfg.SilenceDuration,
				Timeout:         25.0,
			}
			triggered, err := audio.Record(context.Background(), opts)
			if err != nil {
				fmt.Fprintf(os.Stderr, "Recording error: %v\n", err)
				os.Exit(1)
			}
			if triggered {
				// Re-invoke assistant toggle to trigger processing
				exe, _ := os.Executable()
				cmd := exec.Command(exe, "--toggle")
				cmd.Env = os.Environ()
				cmd.Env = append(cmd.Env, "DISPLAY=:0", "WAYLAND_DISPLAY=wayland-0")
				_ = cmd.Start()
			}
			os.Exit(0)

		case "speak":
			text := strings.Join(os.Args[2:], " ")
			if text == "" {
				os.Exit(0)
			}
			_ = tts.Speak(text, projectDir, cfg.VoiceModel, cfg.VoiceSpeaker, cfg.TTSVolume, cfg.AudioDucking)
			os.Exit(0)

		case "fastpath":
			if len(os.Args) < 3 {
				fmt.Println(`{"handled": false}`)
				os.Exit(0)
			}
			lang := "es"
			if len(os.Args) > 3 {
				lang = os.Args[3]
			}
			res := fastpath.TryMatch(os.Args[2], lang)
			data, _ := json.Marshal(res)
			fmt.Println(string(data))
			os.Exit(0)

		case "agent":
			fs := flag.NewFlagSet("agent", flag.ExitOnError)
			textFlag := fs.String("text", "", "Voice transcription")
			notifFlag := fs.String("notif-id", "", "Notification ID")
			forceFlag := fs.Bool("force-new", false, "Force new session")
			_ = fs.Parse(os.Args[2:])

			res, err := agent.RunAgent(cfg, *textFlag, *notifFlag, *forceFlag)
			if err != nil {
				fmt.Fprintf(os.Stderr, "Agent error: %v\n", err)
			}
			fmt.Println(res)
			os.Exit(0)

		case "conversations":
			fs := flag.NewFlagSet("conversations", flag.ExitOnError)
			listFlag := fs.Bool("list", false, "List summaries")
			turnsFlag := fs.String("turns", "", "Get conversation turns")
			resetFlag := fs.Bool("reset", false, "Reset active conversation session")
			deleteFlag := fs.String("delete", "", "Delete conversation")
			exportFlag := fs.String("export", "", "Export markdown")
			_ = fs.Parse(os.Args[2:])

			if *listFlag {
				list, err := conversations.List(cfg.ActiveConversationID, 60)
				if err != nil {
					fmt.Fprintf(os.Stderr, "Error: %v\n", err)
					os.Exit(1)
				}
				data, _ := json.Marshal(list)
				fmt.Println(string(data))
				os.Exit(0)
			}
			if *turnsFlag != "" {
				turns, err := conversations.GetTurns(*turnsFlag)
				if err != nil {
					fmt.Fprintf(os.Stderr, "Error: %v\n", err)
					os.Exit(1)
				}
				data, _ := json.Marshal(turns)
				fmt.Println(string(data))
				os.Exit(0)
			}
			if *resetFlag {
				newID, err := conversations.ResetActiveSession(projectDir)
				if err != nil {
					fmt.Fprintf(os.Stderr, "Error: %v\n", err)
					os.Exit(1)
				}
				fmt.Println(newID)
				os.Exit(0)
			}
			if *deleteFlag != "" {
				_ = conversations.Delete(*deleteFlag)
				os.Exit(0)
			}
			if *exportFlag != "" {
				md, err := conversations.ExportMarkdown(*exportFlag)
				if err != nil {
					fmt.Fprintf(os.Stderr, "Error: %v\n", err)
					os.Exit(1)
				}
				fmt.Println(md)
				os.Exit(0)
			}
			os.Exit(0)
		}
	}

	// Default action: Toggle mode (Record / Stop & Process)
	handleToggle(projectDir, cfg)
}

func handleToggle(projectDir string, cfg *config.Config) {
	if !cfg.Enabled {
		_ = exec.Command("notify-send", "-a", "AI Voice Assistant", "-i", "dialog-information", "-t", "3000",
			"Asistente IA", "El asistente está deshabilitado en los ajustes.").Run()
		return
	}

	// File lock to avoid race conditions
	lockF, err := os.OpenFile(lockFile, os.O_CREATE|os.O_RDWR, 0644)
	if err != nil {
		return
	}
	defer lockF.Close()

	if err := syscall.Flock(int(lockF.Fd()), syscall.LOCK_EX|syscall.LOCK_NB); err != nil {
		return
	}
	defer syscall.Flock(int(lockF.Fd()), syscall.LOCK_UN)

	isEN := (cfg.AssistantLanguage == "en")

	// =========================================================================
	// STATE 1: ALREADY RECORDING -> STOP & PROCESS
	// =========================================================================
	if pidData, err := os.ReadFile(pidFile); err == nil {
		pidStr := strings.TrimSpace(string(pidData))
		if pid, err := strconv.Atoi(pidStr); err == nil && pid > 0 {
			// Stop recording process cleanly
			_ = syscall.Kill(pid, syscall.SIGINT)
			for i := 0; i < 20; i++ {
				if err := syscall.Kill(pid, 0); err != nil {
					break
				}
				time.Sleep(50 * time.Millisecond)
			}
			if err := syscall.Kill(pid, 0); err == nil {
				_ = syscall.Kill(pid, syscall.SIGKILL)
			}
		}
		_ = os.Remove(pidFile)

		// Audio feedback chime
		playSoundAsync(soundStop, cfg.TTSVolume)

		// Processing voice cue
		procesandoWAV := filepath.Join(projectDir, "voices", "procesando.wav")
		if cfg.EnableProcessingVoiceCue {
			playSoundAsync(procesandoWAV, cfg.TTSVolume)
		}

		// Read previous notification ID
		var notifID string
		if data, err := os.ReadFile(notifIDFile); err == nil {
			notifID = strings.TrimSpace(string(data))
		}

		pTitle := "Procesando voz..."
		pBody := "Interpretando lo que has dicho..."
		if isEN {
			pTitle = "Processing voice..."
			pBody = "Interpreting what you said..."
		}

		if notifID != "" {
			_ = exec.Command("notify-send", "-r", notifID, "-a", "AI Voice Assistant", "-i", "system-run", "-t", "0", pTitle, pBody).Run()
		} else {
			out, err := exec.Command("notify-send", "-p", "-a", "AI Voice Assistant", "-i", "system-run", "-t", "0", pTitle, pBody).Output()
			if err == nil {
				notifID = strings.TrimSpace(string(out))
				_ = os.WriteFile(notifIDFile, []byte(notifID), 0644)
			}
		}

		// Validate audio file
		fi, err := os.Stat(audioFile)
		if err != nil || fi.Size() < 100 {
			noAudioTitle := "Asistente IA"
			noAudioBody := "No se detectó audio."
			if isEN {
				noAudioTitle = "AI Assistant"
				noAudioBody = "No audio detected."
			}
			_ = exec.Command("notify-send", "-r", notifID, "-a", "AI Voice Assistant", "-i", "dialog-warning", "-t", "5000", noAudioTitle, noAudioBody).Run()
			return
		}

		// Transcribe locally
		text, err := transcribeAudio(projectDir, cfg.WhisperModel, cfg.AssistantLanguage)
		if err != nil || text == "" {
			warnTitle := "Asistente IA"
			warnBody := "No se detectó ninguna instrucción clara."
			fallback := "No te he entendido bien."
			if isEN {
				warnTitle = "AI Assistant"
				warnBody = "No clear speech detected."
				fallback = "I didn't catch that."
			}
			_ = exec.Command("notify-send", "-r", notifID, "-a", "AI Voice Assistant", "-i", "dialog-warning", "-t", "5000", warnTitle, warnBody).Run()
			if cfg.EnableVoiceReply {
				_ = tts.Speak(fallback, projectDir, cfg.VoiceModel, cfg.VoiceSpeaker, cfg.TTSVolume, cfg.AudioDucking)
			}
			return
		}

		// Fast Path local execution check (<2ms)
		fastRes := fastpath.TryMatch(text, cfg.AssistantLanguage)
		if fastRes.Handled {
			_ = exec.Command("notify-send", "-r", notifID, "-a", "AI Voice Assistant", "-i", "dialog-ok", "-t", "4000", fastRes.Title, fastRes.Reply).Run()
			hudData, _ := json.Marshal(map[string]string{"title": fastRes.Title, "reply": fastRes.Reply})
			_ = os.WriteFile(hudEventFile, hudData, 0644)

			if cfg.EnableVoiceReply {
				_ = tts.Speak(fastRes.Reply, projectDir, cfg.VoiceModel, cfg.VoiceSpeaker, cfg.TTSVolume, cfg.AudioDucking)
			}
			_ = os.Remove(notifIDFile)
			return
		}

		// Transcribed speech notification
		inputTitle := "Has dicho:"
		inputBody := fmt.Sprintf("%s\n\n(Ejecutando...)", text)
		if isEN {
			inputTitle = "You said:"
			inputBody = fmt.Sprintf("%s\n\n(Executing...)", text)
		}
		_ = exec.Command("notify-send", "-r", notifID, "-a", "AI Voice Assistant", "-i", "audio-input-microphone", "-t", "0", inputTitle, inputBody).Run()

		// Execute with AGY Agent
		agentReply, _ := agent.RunAgent(cfg, text, notifID, false)

		// Final notification
		finalTitle := "Asistente Nobara"
		if isEN {
			finalTitle = "Nobara Assistant"
		}
		timeoutStr := strconv.Itoa(cfg.ResultNotifTimeout)
		_ = exec.Command("notify-send", "-r", notifID, "-a", "AI Voice Assistant", "-i", "dialog-ok", "-t", timeoutStr, finalTitle, agentReply).Run()

		hudData, _ := json.Marshal(map[string]string{"title": finalTitle, "reply": agentReply})
		_ = os.WriteFile(hudEventFile, hudData, 0644)

		if cfg.EnableVoiceReply {
			_ = tts.Speak(agentReply, projectDir, cfg.VoiceModel, cfg.VoiceSpeaker, cfg.TTSVolume, cfg.AudioDucking)
		}
		_ = os.Remove(notifIDFile)
		return
	}

	// =========================================================================
	// STATE 2: NOT RECORDING -> START RECORDING
	// =========================================================================
	_ = os.Remove(audioFile)
	stopSpeechAndTasks()
	playSoundAsync(soundStart, cfg.TTSVolume)

	listenTitle := "Escuchando..."
	listenBody := "Habla ahora. Pulsa el atajo de nuevo cuando termines."
	if cfg.AutoStopSilence {
		listenBody = "Habla ahora. Se procesará solo al guardar silencio."
	}
	if isEN {
		listenTitle = "Listening..."
		listenBody = "Speak now. Press shortcut again when done."
		if cfg.AutoStopSilence {
			listenBody = "Speak now. Auto-stops when you pause."
		}
	}

	out, err := exec.Command("notify-send", "-p", "-a", "AI Voice Assistant", "-i", "audio-input-microphone", "-t", "0", listenTitle, listenBody).Output()
	if err == nil {
		notifID := strings.TrimSpace(string(out))
		_ = os.WriteFile(notifIDFile, []byte(notifID), 0644)
	}

	// Launch audio capture
	if cfg.AutoStopSilence {
		exe, _ := os.Executable()
		cmd := exec.Command(exe, "record-vad")
		if err := cmd.Start(); err == nil {
			_ = os.WriteFile(pidFile, []byte(strconv.Itoa(cmd.Process.Pid)), 0644)
		}
	} else {
		cmd := exec.Command("pw-record", "--rate", "16000", "--channels", "1", "--format", "s16", audioFile)
		if err := cmd.Start(); err == nil {
			_ = os.WriteFile(pidFile, []byte(strconv.Itoa(cmd.Process.Pid)), 0644)
		}
	}
}
