package agent

import (
	"bufio"
	"encoding/json"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"regexp"
	"strconv"
	"strings"
	"time"

	"nobara-voice-assistant/internal/config"
)

const (
	liveStatusFile = "/tmp/nobara_assistant_live.json"
	agentPIDFile   = "/tmp/nobara_assistant_agent.pid"
)

var resetKeywords = []*regexp.Regexp{
	regexp.MustCompile(`(?i)^nueva conversaci[oó]n`),
	regexp.MustCompile(`(?i)^nuevo tema`),
	regexp.MustCompile(`(?i)^reinicia(?:r)? (?:la )?conversaci[oó]n`),
	regexp.MustCompile(`(?i)^reinicia(?:r)? (?:el )?contexto`),
	regexp.MustCompile(`(?i)^empezar de cero`),
	regexp.MustCompile(`(?i)^empecemos de cero`),
	regexp.MustCompile(`(?i)^olvida lo anterior`),
	regexp.MustCompile(`(?i)^olvida la conversaci[oó]n`),
	regexp.MustCompile(`(?i)^limpia(?:r)? (?:el )?contexto`),
	regexp.MustCompile(`(?i)^limpia(?:r)? (?:la )?conversaci[oó]n`),
	regexp.MustCompile(`(?i)^new conversation`),
	regexp.MustCompile(`(?i)^new topic`),
	regexp.MustCompile(`(?i)^reset conversation`),
	regexp.MustCompile(`(?i)^reset (?:the )?context`),
	regexp.MustCompile(`(?i)^start over`),
	regexp.MustCompile(`(?i)^start from scratch`),
	regexp.MustCompile(`(?i)^forget (?:the )?previous`),
	regexp.MustCompile(`(?i)^forget everything`),
	regexp.MustCompile(`(?i)^clear (?:the )?context`),
	regexp.MustCompile(`(?i)^clear (?:the )?conversation`),
}

var leadingSep = regexp.MustCompile(`^[,\-:yY\s]+`)

// LiveStatus represents current agent execution state for UI monitors.
type LiveStatus struct {
	Status         string   `json:"status"`
	PID            int      `json:"pid,omitempty"`
	StartedAt      float64  `json:"started_at,omitempty"`
	UserText       string   `json:"user_text,omitempty"`
	ConversationID string   `json:"conversation_id,omitempty"`
	CurrentAction  string   `json:"current_action,omitempty"`
	ToolName       string   `json:"tool_name,omitempty"`
	ToolDetail     string   `json:"tool_detail,omitempty"`
	Logs           []string `json:"logs,omitempty"`
	LastAction     string   `json:"last_action,omitempty"`
	LastResponse   string   `json:"last_response,omitempty"`
	LastUserText   string   `json:"last_user_text,omitempty"`
	CompletedAt    float64  `json:"completed_at,omitempty"`
	UpdatedAt      float64  `json:"updated_at,omitempty"`
}

// UpdateLiveStatus writes execution state atomically to file.
func UpdateLiveStatus(st *LiveStatus) {
	st.UpdatedAt = float64(time.Now().UnixNano()) / 1e9
	data, err := json.MarshalIndent(st, "", "  ")
	if err != nil {
		return
	}
	tmp := liveStatusFile + ".tmp"
	if err := os.WriteFile(tmp, data, 0644); err == nil {
		_ = os.Rename(tmp, liveStatusFile)
	}
}

// UpdateDesktopNotification updates in-place desktop notification.
func UpdateDesktopNotification(notifID, title, body string) {
	if notifID == "" {
		return
	}
	_ = exec.Command("notify-send", "-r", notifID, "-a", "AI Voice Assistant", "-i", "system-run", "-t", "0", title, body).Run()
}

