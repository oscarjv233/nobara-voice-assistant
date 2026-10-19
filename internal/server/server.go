package server

import (
	"context"
	"embed"
	"encoding/json"
	"fmt"
	"io/fs"
	"net"
	"net/http"
	"os"
	"os/exec"
	"os/signal"
	"path/filepath"
	"strconv"
	"strings"
	"sync"
	"syscall"
	"time"

	"nobara-voice-assistant/internal/config"
	"nobara-voice-assistant/internal/conversations"
	"nobara-voice-assistant/internal/fastpath"
	"nobara-voice-assistant/internal/tts"
)

//go:embed all:web
var webAssets embed.FS

var (
	lastActivity  = time.Now()
	activityMu    sync.Mutex
	hasEverActive = false
)

func recordActivity() {
	activityMu.Lock()
	defer activityMu.Unlock()
	lastActivity = time.Now()
	hasEverActive = true
}

func activityMiddleware(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		recordActivity()
		w.Header().Set("Cache-Control", "no-cache, no-store, must-revalidate")
		next.ServeHTTP(w, r)
	})
}

// StartAndOpenUI starts local control server and launches desktop window.
func StartAndOpenUI(projectDir string) error {
	const defaultPort = 4242
	addr := fmt.Sprintf("127.0.0.1:%d", defaultPort)

	// Check if server is already running on default port
	client := &http.Client{Timeout: 800 * time.Millisecond}
	resp, err := client.Get(fmt.Sprintf("http://%s/api/config", addr))
	if err == nil && resp.StatusCode == http.StatusOK {
		_ = resp.Body.Close()
		return openDesktopWindow(fmt.Sprintf("http://%s", addr))
	}

	listener, err := net.Listen("tcp", addr)
	if err != nil {
		// Port conflict, fallback to dynamic available port
		listener, err = net.Listen("tcp", "127.0.0.1:0")
		if err != nil {
			return fmt.Errorf("failed to bind server port: %w", err)
		}
	}
	defer listener.Close()

	port := listener.Addr().(*net.TCPAddr).Port
	appURL := fmt.Sprintf("http://127.0.0.1:%d", port)

	mux := http.NewServeMux()
	registerRoutes(mux, projectDir)

	server := &http.Server{
		Handler: activityMiddleware(mux),
	}

	// Channel to catch interrupt signals
	stopChan := make(chan os.Signal, 1)
	signal.Notify(stopChan, os.Interrupt, syscall.SIGTERM)

	// Background idle monitor to shut down when window is closed
	go func() {
		ticker := time.NewTicker(2 * time.Second)
		defer ticker.Stop()
		gracePeriod := time.Now().Add(35 * time.Second)

		for {
			select {
			case <-ticker.C:
				activityMu.Lock()
				active := hasEverActive
				last := lastActivity
				activityMu.Unlock()

				if active {
					if time.Since(last) > 12*time.Second {
						_ = server.Shutdown(context.Background())
						return
					}
				} else if time.Now().After(gracePeriod) {
					_ = server.Shutdown(context.Background())
					return
				}
			case <-stopChan:
				_ = server.Shutdown(context.Background())
				return
			}
		}
	}()

	// Launch desktop window in KDE
	go func() {
		time.Sleep(150 * time.Millisecond)
		_ = openDesktopWindow(appURL)
	}()

	// Run server
	if err := server.Serve(listener); err != nil && err != http.ErrServerClosed {
		return err
	}
	return nil
}

func openDesktopWindow(appURL string) error {
	env := append(os.Environ(), "DISPLAY=:0", "WAYLAND_DISPLAY=wayland-0")

	braveBin, err := exec.LookPath("brave-browser")
	if err != nil {
		braveBin, err = exec.LookPath("brave")
	}

	if err == nil {
		cmd := exec.Command("kstart", "--", braveBin,
			fmt.Sprintf("--app=%s", appURL),
			"--window-size=1040,760",
			"--user-data-dir=/tmp/nobara_assistant_gui_profile",
		)
		cmd.Env = env
		return cmd.Start()
	}

	// Fallback to system browser
	cmd := exec.Command("kstart", "--", "xdg-open", appURL)
	cmd.Env = env
	return cmd.Start()
}