// CheckResetIntent detects if voice input requests clearing conversation session.
func CheckResetIntent(text string) (bool, string) {
	clean := strings.TrimSpace(text)
	for _, pat := range resetKeywords {
		loc := pat.FindStringIndex(clean)
		if len(loc) == 2 && loc[0] == 0 {
			remainder := clean[loc[1]:]
			remainder = leadingSep.ReplaceAllString(remainder, "")
			remainder = strings.TrimSpace(remainder)
			if remainder == "" {
				return true, ""
			}
			return false, remainder
		}
	}
	return false, clean
}

// StreamEvent represents incoming AGY streaming JSON events.
type StreamEvent struct {
	Event          string `json:"event"`
	ConversationID string `json:"conversation_id,omitempty"`
	StepUpdate     *struct {
		StepType string `json:"step_type"`
		State    string `json:"state"`
		ToolName string `json:"tool_name"`
		ToolInfo *struct {
			Parameters map[string]interface{} `json:"parameters"`
		} `json:"tool_info"`
	} `json:"step_update,omitempty"`
	Result *struct {
		Response string `json:"response"`
	} `json:"result,omitempty"`
}

// RunAgent executes AGY agent turn with real-time feedback and state tracking.
func RunAgent(cfg *config.Config, rawText, notifID string, forceNew bool) (string, error) {
	isEN := (cfg.AssistantLanguage == "en")
	isPureReset, cleanText := CheckResetIntent(rawText)

	if isPureReset {
		_ = config.UpdateValue(cfg.ConfigPath, "ACTIVE_CONVERSATION_ID", "")
		msg := "Contexto reiniciado. He iniciado una nueva conversación."
		if isEN {
			msg = "Context reset. Started a new conversation."
		}
		UpdateLiveStatus(&LiveStatus{
			Status:       "IDLE",
			LastAction:   "Contexto reiniciado",
			LastResponse: msg,
		})
		return msg, nil
	}

	activeConvID := strings.TrimSpace(cfg.ActiveConversationID)
	if forceNew || cleanText != rawText {
		activeConvID = ""
		_ = config.UpdateValue(cfg.ConfigPath, "ACTIVE_CONVERSATION_ID", "")
	}

	home, _ := os.UserHomeDir()
	brainDir := filepath.Join(home, ".gemini", "antigravity-cli", "brain")
	if activeConvID != "" {
		if fi, err := os.Stat(filepath.Join(brainDir, activeConvID)); err != nil || !fi.IsDir() {
			activeConvID = ""
			_ = config.UpdateValue(cfg.ConfigPath, "ACTIVE_CONVERSATION_ID", "")
		}
	}

	agyBin := cfg.AgyBin
	if _, err := os.Stat(agyBin); err != nil {
		agyBin = filepath.Join(home, ".local", "bin", "agy")
	}

	args := []string{"--dangerously-skip-permissions", "--output-format", "stream-json"}
	if cfg.ContinuousConversation && activeConvID != "" {
		args = append(args, "--conversation", activeConvID)
	}

	// Build prompt with KDE Plasma 6 Wayland display rules
	var prompt string
	if isEN {
		prompt = fmt.Sprintf(
			"User voice instruction on Nobara Linux (KDE Plasma 6 / Wayland): '%s'.\n"+
				"MANDATORY RULES:\n"+
				"1. SCREEN VISIBILITY: If the user asks to see, show, open programs, terminals or graphical info, "+
				"open VISIBLE windows on their main desktop using DISPLAY=:0 WAYLAND_DISPLAY=wayland-0 kstart -- <command>. "+
				"If it's an interactive terminal command (e.g. htop, btop, logs, system stats), open a VISIBLE separate Konsole: "+
				"DISPLAY=:0 WAYLAND_DISPLAY=wayland-0 kstart -- konsole --separate -e bash -c \"<command>; echo ''; read -p 'Press Enter to close...'\"\n"+
				"NEVER leave graphical apps running hidden in the background.\n"+
				"2. SYSTEM ACTIONS: If the user asks for background actions (volume, music pause, querying RAM/CPU stats for speech), execute directly with bash without opening unnecessary windows.\n"+
				"3. LANGUAGE & CONCISENESS: Respond STRICTLY in English. Keep your response very concise and direct (maximum 1 or 2 sentences) as it will be read aloud by TTS and shown in a notification.",
			cleanText,
		)
	} else {
		prompt = fmt.Sprintf(
			"Instrucción de voz del usuario en Nobara Linux (KDE Plasma 6 / Wayland): '%s'.\n"+
				"REGLAS OBLIGATORIAS:\n"+
				"1. VISUALIZACIÓN EN PANTALLA: Si el usuario pide ver, mostrar, abrir programas, terminales o información gráfica, "+
				"abre ventanas VISIBLES en su escritorio principal con DISPLAY=:0 WAYLAND_DISPLAY=wayland-0 kstart -- <comando>. "+
				"Si es un comando de consola que el usuario quiere ver en directo (ej. htop, btop, logs, monitores), abre un terminal de Konsole VISIBLE e independiente: "+
				"DISPLAY=:0 WAYLAND_DISPLAY=wayland-0 kstart -- konsole --separate -e bash -c \"<comando>; echo ''; read -p 'Presiona Enter para cerrar...'\"\n"+
				"NUNCA dejes aplicaciones gráficas en segundo plano ocultas.\n"+
				"2. ACCIONES DEL SISTEMA: Si pide cambiar volumen, pausar, o consultar datos para voz, ejecútalo directamente con bash sin abrir ventanas.\n"+
				"3. RESPUESTA: Responde ESTRICTAMENTE en español. Responde de forma muy concisa y directa (máximo 1 o 2 frases) ya que tu respuesta se leerá por voz y en notificación.",
			cleanText,
		)
	}
	args = append(args, "-p", prompt)

	cmd := exec.Command(agyBin, args...)
	cmd.Env = os.Environ()
	cmd.Env = append(cmd.Env,
		"DISPLAY=:0",
		"WAYLAND_DISPLAY=wayland-0",
		"XDG_CURRENT_DESKTOP=KDE",
		"KDE_FULL_SESSION=true",
		fmt.Sprintf("PATH=%s/.gemini/antigravity-cli/bin:%s/.local/bin:/usr/local/bin:/usr/bin:/bin:%s", home, home, os.Getenv("PATH")),
	)

	stdout, err := cmd.StdoutPipe()
	if err != nil {
		return "", err
	}

	if err := cmd.Start(); err != nil {
		return "", fmt.Errorf("failed to start AGY: %v", err)
	}

	pid := cmd.Process.Pid
	_ = os.WriteFile(agentPIDFile, []byte(strconv.Itoa(pid)), 0644)
	defer os.Remove(agentPIDFile)

	startTime := float64(time.Now().UnixNano()) / 1e9
	initAction := "Analizando orden..."
	if isEN {
		initAction = "Analyzing instruction..."
	}

	statusConvID := activeConvID
	if statusConvID == "" {
		statusConvID = "Iniciando nueva sesión..."
		if isEN {
			statusConvID = "Starting new session..."
		}
	}

	st := &LiveStatus{
		Status:         "RUNNING",
		PID:            pid,
		StartedAt:      startTime,
		UserText:       cleanText,
		ConversationID: statusConvID,
		CurrentAction:  initAction,
		Logs:           []string{fmt.Sprintf("[%s] Entrada: '%s'", time.Now().Format("15:04:05"), cleanText)},
	}
	UpdateLiveStatus(st)

	if notifID != "" {
		pTitle := "Procesando orden..."
		pBody := fmt.Sprintf("Interpretando: %s", truncate(cleanText, 45))
		if isEN {
			pTitle = "Processing order..."
			pBody = fmt.Sprintf("Interpreting: %s", truncate(cleanText, 45))
		}
		UpdateDesktopNotification(notifID, pTitle, pBody)
	}

	var finalResponse string
	assignedConvID := activeConvID
	scanner := bufio.NewScanner(stdout)

	for scanner.Scan() {
		line := strings.TrimSpace(scanner.Text())
		if line == "" {
			continue
		}

		var ev StreamEvent
		if err := json.Unmarshal([]byte(line), &ev); err != nil {
			continue
		}

		switch ev.Event {
		case "init":
			if ev.ConversationID != "" {
				assignedConvID = ev.ConversationID
				if cfg.ContinuousConversation {
					_ = config.UpdateValue(cfg.ConfigPath, "ACTIVE_CONVERSATION_ID", assignedConvID)
				}
				st.ConversationID = assignedConvID
				st.Logs = append(st.Logs, fmt.Sprintf("[%s] Sesión conectada: %s", time.Now().Format("15:04:05"), truncate(assignedConvID, 8)))
				UpdateLiveStatus(st)
			}

		case "step_update":
			if ev.StepUpdate == nil {
				continue
			}
			su := ev.StepUpdate

			if su.StepType == "tool" && su.State == "ACTIVE" {
				tName := su.ToolName
				cmdLine := ""
				actionSummary := ""
				if su.ToolInfo != nil && su.ToolInfo.Parameters != nil {
					if c, ok := su.ToolInfo.Parameters["CommandLine"].(string); ok {
						cmdLine = c
					}
					if s, ok := su.ToolInfo.Parameters["toolSummary"].(string); ok {
						actionSummary = s
					}
				}

				displayAction := fmt.Sprintf("Usando %s", tName)
				if isEN {
					displayAction = fmt.Sprintf("Using %s", tName)
				}
				if cmdLine != "" {
					displayAction = fmt.Sprintf("Ejecutando: %s", truncate(cmdLine, 50))
					if isEN {
						displayAction = fmt.Sprintf("Executing: %s", truncate(cmdLine, 50))
					}
				} else if actionSummary != "" {
					displayAction = fmt.Sprintf("Acción: %s", actionSummary)
					if isEN {
						displayAction = fmt.Sprintf("Action: %s", actionSummary)
					}
				}

				st.CurrentAction = displayAction
				st.ToolName = tName
				st.ToolDetail = cmdLine
				if st.ToolDetail == "" {
					st.ToolDetail = actionSummary
				}
				st.Logs = append(st.Logs, fmt.Sprintf("[%s] %s", time.Now().Format("15:04:05"), displayAction))
				UpdateLiveStatus(st)

				if notifID != "" {
					title := "Ejecutando..."
					if isEN {
						title = "Executing..."
					}
					UpdateDesktopNotification(notifID, title, displayAction)
				}

			} else if su.StepType == "agent_response" && su.State == "ACTIVE" {
				st.CurrentAction = "Generando respuesta..."
				if isEN {
					st.CurrentAction = "Generating response..."
				}
				UpdateLiveStatus(st)
			}

		case "result":
			if ev.Result != nil {
				finalResponse = strings.TrimSpace(ev.Result.Response)
			}
		}
	}

	_ = cmd.Wait()

	// Clean internal noise from response
	var cleanedLines []string
	for _, l := range strings.Split(finalResponse, "\n") {
		trimmed := strings.TrimSpace(l)
		if strings.Contains(trimmed, "warning: --mode auto") || strings.Contains(trimmed, "jetski:") {
			continue
		}
		cleanedLines = append(cleanedLines, l)
	}
	finalResponse = strings.TrimSpace(strings.Join(cleanedLines, "\n"))

	if finalResponse == "" {
		finalResponse = "Orden completada."
		if isEN {
			finalResponse = "Order completed."
		}
	}

	elapsed := float64(time.Now().UnixNano())/1e9 - startTime
	UpdateLiveStatus(&LiveStatus{
		Status:         "IDLE",
		LastAction:     fmt.Sprintf("Completado en %.1fs", elapsed),
		LastResponse:   finalResponse,
		LastUserText:   cleanText,
		ConversationID: assignedConvID,
		CompletedAt:    float64(time.Now().UnixNano()) / 1e9,
	})

	return finalResponse, nil
}

func truncate(s string, maxLen int) string {
	if len(s) <= maxLen {
		return s
	}
	return s[:maxLen] + "..."
}