func registerRoutes(mux *http.ServeMux, projectDir string) {
	// 1. Static Web Assets
	subFS, err := fs.Sub(webAssets, "web")
	if err == nil {
		fileServer := http.FileServer(http.FS(subFS))
		mux.Handle("GET /", fileServer)
	}

	// 2. Configuration Endpoints
	mux.HandleFunc("GET /api/config", func(w http.ResponseWriter, r *http.Request) {
		cfg, err := config.Load(projectDir)
		if err != nil {
			http.Error(w, err.Error(), http.StatusInternalServerError)
			return
		}
		w.Header().Set("Content-Type", "application/json")
		_ = json.NewEncoder(w).Encode(cfg)
	})

	mux.HandleFunc("POST /api/config", func(w http.ResponseWriter, r *http.Request) {
		var in config.Config
		if err := json.NewDecoder(r.Body).Decode(&in); err != nil {
			http.Error(w, err.Error(), http.StatusBadRequest)
			return
		}

		current, err := config.Load(projectDir)
		if err != nil {
			http.Error(w, err.Error(), http.StatusInternalServerError)
			return
		}

		current.Enabled = in.Enabled
		current.AssistantLanguage = in.AssistantLanguage
		if in.VoiceModel != "" {
			current.VoiceModel = in.VoiceModel
		}
		current.VoiceSpeaker = in.VoiceSpeaker
		current.TTSVolume = in.TTSVolume
		current.EnableVoiceReply = in.EnableVoiceReply
		current.EnableProcessingVoiceCue = in.EnableProcessingVoiceCue
		current.WhisperModel = in.WhisperModel
		current.AutoStopSilence = in.AutoStopSilence
		current.SilenceDuration = in.SilenceDuration
		current.ContinuousConversation = in.ContinuousConversation
		current.AudioDucking = in.AudioDucking
		current.WakeWordEnabled = in.WakeWordEnabled
		current.WakeWordModel = in.WakeWordModel
		current.WakeWordThreshold = in.WakeWordThreshold
		current.OverlayHUDEnabled = in.OverlayHUDEnabled
		current.Autostart = in.Autostart

		if err := config.SaveConfig(current); err != nil {
			http.Error(w, err.Error(), http.StatusInternalServerError)
			return
		}

		w.Header().Set("Content-Type", "application/json")
		_ = json.NewEncoder(w).Encode(map[string]bool{"ok": true})
	})

	// 3. Conversation Management Endpoints
	mux.HandleFunc("GET /api/conversations", func(w http.ResponseWriter, r *http.Request) {
		cfg, _ := config.Load(projectDir)
		list, err := conversations.List(cfg.ActiveConversationID, 60)
		if err != nil {
			http.Error(w, err.Error(), http.StatusInternalServerError)
			return
		}
		w.Header().Set("Content-Type", "application/json")
		_ = json.NewEncoder(w).Encode(list)
	})

	mux.HandleFunc("GET /api/conversations/{id}", func(w http.ResponseWriter, r *http.Request) {
		id := r.PathValue("id")
		if id == "" {
			http.Error(w, "missing conversation id", http.StatusBadRequest)
			return
		}
		detail, err := conversations.GetDetail(id)
		if err != nil {
			http.Error(w, err.Error(), http.StatusNotFound)
			return
		}
		w.Header().Set("Content-Type", "application/json")
		_ = json.NewEncoder(w).Encode(detail)
	})

	mux.HandleFunc("GET /api/conversations/{id}/export", func(w http.ResponseWriter, r *http.Request) {
		id := r.PathValue("id")
		md, err := conversations.ExportMarkdown(id)
		if err != nil {
			http.Error(w, err.Error(), http.StatusNotFound)
			return
		}
		w.Header().Set("Content-Type", "application/json")
		_ = json.NewEncoder(w).Encode(map[string]string{"markdown": md})
	})

	mux.HandleFunc("DELETE /api/conversations/{id}", func(w http.ResponseWriter, r *http.Request) {
		id := r.PathValue("id")
		if err := conversations.Delete(id); err != nil {
			http.Error(w, err.Error(), http.StatusInternalServerError)
			return
		}
		w.Header().Set("Content-Type", "application/json")
		_ = json.NewEncoder(w).Encode(map[string]bool{"ok": true})
	})

	mux.HandleFunc("POST /api/conversations/active", func(w http.ResponseWriter, r *http.Request) {
		var body struct {
			ID string `json:"id"`
		}
		if err := json.NewDecoder(r.Body).Decode(&body); err != nil || body.ID == "" {
			http.Error(w, "invalid request", http.StatusBadRequest)
			return
		}
		configPath := filepath.Join(projectDir, "config", "config.env")
		if err := config.UpdateValue(configPath, "ACTIVE_CONVERSATION_ID", body.ID); err != nil {
			http.Error(w, err.Error(), http.StatusInternalServerError)
			return
		}
		w.Header().Set("Content-Type", "application/json")
		_ = json.NewEncoder(w).Encode(map[string]bool{"ok": true})
	})

	mux.HandleFunc("POST /api/conversations/new", func(w http.ResponseWriter, r *http.Request) {
		newID, err := conversations.ResetActiveSession(projectDir)
		if err != nil {
			http.Error(w, err.Error(), http.StatusInternalServerError)
			return
		}
		w.Header().Set("Content-Type", "application/json")
		_ = json.NewEncoder(w).Encode(map[string]string{"id": newID})
	})

	// 4. Live Status & Task Cancellation
	mux.HandleFunc("GET /api/status", func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		liveData, err := os.ReadFile("/tmp/nobara_assistant_live.json")
		if err == nil {
			var st map[string]interface{}
			if err := json.Unmarshal(liveData, &st); err == nil {
				if pidF, ok := st["pid"].(float64); ok && pidF > 0 {
					pid := int(pidF)
					process, err := os.FindProcess(pid)
					if err == nil && process.Signal(syscall.Signal(0)) == nil {
						_, _ = w.Write(liveData)
						return
					}
				}
			}
		}

		_ = json.NewEncoder(w).Encode(map[string]interface{}{
			"status":         "IDLE",
			"last_user_text": "",
			"last_action":    "Esperando comando de voz",
		})
	})

	mux.HandleFunc("POST /api/task/cancel", func(w http.ResponseWriter, r *http.Request) {
		_ = exec.Command("pkill", "-f", "piper").Run()
		_ = exec.Command("pkill", "-f", "pw-play").Run()
		_ = exec.Command("pkill", "-f", "speak.py").Run()

		agentPidData, err := os.ReadFile("/tmp/nobara_assistant_agent.pid")
		if err == nil {
			if pid, err := strconv.Atoi(strings.TrimSpace(string(agentPidData))); err == nil {
				_ = syscall.Kill(pid, syscall.SIGTERM)
			}
			_ = os.Remove("/tmp/nobara_assistant_agent.pid")
		}

		notifData, err := os.ReadFile("/tmp/nobara_assistant_notif.id")
		if err == nil {
			idStr := strings.TrimSpace(string(notifData))
			if idStr != "" {
				_ = exec.Command("notify-send", "-C", idStr).Run()
			}
			_ = os.Remove("/tmp/nobara_assistant_notif.id")
		}

		w.Header().Set("Content-Type", "application/json")
		_ = json.NewEncoder(w).Encode(map[string]bool{"ok": true})
	})

	// 5. Hardware Sensors & MPRIS
	mux.HandleFunc("GET /api/hardware", func(w http.ResponseWriter, r *http.Request) {
		gpu, cpu, vol, summary := fastpath.GetHardwareMetrics("es")
		w.Header().Set("Content-Type", "application/json")
		_ = json.NewEncoder(w).Encode(map[string]interface{}{
			"gpu_temp": gpu,
			"cpu_temp": cpu,
			"volume":   vol,
			"summary":  summary,
		})
	})

	// 6. Test Endpoints (Voice synthesis and mic transcription)
	mux.HandleFunc("POST /api/test/voice", func(w http.ResponseWriter, r *http.Request) {
		var body struct {
			Model   string  `json:"model"`
			Speaker string  `json:"speaker"`
			Volume  float64 `json:"volume"`
		}
		_ = json.NewDecoder(r.Body).Decode(&body)
		if body.Volume <= 0 {
			body.Volume = 0.35
		}
		sampleText := "Hola, este es el panel de control del asistente de voz en Nobara Linux."
		go func() {
			_ = tts.Speak(sampleText, projectDir, body.Model, body.Speaker, body.Volume, false)
		}()
		w.Header().Set("Content-Type", "application/json")
		_ = json.NewEncoder(w).Encode(map[string]bool{"ok": true})
	})

	mux.HandleFunc("POST /api/test/mic", func(w http.ResponseWriter, r *http.Request) {
		var body struct {
			Model string `json:"model"`
			Lang  string `json:"lang"`
		}
		_ = json.NewDecoder(r.Body).Decode(&body)
		if body.Model == "" {
			body.Model = "base"
		}
		if body.Lang == "" {
			body.Lang = "es"
		}

		testWav := "/tmp/nobara_assistant_mic.wav"
		ctx, cancel := context.WithTimeout(context.Background(), 3*time.Second)
		cmd := exec.CommandContext(ctx, "pw-record", "--rate=16000", "--channels=1", "--format=s16", testWav)
		_ = cmd.Run()
		cancel()

		transcribeScript := filepath.Join(projectDir, "src", "transcribe.py")
		out, err := exec.Command("python3", transcribeScript, testWav, body.Model, body.Lang).Output()
		text := ""
		if err == nil {
			text = strings.TrimSpace(string(out))
		}

		w.Header().Set("Content-Type", "application/json")
		_ = json.NewEncoder(w).Encode(map[string]string{"text": text})
	})
}
